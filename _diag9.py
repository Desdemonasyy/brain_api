"""用 offset 分页拉全部数据集，去重后输出。"""
import time

import brain

s = brain.load()
if not brain.authenticated(s):
    print("cookie 失效，请重新登录")
    raise SystemExit(1)

BASE = "https://api.worldquantbrain.com"
seen = {}
for off in range(0, 600, 50):
    r = s.get(f"{BASE}/data-sets?limit=50&offset={off}",
              headers={"Accept": "application/json;version=2.0"}, timeout=90)
    if r.status_code != 200:
        print(f"offset={off} status={r.status_code}")
        break
    batch = r.json().get("results", [])
    if not batch:
        break
    for x in batch:
        did = x.get("id")
        if did and did not in seen:
            seen[did] = x
    print(f"offset={off} +{len(batch)} 累计唯一={len(seen)}", flush=True)
    time.sleep(2)

print(f"\n唯一数据集共 {len(seen)} 个\n")
print(f"{'ID':<20} {'字段':<6} {'alpha':<9} 名称")
print("-" * 90)
for did in sorted(seen):
    x = seen[did]
    print(f'{did:<20} {str(x.get("fieldCount","")):<6} {str(x.get("alphaCount","")):<9} '
          f'{(x.get("name") or "")[:48]}')
