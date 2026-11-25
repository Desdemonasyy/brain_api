"""查已提交 alpha 的日期分布，验证"每天只计一条"假设。"""
import brain

s = brain.load()
if not brain.authenticated(s):
    print("cookie 失效")
    raise SystemExit(1)

BASE = "https://api.worldquantbrain.com"
subs = []
url = f"{BASE}/users/self/alphas?limit=50&status=SUBMITTED"
pages = 0
while url and pages < 6:
    r = s.get(url, headers={"Accept": "application/json;version=2.0"}, timeout=60)
    if r.status_code != 200:
        print(f"status={r.status_code} {r.text[:200]}")
        break
    d = r.json()
    for a in d.get("results", []):
        st = a.get("is") or {}
        subs.append({
            "id": a.get("id"),
            "date": (a.get("dateSubmitted") or "")[:10],
            "sharpe": st.get("sharpe"),
            "fitness": st.get("fitness"),
            "turnover": st.get("turnover"),
            "universe": (a.get("settings") or {}).get("universe"),
            "neutral": (a.get("settings") or {}).get("neutralization"),
            "grade": a.get("grade"),
        })
    url = d.get("next")
    pages += 1

print(f"\n已提交 alpha 总数: {len(subs)}\n")
subs.sort(key=lambda x: x["date"])
by_day = {}
for a in subs:
    by_day.setdefault(a["date"], []).append(a)

print(f"{'日期':<12} {'条数':<5} alpha (Sharpe / Fitness / Turnover / Universe)")
print("-" * 92)
for day in sorted(by_day):
    items = by_day[day]
    for i, a in enumerate(items):
        tag = day if i == 0 else ""
        print(f"{tag:<12} {len(items) if i == 0 else '':<5} {a['id']:<11} "
              f"S={a['sharpe']:<5} F={a['fitness']:<5} T={a['turnover']:<7} "
              f"{a['universe']}/{a['neutral']} {a['grade']}")
print(f"\n有提交的天数: {len(by_day)}    总条数: {len(subs)}")
print(f"平均每天: {len(subs) / max(len(by_day), 1):.1f} 条")
