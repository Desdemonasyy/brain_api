"""探查 model16 / model51 / socialmedia8 全部字段，以及 analyst4 的目标价与评级族。"""
import time

import brain

s = brain.load()
if not brain.authenticated(s):
    print("cookie 失效，请重新登录")
    raise SystemExit(1)

BASE = "https://api.worldquantbrain.com"


def dump(ds, limit=40, keyword=None):
    print(f"\n{'=' * 70}\n[{ds}]" + (f"  关键词={keyword}" if keyword else ""))
    off = 0
    shown = 0
    total = None
    while off < 400 and shown < limit:
        url = f"{BASE}/data-fields?dataset.id={ds}&limit=50&offset={off}"
        r = None
        for a in range(3):
            r = s.get(url, headers={"Accept": "application/json;version=2.0"}, timeout=60)
            if r.status_code == 200:
                break
            time.sleep(6 * (a + 1))
        if r is None or r.status_code != 200:
            print(f"  status={r.status_code if r else 'none'}")
            return
        d = r.json()
        if total is None:
            total = d.get("count", 0)
            print(f"  字段总数: {total}")
        batch = d.get("results", [])
        if not batch:
            break
        for f in batch:
            fid = f.get("id", "")
            if keyword and keyword.lower() not in fid.lower():
                continue
            print(f'    {fid:<44} {f.get("type",""):<7} cov={f.get("coverage")} '
                  f'users={f.get("alphaCount")}  {(f.get("description") or "")[:38]}')
            shown += 1
            if shown >= limit:
                break
        off += 50
        time.sleep(1.5)


dump("model16", limit=30)
dump("model51", limit=20)
dump("socialmedia8", limit=10)
dump("analyst4", limit=30, keyword="target")
dump("analyst4", limit=25, keyword="rating")
