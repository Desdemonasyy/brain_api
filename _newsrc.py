"""筛查此前未用过的两个数据集（model51 风险指标 / option9 期权分析）的单信号强度。"""
import csv
import time
from datetime import datetime

import brain

N = "n = group_rank(ts_mean(vec_avg(nws12_afterhsz_sl), 20), subindustry) - 0.5;"
V = "v = group_rank(ts_zscore(cashflow_op / cap, 250), subindustry) - 0.5;"

SIGNALS = [
    ("low_beta_90", "-group_rank(beta_last_90_days_spy, subindustry)"),
    ("low_beta_360", "-group_rank(beta_last_360_days_spy, subindustry)"),
    ("low_idio_vol_90", "-group_rank(unsystematic_risk_last_90_days, subindustry)"),
    ("low_corr_90", "-group_rank(correlation_last_90_days_spy, subindustry)"),
    ("fwd_price_90", "group_rank(forward_price_90 / close - 1, subindustry)"),
    ("call_breakeven_90", "group_rank((call_breakeven_90 - close) / close, subindustry)"),
    ("put_breakeven_90", "group_rank((put_breakeven_90 - close) / close, subindustry)"),
    ("pcr_oi_90_neg", "-group_rank(pcr_oi_90, subindustry)"),
    ("breakeven_spread_90",
     "group_rank((call_breakeven_90 - put_breakeven_90) / close, subindustry)"),
]


def main():
    s = brain.load()
    if not brain.authenticated(s):
        print("cookie 失效，请先运行: python login_playwright.py")
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"results/newsrc_{stamp}.csv"
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
            row = {"name": name, "alpha_id": aid, "sharpe": st.get("sharpe"),
                   "fitness": st.get("fitness"), "turnover": st.get("turnover"),
                   "returns": st.get("returns")}
            rows.append(row)
            print(f'[{i}/{len(SIGNALS)}] {name:22s} {aid}  S={row["sharpe"]}  '
                  f'F={row["fitness"]}  T={row["turnover"]}  R={row["returns"]}', flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{len(SIGNALS)}] {name:22s} FAILED: {e}", flush=True)
            rows.append({"name": name, "alpha_id": "", "sharpe": "", "fitness": "",
                         "turnover": "", "returns": ""})
        flush()
        time.sleep(2)

    ok = [r for r in rows if isinstance(r["sharpe"], (int, float))]
    ok.sort(key=lambda r: abs(r["sharpe"]), reverse=True)
    print("\n=== 按 |Sharpe| 排序 ===")
    for r in ok:
        print(f'{r["sharpe"]:6.2f}  {r["name"]:22s} {r["alpha_id"]}  F={r["fitness"]}  T={r["turnover"]}')
    print(f"\n结果已保存: {out}")


if __name__ == "__main__":
    main()
