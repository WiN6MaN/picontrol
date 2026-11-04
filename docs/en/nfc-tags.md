# NFC tags ("cartridges")

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

`write` refuses a ROM that does not exist (use `--force` to override), and always **reads the tag back** to verify. You can also hold the reset button during a game, then present a tag.

The commands wait for the reader (the service releases it between polls), so they can be used while the service runs.

## Tag compatibility

- Tags written by the original Pi Control **work unchanged**, and tags written here work with it.
- Type: MIFARE Classic 1K with default keys (4-byte UID). Foreign tags (other keys), blank tags and NTAG tags are detected and **ignored**, never launched.
- Only data blocks are written. Sector 0 and the sector trailers (keys and access bits) are never touched.

### On-tag format

```
03 <payload length> <91 | D1>                header (91 = two or more records)
per record:  01 <length+3> 54 02 'e' 'n' <text> <terminator>
terminator:  11 or 51 = another record follows, FE = last record
```

Data starts at block 4 and skips every fourth block (the trailers): capacity is 45 blocks = 720 bytes, but the container is limited to 255 bytes of payload.

One improvement over the original decoder: it located records by looking for the terminator **byte values** inside the text, so a capital `Q` (0x51) in a name cut the record short. This reader walks the records by their declared length, so every character is safe.

## Behaviour while a game runs

- A game started by a tag stops EmulationStation and restarts it afterwards. EmulationStation cannot be asked to start a game from outside, and it must release the screen and controllers first. Games started from EmulationStation itself are not affected. Tips to speed the restart up: [installation](installation.md#faster-emulationstation).
- Presenting a different tag while a game runs stops the game and launches the new one.
- `quit_on_remove = true` quits the game when its tag is removed.
- Removing and re-presenting the same tag launches again; leaving it in place does not.

## Not supported

NTAG/Ultralight tags, tags with non-default keys, a web interface for managing tags (use the commands above), and writing from a phone.
