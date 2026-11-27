"""列出 USA/D1/TOP3000 下可用的数据集（去重后）。"""
import time

import brain

s = brain.load()
if not brain.authenticated(s):
    print("cookie 失效，请重新登录")
    raise SystemExit(1)

BASE = "https://api.worldquantbrain.com"
url = (f"{BASE}/data-sets?instrumentType=EQUITY&region=USA&delay=1"
       f"&universe=TOP3000&limit=100")
seen = {}
pages = 0
while url and pages < 8:
    r = None
    for attempt in range(4):
        r = s.get(url, headers={"Accept": "application/json;version=2.0"}, timeout=90)
        if r.status_code == 200:
            break
        time.sleep(8 * (attempt + 1))
    if r is None or r.status_code != 200:
        print(f"status={r.status_code if r else 'none'}")
        break
    d = r.json()
    for x in d.get("results", []):
        did = x.get("id")
        if did and did not in seen:
            seen[did] = x
    url = d.get("next")
    pages += 1
    time.sleep(3)

print(f"去重后数据集数: {len(seen)}\n")
print(f"{'ID':<20} {'字段':<6} {'alpha':<8} 名称")
print("-" * 88)
for did in sorted(seen):
    x = seen[did]
    print(f'{did:<20} {str(x.get("fieldCount","")):<6} {str(x.get("alphaCount","")):<8} '
          f'{(x.get("name") or "")[:46]}')
