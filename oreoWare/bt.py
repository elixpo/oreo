"""Bluetooth (BLE) manager for the Oreo Badge.

Usage:
    from oreoWare import bt
    bt.set_active(True)
    bt.is_active()
"""

_ble = None


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
    try:
        _get_ble().active(on)
        return True
    except Exception:
        return False


def toggle():
    return set_active(not is_active())


def init_from_config():
    try:
        import config
        if config.BT_AUTO_ENABLE:
            set_active(True)
    except Exception:
        pass
