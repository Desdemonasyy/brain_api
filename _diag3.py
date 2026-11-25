"""查用户提交记录与 alpha 清单。"""
import json

import brain

s = brain.load()
if not brain.authenticated(s):
    print("cookie 失效")
    raise SystemExit(1)

BASE = "https://api.worldquantbrain.com"


def show(title, url, limit=9000):
    print(f"\n{'=' * 16} {title} {'=' * 16}")
    try:
        r = s.get(url, headers={"Accept": "application/json;version=2.0"}, timeout=60)
        print(f"status={r.status_code}")
        try:
            print(json.dumps(r.json(), ensure_ascii=False, indent=2)[:limit])
        except Exception:  # noqa: BLE001
            print(r.text[:limit])
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {e}")


show("self alphas", f"{BASE}/users/self/alphas?limit=50", 12000)
show("submissions activity", f"{BASE}/users/self/activities/submissions", 4000)
