"""遍历全部 alpha，找出真正有 dateSubmitted 的（即真正提交成功的）。"""
import brain

s = brain.load()
if not brain.authenticated(s):
    print("cookie 失效")
    raise SystemExit(1)

BASE = "https://api.worldquantbrain.com"
subs = []
all_count = 0
statuses = {}
url = f"{BASE}/users/self/alphas?limit=50"
pages = 0
while url and pages < 12:
    r = s.get(url, headers={"Accept": "application/json;version=2.0"}, timeout=90)
    if r.status_code != 200:
        print(f"status={r.status_code} {r.text[:200]}")
        break
    d = r.json()
    for a in d.get("results", []):
        all_count += 1
        statuses[a.get("status")] = statuses.get(a.get("status"), 0) + 1
        if a.get("dateSubmitted"):
            st = a.get("is") or {}
            subs.append({
                "id": a.get("id"),
                "date": a["dateSubmitted"][:10],
                "sharpe": st.get("sharpe"),
                "fitness": st.get("fitness"),
                "turnover": st.get("turnover"),
                "universe": (a.get("settings") or {}).get("universe"),
                "neutral": (a.get("settings") or {}).get("neutralization"),
                "grade": a.get("grade"),
                "comps": a.get("competitions"),
            })
    url = d.get("next")
    pages += 1

print(f"\n扫描 alpha 总数: {all_count}")
print(f"status 分布: {statuses}")
print(f"有 dateSubmitted 的: {len(subs)}\n")

subs.sort(key=lambda x: x["date"])
by_day = {}
for a in subs:
    by_day.setdefault(a["date"], []).append(a)

print(f"{'日期':<12} {'alpha':<11} {'S':<5} {'F':<5} {'T':<7} {'Universe/Neutral':<22} grade")
print("-" * 90)
for day in sorted(by_day):
    for a in by_day[day]:
        print(f"{day:<12} {a['id']:<11} {str(a['sharpe']):<5} {str(a['fitness']):<5} "
              f"{str(a['turnover']):<7} {a['universe']}/{a['neutral']:<14} {a['grade']}")
    if len(by_day[day]) > 1:
        print(f"{'':12} ^^ 当天共 {len(by_day[day])} 条")

print(f"\n有提交的天数: {len(by_day)}    提交总条数: {len(subs)}")
