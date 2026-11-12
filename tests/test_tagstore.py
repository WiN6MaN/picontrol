import pytest

from fakes import Card, NtagCard
from picontrol import tagstore
from picontrol.errors import NotOurTag, ReaderError, TagError


def test_write_then_read(reader, sim):
    card = Card([1, 2, 3, 4])
    sim.place(card)
    uid = reader.read_uid()
    tagstore.write_records(reader, uid, ["nes", "Super Mario Bros.nes"])
    uid = reader.read_uid()
    assert tagstore.read_records(reader, uid) == ["nes", "Super Mario Bros.nes"]


def test_trailers_and_sector_zero_are_never_touched(reader, sim):
    card = Card([1, 2, 3, 4])
    sim.place(card)
    tagstore.write_records(reader, reader.read_uid(), ["arcade", "Quake Arena.zip"])
    assert card.trailers_intact()
    assert all(bytes(card.mem[b]) == bytes(16) for b in (0, 1, 2))


def test_shorter_rewrite_replaces_longer_content(reader, sim):
    sim.place(Card([1, 2, 3, 4]))
    tagstore.write_records(reader, reader.read_uid(), ["nes", "A very long game name that spans blocks.nes"])
    tagstore.write_records(reader, reader.read_uid(), ["nes", "B.nes"])
    assert tagstore.read_records(reader, reader.read_uid()) == ["nes", "B.nes"]


def test_blank_tag_is_not_ours(reader, sim):
    sim.place(Card([5, 5, 5, 5]))
    with pytest.raises(NotOurTag):
        tagstore.read_records(reader, reader.read_uid())


def test_mifare_classic_with_a_seven_byte_uid_is_still_refused(reader, sim):
    sim.place(Card([1, 2, 3, 4, 5, 6, 7]))  # SAK 0x08: a Classic, not an NTAG
    uid = reader.read_uid()
    with pytest.raises(NotOurTag, match="unsupported tag type"):
        tagstore.read_records(reader, uid)
    with pytest.raises(NotOurTag):
        tagstore.write_records(reader, uid, ["a", "b"])


def test_capacity_constants():
    assert tagstore.DATA_BLOCKS[:4] == [4, 5, 6, 8]
    assert all(b % 4 != 3 for b in tagstore.DATA_BLOCKS)
    assert tagstore.CAPACITY == 45 * 16


# ---------------------------------------------------------------------- NTAG / Ultralight
UID7 = [0x04, 0xAF, 0x38, 0x62, 0xA1, 0x48, 0x80]  # the shape of a real NTAG UID


@pytest.mark.parametrize("size", [144, 496, 872])  # NTAG213, NTAG215, NTAG216
def test_ntag_write_then_read(reader, sim, size):
    card = NtagCard(UID7, size)
    sim.place(card)
    tagstore.write_records(reader, reader.read_uid(), ["nes", "Super Mario Bros.nes"])
    assert tagstore.read_records(reader, reader.read_uid()) == ["nes", "Super Mario Bros.nes"]


def test_ntag_protected_pages_are_never_written(reader, sim):
    card = NtagCard(UID7, 144)
    before = card.protected_pages()
    sim.place(card)
    tagstore.write_records(reader, reader.read_uid(), ["arcade", "Quake Arena.zip"])
    assert card.protected_pages() == before  # UID, lock bytes, capability container, configuration pages
    assert card.writes and min(card.writes) == 4 and max(card.writes) < 4 + 144 // 4


def test_ntag_content_is_standard_ndef(reader, sim):
    card = NtagCard(UID7)
    sim.place(card)
    tagstore.write_records(reader, reader.read_uid(), ["nes", "Zelda.nes"])
    raw = b"".join(bytes(p) for p in card.pages[4:14])
    length = raw[1]
    assert raw[0] == 0x03 and raw[2] == 0x91 and raw[2 + length] == 0xFE  # TLV | first Text record (MB) | FE after the message
    assert raw[3:9] == bytes([0x01, 0x06, 0x54, 0x02]) + b"en"  # type length, payload length, "T", UTF-8 + "en"
    assert raw[9:12] == b"nes" and raw[12] == 0x51  # the text, then the header of the last record (ME)


def test_ntag_that_is_too_small_gets_a_clear_error(reader, sim):
    sim.place(NtagCard(UID7, 48))  # Ultralight-sized
    with pytest.raises(TagError, match="too long for this tag"):
        tagstore.write_records(reader, reader.read_uid(), ["nes", "A very long ROM name that needs lots of room " * 2 + ".nes"])
    assert sim.card.writes == []  # nothing was written


def test_blank_ntag_is_not_ours(reader, sim):
    sim.place(NtagCard(UID7))  # factory state: empty NDEF message
    with pytest.raises(NotOurTag, match="empty"):
        tagstore.read_records(reader, reader.read_uid())


def test_unformatted_ntag_is_not_ours(reader, sim):
    sim.place(NtagCard(UID7, formatted=False))
    with pytest.raises(NotOurTag, match="not NDEF-formatted"):
        tagstore.read_records(reader, reader.read_uid())


def test_a_url_tag_written_by_a_phone_is_ignored(reader, sim):
    card = NtagCard(UID7)
    url = bytes([0x03, 0x0B, 0xD1, 0x01, 0x07, 0x55, 0x04]) + b"ab.com" + bytes([0xFE])  # NDEF URI record
    for i in range(0, len(url), 4):
        card.pages[4 + i // 4][:len(url[i:i + 4])] = url[i:i + 4]
    sim.place(card)
    with pytest.raises(NotOurTag, match="not a Text record"):
        tagstore.read_records(reader, reader.read_uid())


def test_a_text_tag_written_by_a_phone_app_is_read(reader, sim):
    card = NtagCard(UID7)
    first = bytes([0x01, 1 + 2 + len(b"nes"), 0x54, 0x02]) + b"fr" + b"nes"
    second = bytes([0x01, 1 + 2 + len(b"Zelda.nes"), 0x54, 0x02]) + b"fr" + b"Zelda.nes"
    message = bytes([0x91]) + first + bytes([0x51]) + second  # a phone app writes exactly this kind of message
    data = bytes([0x03, len(message)]) + message + bytes([0xFE])
    for i in range(0, len(data), 4):
        card.pages[4 + i // 4][:len(data[i:i + 4])] = data[i:i + 4]
    sim.place(card)
    assert tagstore.read_records(reader, reader.read_uid()) == ["nes", "Zelda.nes"]


def test_locked_ntag_reports_a_clear_error(reader, sim):
    card = NtagCard(UID7)
    card.locked = True
    sim.place(card)
    with pytest.raises(ReaderError, match="locked"):
        tagstore.write_records(reader, reader.read_uid(), ["nes", "Zelda.nes"])


def test_other_seven_byte_families_are_refused_with_their_sak(reader, sim):
    card = NtagCard(UID7)
    card.sak = 0x20  # e.g. NTAG 424 DNA / DESFire: ISO-DEP, not Type 2
    sim.place(card)
    with pytest.raises(NotOurTag, match="SAK 0x20"):
        tagstore.read_records(reader, reader.read_uid())


def test_the_family_is_chosen_from_the_tag_not_from_the_history(reader, sim):
    sim.place(NtagCard(UID7))
    tagstore.write_records(reader, reader.read_uid(), ["nes", "Zelda.nes"])
    sim.place(Card([1, 2, 3, 4]))  # now a Classic
    tagstore.write_records(reader, reader.read_uid(), ["snes", "Chrono Trigger.sfc"])
    assert tagstore.read_records(reader, reader.read_uid()) == ["snes", "Chrono Trigger.sfc"]
