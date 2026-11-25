"""第十五阶段：X3 叠加两个差异源，目标 corr < 0.70。

已证：
  9qGZbZ2o (SUBINDUSTRY/d3/TOP1000) 已提交 S2.29 F2.22
  akRjlY15 (MARKET/d3/TOP1000)      corr 0.7743 -> 被拒
单一差异源（换中性化）只能降 ~0.18，不足以到 0.7 以下。
本批每条叠加两个差异源：中性化 + Universe，或 中性化 + 换腿。
"""
import csv
import time
from datetime import datetime

import brain

EBIT = "ts_rank(anl4_ebit_value / cap, 126)"
CF = "ts_rank(cashflow_op / cap, 126)"
ROE = "ts_rank(operating_income / equity, 126)"
TURN = "ts_rank(sales / assets, 126)"
IVL = "ts_backfill(implied_volatility_call_120 / parkinson_volatility_120, 20)"

LEGS = [
    # v1 中性化 + Universe
    ("X3v1_t3k", f"rank({EBIT}) + rank({IVL}) + 0.5 * rank({ROE})",
     {"neutralization": "MARKET", "decay": 3, "universe": "TOP3000"}),
    # v2 中性化 + 换腿（ROE -> 资产周转率）
    ("X3v2_turn", f"rank({EBIT}) + rank({IVL}) + 0.5 * rank({TURN})",
     {"neutralization": "MARKET", "decay": 3, "universe": "TOP1000"}),
    # v3 中性化 + 换腿（EBIT -> CF/cap）
    ("X3v3_cf", f"rank({CF}) + rank({IVL}) + 0.5 * rank({ROE})",
     {"neutralization": "MARKET", "decay": 3, "universe": "TOP1000"}),
    # v4 中性化 + Universe（TOP2000）
    ("X3v4_t2k", f"rank({EBIT}) + rank({IVL}) + 0.5 * rank({ROE})",
     {"neutralization": "MARKET", "decay": 3, "universe": "TOP2000"}),
]


def main():
    s = brain.load()
    if not brain.authenticated(s):
        print("cookie 失效，请重新登录")
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"results/legs15_{stamp}.csv"
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
            d = brain.wait(s, sim_id, timeout=420)
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
            print(f'[{i}/{len(LEGS)}] {name:11s} {aid}  S={row["sharpe"]}  '
                  f'F={row["fitness"]}  T={row["turnover"]}  R={row["returns"]}  '
                  f'FAIL={bad}', flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{len(LEGS)}] {name:11s} FAILED: {str(e)[:160]}", flush=True)
            rows.append({"name": name, "alpha_id": "", "sharpe": "", "fitness": "",
                         "turnover": "", "returns": "", "fails": "ERROR"})
        flush()
        time.sleep(2)

    ok = [r for r in rows if isinstance(r["sharpe"], (int, float))]
    ok.sort(key=lambda r: r["fitness"] if isinstance(r["fitness"], (int, float)) else -9,
            reverse=True)
    print("\n=== 按 Fitness 排序 ===")
    for r in ok:
        print(f'{r["sharpe"]:6.2f}  F={r["fitness"]:<5} T={r["turnover"]:<7} '
              f'{r["name"]:11s} {r["alpha_id"]}  {r["fails"]}')
    print(f"\n结果已保存: {out}")


if __name__ == "__main__":
    main()
