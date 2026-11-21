"""Milestone alerts: subscribers and favorites per mod, and total subscribers.

The last milestone reached for each counter is kept in state/milestones.json,
so every alert fires once. Counters seen for the first time are recorded
silently (no alerts for milestones passed before tracking started).
"""
import os

SUBS = [100, 250, 500, 750, 1000, 1500, 2000, 2500, 3000, 4000, 5000, 7500, 10000, 15000, 20000,
        25000, 30000, 40000, 50000, 75000, 100000, 150000, 200000, 250000, 500000, 1000000]
FAVS = [50, 100, 250, 500, 750, 1000, 2500, 5000, 10000, 25000, 50000, 100000]
TOTAL = [2500, 5000, 7500, 10000, 15000, 20000, 25000, 30000, 40000, 50000, 75000, 100000,
         150000, 178000, 200000, 250000, 500000, 1000000]  # 178k = top-submod size goal


def reached(value, steps):
    best = 0
    for s in steps:
        if value >= s:
            best = s
    return best


def check(mods, state_dir, notify, read_json, write_json):
    state = read_json("milestones.json", {})
    alerts = []
    page = lambda fid: f"https://steamcommunity.com/sharedfiles/filedetails/?id={fid}"

    def track(key, value, steps, title, body, url):
        level = reached(value or 0, steps)
        if key not in state:
            state[key] = level  # first time: remember silently
            return
        if level > state[key]:
            state[key] = level
            alerts.append((title(level), body, url))

    for m in mods:
        fid, name = m["id"], m["title"]
        track(f"subs:{fid}", m.get("subs"), SUBS,
              lambda n, name=name: f"🎉 {name} reached {n:,} subscribers",
              f"Now {m.get('subs', 0):,} subscribers and {m.get('favorites', 0):,} favorites.", page(fid))
        track(f"favs:{fid}", m.get("favorites"), FAVS,
              lambda n, name=name: f"⭐ {name} reached {n:,} favorites",
              f"Now {m.get('favorites', 0):,} favorites.", page(fid))
    total = sum(m.get("subs") or 0 for m in mods)
    track("subs:total", total, TOTAL,
          lambda n: f"🏆 Your mods reached {n:,} subscribers in total",
          f"{total:,} subscribers across {len(mods)} mods.", "https://gratierodu.github.io/workshop-ledger/")

    for title, body, url in alerts:
        notify(title, body, url)
    write_json(os.path.join(state_dir, "milestones.json"), state)
    return alerts
