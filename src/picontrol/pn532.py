"""PN532 NFC reader driver over software SPI. / Pilote du lecteur NFC PN532 en SPI logiciel.

The Pi Control board wires the PN532 to ordinary GPIO pins (not the Pi's hardware SPI), so the SPI
bus is bit-banged here: mode 0, least-significant bit first, as the PN532 requires.
Protocol reference: NXP "PN532 User Manual" (UM0701-02), host interface and command set.

La carte câble le PN532 sur des GPIO ordinaires (pas le SPI matériel) : le bus SPI est donc émulé
par logiciel (mode 0, bit de poids faible en premier).

Design notes / Notes de conception
  * Every wait has a timeout and every failure raises ReaderError (never returns None).
  * The chip is never powered down between polls; ``init`` is the only slow operation.
  * ``read_uid`` can cut the RF field first so a tag is always seen as "fresh" (see docs/architecture).
"""

import binascii
import time

from .errors import NotOurTag, ReaderError

ACK = bytes([0x01, 0x00, 0x00, 0xFF, 0x00, 0xFF, 0x00])  # includes the leading SPI status byte
CMD_GET_FIRMWARE = 0x02
CMD_SAM_CONFIG = 0x14
CMD_RF_CONFIG = 0x32
CMD_IN_DATA_EXCHANGE = 0x40
CMD_IN_LIST_PASSIVE = 0x4A
MIFARE_READ = 0x30  # also the Type 2 (NTAG / Ultralight) READ: 4 pages = 16 bytes
MIFARE_WRITE = 0xA0
TYPE2_WRITE = 0xA2  # NTAG / Ultralight WRITE: one 4-byte page
MIFARE_AUTH_B = 0x61
DEFAULT_KEY = bytes([0xFF] * 6)


def hexstr(data):
    return binascii.hexlify(bytes(data)).decode()


class SoftSpi:
    """Bit-banged SPI master, mode 0, LSB first."""

    def __init__(self, gpio, sclk, mosi, miso):
        self.gpio, self.sclk, self.mosi, self.miso = gpio, sclk, mosi, miso

    def setup(self):
        self.gpio.setup_output(self.sclk, 0)
        self.gpio.setup_output(self.mosi, 0)
        self.gpio.setup_input(self.miso)

    def transfer(self, data):
        out = bytearray(len(data))
        write, read = self.gpio.write, self.gpio.read
        sclk, mosi, miso = self.sclk, self.mosi, self.miso
        for index, byte in enumerate(data):
            value = 0
            for bit in range(8):
                write(mosi, (byte >> bit) & 1)
                write(sclk, 1)
                if read(miso):
                    value |= 1 << bit
                write(sclk, 0)
            out[index] = value
        return out


class PN532:
    def __init__(self, gpio, cs, sclk, mosi, miso, rf_reset_each_poll=True,
                 wake_delay=1.0, ack_timeout=0.3, sleep=time.sleep):
        self.gpio, self.cs = gpio, cs
        self.spi = SoftSpi(gpio, sclk, mosi, miso)
        self.rf_reset_each_poll = rf_reset_each_poll
        self.wake_delay, self.ack_timeout, self._sleep = wake_delay, ack_timeout, sleep
        self.last_sak = None  # SAK of the tag found by the last read_uid (tells the tag families apart)
        self._setup_pins()

    def _setup_pins(self):
        self.gpio.setup_output(self.cs, 1)
        self.spi.setup()

    # ------------------------------------------------------------------ low level
    def _xfer(self, data):
        self.gpio.write(self.cs, 0)
        self._sleep(0.002)  # the PN532 needs a moment after CS goes low
        try:
            return self.spi.transfer(data)
        finally:
            self.gpio.write(self.cs, 1)

    def _write_frame(self, data):
        length = len(data)
        if not 0 < length < 255:
            raise ValueError("a frame carries 1 to 254 bytes")
        frame = bytearray(length + 8)
        frame[0] = 0x01  # SPI "data write"
        frame[2], frame[3] = 0x00, 0xFF  # start code (frame[1] is the preamble)
        frame[4] = length
        frame[5] = (~length + 1) & 0xFF
        frame[6:6 + length] = data
        frame[-2] = (~(0xFF + sum(data))) & 0xFF
        self._xfer(frame)

    def _read_data(self, count):
        frame = bytearray(count)
        frame[0] = 0x03  # SPI "data read"
        return self._xfer(frame)

    def _wait_ready(self, timeout):
        deadline = time.monotonic() + timeout
        while True:
            if self._xfer(bytearray([0x02, 0x00]))[1] == 0x01:  # SPI "status read"
                return True
            if time.monotonic() >= deadline:
                return False
            self._sleep(0.005)

    def _read_frame(self, length):
        resp = self._read_data(length + 8)
        if resp[0] != 0x01:
            raise ReaderError("invalid response header")
        pos = 1
        while pos < len(resp) and resp[pos] == 0x00:
            pos += 1
        if pos >= len(resp) or resp[pos] != 0xFF:
            raise ReaderError("invalid response preamble")
        pos += 1
        if pos + 1 >= len(resp):
            raise ReaderError("truncated response")
        size = resp[pos]
        if (size + resp[pos + 1]) & 0xFF:
            raise ReaderError("response length checksum mismatch")
        end = pos + 2 + size
        if end + 1 > len(resp):
            raise ReaderError("response too short")
        if sum(resp[pos + 2:end + 1]) & 0xFF:
            raise ReaderError("response checksum mismatch")
        return resp[pos + 2:end]

    def call(self, command, params=(), response_length=0, timeout=1.0):
        """Send a command and return its response payload. Raises ReaderError on any failure."""
        self._write_frame(bytearray([0xD4, command & 0xFF]) + bytearray(params))
        if not self._wait_ready(min(timeout, self.ack_timeout)):
            raise ReaderError("no ACK for command 0x%02X" % command)
        ack = self._read_data(len(ACK))
        if bytes(ack) != ACK:
            raise ReaderError("bad ACK: %s" % hexstr(ack))
        if not self._wait_ready(timeout):
            raise ReaderError("no response to command 0x%02X" % command)
        resp = self._read_frame(response_length + 2)
        if len(resp) < 2 or resp[0] != 0xD5 or resp[1] != ((command + 1) & 0xFF):
            raise ReaderError("unexpected response: %s" % hexstr(resp))
        return resp[2:]

    # ------------------------------------------------------------------ lifecycle
    def abort_pending(self):
        """Cancel a command the chip may still be executing (host ACK frame), best effort."""
        try:
            self._xfer(bytearray([0x01, 0x00, 0x00, 0xFF, 0x00, 0xFF, 0x00]))
            self._sleep(0.05)
            for _ in range(3):  # drain any response left in the output buffer
                if self._xfer(bytearray([0x02, 0x00]))[1] != 0x01:
                    break
                self._read_data(32)
        except Exception:  # noqa: BLE001 - cleanup must never raise
            pass

    def init(self):
        """(Re)initialise the chip: wake it, check the firmware, configure it. Returns the firmware tuple."""
        self._setup_pins()
        self.abort_pending()
        self.gpio.write(self.cs, 0)  # holding CS low wakes the PN532
        self._sleep(self.wake_delay)
        try:
            fw = self.call(CMD_GET_FIRMWARE, response_length=4)
        finally:
            self.gpio.write(self.cs, 1)
        if len(fw) < 4 or fw[0] != 0x32:
            raise ReaderError("PN532 not detected (firmware answer: %s)" % hexstr(fw))
        self.call(CMD_SAM_CONFIG, [0x01, 0x14, 0x01])  # normal mode
        # One activation attempt per poll: InListPassiveTarget returns quickly with 0 targets
        # instead of staying busy waiting for a tag.
        self.call(CMD_RF_CONFIG, [0x05, 0xFF, 0x01, 0x01])
        return fw[0], fw[1], fw[2]

    # ------------------------------------------------------------------ tags
    def rf_off(self):
        self.call(CMD_RF_CONFIG, [0x01, 0x00], timeout=0.5)

    def read_uid(self):
        """Return the UID (bytes) of the tag in the field, or None."""
        if self.rf_reset_each_poll:
            self.rf_off()
        resp = self.call(CMD_IN_LIST_PASSIVE, [0x01, 0x00], 17, timeout=1.5)
        if len(resp) == 0 or resp[0] == 0:
            return None
        if resp[0] != 1 or len(resp) < 6:
            raise ReaderError("invalid detection response: %s" % hexstr(resp))
        size = resp[5]
        if size not in (4, 7, 10) or len(resp) < 6 + size:
            raise ReaderError("unexpected UID length %d" % size)
        self.last_sak = resp[4]
        return bytes(resp[6:6 + size])

    def _exchange(self, params, response_length):
        resp = self.call(CMD_IN_DATA_EXCHANGE, params, response_length)
        if len(resp) < 1:
            raise ReaderError("empty InDataExchange response")
        return resp[0] & 0x3F, resp[1:]

    def auth(self, uid, block, key=DEFAULT_KEY):
        """Authenticate a MIFARE Classic sector with key B."""
        status, _ = self._exchange(bytes([0x01, MIFARE_AUTH_B, block & 0xFF]) + key + uid, 1)
        if status == 0x00:
            return
        if status == 0x14:
            raise NotOurTag("authentication refused (non-default keys) - foreign tag")
        raise ReaderError("authentication of block %d failed: status 0x%02X" % (block, status))

    def read_block(self, block):
        status, data = self._exchange(bytes([0x01, MIFARE_READ, block & 0xFF]), 17)
        if status != 0x00 or len(data) < 16:
            raise ReaderError("read of block/page %d failed: status 0x%02X" % (block, status))
        return bytes(data[:16])

    def write_page(self, page, data):
        """Write one 4-byte page of an NTAG / Ultralight tag."""
        if len(data) != 4:
            raise ValueError("a page is 4 bytes")
        status, _ = self._exchange(bytes([0x01, TYPE2_WRITE, page & 0xFF]) + bytes(data), 1)
        if status != 0x00:
            raise ReaderError("write of page %d failed: status 0x%02X (is the tag locked?)" % (page, status))

    def write_block(self, block, data):
        if len(data) != 16:
            raise ValueError("a block is 16 bytes")
        status, _ = self._exchange(bytes([0x01, MIFARE_WRITE, block & 0xFF]) + bytes(data), 1)
        if status != 0x00:
            raise ReaderError("write of block %d failed: status 0x%02X" % (block, status))
