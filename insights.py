"""Workshop insights that need the Steam Web API key (STEAM_API_KEY secret).

  * where each of your mods ranks: trending this week and most subscribed,
    among all CK3 mods and among AGOT submods
  * the AGOT leaderboard (top submods), with 24 h / 7 day subscriber growth
  * collections that include your mods, with alerts when a new one appears
Recomputed at most once an hour (about 60 API calls) and written to
docs/data/insights.json.
"""
import json, os, time, urllib.parse, urllib.request

APP = "1158310"   # Crusader Kings III
AGOT = "2962333032"  # A Game of Thrones: every submod lists it as required
EVERY = 3600       # seconds between recomputations
TOP = 10           # leaderboard length
MAX_PAGES_ALL = 10   # 100 ids per page: ranks up to #1000 among all CK3 mods
MAX_PAGES_AGOT = 8   # 723 AGOT submods today

KEY = os.environ.get("STEAM_API_KEY", "").strip()


def api(method, **q):
    """Call IPublishedFileService; returns the 'response' dict or None. Never logs the key."""
    q["key"] = KEY
    url = (f"https://api.steampowered.com/IPublishedFileService/{method}/v1/?"
           + urllib.parse.urlencode(q, doseq=True))
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.loads(r.read()).get("response", {})
    except Exception as e:
        print(f"{method} failed:", getattr(e, "code", type(e).__name__))
        return None


def details(ids, votes=True):
    """GetDetails for up to 100 ids per call -> {id: item}."""
    out = {}
    ids = list(dict.fromkeys(ids))
    for i in range(0, len(ids), 100):
        q = {f"publishedfileids[{n}]": fid for n, fid in enumerate(ids[i:i + 100])}
        r = api("GetDetails", includevotes="true" if votes else "false", includetags="false",
                includeadditionalpreviews="false", includechildren="false", short_description="true", **q)
        for d in (r or {}).get("publishedfiledetails", []):
            if d.get("result") == 1:
                out[str(d["publishedfileid"])] = d
    return out


def user_file_ids(steam_id):
    r = api("GetUserFiles", steamid=steam_id, appid=APP, numperpage=100, ids_only="true")
    if not r or "publishedfiledetails" not in r:
        return None
    return [str(d["publishedfileid"]) for d in r["publishedfiledetails"]]


TOTALS = {}


def ranked_ids(query_type, pages, stop_when=(), label=None, **extra):
    """Ids in ranked order, paging with the cursor until `stop_when` ids are all seen."""
    out, cursor, want = [], "*", set(stop_when)
    for _ in range(pages):
        r = api("QueryFiles", query_type=query_type, appid=APP, creator_appid=APP,
                numperpage=100, cursor=cursor, ids_only="true", **extra)
        if not r:
            break
        if label and r.get("total"):
            TOTALS[label] = r["total"]
        page = [str(d["publishedfileid"]) for d in r.get("publishedfiledetails", [])]
        out += page
        if not page or not r.get("next_cursor") or r["next_cursor"] == cursor:
            break
        cursor = r["next_cursor"]
        if want and want <= set(out):
            break
        time.sleep(0.3)
    return out


def rank_of(order, fid):
    try:
        return order.index(fid) + 1
    except ValueError:
        return None


def pct(v):
    up, down = v.get("votes_up", 0), v.get("votes_down", 0)
    return round(up / (up + down) * 100) if up + down else None


def growth(series, now, secs):
    """Subscriber change since the snapshot nearest `secs` ago."""
    base = None
    for t, subs in series:
        if t <= now - secs:
            base = subs
    return None if base is None or not series else series[-1][1] - base


def run(my_ids, state_dir, out_path, notify, now, read_json, write_json):
    if not KEY:
        return
    prev = read_json("insights_state.json", {})
    if now - prev.get("t", 0) < EVERY - 120:
        return
    mine = list(my_ids)

    # Rankings
    trend_all = ranked_ids(3, MAX_PAGES_ALL, mine, "all", days=7)
    subs_all = ranked_ids(9, MAX_PAGES_ALL, mine, "all")
    trend_agot = ranked_ids(3, MAX_PAGES_AGOT, mine, "agot", days=7, child_publishedfileid=AGOT)
    subs_agot = ranked_ids(9, MAX_PAGES_AGOT, mine, "agot", child_publishedfileid=AGOT)
    if not (trend_agot and subs_agot):
        print("insights: rankings unavailable this run")
        return
    ranks = {fid: {"trend_all": rank_of(trend_all, fid), "subs_all": rank_of(subs_all, fid),
                   "trend_agot": rank_of(trend_agot, fid), "subs_agot": rank_of(subs_agot, fid)}
             for fid in mine}

    # Collections that include each mod (file type 1 = collections)
    coll_of = {}
    for fid in mine:
        r = api("QueryFiles", query_type=9, appid=APP, creator_appid=APP, numperpage=100, cursor="*",
                ids_only="true", filetype=1, child_publishedfileid=fid)
        for d in (r or {}).get("publishedfiledetails", []):
            coll_of.setdefault(str(d["publishedfileid"]), []).append(fid)

    # Details for the leaderboards and collections
    lead_ids = subs_agot[:TOP] + trend_agot[:TOP] + subs_all[:TOP] + trend_all[:TOP]
    info = details(lead_ids + list(coll_of) + mine)

    # Subscriber history for leaderboard mods and yours (hourly, 8 days)
    hist = read_json("leader_history.json", {})
    for fid in set(lead_ids + mine):
        if fid in info:
            s = hist.setdefault(fid, [])
            s.append([now, info[fid].get("subscriptions", 0)])
            hist[fid] = [p for p in s if p[0] >= now - 8 * 86400]
    hist = {k: v for k, v in hist.items() if v and v[-1][0] >= now - 8 * 86400}
    write_json(os.path.join(state_dir, "leader_history.json"), hist)

    def row(fid, rank):
        d = info.get(fid, {})
        s = hist.get(fid, [])
        return {"id": fid, "rank": rank, "title": d.get("title", fid), "subs": d.get("subscriptions"),
                "positive": pct(d.get("vote_data") or {}), "preview": d.get("preview_url", ""),
                "d1": growth(s, now, 86400), "d7": growth(s, now, 7 * 86400), "mine": fid in mine}

    def board(order):
        rows = [row(fid, n + 1) for n, fid in enumerate(order[:TOP])]
        rows += sorted((row(fid, rank_of(order, fid)) for fid in mine
                        if fid not in order[:TOP] and rank_of(order, fid)), key=lambda r: r["rank"])
        return rows

    # Rank history (to show climbs over 24 h)
    rank_hist = read_json("rank_history.json", [])
    rank_hist.append({"t": now, "ranks": ranks})
    rank_hist = [r for r in rank_hist if r["t"] >= now - 3 * 86400]
    write_json(os.path.join(state_dir, "rank_history.json"), rank_hist)
    base = None
    for r in rank_hist:
        if r["t"] <= now - 86400:
            base = r
    for fid, rk in ranks.items():
        old = (base or {}).get("ranks", {}).get(fid, {})
        rk["d1"] = {k: old[k] - v for k, v in rk.items() if isinstance(v, int) and isinstance(old.get(k), int)}

    # Collections list
    first_seen = prev.get("collections_seen", {})
    first_run = not first_seen and not prev.get("t")
    collections = []
    for cid, mods in coll_of.items():
        d = info.get(cid, {})
        if cid not in first_seen:
            first_seen[cid] = now
            if not first_run:
                names = ", ".join(info.get(m, {}).get("title", m) for m in mods)
                notify(f"New collection: {d.get('title', 'untitled')}",
                       f"Includes {names} · {d.get('views', 0):,} visitors",
                       f"https://steamcommunity.com/sharedfiles/filedetails/?id={cid}")
        collections.append({"id": cid, "title": d.get("title", "(private or hidden)"),
                            "views": d.get("views", 0), "favorites": d.get("favorited", 0),
                            "items": d.get("num_children"),
                            "mods": mods, "first_seen": first_seen[cid]})
    # Steam counts no subscribers on collections, so rank them by visitors
    collections.sort(key=lambda c: -(c["views"] or 0))

    # Ranking milestones (top 10, top 5, #1 ...), each alerted once
    import milestones
    milestones.check_ranks({f: {k: v for k, v in r.items() if k != "d1"} for f, r in ranks.items()},
                           {f: info.get(f, {}).get("title", f) for f in mine},
                           state_dir, notify, read_json, write_json)

    write_json(os.path.join(state_dir, "insights_state.json"),
               {"t": now, "collections_seen": first_seen, "ranks": ranks})
    write_json(out_path, {
        "fetched": now,
        "totals": {"all": TOTALS.get("all"), "agot": TOTALS.get("agot")},
        "ranks": ranks,
        "leaders": {"subs": board(subs_agot), "trend": board(trend_agot)},
        "leaders_all": {"subs": board(subs_all), "trend": board(trend_all)},
        "collections": collections,
        "titles": {fid: info.get(fid, {}).get("title", fid) for fid in mine},
    })
    print(f"insights: {len(collections)} collections, ranks {ranks}")
