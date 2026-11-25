"""一次性拉取数据集字段并缓存，按多个关键词检索。

用法：python _probe.py fundamental6 net_income cashflow_op gross_profit ...
"""
import json
import re
import sys
import time
from pathlib import Path

import brain

API = "https://api.worldquantbrain.com"
H = {"Accept": "application/json;version=2.0"}
BASE = {"instrumentType": "EQUITY", "region": "USA", "delay": 1, "universe": "TOP3000"}
CACHE = Path(__file__).parent / ".state"


def fetch(s, ds):
    path = CACHE / f"fields_{ds}.json"
    if path.exists():
        return json.loads(path.read_text())
    out, offset = [], 0
    while True:
        params = {**BASE, "dataset.id": ds, "limit": 50, "offset": offset}
        r = s.get(f"{API}/data-fields", headers=H, params=params, timeout=60)
        if r.status_code == 429:
            time.sleep(8)
            continue
        if r.status_code != 200:
            print("HTTP", r.status_code, r.text[:200])
            break
        d = r.json()
        out += d.get("results", [])
        offset += 50
        if offset >= d.get("count", 0):
            break
        time.sleep(0.3)
    path.write_text(json.dumps(out))
    return out


def main():
    ds = sys.argv[1]
    pats = sys.argv[2:]
    s = brain.load()
    fs = fetch(s, ds)
    print(f"{ds}: {len(fs)} fields (cached: .state/fields_{ds}.json)")
    if not pats:
        fs.sort(key=lambda x: -(x.get("alphaCount") or 0))
        for f in fs[:45]:
            print(f'  {f["id"]:46s} cov={f.get("coverage", 0):.2f} '
                  f'alphas={f.get("alphaCount", 0):6d} {f.get("type", "")}  '
                  f'{str(f.get("description", ""))[:44]}')
        return
    for p in pats:
        hits = [f for f in fs if re.search(p, f.get("id", ""), re.I)]
        hits.sort(key=lambda x: -(x.get("alphaCount") or 0))
        print(f"\n-- {p}: {len(hits)} hits")
        for f in hits[:8]:
            print(f'  {f["id"]:46s} cov={f.get("coverage", 0):.2f} '
                  f'alphas={f.get("alphaCount", 0):6d} {f.get("type", "")}')


if __name__ == "__main__":
    main()
