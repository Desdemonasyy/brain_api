"""第五阶段：O5（看跌持仓变化）与高收益腿的正交组合。

O5 单腿：S1.22 / F0.56 / T9.95% / R2.67% —— Sharpe 够但收益不足以撑起 Fitness。
L3 单腿：S1.87 / F1.57 / T8.04% / R8.83% —— 收益高。
两者数据源独立（option9 持仓结构 vs analyst4 分析师预期），预期组合 S~1.8 / R~10%。
"""
import csv
import time
from datetime import datetime

import brain

LEGS = [
    # C1 O5 + L3（90 日持仓 / 20 日变化 + 前瞻 E/P）
    ("C1_o5_l3",
     "rank(-ts_delta(ts_backfill(pcr_oi_90, 20), 20)) + rank(ts_rank(anl4_afv4_eps_mean / close, 126))",
     {"neutralization": "SUBINDUSTRY", "decay": 20}),
    # C2 长窗口版：180 日持仓 / 63 日变化 + 前瞻 E/P
    ("C2_o5long_l3",
     "rank(-ts_delta(ts_backfill(pcr_oi_180, 20), 63)) + rank(ts_rank(anl4_afv4_eps_mean / close, 126))",
     {"neutralization": "SUBINDUSTRY", "decay": 20}),
    # C3 O5 + E1（EBIT 收益率）
    ("C3_o5_e1",
     "rank(-ts_delta(ts_backfill(pcr_oi_90, 20), 20)) + rank(ts_rank(ts_backfill(anl4_ebit_value, 20) / cap, 126))",
     {"neutralization": "SUBINDUSTRY", "decay": 20}),
]


def main():
    s = brain.load()
    if not brain.authenticated(s):
        print("cookie 失效，请重新登录")
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"results/legs5_{stamp}.csv"
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

    print(f"\n结果已保存: {out}")


if __name__ == "__main__":
    main()
