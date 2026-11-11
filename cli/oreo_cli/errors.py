"""Errors the CLI reports to the user (one line plus an optional hint).

Exit status (documented in docs/CLI.md, "Exit status"):

    0    success
    1    error (the command failed; the message says why)
    2    usage error (bad arguments, missing argument)
    3    no badge found, or more than one and no --port
    4    the badge could not be reached: port busy or missing, no answer,
         connection lost
    5    the badge is not running OreoOS (or the OreoOS on it is too old
         for this command)
    130  cancelled (Ctrl-C, or "no" at a confirmation)
"""

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_NO_BADGE = 3
EXIT_LINK = 4
EXIT_NO_OREOOS = 5
EXIT_CANCELLED = 130


class OreoError(Exception):
    """A failure with a message meant for the user.

    `hint` says what to do about it; `code` is the process exit status.
    """

    code = EXIT_ERROR

    def __init__(self, message, hint=None):
        super().__init__(message)
        self.message = message
        self.hint = hint


class UsageError(OreoError):
    """The command line is incomplete or contradictory."""
    code = EXIT_USAGE


class NoBadge(OreoError):
    code = EXIT_NO_BADGE


class ManyBadges(OreoError):
    code = EXIT_NO_BADGE


class LinkError(OreoError):
    """The serial link failed: port busy or gone, no answer, unplugged."""
    code = EXIT_LINK


class BadgeError(OreoError):
    """Code running on the badge raised. `detail` is the badge traceback."""

    def __init__(self, message, detail="", hint=None):
        super().__init__(message, hint)
        self.detail = detail


class NoOreoOS(BadgeError):
    """The badge answers, but OreoOS (or the part of it needed) is missing."""
    code = EXIT_NO_OREOOS


class Cancelled(OreoError):
    code = EXIT_CANCELLED


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
