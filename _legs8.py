"""第八阶段：Universe 切换 —— 唯一未探索的维度。

理由：
1. Challenge 质量分随 Universe 缩小而提高（TOP1000/TOP500 系数更高）
2. 同一表达式在不同股票池的 PnL 相关性可能 <0.7，提供新的自相关豁免空间
3. 大盘股分析师覆盖更完整，前瞻类因子 Sharpe 可能更高

注意 sub-universe 门槛：sub_sharpe >= 0.75 * sqrt(sub_size/alpha_size) * alpha_sharpe
"""
import csv
import time
from datetime import datetime

import brain

SUB = "SUBINDUSTRY"

LEGS = [
    # L3 前瞻 E/P
    ("L3_1000",
     "rank(ts_rank(anl4_afv4_eps_mean / close, 126))",
     {"neutralization": SUB, "decay": 10, "universe": "TOP1000"}),
    # E1 EBIT 收益率
    ("E1_1000",
     "rank(ts_rank(ts_backfill(anl4_ebit_value, 20) / cap, 126))",
     {"neutralization": SUB, "decay": 10, "universe": "TOP1000"}),
    # ROE + 杠杆（已提交 LLKQmR7M 的原式）
    ("LLKQ_1000",
     "rank(ts_rank(operating_income / equity, 126)) + rank(-equity / assets)",
     {"neutralization": SUB, "decay": 10, "universe": "TOP1000"}),
    # 期权 IV / 已实现波动
    ("rK7_1000",
     "rank(ts_backfill(implied_volatility_call_120 / parkinson_volatility_120, 20))",
     {"neutralization": SUB, "decay": 20, "universe": "TOP1000"}),
    # L3 前瞻 E/P on TOP500
    ("L3_500",
     "rank(ts_rank(anl4_afv4_eps_mean / close, 126))",
     {"neutralization": SUB, "decay": 10, "universe": "TOP500"}),
]


def main():
    s = brain.load()
    if not brain.authenticated(s):
        print("cookie 失效，请重新登录")
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"results/legs8_{stamp}.csv"
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
