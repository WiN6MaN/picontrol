import pytest

from picontrol import tagformat
from picontrol.errors import NotOurTag


def original_encode(values):
    """Byte-for-byte re-statement of the on-tag format written by the original Pi Control."""
    count = len(values)
    payload = sum(len(v) + 7 for v in values)
    buf = bytearray(payload + 3)
    buf[0], buf[1], buf[2] = 0x03, payload, (0x91 if count >= 2 else 0xD1)
    pos = 3
    for i, value in enumerate(values):
        for byte in (0x01, len(value) + 3, 0x54, 0x02, ord("e"), ord("n")):
            buf[pos] = byte
            pos += 1
        for char in value:
            buf[pos] = ord(char)
            pos += 1
        buf[pos] = 0xFE
        if count >= 2 and i <= count - 3:
            buf[pos] = 0x11
            pos += 1
        elif count >= 2 and i <= count - 2:
            buf[pos] = 0x51
            pos += 1
    return bytes(buf)


def original_decode(buf):
    """The original decoder: scans for terminator byte values."""
    out, parser = [], []
    for byte in buf[3:]:
        if byte in (0x11, 0x51, 0xFE):
            out.append("".join(chr(c) for c in parser[6:]))
            parser = []
            if byte == 0xFE:
                break
        else:
            parser.append(byte)
    return out


@pytest.mark.parametrize("values", [["nes", "Super Mario Bros.nes"], ["snes", "Zelda (USA).zip"], ["gb", "Pokemon's Red.gb"]])
def test_byte_compatible_with_the_original(values):
    assert tagformat.encode(values) == original_encode(values)
    assert tagformat.decode(original_encode(values)) == values
    assert original_decode(tagformat.encode(values)) == values


def test_capital_q_no_longer_truncates():
    values = ["arcade", "Quake Arena.zip"]
    data = tagformat.encode(values)
    assert tagformat.decode(data) == values
    assert original_decode(data) != values  # the bug of the original decoder


def test_non_ascii_names_round_trip():
    values = ["nes", "Pokémon – édition.nes"]
    assert tagformat.decode(tagformat.encode(values)) == values


def test_single_and_triple_records():
    assert tagformat.decode(tagformat.encode(["only"])) == ["only"]
    assert tagformat.decode(tagformat.encode(["a", "b", "c"])) == ["a", "b", "c"]


def test_encode_rejects_bad_input():
    with pytest.raises(ValueError):
        tagformat.encode([])
    with pytest.raises(ValueError):
        tagformat.encode(["x" * 300])
    with pytest.raises(ValueError):
        tagformat.encode(["x" * 200, "y" * 200])


@pytest.mark.parametrize("bad", [b"", b"\x00" * 20, b"\x03\x05\xd1\x01", bytes([0x03, 20, 0x91, 1, 200, 0x54]),
                                 bytes([0x03, 9, 0xD1, 0x01, 6, 0x54, 0x02, 0x65, 0x6E, 0x61, 0x62, 0x63, 0x99])])
def test_decode_rejects_garbage(bad):
    with pytest.raises(NotOurTag):
        tagformat.decode(bad)


def test_the_container_is_a_standard_ndef_message():
    data = tagformat.encode(["nes", "Zelda.nes"])
    assert data[0] == 0x03 and data[1] == len(data) - 3  # TLV length counts the message, not the final FE
    assert data[2] == 0x91 and data[-1] == 0xFE
    assert tagformat.encode(["only"])[2] == 0xD1  # a single record is MB+ME
    assert tagformat.encode(["a", "b", "c"]).count(bytes([0x11])) >= 1  # middle record header


def test_text_records_with_other_language_codes_are_read():
    message = bytes([0x91, 0x01, 1 + 5 + 3, 0x54, 0x05]) + b"fr-CA" + b"nes" + bytes([0x51, 0x01, 1 + 2 + 5, 0x54, 0x02]) + b"en" + b"a.nes"
    data = bytes([0x03, len(message)]) + message + bytes([0xFE])
    assert tagformat.decode(data) == ["nes", "a.nes"]


@pytest.mark.parametrize("bad, fragment", [
    (bytes([0x03, 0x00, 0xFE]), "empty"),
    (bytes([0x03, 0xFF, 0x91]) + bytes(300), "too long"),
    (bytes([0x03, 0x0B, 0xD1, 0x01, 0x07, 0x55, 0x04]) + b"ab.com" + bytes([0xFE]), "not a Text record"),
    (bytes([0x03, 0x07, 0x81, 0x01, 0x04, 0x54, 0x02, 0x65, 0x6E, 0x61, 0xFE]), "unexpected NDEF record header"),
    (bytes([0x03, 0x08, 0xD1, 0x01, 0x04, 0x54, 0x82, 0x65, 0x6E, 0x61, 0xFE]), "UTF-16"),
])
def test_other_ndef_content_is_refused_clearly(bad, fragment):
    with pytest.raises(NotOurTag, match=fragment):
        tagformat.decode(bad)


def test_longest_message_stays_below_the_extended_length_marker():
    assert tagformat.MAX_PAYLOAD == 254
    with pytest.raises(ValueError):
        tagformat.encode(["x" * 120, "y" * 130])
