"""第二十二阶段：深挖 L4（反转+前瞻E/P+IV+ROE）。

L4 基线：S2.32 / F2.52 / T19.67% / R23.17%（decay10, MARKET, TOP1000）
T19.67% 刚超过 12.5% 阈值，F 分母未锁定。若能降到 <12.5%，F 可再跳一档。

  S2.32 T19.67% R23.17% -> F=2.52
  若 S2.20 T12%   R22%   -> F=2.92
"""
import csv
import time
from datetime import datetime

import brain

FEP = "ts_rank(anl4_afv4_eps_mean / close, 126)"
ROE = "ts_rank(operating_income / equity, 126)"
TURN = "ts_rank(sales / assets, 126)"
IVL = "ts_backfill(implied_volatility_call_120 / parkinson_volatility_120, 20)"
REV = "ts_rank(returns, 5)"


def l4(roe_w="0.5", iv_w="0.5", extra=""):
    return (f"-rank({REV}) + rank({FEP}) + {iv_w} * rank({IVL})"
            f" + {roe_w} * rank({ROE}){extra}")


LEGS = [
    ("M1_d15", l4(), {"neutralization": "MARKET", "decay": 15, "universe": "TOP1000"}),
    ("M2_d20", l4(), {"neutralization": "MARKET", "decay": 20, "universe": "TOP1000"}),
    ("M3_roe10", l4(roe_w="1.0"),
     {"neutralization": "MARKET", "decay": 10, "universe": "TOP1000"}),
    ("M4_iv10", l4(iv_w="1.0"),
     {"neutralization": "MARKET", "decay": 10, "universe": "TOP1000"}),
    ("M5_quad", l4(extra=f" + 0.5 * rank({TURN})"),
     {"neutralization": "MARKET", "decay": 10, "universe": "TOP1000"}),
    ("M6_d15_tr05", l4(),
     {"neutralization": "MARKET", "decay": 15, "universe": "TOP1000", "truncation": 0.05}),
]


def main():
    s = brain.load()
    if not brain.authenticated(s):
        print("cookie 失效，请重新登录")
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"results/legs22_{stamp}.csv"
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
    print("\n=== 按 Fitness 排序（L4 基线 S2.32 F2.52 T19.67% R23.17%）===")
    for r in ok:
        print(f'{r["sharpe"]:6.2f}  F={r["fitness"]:<5} T={r["turnover"]:<7} '
              f'R={r["returns"]:<7} {r["name"]:12s} {r["alpha_id"]}  {r["fails"]}')
    print(f"\n结果已保存: {out}")


if __name__ == "__main__":
    main()
