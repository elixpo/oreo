"""A small streaming RSS parser for podcast feeds.

Feeds can be megabytes (years of episodes, each with a long HTML
description), so the parser never holds the feed: feed() takes it in
chunks as it downloads, keeps only an unfinished tag (at most MAX_TAG
bytes) and the text of the few elements it wants, and drops everything
else, CDATA and comments included, as it goes. Once it has max_items
episodes, `done` is set and the download can stop.

    p = RssParser(max_items=40)
    for chunk in body:
        if not p.feed(chunk):
            break
    p.title, p.items   # items: {title, url, length, date, duration, guid}

Only episodes with an MP3 enclosure are kept (the badge decodes MP3);
`skipped` counts the others.
"""

MAX_TAG = 4096
MAX_TEXT = 300

_ENT = {"amp": "&", "lt": "<", "gt": ">", "quot": "\"", "apos": "'", "nbsp": " "}

# Elements whose text an episode keeps, by tag name -> item key.
_ITEM_TEXT = {"title": "title", "pubdate": "date", "itunes:duration": "duration",
              "guid": "guid", "itunes:title": "ititle"}


def unescape(s):
    """Decode XML entities (&amp; &#39; &#x2019; ...)."""
    if "&" not in s:
        return s
    out = []
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if ch != "&":
            out.append(ch)
            i += 1
            continue
        j = s.find(";", i + 1, i + 12)
        if j < 0:
            out.append(ch)
            i += 1
            continue
        ent = s[i + 1:j]
        rep = None
        if ent.startswith("#x") or ent.startswith("#X"):
            try:
                rep = chr(int(ent[2:], 16))
            except Exception:
                rep = None
        elif ent.startswith("#"):
            try:
                rep = chr(int(ent[1:]))
            except Exception:
                rep = None
        else:
            rep = _ENT.get(ent)
        if rep is None:
            out.append(ch)
            i += 1
        else:
            out.append(rep)
            i = j + 1
    return "".join(out)


def attrs(tag):
    """{name: value} of a tag's attributes (names lower-cased)."""
    out = {}
    i = 0
    n = len(tag)
    # skip the element name
    while i < n and tag[i] not in " \t\r\n":
        i += 1
    while i < n:
        while i < n and tag[i] in " \t\r\n/":
            i += 1
        eq = tag.find("=", i)
        if eq < 0:
            break
        name = tag[i:eq].strip().lower()
        j = eq + 1
        while j < n and tag[j] in " \t\r\n":
            j += 1
        if j >= n:
            break
        q = tag[j]
        if q in "\"'":
            end = tag.find(q, j + 1)
            if end < 0:
                end = n
            out[name] = unescape(tag[j + 1:end])
            i = end + 1
        else:
            end = j
            while end < n and tag[end] not in " \t\r\n>":
                end += 1
            out[name] = unescape(tag[j:end])
            i = end
    return out


def duration_s(text):
    """itunes:duration ("1:02:03", "62:03" or "3723") in seconds."""
    if not text:
        return 0
    try:
        parts = [int(float(p)) for p in text.strip().split(":")]
    except ValueError:
        return 0
    s = 0
    for p in parts:
        s = s * 60 + p
    return s


def is_mp3(url, mime):
    mime = (mime or "").lower()
    if mime in ("audio/mpeg", "audio/mp3", "audio/mpeg3", "audio/x-mpeg", "audio/x-mp3"):
        return True
    if mime and not mime.startswith("application/octet") and mime != "audio":
        return False
    return url.split("?", 1)[0].lower().endswith(".mp3")


def _dec(b):
    try:
        return bytes(b).decode("utf-8")
    except Exception:
        return "".join(chr(c) if c < 128 else "?" for c in bytes(b))


class RssParser:
    def __init__(self, max_items=40):
        self.max_items = max_items
        self.title = ""
        self.items = []
        self.skipped = 0
        self.done = False
        self._buf = bytearray()
        self._mode = 0              # 0 markup, 1 CDATA, 2 comment
        self._item = None
        self._depth_skip = 0        # inside <image> etc. at channel level
        self._cap = None            # element whose text is being kept
        self._text = bytearray()

    def feed(self, data):
        """Parse the next chunk. Returns False once done (stop reading)."""
        if self.done:
            return False
        self._buf.extend(data)
        self._run()
        return not self.done

    def _keep_text(self, b):
        if self._cap is not None and len(self._text) < MAX_TEXT * 2:
            self._text.extend(b[:MAX_TEXT * 2 - len(self._text)])

    def _run(self):
        buf = self._buf
        while buf and not self.done:
            if self._mode:
                end = b"]]>" if self._mode == 1 else b"-->"
                i = buf.find(end)
                if i < 0:
                    keep = len(buf) - 2
                    if keep > 0:
                        if self._mode == 1:
                            self._keep_text(buf[:keep])
                        del buf[:keep]
                    return
                if self._mode == 1:
                    self._keep_text(buf[:i])
                del buf[:i + 3]
                self._mode = 0
                continue
            lt = buf.find(b"<")
            if lt < 0:
                self._keep_text(buf)
                del buf[:]
                return
            if lt:
                self._keep_text(buf[:lt])
                del buf[:lt]
            if len(buf) < 9 and (b"<![CDATA["[:len(buf)] == bytes(buf) or
                                 b"<!--"[:len(buf)] == bytes(buf[:4])):
                return                  # can't tell yet
            if buf[:9] == b"<![CDATA[":
                self._mode = 1
                del buf[:9]
                continue
            if buf[:4] == b"<!--":
                self._mode = 2
                del buf[:4]
                continue
            gt = buf.find(b">")
            if gt < 0:
                if len(buf) > MAX_TAG:
                    del buf[:]          # not a tag we can use; resync
                return
            tag = _dec(buf[1:gt])
            del buf[:gt + 1]
            self._tag(tag)

    def _tag(self, tag):
        if not tag or tag[0] in "?!":
            return
        closing = tag[0] == "/"
        if closing:
            tag = tag[1:]
        selfclose = tag.endswith("/")
        sp = 0
        while sp < len(tag) and tag[sp] not in " \t\r\n/":
            sp += 1
        name = tag[:sp].lower()
        if closing:
            self._close(name)
        else:
            self._open(name, tag)
            if selfclose:
                self._close(name)

    def _open(self, name, tag):
        if name == "item":
            self._item = {}
            self._cap = None
            return
        if self._item is not None:
            if name == "enclosure":
                a = attrs(tag)
                url = a.get("url", "")
                if url and "url" not in self._item:
                    if is_mp3(url, a.get("type")):
                        self._item["url"] = url
                        try:
                            self._item["length"] = int(a.get("length") or 0)
                        except ValueError:
                            self._item["length"] = 0
                    else:
                        self._item["bad"] = True
            elif name in _ITEM_TEXT and self._cap is None:
                self._cap = name
                self._text = bytearray()
            return
        if name in ("image", "itunes:owner", "itunes:category"):
            self._depth_skip += 1
        elif name == "title" and not self.title and not self._depth_skip:
            self._cap = name
            self._text = bytearray()

    def _close(self, name):
        if name == self._cap:
            text = unescape(_dec(self._text)).strip()[:MAX_TEXT]
            self._cap = None
            self._text = bytearray()
            if self._item is not None:
                key = _ITEM_TEXT.get(name)
                if key and key not in self._item:
                    self._item[key] = text
            elif name == "title":
                self.title = text
            return
        if name == "item" and self._item is not None:
            it = self._item
            self._item = None
            self._cap = None
            if "url" not in it:
                if it.get("bad"):
                    self.skipped += 1
                return
            title = it.get("title") or it.get("ititle") or "Episode"
            self.items.append({
                "title": title,
                "url": it["url"],
                "length": it.get("length", 0),
                "date": _short_date(it.get("date", "")),
                "duration": duration_s(it.get("duration", "")),
                "guid": it.get("guid") or it["url"],
            })
            if len(self.items) >= self.max_items:
                self.done = True
        elif name in ("image", "itunes:owner", "itunes:category") and self._depth_skip:
            self._depth_skip -= 1


def _short_date(rfc822):
    """'Tue, 03 Nov 2026 10:00:00 GMT' -> '03 Nov 2026'."""
    parts = rfc822.replace(",", " ").split()
    if len(parts) >= 4 and parts[0][:1].isalpha() and not parts[0][:1].isdigit():
        parts = parts[1:]
    return " ".join(parts[:3])
