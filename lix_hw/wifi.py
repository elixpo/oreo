"""WiFi manager for the Elixpo Badge.

Usage:
    from lix_hw import wifi
    wifi.connect_from_config()   # reads config.py, connects in background
    wifi.is_connected()          # True / False
    wifi.ip()                    # "192.168.x.x" or None
"""

import network
import time

_wlan = None


def _get_wlan():
    global _wlan
    if _wlan is None:
        _wlan = network.WLAN(network.STA_IF)
    return _wlan


def connect(ssid, password, timeout_ms=12000):
    """Connect to WiFi. Returns True on success, False on timeout."""
    wlan = _get_wlan()
    wlan.active(True)
    if wlan.isconnected() and wlan.config("essid") == ssid:
        return True
    wlan.connect(ssid, password)
    start = time.ticks_ms()
    while not wlan.isconnected():
        if time.ticks_diff(time.ticks_ms(), start) > timeout_ms:
            return False
        time.sleep_ms(200)
    return True


def connect_from_config():
    """Read config.py and connect if WIFI_AUTO_CONNECT is True."""
    try:
        import config
        if not config.WIFI_AUTO_CONNECT:
            return False
        return connect(config.WIFI_SSID, config.WIFI_PASSWORD)
    except Exception:
        return False


def disconnect():
    wlan = _get_wlan()
    wlan.disconnect()
    wlan.active(False)


def is_connected():
    try:
        return _get_wlan().isconnected()
    except Exception:
        return False


def ip():
    try:
        wlan = _get_wlan()
        if wlan.isconnected():
            return wlan.ifconfig()[0]
    except Exception:
        pass
    return None


def rssi():
    """Signal strength in dBm, or None."""
    try:
        return _get_wlan().status("rssi")
    except Exception:
        return None
