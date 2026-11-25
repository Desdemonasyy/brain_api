"""第三批新信号筛查：按 docs/12 实测结论（基本面优先 / group_rank+ts_rank / 低换手 / SUBINDUSTRY）。

docs/12 核心约束：
- 目标 S>=1.5、F>=1.2、T 2-10%（Fitness 分母在 T<12.5% 时固定 0.125）
- 表达式内已 group_rank 时，Settings 用 MARKET 或 NONE，避免双重中性化
- 避免日频价差 / log(负数) / 除以 volume / 短窗口情绪（窗口 >=15）
"""
import csv
import time
from datetime import datetime

import brain

SIGNALS = [
    # docs/12 实测最高：S2.10 / F1.81 / T5.68%
    ("roe_lev_combo",
     "rank(ts_rank(operating_income / equity, 126)) + rank(-equity / assets)",
     {"neutralization": "SUBINDUSTRY", "decay": 10}),
    # 同族单腿（盈利能力 only），用于判断杠杆腿贡献
    ("roe_group_sector",
     "group_rank(ts_rank(operating_income / equity, 126), sector)",
     {"neutralization": "MARKET", "decay": 10}),
    # docs/12 实测：S1.47 / F1.77 / T~10%（情绪波动，与新闻情绪是不同数据集）
    ("buzz_std20",
     "-ts_std_dev(scl12_buzz, 20)",
     {"neutralization": "SUBINDUSTRY", "decay": 20}),
    # 权益增长维度（与水平类不同）
    ("equity_growth",
     "group_rank(ts_rank(ts_delta(equity, 63), 126), sector)",
     {"neutralization": "MARKET", "decay": 10}),
    # 期权：IV / Parkinson 波动（跨数据集，低相关候选）
    ("iv_parkinson",
     "rank(ts_backfill(implied_volatility_call_120 / parkinson_volatility_120, 20))",
     {"neutralization": "SUBINDUSTRY", "decay": 20}),
    # FCF / 权益（与 A5 的 cashflow_op/cap 口径不同）
    ("fcf_equity",
     "rank(ts_rank(free_cash_flow_reported_value / equity, 126))",
     {"neutralization": "SUBINDUSTRY", "decay": 10}),
    # 分析师：目标价与 FCF 预期的一致性（低一致性 = 分歧）
    ("ptp_fcf_corr",
     "-ts_corr(est_ptp, est_fcf, 252)",
     {"neutralization": "SUBINDUSTRY", "decay": 10}),
]


def main():
    s = brain.load()
    if not brain.authenticated(s):
        print("cookie 失效")
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"results/newsrc3_{stamp}.csv"
    fields = ["name", "alpha_id", "sharpe", "fitness", "turnover", "returns", "fails"]
    rows = []

    def flush():
        with open(out, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)

    for i, (name, expr, over) in enumerate(SIGNALS, 1):
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
            print(f'[{i}/{len(SIGNALS)}] {name:18s} {aid}  S={row["sharpe"]}  '
                  f'F={row["fitness"]}  T={row["turnover"]}  R={row["returns"]}  '
                  f'FAIL={bad}', flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{len(SIGNALS)}] {name:18s} FAILED: {str(e)[:200]}", flush=True)
            rows.append({"name": name, "alpha_id": "", "sharpe": "", "fitness": "",
                         "turnover": "", "returns": "", "fails": "ERROR"})
        flush()
        time.sleep(2)

    ok = [r for r in rows if isinstance(r["sharpe"], (int, float))]
    ok.sort(key=lambda r: abs(r["sharpe"]), reverse=True)
    print("\n=== 按 |Sharpe| 排序 ===")
    for r in ok:
        print(f'{r["sharpe"]:6.2f}  F={r["fitness"]:<5} T={r["turnover"]:<7} {r["name"]:18s} '
              f'{r["alpha_id"]}  {r["fails"]}')
    print(f"\n结果已保存: {out}")


if __name__ == "__main__":
    main()
