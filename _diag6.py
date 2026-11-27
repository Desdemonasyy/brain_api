"""列出账号可用的全部数据集，重点找未探查的类别。"""
import brain

s = brain.load()
if not brain.authenticated(s):
    print("cookie 失效，请重新登录")
    raise SystemExit(1)

BASE = "https://api.worldquantbrain.com"
sets = []
url = f"{BASE}/data-sets?limit=50"
pages = 0
while url and pages < 10:
    r = s.get(url, headers={"Accept": "application/json;version=2.0"}, timeout=90)
    if r.status_code != 200:
        print(f"status={r.status_code} {r.text[:200]}")
        break
    d = r.json()
    sets.extend(d.get("results", []))
    url = d.get("next")
    pages += 1

print(f"可用数据集总数: {len(sets)}\n")
sets.sort(key=lambda x: x.get("id", ""))
print(f"{'ID':<22} {'字段数':<7} {'alpha数':<9} 名称")
print("-" * 95)
for d in sets:
    print(f'{d.get("id", ""):<22} {str(d.get("fieldCount", "")):<7} '
          f'{str(d.get("alphaCount", "")):<9} {(d.get("name") or "")[:50]}')
