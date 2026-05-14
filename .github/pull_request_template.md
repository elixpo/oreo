<!--
Thanks for sending a PR to OreoOS! 🐼
Fill out the sections that apply; delete the rest.
-->

## What's changing

<!-- 1-2 sentences. The README of this PR. -->

## Why

<!-- The motivation. Linked issue? User-reported bug? Design tweak? -->

Fixes: #
Related: #

## Type of change

- [ ] 🐛 Bug fix
- [ ] ✨ New app
- [ ] 🔧 OS / driver change
- [ ] 🎨 UI / theme polish
- [ ] 📦 Build / tooling
- [ ] 📚 Docs
- [ ] 🔐 Security
- [ ] 🧪 Test / CI

## How was it tested

<!-- Did you flash a real badge? Run any of the apps? Confirm wake-from-sleep? -->

- [ ] `python tools/deploy.py /dev/ttyACM0` passed
- [ ] Booted to home screen on hardware
- [ ] App(s) touched still open + render
- [ ] Wake-from-sleep still works (if power-management touched)
- [ ] OTA staging not broken (if `oreoOS/ota.py` or release pipeline touched)

## Screenshots / photos

<!-- Phone snaps of the badge running the change are very welcome. -->

## Checklist before merging

- [ ] I read [`CONTRIBUTING.md`](https://github.com/elixpo/oreo-badge/blob/main/CONTRIBUTING.md).
- [ ] My changes follow the project's tone + commenting style.
- [ ] No `print()` debug spam left behind.
- [ ] If I added a new app, it has a manifest, an icon prompt under `prompts/`, and an entry in `apps/`.
- [ ] If I touched `oreoOS/config.py: VERSION`, I bumped it intentionally.

---

<sub>By submitting this PR I confirm my contribution is offered under the
[Oreo Panda Community Licence](https://github.com/elixpo/oreo-badge/blob/main/LICENSE).</sub>
