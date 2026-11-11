# Contributing to Elixpo

Thank you for your interest in contributing! Elixpo is built in the open by a
community of 45+ contributors, and we welcome developers, designers, writers,
and first-time contributors alike. This guide is the **standard** used across
every Elixpo repository.

## Ways to contribute

- **Code** - fix a bug, build a feature, improve performance or accessibility.
- **Docs** - improve guides, READMEs, or inline comments.
- **Design & brand** - icons, illustrations, and assets (see `brand/MASCOT.md`).
- **Triage** - reproduce issues, suggest labels, help others in Discussions.
- **Ideas** - propose features in [GitHub Discussions](https://github.com/orgs/elixpo/discussions).
- **Google Summer of Code 2027** - Elixpo is applying as a mentoring organisation; see the proposed ideas at [gsoc.elixpo.com](https://gsoc.elixpo.com).

## Before you start

1. Read the [Code of Conduct](CODE_OF_CONDUCT.md) - it applies everywhere.
2. Look for issues labelled **good first issue** or **help wanted**.
3. For anything non-trivial, open or comment on an issue first so we can align
   before you invest time.

## Workflow

1. **Fork** the repository and create a branch from `main`:
   `git checkout -b feat/short-description`
2. **Make your change.** Match the existing code style and keep commits focused.
3. **Test it.** Make sure the project builds and existing checks pass.
4. **Open a pull request** with a clear title and description of what changed
   and why. Link any related issue.
5. A maintainer will review. Address feedback, and once approved we merge.

## Contributing to OreoOS

### Apps

Start from [`app_templates/`](app_templates/) and follow
[`docs/APPS.md`](docs/APPS.md). Before opening a pull request:

- [ ] `python3 tools/validate_app.py <your app folder>` reports no errors.
- [ ] The app folder has a `README.md`: one sentence on what it does, the
      controls, and a screenshot or photo of it running on a badge.
- [ ] The app has an icon (`python3 tools/app_icon.py <folder>`).
- [ ] A selects, B goes back, HOME exits; C is left to the notification
      panel unless the app sets `CAPTURES_C`.
- [ ] Movement uses `dt`, `draw()` skips unchanged frames, and nothing
      blocks the run loop.
- [ ] Saves go through `oreoOS.state`; the owner's details come from
      `oreoOS.profile`.
- [ ] No tokens, passwords or personal data in the code.
- [ ] App Store apps: `python3 tools/build_store_index.py` run and the
      `apps_market/index.json` entry filled in; `version` bumped when an
      existing app changes.

### The OS

- Run `python3 -m unittest discover -s tests` (and
  `python3 -m unittest discover -s cli/tests` for `cli/`). Add a test for
  what you change; tests use only the standard library.
- Badge code runs on MicroPython 1.28 with a small heap. Keep imports
  light and compile-check with `mpy-cross` when you can.
- A new module under `oreoOS/` or `oreoWare/` must be added to the
  `DEPLOY` list in `tools/deploy.py` and to `SHIP_PATTERNS` in
  `tools/build_release.py`; a test fails otherwise.
- Coding agents: see [`AGENTS.md`](AGENTS.md).

### Releasing

Maintainers cut an OS release with `python tools/release.py` (see the
script's header for `--channel beta` and `--dry-run`). It reads
`VERSION` from `oreoOS/config.py`, tags `stable/vX.Y.Z` (or `beta/...`),
builds the OTA manifest with `tools/build_release.py` and publishes the
GitHub release that badges update from. Needs the `gh` CLI and push
access.

## Commit & PR conventions

- Write clear, present-tense commit messages (e.g. `fix: handle empty roster`).
- Keep pull requests small and single-purpose where possible.
- Update docs and tests alongside code changes.

## Licensing of contributions

By submitting a contribution you agree it is licensed inbound under the Elixpo
standard (**MIT** for code, **CC-BY-4.0** for assets) and that you have the
right to submit it. The
[Developer Certificate of Origin](https://developercertificate.org) applies to
every commit. We do not require a CLA. See [LICENSE](LICENSE) and
[NOTICE](LICENSES/NOTICE) for details, including the reserved Elixpo/Oreo brand.

## Questions?

Open a thread in [Discussions](https://github.com/orgs/elixpo/discussions) or
email **hello@elixpo.com**. We're glad you're here.
