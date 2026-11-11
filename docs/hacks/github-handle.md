# Put your GitHub handle on the badge

The **Badge** app turns the screen into a conference badge: your name, your
title, `@your-handle` and a GitHub card with your location, bio and repo,
follower and following counts. Nothing is set by default, so a fresh badge
shows a setup card instead of someone else's profile. This hack fills it in.

- **Difficulty:** beginner, about 5 minutes
- **You need:** a badge, a USB-C cable, [oreo-cli](../CLI.md#install), and
  Wi-Fi on the badge for the GitHub card (your name and title work without it)

## 1. Connect the badge

Plug the badge into your computer and check that `oreo` finds it:

```bash
oreo doctor
```

If it does not, [USB.md](../USB.md) covers ports and Linux permissions.

## 2. Set your profile

The profile is a small file on the badge, `/profile.json`. `oreo setup`
writes it for you. Either answer the questions:

```bash
oreo setup
```

or give the values directly:

```bash
oreo setup --github-user octocat --name "Mona Lisa" --designation "Firmware @ Example"
```

The keys behind these options are the same names you would put in
`.env.local`:

| Key | What the Badge app does with it |
|---|---|
| `GITHUB_USER` | `@handle` under your name, and the GitHub card |
| `DISPLAY_NAME` | Your name, in the large font (falls back to your GitHub name, then the login) |
| `DISPLAY_DESIGNATION` | The line under your name (`DESIGNATION` is accepted as the older name) |

If you keep them in an `.env`-style file, `oreo setup --from-file .env.local`
takes only the profile keys and leaves everything else in the file alone.
Names must be short plain ASCII: the badge font has no other characters.

`oreo setup` restarts OreoOS when it is done, so the apps read the new
profile.

## 3. Give it Wi-Fi

The GitHub card comes from GitHub's public API, fetched by the badge
itself. Add a network once:

```bash
oreo wifi connect "Home Net"
```

The badge only uses Wi-Fi for the internet; everything from your computer
goes over USB.

## 4. Open Badge

Open **Badge** from the apps drawer. Your name and title show at once. The
GitHub card is cached on flash, so after the first fetch it draws
immediately, Wi-Fi or not. It refreshes in the background when the copy is
older than six hours (`PROFILE_TTL_S` in `oreoOS/github.py`), or when you
press **A**.

## 5. Your avatar (optional)

The round photo comes from a module baked on your computer, not fetched by
the badge: `apps/badge/assets/optimized/avatar.py`. Without it the badge
draws your initials. Note that the repository currently ships the
maintainer's avatar in that file, so replace it with yours. From an OreoOS
checkout (it needs Pillow):

```bash
python3 tools/fetch_avatar.py --user octocat
oreo push apps/badge/assets/optimized/avatar.py /apps/badge/assets/optimized/avatar.py
```

An OreoOS update or a deploy from a checkout without your file puts the
shipped avatar back; run the two commands again afterwards.

## Troubleshooting

- **Only a setup card:** neither `GITHUB_USER` nor `DISPLAY_NAME` is set.
  `oreo setup --show` prints what the badge has and where each value came
  from.
- **No GitHub card:** the badge is offline, or GitHub's limit of 60
  unauthenticated requests an hour per network was reached. The card
  appears after the next successful refresh.
- **Developers:** apps read the profile with
  `oreoOS.profile.get("GITHUB_USER")`; see [PROFILE.md](../PROFILE.md).

## See also

- [PROFILE.md](../PROFILE.md): every profile key and where the badge looks
  for it
- [CLI.md: oreo setup](../CLI.md#oreo-setup-owner-profile)
