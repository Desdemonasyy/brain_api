"""第十三阶段续：X3 decay 微调，目标 Sharpe >= 2.25（留出 10% 豁免安全边际）。

基线：
  E5Q903PL (已提交)  TOP1000/SUB/decay15/trunc0.01  S2.02 F2.05
  X3_d5              TOP1000/SUB/decay5 /trunc0.01  S2.22 F2.36
豁免线 2.222，X3_d5 差 0.002。
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
    ("X3_d3", X3, {"neutralization": SUB, "decay": 3, "universe": "TOP1000"}),
    ("X3_d7", X3, {"neutralization": SUB, "decay": 7, "universe": "TOP1000"}),
    ("X3_d5_t02", X3, {"neutralization": SUB, "decay": 5, "universe": "TOP1000",
                       "truncation": 0.02}),
    ("X3_d4", X3, {"neutralization": SUB, "decay": 4, "universe": "TOP1000"}),
]


def main():
    s = brain.load()
    if not brain.authenticated(s):
        print("cookie 失效，请重新登录")
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"results/legs13b_{stamp}.csv"
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
            sh = st.get("sharpe")
            if isinstance(sh, (int, float)) and sh >= 2.25:
                flag = "  <== 过 2.25 安全线"
            print(f'[{i}/{len(LEGS)}] {name:10s} {aid}  S={row["sharpe"]}  '
                  f'F={row["fitness"]}  T={row["turnover"]}  R={row["returns"]}  '
                  f'FAIL={bad}{flag}', flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{len(LEGS)}] {name:10s} FAILED: {str(e)[:160]}", flush=True)
            rows.append({"name": name, "alpha_id": "", "sharpe": "", "fitness": "",
                         "turnover": "", "returns": "", "fails": "ERROR"})
        flush()
        time.sleep(2)

    ok = [r for r in rows if isinstance(r["sharpe"], (int, float))]
    ok.sort(key=lambda r: r["sharpe"], reverse=True)
    print("\n=== 按 Sharpe 排序（目标 >= 2.25）===")
    for r in ok:
        print(f'{r["sharpe"]:6.2f}  F={r["fitness"]:<5} T={r["turnover"]:<7} '
              f'{r["name"]:10s} {r["alpha_id"]}  {r["fails"]}')
    print(f"\n结果已保存: {out}")


if __name__ == "__main__":
    main()
