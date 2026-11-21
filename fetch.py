"""Workshop Ledger data job: run by GitHub Actions every ~15 minutes.

Fetches public Steam data for every Workshop item on the profile below and writes
  docs/data/stats.json      what the page shows (mods, 24 h gains, subscriber trend)
  docs/data/comments.json   latest comments across all mods
  state/*.json              memory between runs (history, known comments, milestones)
Everything that the Steam Web API offers comes from it (STEAM_API_KEY secret). Only
comment text comes from the comment feed (no API exists for it), and one Workshop page
per run cross-checks the star rating.
New comments by other people are pushed to the phone through ntfy when the
NTFY_TOPIC secret is set.
"""
import html as htmllib
import json, os, re, time
import urllib.request, urllib.parse
import insights
import milestones

STEAM_ID = "76561198108112056"
APP_ID = "1158310"  # Crusader Kings III
HIDDEN_IDS = {"3836185589"}  # left off the dashboard (Muster Army)
EXTRA_IDS = []  # add an id here if one ever fails to show up
MY_ACCOUNT = str(int(STEAM_ID) - 76561197960265728)  # your own replies never notify
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "").strip()
STEAM_API_KEY = os.environ.get("STEAM_API_KEY", "").strip()  # optional: enables up/down vote counts
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
    ids = insights.user_file_ids(STEAM_ID) if STEAM_API_KEY else None
    if ids:  # official list from the Web API
        write_json(os.path.join(STATE, "mod_ids.json"), ids)
        ids += [str(i) for i in EXTRA_IDS if str(i) not in ids]
        return [i for i in ids if i not in HIDDEN_IDS]
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
    """Keyless fallback (ISteamRemoteStorage) used only when the Web API key is missing."""
    form = {"itemcount": len(ids)}
    for n, i in enumerate(ids):
        form[f"publishedfileids[{n}]"] = i
    js = json.loads(get("https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/",
                        urllib.parse.urlencode(form).encode()))
    return {d["publishedfileid"]: d for d in js["response"]["publishedfiledetails"] if d.get("result") == 1}


def steam_details(ids):
    """Everything per mod from one API call: stats, votes, comment count, reports."""
    if STEAM_API_KEY:
        d = insights.details(ids)
        if d:
            return d, True
    return api_details(ids), False


MIN_RATED_VOTES = 26  # observed: 25 votes showed "not enough ratings", 26 showed stars


def stars_from_score(score, votes):
    """Steam's star image from the API vote score (matches every mod with stars so far:
    0.648 -> 4, 0.598 -> 3, 0.592 -> 3)."""
    if score is None or votes < MIN_RATED_VOTES:
        return None
    return 5 if score >= 0.8 else 4 if score >= 0.6 else 3 if score >= 0.4 else 2 if score >= 0.2 else 1


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


def check_stars(mods):
    """Cross-check one Workshop page per run against the API-based stars. If the page
    disagrees (same vote count), its value is kept as an override until votes change."""
    overrides = read_json("star_overrides.json", {})
    checked = read_json("star_checked.json", {})
    if not mods:
        return overrides
    # the mod whose vote count changed since its last check first, then the stalest
    todo = sorted(mods, key=lambda m: (checked.get(m["id"], {}).get("ratings") == m["ratings"],
                                       checked.get(m["id"], {}).get("t", 0)))
    m = todo[0]
    e = page_extras(m["id"])
    if e is None:
        print("Workshop page refused for", m["id"], "(stars stay API-based)")
        return overrides
    checked[m["id"]] = {"t": e["t"], "ratings": e["ratings"]}
    write_json(os.path.join(STATE, "star_checked.json"), checked)
    if e["ratings"] == m["ratings"] and e["stars"] != m["stars"]:
        print(f"stars: page says {e['stars']} for {m['id']}, API estimate {m['stars']}; using the page")
        overrides[m["id"]] = {"stars": e["stars"], "ratings": e["ratings"]}
        write_json(os.path.join(STATE, "star_overrides.json"), overrides)
    return overrides


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
    return out, js.get("total_count", len(out))


def notify(title, message, click):
    if not NTFY_TOPIC:
        return
    body = json.dumps({"topic": NTFY_TOPIC, "title": title, "message": message[:400],
                       "click": click, "tags": ["speech_balloon"]}).encode()
    try:
        get("https://ntfy.sh/", body, {"Content-Type": "application/json"})
    except Exception as e:
        print("ntfy failed:", e)


def rating_alerts(mods, prev_mods, titles):
    """Phone alerts for new downvotes, reports, and star drops (rises are milestones)."""
    page = lambda fid: f"https://steamcommunity.com/sharedfiles/filedetails/?id={fid}"
    for m in mods:
        was = prev_mods.get(m["id"])
        if not was or m.get("up") is None or was.get("up") is None:
            continue
        name = titles.get(m["id"], m["id"])
        if m["down"] > was["down"]:
            n = m["down"] - was["down"]
            total = m["up"] + m["down"]
            notify(f"{name}: {n} new downvote{'s' if n > 1 else ''}",
                   f"Now {m['up']:,} up · {m['down']:,} down ({round(m['up'] / total * 100)}% positive).", page(m["id"]))
        if (m.get("reports") or 0) > (was.get("reports") or 0):
            notify(f"{name} was reported", f"{m['reports']} report(s) on Steam. Worth checking the comments.", page(m["id"]))
        if m.get("stars") and was.get("stars") and m["stars"] < was["stars"]:
            notify(f"{name}: rating down to {m['stars']} stars", f"Was {was['stars']} stars.", page(m["id"]))


def check_comments(titles, counts=None):
    """Load comment feeds and alert on new comments. With `counts` (from the API), only
    mods whose comment count changed are loaded: fewer requests Steam can refuse."""
    store = read_json("comments.json", {})
    totals = read_json("comment_totals.json", {})
    first_run = not store
    new = []
    for fid in titles:
        if counts is not None and fid in store and counts.get(fid) == totals.get(fid):
            continue  # nothing new on this mod
        res = fetch_comments(fid)
        if res is not None:
            items, totals[fid] = res
            if fid in store:
                known = {c["id"] for c in store[fid]}
                new += [c for c in items if c["id"] not in known and not c["mine"]]
            store[fid] = items
        time.sleep(PAUSE)
    write_json(os.path.join(STATE, "comments.json"), store)
    write_json(os.path.join(STATE, "comment_totals.json"), totals)
    if not first_run:
        for c in sorted(new, key=lambda c: c["t"])[-5:]:
            notify(f"New comment on {titles.get(c['mod'], 'your mod')}", f"{c['author']}: {c['text']}", c["url"])
        if len(new) > 5:
            notify(f"{len(new)} new Workshop comments", "Open Workshop Ledger to read them all.", "")
    return store, totals, new


def write_comments_page(store, titles, now):
    comments = [dict(c, title=titles.get(fid, fid)) for fid, items in store.items()
                if fid in titles for c in items]
    comments.sort(key=lambda c: -c["t"])
    write_json(os.path.join(OUT, "comments.json"), {"fetched": now, "items": comments[:150]})
    return len(comments)


def comment_counts(details):
    return {fid: d["num_comments_public"] for fid, d in details.items() if "num_comments_public" in d}


def comments_only():
    """Quick run (every 5 min): comments and alerts only."""
    now = int(time.time())
    try:
        with open(os.path.join(OUT, "stats.json"), encoding="utf-8") as f:
            stats = json.load(f)
    except Exception:
        print("no stats.json yet; run the full update first")
        return
    titles = {m["id"]: m["title"] for m in stats["mods"]}
    details, keyed = steam_details(list(titles))
    counts = comment_counts(details) if keyed else None
    store, totals, new = check_comments(titles, counts)
    if not new:
        print("no new comments")
        return
    write_comments_page(store, titles, now)
    for m in stats["mods"]:
        m["comments"] = (counts or totals).get(m["id"], m["comments"])
    write_json(os.path.join(OUT, "stats.json"), stats)
    print(f"{len(new)} new comments")


def main():
    now = int(time.time())
    ids = discover_ids()
    details, keyed = steam_details(ids)
    titles = {fid: d.get("title", "") for fid, d in details.items()}
    try:
        with open(os.path.join(OUT, "stats.json"), encoding="utf-8") as f:
            prev_mods = {m["id"]: m for m in json.load(f)["mods"]}
    except Exception:
        prev_mods = {}

    counts = comment_counts(details) if keyed else None
    store, totals, new = check_comments(titles, counts)

    mods = []
    for fid in ids:
        d = details.get(fid)
        if not d:
            continue
        v = d.get("vote_data") or {}
        up, down = (v.get("votes_up"), v.get("votes_down")) if v else (None, None)
        ratings = up + down if up is not None else None
        mods.append({
            "id": fid, "title": d.get("title", ""), "preview": d.get("preview_url", ""),
            "visibility": {0: "Public", 1: "Friends", 2: "Private", 3: "Unlisted"}.get(d.get("visibility"), "?"),
            "subs": d.get("subscriptions", 0), "lifetime_subs": d.get("lifetime_subscriptions", 0),
            "favorites": d.get("favorited", 0), "views": d.get("views", 0),
            "visitors": d.get("views", 0),  # the API's views = unique visitors
            "size": int(d.get("file_size") or 0),
            "created": d.get("time_created", 0), "updated": d.get("time_updated", 0),
            "tags": [t["tag"] for t in d.get("tags", []) if isinstance(t, dict)],
            "stars": stars_from_score(v.get("score"), ratings or 0) if ratings is not None else None,
            "ratings": ratings, "up": up, "down": down, "reports": d.get("num_reports"),
            "comments": (counts or {}).get(fid, totals.get(fid)),
            "pending": ratings is None,
        })

    # One Workshop page per run, only as a cross-check of the API-based stars.
    overrides = check_stars([m for m in mods if m["ratings"] is not None])
    for m in mods:
        o = overrides.get(m["id"])
        if o and o["ratings"] == m["ratings"]:
            m["stars"] = o["stars"]

    rating_alerts(mods, prev_mods, titles)

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
    n_comments = write_comments_page(store, titles, now)
    print(f"{len(mods)} mods ({'API key' if keyed else 'keyless API'}), {n_comments} comments, {len(new)} new")
    try:
        for title, _, _ in milestones.check(mods, STATE, notify, read_json, write_json):
            print("milestone:", title)
    except Exception as e:
        print("milestones failed:", type(e).__name__, e)
    try:
        insights.run([m["id"] for m in mods], STATE, os.path.join(OUT, "insights.json"),
                      notify, now, read_json, write_json)
    except Exception as e:  # insights must never break the main update
        print("insights failed:", type(e).__name__, e)


if __name__ == "__main__":
    import sys
    comments_only() if "--comments" in sys.argv else main()
