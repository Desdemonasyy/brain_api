"""假设批次 1：7 个独立会计维度的经济假设验证（基本面纯因子，低换手结构）。

统一结构 rank(ts_rank(X, N)) + SUBINDUSTRY 中性化：
- ts_rank 拉长持仓期（T 目标 2-10%），rank 归一化防 CONCENTRATED_WEIGHT
- 每个信号对应一个不同的会计概念，彼此相关性预期低
"""
import csv
import time
from datetime import datetime

import brain

SIGNALS = [
    # H1 应计异象（Sloan 1996）：利润中现金成分越低，未来越差
    ("accruals",
     "rank(-ts_rank((income - cashflow_op) / assets, 126))"),
    # H2 应收占收入比恶化：应收增速超收入 = 收入质量下降
    ("receivable_ratio",
     "rank(-ts_rank(ts_delta(receivable / sales, 252), 126))"),
    # H3 存货周转效率：周转越快，需求与运营越好
    ("inventory_turn",
     "rank(ts_rank(inventory_turnover, 126))"),
    # H4 留存收益/权益：累计盈利厚度，财务稳健性
    ("retained_eq",
     "rank(ts_rank(retained_earnings / equity, 126))"),
    # H5 股东回报：现金分红/市值（符号待实测）
    ("div_yield",
     "rank(ts_rank(cashflow_dividends / cap, 252))"),
    # H6 经营利润率同比扩张：经营杠杆释放
    ("margin_expand",
     "rank(ts_rank(ts_delta(operating_income / sales, 252), 126))"),
    # H7 杠杆扩张（反向）：债务/资产同比上升 = 风险积累
    ("debt_expand",
     "rank(-ts_rank(ts_delta(debt / assets, 252), 126))"),
]

SETTINGS = {"neutralization": "SUBINDUSTRY", "decay": 10}


def main():
    s = brain.load()
    if not brain.authenticated(s):
        print("cookie 失效")
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"results/hypo1_{stamp}.csv"
    fields = ["name", "alpha_id", "sharpe", "fitness", "turnover", "returns", "fails"]
    rows = []

    def flush():
        with open(out, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)

    for i, (name, expr) in enumerate(SIGNALS, 1):
        try:
            sim_id, retry_after = brain.simulate(s, expr, **SETTINGS)
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
            print(f'[{i}/{len(SIGNALS)}] {name:16s} {aid}  S={row["sharpe"]}  '
                  f'F={row["fitness"]}  T={row["turnover"]}  R={row["returns"]}  '
                  f'FAIL={bad}', flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{len(SIGNALS)}] {name:16s} FAILED: {str(e)[:200]}", flush=True)
            rows.append({"name": name, "alpha_id": "", "sharpe": "", "fitness": "",
                         "turnover": "", "returns": "", "fails": "ERROR"})
        flush()
        time.sleep(2)

    ok = [r for r in rows if isinstance(r["sharpe"], (int, float))]
    ok.sort(key=lambda r: abs(r["sharpe"]), reverse=True)
    print("\n=== 按 |Sharpe| 排序 ===")
    for r in ok:
        print(f'{r["sharpe"]:6.2f}  F={r["fitness"]:<5} T={r["turnover"]:<7} {r["name"]:16s} '
              f'{r["alpha_id"]}  {r["fails"]}')
    print(f"\n结果已保存: {out}")


if __name__ == "__main__":
    main()
