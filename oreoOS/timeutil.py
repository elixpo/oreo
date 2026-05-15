"""Time + NTP helpers shared by the home clock, Settings, and notif panel."""

_DAYS  = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MONTHS = ("", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

try:
    from datetime import datetime as _DT

    def now():
        """Return (hour, minute, second, weekday_str, day, month_str, year)."""
        n = _DT.now()
        return (n.hour, n.minute, n.second,
                _DAYS[n.weekday()], n.day, _MONTHS[n.month], n.year)

except ImportError:
    import time as _t

    def now():
        t = _t.localtime()
        return (t[3], t[4], t[5], _DAYS[t[6]], t[2], _MONTHS[t[1]], t[0])


# ── NTP sync ────────────────────────────────────────────────────────────
# Shared by the boot path (one-shot at startup) AND by the manual "Sync"
# actions in the notification panel and the Settings app. Module-level
# status is the source of truth for both surfaces so they agree on what
# the last sync attempt did.

_last_sync_status = "never"     # "never" | "ok" | "no-wifi" | "failed"
_last_sync_ts     = 0           # epoch seconds of the last successful sync


def last_sync_status():
    return _last_sync_status


def last_sync_ts():
    return _last_sync_ts


def sync_from_ntp(timezone_offset_h=None):
    """Pull NTP time once, shift by the user's timezone offset, and write
    the RTC. Returns (ok, message).

    Blocks for ~2 s on success, returns immediately on no-wifi. Safe to
    call from a UI event handler — exceptions are caught and surfaced
    through the return value plus `last_sync_status()`.
    """
    global _last_sync_status, _last_sync_ts

    # WiFi gate — the radio sometimes lingers as "connected" right after
    # disconnect, so we still wrap the NTP call in try/except below.
    try:
        from oreoWare import wifi
        if not wifi.is_connected():
            _last_sync_status = "no-wifi"
            return False, "no wifi"
    except Exception:
        pass

    try:
        import ntptime
        import machine
        import time as _t
        ntptime.host = "pool.ntp.org"
        ntptime.settime()

        if timezone_offset_h is None:
            try:
                from oreoOS.config import TIMEZONE_OFFSET as _TZ
                timezone_offset_h = _TZ
            except Exception:
                timezone_offset_h = 0

        if timezone_offset_h:
            shifted = _t.localtime(_t.time() + int(timezone_offset_h * 3600))
            machine.RTC().datetime(
                (shifted[0], shifted[1], shifted[2], shifted[6] + 1,
                 shifted[3], shifted[4], shifted[5], 0))

        _last_sync_ts     = _t.time()
        _last_sync_status = "ok"
        return True, "synced"
    except ImportError:
        _last_sync_status = "failed"
        return False, "no ntptime"
    except Exception as e:
        _last_sync_status = "failed"
        return False, (str(e) or "failed")[:20]
