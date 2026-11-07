"""WiFi manager for the Oreo Badge.

Saved networks live in `/wifi.json` on flash — a user-editable list
maintained by the WiFi settings app:

    [
      {"ssid": "Home",   "password": "...", "priority": 1, "metered": false},
      {"ssid": "Hotspot","password": "...", "priority": 5, "metered": true}
    ]

Two sources can populate that list:
  • `secrets.WIFI_NETWORKS` (from `.env` via `tools/deploy.py`) — a
    list of {ssid, password, priority, metered} dicts. On every boot
    `connect_from_config()` merges this list into `/wifi.json`,
    refreshing passwords + priorities and adding any new entries
    without touching user-added networks. Edit `.env`, redeploy,
    new networks are live.
  • The on-device Settings → WiFi → Networks page — `add_saved()` /
    `remove_saved()` write the same json directly.

`.env` format is parallel CSV — first SSID matches first password:

    WIFI_SSID=home_net,elixpo_srv,office
    WIFI_PASSWORD=homepass,srvpass,officepass

`connect_from_config()` walks the merged list in ascending-priority
order (lower number = tried first) and stops on the first SSID that
associates.

Usage:
    from oreoWare import wifi
    wifi.connect_from_config()        # auto-pick best saved network
    wifi.is_connected()
    wifi.list_saved()                 # for the settings UI
    wifi.add_saved(ssid, pw, priority=10, metered=False)
    wifi.remove_saved(ssid)
    wifi.is_metered()                 # current link metered?

Non-blocking API (OreoOS 2.0). Nothing below ever waits for the radio;
callers poll from their update()/run-loop tick instead:

    wifi.scan_start()                 # background scan (own thread)
    wifi.scan_poll()                  # "busy" | "done" | "error" | "idle"
    wifi.nearby()                     # last scan, strongest first; falls
                                      # back to /wifi_seen.json from an
                                      # earlier scan so UIs paint instantly
    wifi.connect_begin(ssid, pw)      # starts association, returns at once
    wifi.connect_poll()               # CONN_* result string
    wifi.auto_begin() / auto_tick()   # boot auto-connect state machine
"""

import network
import time

try:
    import json as _json
except ImportError:
    _json = None

try:
    import os as _os
except ImportError:
    _os = None

_wlan = None

_SAVED_PATH       = "/wifi.json"
_PER_NET_TIMEOUT  = 10000   


def _get_wlan():
    global _wlan
    if _wlan is None:
        _wlan = network.WLAN(network.STA_IF)
    return _wlan


def _apply_power_cap(wlan):
    """Apply the secrets-baked TX-power dBm cap + power-save mode.

    Done as a best-effort: every `wlan.config(...)` call is wrapped in
    try/except so older / minimal MicroPython builds without one of these
    keys don't kill WiFi entirely.
    """
    try:
        from secrets import WIFI_TX_DBM
        try:
            wlan.config(txpower=int(WIFI_TX_DBM))
        except Exception:
            pass
    except Exception:
        pass
    try:
        from secrets import WIFI_POWERSAVE
        if WIFI_POWERSAVE:
            try:
                wlan.config(pm=wlan.PM_POWERSAVE)
            except Exception:
                pass
    except Exception:
        pass


MDNS_HOSTNAME = "oreo"


_hostname_applied        = False     # per-WLAN dhcp_hostname / hostname
_global_hostname_applied = False     # network.hostname() (mDNS)


def _apply_global_hostname():
    """Set the global network hostname BEFORE `wlan.active(True)`.

    This is the one that actually drives the ESP-IDF mDNS responder
    — once `network.hostname("oreo")` is set and the interface comes
    up, IDF auto-advertises `oreo.local` to the LAN. Setting it
    AFTER active(True) is a no-op on most builds because the mDNS
    service is already configured by then.

    The earlier worry that this call leaves the radio in a half-
    initialised state was misplaced — the actual culprit was IDF
    auto-connecting from cached NVS credentials, which we now
    cancel with wlan.disconnect() in connect(). Calling
    network.hostname() before any radio activity is safe.
    """
    global _global_hostname_applied
    if _global_hostname_applied:
        return
    try:
        import network as _net
        if hasattr(_net, "hostname"):
            _net.hostname(MDNS_HOSTNAME)
            _global_hostname_applied = True
    except Exception as e:
        # Older build without network.hostname() — fall through; the
        # per-WLAN dhcp_hostname applied later still gets us into the
        # router's DHCP-snooping resolver on most home gateways.
        try: print("[wifi] network.hostname() failed:", e)
        except Exception: pass


def _apply_hostname(wlan):
    """Per-WLAN hostname config (`dhcp_hostname` / `hostname`).
    Called AFTER active+disconnect so the radio is stable. The
    global mDNS broadcast was already configured by
    `_apply_global_hostname()` before active(True) — this is the
    secondary "tell the router via DHCP Option 12" path.
    """
    global _hostname_applied
    if _hostname_applied:
        return
    for key in ("dhcp_hostname", "hostname"):
        try:
            wlan.config(**{key: MDNS_HOSTNAME})
            _hostname_applied = True
        except Exception:
            pass


def radio_on():
    """Power up the radio without trying to associate. Lets the user
    flip WiFi 'on' from the Settings page even when no saved network
    is reachable — keeps the toggle from feeling broken when the
    badge is somewhere with no known WiFi nearby."""
    try:
        wlan = _get_wlan()
        wlan.active(True)
        return True
    except Exception:
        return False


def radio_off():
    """Power the radio fully down. Releases any active connection
    cleanly and saves the ~70 mA the WiFi MAC pulls in idle. Pairs
    with `radio_on()` so a UI toggle has a real on/off semantic."""
    try:
        wlan = _get_wlan()
        try: wlan.disconnect()
        except Exception: pass
        try: wlan.active(False)
        except Exception: pass
        return True
    except Exception:
        return False


def is_radio_on():
    """True iff the WiFi MAC is powered up. Distinct from
    `is_connected()`, which only flips true after a full association.
    UI 'WiFi: ON/OFF' should track this — association state is a
    sub-label on the same row."""
    try:
        return bool(_get_wlan().active())
    except Exception:
        return False


def connect(ssid, password, timeout_ms=6000, pump_cb=None):
    """Initiate a WiFi association and wait (up to `timeout_ms`) for it
    to complete.

    On ESP32-S3, IDF auto-starts a connect attempt with its own
    NVS-cached credentials the moment `wlan.active(True)` is called.
    If we don't cancel that first, every subsequent `wlan.config()`
    or `wlan.connect()` returns `Wifi Internal State Error` because
    IDF thinks "sta is already connecting". We unconditionally
    `wlan.disconnect()` + sleep briefly to flush that state before
    doing any config of our own.

    `pump_cb` is the escape-hatch from the "badge looks frozen during
    SEARCH" trap: the wait loop calls it ~12 times per second and
    bails immediately if it returns truthy.
    """
    wlan = _get_wlan()
    # Set the global hostname BEFORE bringing the radio up. The mDNS
    # responder in ESP-IDF reads it during interface init; setting
    # it later doesn't change the already-broadcast service record.
    # This is the single most important line for `oreo.local` to
    # actually resolve on the LAN.
    _apply_global_hostname()
    try:
        wlan.active(True)
    except Exception as e:
        print("[wifi] active(True) raised:", e)
        return False
    # Cancel any in-flight connect IDF kicked off on active(True). This
    # is the single most important line in this function on ESP32 —
    # without it the next wlan.config()/wlan.connect() returns "sta is
    # connecting, cannot set config" and the radio never associates to
    # the credentials we actually want.
    try:
        wlan.disconnect()
    except Exception:
        pass
    # Tiny settle window so the disconnect propagates inside the
    # IDF state machine before we issue the new connect. 50 ms is
    # enough on every build we've tested.
    time.sleep_ms(50)
    try:
        _apply_hostname(wlan)
    except Exception:
        pass
    try:
        _apply_power_cap(wlan)
    except Exception:
        pass
    try:
        if wlan.isconnected() and wlan.config("essid") == ssid:
            return True
    except Exception:
        pass
    try:
        wlan.connect(ssid, password)
    except Exception as e:
        print("[wifi] wlan.connect raised:", e)
        return False
    start = time.ticks_ms()
    while not wlan.isconnected():
        if time.ticks_diff(time.ticks_ms(), start) > timeout_ms:
            return False
        # Pump first so the very-first frame of "searching..." can be
        # cancelled. Sleep duration is intentionally short (~80 ms) so
        # button-to-cancel feels instant, but long enough that we don't
        # eat all the CPU we're trying to keep available.
        if pump_cb:
            try:
                if pump_cb():
                    print("[wifi] connect cancelled by pump_cb")
                    return False
            except Exception:
                pass
        time.sleep_ms(80)
    try:
        _apply_power_cap(wlan)
    except Exception:
        pass
    return True


def _exists(path):
    if _os is None:
        return False
    try:
        _os.stat(path)
        return True
    except OSError:
        return False


def _load_saved_raw():
    """Read `/wifi.json` as a Python list. Returns [] on missing/bad
    file — the caller is expected to bootstrap from secrets if so."""
    if _json is None or not _exists(_SAVED_PATH):
        return []
    try:
        with open(_SAVED_PATH) as f:
            data = _json.loads(f.read())
        if not isinstance(data, list):
            return []
        return data
    except Exception:
        return []


def _save_raw(networks):
    if _json is None:
        return False
    try:
        with open(_SAVED_PATH, "w") as f:
            f.write(_json.dumps(networks))
        return True
    except Exception:
        return False


def _secrets_networks():
    """Read the canonical list of deploy-time networks from secrets.py.

    Modern secrets.py (generated by `tools/deploy.py`) ships
    WIFI_NETWORKS as a list of {ssid, password, priority, metered}
    dicts. Older builds only have the singular WIFI_SSID / WIFI_PASSWORD
    pair; we wrap that into a one-entry list so callers don't care.
    Returns [] when nothing is configured.
    """
    try:
        import secrets
    except Exception:
        return []
    nets = getattr(secrets, "WIFI_NETWORKS", None)
    if isinstance(nets, (list, tuple)) and nets:
        return [dict(n) for n in nets if isinstance(n, dict) and n.get("ssid")]
    # Legacy fallback: just the first pair.
    ssid = getattr(secrets, "WIFI_SSID", "")
    pw   = getattr(secrets, "WIFI_PASSWORD", "")
    if ssid:
        return [{"ssid": ssid, "password": pw, "priority": 1, "metered": False}]
    return []


def _sync_secrets_into_saved():
    """Merge the deploy-time WIFI_NETWORKS list into /wifi.json.

    Called once per boot from connect_from_config(). Semantics:
      • Every secrets network is ENSURED to be in /wifi.json. If
        present already (matched by SSID), its priority is refreshed
        and its password is refreshed ONLY when the new password is
        non-empty — that protects a previously-working credential
        from being clobbered if the user trims their .env (e.g.
        adds a new SSID slot but doesn't add the matching
        WIFI_PASSWORD entry).
      • Networks the user added on-device that are NOT in secrets
        are preserved as-is.
      • If /wifi.json doesn't exist yet, this acts as the initial
        bootstrap (replaces the old _bootstrap_from_secrets path).
    """
    secret_nets = _secrets_networks()
    if not secret_nets:
        return
    saved = _load_saved_raw() or []
    by_ssid = {n.get("ssid", ""): n for n in saved if n.get("ssid")}
    changed   = False
    added     = 0
    refreshed = 0
    for s in secret_nets:
        ssid = s.get("ssid", "")
        if not ssid:
            continue
        existing = by_ssid.get(ssid)
        if existing is None:
            saved.append({
                "ssid":     ssid,
                "password": s.get("password", ""),
                "priority": int(s.get("priority", 10)),
                "metered":  bool(s.get("metered", False)),
            })
            changed = True
            added  += 1
            continue
        # Existing entry — refresh priority unconditionally, password
        # only if the new value is non-empty.
        new_pri = int(s.get("priority", existing.get("priority", 10)))
        new_pw  = s.get("password", "") or ""
        local_changed = False
        if int(existing.get("priority", 99)) != new_pri:
            existing["priority"] = new_pri
            local_changed = True
        if new_pw and existing.get("password") != new_pw:
            existing["password"] = new_pw
            local_changed = True
        if local_changed:
            changed    = True
            refreshed += 1
    if changed:
        _save_raw(saved)
        print("[wifi] secrets sync: +%d new, %d refreshed (of %d)" %
              (added, refreshed, len(secret_nets)))


def _bootstrap_from_secrets():
    """Compat shim — older code paths call this. Delegates to the
    sync logic and then returns the freshly-loaded list."""
    _sync_secrets_into_saved()
    return _load_saved_raw()


def list_saved():
    """Return the saved-networks list, sorted by ascending priority.
    Caller gets fresh dicts — mutating them doesn't affect on-disk state
    until save_saved() is called."""
    nets = _load_saved_raw() or _bootstrap_from_secrets()
    # Defensive copy + priority sort (None or missing → very high so
    # nameless entries sink to the bottom).
    def _key(n):
        try:
            return int(n.get("priority", 999))
        except Exception:
            return 999
    return sorted([dict(n) for n in nets if n.get("ssid")], key=_key)


def save_saved(networks):
    """Replace the entire saved list. Settings UI uses this after
    add / remove / reorder."""
    return _save_raw(list(networks))


def add_saved(ssid, password, priority=10, metered=False):
    """Add or update a single saved network. Matched by SSID; existing
    entries are overwritten so the user doesn't accumulate duplicates
    if they re-enter the same network. The "last connected" marker
    survives an update so the boot fast path keeps working."""
    nets = _load_saved_raw() or _bootstrap_from_secrets()
    last = False
    out  = []
    for n in nets:
        if n.get("ssid") == ssid:
            last = bool(n.get("last"))
        else:
            out.append(n)
    entry = {
        "ssid":     ssid,
        "password": password or "",
        "priority": int(priority),
        "metered":  bool(metered),
    }
    if last:
        entry["last"] = True
    out.append(entry)
    return _save_raw(out)


def remove_saved(ssid):
    nets = _load_saved_raw()
    out  = [n for n in nets if n.get("ssid") != ssid]
    if len(out) == len(nets):
        return False
    return _save_raw(out)


def set_priority(ssid, priority):
    nets = _load_saved_raw()
    changed = False
    for n in nets:
        if n.get("ssid") == ssid:
            n["priority"] = int(priority)
            changed = True
            break
    if not changed:
        return False
    return _save_raw(nets)


def is_metered():
    """True iff the currently-associated SSID is flagged metered in
    /wifi.json. Used by OTA + Store to back off on tethered/hotspot
    connections so we don't burn the user's data plan."""
    cur = ssid()
    if not cur:
        return False
    for n in _load_saved_raw():
        if n.get("ssid") == cur:
            return bool(n.get("metered"))
    return False


def connect_from_config(pump_cb=None):
    """Try each saved network in priority order until one associates.

    Order of operations:
      0. Merge the .env-defined WIFI_NETWORKS list into /wifi.json
         (ensures every secret network is present + has current
         creds, without clobbering user-added entries).
      1. /wifi.json — the user-managed list, edited via Settings → WiFi.
      2. secrets.py legacy single-pair bootstrap if step 0 produced
         nothing somehow.
      3. Otherwise: return False, radio stays off.

    Per-network timeout is short (_PER_NET_TIMEOUT) so a stale entry
    doesn't stall the boot.
    """
    # Pull deploy-time networks into the on-flash list. Cheap on
    # subsequent calls — only re-writes /wifi.json if something
    # actually changed since the last sync.
    try:
        _sync_secrets_into_saved()
    except Exception as e:
        print("[wifi] secrets sync failed:", e)
    nets = list_saved()
    if not nets:
        # Last-ditch: try the deploy-time secret directly. Without this
        # an empty /wifi.json silently disabled WiFi forever on freshly
        # flashed badges — the toggle on the Status row would call
        # connect_from_config(), find no saved nets, and bail without
        # ever bringing the radio up.
        try:
            import secrets
            ssid_ = getattr(secrets, "WIFI_SSID", "")
            pw    = getattr(secrets, "WIFI_PASSWORD", "")
            if ssid_:
                print("[wifi] no saved nets, falling back to secrets bootstrap")
                # Persist as the new "priority 1" entry so this branch
                # only fires once per device — subsequent connects use
                # the normal path.
                try:
                    add_saved(ssid_, pw, priority=1, metered=False)
                except Exception:
                    pass
                ok = False
                try:
                    ok = connect(ssid_, pw,
                                 timeout_ms=_PER_NET_TIMEOUT,
                                 pump_cb=pump_cb)
                except Exception:
                    pass
                return ok
        except Exception as e:
            print("[wifi] secrets bootstrap failed:", e)
        print("[wifi] no networks configured")
        return False
    for n in nets:
        ssid_ = n.get("ssid") or ""
        if not ssid_:
            continue
        pw = n.get("password") or ""
        try:
            print("[wifi] try %s (p=%s)" %
                  (ssid_, n.get("priority", "?")))
            ok = connect(ssid_, pw,
                         timeout_ms=_PER_NET_TIMEOUT,
                         pump_cb=pump_cb)
        except Exception as e:
            print("[wifi] connect raised:", e)
            ok = False
        if ok:
            print("[wifi] associated:", ssid_)
            return True
        # If the user cancelled mid-search, stop trying further
        # networks — they explicitly asked us to give up. Without
        # this we'd plough through every saved entry honouring their
        # individual timeouts.
        if pump_cb is not None:
            try:
                if pump_cb():
                    print("[wifi] connect_from_config cancelled")
                    return False
            except Exception:
                pass
    print("[wifi] all %d saved networks failed" % len(nets))
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
    try:
        return _get_wlan().status("rssi")
    except Exception:
        return None


def ssid():
    """Currently-associated SSID, or None if not connected."""
    try:
        wlan = _get_wlan()
        if wlan.isconnected():
            return wlan.config("essid")
    except Exception:
        pass
    return None


def ping(host="8.8.8.8", port=53, timeout_s=2):
    """TCP-connect "ping" to a known endpoint. MicroPython doesn't ship
    raw ICMP sockets on this port, so we time the TCP handshake to a
    cheap target (Google's DNS on port 53 by default).

    Returns (ok, rtt_ms). `ok=False, rtt_ms=None` on failure.
    """
    try:
        import socket as _s
    except ImportError:
        return (False, None)
    if not is_connected():
        return (False, None)
    try:
        addr = _s.getaddrinfo(host, port)[0][-1]
    except Exception:
        return (False, None)
    sock = _s.socket()
    try:
        sock.settimeout(timeout_s)
    except Exception:
        pass
    t0 = time.ticks_ms()
    try:
        sock.connect(addr)
        rtt = time.ticks_diff(time.ticks_ms(), t0)
        return (True, rtt)
    except Exception:
        return (False, None)
    finally:
        try:
            sock.close()
        except Exception:
            pass


def speed_test(bytes_=200_000, timeout_s=10, pump_cb=None):
    """Throughput probe: download `bytes_` from speed.cloudflare.com
    and report observed kbps.

    `pump_cb` is called between every recv() so the caller can keep
    the OS run loop alive — typically passes a closure that re-reads
    the button matrix and bumps the screen. The socket is set to a
    50-ms recv timeout so each blocked read can't freeze the UI for
    more than that. If pump_cb returns True the test aborts cleanly
    (used by the WiFi app's "cancel by any keypress" UX).

    Default size dropped from 500 KB → 200 KB. The handshake is
    still amortised but the test finishes in ~1–2 s on home WiFi
    and ~5 s on weak links, both well within user attention span.

    Returns (ok, kbps, elapsed_ms). On failure or cancel,
    (False, 0, elapsed).
    """
    try:
        import socket as _s
        import ssl    as _ssl
    except ImportError:
        return (False, 0, 0)
    if not is_connected():
        return (False, 0, 0)
    host = "speed.cloudflare.com"
    path = "/__down?bytes=%d" % int(bytes_)
    try:
        addr = _s.getaddrinfo(host, 443)[0][-1]
    except Exception:
        return (False, 0, 0)

    raw = None
    s   = None
    deadline = time.ticks_add(time.ticks_ms(), int(timeout_s * 1000))
    t0 = time.ticks_ms()
    received = 0
    body_started = False
    cancelled = False

    # 50 ms recv timeout caps each blocking read so the run loop
    # can resume between reads. This is the difference between
    # "buttons frozen for 5 s" and "buttons responsive throughout".
    PER_READ_S = 0.05

    def _pump():
        """Run the caller's pump callback if any; flag cancel."""
        nonlocal cancelled
        if pump_cb is None:
            return
        try:
            if pump_cb():
                cancelled = True
        except Exception:
            pass

    try:
        raw = _s.socket()
        try: raw.settimeout(timeout_s)   # connect can take a while
        except Exception: pass
        raw.connect(addr)
        s = _ssl.wrap_socket(raw, server_hostname=host)
        try: s.settimeout(PER_READ_S)
        except Exception: pass
        req = ("GET %s HTTP/1.1\r\nHost: %s\r\n"
               "User-Agent: OreoBadge-Speed\r\n"
               "Accept-Encoding: identity\r\n"
               "Connection: close\r\n\r\n") % (path, host)
        s.write(req.encode())
        head = b""
        # Read headers. With the short PER_READ_S timeout each recv
        # bails fast on no-data; we loop until the separator arrives
        # or the overall deadline blows.
        while b"\r\n\r\n" not in head:
            if cancelled:
                break
            if time.ticks_diff(deadline, time.ticks_ms()) <= 0:
                break
            try:
                chunk = s.read(2048)
            except OSError:
                _pump()
                continue
            except Exception:
                break
            if not chunk:
                break
            head += chunk
            if len(head) > 16 * 1024:
                break
            _pump()
        sep = head.find(b"\r\n\r\n")
        if sep >= 0:
            body_started = True
            received = len(head) - (sep + 4)
        # Drain the body.
        while body_started:
            if cancelled:
                break
            if time.ticks_diff(deadline, time.ticks_ms()) <= 0:
                break
            try:
                chunk = s.read(4096)
            except OSError:
                _pump()
                continue
            except Exception:
                break
            if not chunk:
                break
            received += len(chunk)
            _pump()
            if received >= bytes_:
                break
    except Exception:
        pass
    finally:
        for h in (s, raw):
            try:
                if h is not None:
                    h.close()
            except Exception:
                pass
    elapsed = max(1, time.ticks_diff(time.ticks_ms(), t0))
    if cancelled:
        return (False, 0, elapsed)
    if received <= 0:
        return (False, 0, elapsed)
    kbps = int((received * 8) // elapsed)   # bytes*8 / ms = kbps
    return (True, kbps, elapsed)


def info():
    """One-shot snapshot for the WiFi detail screen.

    Returns a dict with `connected`, `ssid`, `ip`, `subnet`, `gateway`,
    `dns`, and `rssi`. Missing fields are None — the UI fills with '—'.
    """
    out = {"connected": False, "radio_on": False,
           "ssid": None,    "ip": None,
           "subnet":   None,  "gateway": None, "dns": None,
           "rssi":     None}
    try:
        wlan = _get_wlan()
        try:
            out["radio_on"] = bool(wlan.active())
        except Exception:
            pass
        out["connected"] = bool(wlan.isconnected())
        if out["connected"]:
            cfg = wlan.ifconfig()    # (ip, subnet, gateway, dns)
            out["ip"]      = cfg[0]
            out["subnet"]  = cfg[1]
            out["gateway"] = cfg[2]
            out["dns"]     = cfg[3]
            try:
                out["ssid"] = wlan.config("essid")
            except Exception:
                pass
            try:
                out["rssi"] = wlan.status("rssi")
            except Exception:
                pass
    except Exception:
        pass
    return out


# ── power-mode preset cycling ────────────────────────────────────────────
# A single dial that covers TX dBm + power-save mode together so the user
# doesn't reason about both. Persisted on the OS settings dict so the
# choice survives a reboot.

POWER_MODES = ("off", "eco", "balanced", "max")

_MODE_TX_DBM = {"eco": 5, "balanced": 11, "max": 19}


def set_power_mode(mode):
    """Apply a coherent (tx_dbm, pm) preset to the live radio.

    'off'      → radio down
    'eco'      → 5 dBm, PM_POWERSAVE
    'balanced' → 11 dBm, PM_POWERSAVE (matches existing default)
    'max'      → 19 dBm, PM_NONE
    """
    if mode not in POWER_MODES:
        return False
    wlan = _get_wlan()
    if mode == "off":
        try:
            wlan.disconnect()
        except Exception:
            pass
        try:
            wlan.active(False)
        except Exception:
            pass
        return True

    try:
        wlan.active(True)
    except Exception:
        return False
    try:
        wlan.config(txpower=_MODE_TX_DBM[mode])
    except Exception:
        pass
    try:
        wlan.config(pm=(wlan.PM_NONE if mode == "max" else wlan.PM_POWERSAVE))
    except Exception:
        pass
    return True


def get_power_mode():
    """Best-effort introspection — returns the current preset name based
    on the active TX-power level and PM mode. Falls back to 'balanced'
    when MicroPython doesn't expose enough config to be sure."""
    try:
        wlan = _get_wlan()
        if not wlan.active():
            return "off"
        try:
            tx = int(wlan.config("txpower"))
        except Exception:
            return "balanced"
        if tx <= 6:
            return "eco"
        if tx >= 17:
            return "max"
        return "balanced"
    except Exception:
        return "balanced"


# ═════════════════════════════════════════════════════════════════════════
# Non-blocking scan / connect / boot auto-connect (OreoOS 2.0)
# ═════════════════════════════════════════════════════════════════════════
#
# Everything below returns immediately. A scan runs in a short-lived
# `_thread` worker: MicroPython's ESP32 port releases the GIL around
# esp_wifi_scan_start(), so the UI keeps drawing while the radio hops
# channels (~1.5-2.5 s). Builds without `_thread` fall back to a
# synchronous scan, which costs one ~2 s hitch but is otherwise identical.
#
# The worker only touches `_scan_raw` / `_scan_err` / `_scan_busy`; all
# parsing, flash writes and state changes happen on the main thread in
# scan_poll(), so there is no shared mutable state beyond three scalars.

_SEEN_PATH     = "/wifi_seen.json"
_SEEN_MAX      = 16          # networks remembered from the last scan
_SCAN_TIMEOUT  = 8000        # ms; a worker that never reports is abandoned

# Association results returned by connect_poll().
CONN_IDLE     = "idle"
CONN_BUSY     = "connecting"
CONN_OK       = "ok"
CONN_BAD_PW   = "bad_password"
CONN_NO_AP    = "not_found"
CONN_TIMEOUT  = "timeout"
CONN_FAIL     = "failed"

# Driver status codes (network.STAT_* on the ESP32 port). Hard-coded so
# the classifier also works on the host and on builds that do not export
# every constant.
_ST_NO_AP     = (201, 210, 211, 212)    # NO_AP_FOUND (+ threshold variants)
_ST_BAD_PW    = (202, 15, 204)          # AUTH_FAIL / 4-way handshake timeout
_BAD_HOLD_MS  = 2500                    # a bad status must persist this long

_scan_busy    = False
_scan_raw     = None
_scan_err     = None
_scan_t0      = 0
_scan_seq     = 0            # bumps on every completed scan
_nearby       = None         # parsed list from the most recent scan
_nearby_live  = False        # True once a scan finished this boot


def _now():
    return time.ticks_ms()


def _decode_ssid(raw):
    """Scan SSIDs are bytes and may not be valid UTF-8. Never raise."""
    if isinstance(raw, str):
        return raw
    try:
        return raw.decode("utf-8")
    except Exception:
        return "".join(chr(b) if 32 <= b < 127 else "?" for b in raw)


def parse_scan(raw, limit=_SEEN_MAX):
    """wlan.scan() tuples -> [{ssid, rssi, secure, ch}], strongest first.

    Hidden networks (empty SSID) are dropped and an SSID broadcast by
    several access points is kept once, with its strongest signal.
    Pure function: host-tested in tests/test_wifi_logic.py.
    """
    best = {}
    for r in raw or ():
        try:
            ssid = _decode_ssid(r[0])
            rssi = int(r[3])
            auth = int(r[4])
            ch   = int(r[2])
        except Exception:
            continue
        if not ssid:
            continue
        cur = best.get(ssid)
        if cur is None or rssi > cur["rssi"]:
            best[ssid] = {"ssid": ssid, "rssi": rssi,
                          "secure": auth != 0, "ch": ch}
    out = sorted(best.values(), key=lambda n: -n["rssi"])
    return out[:limit]


def signal_level(rssi):
    """RSSI (dBm) -> 0..4 bars. Same thresholds the WiFi app always used."""
    if rssi is None:
        return 0
    if rssi >= -50:
        return 4
    if rssi >= -65:
        return 3
    if rssi >= -75:
        return 2
    if rssi >= -85:
        return 1
    return 0


def classify_status(code):
    """wlan.status() -> CONN_BAD_PW / CONN_NO_AP, or None (still trying
    / connected / unknown)."""
    try:
        code = int(code)
    except Exception:
        return None
    if code in _ST_BAD_PW:
        return CONN_BAD_PW
    if code in _ST_NO_AP:
        return CONN_NO_AP
    return None


def pick_candidates(saved, visible, exclude=()):
    """Saved networks worth trying, best first.

    With a scan in hand only networks that are actually on the air are
    returned, ordered by (priority, strongest signal). Without one
    (`visible` is None, e.g. the scan failed) every saved network is
    returned in priority order so the badge still tries something.
    """
    def _pri(n):
        try:
            return int(n.get("priority", 999))
        except Exception:
            return 999
    if visible is None:
        nets = [n for n in saved
                if n.get("ssid") and n.get("ssid") not in exclude]
        return sorted(nets, key=_pri)
    rssi = {}
    for v in visible:
        rssi[v["ssid"]] = v["rssi"]
    nets = [n for n in saved
            if n.get("ssid") in rssi and n.get("ssid") not in exclude]
    return sorted(nets, key=lambda n: (_pri(n), -rssi[n["ssid"]]))


def _scan_worker():
    global _scan_raw, _scan_err, _scan_busy
    wlan = _get_wlan()
    try:
        try:
            res = wlan.scan()
        except OSError:
            # IDF refuses to scan while the driver is retrying a failed
            # association ("sta is connecting"). Stop that loop and retry
            # once; never touch a link that is actually up.
            if wlan.isconnected():
                raise
            try:
                wlan.disconnect()
            except Exception:
                pass
            time.sleep_ms(50)
            res = wlan.scan()
        _scan_raw = res
    except Exception as e:
        _scan_err = str(e) or "scan failed"
    _scan_busy = False


def scan_start():
    """Start a background scan. Returns True if one is running now."""
    global _scan_busy, _scan_raw, _scan_err, _scan_t0
    if _scan_busy:
        return True
    try:
        _apply_global_hostname()
        wlan = _get_wlan()
        if not wlan.active():
            wlan.active(True)
    except Exception as e:
        _scan_err = str(e) or "radio error"
        return False
    _scan_raw  = None
    _scan_err  = None
    _scan_busy = True
    _scan_t0   = _now()
    try:
        import _thread
        _thread.start_new_thread(_scan_worker, ())
    except Exception:
        _scan_worker()           # no threads: synchronous fallback
    return True


def scan_busy():
    return _scan_busy


def scan_seq():
    """Counter that increases each time fresh scan results land."""
    return _scan_seq


def scan_error():
    return _scan_err


def scan_elapsed_ms():
    if not _scan_busy:
        return 0
    return time.ticks_diff(_now(), _scan_t0)


def scan_poll():
    """Collect a finished scan. Main thread only. Returns "busy",
    "done" (fresh results just landed), "error" or "idle"."""
    global _scan_raw, _scan_busy, _scan_err, _scan_seq, _nearby, _nearby_live
    if _scan_busy:
        if time.ticks_diff(_now(), _scan_t0) > _SCAN_TIMEOUT:
            # Worker wedged; abandon it (its late result is ignored on
            # the next scan_start, which resets _scan_raw).
            _scan_busy = False
            _scan_err  = "scan timed out"
            return "error"
        return "busy"
    raw = _scan_raw
    if raw is not None:
        _scan_raw    = None
        _nearby      = parse_scan(raw)
        _nearby_live = True
        _scan_seq   += 1
        _save_seen(_nearby)
        return "done"
    if _scan_err:
        return "error"
    return "idle"


def nearby():
    """Networks from the most recent scan (this boot), else the list
    remembered on flash from an earlier one. Strongest first."""
    global _nearby
    if _nearby is None:
        _nearby = _load_seen()
    return _nearby


def nearby_is_live():
    """False while nearby() is still showing the remembered list."""
    return _nearby_live


def _load_seen():
    if _json is None or not _exists(_SEEN_PATH):
        return []
    try:
        with open(_SEEN_PATH) as f:
            data = _json.loads(f.read())
        if isinstance(data, list):
            return [d for d in data if isinstance(d, dict) and d.get("ssid")]
    except Exception:
        pass
    return []


_seen_sig = None


def _save_seen(nets):
    """Persist the scan so the next boot's Settings page paints
    instantly. Only rewritten when the set of SSIDs changes, so the
    flash is not worn by every periodic scan."""
    global _seen_sig
    if _json is None:
        return
    sig = ",".join(sorted(n["ssid"] for n in nets))
    if _seen_sig is None:
        _seen_sig = ",".join(sorted(n.get("ssid", "") for n in _load_seen()))
    if sig == _seen_sig:
        return
    try:
        with open(_SEEN_PATH, "w") as f:
            f.write(_json.dumps(
                [{"ssid": n["ssid"], "rssi": n["rssi"],
                  "secure": n["secure"]} for n in nets]))
        _seen_sig = sig
    except Exception:
        pass


def saved_ssids():
    """Set-like dict of saved SSIDs, for "is this network known?" checks."""
    out = {}
    for n in _load_saved_raw():
        s = n.get("ssid")
        if s:
            out[s] = True
    return out


def get_saved(ssid):
    for n in _load_saved_raw():
        if n.get("ssid") == ssid:
            return dict(n)
    return None


def _mark_last(ssid):
    """Remember which network connected so the next boot tries it first
    without scanning. Writes only when the marker moves."""
    nets = _load_saved_raw()
    changed = False
    for n in nets:
        want = n.get("ssid") == ssid
        if bool(n.get("last")) != want:
            if want:
                n["last"] = True
            else:
                n.pop("last", None)
            changed = True
    if changed:
        _save_raw(nets)


def last_connected(saved=None):
    """The saved entry that connected most recently, or None."""
    for n in (saved if saved is not None else _load_saved_raw()):
        if n.get("last") and n.get("ssid"):
            return n
    return None


# ── non-blocking association ────────────────────────────────────────────

_conn_ssid    = None
_conn_t0      = 0
_conn_timeout = 12000
_conn_bad     = None     # classify_status() result currently held
_conn_bad_t0  = 0
_conn_result  = CONN_IDLE


def connect_begin(ssid, password, timeout_ms=12000):
    """Start associating with `ssid` and return at once. Poll
    connect_poll() for the outcome. The password is never printed."""
    global _conn_ssid, _conn_t0, _conn_timeout, _conn_bad, _conn_result
    if not ssid:
        _conn_result = CONN_FAIL
        return False
    wlan = _get_wlan()
    _apply_global_hostname()
    try:
        wlan.active(True)
        # Same flush as connect(): cancel IDF's own NVS auto-connect
        # (or a previous retry loop) before configuring a new target.
        try:
            wlan.disconnect()
        except Exception:
            pass
        time.sleep_ms(30)
        _apply_hostname(wlan)
        _apply_power_cap(wlan)
        wlan.connect(ssid, password or "")
    except Exception as e:
        print("[wifi] connect_begin failed:", e)
        _conn_ssid   = None
        _conn_result = CONN_FAIL
        return False
    print("[wifi] connecting to", ssid)
    _conn_ssid    = ssid
    _conn_t0      = _now()
    _conn_timeout = int(timeout_ms)
    _conn_bad     = None
    _conn_result  = CONN_BUSY
    return True


def connect_target():
    """SSID currently being joined, or None."""
    return _conn_ssid


def connect_elapsed_ms():
    if _conn_ssid is None:
        return 0
    return time.ticks_diff(_now(), _conn_t0)


def connect_cancel():
    global _conn_ssid, _conn_result
    if _conn_ssid is None:
        return
    _conn_ssid = None
    _conn_result = CONN_IDLE
    try:
        _get_wlan().disconnect()
    except Exception:
        pass


def connect_poll():
    """Advance the association started by connect_begin()."""
    global _conn_ssid, _conn_bad, _conn_bad_t0, _conn_result
    if _conn_ssid is None:
        return _conn_result
    wlan = _get_wlan()
    now  = _now()
    try:
        up = wlan.isconnected()
    except Exception:
        up = False
    if up:
        ssid = _conn_ssid
        _conn_ssid   = None
        _conn_result = CONN_OK
        try:
            _apply_power_cap(wlan)
        except Exception:
            pass
        try:
            _mark_last(ssid)
        except Exception:
            pass
        print("[wifi] associated:", ssid)
        return CONN_OK
    try:
        bad = classify_status(wlan.status())
    except Exception:
        bad = None
    fail = None
    if bad is None:
        _conn_bad = None
    elif bad != _conn_bad:
        _conn_bad, _conn_bad_t0 = bad, now
    elif time.ticks_diff(now, _conn_bad_t0) >= _BAD_HOLD_MS:
        fail = bad
    if fail is None and time.ticks_diff(now, _conn_t0) > _conn_timeout:
        fail = CONN_TIMEOUT
    if fail is None:
        return CONN_BUSY
    print("[wifi] connect %s: %s" % (fail, _conn_ssid))
    _conn_ssid   = None
    _conn_result = fail
    try:
        wlan.disconnect()       # stop the driver's endless retry loop
    except Exception:
        pass
    return fail


# ── boot auto-connect state machine ─────────────────────────────────────
#
#   auto_begin()  — returns immediately. Fast path: if a saved network
#                   connected last time, start joining it with no scan.
#                   Otherwise start a background scan first.
#   auto_tick()   — call every frame (cheap: rate-limited). Returns True
#                   exactly once, on the tick the badge gets an IP, so the
#                   caller can start the HTTP server / NTP sync.
#
# After connecting, one background scan refreshes the nearby list (and
# /wifi_seen.json) so Settings shows nearby networks immediately. When no
# saved network is in range, the scan still runs and its results are kept.

AUTO_OFF   = "off"
AUTO_TRY   = "connecting"
AUTO_SCAN  = "scanning"
AUTO_DONE  = "connected"
AUTO_FAIL  = "no_network"

_auto_state   = AUTO_OFF
_auto_queue   = []
_auto_tried   = []
_auto_scanned = False
_auto_refresh = False     # post-connect nearby scan still to do
_auto_next_ms = 0
_AUTO_TICK_MS = 150


def auto_state():
    return _auto_state


def _auto_try_next():
    global _auto_state
    while _auto_queue:
        n = _auto_queue.pop(0)
        ssid = n.get("ssid") or ""
        if not ssid or ssid in _auto_tried:
            continue
        _auto_tried.append(ssid)
        if connect_begin(ssid, n.get("password") or ""):
            _auto_state = AUTO_TRY
            return True
    return False


def auto_begin():
    """Kick off boot auto-connect without blocking. Safe to call again
    (e.g. from the WiFi app) — it restarts the sequence."""
    global _auto_state, _auto_queue, _auto_tried, _auto_scanned, _auto_refresh
    try:
        _sync_secrets_into_saved()
    except Exception as e:
        print("[wifi] secrets sync failed:", e)
    saved = list_saved()
    _auto_queue   = []
    _auto_tried   = []
    _auto_scanned = False
    _auto_refresh = True
    if is_connected():
        _auto_state = AUTO_DONE
        return
    last = last_connected(saved)
    if last is not None:
        _auto_queue.append(last)
        if _auto_try_next():
            return
    _auto_scanned = True
    _auto_state = AUTO_SCAN if scan_start() else AUTO_FAIL


def auto_tick():
    """Advance auto-connect. True exactly once when the link comes up."""
    global _auto_state, _auto_queue, _auto_scanned, _auto_refresh, _auto_next_ms
    if _auto_state == AUTO_OFF:
        return False
    now = _now()
    if time.ticks_diff(now, _auto_next_ms) < 0:
        return False
    _auto_next_ms = time.ticks_add(now, _AUTO_TICK_MS)

    if _auto_state == AUTO_TRY:
        r = connect_poll()
        if r == CONN_BUSY:
            return False
        if r == CONN_OK:
            _auto_state = AUTO_DONE
            return True
        if _auto_try_next():
            return False
        if not _auto_scanned:
            _auto_scanned = True
            _auto_state = AUTO_SCAN if scan_start() else AUTO_FAIL
            return False
        _auto_state = AUTO_FAIL
        return False

    if _auto_state == AUTO_SCAN:
        s = scan_poll()
        if s == "busy":
            return False
        visible = nearby() if s == "done" else None
        saved = list_saved()
        _auto_queue = pick_candidates(saved, visible, _auto_tried)
        if _auto_try_next():
            return False
        _auto_state = AUTO_FAIL
        _auto_refresh = False
        if not saved:
            # Nothing to join: power down like the old boot path did.
            radio_off()
        return False

    if _auto_state == AUTO_DONE and _auto_refresh:
        # One post-connect scan so Settings shows what is around. Runs in
        # the background thread; skipped silently on thread-less builds
        # (a synchronous 2 s scan here would stall the home screen).
        if not _scan_busy:
            try:
                import _thread  # noqa: F401 (availability probe)
                _auto_refresh = False
                scan_start()
            except Exception:
                _auto_refresh = False
        return False

    if _scan_busy or _scan_raw is not None:
        scan_poll()       # collect the post-connect refresh scan
    return False
