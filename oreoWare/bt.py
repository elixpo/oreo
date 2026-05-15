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


# ── discovery state (BLE central-role scan) ─────────────────────────────
# scan_results is mac_str → entry with {name, mac, rssi, appearance,
# services, type, last_seen_ms}. Updated from the _IRQ_SCAN_RESULT handler
# below; consumed by apps/bt for the Nearby list.

_scan_results = {}
_scan_active  = False

# Appearance ranges we DROP from the Nearby list. Bluetooth appearance is
# a 16-bit field laid out as 10-bit category + 6-bit subtype, so each
# 0x40-wide window is one category.
_FILTERED_APPEARANCES = (
    (0x0840, 0x087F),   # Audio Sink (speakers, soundbars)
    (0x0880, 0x08BF),   # Audio Source
    (0x0940, 0x097F),   # Wearable Audio (earbuds, headphones)
    (0x0980, 0x09BF),   # Hearing aid
    (0x09C0, 0x09FF),   # Microphone subcategory
)

# Service-UUID blocklist (16-bit profiles) — secondary filter for devices
# that don't advertise an appearance.
_AUDIO_SERVICE_UUIDS = (
    0x110A, 0x110B, 0x110C, 0x110D, 0x110E,   # A2DP / AVRCP
    0x1108, 0x111E, 0x1112,                    # Headset / HFP
    0x184E, 0x184F, 0x1850, 0x1851, 0x1852,   # LE Audio profiles
)


def _is_audio_appearance(app):
    if app is None:
        return False
    for lo, hi in _FILTERED_APPEARANCES:
        if lo <= app <= hi:
            return True
    return False


def _has_audio_service(services):
    for s in services:
        if s in _AUDIO_SERVICE_UUIDS:
            return True
    return False


def _classify_appearance(app):
    """Return a short tag for the type column. Unknown → 'other'."""
    if app is None:
        return "other"
    if 0x0040 <= app <= 0x007F: return "phone"
    if 0x0080 <= app <= 0x00BF: return "computer"
    if 0x00C0 <= app <= 0x00FF: return "watch"
    if 0x0140 <= app <= 0x017F: return "display"   # incl. tablet
    return "other"


# AD record types (BT Core Spec 5.x Vol 3 Part C 18.x)
_AD_FLAGS              = 0x01
_AD_INCOMPLETE_UUID16  = 0x02
_AD_COMPLETE_UUID16    = 0x03
_AD_SHORT_NAME         = 0x08
_AD_COMPLETE_NAME      = 0x09
_AD_APPEARANCE         = 0x19


def _parse_adv(adv_data):
    """Walk AD structures. Returns (name_or_None, appearance_or_None,
    [uuid16, ...]). Tolerates malformed payloads — we never trust a peer
    advertiser to be conformant."""
    name       = None
    appearance = None
    services   = []
    if not adv_data:
        return name, appearance, services
    i = 0
    n = len(adv_data)
    while i < n:
        try:
            ln = adv_data[i]
        except IndexError:
            break
        if ln == 0:
            break
        if i + ln >= n:
            break
        ad_type = adv_data[i + 1]
        payload = adv_data[i + 2 : i + 1 + ln]
        if ad_type in (_AD_COMPLETE_NAME, _AD_SHORT_NAME):
            try:
                name = bytes(payload).decode("utf-8")
            except Exception:
                name = None
        elif ad_type == _AD_APPEARANCE and len(payload) >= 2:
            appearance = payload[0] | (payload[1] << 8)
        elif ad_type in (_AD_INCOMPLETE_UUID16, _AD_COMPLETE_UUID16):
            for j in range(0, len(payload), 2):
                if j + 1 < len(payload):
                    services.append(payload[j] | (payload[j + 1] << 8))
        i += 1 + ln
    return name, appearance, services


def _mac_str(addr_bytes):
    try:
        return ":".join("%02X" % b for b in bytes(addr_bytes))
    except Exception:
        return "??:??:??:??:??:??"


# ── discovery API used by apps/bt ───────────────────────────────────────

def own_name():
    """Return the GAP Complete Local Name the badge advertises as."""
    try:
        return _get_ble().config("gap_name")
    except Exception:
        return DEVICE_NAME


def own_mac():
    """Public BLE MAC as 'AA:BB:CC:DD:EE:FF'."""
    try:
        addr = _get_ble().config("mac")
        # config('mac') returns either (type, bytes) or just bytes
        # depending on the MicroPython build. Handle both.
        if isinstance(addr, tuple) and len(addr) == 2:
            return _mac_str(addr[1])
        return _mac_str(addr)
    except Exception:
        return "—"


def scan_start(duration_ms=8000):
    """Begin a BLE central-role scan. Use scan_results() any time to read
    the cumulative list; scan_is_active() reports done/in-progress."""
    global _scan_active, _scan_results
    try:
        ble = _get_ble()
        if not ble.active():
            ble.active(True)
        _register_service(ble)
    except Exception:
        return False
    _scan_results = {}
    try:
        # active scan (last arg True) so we get scan-response data,
        # which more often carries the complete local name.
        ble.gap_scan(duration_ms, 30000, 30000, True)
        _scan_active = True
        return True
    except Exception:
        _scan_active = False
        return False


def scan_stop():
    global _scan_active
    try:
        _get_ble().gap_scan(None)
    except Exception:
        pass
    _scan_active = False


def scan_is_active():
    return _scan_active


def scan_results():
    """Filtered, RSSI-sorted snapshot of discovered devices."""
    out = []
    for v in _scan_results.values():
        if _is_audio_appearance(v.get("appearance")):
            continue
        if _has_audio_service(v.get("services", [])):
            continue
        out.append(v)
    out.sort(key=lambda d: d.get("rssi", -999), reverse=True)
    return out


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
_IRQ_SCAN_RESULT        = 5
_IRQ_SCAN_DONE          = 6


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
    elif event == _IRQ_SCAN_RESULT:
        addr_type, addr, adv_type, rssi, adv_data = data
        # Each result fires many times per device per scan window; we
        # merge into the dict so the most recent RSSI + any newly
        # discovered name wins. bytes(addr) copies out of the IRQ-scoped
        # buffer so we can keep the dict entry around.
        mac  = _mac_str(bytes(addr))
        name, appearance, services = _parse_adv(bytes(adv_data))
        cur = _scan_results.get(mac)
        if cur is None:
            cur = {"mac":         mac,
                   "name":        name or "(unknown)",
                   "rssi":        rssi,
                   "appearance":  appearance,
                   "services":    services,
                   "type":        _classify_appearance(appearance)}
            _scan_results[mac] = cur
        else:
            cur["rssi"] = rssi
            if name and (cur["name"] == "(unknown)" or len(name) > len(cur["name"])):
                cur["name"] = name
            if appearance and not cur["appearance"]:
                cur["appearance"] = appearance
                cur["type"]       = _classify_appearance(appearance)
            if services:
                cur["services"] = services
    elif event == _IRQ_SCAN_DONE:
        global _scan_active
        _scan_active = False


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
        kind_label = "image"
        notif_target = "gallery"
    elif st.type_byte == b"M":
        ok = _write_text(bytes(st.buf), ext="md")
        kind_label = "markdown"
        notif_target = "reader"
    else:
        ok = _write_text(bytes(st.buf), ext="txt")
        kind_label = "text"
        notif_target = "reader"
    _notify(_STATUS_DONE if ok else _STATUS_WRITE_FAIL)
    if ok:
        _post_notification(kind_label, len(st.buf), notif_target)


def _post_notification(kind_label, size_bytes, target):
    """Best-effort push into the OS notification ring. oreoWare doesn't
    depend on oreoOS, so this is wrapped in try/except so the BT module
    stays importable on hosts where oreoOS isn't available."""
    try:
        from oreoOS import notifications
        notifications.push(
            "file",
            "New %s" % kind_label,
            "%d bytes via BT" % size_bytes,
            target=target,
        )
    except Exception:
        pass


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
