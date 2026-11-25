"""第十九阶段：反转 + 价值 —— 池内 6 条反转全是纯反转，从未与价值腿组合。

反转单腿（池内最强）：N1PEbr17 S1.97
价值单腿（实测最强）：前瞻E/P，四腿配方下 S2.24
两者经济逻辑互补：短期被抛售 vs 长期预期便宜。

R4（反转×杠杆）corr 0.8136 失败的教训：价值腿选择很关键，
杠杆与反转在 PnL 上可能同源（都反映财务困境），而前瞻E/P 不会。
"""
import csv
import time
from datetime import datetime

import brain

REV5 = "ts_rank(returns, 5)"
REVI = "ts_rank((close - open) / open, 5)"
FEP = "ts_rank(anl4_afv4_eps_mean / close, 126)"
EBIT = "ts_rank(anl4_ebit_value / cap, 126)"
IVL = "ts_backfill(implied_volatility_call_120 / parkinson_volatility_120, 20)"

LEGS = [
    ("J1_rev_fep", f"-rank({REV5}) + rank({FEP})",
     {"neutralization": "MARKET", "decay": 3, "universe": "TOP1000"}),
    ("J2_rev_fep_iv", f"-rank({REV5}) + rank({FEP}) + 0.5 * rank({IVL})",
     {"neutralization": "MARKET", "decay": 3, "universe": "TOP1000"}),
    ("J3_rev_ebit", f"-rank({REV5}) + rank({EBIT})",
     {"neutralization": "MARKET", "decay": 3, "universe": "TOP1000"}),
    ("J4_intraday_rev_fep", f"-rank({REVI}) + rank({FEP})",
     {"neutralization": "MARKET", "decay": 3, "universe": "TOP1000"}),
]


def main():
    s = brain.load()
    if not brain.authenticated(s):
        print("cookie 失效，请重新登录")
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"results/legs19_{stamp}.csv"
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
            print(f'[{i}/{len(LEGS)}] {name:20s} {aid}  S={row["sharpe"]}  '
                  f'F={row["fitness"]}  T={row["turnover"]}  R={row["returns"]}  '
                  f'FAIL={bad}', flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{len(LEGS)}] {name:20s} FAILED: {str(e)[:160]}", flush=True)
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
              f'{r["name"]:20s} {r["alpha_id"]}  {r["fails"]}')
    print(f"\n结果已保存: {out}")


if __name__ == "__main__":
    main()
