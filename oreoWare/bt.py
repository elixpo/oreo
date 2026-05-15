"""Bluetooth (BLE) manager for the Oreo Badge.

Advertises as **Oreo** (GAP Complete Local Name). Exposes a tiny custom
GATT service so a paired phone / laptop can push a single image or text
document to the badge:

  Service: 6f72-656f-0000-1000-8000-00805f9b34fb   ("oreo" in ASCII)
  Char RX (write):    ...0001-...   host  → badge   (chunked payload)
  Char TX (notify):   ...0002-...   badge → host    (status codes)

Wire format on RX (concatenated across one or many writes):

  +------+----+----+----+----+----------------+--------+
  | type | length (4B, big-endian)            | bytes  | crc32 (4B)
  +------+----+----+----+----+----------------+--------+
   1B    └──────── 4 bytes ────────┘   payload (length B)

  type=b'I'  image    (raw bytes, written as-is — must be < IMAGE_MAX bytes)
  type=b'T'  text     (deflate-compressed UTF-8 — decompressed on landing)
  type=b'M'  markdown (deflate-compressed UTF-8 — rendered by the reader app)

Routing (per the v1 decision):
  images   → apps/gallery/assets/raw/bt_<ts>.<ext>
  text     → documents/bt_<ts>.txt
  markdown → documents/bt_<ts>.md

Status codes notified back over TX (single byte):
  0x01 START_OK          header accepted, sending payload
  0x02 DONE              file written successfully
  0xE1 TOO_LARGE         image payload > IMAGE_MAX
  0xE2 BAD_CRC           checksum failed
  0xE3 BAD_TYPE          unknown type byte
  0xE4 DECOMPRESS_FAIL   deflate raised
  0xE5 WRITE_FAIL        filesystem error (likely out of space)

Usage:
    from oreoWare import bt
    bt.set_active(True)
    bt.is_active()
"""

DEVICE_NAME = "Oreo"
IMAGE_MAX   = 250 * 1024    # 250 KB hard cap on incoming images.

GALLERY_DIR  = "apps/gallery/assets/raw"
DOCUMENTS_DIR = "documents"

_STATUS_START_OK         = b"\x01"
_STATUS_DONE             = b"\x02"
_STATUS_TOO_LARGE        = b"\xE1"
_STATUS_BAD_CRC          = b"\xE2"
_STATUS_BAD_TYPE         = b"\xE3"
_STATUS_DECOMPRESS_FAIL  = b"\xE4"
_STATUS_WRITE_FAIL       = b"\xE5"


_ble        = None
_rx_handle  = None
_tx_handle  = None
_conn       = None    # current central connection handle
_rx_state   = None    # active reassembler, if any

_HEADER_LEN = 5       # type (1) + length (4)
_CRC_LEN    = 4


def _get_ble():
    global _ble
    if _ble is None:
        import bluetooth
        _ble = bluetooth.BLE()
    return _ble


def is_active():
    try:
        return _get_ble().active()
    except Exception:
        return False


def set_active(on):
    """Bring the radio up or down. On up, also registers the transfer
    service and starts advertising as 'Oreo'."""
    try:
        ble = _get_ble()
        ble.active(on)
        if on:
            _register_service(ble)
            _start_advertising(ble)
        else:
            try:
                ble.gap_advertise(None)   # stop adv
            except Exception:
                pass
        return True
    except Exception:
        return False


def toggle():
    return set_active(not is_active())


def init_from_config():
    """Enable BT on boot when the deploy-baked secrets request it."""
    try:
        from secrets import BT_AUTO_ENABLE
        if BT_AUTO_ENABLE:
            set_active(True)
    except Exception:
        pass


# ─── service registration ────────────────────────────────────────────────

def _register_service(ble):
    """Idempotent — only registers once per boot."""
    global _rx_handle, _tx_handle
    if _rx_handle is not None:
        return
    import bluetooth
    _SVC_UUID = bluetooth.UUID("6f72656f-0000-1000-8000-00805f9b34fb")
    _RX_UUID  = bluetooth.UUID("6f72656f-0001-1000-8000-00805f9b34fb")
    _TX_UUID  = bluetooth.UUID("6f72656f-0002-1000-8000-00805f9b34fb")
    rx_char = (_RX_UUID, bluetooth.FLAG_WRITE | bluetooth.FLAG_WRITE_NO_RESPONSE)
    tx_char = (_TX_UUID, bluetooth.FLAG_NOTIFY)
    svc     = (_SVC_UUID, (rx_char, tx_char))
    try:
        ((_rx_handle, _tx_handle),) = ble.gatts_register_services((svc,))
    except Exception:
        _rx_handle = _tx_handle = None
        return
    # Allow the RX char to buffer a single MTU's worth — we drain it
    # every IRQ so this is sized for one chunk, not the whole file.
    try:
        ble.gatts_set_buffer(_rx_handle, 512, True)
    except Exception:
        pass
    ble.irq(_irq)


# ─── advertising ─────────────────────────────────────────────────────────

def _adv_payload(name):
    """Build a minimal connectable adv payload: Flags (LE general disc) +
    Complete Local Name. Stays well under the 31-byte limit."""
    name_bytes = name.encode("utf-8")
    return (b"\x02\x01\x06"
            + bytes((len(name_bytes) + 1, 0x09)) + name_bytes)


def _start_advertising(ble):
    """Set the GAP name and start advertising at the configured interval."""
    try:
        ble.config(gap_name=DEVICE_NAME)
    except Exception:
        pass
    interval_us = 500_000
    try:
        from secrets import BT_ADV_INTERVAL_MS
        interval_us = int(BT_ADV_INTERVAL_MS) * 1000
    except Exception:
        pass
    try:
        ble.gap_advertise(interval_us, adv_data=_adv_payload(DEVICE_NAME))
    except Exception:
        pass


# ─── IRQ dispatch + reassembly ───────────────────────────────────────────

_IRQ_CENTRAL_CONNECT    = 1
_IRQ_CENTRAL_DISCONNECT = 2
_IRQ_GATTS_WRITE        = 3


class _RxState:
    """Stateful reassembler: header → payload → crc → write."""
    __slots__ = ("type_byte", "length", "buf", "crc_buf")
    def __init__(self):
        self.type_byte = None
        self.length    = None
        self.buf       = bytearray()
        self.crc_buf   = bytearray()


def _irq(event, data):
    global _conn, _rx_state
    if event == _IRQ_CENTRAL_CONNECT:
        conn_handle, _addr_type, _addr = data
        _conn = conn_handle
        _rx_state = _RxState()
    elif event == _IRQ_CENTRAL_DISCONNECT:
        _conn = None
        _rx_state = None
        # Restart advertising so the next peer can find us.
        try:
            _start_advertising(_get_ble())
        except Exception:
            pass
    elif event == _IRQ_GATTS_WRITE:
        conn_handle, attr_handle = data
        if attr_handle != _rx_handle:
            return
        chunk = _get_ble().gatts_read(_rx_handle)
        if chunk:
            _feed(chunk)


def _notify(status_byte):
    if _conn is None or _tx_handle is None:
        return
    try:
        _get_ble().gatts_notify(_conn, _tx_handle, status_byte)
    except Exception:
        pass


def _feed(chunk):
    """Push bytes into the active reassembler. May complete one transfer
    per call (or part of one — we resume across chunks)."""
    global _rx_state
    st = _rx_state
    if st is None:
        return

    pos = 0
    # Header phase — accumulate 5 bytes.
    if st.length is None:
        need = _HEADER_LEN - len(st.buf)
        st.buf.extend(chunk[pos:pos + need])
        pos += need
        if len(st.buf) < _HEADER_LEN:
            return
        st.type_byte = bytes(st.buf[0:1])
        st.length    = (st.buf[1] << 24) | (st.buf[2] << 16) \
                     | (st.buf[3] << 8)  |  st.buf[4]
        st.buf = bytearray()
        # Validate before consuming any payload.
        if st.type_byte not in (b"I", b"T", b"M"):
            _notify(_STATUS_BAD_TYPE)
            _rx_state = _RxState()
            return
        if st.type_byte == b"I" and st.length > IMAGE_MAX:
            _notify(_STATUS_TOO_LARGE)
            _rx_state = _RxState()
            return
        _notify(_STATUS_START_OK)

    # Payload phase.
    remaining = st.length - len(st.buf)
    if remaining > 0:
        take = chunk[pos:pos + remaining]
        st.buf.extend(take)
        pos += len(take)
        if len(st.buf) < st.length:
            return

    # CRC phase.
    need = _CRC_LEN - len(st.crc_buf)
    st.crc_buf.extend(chunk[pos:pos + need])
    if len(st.crc_buf) < _CRC_LEN:
        return

    _finish(st)
    _rx_state = _RxState()


def _finish(st):
    """Validate CRC and commit the payload to disk."""
    import binascii
    expected = (st.crc_buf[0] << 24) | (st.crc_buf[1] << 16) \
             | (st.crc_buf[2] << 8)  |  st.crc_buf[3]
    actual = binascii.crc32(bytes(st.buf)) & 0xFFFFFFFF
    if actual != expected:
        _notify(_STATUS_BAD_CRC)
        return

    if st.type_byte == b"I":
        ok = _write_image(bytes(st.buf))
    elif st.type_byte == b"M":
        ok = _write_text(bytes(st.buf), ext="md")
    else:
        ok = _write_text(bytes(st.buf), ext="txt")
    _notify(_STATUS_DONE if ok else _STATUS_WRITE_FAIL)


# ─── disk landing ────────────────────────────────────────────────────────

def _ensure_dir(path):
    import os
    parts = path.split("/")
    cur = ""
    for p in parts:
        cur = (cur + "/" + p) if cur else p
        try:
            os.mkdir(cur)
        except OSError:
            pass


def _ts():
    try:
        import time
        return str(time.time())
    except Exception:
        return "0"


def _sniff_image_ext(buf):
    """Best-effort magic-number sniff. Default to .bin if unknown."""
    if len(buf) >= 8 and buf[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if len(buf) >= 3 and buf[:3] == b"\xFF\xD8\xFF":
        return "jpg"
    if len(buf) >= 6 and buf[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    return "bin"


def _write_image(buf):
    try:
        _ensure_dir(GALLERY_DIR)
        ext = _sniff_image_ext(buf)
        path = GALLERY_DIR + "/bt_" + _ts() + "." + ext
        with open(path, "wb") as f:
            f.write(buf)
        return True
    except Exception:
        return False


def _write_text(buf, ext="txt"):
    """Decompress (deflate / zlib) and write to documents/.

    `ext` controls the landing extension — "txt" for plain text and "md"
    for markdown payloads. Both share the same wire compression."""
    try:
        import deflate
        import io
        plain = deflate.DeflateIO(io.BytesIO(buf)).read()
    except Exception:
        # Sender may have skipped compression for tiny payloads — accept
        # as-is if it decodes as UTF-8, otherwise fail loudly.
        try:
            buf.decode("utf-8")
            plain = buf
        except Exception:
            _notify(_STATUS_DECOMPRESS_FAIL)
            return False
    try:
        _ensure_dir(DOCUMENTS_DIR)
        path = DOCUMENTS_DIR + "/bt_" + _ts() + "." + ext
        with open(path, "wb") as f:
            f.write(plain)
        return True
    except Exception:
        return False
