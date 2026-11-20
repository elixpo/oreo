# Jamendo

Creative Commons music from [Jamendo](https://www.jamendo.com) on the PCB
Falera Badge's speaker: featured tracks, this week's popular tracks,
genres, albums and search. A list plays from the chosen track on; an album
plays in order. The player always shows the track's artist and its CC
licence, which Jamendo's licences require.

- **A** opens or plays; on the player **LEFT/RIGHT** change track,
  **UP/DOWN** the volume, **A** play/stop. **B** goes back. Touch works.

The app uses the Falera Badge's Jamendo client id (a public app id, in
`src/config.py`). To use your own, create an app on
devportal.jamendo.com and save its client id as `{"client_id": "..."}` in
`/state/jamendo.json` on the badge. Never put a client secret on the badge.
