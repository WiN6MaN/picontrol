"""Tag content format. / Format du contenu des tags.

Compatible with tags written by the original Pi Control: a tiny NDEF-like container holding two
text records, ``[system, rom]`` (for example ``["nes", "Super Mario Bros.nes"]``).

    03 <payload_len> <91|D1>   header
    per record:  01 <len+3> 54 02 'e' 'n' <text...> <terminator>
    terminators: 11 / 51 = "another record follows", FE = last record

The original decoder looked for the terminator *byte values* inside the text, so a capital "Q"
(0x51) in a ROM name truncated the record. This decoder walks the records by their declared
length instead, which makes every character safe.
Compatible avec les tags de l'original ; le décodage se fait par longueur (un « Q » ne casse plus rien).
"""

from .errors import NotOurTag

MAX_PAYLOAD = 255


def encode(values):
    """Encode a list of strings into the on-tag byte format."""
    count = len(values)
    if count == 0:
        raise ValueError("at least one record is required")
    body = bytearray()
    for index, value in enumerate(values):
        text = value.encode("utf-8")
        if len(text) + 3 > 255:
            raise ValueError("text too long: %r" % value)
        body += bytes([0x01, len(text) + 3, 0x54, 0x02]) + b"en" + text
        if index == count - 1:
            body.append(0xFE)
        else:
            body.append(0x11 if index <= count - 3 else 0x51)
    if len(body) > MAX_PAYLOAD:
        raise ValueError("content too long for a tag (%d bytes, max %d)" % (len(body), MAX_PAYLOAD))
    return bytes([0x03, len(body), 0x91 if count >= 2 else 0xD1]) + bytes(body)


def decode(buf):
    """Decode the on-tag bytes into a list of strings. Raises NotOurTag if the content is not valid."""
    if len(buf) < 3 or buf[0] != 0x03:
        raise NotOurTag("no Pi Control data on this tag")
    records = []
    pos = 3
    while True:
        if pos + 6 > len(buf):
            raise NotOurTag("truncated data")
        text_len = buf[pos + 1] - 3
        if text_len < 0:
            raise NotOurTag("invalid record")
        start, end = pos + 6, pos + 6 + text_len
        if end >= len(buf):
            raise NotOurTag("truncated data")
        raw = bytes(buf[start:end])
        try:
            records.append(raw.decode("utf-8"))
        except UnicodeDecodeError:
            records.append(raw.decode("latin-1"))
        terminator = buf[end]
        if terminator == 0xFE:
            return records
        if terminator not in (0x11, 0x51):
            raise NotOurTag("invalid record terminator 0x%02X" % terminator)
        pos = end + 1
