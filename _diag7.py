"""探测高正交性数据集是否对账号开放，并采样字段。"""
import time

import brain

s = brain.load()
if not brain.authenticated(s):
    print("cookie 失效，请重新登录")
    raise SystemExit(1)

BASE = "https://api.worldquantbrain.com"
CANDIDATES = [
    "institutions", "insider", "shortinterest", "earnings",
    "sentiment", "macro", "esg", "analyst45",
]

for ds in CANDIDATES:
    print(f"\n{'=' * 62}\n[{ds}]")
    try:
        r = s.get(f"{BASE}/data-fields?dataset.id={ds}&limit=12",
                  headers={"Accept": "application/json;version=2.0"}, timeout=60)
        if r.status_code != 200:
            print(f"  status={r.status_code}")
            continue
        d = r.json()
        cnt = d.get("count", 0)
        print(f"  字段总数: {cnt}")
        if not cnt:
            continue
        for f in d.get("results", [])[:12]:
            print(f'    {f.get("id"):<42} {f.get("type",""):<7} '
                  f'cov={f.get("coverage")} users={f.get("alphaCount")}  '
                  f'{(f.get("description") or "")[:40]}')
    except Exception as e:  # noqa: BLE001
        print(f"  ERROR: {str(e)[:100]}")
    time.sleep(2)
