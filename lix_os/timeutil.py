"""Cross-platform time helper (CPython + MicroPython)."""

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
