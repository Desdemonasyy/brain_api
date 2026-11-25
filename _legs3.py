"""第三阶段：补齐经典维度 —— 低波动、动量、预期分歧。

M1/M2 用 option8 的 historical_volatility（覆盖 0.98，此前只用过 IV 比值）
M3/M4 用 pv1 价格，但与已提交的反转族方向相反（长窗口动量）
M5/M6 用 analyst4 的预测区间宽度（不确定性），与 L3/E1 的收益率水平不同口径
"""
import csv
import time
from datetime import datetime

import brain

LEGS = [
    # M1 低波动异象：已实现波动率水平反向
    ("M1_lowvol",
     "rank(-ts_rank(historical_volatility_120, 126))",
     {"neutralization": "SUBINDUSTRY", "decay": 20}),
    # M2 已实现波动率期限结构：短期 / 长期
    ("M2_hv_term",
     "rank(ts_rank(historical_volatility_20 / historical_volatility_180, 126))",
     {"neutralization": "SUBINDUSTRY", "decay": 20}),
    # M3 12 月动量
    ("M3_mom12",
     "rank(ts_rank(close, 252))",
     {"neutralization": "SUBINDUSTRY", "decay": 10}),
    # M4 12-1 动量（跳过最近一月，避开短期反转）
    ("M4_mom12_1",
     "rank(ts_rank(close / ts_delay(close, 21), 252))",
     {"neutralization": "SUBINDUSTRY", "decay": 10}),
    # M5 资本开支预期区间宽度（反向 = 分歧越小越好）
    ("M5_capex_disp",
     "rank(-ts_rank(ts_backfill(anl4_capex_high - anl4_capex_low, 20) / cap, 126))",
     {"neutralization": "SUBINDUSTRY", "decay": 10}),
    # M6 经营现金流预期区间宽度（反向）
    ("M6_cfo_disp",
     "rank(-ts_rank(ts_backfill(anl4_cfo_high - anl4_cfo_low, 20) / cap, 126))",
     {"neutralization": "SUBINDUSTRY", "decay": 10}),
]


def main():
    s = brain.load()
    if not brain.authenticated(s):
        print("cookie 失效，请重新登录")
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"results/legs3_{stamp}.csv"
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
            d = brain.wait(s, sim_id)
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
            print(f'[{i}/{len(LEGS)}] {name:14s} {aid}  S={row["sharpe"]}  '
                  f'F={row["fitness"]}  T={row["turnover"]}  R={row["returns"]}  '
                  f'FAIL={bad}', flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{len(LEGS)}] {name:14s} FAILED: {str(e)[:200]}", flush=True)
            rows.append({"name": name, "alpha_id": "", "sharpe": "", "fitness": "",
                         "turnover": "", "returns": "", "fails": "ERROR"})
        flush()
        time.sleep(2)

    ok = [r for r in rows if isinstance(r["sharpe"], (int, float))]
    ok.sort(key=lambda r: r["sharpe"], reverse=True)
    print("\n=== 按 Sharpe 排序 ===")
    for r in ok:
        print(f'{r["sharpe"]:6.2f}  F={r["fitness"]:<5} T={r["turnover"]:<7} '
              f'{r["name"]:14s} {r["alpha_id"]}  {r["fails"]}')
    print(f"\n结果已保存: {out}")


if __name__ == "__main__":
    main()
