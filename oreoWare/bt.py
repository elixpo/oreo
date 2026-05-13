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
    """Enable BT on boot when the deploy-baked secrets request it.

    `config.py` lives on the build host; the deploy script snapshots its
    public attrs into `secrets.py` on the device — that's what we read here.
    """
    try:
        from secrets import BT_AUTO_ENABLE
        if BT_AUTO_ENABLE:
            set_active(True)
    except Exception:
        pass
