"""Jamendo API settings.

DEFAULT_CLIENT_ID is the Falera Badge's Jamendo application id, from
devportal.jamendo.com. It is a public, project-wide app id (Jamendo sends it
in every request URL), not a secret and not personal data; the app's
*client secret* is never needed for reading the catalogue and must never be
committed.

A badge can use another id by writing it into the app's saved state:
{"client_id": "..."} in /state/jamendo.json (e.g. with `falera` file
transfer, or from the REPL: oreoOS.state). An empty default and no saved id
make the app show "Jamendo not set up".
"""

DEFAULT_CLIENT_ID = "c4a5c1db"
