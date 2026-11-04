"""Command line interface. / Interface en ligne de commande.

  picontrol run [--dry-run]            start the service
  picontrol tag read                   show the tag in the field
  picontrol tag write SYSTEM ROM       write a tag (or: tag write --current)
  picontrol test led|fan|buttons|nfc   hardware tests
  picontrol doctor                     check the installation
"""

import argparse
import sys

from . import __version__, doctor, hwtest
from .config import Config
from .errors import ConfigError, LaunchError, PicontrolError, ReaderError
from .launcher import Launcher
from .lock import ReaderLock
from .logging_setup import setup_logging
from .nfc import reader_from_config, write_and_verify
from .pn532 import hexstr
from .retroarch import RetroArch
from . import tagstore


def build_parser():
    parser = argparse.ArgumentParser(prog="picontrol", description="Pi Control: buttons, fan, LED and NFC for RetroPie")
    parser.add_argument("--version", action="version", version="picontrol " + __version__)
    parser.add_argument("-c", "--config", help="configuration file (default: /etc/picontrol/picontrol.conf)")
    parser.add_argument("--debug", action="store_true", help="verbose log on stderr")
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    run = sub.add_parser("run", help="run the service")
    run.add_argument("--dry-run", action="store_true", help="log what would happen; stop/start/shutdown nothing")

    tag = sub.add_parser("tag", help="read or write NFC tags").add_subparsers(dest="action", metavar="ACTION")
    tag.add_parser("read", help="show the tag in the field")
    write = tag.add_parser("write", help="write a tag")
    write.add_argument("system", nargs="?", help="system folder, e.g. nes")
    write.add_argument("rom", nargs="?", help="ROM file name, e.g. 'Super Mario Bros.nes'")
    write.add_argument("--current", action="store_true", help="write the game that is running now")
    write.add_argument("--force", action="store_true", help="write even if the ROM is not found")

    test = sub.add_parser("test", help="hardware tests")
    test.add_argument("what", choices=("led", "fan", "buttons", "nfc"))

    sub.add_parser("doctor", help="check the installation")
    return parser


def _gpio():
    from .gpio import Gpio
    try:
        return Gpio()
    except ImportError:
        raise PicontrolError("RPi.GPIO is not available (sudo apt install python3-rpi.gpio)")


def _wait_for_tag(reader, timeout=20.0):
    import time
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        uid = reader.read_uid()
        if uid:
            return uid
        time.sleep(0.3)
    return None


def cmd_tag_read(cfg):
    with ReaderLock(cfg.nfc.lock_file, wait=20) as got:
        if not got:
            print("The reader is busy.")
            return 1
        reader = reader_from_config(cfg, _gpio())
        reader.init()
        print("Present a tag...")
        uid = _wait_for_tag(reader, 15)
        if uid is None:
            print("No tag detected.")
            return 1
        print("UID:    %s" % hexstr(uid))
        try:
            records = tagstore.read_records(reader, uid)
        except PicontrolError as exc:
            print("Content: %s" % exc)
            return 0
        print("System: %s" % records[0])
        print("ROM:    %s" % (records[1] if len(records) > 1 else "(none)"))
        return 0


def cmd_tag_write(cfg, args):
    launcher = Launcher(cfg, RetroArch(cfg.retroarch.host, cfg.retroarch.port))
    if args.current:
        system, rom = launcher.current_game()
    elif args.system and args.rom:
        system, rom = args.system, args.rom
        try:
            launcher.resolve_rom(system, rom)
        except LaunchError as exc:
            if not args.force:
                print("Refused: %s (use --force to write anyway)" % exc)
                return 2
    else:
        print("Give SYSTEM and ROM, or --current.")
        return 2
    with ReaderLock(cfg.nfc.lock_file, wait=20) as got:
        if not got:
            print("The reader is busy.")
            return 1
        reader = reader_from_config(cfg, _gpio())
        reader.init()
        print("Present the tag to write (%s / %s)..." % (system, rom))
        uid = _wait_for_tag(reader, 20)
        if uid is None:
            print("No tag detected.")
            return 1
        write_and_verify(reader, uid, [system, rom])
        print("Written and verified: %s / %s" % (system, rom))
        return 0


def cmd_doctor(cfg, config_path):
    symbols = {doctor.OK: "[ OK ]", doctor.WARN: "[WARN]", doctor.FAIL: "[FAIL]"}
    failures = 0
    for status, title, detail in doctor.run_checks(cfg, config_path):
        print("%s %s%s" % (symbols[status], title, (" - " + detail) if detail else ""))
        failures += status == doctor.FAIL
    print("\n%s" % ("Everything required is in place." if not failures else "%d problem(s) to fix." % failures))
    return 1 if failures else 0


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0
    try:
        cfg = Config.load(args.config)
        setup_logging(cfg, debug=args.debug)
        if args.command == "doctor":
            return cmd_doctor(cfg, args.config)
        if args.command == "run":
            from .service import Service
            Service(cfg, gpio=_gpio(), dry_run=args.dry_run).run()
            return 0
        if args.command == "tag":
            if args.action == "read":
                return cmd_tag_read(cfg)
            if args.action == "write":
                return cmd_tag_write(cfg, args)
            parser.parse_args(["tag", "--help"])
        if args.command == "test":
            gpio = _gpio()
            return getattr(hwtest, "test_" + args.what)(cfg, gpio)
    except (ConfigError, ReaderError, LaunchError) as exc:
        print("Error: %s" % exc, file=sys.stderr)
        return 2 if isinstance(exc, ConfigError) else 1
    except PicontrolError as exc:
        print("Error: %s" % exc, file=sys.stderr)
        return 1
    return 0
