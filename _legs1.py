"""第一阶段：8 条候选「腿」的单腿强度筛选（为下一轮双腿配对做前置）。

判定标准：单腿 Sharpe >= 0.8 才可作为主导腿，0.5-0.8 只能当配角腿。
全部 SUBINDUSTRY 中性化（表达式内无 group_rank，不构成双重中性化）。
"""
import csv
import time
from datetime import datetime

import brain

LEGS = [
    # L1 期权期限结构：短期 IV / 长期 IV（事件风险溢价）
    ("L1_iv_term",
     "rank(ts_rank(implied_volatility_mean_30 / implied_volatility_mean_360, 126))",
     {"neutralization": "SUBINDUSTRY", "decay": 10}),
    # L2 隐含偏斜陡度（尾部风险定价）
    ("L2_skew90",
     "rank(ts_backfill(implied_volatility_mean_skew_90, 20))",
     {"neutralization": "SUBINDUSTRY", "decay": 4}),
    # L3 前瞻 E/P（分析师一致预期）
    ("L3_fwd_ep",
     "rank(ts_rank(anl4_afv4_eps_mean / close, 126))",
     {"neutralization": "SUBINDUSTRY", "decay": 10}),
    # L4 分析师分歧度（反向）
    ("L4_dispersion",
     "rank(-ts_rank(ts_backfill(anl4_dts_rspe, 20) / close, 126))",
     {"neutralization": "SUBINDUSTRY", "decay": 10}),
    # L5 现金充足度（水平）
    ("L5_cash_assets",
     "rank(cash / assets)",
     {"neutralization": "SUBINDUSTRY", "decay": 4}),
    # L6 短期负债压力（反向，水平）
    ("L6_curr_liab",
     "rank(-liabilities_curr / assets)",
     {"neutralization": "SUBINDUSTRY", "decay": 4}),
    # L7 净利率（水平，ROE 分解项之一）
    ("L7_net_margin",
     "rank(operating_income / sales)",
     {"neutralization": "SUBINDUSTRY", "decay": 4}),
    # L8 股息回报时序分位（已知 S0.61，作为参照）
    ("L8_div",
     "rank(ts_rank(cashflow_dividends / cap, 252))",
     {"neutralization": "SUBINDUSTRY", "decay": 10}),
]


def main():
    s = brain.load()
    if not brain.authenticated(s):
        print("cookie 失效")
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"results/legs1_{stamp}.csv"
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
            print(f'[{i}/{len(LEGS)}] {name:14s} {aid}  S={row["sharpe"]}  '
                  f'F={row["fitness"]}  T={row["turnover"]}  R={row["returns"]}  '
                  f'FAIL={bad}', flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{len(LEGS)}] {name:14s} FAILED: {str(e)[:200]}", flush=True)
            rows.append({"name": name, "alpha_id": "", "sharpe": "", "fitness": "",
                         "turnover": "", "returns": "", "fails": "ERROR"})
        flush()
        time.sleep(2)

    ok = [r for r in rows if isinstance(r["sharpe"], (int, float))]
    ok.sort(key=lambda r: abs(r["sharpe"]), reverse=True)
    print("\n=== 按 |Sharpe| 排序（>=0.8 可作主导腿）===")
    for r in ok:
        print(f'{r["sharpe"]:6.2f}  F={r["fitness"]:<5} T={r["turnover"]:<7} {r["name"]:14s} '
              f'{r["alpha_id"]}  {r["fails"]}')
    print(f"\n结果已保存: {out}")


if __name__ == "__main__":
    main()
