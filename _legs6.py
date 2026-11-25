"""第六阶段：C1（O5+L3）微调 —— 目标 Sharpe >= 2.057（L3 的 1.1 倍豁免线）。

C1 = wpo0xVGY：S2.03 / F1.62 / T8.48% / R7.99%，但与已提交 L3(VkNAvwJJ S1.87) corr 0.8832。
只差 0.027 就能触发「Sharpe 提升 10%」豁免。
"""
import csv
import time
from datetime import datetime

import brain

SUB = "SUBINDUSTRY"

LEGS = [
    # W15 提高 O5 权重 1.5 倍
    ("W15",
     "1.5 * rank(-ts_delta(ts_backfill(pcr_oi_90, 20), 20)) + rank(ts_rank(anl4_afv4_eps_mean / close, 126))",
     {"neutralization": SUB, "decay": 20}),
    # W20 提高 O5 权重 2 倍
    ("W20",
     "2.0 * rank(-ts_delta(ts_backfill(pcr_oi_90, 20), 20)) + rank(ts_rank(anl4_afv4_eps_mean / close, 126))",
     {"neutralization": SUB, "decay": 20}),
    # O60 更短持仓周期
    ("O60",
     "rank(-ts_delta(ts_backfill(pcr_oi_60, 20), 20)) + rank(ts_rank(anl4_afv4_eps_mean / close, 126))",
     {"neutralization": SUB, "decay": 20}),
    # O120 更长持仓周期
    ("O120",
     "rank(-ts_delta(ts_backfill(pcr_oi_120, 20), 20)) + rank(ts_rank(anl4_afv4_eps_mean / close, 126))",
     {"neutralization": SUB, "decay": 20}),
    # T3 加股息第三腿
    ("T3",
     "rank(-ts_delta(ts_backfill(pcr_oi_90, 20), 20)) + rank(ts_rank(anl4_afv4_eps_mean / close, 126)) + 0.5 * rank(ts_rank(cashflow_dividends / cap, 252))",
     {"neutralization": SUB, "decay": 20}),
]


def main():
    s = brain.load()
    if not brain.authenticated(s):
        print("cookie 失效，请重新登录")
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"results/legs6_{stamp}.csv"
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
            flag = " <== 过线" if isinstance(st.get("sharpe"), (int, float)) and st["sharpe"] >= 2.057 else ""
            print(f'[{i}/{len(LEGS)}] {name:6s} {aid}  S={row["sharpe"]}  '
                  f'F={row["fitness"]}  T={row["turnover"]}  R={row["returns"]}  '
                  f'FAIL={bad}{flag}', flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{len(LEGS)}] {name:6s} FAILED: {str(e)[:200]}", flush=True)
            rows.append({"name": name, "alpha_id": "", "sharpe": "", "fitness": "",
                         "turnover": "", "returns": "", "fails": "ERROR"})
        flush()
        time.sleep(2)

    print(f"\n结果已保存: {out}")


if __name__ == "__main__":
    main()
