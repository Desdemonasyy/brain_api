"""列出当前账号可用数据集（只读），用于寻找新的原始信号源。"""
import brain

API = "https://api.worldquantbrain.com"
H = {"Accept": "application/json;version=2.0"}
BASE = {"instrumentType": "EQUITY", "region": "USA", "delay": 1, "universe": "TOP3000"}


def list_sets(s):
    out, offset = [], 0
    while True:
        params = {**BASE, "limit": 50, "offset": offset}
        r = s.get(f"{API}/data-sets", headers=H, params=params, timeout=60)
        if r.status_code != 200:
            print("HTTP", r.status_code, r.text[:300])
            break
        d = r.json()
        out += d.get("results", [])
        offset += 50
        if offset >= d.get("count", 0):
            break
    return out


def main():
    s = brain.load()
    if not brain.authenticated(s):
        print("cookie 失效，请先运行: python login_playwright.py")
        return
    sets = list_sets(s)
    print(f"共 {len(sets)} 个数据集\n")
    rows = sorted(sets, key=lambda x: -(x.get("alphaCount") or 0))
    print(f'{"id":34s} {"name":38s} {"cov":>6s} {"fields":>6s} {"alphas":>7s}')
    for x in rows:
        print(
            f'{x.get("id",""):34s} {str(x.get("name",""))[:36]:38s} '
            f'{x.get("coverage",0):6.2f} {x.get("fieldCount",0):6d} {x.get("alphaCount",0):7d}'
        )


if __name__ == "__main__":
    main()
