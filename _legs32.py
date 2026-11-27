"""第三十二阶段：突破 Returns。

已知：decay 只降换手不改收益（M3 decay10 与 N1 decay15 的 R 都是 21.56%）。
本批测五条提高收益幅度的路径：高波动源 / 强腿加权 / 集中度 / 高频 / 短窗口。
基准 N1：S2.45 F3.12 T12.52% R21.56%
"""
import csv
import time
from datetime import datetime

import brain

REV = "ts_rank(returns, 5)"
FEP = "ts_rank(anl4_afv4_eps_mean / close, 126)"
IV = "ts_backfill(implied_volatility_call_120 / parkinson_volatility_120, 20)"
ROE = "ts_rank(operating_income / equity, 126)"

N1 = f"-rank({REV}) + rank({FEP}) + rank({IV}) + rank({ROE})"

NEWS = "ts_mean(vec_avg(nws12_afterhsz_sl), 20)"
SKEW = "ts_backfill(implied_volatility_call_90 - implied_volatility_put_90, 20)"

LEGS = [
    ("R1_plus_news", f"{N1} + 0.5 * group_rank({NEWS}, subindustry)", {}),
    ("R2_plus_skew", f"{N1} + 0.5 * rank({SKEW})", {}),
    ("R3_rev_w20", f"- 2.0 * rank({REV}) + rank({FEP}) + rank({IV}) + rank({ROE})", {}),
    ("R4_trunc04", N1, {"truncation": 0.04}),
    ("R5_decay05", N1, {"decay": 5}),
    ("R6_rev3d", f"-rank(ts_rank(returns, 3)) + rank({FEP}) + rank({IV}) + rank({ROE})", {}),
]

BASE = {"neutralization": "MARKET", "decay": 15, "universe": "TOP1000",
        "truncation": 0.02}


def main():
    s = brain.load()
    if not brain.authenticated(s):
        print("cookie 失效，请重新登录")
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"results/legs32_{stamp}.csv"
    fields = ["name", "alpha_id", "sharpe", "fitness", "turnover", "returns", "fails"]
    rows = []

    def flush():
        with open(out, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)

    for i, (name, expr, over) in enumerate(LEGS, 1):
        cfg = dict(BASE)
        cfg.update(over)
        try:
            sim_id, ra = brain.simulate(s, expr, **cfg)
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
            print(f'[{i}/{len(LEGS)}] {name:16s} {aid} S={row["sharpe"]} F={row["fitness"]} '
                  f'T={row["turnover"]} R={row["returns"]} FAIL={bad}', flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{len(LEGS)}] {name:16s} FAILED {str(e)[:130]}", flush=True)
            rows.append({"name": name, "alpha_id": "", "sharpe": "", "fitness": "",
                         "turnover": "", "returns": "", "fails": "ERROR"})
        flush()
        time.sleep(2)

    ok = [r for r in rows
          if isinstance(r["sharpe"], (int, float)) and isinstance(r["fitness"], (int, float))]
    ok.sort(key=lambda r: r["fitness"], reverse=True)
    print("\n=== 按 Fitness 排序（N1 基准 F3.12 R21.56%）===")
    for r in ok:
        print(f'{r["fitness"]:6.2f}  S={r["sharpe"]:<5} T={r["turnover"]:<7} '
              f'R={r["returns"]:<7} {r["name"]:16s} {r["alpha_id"]}  {r["fails"]}')
    print(f"\n结果已保存: {out}")


if __name__ == "__main__":
    main()
