"""第二批新信号筛查：分析师评级 / 管理层指引 / 期权隐含波动率。"""
import csv
import time
from datetime import datetime

import brain

SIGNALS = [
    ("rating_neg", "-group_rank(anl4_eaz2lrec_ratingvalue, subindustry)"),
    ("rating_pos", "group_rank(anl4_eaz2lrec_ratingvalue, subindustry)"),
    ("rating_chg60", "group_rank(ts_delta(anl4_eaz2lrec_ratingvalue, 60), subindustry)"),
    ("cf_guid_level",
     "group_rank((max_operating_cashflow_guidance + min_operating_cashflow_guidance) "
     "/ 2 / assets, subindustry)"),
    ("cf_guid_chg90",
     "group_rank(ts_delta(max_operating_cashflow_guidance + min_operating_cashflow_guidance, 90) "
     "/ 2 / assets, subindustry)"),
    ("iv_low_10", "-group_rank(implied_volatility_mean_10, subindustry)"),
    ("iv_term_90_30",
     "group_rank(implied_volatility_call_90 - implied_volatility_call_30, subindustry)"),
    ("iv_put_minus_call_90",
     "group_rank(implied_volatility_put_90 - implied_volatility_call_90, subindustry)"),
]


def main():
    s = brain.load()
    if not brain.authenticated(s):
        print("cookie 失效")
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"results/newsrc2_{stamp}.csv"
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
