"""Reading and writing records on MIFARE Classic 1K tags. / Lecture et écriture des enregistrements.

Layout: data starts at block 4 and uses only data blocks (sector trailers - every 4th block - are
never touched, so keys and access bits stay intact). Sector 0 is never written.
Les blocs « trailer » (clés, droits d'accès) et le secteur 0 ne sont jamais modifiés.
"""

from . import tagformat
from .errors import NotOurTag

DATA_BLOCKS = [block for block in range(4, 64) if block % 4 != 3]
CAPACITY = len(DATA_BLOCKS) * 16


def read_buffer(reader, uid):
    """Read exactly the bytes the container declares (no scanning for empty blocks)."""
    if len(uid) != 4:
        raise NotOurTag("not a MIFARE Classic tag (UID of %d bytes): unsupported" % len(uid))
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
                raise NotOurTag("no Pi Control data on this tag")
            need = 3 + buf[1]
        if len(buf) >= need:
            return bytes(buf[:need])
    raise NotOurTag("truncated data")


def read_records(reader, uid):
    return tagformat.decode(read_buffer(reader, uid))


def write_records(reader, uid, values):
    """Write ``values``; the caller should verify by reading back (see ``nfc.write_and_verify``)."""
    if len(uid) != 4:
        raise NotOurTag("only MIFARE Classic tags (4-byte UID) are supported")
    data = tagformat.encode(values)
    chunks = [data[i:i + 16].ljust(16, b"\x00") for i in range(0, len(data), 16)]
    if len(chunks) < len(DATA_BLOCKS):
        chunks.append(bytes(16))  # trailing empty block: keeps the original reader happy
    last_sector = -1
    for block, chunk in zip(DATA_BLOCKS, chunks):
        if block // 4 != last_sector:
            reader.auth(uid, block)
            last_sector = block // 4
        reader.write_block(block, chunk)
