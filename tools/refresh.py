"""Rally refresh: validate incoming candidates, publish the ready ones, and write a run summary.

Inputs  tools/incoming.json   {"clips": [...], "stories": [...]}  (written by the scheduled run or by hand)
State   tools/yt_items.json   live official clips;  stories.json  live written stories
Output  manifest.json, stories.json, tools/runs/<stamp>.json and tools/runs/latest.json
"""
import json, os, sys, datetime
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = lambda *a: os.path.join(ROOT, *a)
now = datetime.datetime.now(datetime.timezone.utc)
stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
_src = json.load(open(P("tools", "sources.json"))); src = _src["youtube"]; geo = _src.get("blocked_for_us_viewers", {})
inc = json.load(open(P("tools", "incoming.json"))) if os.path.exists(P("tools", "incoming.json")) else {"clips": [], "stories": []}
live = json.load(open(P("tools", "yt_items.json")))
stories = json.load(open(P("stories.json")))
dropped, added, s_added = [], [], []
live_ids = {c["id"] for c in live}; live_yt = {(c["yt"], tuple((m["start"], m["end"]) for m in c["moments"])) for c in live}
live_story_kind = {(c.get("story"), c["kind"]) for c in live if c.get("story")}
def drop(c, why): dropped.append({"id": c.get("id"), "headline": c.get("headline") or c.get("title"), "why": why})
for c in inc.get("clips", []):
    need = ["id", "yt", "publisher", "lang", "kind", "topic", "headline", "kicker", "published", "moments", "url"]
    miss = [k for k in need if not c.get(k)]
    if miss: drop(c, "missing " + ", ".join(miss)); continue
    if c["publisher"] in geo: drop(c, f"{c['publisher']}: {geo[c['publisher']]}"); continue
    if c["publisher"] not in src: drop(c, f"publisher '{c['publisher']}' isn't on the official list (likely a reupload)"); continue
    if c["kind"] not in src[c["publisher"]]["kind"]: drop(c, f"{c['publisher']} isn't a source for {c['kind']}"); continue
    v = c.get("verify", {})
    # "allowlisted": oEmbed couldn't be fetched in this run, but the channel is on the official list and the
    # channel name came from the search listing. The app skips any clip whose player reports an error.
    if not (v.get("embeddable") is True or v.get("embeddable") == "allowlisted"): drop(c, "embedding not confirmed (oEmbed) and no listing check"); continue
    if v.get("author") != c["publisher"]: drop(c, f"oEmbed author '{v.get('author')}' doesn't match publisher"); continue
    if c["kind"] == "sports" and not (c.get("sources") and all(m.get("minute") for m in c["moments"])): drop(c, "sports clip without a match report and match minutes"); continue
    bad = [m for m in c["moments"] if not (0 <= m["start"] < m["end"]) or (v.get("duration") and m["end"] > v["duration"] + 0.5)]
    if bad: drop(c, "moment times outside the video"); continue
    if not v.get("timestamps") in ("frames", "whole-video", "chapters"): drop(c, "start point not verified"); continue
    if c["id"] in live_ids or (c["yt"], tuple((m["start"], m["end"]) for m in c["moments"])) in live_yt: drop(c, "already live"); continue
    if c.get("story") and (c["story"], c["kind"]) in live_story_kind and not c.get("supersedes"): drop(c, "same story already has a clip"); continue
    c["type"] = "yt"; c.setdefault("follow", {"type": "match"} if c["kind"] == "sports" else None); c["addedAt"] = stamp
    if c.get("follow") is None: c.pop("follow")
    if c.get("supersedes"): live = [x for x in live if x["id"] != c["supersedes"]]
    live.insert(0, c); live_ids.add(c["id"]); added.append(c["id"])
# windows: news-type clips 3 days, sports 7 days, evergreen kept
def age_days(c): return (now - datetime.datetime.fromisoformat(c.get("addedAt", c["published"]).replace("Z", "+00:00"))).total_seconds() / 86400
before = len(live)
live = [c for c in live if c.get("evergreen") or age_days(c) <= (7 if c["kind"] == "sports" else 3) or c["id"] in added]
expired = before - len(live)
known = {s["id"] for s in stories["stories"]}
for s in inc.get("stories", []):
    miss = [k for k in ("id", "lang", "topic", "title", "summary", "happened", "why", "next", "source", "url", "published") if not s.get(k)]
    if miss: drop(s, "story missing " + ", ".join(miss)); continue
    if s["id"] in known: drop(s, "story already live"); continue
    stories["stories"].insert(0, s); known.add(s["id"]); s_added.append(s["id"])
stories["updatedAt"] = stamp
json.dump(live, open(P("tools", "yt_items.json"), "w"), ensure_ascii=False, indent=1)
json.dump(stories, open(P("stories.json"), "w"), ensure_ascii=False)
os.system(f"cd {ROOT} && python3 tools/build.py run-{now.strftime('%m%d-%H%M')} > /tmp/build.out")
man = json.load(open(P("manifest.json")))
pt = sum(1 for c in man["clips"] if c["lang"] == "pt")
summary = {"at": stamp, "found": len(inc.get("clips", [])) + len(inc.get("stories", [])), "clipsAdded": added, "storiesAdded": s_added, "dropped": dropped, "expired": expired,
           "inventory": len(man["clips"]), "inline": len(man["clips"]), "portuguese": pt, "build": man["build"]}
for name in (stamp.replace(":", "") + ".json", "latest.json"): json.dump(summary, open(P("tools", "runs", name), "w"), ensure_ascii=False, indent=1)
json.dump(summary, open(P("run.json"), "w"), ensure_ascii=False)
print(json.dumps(summary, ensure_ascii=False, indent=1))
