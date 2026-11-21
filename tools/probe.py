"""One-off: print the shape of Steam API answers (never the key)."""
import json, os, urllib.request, urllib.parse

KEY = os.environ["STEAM_API_KEY"].strip()
STEAM_ID = "76561198108112056"
APP = 1158310
AGOT = "2962333032"
ARMORY = "3841377701"


def call(method, **q):
    q["key"] = KEY
    url = f"https://api.steampowered.com/IPublishedFileService/{method}/v1/?" + urllib.parse.urlencode(q, doseq=True)
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.loads(r.read())["response"]
    except Exception as e:
        return {"ERROR": getattr(e, "code", str(type(e).__name__))}


def show(label, resp, n=3, fields=("publishedfileid", "title", "subscriptions", "file_type", "followers", "vote_data")):
    print(f"\n=== {label}")
    items = resp.get("publishedfiledetails") or []
    print("top keys:", {k: (v if not isinstance(v, (list, dict)) else type(v).__name__) for k, v in resp.items() if k != "publishedfiledetails"})
    if items:
        print("item keys:", sorted(items[0].keys()))
    for it in items[:n]:
        print({k: it.get(k) for k in fields})


d = call("GetDetails", **{"publishedfileids[0]": ARMORY, "includevotes": "true", "includechildren": "true",
                          "includeadditionalpreviews": "false", "includetags": "false"})
show("GetDetails Armory", d, 1, ("publishedfileid", "title", "subscriptions", "followers", "lifetime_followers",
                                  "num_reports", "num_children", "vote_data", "lifetime_playtime", "views", "num_comments_public", "children"))

show("GetUserFiles", call("GetUserFiles", steamid=STEAM_ID, appid=APP, numperpage=50, return_vote_data="true"), 10,
     ("publishedfileid", "title", "subscriptions", "visibility", "vote_data"))

base = {"appid": APP, "creator_appid": APP, "numperpage": 5, "return_vote_data": "true", "cursor": "*"}
show("QueryFiles trend 7d (all CK3)", call("QueryFiles", query_type=3, days=7, **base))
show("QueryFiles most subscribed (all CK3)", call("QueryFiles", query_type=9, **base))
show("QueryFiles referencing AGOT, most subscribed", call("QueryFiles", query_type=9, child_publishedfileid=AGOT, **base))
show("QueryFiles referencing AGOT, trend 7d", call("QueryFiles", query_type=3, days=7, child_publishedfileid=AGOT, **base))
show("QueryFiles collections containing Armory", call("QueryFiles", query_type=9, child_publishedfileid=ARMORY, filetype=1, **base))
show("QueryFiles anything containing Armory", call("QueryFiles", query_type=9, child_publishedfileid=ARMORY, **base))
ids = call("QueryFiles", query_type=3, days=7, ids_only="true", **dict(base, numperpage=100))
print("\n=== ids_only page: total", ids.get("total"), "next_cursor" in ids, len(ids.get("publishedfiledetails", [])))
