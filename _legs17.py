"""第十七阶段：四腿结构 —— ROE 主导 + 周转率稀释行业暴露。

已提交：
  9qGZbZ2o  EBIT+IV+0.5ROE  SUB/d3/TOP1000       S2.29 F2.22
  j2VzwkrE  EBIT+IV+1.0Turn MARKET/d3/TOP1000    S1.80 F2.00
  LL8VXO86  CF+IV+ROE       MARKET/d3/TOP1000    S1.94 F2.24
  akRjlY15  EBIT+IV+0.5ROE  MARKET/d3/TOP1000    S2.08 F2.50 corr0.7743 被拒

本批四腿：ROE 权重提到 1.5-2.0（主导），周转率权重 1.0（稀释行业暴露）
避免 w1.5 那种 Sharpe 掉到 1.66 的问题。
"""
import csv
import time
from datetime import datetime

import brain

EBIT = "ts_rank(anl4_ebit_value / cap, 126)"
CF = "ts_rank(cashflow_op / cap, 126)"
FEP = "ts_rank(anl4_afv4_eps_mean / close, 126)"
ROE = "ts_rank(operating_income / equity, 126)"
TURN = "ts_rank(sales / assets, 126)"
IVL = "ts_backfill(implied_volatility_call_120 / parkinson_volatility_120, 20)"


def quad(leg1, roe_w="1.5"):
    return f"rank({leg1}) + rank({IVL}) + {roe_w} * rank({ROE}) + 1.0 * rank({TURN})"


LEGS = [
    ("B1_quad", quad(EBIT), {"neutralization": "MARKET", "decay": 3, "universe": "TOP1000"}),
    ("B2_roe2", quad(EBIT, "2.0"), {"neutralization": "MARKET", "decay": 3, "universe": "TOP1000"}),
    ("B3_t2k", quad(EBIT), {"neutralization": "MARKET", "decay": 3, "universe": "TOP2000"}),
    ("B4_ind", quad(EBIT), {"neutralization": "INDUSTRY", "decay": 3, "universe": "TOP1000"}),
    ("B5_cf_quad", quad(CF), {"neutralization": "MARKET", "decay": 3, "universe": "TOP1000"}),
    ("B6_fep_quad", quad(FEP), {"neutralization": "MARKET", "decay": 3, "universe": "TOP1000"}),
]


def main():
    s = brain.load()
    if not brain.authenticated(s):
        print("cookie 失效，请重新登录")
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"results/legs17_{stamp}.csv"
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
            print(f'[{i}/{len(LEGS)}] {name:12s} {aid}  S={row["sharpe"]}  '
                  f'F={row["fitness"]}  T={row["turnover"]}  R={row["returns"]}  '
                  f'FAIL={bad}', flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{len(LEGS)}] {name:12s} FAILED: {str(e)[:160]}", flush=True)
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
              f'{r["name"]:12s} {r["alpha_id"]}  {r["fails"]}')
    print(f"\n结果已保存: {out}")


if __name__ == "__main__":
    main()
