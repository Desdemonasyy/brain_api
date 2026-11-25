"""第十八阶段：更换盈利口径 —— 池内未用过的三条新腿。

已提交 X3 家族 4 条：
  9qGZbZ2o  EBIT/cap + IV + 0.5ROE   SUB/d3/T1K       S2.29 F2.22
  j2VzwkrE  EBIT/cap + IV + 1.0Turn  MARKET/d3/T1K    S1.80 F2.00
  LL8VXO86  CF/cap   + IV + ROE      MARKET/d3/T1K    S1.94 F2.24
  legprrG8  前瞻E/P  + IV + 1.5ROE + 1.0Turn  MARKET/d3/T1K  S2.24 F2.60

新盈利口径（从未出现在任何已提交 alpha）：
  income/cap            经典 E/P（净利润/市值）
  cashflow_op/equity    现金回报率
  operating_income/sales 营业净利率
"""
import csv
import time
from datetime import datetime

import brain

FEP = "ts_rank(anl4_afv4_eps_mean / close, 126)"
NI = "ts_rank(income / cap, 126)"
CFE = "ts_rank(cashflow_op / equity, 126)"
NPM = "ts_rank(operating_income / sales, 126)"
ROE = "ts_rank(operating_income / equity, 126)"
TURN = "ts_rank(sales / assets, 126)"
IVL = "ts_backfill(implied_volatility_call_120 / parkinson_volatility_120, 20)"
HV = "ts_backfill(historical_volatility_120, 20)"

LEGS = [
    ("H1_ni_ep", f"rank({NI}) + rank({IVL}) + 1.5 * rank({ROE}) + 1.0 * rank({TURN})",
     {"neutralization": "MARKET", "decay": 3, "universe": "TOP1000"}),
    ("H2_cf_equity", f"rank({CFE}) + rank({IVL}) + 1.5 * rank({ROE}) + 1.0 * rank({TURN})",
     {"neutralization": "MARKET", "decay": 3, "universe": "TOP1000"}),
    ("H3_npm", f"rank({NPM}) + rank({IVL}) + 1.5 * rank({ROE}) + 1.0 * rank({TURN})",
     {"neutralization": "MARKET", "decay": 3, "universe": "TOP1000"}),
    ("H4_fep_npm", f"rank({FEP}) + rank({IVL}) + 1.5 * rank({NPM}) + 1.0 * rank({TURN})",
     {"neutralization": "MARKET", "decay": 3, "universe": "TOP1000"}),
    ("H5_fep_hv", f"rank({FEP}) + rank({HV}) + 1.5 * rank({ROE}) + 1.0 * rank({TURN})",
     {"neutralization": "MARKET", "decay": 3, "universe": "TOP1000"}),
    ("H6_fep_ind2k", f"rank({FEP}) + rank({IVL}) + 1.5 * rank({ROE}) + 1.0 * rank({TURN})",
     {"neutralization": "INDUSTRY", "decay": 3, "universe": "TOP2000"}),
]


def main():
    s = brain.load()
    if not brain.authenticated(s):
        print("cookie 失效，请重新登录")
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"results/legs18_{stamp}.csv"
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
            print(f'[{i}/{len(LEGS)}] {name:13s} {aid}  S={row["sharpe"]}  '
                  f'F={row["fitness"]}  T={row["turnover"]}  R={row["returns"]}  '
                  f'FAIL={bad}', flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{len(LEGS)}] {name:13s} FAILED: {str(e)[:160]}", flush=True)
            rows.append({"name": name, "alpha_id": "", "sharpe": "", "fitness": "",
                         "turnover": "", "returns": "", "fails": "ERROR"})
        flush()
        time.sleep(2)

    ok = [r for r in rows if isinstance(r["sharpe"], (int, float))]
    ok.sort(key=lambda r: r["fitness"] if isinstance(r["fitness"], (int, float)) else -9,
            reverse=True)
    print("\n=== 按 Fitness 排序（对照 legprrG8 F2.60 / S2.24）===")
    for r in ok:
        print(f'{r["sharpe"]:6.2f}  F={r["fitness"]:<5} T={r["turnover"]:<7} '
              f'{r["name"]:13s} {r["alpha_id"]}  {r["fails"]}')
    print(f"\n结果已保存: {out}")


if __name__ == "__main__":
    main()
