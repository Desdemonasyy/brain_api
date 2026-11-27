"""探查 analyst4 目标价/评级相关字段（用 search 参数，失败则分页本地过滤）。"""
import time

import brain

s = brain.load()
if not brain.authenticated(s):
    print("cookie 失效，请重新登录")
    raise SystemExit(1)

BASE = "https://api.worldquantbrain.com"
KEYS = ["target", "rating", "recomm", "price"]


def get(url):
    for a in range(4):
        try:
            r = s.get(url, headers={"Accept": "application/json;version=2.0"}, timeout=90)
        except Exception as e:  # noqa: BLE001
            print(f"  EXC {str(e)[:70]}", flush=True)
            time.sleep(20)
            continue
        if r.status_code == 200:
            return r.json()
        print(f"  status={r.status_code}", flush=True)
        time.sleep(20 * (a + 1))
    return None


# 方案1：search 参数
hit = False
for kw in KEYS:
    d = get(f"{BASE}/data-fields?dataset.id=analyst4&search={kw}&limit=50")
    if not d:
        continue
    res = d.get("results", [])
    print(f"\n=== search={kw}  count={d.get('count')} ===")
    for f in res[:30]:
        print(f'  {f.get("id"):<46} {f.get("type",""):<7} cov={f.get("coverage")} '
              f'users={f.get("alphaCount")}  {(f.get("description") or "")[:36]}')
    if res:
        hit = True
    time.sleep(6)

if not hit:
    print("\nsearch 无结果，改用分页本地过滤")
    for off in range(0, 1400, 50):
        d = get(f"{BASE}/data-fields?dataset.id=analyst4&limit=50&offset={off}")
        if not d:
            break
        batch = d.get("results", [])
        if not batch:
            break
        for f in batch:
            fid = (f.get("id") or "").lower()
            if any(k in fid for k in KEYS):
                print(f'  {f.get("id"):<46} {f.get("type",""):<7} cov={f.get("coverage")} '
                      f'users={f.get("alphaCount")}  {(f.get("description") or "")[:36]}')
        print(f"  offset={off} done", flush=True)
        time.sleep(4)
