"""第二十八阶段：基于新探查的 analyst4 字段构造 alpha。

核心正交点：capex（投资维度，Titman-Wei-Xie 2004 过度投资异象），
与盈利/现金流/价格全部无关，池内从未使用过水平值。
"""
import csv
import time
from datetime import datetime

import brain

EBITDA_Y = "ts_rank(ts_backfill(anl4_ebitda_value, 20) / cap, 126)"
EBIT_Y = "ts_rank(ts_backfill(anl4_ebit_mean, 20) / cap, 126)"
FCF_Y = "ts_rank(ts_backfill(anl4_fcf_median, 20) / cap, 126)"
CAPEX_NEG = "ts_rank(ts_backfill(anl4_capex_mean, 20) / sales, 126)"
CAPEX_A_NEG = "ts_rank(ts_backfill(anl4_capex_mean, 20) / assets, 126)"
COVER = "ts_rank(ts_backfill(anl4_ebitda_number, 20), 126)"

LEGS = [
    ("C1_capex_sales", f"rank(-{CAPEX_NEG})"),
    ("C2_capex_assets", f"rank(-{CAPEX_A_NEG})"),
    ("C3_capex_accel",
     "rank(-ts_rank(ts_backfill(anl4_capex_mean, 20)"
     " / ts_mean(ts_backfill(anl4_capex_mean, 20), 252), 126))"),
    ("C4_ebitda_capex", f"rank({EBITDA_Y}) + rank(-{CAPEX_NEG})"),
    ("C5_ebit_capex", f"rank({EBIT_Y}) + rank(-{CAPEX_NEG})"),
    ("C6_coverage", f"rank({COVER})"),
    ("C7_fcf_median", f"rank({FCF_Y})"),
    ("C8_three_leg", f"rank({EBITDA_Y}) + rank(-{CAPEX_NEG}) + 0.5 * rank({FCF_Y})"),
]

SET = {"neutralization": "SUBINDUSTRY", "decay": 10, "universe": "TOP3000"}


def main():
    s = brain.load()
    if not brain.authenticated(s):
        print("cookie 失效，请重新登录")
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"results/legs28_{stamp}.csv"
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
            print(f'[{i}/{len(LEGS)}] {name:18s} {aid} S={row["sharpe"]} F={row["fitness"]} '
                  f'T={row["turnover"]} R={row["returns"]} FAIL={bad}', flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{len(LEGS)}] {name:18s} FAILED {str(e)[:130]}", flush=True)
            rows.append({"name": name, "alpha_id": "", "sharpe": "", "fitness": "",
                         "turnover": "", "returns": "", "fails": "ERROR"})
        flush()
        time.sleep(2)

    ok = [r for r in rows
          if isinstance(r["sharpe"], (int, float)) and isinstance(r["fitness"], (int, float))]
    ok.sort(key=lambda r: r["fitness"], reverse=True)
    print("\n=== 按 Fitness 排序 ===")
    for r in ok:
        print(f'{r["sharpe"]:6.2f}  F={r["fitness"]:<5} T={r["turnover"]:<7} '
              f'R={r["returns"]:<7} {r["name"]:18s} {r["alpha_id"]}  {r["fails"]}')
    print(f"\n结果已保存: {out}")


if __name__ == "__main__":
    main()
