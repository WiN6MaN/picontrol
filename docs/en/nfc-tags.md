# NFC tags ("cartridges")

## NFC in a few words

An NFC tag is a tiny passive chip with no battery. The reader (the PN532 module) continuously produces a magnetic field at 13.56 MHz. When a tag comes within about 3-4 cm, the field powers it by induction - like a wireless charger - and it answers with its unique identifier (the **UID**). The reader can then read and write the tag's memory, after authenticating with a key. The MIFARE Classic 1K tags of the kit hold 1 KB, organised in blocks.

Here the tag does **not** contain the game. It holds two short texts - the system and the ROM name - and the software looks the game up on your SD card. A tag therefore works on any console that has the same ROM under the same name.

## How it works

A tag stores two pieces of text: a **system** (the RetroPie folder name, for example `nes`, `snes`, `megadrive`) and a **ROM file name** (for example `Super Mario Bros.nes`). When you present a tag the service reads it, checks that the ROM exists, and starts it through RetroPie's `runcommand.sh`.

Rules for the names:

- The system is 1-40 characters: letters, digits, `_`, `+`, `-`.
- The ROM is a **file name only** (no folders), found directly inside `roms_dir/<system>/`.
- Anything else is refused - see [SECURITY](../../SECURITY.md): tag content is untrusted input.

## Writing and reading tags

```
picontrol tag write nes "Super Mario Bros.nes"   # then present the tag
picontrol tag write --current                    # the game that is running right now
picontrol tag read                               # show UID, system and ROM
```

`write` refuses a ROM that does not exist (use `--force` to override), and always **reads the tag back** to verify. You can also hold the reset button during a game, then present a tag, or use the [web interface](web.md), which adds a game search.

The commands wait for the reader (the service releases it between polls), so they can be used while the service runs.

## Tag compatibility

- Tags written by the original Pi Control **work unchanged**, and tags written here work with it.
- Supported types, detected automatically: **MIFARE Classic 1K** (4-byte UID, the tags of the kit, default keys) and **NTAG213 / NTAG215 / NTAG216 / MIFARE Ultralight** (7-byte UID). Blank tags, tags holding something else (a web address written by a phone, for instance) and unsupported families (tags with other keys, NTAG 424 DNA, DESFire) are detected and **ignored**, never launched.
- Only user data is written. On a MIFARE Classic, sector 0 and the sector trailers (keys and access bits) are never touched; on an NTAG, the UID, lock bytes, capability container and configuration pages are never touched.
- Capacity: an NTAG213 holds 144 bytes, an NTAG215 496, an NTAG216 872 - plenty for a system and a ROM name (about 40 bytes). If a name is too long for the tag, writing is refused with a clear message.

### On-tag format

The content is a standard NFC Forum NDEF message holding two Text records (the system, then the ROM), so any NFC app can read it - and write compatible tags:

```
03 <length>                                          NDEF TLV (length = the message below)
<header> 01 <n+3> 54 02 'e' 'n' <system, n bytes>    first Text record (header 91; D1 if it is alone)
<header> 01 <m+3> 54 02 'e' 'n' <ROM, m bytes>       last Text record (header 51; 11 for a middle one)
FE                                                   terminator
```

`<header>` is the NDEF record header, `54` the type "T" (Text) and `02` the status byte (UTF-8, two-letter language code). Text records written by other apps with another language code are read too. On a MIFARE Classic the data starts at block 4 and skips every fourth block (the trailers); on an NTAG it starts at page 4. The message is limited to 254 bytes.

One improvement over the original decoder: it located records by looking for the header **byte values** inside the text, so a capital `Q` (0x51) in a name cut the record short. This reader walks the records by their declared length, so every character is safe.

## Behaviour while a game runs

- A game started by a tag stops EmulationStation and restarts it afterwards. EmulationStation cannot be asked to start a game from outside, and it must release the screen and controllers first. Games started from EmulationStation itself are not affected. Tips to speed the restart up: [installation](installation.md#faster-emulationstation).
- Presenting a different tag while a game runs stops the game and launches the new one.
- `quit_on_remove = true` quits the game when its tag is removed.
- Removing and re-presenting the same tag launches again; leaving it in place does not.

## Not supported

Tags with non-default keys, NTAG 424 DNA and DESFire tags, and writing to locked (read-only) tags. Phones are fine as a companion: any NFC app can read these tags and write compatible ones.
