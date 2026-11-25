"""IV 偏斜修正版：回填+全局排序+行业中性，及与现金流组合。"""
import csv
import time
from datetime import datetime

import brain

SIGNALS = [
    ("fixed_90",
     "d = implied_volatility_call_90 - implied_volatility_put_90;\n"
     "group_neutralize(rank(ts_backfill(d, 20)), subindustry)"),
    ("fixed_120",
     "d = implied_volatility_call_120 - implied_volatility_put_120;\n"
     "group_neutralize(rank(ts_backfill(d, 20)), subindustry)"),
    ("combo_90_value",
     "d = implied_volatility_call_90 - implied_volatility_put_90;\n"
     "s = group_neutralize(rank(ts_backfill(d, 20)), subindustry) - 0.5;\n"
     "v = group_rank(ts_zscore(cashflow_op / cap, 250), subindustry) - 0.5;\n"
     "s + 1.0 * v"),
]


def main():
    s = brain.load()
    if not brain.authenticated(s):
        print("cookie 失效")
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"results/ivfix_{stamp}.csv"
    fields = ["name", "alpha_id", "sharpe", "fitness", "turnover", "returns"]
    rows = []

    def flush():
        with open(out, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)

    for i, (name, expr) in enumerate(SIGNALS, 1):
        try:
            sim_id, retry_after = brain.simulate(s, expr)
            time.sleep(retry_after)
            d = brain.wait(s, sim_id)
            aid = d.get("alpha")
            a = s.get(f"https://api.worldquantbrain.com/alphas/{aid}",
                      headers={"Accept": "application/json;version=2.0"},
                      timeout=60).json()
            st = a.get("is") or {}
            checks = [(c["name"], c["result"]) for c in st.get("checks", [])]
            row = {"name": name, "alpha_id": aid, "sharpe": st.get("sharpe"),
                   "fitness": st.get("fitness"), "turnover": st.get("turnover"),
                   "returns": st.get("returns")}
            rows.append(row)
            bad = [c for c in checks if c[1] == "FAIL"]
            print(f'[{i}/{len(SIGNALS)}] {name:16s} {aid}  S={row["sharpe"]}  '
                  f'F={row["fitness"]}  T={row["turnover"]}  R={row["returns"]}  '
                  f'FAIL={bad}', flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{len(SIGNALS)}] {name:16s} FAILED: {e}", flush=True)
            rows.append({"name": name, "alpha_id": "", "sharpe": "", "fitness": "",
                         "turnover": "", "returns": ""})
        flush()
        time.sleep(2)

    print(f"\n结果已保存: {out}")


if __name__ == "__main__":
    main()
