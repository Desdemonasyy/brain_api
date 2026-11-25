"""第十二阶段：同比增长率 —— 池内从未出现的第三类结构。

池内 12 条全部是「水平值」或「时序分位」或「收益差分」：
  收益差分（反转）6 条 / 会计科目水平 5 条 / 波动率曲面水平 2 条
本批改用 ts_delta(X, 252) / 分母 = 同比变化量，属于独立因子家族。

特点：基本面季度更新 -> 换手 2-5% -> Fitness 分母锁 0.125，对 Fitness 有利。
"""
import csv
import time
from datetime import datetime

import brain

SUB = "SUBINDUSTRY"

LEGS = [
    # G1 资产增长（负向）：Cooper et al. 2008 资产扩张异象
    ("G1_asset_growth",
     "rank(-ts_rank(ts_delta(assets, 252) / assets, 126))",
     {"neutralization": SUB, "decay": 10}),
    # G2 销售增长
    ("G2_sales_growth",
     "rank(ts_rank(ts_delta(sales, 252) / sales, 126))",
     {"neutralization": SUB, "decay": 10}),
    # G3 经营现金流增长（以资产标准化）
    ("G3_cf_growth",
     "rank(ts_rank(ts_delta(cashflow_op, 252) / assets, 126))",
     {"neutralization": SUB, "decay": 10}),
    # G4 权益增长（负向）：股权稀释
    ("G4_equity_growth",
     "rank(-ts_rank(ts_delta(equity, 252) / equity, 126))",
     {"neutralization": SUB, "decay": 10}),
    # G5 应计增长（负向）：盈余质量恶化
    ("G5_accrual_growth",
     "rank(-ts_rank(ts_delta(income - cashflow_op, 252) / assets, 126))",
     {"neutralization": SUB, "decay": 10}),
    # G6 负债增长（负向）：杠杆快速累积
    ("G6_debt_growth",
     "rank(-ts_rank(ts_delta(debt, 252) / assets, 126))",
     {"neutralization": SUB, "decay": 10}),
]


def main():
    s = brain.load()
    if not brain.authenticated(s):
        print("cookie 失效，请重新登录")
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"results/legs12_{stamp}.csv"
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
            print(f'[{i}/{len(LEGS)}] {name:17s} {aid}  S={row["sharpe"]}  '
                  f'F={row["fitness"]}  T={row["turnover"]}  R={row["returns"]}  '
                  f'FAIL={bad}', flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{len(LEGS)}] {name:17s} FAILED: {str(e)[:160]}", flush=True)
            rows.append({"name": name, "alpha_id": "", "sharpe": "", "fitness": "",
                         "turnover": "", "returns": "", "fails": "ERROR"})
        flush()
        time.sleep(2)

    ok = [r for r in rows if isinstance(r["sharpe"], (int, float))]
    ok.sort(key=lambda r: r["sharpe"], reverse=True)
    print("\n=== 按 Sharpe 排序 ===")
    for r in ok:
        print(f'{r["sharpe"]:6.2f}  F={r["fitness"]:<5} T={r["turnover"]:<7} '
              f'{r["name"]:17s} {r["alpha_id"]}  {r["fails"]}')
    print(f"\n结果已保存: {out}")


if __name__ == "__main__":
    main()
