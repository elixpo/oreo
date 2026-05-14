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
        ble = _get_ble()
        ble.active(on)
        if on:
            _apply_power_cap(ble)
        return True
    except Exception:
        return False


def _apply_power_cap(ble):
    """Start advertising at the secrets-baked interval so BT's average RF
    duty (and therefore its average current draw) is capped.

    BLE peak TX current is tiny compared to WiFi (~7-15 mA), but during
    discovery the radio TXes every advertising interval. A 500 ms interval
    keeps discovery snappy while reducing average current ~5x vs the
    default ~100 ms. Only fires when BT was just brought up.
    """
    try:
        from secrets import BT_ADV_INTERVAL_MS
        # MicroPython gap_advertise takes microseconds.
        ble.gap_advertise(int(BT_ADV_INTERVAL_MS) * 1000)
    except Exception:
        pass


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
