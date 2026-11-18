"""Merge Rally originals (rendered MP4s) and verified official YouTube moments into manifest.json."""
import json, datetime, sys, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
orig = json.load(open(os.path.join(ROOT, "tools", "originals.json")))  # Rally-made clips in clips/
yts = json.load(open(os.path.join(ROOT, "tools", "yt_items.json")))
for y in yts:
    y["src"] = "yt:" + y["yt"]; y["poster"] = f"https://i.ytimg.com/vi/{y['yt']}/hqdefault.jpg"
    off, cues = 0, []
    for m in y["moments"]:
        L = (m["end"] if m.get("end") is not None else (y.get("verify", {}).get("duration") or 90)) - m["start"]; cues.append({"s": round(off + 0.3, 2), "e": round(off + L, 2), "t": m["cue"]}); off += L
    y["dur"] = round(off, 2); y["cues"] = cues; y["transcript"] = " ".join(f"{m['label']} ({m.get('minute','')}): {m['cue']}." for m in y["moments"])
label = sys.argv[1] if len(sys.argv) > 1 else "gh"
now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
HIDE = {"c-vini-12min", "c-england-madrid"}  # synthetic sports clips replaced by real footage
items = yts + [o for o in orig if o["id"] not in HIDE]
json.dump({"build": f"{label}-{len(items)}", "updatedAt": now, "clips": items}, open(os.path.join(ROOT, "manifest.json"), "w"), ensure_ascii=False)
print(label, len(items), "items:", sum(1 for i in items if i.get("type") == "yt"), "official YouTube,", sum(1 for i in items if i.get("type") != "yt"), "Rally originals")
