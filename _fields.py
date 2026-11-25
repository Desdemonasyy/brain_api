"""列出指定数据集的字段（只读）。"""
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
            time.sleep(10)
            continue
        if r.status_code != 200:
            print("HTTP", r.status_code, r.text[:200])
            break
        d = r.json()
        out += d.get("results", [])
        offset += 50
        if offset >= d.get("count", 0):
            break
        time.sleep(1)
    return out


def main():
    ids = sys.argv[1:] or ["model16"]
    s = brain.load()
    if not brain.authenticated(s):
        print("cookie 失效，请先运行: python login_playwright.py")
        return
    for ds in ids:
        fs = fields(s, ds)
        fs.sort(key=lambda x: -(x.get("alphaCount") or 0))
        print(f"\n=== {ds}  ({len(fs)} fields) ===")
        for f in fs:
            desc = str(f.get("description", ""))[:60]
            print(
                f'{f.get("id",""):46s} {f.get("type",""):6s} '
                f'cov={f.get("coverage",0):.2f} alphas={f.get("alphaCount",0):6d}  {desc}'
            )


if __name__ == "__main__":
    main()
