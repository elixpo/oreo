"""Spotify sign-in for the badge: saved tokens, refresh timing and the
PIN pairing state machine. No I/O here except through the functions the
caller passes in, so all of it runs in host tests.

How a badge gets linked (the relay is falera.elixpo/functions/api/spotify):

  1. The badge POSTs {relay}/api/spotify/session. The relay answers with
     a 6-character PIN to show, a poll secret the badge keeps to itself,
     and the sign-in URL (drawn as a QR code).
  2. The owner opens {relay}/spotify/?pin=PIN on a phone or computer and
     signs in to Spotify (Authorization Code with PKCE: no client secret
     anywhere).
  3. The badge POSTs {relay}/api/spotify/poll with PIN and secret every
     few seconds. Once the owner has signed in, the relay hands over the
     tokens once and forgets them.
  4. Every hour or so the badge refreshes its access token by POSTing
     the refresh token to {relay}/api/spotify/refresh, which forwards it
     to accounts.spotify.com with the public client id (PKCE refresh, no
     secret) and keeps nothing. The relay is used because
     accounts.spotify.com's certificate chains to a root CA that the
     badge's TLS bundle (oreoOS/tls_roots.py) does not carry; api.spotify.com
     and falera.elixpo.com chain to roots it does.

Tokens live in /state/spotify.json through oreoOS.state. The relay base
URL is the "relay" key of that file when set (an https:// URL), else
DEFAULT_RELAY.
"""

try:
    import json
except ImportError:  # pragma: no cover
    import ujson as json

DEFAULT_RELAY = "https://falera.elixpo.com"
REFRESH_MARGIN_S = 120      # refresh this long before the token expires

TOKEN_KEYS = ("access_token", "refresh_token", "client_id", "expires_at")

# Pairing states
IDLE = "idle"
STARTING = "starting"       # asking the relay for a PIN
WAITING = "waiting"         # PIN on screen, polling
LINKED = "linked"           # tokens received (Pairing.tokens)
EXPIRED = "expired"         # PIN timed out; press C for a new one
FAILED = "failed"           # see Pairing.error

# Pairing.error values
ERR_NOT_CONFIGURED = "not_configured"   # relay has no client id / KV
ERR_UNREACHABLE = "unreachable"         # no HTTP answer
ERR_RELAY = "relay"                     # relay answered with an error
ERR_BAD_RELAY = "bad_relay"             # configured relay URL is invalid


def relay_base(saved):
    """The relay base URL (no trailing slash) from the app's saved state,
    or None when the configured value is not an https:// URL."""
    url = (saved or {}).get("relay") or DEFAULT_RELAY
    if not isinstance(url, str) or not url.startswith("https://") or len(url) < 12:
        return None
    return url.rstrip("/")


def has_tokens(saved):
    s = saved or {}
    return bool(s.get("refresh_token") and s.get("client_id"))


def clear_tokens(saved):
    """A copy of `saved` without any token (keeps the relay override)."""
    out = dict(saved or {})
    for k in TOKEN_KEYS:
        out.pop(k, None)
    return out


def needs_refresh(saved, now, margin=REFRESH_MARGIN_S):
    """True when the access token is missing or expires within `margin`
    seconds of `now` (wall-clock seconds, as time.time())."""
    s = saved or {}
    if not s.get("access_token"):
        return True
    try:
        exp = float(s.get("expires_at") or 0)
    except (TypeError, ValueError):
        return True
    return exp <= now + margin


def apply_token_response(saved, data, now):
    """`saved` updated with a token endpoint (or relay poll) response.
    Returns None when the response holds no access token. Spotify may or
    may not rotate the refresh token; the old one is kept when it does
    not send a new one."""
    if not isinstance(data, dict):
        return None
    tok = data.get("access_token")
    if not isinstance(tok, str) or not tok:
        return None
    out = dict(saved or {})
    out["access_token"] = tok
    rt = data.get("refresh_token")
    if isinstance(rt, str) and rt:
        out["refresh_token"] = rt
    cid = data.get("client_id")
    if isinstance(cid, str) and cid:
        out["client_id"] = cid
    try:
        life = int(data.get("expires_in") or 3600)
    except (TypeError, ValueError):
        life = 3600
    out["expires_at"] = int(now) + max(60, life)
    return out


_SAFE = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_.~"


def quote(s):
    """Percent-encode for a query string or form body (no urllib on
    MicroPython)."""
    out = []
    for b in str(s).encode("utf-8"):
        if b in _SAFE:
            out.append(chr(b))
        else:
            out.append("%%%02X" % b)
    return "".join(out)


def form(pairs):
    """application/x-www-form-urlencoded body from (key, value) pairs."""
    return "&".join(quote(k) + "=" + quote(v) for k, v in pairs)


def refresh_request(saved, relay):
    """(url, headers, body) for refreshing the access token through the
    relay, or None without a refresh token or relay."""
    rt = (saved or {}).get("refresh_token")
    if not rt or not relay:
        return None
    return (relay + "/api/spotify/refresh",
            {"Content-Type": "application/json"},
            json.dumps({"refresh_token": rt}))


def refresh_revoked(status, data):
    """True when a refresh failed because the grant is gone (the owner
    removed the app from their Spotify account, or the refresh token was
    rotated elsewhere): the badge has to be linked again."""
    if status != 400 or not isinstance(data, dict):
        return False
    return data.get("error") in ("invalid_grant", "invalid_client")


class Pairing:
    """The PIN pairing flow as a state machine. The app calls want(now)
    each frame; when it returns "session" or "poll" the app runs that
    request on its worker and passes the result to on_session/on_poll.
    `now` is any monotonic seconds counter."""

    POLL_S = 3
    LIFETIME_S = 600

    def __init__(self):
        self.reset()

    def reset(self):
        self.state = IDLE
        self.pin = None
        self.secret = None
        self.url = None
        self.error = None
        self.detail = ""
        self.tokens = None
        self.deadline = 0
        self.next_poll = 0
        self.interval = self.POLL_S
        self.busy = False

    def start(self):
        self.reset()
        self.state = STARTING

    def remaining(self, now):
        if self.state != WAITING:
            return 0
        return max(0, int(self.deadline - now))

    def want(self, now):
        """The request to run now ("session", "poll") or None."""
        if self.busy:
            return None
        if self.state == STARTING:
            return "session"
        if self.state == WAITING:
            if now >= self.deadline:
                self.state = EXPIRED
                self.secret = None
                return None
            if now >= self.next_poll:
                return "poll"
        return None

    def _fail(self, error, detail=""):
        self.state = FAILED
        self.error = error
        self.detail = detail
        self.secret = None

    def on_session(self, status, data, now):
        self.busy = False
        if status == 0:
            self._fail(ERR_UNREACHABLE)
            return
        if not isinstance(data, dict):
            data = {}
        if data.get("error") == ERR_NOT_CONFIGURED:
            self._fail(ERR_NOT_CONFIGURED, data.get("message") or "")
            return
        pin = data.get("pin")
        secret = data.get("secret")
        if status != 200 or data.get("status") != "ok" or not pin or not secret:
            self._fail(ERR_RELAY, "HTTP %d" % status if status != 200
                       else (data.get("message") or "bad answer"))
            return
        self.pin = str(pin)
        self.secret = str(secret)
        self.url = data.get("url") or None
        try:
            life = int(data.get("expires_in") or self.LIFETIME_S)
        except (TypeError, ValueError):
            life = self.LIFETIME_S
        try:
            self.interval = max(2, min(15, int(data.get("interval") or self.POLL_S)))
        except (TypeError, ValueError):
            self.interval = self.POLL_S
        self.deadline = now + life
        self.next_poll = now + self.interval
        self.state = WAITING

    def on_poll(self, status, data, now):
        self.busy = False
        if self.state != WAITING:
            return
        if not isinstance(data, dict):
            data = {}
        if data.get("error") == ERR_NOT_CONFIGURED:
            self._fail(ERR_NOT_CONFIGURED, data.get("message") or "")
            return
        st = data.get("status")
        if status == 200 and st == "authorized":
            if data.get("access_token") and data.get("refresh_token") and data.get("client_id"):
                self.tokens = data
                self.state = LINKED
                self.secret = None
            else:
                self._fail(ERR_RELAY, "incomplete tokens")
            return
        if status == 200 and st == "pending":
            self.next_poll = now + self.interval
            return
        if st == "expired" or status in (404, 410):
            self.state = EXPIRED
            self.secret = None
            return
        if status == 403:
            self._fail(ERR_RELAY, "PIN rejected")
            return
        # Offline, 429 or a 5xx: keep the PIN and try again a bit later.
        self.next_poll = now + self.interval * (4 if status == 429 else 2)
