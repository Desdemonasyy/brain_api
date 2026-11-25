"""查 Challenge 计分明细：哪些 alpha 计了分，去重规则是什么。"""
import json

import brain

s = brain.load()
if not brain.authenticated(s):
    print("cookie 失效")
    raise SystemExit(1)

BASE = "https://api.worldquantbrain.com"


def show(title, url, limit=6000):
    print(f"\n{'=' * 18} {title} {'=' * 18}")
    try:
        r = s.get(url, headers={"Accept": "application/json;version=2.0"}, timeout=60)
        print(f"status={r.status_code}")
        try:
            print(json.dumps(r.json(), ensure_ascii=False, indent=2)[:limit])
        except Exception:  # noqa: BLE001
            print(r.text[:limit])
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {e}")


# 1. Challenge 竞赛详情（可能含 alpha 计分明细）
show("competition challenge", f"{BASE}/competitions/challenge", 3000)
# 2. 用户在该竞赛下的状态
show("user in challenge", f"{BASE}/users/self/competitions/challenge", 3000)
# 3. 最近提交的 alpha 列表，看是否带 challenge 计分字段
show("recent alphas", f"{BASE}/alphas?limit=25&order=-dateSubmitted", 8000)
