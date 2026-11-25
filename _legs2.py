"""第二阶段：分析师一致预期数据源的三个不同口径（验证 L3 的稳健性）。

对照基准 L3：rank(ts_rank(anl4_afv4_eps_mean / close, 126)) → S1.87/F1.57/T8.04%
"""
import csv
import time
from datetime import datetime

import brain

LEGS = [
    # E1 EBIT 收益率：企业价值口径，跨资本结构，与 EPS 口径不同
    ("E1_ebit_yield",
     "rank(ts_rank(ts_backfill(anl4_ebit_value, 20) / cap, 126))",
     {"neutralization": "SUBINDUSTRY", "decay": 10}),
    # E2 预期修正动量：水平 → 变化率，不同信号类型
    ("E2_eps_revision",
     "rank(ts_delta(ts_backfill(anl4_afv4_eps_mean, 20), 63) / close)",
     {"neutralization": "SUBINDUSTRY", "decay": 10}),
    # E3 FCF 预期覆盖广度：分析师跟踪密度
    ("E3_fcfps_number",
     "rank(ts_rank(ts_backfill(anl4_fcfps_number, 20), 126))",
     {"neutralization": "SUBINDUSTRY", "decay": 10}),
]


def main():
    s = brain.load()
    if not brain.authenticated(s):
        print("cookie 失效，请重新登录")
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"results/legs2_{stamp}.csv"
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
            print(f'[{i}/{len(LEGS)}] {name:16s} {aid}  S={row["sharpe"]}  '
                  f'F={row["fitness"]}  T={row["turnover"]}  R={row["returns"]}  '
                  f'FAIL={bad}', flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{len(LEGS)}] {name:16s} FAILED: {str(e)[:200]}", flush=True)
            rows.append({"name": name, "alpha_id": "", "sharpe": "", "fitness": "",
                         "turnover": "", "returns": "", "fails": "ERROR"})
        flush()
        time.sleep(2)

    print(f"\n结果已保存: {out}")


if __name__ == "__main__":
    main()
