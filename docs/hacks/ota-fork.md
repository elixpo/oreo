# Self-host OTA updates from your fork

Badges update OreoOS over the air from GitHub releases of `elixpo/oreo`.
Point your badge at your own fork instead, and every release you publish
there reaches your badge through **Settings > Updates** or `oreo update`,
with the same checks as an official update.

- **Difficulty:** advanced, about an hour
- **You need:** a GitHub fork of `elixpo/oreo` and a clone of it, the
  [`gh`](https://cli.github.com) CLI logged in (`gh auth status`), a badge
  with Wi-Fi, a USB-C cable and [oreo-cli](../CLI.md#install)

## How OTA works

`oreoOS/ota.py` updates files, not firmware:

1. It lists the repository's tags
   (`https://api.github.com/repos/<OTA_REPO>/tags?per_page=10`) and takes
   the first tag on its channel: `stable/vX.Y.Z` or `beta/vX.Y.Z`.
2. If that version is newer than `VERSION` in `oreoOS/config.py`, it
   downloads `manifest.json` from the release with that tag. The manifest
   lists every file with its size, SHA-256 and download URL.
3. Files whose checksum differs are downloaded into `/_ota/` and checked.
   The manifest is written last, as the "ready" marker.
4. On the next boot the files are moved into place. A power cut before
   that leaves the old version running.

Apps, photos, documents, saved Wi-Fi and your profile are kept.

## 1. Point the code at your fork

In your clone, change two lines (`you/oreo` is your fork):

- `oreoOS/ota.py`:

  ```python
  OTA_REPO       = "you/oreo"      # owner/repo on GitHub
  ```

- `tools/release.py`, where the manifest's download URLs are built:

  ```python
  asset_base = "https://github.com/you/oreo/releases/download/%s/" % tag
  ```

  Without this, the manifest from your release points at `elixpo/oreo`'s
  downloads, which do not exist for your tag.

Make `gh` act on your fork rather than the upstream repository:

```bash
gh repo set-default you/oreo
```

## 2. Put your build on the badge once, over USB

The badge still asks `elixpo/oreo` until it runs your `ota.py`. Install
your checkout over USB:

```bash
oreo update --repo .        # runs ./deploy --board from this checkout
```

(or `./deploy --board` directly).

## 3. Publish a release

Pick a version higher than what the badge runs and higher than any tag
your fork copied from upstream, then preview and publish:

```bash
python3 tools/release.py v9.0.0 --dry-run      # prints every command
python3 tools/release.py v9.0.0                # stable channel
python3 tools/release.py v9.1.0 --channel beta # or a prerelease
```

`release.py` sets `VERSION` in `oreoOS/config.py`, commits, tags
`stable/v9.0.0` (or `beta/...`), pushes, builds the manifest and files with
`tools/build_release.py` into `dist/`, and creates the GitHub release with
them. If it stops halfway, run it again: it resumes from the tag or the
upload.

Check that your tag is among the ten the badge reads:

```bash
gh api "repos/you/oreo/tags?per_page=10" --jq '.[].name'
```

## 4. Update the badge

On the badge, **Settings > Updates** checks the stable channel. From a
computer, with the badge on USB:

```bash
oreo update --check            # is there a newer release?
oreo update                    # stable
oreo update --channel beta     # beta
```

The badge also checks by itself in the background, but not in the first
15 minutes after boot.

## Things to know

- **Your fork controls your badge.** Anyone who can push tags and releases
  to the fork can change the code it runs. Protect the fork like a deploy
  key.
- **Firmware is not updated.** OTA only replaces OreoOS's Python files and
  assets. A firmware change needs `oreo flash` over USB.
- **Going back to official updates:** set `OTA_REPO` back to
  `elixpo/oreo` and install that over USB, or run `oreo update --repo`
  from an upstream checkout.
- **GitHub rate limit:** the badge asks without a token, which allows 60
  requests an hour per network.
- `secrets.py`, caches and raw assets are never part of a release
  (`tools/build_release.py`).

## See also

- [CLI.md: oreo update](../CLI.md#oreo-update-update-oreoos)
- [HARDWARE.md: OTA update partition](../HARDWARE.md#ota-update-partition)
