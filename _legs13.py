"""第十三阶段：X3（E5Q903PL）参数矩阵扫描。

X3 基线：TOP1000 / SUBINDUSTRY / decay 15 / trunc 0.01
        E5Q903PL: S2.02 / F2.05 / T7.82% / R12.92%  已提交

两条豁免路径：
  1. 换 Universe -> PnL 差异大时 corr < 0.7
  2. 参数优化 -> Sharpe 提升 >= 10%
"""
import csv
import time
from datetime import datetime

import brain

X3 = ("rank(ts_rank(anl4_ebit_value / cap, 126)) "
      "+ rank(ts_backfill(implied_volatility_call_120 / parkinson_volatility_120, 20)) "
      "+ 0.5 * rank(ts_rank(operating_income / equity, 126))")

SUB = "SUBINDUSTRY"

LEGS = [
    # Universe 变体
    ("X3_3000", X3, {"neutralization": SUB, "decay": 15, "universe": "TOP3000"}),
    ("X3_2000", X3, {"neutralization": SUB, "decay": 15, "universe": "TOP2000"}),
    # decay 变体
    ("X3_d5", X3, {"neutralization": SUB, "decay": 5, "universe": "TOP1000"}),
    ("X3_d25", X3, {"neutralization": SUB, "decay": 25, "universe": "TOP1000"}),
    # truncation 变体
    ("X3_t05", X3, {"neutralization": SUB, "decay": 15, "universe": "TOP1000",
                    "truncation": 0.05}),
    ("X3_t02", X3, {"neutralization": SUB, "decay": 15, "universe": "TOP1000",
                    "truncation": 0.02}),
]


def main():
    s = brain.load()
    if not brain.authenticated(s):
        print("cookie 失效，请重新登录")
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"results/legs13_{stamp}.csv"
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
            flag = ""
            if isinstance(st.get("sharpe"), (int, float)) and st["sharpe"] >= 2.222:
                flag = "  <== S 超基线 10%"
            print(f'[{i}/{len(LEGS)}] {name:9s} {aid}  S={row["sharpe"]}  '
                  f'F={row["fitness"]}  T={row["turnover"]}  R={row["returns"]}  '
                  f'FAIL={bad}{flag}', flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{len(LEGS)}] {name:9s} FAILED: {str(e)[:160]}", flush=True)
            rows.append({"name": name, "alpha_id": "", "sharpe": "", "fitness": "",
                         "turnover": "", "returns": "", "fails": "ERROR"})
        flush()
        time.sleep(2)

    ok = [r for r in rows if isinstance(r["sharpe"], (int, float))]
    ok.sort(key=lambda r: r["sharpe"], reverse=True)
    print("\n=== 按 Sharpe 排序（基线 2.02）===")
    for r in ok:
        print(f'{r["sharpe"]:6.2f}  F={r["fitness"]:<5} T={r["turnover"]:<7} '
              f'{r["name"]:9s} {r["alpha_id"]}  {r["fails"]}')
    print(f"\n结果已保存: {out}")


if __name__ == "__main__":
    main()
