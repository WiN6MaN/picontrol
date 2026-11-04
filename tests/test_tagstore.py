import pytest

from fakes import Card
from picontrol import tagstore
from picontrol.errors import NotOurTag


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


def test_seven_byte_tags_are_unsupported(reader, sim):
    sim.place(Card([1, 2, 3, 4, 5, 6, 7]))
    uid = reader.read_uid()
    with pytest.raises(NotOurTag):
        tagstore.read_records(reader, uid)
    with pytest.raises(NotOurTag):
        tagstore.write_records(reader, uid, ["a", "b"])


def test_capacity_constants():
    assert tagstore.DATA_BLOCKS[:4] == [4, 5, 6, 8]
    assert all(b % 4 != 3 for b in tagstore.DATA_BLOCKS)
    assert tagstore.CAPACITY == 45 * 16
