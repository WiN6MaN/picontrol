"""Reading and writing records on NFC tags. / Lecture et écriture des enregistrements sur les tags NFC.

Two tag families are supported, detected automatically:
  * MIFARE Classic 1K (4-byte UID, the tags of the kit): data starts at block 4 and uses only data blocks.
    Sector trailers (every 4th block: keys and access bits) and sector 0 are never touched.
  * NTAG213/215/216 and MIFARE Ultralight (7-byte UID, SAK 0x00; NFC Forum Type 2): data starts at page 4, in the
    user memory announced by the capability container (page 3). Pages 0-3 (UID, lock bytes, capability container)
    and the configuration pages are never touched.
Deux familles de tags, détectées automatiquement : MIFARE Classic 1K et NTAG/Ultralight (UID de 7 octets).
Les zones sensibles (clés, octets de verrouillage, configuration) ne sont jamais modifiées.
"""

from . import tagformat
from .errors import NotOurTag, TagError

DATA_BLOCKS = [block for block in range(4, 64) if block % 4 != 3]
CAPACITY = len(DATA_BLOCKS) * 16
TYPE2_FIRST_PAGE = 4


def tag_kind(reader, uid):
    """"classic" or "type2"; NotOurTag for anything this reader cannot handle."""
    if len(uid) == 4:
        return "classic"
    sak = getattr(reader, "last_sak", None)
    if len(uid) == 7 and sak in (None, 0x00):
        return "type2"
    raise NotOurTag("unsupported tag type (UID of %d bytes%s): use MIFARE Classic 1K or NTAG/Ultralight tags"
                    % (len(uid), "" if sak is None else ", SAK 0x%02X" % sak))


# ---------------------------------------------------------------------- MIFARE Classic 1K
def _read_classic(reader, uid):
    """Read exactly the bytes the container declares (no scanning for empty blocks)."""
    buf = bytearray()
    need = None
    last_sector = -1
    for block in DATA_BLOCKS:
        if block // 4 != last_sector:
            reader.auth(uid, block)
            last_sector = block // 4
        buf += reader.read_block(block)
        if need is None:
            if buf[0] != 0x03:
                raise NotOurTag("no NDEF message on this tag")
            need = 3 + buf[1]
        if len(buf) >= need:
            return bytes(buf[:need])
    raise NotOurTag("truncated data")


def _write_classic(reader, uid, data):
    chunks = [data[i:i + 16].ljust(16, b"\x00") for i in range(0, len(data), 16)]
    if len(chunks) < len(DATA_BLOCKS):
        chunks.append(bytes(16))  # trailing empty block: keeps the original reader happy
    last_sector = -1
    for block, chunk in zip(DATA_BLOCKS, chunks):
        if block // 4 != last_sector:
            reader.auth(uid, block)
            last_sector = block // 4
        reader.write_block(block, chunk)


# ---------------------------------------------------------------------- NTAG / Ultralight (Type 2)
def type2_capacity(reader):
    """Size in bytes of the user memory, from the capability container in page 3."""
    cc = reader.read_block(3)[:4]
    if cc[0] != 0xE1:
        raise NotOurTag("this tag is not NDEF-formatted (no capability container)")
    size = cc[2] * 8
    if size < 8:
        raise NotOurTag("this tag reports no user memory")
    return size


def _read_type2(reader):
    size = type2_capacity(reader)
    buf = bytearray()
    need = None
    for page in range(TYPE2_FIRST_PAGE, TYPE2_FIRST_PAGE + size // 4, 4):
        buf += reader.read_block(page)  # 4 pages = 16 bytes per read
        if need is None:
            if buf[0] != 0x03:
                raise NotOurTag("no NDEF message on this tag")
            if buf[1] == 0xFF:
                raise NotOurTag("NDEF message too long for Pi Control")
            need = 3 + buf[1]
            if need > size:
                raise NotOurTag("invalid NDEF length")
        if len(buf) >= need:
            return bytes(buf[:need])
    raise NotOurTag("truncated data")


def _write_type2(reader, data):
    size = type2_capacity(reader)
    if len(data) > size:
        raise TagError("too long for this tag: %d bytes needed, it holds %d (use a larger NTAG or a shorter name)"
                       % (len(data), size))
    padded = data.ljust((len(data) + 3) // 4 * 4, b"\x00")
    for offset in range(0, len(padded), 4):
        reader.write_page(TYPE2_FIRST_PAGE + offset // 4, padded[offset:offset + 4])


# ---------------------------------------------------------------------- public API
def read_buffer(reader, uid):
    return _read_classic(reader, uid) if tag_kind(reader, uid) == "classic" else _read_type2(reader)


def read_records(reader, uid):
    return tagformat.decode(read_buffer(reader, uid))


def write_records(reader, uid, values):
    """Write ``values``; the caller should verify by reading back (see ``nfc.write_and_verify``)."""
    kind = tag_kind(reader, uid)
    data = tagformat.encode(values)
    if kind == "classic":
        _write_classic(reader, uid, data)
    else:
        _write_type2(reader, data)
