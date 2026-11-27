"""第三十阶段：弱腿组合的 sqrt(n) 对照实验。

单腿 Sharpe：商誉 0.09 / 股息 -0.23 / capex 0.46 / 存货 0.77
若各腿独立，6 腿组合理论可达 0.5*sqrt(6)=1.22。
历史反证：同源弱腿组合（Q7 0.87->0.67, S4 0.78->0.20, C8 1.63->1.64）均无协同。
本批用分散在不同数据源的弱腿做首次异源组合实验。
"""
import csv
import time
from datetime import datetime

import brain

# 各弱腿（按经济逻辑方向）
GW = "ts_rank(goodwill / assets, 126)"                    # 商誉：高=减值风险
DIV = "ts_rank(dividend / close, 252)"                    # 股息溢价
CAPEX = "ts_rank(ts_backfill(anl4_capex_mean, 20) / sales, 126)"  # 高 capex=过度投资
INV = "ts_rank(inventory / assets, 126)"                  # 存货占款
ACCR = "ts_rank((income - cashflow_op) / assets, 126)"    # 应计
REC = "ts_rank(ts_delta(receivable / sales, 252), 126)"   # 应收恶化

EBITDA_Y = "ts_rank(ts_backfill(anl4_ebitda_value, 20) / cap, 126)"
REV = "ts_rank(returns, 5)"

W1 = f"-rank({GW}) + rank({DIV}) - rank({CAPEX}) - rank({INV})"
W2 = (f"-rank({GW}) + rank({DIV}) - rank({CAPEX}) - rank({INV})"
      f" - rank({ACCR}) - rank({REC})")

LEGS = [
    ("W1_4weak", W1),
    ("W2_6weak", W2),
    ("W3_2weak", f"-rank({CAPEX}) - rank({INV})"),
    ("W4_6weak_ebitda", f"0.5 * ({W2}) + rank({EBITDA_Y})"),
    ("W5_6weak_rev", f"0.5 * ({W2}) - rank({REV})"),
    ("W6_4weak_rev_sign", f"rank({GW}) - rank({DIV}) + rank({CAPEX}) + rank({INV})"),
]

SET = {"neutralization": "SUBINDUSTRY", "decay": 10, "universe": "TOP3000"}


def main():
    s = brain.load()
    if not brain.authenticated(s):
        print("cookie 失效，请重新登录")
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"results/legs30_{stamp}.csv"
    fields = ["name", "alpha_id", "sharpe", "fitness", "turnover", "returns", "fails"]
    rows = []

    def flush():
        with open(out, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)

    for i, (name, expr) in enumerate(LEGS, 1):
        try:
            sim_id, ra = brain.simulate(s, expr, **SET)
            time.sleep(ra)
            d = brain.wait(s, sim_id, timeout=520)
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
            print(f'[{i}/{len(LEGS)}] {name:20s} {aid} S={row["sharpe"]} F={row["fitness"]} '
                  f'T={row["turnover"]} R={row["returns"]} FAIL={bad}', flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{len(LEGS)}] {name:20s} FAILED {str(e)[:130]}", flush=True)
            rows.append({"name": name, "alpha_id": "", "sharpe": "", "fitness": "",
                         "turnover": "", "returns": "", "fails": "ERROR"})
        flush()
        time.sleep(2)

    ok = [r for r in rows
          if isinstance(r["sharpe"], (int, float)) and isinstance(r["fitness"], (int, float))]
    ok.sort(key=lambda r: r["sharpe"], reverse=True)
    print("\n=== 按 Sharpe 排序（单腿基准：存货0.77 capex0.46 商誉0.09 股息-0.23）===")
    for r in ok:
        print(f'{r["sharpe"]:6.2f}  F={r["fitness"]:<5} T={r["turnover"]:<7} '
              f'R={r["returns"]:<7} {r["name"]:20s} {r["alpha_id"]}  {r["fails"]}')
    print(f"\n结果已保存: {out}")


if __name__ == "__main__":
    main()
