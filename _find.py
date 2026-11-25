"""按关键词检索数据集字段（只读，输出精简）。"""
import re
import sys
import time

import brain

API = "https://api.worldquantbrain.com"
H = {"Accept": "application/json;version=2.0"}
BASE = {"instrumentType": "EQUITY", "region": "USA", "delay": 1, "universe": "TOP3000"}


def fields(s, ds):
    out, offset = [], 0
    while True:
        params = {**BASE, "dataset.id": ds, "limit": 50, "offset": offset}
        r = s.get(f"{API}/data-fields", headers=H, params=params, timeout=60)
        if r.status_code == 429:
            time.sleep(8)
            continue
        if r.status_code != 200:
            print("HTTP", r.status_code, r.text[:150])
            break
        d = r.json()
        out += d.get("results", [])
        offset += 50
        if offset >= d.get("count", 0):
            break
        time.sleep(0.4)
    return out


def main():
    ds, pat = sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "."
    s = brain.load()
    if not brain.authenticated(s):
        print("cookie 失效")
        return
    fs = fields(s, ds)
    hit = [f for f in fs if re.search(pat, f.get("id", ""), re.I)]
    hit.sort(key=lambda x: -(x.get("alphaCount") or 0))
    print(f"{ds}: {len(fs)} fields, matched {len(hit)}")
    for f in hit[:18]:
        print(f'  {f.get("id",""):46s} cov={f.get("coverage",0):.2f} '
              f'alphas={f.get("alphaCount",0):6d}  {str(f.get("description",""))[:52]}')


if __name__ == "__main__":
    main()
