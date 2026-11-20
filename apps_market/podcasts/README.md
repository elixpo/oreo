# Podcasts

Podcasts on the PCB Falera Badge's speaker. Search shows with the iTunes
Search API (no account), subscribe, and play episodes from the show's own
RSS feed. Each episode remembers where you stopped.

- **A** opens a show or plays an episode; **RIGHT** on a show subscribes.
- On the player: **LEFT** back 15 s, **RIGHT** forward 30 s, **UP/DOWN**
  volume, **A** play/stop, **B** back. Touch works everywhere.

Skipping needs the episode's server to support HTTP Range requests, which
nearly all podcast hosts do; when one doesn't, the player says so. Only MP3
episodes are listed (the badge decodes MP3). Feeds are read as they
download and only the newest 40 episodes are kept, so large feeds work.
