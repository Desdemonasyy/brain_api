"""诊断 Challenge 积分未增加的原因。

检查项：
1. 用户基本信息与累计积分
2. 当前开放的竞赛及其要求（universe / delay / region）
3. 最近的活动记录
"""
import json

import brain

s = brain.load()
if not brain.authenticated(s):
    print("cookie 失效，请先 python login_playwright.py")
    raise SystemExit(1)


def show(title, url, limit=2500):
    print(f"\n{'=' * 20} {title} {'=' * 20}")
    try:
        r = s.get(url, headers={"Accept": "application/json;version=2.0"}, timeout=60)
        print(f"status={r.status_code}")
        txt = r.text
        try:
            print(json.dumps(r.json(), ensure_ascii=False, indent=2)[:limit])
        except Exception:  # noqa: BLE001
            print(txt[:limit])
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {e}")


show("users/self", "https://api.worldquantbrain.com/users/self")
show("competitions OPEN", "https://api.worldquantbrain.com/competitions?status=OPEN&limit=20", 4000)
show("activities", "https://api.worldquantbrain.com/users/self/activities?limit=10", 2500)
