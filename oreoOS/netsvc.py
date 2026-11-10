"""Background network service (#118, #119).

Owns what happens around the Wi-Fi link so that no network work runs
inside a UI frame for longer than a poll:

  * boot auto-connect: begin() applies the boot gates (secrets flag, the
    Settings auto-connect switch, the brownout skip, safe mode) and starts
    wifi.auto_begin(); tick() drives wifi.auto_tick() from the run loop.
  * link-up jobs: when the link comes up (however it came up: boot
    auto-connect, a re-join, or the WiFi app), the LAN upload server is
    (re)bound and a clock sync is scheduled.
  * time sync: timeutil.sync_from_ntp() (DNS lookup + UDP query, up to a
    few seconds) runs on a one-shot _thread worker, retries with backoff
    and re-syncs every NTP_RESYNC_S.
  * keep-alive: a dropped link is noticed within POLL_MS and re-joined
    with wifi.auto_begin() (last network first, then other saved ones),
    with backoff. Boot auto-connect that found nothing is retried the
    same way, so walking into range later still connects.
  * quiet window: nothing above starts until QUIET_MS after the first
    Home frame is on the panel, so the first presses are answered at once.

Why a worker thread and not asyncio: the run loop is a plain synchronous
loop (launcher.run_app), and the slow part, socket.getaddrinfo(), is a
blocking call with no asyncio variant on MicroPython. Under asyncio it
would still stall the loop. A _thread worker releases the GIL inside the
blocking lwIP calls, so the UI keeps running. The wifi state machine
(auto_begin/auto_tick) and the HTTP listener stay on the UI thread: they
are non-blocking already and are not written to be thread-safe.

Status for the status bar and the C panel: status() / status_text().
"""

import time

try:
    import _thread
except ImportError:
    _thread = None

QUIET_MS      = 4000            # after Home appears: start nothing heavy
POLL_MS       = 1000            # link check cadence
REJOIN_S      = (5, 15, 30, 60, 120, 300)
NTP_RETRY_S   = (15, 60, 180, 600, 1800)
NTP_RESYNC_S  = 6 * 3600
NTP_FRESH_S   = 30 * 60         # a re-join this soon after a sync skips NTP
WORKER_STACK  = 8 * 1024
# Foreground apps that drive the radio themselves (manual join, scans):
# keep-alive never calls auto_begin() under them.
RADIO_OWNERS  = ("WiFi",)

_os         = None
_started    = False             # begin() ran
_secrets_ok = True              # secrets.WIFI_AUTO_CONNECT
_hold       = False             # brownout / safe mode: no automatic joins
_reason     = ""                # why boot auto-connect did not start
_link       = False
_home_ms    = None
_next_poll  = None
_jobs_due   = False
_rejoin_at  = None
_rejoin_n   = 0
_ntp_at     = None
_ntp_n      = 0
_ntp_ok_ms  = None
_ntp_last   = ""                # last result message
_busy       = False             # worker thread running
_result     = None              # (ok, msg) handed back by the worker


def _wifi():
    from oreoWare import wifi
    return wifi


def _log(msg):
    try:
        print("[net] " + msg)
    except Exception:
        pass


def _later(now, secs):
    return time.ticks_add(now, int(secs * 1000))


def _due(now, at):
    return at is not None and time.ticks_diff(now, at) >= 0


# ── boot ────────────────────────────────────────────────────────────────

def _secrets_allow():
    try:
        from secrets import WIFI_AUTO_CONNECT
        return bool(WIFI_AUTO_CONNECT)
    except Exception:
        return True


def _setting_allows():
    try:
        return bool(_os.settings_get("wifi_autoconnect", True))
    except Exception:
        return True


def _brownout():
    # MicroPython exposes BROWNOUT_RESET on most ports; an unknown
    # constant counts as "not a brownout".
    try:
        import machine
        if hasattr(machine, "BROWNOUT_RESET"):
            return machine.reset_cause() == machine.BROWNOUT_RESET
    except Exception:
        pass
    return False


def begin(os_obj, safe=False):
    """Apply the boot gates and start auto-connect without blocking.
    Returns "started" or the reason it did not start.

    A brownout reset skips Wi-Fi for this boot so a weak supply can still
    reach Home; safe mode does the same. Either hold lasts until the user
    connects by hand from the WiFi app."""
    global _os, _started, _secrets_ok, _hold, _reason
    _os = os_obj
    _started = True
    _secrets_ok = _secrets_allow()
    _hold = False
    if safe:
        _hold, _reason = True, "safe mode"
    elif _brownout():
        _hold, _reason = True, "brownout"
    elif not _secrets_ok:
        _reason = "off in secrets"
    elif not _setting_allows():
        _reason = "auto-connect off"
    else:
        _reason = ""
        try:
            _wifi().auto_begin()
            return "started"
        except Exception as e:
            _reason = "failed: %s" % e
    return _reason


def boot_settled(now=None):
    """Called by the splash while it waits. Drives auto-connect and is
    True once Wi-Fi association has started (or will not start): a boot
    that has to scan first keeps the splash until the scan has picked a
    network to join. The splash caps the wait."""
    tick(None, now)
    try:
        return _wifi().auto_state() != "scanning"
    except Exception:
        return True


def home_shown(now=None):
    """The first Home frame is on the panel: start the quiet window."""
    global _home_ms
    if _home_ms is None:
        _home_ms = time.ticks_ms() if now is None else now


def in_quiet(now=None):
    """True before Home appeared and for QUIET_MS after. Screens that
    fetch on first draw can check this and wait."""
    if _home_ms is None:
        return True
    if now is None:
        now = time.ticks_ms()
    return time.ticks_diff(now, _home_ms) < QUIET_MS


# ── run loop ────────────────────────────────────────────────────────────

def tick(foreground=None, now=None):
    """Called once per frame from the run loop. Cheap: one rate-limited
    auto_tick() and, every POLL_MS, one is_connected()."""
    global _next_poll
    if now is None:
        now = time.ticks_ms()
    wifi = _wifi()
    try:
        up = wifi.auto_tick()
    except Exception:
        up = False
    _collect(now)
    if up or _next_poll is None or _due(now, _next_poll):
        _next_poll = _later(now, POLL_MS / 1000)
        try:
            conn = bool(wifi.is_connected())
        except Exception:
            conn = False
        if conn and not _link:
            _link_up(now)
        elif not conn and _link:
            _link_down(now)
        if not conn:
            _keep_alive(now, foreground)
    if _link and not in_quiet(now):
        if _jobs_due:
            _run_link_jobs(now)
        if _due(now, _ntp_at) and not _busy:
            _start_ntp(now)


def _link_up(now):
    global _link, _hold, _rejoin_at, _rejoin_n, _jobs_due, _ntp_at, _ntp_n
    _link = True
    _hold = False           # connected, so the radio is evidently wanted
    _rejoin_at = None
    _rejoin_n = 0
    _jobs_due = True
    if (_ntp_ok_ms is None or
            time.ticks_diff(now, _ntp_ok_ms) > NTP_FRESH_S * 1000):
        _ntp_at = now
        _ntp_n = 0
    _log("link up")
    try:
        from oreoOS import perf
        perf.mark("wifi up", now)
    except Exception:
        pass


def _link_down(now):
    global _link, _jobs_due, _rejoin_at, _rejoin_n
    _link = False
    _jobs_due = False
    _rejoin_n = 0
    _rejoin_at = _later(now, REJOIN_S[0])
    _log("link lost, re-join in %d s" % REJOIN_S[0])
    try:
        from oreoOS import http_server
        http_server.stop()
    except Exception:
        pass


def _may_rejoin():
    if _hold or not _secrets_ok or not _setting_allows():
        return False
    try:
        wifi = _wifi()
        return bool(wifi.is_radio_on() and wifi.list_saved())
    except Exception:
        return False


def _keep_alive(now, foreground):
    """Not connected: schedule or fire a re-join."""
    global _rejoin_at, _rejoin_n
    if not _started:
        return
    try:
        state = _wifi().auto_state()
    except Exception:
        return
    if state in ("connecting", "scanning"):
        return              # a join or scan is already running
    if _rejoin_at is None:
        # Boot auto-connect (or the last re-join) gave up: try again later.
        if state == "no_network" and _may_rejoin():
            secs = REJOIN_S[min(_rejoin_n, len(REJOIN_S) - 1)]
            _rejoin_at = _later(now, secs)
            _log("no network, re-join in %d s" % secs)
        return
    if not _due(now, _rejoin_at):
        return
    if foreground in RADIO_OWNERS:
        return              # the WiFi app has the radio; fire after it
    if not _may_rejoin():
        _rejoin_at = None
        return
    _rejoin_at = None
    _rejoin_n += 1
    _log("re-join attempt %d" % _rejoin_n)
    try:
        _wifi().auto_begin()
    except Exception as e:
        _log("auto_begin failed: %s" % e)


def _run_link_jobs(now):
    global _jobs_due
    _jobs_due = False
    try:
        from oreoOS import http_server
        http_server.start(_os)
    except Exception as e:
        _log("http start failed: %s" % e)


# ── time sync worker ────────────────────────────────────────────────────

def _ntp_worker():
    global _result, _busy
    try:
        from oreoOS import timeutil
        r = timeutil.sync_from_ntp()
    except Exception as e:
        r = (False, str(e) or "error")
    _result = r
    _busy = False


def _start_ntp(now):
    global _ntp_at, _busy
    _ntp_at = None
    if _thread is None:
        # No threads on this build: the old inline sync, after the quiet
        # window at least.
        _busy = True
        _ntp_worker()
        _collect(now)
        return
    _busy = True
    old = None
    try:
        try:
            old = _thread.stack_size(WORKER_STACK)
        except Exception:
            old = None
        _thread.start_new_thread(_ntp_worker, ())
    except Exception as e:
        _busy = False
        _ntp_finished(now, False, "no thread: %s" % e)
    finally:
        if old:
            try:
                _thread.stack_size(old)
            except Exception:
                pass


def _collect(now):
    global _result
    r = _result
    if r is None or _busy:
        return
    _result = None
    _ntp_finished(now, r[0], r[1])


def _ntp_finished(now, ok, msg):
    global _ntp_at, _ntp_n, _ntp_ok_ms, _ntp_last
    _ntp_last = msg
    if ok:
        _ntp_n = 0
        _ntp_ok_ms = now
        _ntp_at = _later(now, NTP_RESYNC_S)
        _log("time synced")
        return
    if msg == "busy":
        secs = 5            # a manual sync is running; check back soon
    else:
        secs = NTP_RETRY_S[min(_ntp_n, len(NTP_RETRY_S) - 1)]
        _ntp_n += 1
    _ntp_at = _later(now, secs)
    _log("time sync failed (%s), retry in %d s" % (msg, secs))


def request_sync(now=None):
    """Ask for a clock sync on the worker instead of on the UI thread
    (for the panel's and Settings' "Sync" rows). False when offline."""
    global _ntp_at, _ntp_n
    if not _link:
        return False
    _ntp_at = time.ticks_ms() if now is None else now
    _ntp_n = 0
    return True


# ── status ──────────────────────────────────────────────────────────────

def status(now=None):
    """(state, seconds). state is one of "connected", "connecting",
    "retrying" (seconds until the next try), "off" (radio off),
    "offline" (nothing scheduled: auto-connect off, held, or no saved
    network)."""
    if now is None:
        now = time.ticks_ms()
    try:
        wifi = _wifi()
        if wifi.is_connected():
            return ("connected", 0)
        if not wifi.is_radio_on():
            return ("off", 0)
        if wifi.auto_state() in ("connecting", "scanning"):
            return ("connecting", 0)
    except Exception:
        return ("offline", 0)
    if _rejoin_at is not None:
        ms = time.ticks_diff(_rejoin_at, now)
        return ("retrying", max(0, (ms + 999) // 1000))
    return ("offline", 0)


def status_text(now=None):
    state, secs = status(now)
    if state == "retrying":
        return "retrying in %d s" % secs
    if state == "off":
        return "Wi-Fi off"
    return state


def time_status():
    """("synced" | "syncing" | "pending" | "failed" | "never", detail)."""
    if _busy:
        return ("syncing", "")
    if _ntp_ok_ms is not None:
        return ("synced", _ntp_last)
    if _ntp_last:
        return ("failed", _ntp_last)
    if _ntp_at is not None:
        return ("pending", "")
    return ("never", "")


def held_reason():
    """Why boot auto-connect did not start ("" when it did)."""
    return _reason
