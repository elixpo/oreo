# App Store catalogue

Every folder here is an app the badge's **App Store** can install. The
Store does not walk this tree on the badge; it downloads one file,
[`index.json`](index.json), from
`raw.githubusercontent.com/elixpo/oreo/main/apps_market/index.json`, caches
it on flash and installs each app's files from the paths listed there.

## Adding or changing an app

1. Create or edit `apps_market/<folder>/` (`main.py`, `manifest.json`,
   `__init__.py`, `src/`, `assets/optimized/`). Raw and transparent PNGs
   stay in the repo; only `assets/optimized/*.py` goes to the badge.
2. Run `python3 tools/build_store_index.py`. It refreshes each entry's
   id (manifest `slug` or the folder name), version, icon, file list and
   size, and adds an entry for any new folder.
3. In `index.json`, give a new entry its `name`, `tagline` (24 characters
   at most: it is the one-line text in the Store list), `description`,
   `category` (Games, Tools, Utilities, Social or System) and `author`.
   These hand-written fields are kept when the tool runs again.
4. Commit the folder and `index.json` together. `tests/test_store.py`
   fails if the index is out of date.

The icon is looked up in the OS image first (`assets/icons/optimized/`),
then downloaded from `apps_market/<folder>/assets/optimized/<icon>.py`,
so an app with a new icon must ship its optimized icon module there.

An entry may be listed before its folder exists (Patakha while it is
being built); the badge then finds its files through the GitHub API at
install time. Run the tool once the folder lands.

## Doom's game data

Doom's engine is in the firmware; its data (Freedoom Episode 1 packed as
OWZ, 6.9 MB) goes into the `doom` flash partition. The Doom entry's
`data` field gives the download URL, size and SHA-256. The App Store
streams it into the partition, verifies it, and only then writes the
first block, so the engine never sees half-written data. It writes
nothing but the `doom` partition.

The URL points at a GitHub release asset that must be published once
(and again whenever the Freedoom version or `tools/pack_wad.py` output
changes):

```bash
python3 tools/fetch_freedoom.py
python3 tools/build_store_index.py --doom-data oreoWare/doom/freedoom1.owz
gh release create doom-freedoom-0.13.0 \
    oreoWare/doom/freedoom1.owz oreoWare/doom/FREEDOOM-COPYING.txt \
    --repo elixpo/oreo --latest=false \
    --title "Doom game data (Freedoom 0.13.0)" \
    --notes "Freedoom Episode 1 packed for the Oreo Badge's doom partition. BSD-3-Clause, see FREEDOOM-COPYING.txt."
```

`--latest=false` matters: OTA updates read `releases/latest`, so this
release must never become the latest one. If `build_store_index.py`
changes the size or SHA-256, commit `index.json`, because the badge
rejects a download that does not match it.
