"""Errors the CLI reports to the user (one line plus an optional hint)."""


class OreoError(Exception):
    """A failure with a message meant for the user.

    `hint` says what to do about it; `code` is the process exit status.
    """

    code = 1

    def __init__(self, message, hint=None):
        super().__init__(message)
        self.message = message
        self.hint = hint


class NoBadge(OreoError):
    code = 3


class ManyBadges(OreoError):
    code = 3


class BadgeError(OreoError):
    """Code running on the badge raised. `detail` is the badge traceback."""

    def __init__(self, message, detail="", hint=None):
        super().__init__(message, hint)
        self.detail = detail


class Cancelled(OreoError):
    code = 130


def redact(text, secrets):
    """Replace every secret (and its repr) in `text` with ***."""
    if not text:
        return text
    for s in secrets or ():
        if not s:
            continue
        escaped = s.replace("\\", "\\\\")
        forms = (repr(s), s.replace("\\", "\\\\").replace("'", "\\'"),
                 escaped.replace('"', '\\"'), repr(s)[1:-1], s)
        for form in forms:
            if form:
                text = text.replace(form, "***")
    return text
