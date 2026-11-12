import pytest

from fakes import Card, NtagCard
from picontrol.errors import NotOurTag, ReaderError
from picontrol.pn532 import PN532


def test_init_configures_the_chip(reader, sim):
    assert sim.retries_config == bytes([0xFF, 0x01, 0x01])
    assert {0x02, 0x14, 0x32} <= set(sim.commands)


def test_no_card_then_card(reader, sim):
    assert reader.read_uid() is None
    sim.place(Card([0xDE, 0xAD, 0xBE, 0xEF]))
    assert reader.read_uid() == bytes([0xDE, 0xAD, 0xBE, 0xEF])
    sim.remove()
    assert reader.read_uid() is None


def test_rf_reset_lets_a_present_tag_be_seen_on_every_poll(reader, sim):
    sim.place(Card([1, 2, 3, 4]))
    assert all(reader.read_uid() == bytes([1, 2, 3, 4]) for _ in range(10))


def test_without_rf_reset_a_selected_tag_is_not_seen_again(reader, sim):
    # worst case modelled by the simulator: this is why rf_reset_each_poll exists
    reader.rf_reset_each_poll = False
    sim.place(Card([1, 2, 3, 4]))
    assert reader.read_uid() == bytes([1, 2, 3, 4])
    assert reader.read_uid() is None


def test_seven_byte_uid(reader, sim):
    sim.place(Card([1, 2, 3, 4, 5, 6, 7]))
    assert len(reader.read_uid()) == 7


def test_block_write_and_read(reader, sim):
    card = Card([9, 9, 9, 9])
    sim.place(card)
    uid = reader.read_uid()
    reader.auth(uid, 4)
    reader.write_block(4, bytes(range(16)))
    assert reader.read_block(4) == bytes(range(16))
    assert card.mem[4] == bytearray(range(16))


def test_read_without_authentication_fails(reader, sim):
    sim.place(Card([9, 9, 9, 9]))
    reader.read_uid()
    with pytest.raises(ReaderError):
        reader.read_block(4)


def test_refused_authentication_means_foreign_tag(reader, sim):
    sim.place(Card([9, 9, 9, 9]))
    sim.deny_auth = True
    uid = reader.read_uid()
    with pytest.raises(NotOurTag):
        reader.auth(uid, 4)


def test_corrupted_response_raises_reader_error(reader, sim):
    sim.garble_next = 1
    with pytest.raises(ReaderError, match="checksum"):
        reader.read_uid()
    sim.queue = []
    assert reader.read_uid() is None  # the chip is usable again


def test_silent_chip_raises_reader_error(reader, sim):
    sim.fail_next = 1
    with pytest.raises(ReaderError, match="no ACK"):
        reader.read_uid()


def test_init_detects_a_missing_chip(gpio, cfg, sim):
    sim.fail_next = 99
    pn = PN532(gpio, cs=22, sclk=4, mosi=27, miso=17, wake_delay=0, sleep=lambda s: None)
    with pytest.raises(ReaderError):
        pn.init()


def test_abort_pending_clears_a_stuck_command(reader, sim):
    sim.queue = [b"junk", b"more"]
    reader.abort_pending()
    assert sim.queue == []


def test_the_sak_of_the_detected_tag_is_remembered(reader, sim):
    assert reader.last_sak is None
    sim.place(Card([1, 2, 3, 4]))
    reader.read_uid()
    assert reader.last_sak == 0x08
    sim.place(NtagCard([4, 1, 2, 3, 4, 5, 6]))
    reader.read_uid()
    assert reader.last_sak == 0x00


def test_write_page(reader, sim):
    card = NtagCard([4, 1, 2, 3, 4, 5, 6])
    sim.place(card)
    reader.read_uid()
    reader.write_page(10, b"abcd")
    assert bytes(card.pages[10]) == b"abcd" and reader.read_block(10)[:4] == b"abcd"
    with pytest.raises(ValueError):
        reader.write_page(10, b"abc")
    card.locked = True
    with pytest.raises(ReaderError, match="locked"):
        reader.write_page(11, b"abcd")
