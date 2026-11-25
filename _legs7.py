"""第七阶段：model16 多因子复合评分导数（覆盖率 1.00，从未使用）。

这些字段本身已是「变化率」，与已提交的 11 条（水平/时序分位信号）在信号类型上正交。
fscore_* 系列覆盖率仅 0.29-0.38 且季度更新，会产生 LOW_TURNOVER，排除。
"""
import csv
import time
from datetime import datetime

import brain

SUB = "SUBINDUSTRY"

LEGS = [
    # S1 盈利确定性排名变化率
    ("S1_certainty",
     "rank(ts_rank(earnings_certainty_rank_derivative, 126))",
     {"neutralization": SUB, "decay": 10}),
    # S2 分析师修正动量（日频变体）
    ("S2_revision",
     "rank(ts_rank(analyst_revision_rank_derivative, 126))",
     {"neutralization": SUB, "decay": 10}),
    # S3 现金流效率排名变化率
    ("S3_cf_eff",
     "rank(ts_rank(cashflow_efficiency_rank_derivative, 126))",
     {"neutralization": SUB, "decay": 10}),
    # S4 相对估值排名变化率（估值改善）
    ("S4_valuation",
     "rank(ts_rank(relative_valuation_rank_derivative, 126))",
     {"neutralization": SUB, "decay": 10}),
    # S5 成长潜力排名变化率
    ("S5_growth",
     "rank(ts_rank(growth_potential_rank_derivative, 126))",
     {"neutralization": SUB, "decay": 10}),
    # S6 多因子加速度（直接水平，不套 ts_rank）
    ("S6_accel",
     "rank(multi_factor_acceleration_score_derivative)",
     {"neutralization": SUB, "decay": 10}),
]


def main():
    s = brain.load()
    if not brain.authenticated(s):
        print("cookie 失效，请重新登录")
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"results/legs7_{stamp}.csv"
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
            print(f'[{i}/{len(LEGS)}] {name:12s} {aid}  S={row["sharpe"]}  '
                  f'F={row["fitness"]}  T={row["turnover"]}  R={row["returns"]}  '
                  f'FAIL={bad}', flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{len(LEGS)}] {name:12s} FAILED: {str(e)[:200]}", flush=True)
            rows.append({"name": name, "alpha_id": "", "sharpe": "", "fitness": "",
                         "turnover": "", "returns": "", "fails": "ERROR"})
        flush()
        time.sleep(2)

    ok = [r for r in rows if isinstance(r["sharpe"], (int, float))]
    ok.sort(key=lambda r: r["sharpe"], reverse=True)
    print("\n=== 按 Sharpe 排序 ===")
    for r in ok:
        print(f'{r["sharpe"]:6.2f}  F={r["fitness"]:<5} T={r["turnover"]:<7} '
              f'{r["name"]:12s} {r["alpha_id"]}  {r["fails"]}')
    print(f"\n结果已保存: {out}")


if __name__ == "__main__":
    main()
