# Vendored minimp3

`minimp3.h` is copied from minimp3, https://github.com/lieff/minimp3, commit
`142823796ab8efa55e1bf11406028f3be77ecceb` (2026-11-18). minimp3 is dedicated
to the public domain under CC0 1.0 Universal; `LICENSE` here is its licence
text, unchanged. The upstream file's SHA-256 is
`f9592be69e8b94044e9da6f45f993c9708000abae38cf6f44b70c699de55b509`.

One local change, so that decoding does not need ~16 KB of stack (a
MicroPython thread has 16 KB at most): in `mp3dec_decode_frame()`, when
`MINIMP3_SCRATCH_PTR` is defined, the `mp3dec_scratch_t` work area is the
one that macro returns for the decoder instead of a local variable.
`../mp3_core.c` defines it; without the macro the file behaves exactly as
upstream. The change is the two `#ifdef MINIMP3_SCRATCH_PTR` blocks.

`../mp3_core.c` builds it with `MINIMP3_ONLY_MP3` (Layer III only) and
`MINIMP3_NO_SIMD`.

To update: copy `minimp3.h` and `LICENSE` from upstream, apply the change
above again, update the commit and hash here, rebuild the firmware and run
`python3 -m unittest tests.test_mp3_decoder`.
