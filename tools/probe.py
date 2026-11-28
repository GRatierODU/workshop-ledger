"""One-off: compare collection counts for the Grand Armory under different QueryFiles filters."""
import json, os, urllib.parse, urllib.request
KEY = os.environ["STEAM_API_KEY"].strip()
def total(**q):
    q.update(key=KEY, appid=1158310, filetype=1, child_publishedfileid="3841377701", totalonly="true", query_type=1, cursor="*", numperpage=1)
    url = "https://api.steampowered.com/IPublishedFileService/QueryFiles/v1/?" + urllib.parse.urlencode(q, doseq=True)
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.loads(r.read())["response"].get("total")
    except Exception as e:
        return "ERR " + str(getattr(e, "code", e))
print("base", total())
for lang in (-1, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29):
    print("language", lang, total(language=lang))
print("descriptors none", total(**{"excluded_content_descriptors[0]": 0}))
print("query_type 0", total(query_type=0))
print("query_type 12 text", total(query_type=12))
print("match_all_tags false", total(match_all_tags="false"))
