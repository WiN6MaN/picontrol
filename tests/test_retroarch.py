import socket

from picontrol.retroarch import RetroArch, read_option


def test_commands_are_sent_over_udp():
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(("127.0.0.1", 0))
    server.settimeout(2)
    ra = RetroArch("127.0.0.1", server.getsockname()[1])
    assert ra.reset() and server.recvfrom(64)[0] == b"RESET"
    assert ra.quit() and server.recvfrom(64)[0] == b"QUIT"
    server.close()


def test_dry_run_sends_nothing():
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(("127.0.0.1", 0))
    server.settimeout(0.2)
    ra = RetroArch("127.0.0.1", server.getsockname()[1], dry_run=True)
    assert ra.reset()
    try:
        server.recvfrom(64)
        raise AssertionError("a datagram was sent")
    except socket.timeout:
        pass
    server.close()


def test_send_failure_is_reported_not_raised():
    assert RetroArch("256.256.256.256", 1).send("RESET") is False


def test_read_option(tmp_path):
    cfg = tmp_path / "retroarch.cfg"
    cfg.write_text('# comment\nnetwork_cmd_enable = "true"\n#network_cmd_port = 1\nnetwork_cmd_port = "55355"\n'
                   'video_driver = gl\n\nbroken line\n')
    assert read_option(str(cfg), "network_cmd_enable") == "true"
    assert read_option(str(cfg), "network_cmd_port") == "55355"
    assert read_option(str(cfg), "video_driver") == "gl"
    assert read_option(str(cfg), "missing") is None
    assert read_option(str(tmp_path / "absent.cfg"), "x") is None
