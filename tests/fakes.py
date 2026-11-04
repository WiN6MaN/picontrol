"""Test doubles: a fake GPIO and a PN532 + MIFARE Classic simulator.

The simulator is wired to the *same* software-SPI pins as the real board, so the whole stack is exercised
(bit-banged LSB-first SPI, frames, checksums, ACK/response, authentication, block read/write).
"""

ACK_FRAME = bytes([0x00, 0x00, 0xFF, 0x00, 0xFF, 0x00])


class Card:
    def __init__(self, uid):
        self.uid = bytes(uid)
        self.mem = [bytearray(16) for _ in range(64)]
        for block in range(3, 64, 4):  # factory trailers: key A = key B = FF..FF
            self.mem[block][:] = bytes([0xFF] * 6 + [0xFF, 0x07, 0x80, 0x69] + [0xFF] * 6)
        self.trailers = [bytes(self.mem[b]) for b in range(3, 64, 4)]

    def trailers_intact(self):
        return [bytes(self.mem[b]) for b in range(3, 64, 4)] == self.trailers


class PN532Sim:
    def __init__(self, cs=22, sclk=4, mosi=27, miso=17):
        self.pin_cs, self.pin_sclk, self.pin_mosi, self.pin_miso = cs, sclk, mosi, miso
        self.cs, self.mosi, self.miso = 1, 0, 0
        self.rx, self.bitcount, self.cur = bytearray(), 0, 0
        self.queue = []
        self.card = None
        self.card_state = "idle"  # idle: answers REQA / active: selected (does not answer again)
        self.authed_sector = None
        self.fail_next = 0  # commands swallowed (no ACK)
        self.garble_next = 0  # responses with a bad checksum
        self.commands = []
        self.retries_config = None
        self.deny_auth = False

    @property
    def pins(self):
        return (self.pin_cs, self.pin_sclk, self.pin_mosi)

    def place(self, card):
        self.card, self.card_state, self.authed_sector = card, "idle", None

    def remove(self):
        self.card = None

    # ---- wire level
    def read(self, pin):
        return self.miso if pin == self.pin_miso else 0

    def on_pin(self, pin, old, val):
        if pin == self.pin_cs:
            if old == 1 and val == 0:
                self.rx, self.bitcount, self.cur = bytearray(), 0, 0
                self.miso = self.out_byte(0) & 1
            elif old == 0 and val == 1:
                self.end_txn()
            self.cs = val
        elif pin == self.pin_mosi:
            self.mosi = val
        elif pin == self.pin_sclk and self.cs == 0:
            if old == 0 and val == 1:  # rising edge: the slave samples MOSI (LSB first)
                self.cur |= self.mosi << self.bitcount
                self.bitcount += 1
                if self.bitcount == 8:
                    self.rx.append(self.cur)
                    self.cur, self.bitcount = 0, 0
            elif old == 1 and val == 0:  # falling edge: the slave presents the next MISO bit
                self.miso = (self.out_byte(len(self.rx)) >> self.bitcount) & 1

    def out_byte(self, index):
        if index == 0:
            return 0x01 if self.queue else 0x00
        command = self.rx[0] if self.rx else None
        if command == 0x02:
            return 0x01 if (index == 1 and self.queue) else 0x00
        if command == 0x03:
            frame = self.queue[0] if self.queue else b""
            return frame[index - 1] if index - 1 < len(frame) else 0x00
        return 0x00

    def end_txn(self):
        if not self.rx:
            return
        if self.rx[0] == 0x03 and self.queue:
            self.queue.pop(0)
        elif self.rx[0] == 0x01:
            self.handle_frame(bytes(self.rx[1:]))

    # ---- frames
    @staticmethod
    def make_frame(data):
        return bytes([0x00, 0x00, 0xFF, len(data), (-len(data)) & 0xFF]) + bytes(data) + bytes([(-sum(data)) & 0xFF, 0x00])

    def handle_frame(self, frame):
        if frame == ACK_FRAME:  # host cancels the current command
            self.queue = []
            return
        assert frame[:3] == bytes([0, 0, 0xFF]), "preamble"
        size = frame[3]
        assert (size + frame[4]) & 0xFF == 0, "length checksum"
        data = frame[5:5 + size]
        assert (sum(data) + frame[5 + size]) & 0xFF == 0, "data checksum"
        assert data[0] == 0xD4
        command, params = data[1], data[2:]
        self.commands.append(command)
        if self.fail_next > 0:
            self.fail_next -= 1
            return
        response = self.make_frame(bytes([0xD5, command + 1]) + self.execute(command, params))
        if self.garble_next > 0:
            self.garble_next -= 1
            response = response[:-2] + bytes([(response[-2] + 1) & 0xFF, 0])
        self.queue = [ACK_FRAME, response]
        self.queue[0] = bytes(ACK_FRAME)

    # ---- PN532 commands
    def execute(self, command, p):
        if command == 0x02:
            return bytes([0x32, 0x01, 0x06, 0x07])
        if command == 0x14:
            return b""
        if command == 0x32:
            if p[0] == 0x01 and p[1] == 0x00:  # RF field off: every tag is reset
                self.card_state, self.authed_sector = "idle", None
            if p[0] == 0x05:
                self.retries_config = bytes(p[1:4])
            return b""
        if command == 0x4A:
            if self.card and self.card_state == "idle":
                self.card_state, self.authed_sector = "active", None
                return bytes([1, 1, 0x00, 0x04, 0x08, len(self.card.uid)]) + self.card.uid
            return bytes([0])
        if command == 0x40:
            return self.data_exchange(bytes(p))
        raise AssertionError("unhandled command 0x%02X" % command)

    def data_exchange(self, p):
        if not self.card or self.card_state != "active":
            return bytes([0x01])  # time out: no card
        sub, block = p[1], p[2]
        if sub == 0x61:
            if self.deny_auth or p[9:13] != self.card.uid or p[3:9] != bytes([0xFF] * 6):
                return bytes([0x14])
            self.authed_sector = block // 4
            return bytes([0x00])
        if self.authed_sector != block // 4:
            return bytes([0x14])
        if sub == 0x30:
            return bytes([0x00]) + bytes(self.card.mem[block])
        if sub == 0xA0:
            self.card.mem[block][:] = p[3:19]
            return bytes([0x00])
        raise AssertionError("unhandled sub-command 0x%02X" % sub)


class FakeGpio:
    """Same four methods as picontrol.gpio.Gpio; levels are plain dict entries tests can set."""

    def __init__(self, sim=None):
        self.levels, self.modes, self.sim = {}, {}, sim
        self.writes = []  # (pin, value) for non-NFC pins

    def setup_input(self, pin, pull_up=False):
        self.modes[pin] = "in"
        self.levels.setdefault(pin, 1 if pull_up else 0)

    def setup_output(self, pin, initial=0):
        self.modes[pin] = "out"
        self.write(pin, initial)

    def read(self, pin):
        if self.sim is not None and pin == self.sim.pin_miso:
            return self.sim.read(pin)
        return self.levels.get(pin, 0)

    def write(self, pin, value):
        old = self.levels.get(pin, 0)
        self.levels[pin] = value
        if self.sim is not None and (pin in self.sim.pins):
            self.sim.on_pin(pin, old, value)
        else:
            self.writes.append((pin, value))


class FakeProcs:
    """Replaces pkill/pgrep. ``running`` holds the patterns currently 'running'."""

    def __init__(self):
        self.running, self.calls = set(), []

    def pkill(self, sig, pattern, full=False):
        self.calls.append(("pkill", sig, pattern, full))
        self.running.discard(pattern)

    def pgrep(self, pattern, full=False):
        return pattern in self.running


class FakePopen:
    instances = []

    def __init__(self, argv, **kwargs):
        self.argv, self.kwargs, self.returncode = list(argv), kwargs, None
        FakePopen.instances.append(self)

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.returncode = 0
        return 0

    def finish(self, code=0):
        self.returncode = code
