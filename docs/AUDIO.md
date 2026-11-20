# Audio

The PCB Falera Badge has a speaker: a MAX98357A class-D I2S amplifier
driving an 8 Ω, 15 × 11 mm mono speaker. FaleraOS plays MP3 through it, from
internet streams, podcast episodes, Jamendo and files on the microSD card.
The breadboard badge has no amp wired for the OS, so audio there is
reported as unavailable and the audio apps say "needs the PCB badge
(speaker)".

```
 network / microSD ──► oreoOS.player (worker thread)
                         │  HTTP(S), redirects, .pls/.m3u, ICY metadata,
                         │  ID3v2 skipped, 64 KB stream ring (PSRAM)
                         ▼
                       _oreo_audio.MP3Decoder (firmware, C, minimp3)
                         │  frames → mono int16 PCM
                         ▼
                       oreoWare.audio (os.audio)
                         │  64 KB PCM ring, volume, fades
                         ▼
                       machine.I2S, non-blocking ──► MAX98357A ──► speaker
```

## Pins (PCB)

| Signal | Where | Notes |
|---|---|---|
| BCLK | GPIO8 | `pins.I2S_BCLK` |
| LRCLK | GPIO9 | `pins.I2S_LRCLK` |
| DIN | GPIO10 | `pins.I2S_DOUT` |
| SD_MODE (amp enable) | AW9523B P1_4 | `pins.EXP_AMP_EN`, high = on |

The amp runs from VSYS. Its SD_MODE pin is the expander's P1_4, so the
amp is off (shutdown, about 1 µA) unless something is playing. The
breadboard's pin map in `oreoWare/pins.py` still lists an amp on GPIO
41/21/46 (with SD tied on); the OS does not drive it.

## Driver: `oreoWare/audio.py` (`os.audio`)

```python
a = os.audio                 # always an object; a.available is False off the PCB
a.volume = 60                # 0-100, software gain (square law)
a.start(22050)               # I2S with silence first, then the amp
n = a.write(pcm, 22050)      # int16 mono bytes taken; never blocks
a.free(), a.buffered()       # bytes
a.flush()                    # drop what is queued
a.stop()                     # fade out, silence, amp off, I2S released
```

- `write()` copies into a 64 KB ring (an ordinary bytearray, so PSRAM) and
  returns how much fitted. It is safe from a worker thread.
- `machine.I2S` runs in non-blocking mode (TX, mono, 16 bit, 12 KB of DMA
  buffers). Each finished transfer schedules `_on_sent()` on the main
  thread, which hands I2S the next 2 KB: queued samples, or silence when
  the ring is empty (counted in `underruns`). The amp, the expander's I2C
  and the I2S peripheral are only touched on the main thread.
- No pops: `start()` sends two chunks of silence before the amp is
  enabled, and the first samples fade in; `stop()` fades the next chunk
  out, drops the rest, sends silence until the DMA buffers hold nothing
  else and only then turns the amp off and deinits I2S. `stop()` returns
  at once.
- Sample-rate changes (8 to 48 kHz) wait until the samples queued at the
  old rate have played, then reopen I2S with the amp muted.
- Volume is applied per chunk in C (`_oreo_audio.gain`), so a change is
  heard within the DMA buffering (about 0.15 to 0.3 s).

## Decoder: `_oreo_audio` (firmware)

`firmware/usermods/oreo_audio/` holds a user C module built into the
OREO_BADGE firmware next to `_oreo_rv565` and `_oreo_ir`:

```python
import _oreo_audio
d = _oreo_audio.MP3Decoder()
consumed, samples, hz, channels = d.decode(chunk, pcm, flush=False)
d.info()     # (hz, channels, bitrate_kbps, frames, skipped_bytes)
d.reset(); d.deinit()
_oreo_audio.gain(pcm, q16)          # scale int16 samples by q16/65536
```

- `decode()` takes as much of `chunk` as fits in its 8 KB input buffer
  (pass the rest on the next call), decodes whole frames into `pcm` (a
  writable buffer of int16, at least 1152 samples), downmixes stereo to
  mono as (L + R) / 2 and returns how many bytes it took and samples it
  wrote. A frame cut off at the end of a chunk waits for the next one; all
  samples of one call share one rate. `flush=True` at the end of a file
  decodes what is left.
- It is minimp3 (CC0, vendored with its licence in `minimp3/`, see
  `minimp3/VENDORED.md`), Layer III only. Its ~16 KB per-frame scratch is
  taken from internal RAM when there is room (faster) and from the
  MicroPython heap otherwise; the decoder state and input buffer (~20 KB)
  are on the heap, which is PSRAM. A MicroPython thread's stack never holds
  it: one local change in `minimp3.h` (`MINIMP3_SCRATCH_PTR`) moves it off
  the stack.
- Resync: garbage before the first frame, a stream joined mid-frame and
  lost data are skipped (`skipped_bytes`); the end of the buffer is kept
  while resyncing so a real frame is not thrown away.
- Size: about 19 KB of flash (18.6 KB minimp3 and wrapper, 0.8 KB
  binding).
- Host test: `tests/test_mp3_decoder.py` builds `mp3_core.c` with `cc`,
  makes MP3s with ffmpeg (1 s, 22050 Hz mono 64 kb/s; 44100 Hz stereo
  128 kb/s), decodes them in random-sized chunks and compares with
  ffmpeg's decode (SNR above 40 dB; it measures about 94-97 dB), checks
  that chunking never changes the output, and that a damaged stream
  resyncs.

## Player: `oreoOS/player.py`

```python
from oreoOS import player
p = player.Player(os.audio)
p.play(url, name="Station")      # http(s) URL or a file path ("/sd/...")
p.update()                       # every frame, from App.update (main thread)
p.state                          # idle / connecting / buffering / playing / error / ended
p.title, p.error, p.station_name, p.bitrate
p.position_s(), p.duration_s(), p.can_seek(), p.seek(+30)
p.stop()
```

The worker thread (16 KB stack for TLS):

1. connects through `oreoOS._http`'s connector (every address of the host,
   DNS fallback) and, for https, `_http.tls_wrap` (certificate checked);
2. sends an HTTP/1.0 GET with `Icy-MetaData: 1` (and `Range` when asked to
   start part way), follows up to 5 redirects and `.pls` / `.m3u`
   playlists (the first URL); HLS, AAC, Ogg and HTML are refused with a
   reason;
3. strips ICY metadata every `icy-metaint` bytes and keeps the
   `StreamTitle` as `p.title`; skips an ID3v2 tag at the start of a file;
4. fills a 64 KB stream ring (PSRAM), waits for 16 KB before starting
   (8 KB after a stall), decodes into the driver's ring and sleeps when
   everything is full;
5. reconnects a live stream that stalls (no data for 10 s) or drops, up
   to 4 times with backoff (1, 2, 4, 8 s), keeping what is buffered; a
   file or episode ends with `ended` when its data runs out.

`update()` only switches the driver on when playback starts and off
when it stops, ends or fails; nothing in it waits.

Seeking (podcasts, Music): a server that answers `Range` with 206 (or
`Accept-Ranges: bytes`) and a file are seekable. `seek(delta)` restarts
the stream at `position × bitrate / 8` bytes, which is exact for a
constant bit rate and close for VBR. A server without ranges is not
seekable and `seek()` returns False.

Wi-Fi is for the internet only: the player makes outgoing connections to
the stream's server and listens on nothing.

## The apps

| App | Source | Where |
|---|---|---|
| Radio | Radio Browser (open directory, no key) | App Store |

`oreoOS/mediaui.py` holds their shared screens: a list, an on-screen
keyboard and the now-playing panel, with touch.

## Badge test steps

1. Build and flash the firmware (`./build-firmware --flash`), then check
   `import _oreo_audio` on the REPL.
2. Radio: play a station. Listen for a click when it starts and stops (there
   should be none), change the volume both ways, switch stations.
3. With nothing playing, measure the badge's current: it should not change
   when the amp's enable is the only difference (amp off when idle).
4. Leave a station playing for 10 minutes; open the notification panel
   and other screens of the app. No dropouts beyond Wi-Fi stalls.
5. Watch `os.audio.underruns` on the REPL while playing to see if the main
   loop starves I2S.
