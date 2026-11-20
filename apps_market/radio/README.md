# Radio

Internet radio on the PCB Falera Badge's speaker. Stations come from
[Radio Browser](https://www.radio-browser.info), the open, community-run
directory (no account or key): top stations, by country, by genre, or by
name. Only MP3 stations are listed, lower bit rates first.

- **A** plays the selected station; on the player, **A** is play/stop.
- **UP/DOWN** move in lists and change the volume on the player.
- **RIGHT** on a station keeps it in Favourites (the star).
- **B** goes back; touch works on every screen.

The player shows the song the station announces. Leaving the app stops the
radio. On the breadboard badge, which has no speaker amp, the app says so.

Radio Browser asks clients to report a play; the app does that when a
station starts, and identifies itself as `FaleraOS-Radio/1.0`.
