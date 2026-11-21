"""Workshop Ledger data job: run by GitHub Actions every ~15 minutes.

Fetches public Steam data for every Workshop item on the profile below and writes
  docs/data/stats.json      what the page shows (mods, 24 h gains, subscriber trend)
  docs/data/comments.json   latest comments across all mods
  state/*.json              memory between runs (history, last good page data, known comments)
New comments by other people are pushed to the phone through ntfy when the
NTFY_TOPIC secret is set.
"""
import html as htmllib
import json, os, re, time
import urllib.request, urllib.parse

STEAM_ID = "76561198108112056"
APP_ID = "1158310"  # Crusader Kings III
HIDDEN_IDS = {"3836185589"}  # left off the dashboard (Muster Army)
EXTRA_IDS = []  # add an id here if one ever fails to show up
MY_ACCOUNT = str(int(STEAM_ID) - 76561197960265728)  # your own replies never notify
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "").strip()
PAUSE = 4  # seconds between steamcommunity.com requests (it answers 429 to bursts)

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "docs", "data")
STATE = os.path.join(HERE, "state")
# Steam answers 429 to unusual user-agents, so look like a normal browser.
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/131.0 Safari/537.36"}


def get(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers=headers or UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def read_json(name, default):
    try:
        with open(os.path.join(STATE, name), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)


def discover_ids():
    ids = []
    try:
        for page in range(1, 6):
            html = get(f"https://steamcommunity.com/profiles/{STEAM_ID}/myworkshopfiles/"
                       f"?appid={APP_ID}&numperpage=30&p={page}")
            new = [i for i in dict.fromkeys(re.findall(r"sharedfiles/filedetails/\?id=(\d+)", html))
                   if i not in ids]
            if not new:
                break
            ids += new
            time.sleep(PAUSE)
    except Exception:
        pass
    if not ids:  # Steam refused the profile page: use the last known list
        ids = read_json("mod_ids.json", [])
    else:
        write_json(os.path.join(STATE, "mod_ids.json"), ids)
    ids += [str(i) for i in EXTRA_IDS if str(i) not in ids]
    return [i for i in ids if i not in HIDDEN_IDS]


def api_details(ids):
    form = {"itemcount": len(ids)}
    for n, i in enumerate(ids):
        form[f"publishedfileids[{n}]"] = i
    js = json.loads(get("https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/",
                        urllib.parse.urlencode(form).encode()))
    return [d for d in js["response"]["publishedfiledetails"] if d.get("result") == 1]


def num(rx, html):
    m = re.search(rx, html)
    return int(m.group(1).replace(",", "")) if m else None


def page_extras(fid):
    """Rating, comments, change notes, visitors from the public Workshop page."""
    try:
        html = get(f"https://steamcommunity.com/sharedfiles/filedetails/?id={fid}")
    except Exception:
        return None
    if "fileRatingDetails" not in html:
        return None
    m = re.search(r'fileRatingDetails"><img src="[^"]*/(\d)-star_large', html)
    return {"stars": int(m.group(1)) if m else None,
            "ratings": num(r"([\d,]+) ratings", html) or 0,
            "comments": num(r'_totalcount">([\d,]+)<', html) or 0,
            "changenotes": num(r"([\d,]+) Change Notes", html) or 0,
            "visitors": num(r"<td>([\d,]+)</td>\s*<td>Unique Visitors", html),
            "t": int(time.time())}


def clean(text):
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r'<img[^>]*alt="([^"]*)"[^>]*>', r" \1 ", text)  # Steam emoticons -> :name:
    text = re.sub(r"<[^>]+>", "", text)
    return htmllib.unescape(text).strip()


def fetch_comments(fid, count=25):
    try:
        js = json.loads(get(f"https://steamcommunity.com/comment/PublishedFile_Public/render/{STEAM_ID}/{fid}/",
                            urllib.parse.urlencode({"start": 0, "count": count}).encode()))
    except Exception:
        return None
    if not js.get("success"):
        return None
    out = []
    for block in js.get("comments_html", "").split('class="commentthread_comment ')[1:]:
        cid = re.search(r'id="comment_(\d+)"', block)
        ts = re.search(r'data-timestamp="(\d+)"', block)
        if not (cid and ts):
            continue
        prof = re.search(r'commentthread_author_link" href="([^"]+)"\s+data-miniprofile="(\d+)"', block)
        name = re.search(r"<bdi>(.*?)</bdi>", block, re.S)
        av = re.search(r'commentthread_comment_avatar.*?<img src="([^"]+)"', block, re.S)
        text = re.search(r'commentthread_comment_text"[^>]*>(.*?)</div>', block, re.S)
        n = len(out)  # position in the thread, newest first; Steam pages hold 50
        out.append({"id": cid.group(1), "mod": fid, "t": int(ts.group(1)),
                    "url": f"https://steamcommunity.com/sharedfiles/filedetails/comments/{fid}"
                           f"?ctp={n // 50 + 1}#comment_{cid.group(1)}",
                    "author": clean(name.group(1)) if name else "?",
                    "profile": prof.group(1) if prof else "",
                    "mine": bool(prof and prof.group(2) == MY_ACCOUNT),
                    "avatar": av.group(1) if av else "",
                    "text": clean(text.group(1)) if text else ""})
    return out


def notify(title, message, click):
    if not NTFY_TOPIC:
        return
    body = json.dumps({"topic": NTFY_TOPIC, "title": title, "message": message[:400],
                       "click": click, "tags": ["speech_balloon"]}).encode()
    try:
        get("https://ntfy.sh/", body, {"Content-Type": "application/json"})
    except Exception as e:
        print("ntfy failed:", e)


def main():
    now = int(time.time())
    ids = discover_ids()
    details = api_details(ids)
    titles = {d["publishedfileid"]: d.get("title", "") for d in details}

    # Workshop pages (rating, comments...). Keep the last good values when Steam refuses.
    extras = read_json("page_cache.json", {})
    todo = [d["publishedfileid"] for d in details]
    for attempt in range(3):  # refused pages get retried, more slowly each pass
        failed = []
        for fid in todo:
            e = page_extras(fid)
            if e:
                extras[fid] = e
            else:
                failed.append(fid)
            time.sleep(PAUSE * (attempt + 1))
        if not failed:
            break
        todo = failed
        time.sleep(20 * (attempt + 1))
    write_json(os.path.join(STATE, "page_cache.json"), extras)

    # Comments, and phone alerts for new ones by other people.
    store = read_json("comments.json", {})
    first_run = not store
    new = []
    for fid in titles:
        items = fetch_comments(fid)
        if items is not None:
            if fid in store:
                known = {c["id"] for c in store[fid]}
                new += [c for c in items if c["id"] not in known and not c["mine"]]
            store[fid] = items
        time.sleep(PAUSE)
    write_json(os.path.join(STATE, "comments.json"), store)
    if not first_run:
        for c in sorted(new, key=lambda c: c["t"])[-5:]:
            notify(f"New comment on {titles.get(c['mod'], 'your mod')}", f"{c['author']}: {c['text']}", c["url"])
        if len(new) > 5:
            notify(f"{len(new)} new Workshop comments", "Open Workshop Ledger to read them all.", "")

    mods = []
    for d in details:
        fid = d["publishedfileid"]
        e = extras.get(fid, {})
        mods.append({
            "id": fid, "title": d.get("title", ""), "preview": d.get("preview_url", ""),
            "visibility": {0: "Public", 1: "Friends", 2: "Private", 3: "Unlisted"}.get(d.get("visibility"), "?"),
            "subs": d.get("subscriptions", 0), "lifetime_subs": d.get("lifetime_subscriptions", 0),
            "favorites": d.get("favorited", 0), "views": d.get("views", 0),
            "visitors": e.get("visitors"), "size": int(d.get("file_size") or 0),
            "created": d.get("time_created", 0), "updated": d.get("time_updated", 0),
            "tags": [t["tag"] for t in d.get("tags", [])],
            "stars": e.get("stars"), "ratings": e.get("ratings"), "comments": e.get("comments"),
            "changenotes": e.get("changenotes"), "pending": not e,
        })

    # History: one snapshot per 30 min, used for 24 h gains and the trend line.
    hist = read_json("history.json", [])
    base = None
    for s in hist:
        if s["t"] <= now - 86400:
            base = s
    for m in mods:
        old = base and base["mods"].get(m["id"])
        m["d1"] = None if not old else {k: m[k] - old[k] for k in old
                                        if m.get(k) is not None and old[k] is not None}
    if not hist or now - hist[-1]["t"] >= 1800:
        hist.append({"t": now, "mods": {m["id"]: {k: m[k] for k in
                     ("subs", "favorites", "visitors", "comments", "ratings")} for m in mods}})
        hist = hist[-6000:]
        write_json(os.path.join(STATE, "history.json"), hist)
    series = [{"t": s["t"], "subs": sum(v["subs"] for k, v in s["mods"].items() if k not in HIDDEN_IDS)}
              for s in hist][-500:]

    write_json(os.path.join(OUT, "stats.json"), {"fetched": now, "mods": mods, "series": series})
    comments = [dict(c, title=titles.get(fid, fid)) for fid, items in store.items()
                if fid in titles for c in items]
    comments.sort(key=lambda c: -c["t"])
    write_json(os.path.join(OUT, "comments.json"), {"fetched": now, "items": comments[:150]})
    print(f"{len(mods)} mods, {len(comments)} comments, {len(new)} new")


if __name__ == "__main__":
    main()
