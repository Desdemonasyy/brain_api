"""第九阶段：TOP1000 上给 E1 加正交腿 + 迁移两条已有信号。

E1_1000 (gJanveKl)：S1.77 / F1.42 / T9.25% —— EBIT 收益率在大盘股上变强（TOP3000 只 1.48）。
目标：组合后 S >= 2.0 且 F >= 1.5，同时满足对 E1(1.48) 和 rK7xGmAE(1.60) 的豁免线。
"""
import csv
import time
from datetime import datetime

import brain

SUB = "SUBINDUSTRY"
U = "TOP1000"

LEGS = [
    # X1 E1 + IV/已实现波动（两个独立数据源）
    ("X1_e1_iv",
     "rank(ts_rank(anl4_ebit_value / cap, 126)) + rank(ts_backfill(implied_volatility_call_120 / parkinson_volatility_120, 20))",
     {"neutralization": SUB, "decay": 15, "universe": U}),
    # X2 E1 + L3（同源不同口径）
    ("X2_e1_l3",
     "rank(ts_rank(anl4_ebit_value / cap, 126)) + rank(ts_rank(anl4_afv4_eps_mean / close, 126))",
     {"neutralization": SUB, "decay": 10, "universe": U}),
    # X3 三腿：E1 + IV + ROE
    ("X3_three",
     "rank(ts_rank(anl4_ebit_value / cap, 126)) + rank(ts_backfill(implied_volatility_call_120 / parkinson_volatility_120, 20)) + 0.5 * rank(ts_rank(operating_income / equity, 126))",
     {"neutralization": SUB, "decay": 15, "universe": U}),
    # X4 CF/cap 原式（A5）迁到 TOP1000
    ("X4_cf_cap",
     "group_rank(ts_zscore(cashflow_op / cap, 250), subindustry)",
     {"neutralization": "MARKET", "decay": 12, "universe": U}),
    # X5 新闻情绪（A6 的 n 腿）迁到 TOP1000
    ("X5_news",
     "group_rank(ts_mean(vec_avg(nws12_afterhsz_sl), 20), subindustry)",
     {"neutralization": "MARKET", "decay": 12, "universe": U}),
]


def main():
    s = brain.load()
    if not brain.authenticated(s):
        print("cookie 失效，请重新登录")
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"results/legs9_{stamp}.csv"
    fields = ["name", "alpha_id", "sharpe", "fitness", "turnover", "returns", "fails"]
    rows = []

    def flush():
        with open(out, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)

    for i, (name, expr, over) in enumerate(LEGS, 1):
        try:
            sim_id, retry_after = brain.simulate(s, expr, **over)
            time.sleep(retry_after)
            d = brain.wait(s, sim_id)
            aid = d.get("alpha")
            a = s.get(f"https://api.worldquantbrain.com/alphas/{aid}",
                      headers={"Accept": "application/json;version=2.0"},
                      timeout=60).json()
            st = a.get("is") or {}
            bad = [c["name"] for c in st.get("checks", []) if c.get("result") == "FAIL"]
            row = {"name": name, "alpha_id": aid, "sharpe": st.get("sharpe"),
                   "fitness": st.get("fitness"), "turnover": st.get("turnover"),
                   "returns": st.get("returns"), "fails": "|".join(bad)}
            rows.append(row)
            print(f'[{i}/{len(LEGS)}] {name:10s} {aid}  S={row["sharpe"]}  '
                  f'F={row["fitness"]}  T={row["turnover"]}  R={row["returns"]}  '
                  f'FAIL={bad}', flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{len(LEGS)}] {name:10s} FAILED: {str(e)[:300]}", flush=True)
            rows.append({"name": name, "alpha_id": "", "sharpe": "", "fitness": "",
                         "turnover": "", "returns": "", "fails": "ERROR"})
        flush()
        time.sleep(2)

    print(f"\n结果已保存: {out}")


if __name__ == "__main__":
    main()
