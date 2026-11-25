"""批量测试四个三腿变体（去相关构造）。"""
import csv
import time
from datetime import datetime

import requests

import brain

API = "https://api.worldquantbrain.com"
H = {"Accept": "application/json;version=2.0"}

N = "n = group_rank(ts_mean(vec_avg(nws12_afterhsz_sl), 20), subindustry) - 0.5;"
V = "v = group_rank(ts_zscore(cashflow_op / cap, 250), subindustry) - 0.5;"

VARIANTS = [
    ("A_cf_assets",
     "rev = -group_zscore((close - open) / open / ts_std_dev(returns, 20), subindustry);\n"
     + N + "\n"
     + "w = group_rank(ts_zscore(cashflow_op / assets, 250), subindustry) - 0.5;\n"
     + "rev + 2.0 * n + 1.5 * w"),
    ("B_vol60",
     "rev = -group_zscore((close - open) / open / ts_std_dev(returns, 60), subindustry);\n"
     + N + "\n" + V + "\n"
     + "rev + 2.0 * n + 1.5 * v"),
    ("C_sizebucket",
     "rev = -group_zscore((close - open) / open / ts_std_dev(returns, 20), "
     'bucket(rank(cap), range="0,1,0.1"));\n'
     + N + "\n" + V + "\n"
     + "rev + 2.0 * n + 1.5 * v"),
    ("D_smooth2",
     "rev = -group_zscore(ts_mean((close - open) / open, 2) / ts_std_dev(returns, 20), subindustry);\n"
     + N + "\n" + V + "\n"
     + "rev + 2.0 * n + 1.5 * v"),
]


def main():
    s = brain.load()
    if not brain.authenticated(s):
        print("cookie 失效，请先运行: python login_playwright.py")
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"results/variants_{stamp}.csv"
    fields = ["name", "alpha_id", "sharpe", "fitness", "turnover", "returns", "sub_univ"]
    rows = []

    def flush():
        with open(out, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)

    for i, (name, expr) in enumerate(VARIANTS, 1):
        try:
            sim_id, retry_after = brain.simulate(s, expr)
            time.sleep(retry_after)
            d = brain.wait(s, sim_id)
            aid = d.get("alpha")
            a = s.get(f"{API}/alphas/{aid}", headers=H, timeout=60).json()
            st = a.get("is") or {}
            checks = {c["name"]: c for c in st.get("checks", [])}
            sub = checks.get("LOW_SUB_UNIVERSE_SHARPE", {})
            row = {
                "name": name,
                "alpha_id": aid,
                "sharpe": st.get("sharpe"),
                "fitness": st.get("fitness"),
                "turnover": st.get("turnover"),
                "returns": st.get("returns"),
                "sub_univ": sub.get("value"),
            }
            rows.append(row)
            print(
                f'[{i}/{len(VARIANTS)}] {name:14s} {aid}  S={row["sharpe"]}  '
                f'F={row["fitness"]}  T={row["turnover"]}  sub={row["sub_univ"]}',
                flush=True,
            )
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{len(VARIANTS)}] {name:14s} FAILED: {e}", flush=True)
            rows.append({"name": name, "alpha_id": "", "sharpe": "", "fitness": "",
                         "turnover": "", "returns": "", "sub_univ": ""})
        flush()
        time.sleep(2)

    ok = [r for r in rows if isinstance(r["sharpe"], (int, float))]
    ok.sort(key=lambda r: r["sharpe"], reverse=True)
    print("\n=== 按 Sharpe 排序 ===")
    for r in ok:
        print(f'{r["sharpe"]:6.2f}  {r["name"]:14s} {r["alpha_id"]}  F={r["fitness"]}  T={r["turnover"]}')
    print(f"\n结果已保存: {out}")


if __name__ == "__main__":
    main()
