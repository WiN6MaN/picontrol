"""Tag content format. / Format du contenu des tags.

The content is a standard NFC Forum NDEF message (two Text records, ``[system, rom]``, for example
``["nes", "Super Mario Bros.nes"]``) inside a standard NDEF TLV. It is exactly what the original Pi Control
wrote, so existing tags keep working, and any NFC app can read or write compatible tags.

    03 <length>                  NDEF TLV: <length> counts the message below, not the final FE
    <header> 01 <n+3> 54 02 'e' 'n' <text 1 (n bytes)>      first record   (header 91; D1 if it is the only one)
    <header> 01 <m+3> 54 02 'e' 'n' <text 2 (m bytes)>      last record    (header 51; 11 for a middle one)
    FE                           terminator TLV

``<header>`` is the NDEF record header (flags + TNF 1 "well known"), 54 is the type "T" (Text), 02 is the
status byte (UTF-8, language code of 2 letters).

The original decoder looked for those header/terminator *byte values* inside the text, so a capital "Q"
(0x51) in a ROM name truncated the record. This decoder walks the records by their declared lengths, so every
character is safe, and it reads Text records written by other apps (any language code).
Message NDEF standard (deux enregistrements Texte) : les tags existants fonctionnent, et n'importe quelle
application NFC peut lire ou écrire des tags compatibles ; décodage par longueur (un « Q » ne casse rien).
"""

from .errors import NotOurTag

MAX_PAYLOAD = 254  # a TLV length of 0xFF would announce an extended length: never produced
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
        raise NotOurTag("no NDEF message on this tag")
    if buf[1] == 0x00:
        raise NotOurTag("the NDEF message is empty")
    if buf[1] == 0xFF:
        raise NotOurTag("NDEF message too long for Pi Control")
    if buf[2] not in (0x91, 0xD1):
        raise NotOurTag("unexpected NDEF record header 0x%02X" % buf[2])
    records = []
    pos = 3  # the "type length" byte of the first record (buf[2] is its header)
    while True:
        if pos + 4 > len(buf):
            raise NotOurTag("truncated data")
        type_len, payload_len, record_type, status = buf[pos], buf[pos + 1], buf[pos + 2], buf[pos + 3]
        if type_len != 1 or record_type != 0x54:
            raise NotOurTag("not a Text record")
        if status & 0x80:
            raise NotOurTag("unsupported text encoding (UTF-16)")
        text_len = payload_len - 1 - (status & 0x3F)
        if text_len < 0:
            raise NotOurTag("invalid record")
        start = pos + 4 + (status & 0x3F)
        end = start + text_len
        if end >= len(buf):
            raise NotOurTag("truncated data")
        raw = bytes(buf[start:end])
        try:
            records.append(raw.decode("utf-8"))
        except UnicodeDecodeError:
            records.append(raw.decode("latin-1"))
        header = buf[end]
        if header == 0xFE:
            return records
        if header not in (0x11, 0x51):
            raise NotOurTag("invalid record header 0x%02X" % header)
        pos = end + 1
