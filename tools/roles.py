"""Build roles.json for the Roles tab from open, community-maintained internship lists.

Sources (public GitHub repos, the same data their READMEs publish):
  - SimplifyJobs/Summer2027-Internships  (direct employer links)
  - vanshb03/Summer2027-Internships       (short redirect links; used to group duplicates, never as the apply link)
Jobby (jobbys.vercel.app) is NOT a data source: its robots.txt disallows /api/ and on-demand AI access, so Rally only links to it.

Each role keeps: firstSeen (when Rally first saw it), listedAt (when the list added it; NOT the employer's post date),
lastSeen (last refresh that still listed it as active). The app checks Greenhouse/Lever/Ashby postings live for
employer post dates, open/closed status and the skills the posting names.
"""
import json, os, re, sys, time, urllib.request, datetime
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "roles.json")
SRC = [
    ("SimplifyJobs", "https://raw.githubusercontent.com/SimplifyJobs/Summer2027-Internships/dev/.github/scripts/listings.json", "https://github.com/SimplifyJobs/Summer2027-Internships"),
    ("vanshb03", "https://raw.githubusercontent.com/vanshb03/Summer2027-Internships/dev/.github/scripts/listings.json", "https://github.com/vanshb03/Summer2027-Internships"),
]
CATS = {"Software", "AI/ML/Data", "Software Engineering", "Data Science, AI & Machine Learning", None}
US = re.compile(r",\s*(A[LKZR]|C[AOT]|D[EC]|FL|GA|HI|I[ADLN]|K[SY]|LA|M[ADEINOST]|N[CDEHJMVY]|O[HKR]|PA|RI|S[CD]|T[NX]|UT|V[AT]|W[AIVY])\b|\bUSA\b|United States|Remote in US|^Remote$", re.I)
SWE = re.compile(r"software|backend|back-end|full[- ]?stack|platform|infrastructure|infra\b|machine learning|\bml\b|\bai\b|data (engineer|platform)|applied scientist|research engineer|swe|developer|systems|cloud|distributed|compiler|security engineer", re.I)
NO = re.compile(r"consult|people analytics|business systems|\bphd\b|ph\.d|doctoral|mba\b|hardware|electrical|mechanical|firmware|asic|fpga|analog|sales|marketing|recruit|product manag|designer|accounting|finance intern|actuar", re.I)
now = datetime.datetime.now(datetime.timezone.utc)
stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")

def fetch(url):
    with urllib.request.urlopen(url, timeout=60) as r: return json.load(r)
def norm(s): return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()
def canon(u):
    u = (u or "").split("?")[0].split("#")[0].rstrip("/"); u = re.sub(r"/apply$", "", u); return u
def provider(u):
    m = re.search(r"(?:job-boards|boards)(?:\.eu)?\.greenhouse\.io/(?:embed/job_app\?for=)?([^/?#]+)/jobs/(\d+)", u)
    if m: return "greenhouse", m.group(1), m.group(2)
    m = re.search(r"jobs(?:\.eu)?\.lever\.co/([^/]+)/([0-9a-f-]{36})", u)
    if m: return "lever", m.group(1), m.group(2)
    m = re.search(r"jobs\.ashbyhq\.com/([^/]+)/([0-9a-f-]{36})", u)
    if m: return "ashby", m.group(1), m.group(2)
    if "myworkdayjobs.com" in u: return "workday", None, None
    return "other", None, None

prev = {}
if os.path.exists(OUT):
    try: prev = {r["key"]: r for r in json.load(open(OUT)).get("roles", [])}
    except Exception: prev = {}
lists, errors = {}, []
for name, url, home in SRC:
    try: lists[name] = fetch(url)
    except Exception as e: errors.append(f"{name}: {e}")
if "SimplifyJobs" not in lists:
    # keep the last good inventory; just record the failure
    summary = {"at": stamp, "ok": False, "errors": errors, "kept": len(prev)}
    print(json.dumps(summary)); sys.exit(0)

roles, seen_keys, dup_groups = {}, set(), 0
by_ctl = {}
for x in lists["SimplifyJobs"]:
    if not (x.get("active") and x.get("is_visible", True)): continue
    terms = x.get("terms") or []
    if not any("Summer 2027" in t for t in terms): continue
    if x.get("category") not in CATS: continue
    t = x.get("title", ""); locs = x.get("locations") or []
    if not SWE.search(t) or NO.search(t): continue
    if x.get("degrees") and all(d in ("PhD", "Master's", "MBA") for d in x["degrees"]): continue
    if locs and not any(US.search(l) for l in locs): continue
    apply = canon(x["url"]); prov, board, jid = provider(x["url"])
    key = f"{prov}:{board}:{jid}" if jid else "u:" + apply.lower()
    ctl = (norm(x["company_name"]), norm(t))
    if key in roles:  # same requisition listed twice (e.g. several locations)
        r = roles[key]; r["locations"] = sorted(set(r["locations"]) | set(locs)); dup_groups += 1; continue
    roles[key] = {"key": key, "employer": x["company_name"], "title": t, "locations": locs, "terms": terms, "category": x.get("category"),
                  "degrees": x.get("degrees") or [], "sponsorship": x.get("sponsorship"), "applyUrl": x["url"], "provider": prov, "board": board, "jobId": jid,
                  "listedAt": datetime.datetime.fromtimestamp(x["date_posted"], datetime.timezone.utc).strftime("%Y-%m-%d") if x.get("date_posted") else None,
                  "firstSeen": prev.get(key, {}).get("firstSeen", stamp), "lastSeen": stamp, "status": "open",
                  "boards": [{"name": "SimplifyJobs", "url": SRC[0][2]}]}
    by_ctl.setdefault(ctl, []).append(key)
# group the second list's copies under the employer posting (match on company + title)
merged = 0
for x in lists.get("vanshb03", []):
    if not x.get("active"): continue
    for key in by_ctl.get((norm(x.get("company_name")), norm(x.get("title"))), []):
        b = roles[key]["boards"]
        if not any(z["name"] == "vanshb03" for z in b): b.append({"name": "vanshb03", "url": SRC[1][2]}); merged += 1
# roles that dropped off the list since last time: keep 14 days as closed so tracking survives
closed = 0
for key, r in prev.items():
    if key in roles: continue
    if r.get("status") == "open": r = dict(r, status="closed", closedAt=stamp, closedWhy="no longer listed as active by SimplifyJobs"); closed += 1
    if (now - datetime.datetime.fromisoformat(r.get("closedAt", stamp).replace("Z", "+00:00"))).days <= 14: roles[key] = r
out = sorted(roles.values(), key=lambda r: (r["status"] != "open", r.get("listedAt") or ""), reverse=False)
out = sorted(out, key=lambda r: (0 if r["status"] == "open" else 1, -(datetime.datetime.fromisoformat(r["listedAt"]).timestamp() if r.get("listedAt") else 0)))
new = [r["key"] for r in out if r["key"] not in prev]
summary = {"at": stamp, "ok": True, "errors": errors, "open": sum(r["status"] == "open" for r in out), "new": len(new),
           "groupedSameRequisition": dup_groups, "alsoOnSecondBoard": merged, "closed": closed,
           "byProvider": {p: sum(1 for r in out if r["provider"] == p) for p in ("greenhouse", "lever", "ashby", "workday", "other")}}
json.dump({"updatedAt": stamp, "sources": [{"name": n, "url": h} for n, _, h in SRC], "jobby": "https://jobbys.vercel.app/?level=intern", "summary": summary, "roles": out}, open(OUT, "w"), ensure_ascii=False)
print(json.dumps(summary))
