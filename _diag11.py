"""单数据集探查，长间隔重试，打印真实状态码。"""
import time

import brain

s = brain.load()
if not brain.authenticated(s):
    print("cookie 失效，请重新登录")
    raise SystemExit(1)

BASE = "https://api.worldquantbrain.com"

for ds in ["model16", "model51", "socialmedia8"]:
    print(f"\n{'=' * 66}\n[{ds}]", flush=True)
    ok = False
    for a in range(5):
        try:
            r = s.get(f"{BASE}/data-fields?dataset.id={ds}&limit=50",
                      headers={"Accept": "application/json;version=2.0"}, timeout=90)
        except Exception as e:  # noqa: BLE001
            print(f"  try{a} EXC {str(e)[:80]}", flush=True)
            time.sleep(15)
            continue
        print(f"  try{a} status={r.status_code}", flush=True)
        if r.status_code == 200:
            d = r.json()
            print(f'  字段总数 {d.get("count")}', flush=True)
            for f in d.get("results", []):
                print(f'    {f.get("id"):<40} {f.get("type",""):<7} '
                      f'cov={f.get("coverage")} users={f.get("alphaCount")}  '
                      f'{(f.get("description") or "")[:40]}', flush=True)
            ok = True
            break
        time.sleep(20 * (a + 1))
    if not ok:
        print("  放弃该数据集", flush=True)
    time.sleep(8)
