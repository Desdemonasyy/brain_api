"""第二十阶段：反转 + 价值，降换手版。

J 系列（legs19）证明信号有效但换手 53-57%，Fitness 被压到 1.17-1.38。
根源：ts_rank(returns,5) 每天重排，组合每天全换手。

修正：先把 5 日收益做 5 日均值，再取 60 日分位 -> 只在相对季度位置变化时调仓。
decay 从 3 提到 20 进一步平滑。

X3 家族已饱和的实证：
  ROE vs NPM 换腿 -> corr 0.9447
  换中性化+universe -> corr 0.8169
质量腿（ROE/NPM/CF权益/净利润率）在 PnL 上等价，换字段无独立性。
"""
import csv
import time
from datetime import datetime

import brain

FEP = "ts_rank(anl4_afv4_eps_mean / close, 126)"
EBIT = "ts_rank(anl4_ebit_value / cap, 126)"
IVL = "ts_backfill(implied_volatility_call_120 / parkinson_volatility_120, 20)"

# 平滑后的反转：5 日均值再取 60 日分位
REV_SLOW = "ts_rank(ts_mean(returns, 5), 60)"
REV_20 = "ts_rank(returns, 20)"

LEGS = [
    ("K1_slow_fep", f"rank(-{REV_SLOW}) + rank({FEP})",
     {"neutralization": "MARKET", "decay": 20, "universe": "TOP1000"}),
    ("K2_slow_fep_iv", f"rank(-{REV_SLOW}) + rank({FEP}) + 0.5 * rank({IVL})",
     {"neutralization": "MARKET", "decay": 20, "universe": "TOP1000"}),
    ("K3_rev20_fep", f"rank(-{REV_20}) + rank({FEP})",
     {"neutralization": "MARKET", "decay": 20, "universe": "TOP1000"}),
    ("K4_slow_ebit", f"rank(-{REV_SLOW}) + rank({EBIT})",
     {"neutralization": "MARKET", "decay": 20, "universe": "TOP1000"}),
]


def main():
    s = brain.load()
    if not brain.authenticated(s):
        print("cookie 失效，请重新登录")
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"results/legs20_{stamp}.csv"
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
            print(f'[{i}/{len(LEGS)}] {name:15s} {aid}  S={row["sharpe"]}  '
                  f'F={row["fitness"]}  T={row["turnover"]}  R={row["returns"]}  '
                  f'FAIL={bad}', flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{len(LEGS)}] {name:15s} FAILED: {str(e)[:160]}", flush=True)
            rows.append({"name": name, "alpha_id": "", "sharpe": "", "fitness": "",
                         "turnover": "", "returns": "", "fails": "ERROR"})
        flush()
        time.sleep(2)

    ok = [r for r in rows if isinstance(r["sharpe"], (int, float))]
    ok.sort(key=lambda r: r["fitness"] if isinstance(r["fitness"], (int, float)) else -9,
            reverse=True)
    print("\n=== 按 Fitness 排序（对照 J2: S2.03 F1.38 T53%）===")
    for r in ok:
        print(f'{r["sharpe"]:6.2f}  F={r["fitness"]:<5} T={r["turnover"]:<7} '
              f'{r["name"]:15s} {r["alpha_id"]}  {r["fails"]}')
    print(f"\n结果已保存: {out}")


if __name__ == "__main__":
    main()
