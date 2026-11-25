"""第四阶段：option9 期权持仓结构 —— 真正未测的数据维度。

option9 有 74 个字段（cov 0.98），此前从未使用：
  pcr_oi_*      看跌/看涨持仓量比率（10-1080 日）
  pcr_vol_*     看跌/看涨成交量比率
  call/put_breakeven_*  盈亏平衡价
  forward_price_*       合成远期价格
"""
import csv
import time
from datetime import datetime

import brain

LEGS = [
    # O1 看涨盈亏平衡溢价：市场定价的上涨空间
    ("O1_call_bep",
     "rank(ts_rank(call_breakeven_120 / close - 1, 126))",
     {"neutralization": "SUBINDUSTRY", "decay": 20}),
    # O2 看跌盈亏平衡折价：下行保护成本
    ("O2_put_bep",
     "rank(ts_rank(1 - put_breakeven_120 / close, 126))",
     {"neutralization": "SUBINDUSTRY", "decay": 20}),
    # O3 合成远期溢价：持有成本（利率 - 股息率）
    ("O3_fwd_prem",
     "rank(ts_rank(forward_price_120 / close - 1, 126))",
     {"neutralization": "SUBINDUSTRY", "decay": 20}),
    # O4 看跌持仓比率（反向）：悲观拥挤后反转
    ("O4_pcr_oi",
     "rank(-ts_rank(pcr_oi_90, 126))",
     {"neutralization": "SUBINDUSTRY", "decay": 20}),
    # O5 看跌持仓比率变化（反向）：恐慌快速累积
    ("O5_pcr_chg",
     "rank(-ts_delta(ts_backfill(pcr_oi_90, 20), 20))",
     {"neutralization": "SUBINDUSTRY", "decay": 20}),
]


def main():
    s = brain.load()
    if not brain.authenticated(s):
        print("cookie 失效，请重新登录")
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"results/legs4_{stamp}.csv"
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
            print(f'[{i}/{len(LEGS)}] {name:12s} {aid}  S={row["sharpe"]}  '
                  f'F={row["fitness"]}  T={row["turnover"]}  R={row["returns"]}  '
                  f'FAIL={bad}', flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{len(LEGS)}] {name:12s} FAILED: {str(e)[:200]}", flush=True)
            rows.append({"name": name, "alpha_id": "", "sharpe": "", "fitness": "",
                         "turnover": "", "returns": "", "fails": "ERROR"})
        flush()
        time.sleep(2)

    ok = [r for r in rows if isinstance(r["sharpe"], (int, float))]
    ok.sort(key=lambda r: r["sharpe"], reverse=True)
    print("\n=== 按 Sharpe 排序 ===")
    for r in ok:
        print(f'{r["sharpe"]:6.2f}  F={r["fitness"]:<5} T={r["turnover"]:<7} '
              f'{r["name"]:12s} {r["alpha_id"]}  {r["fails"]}')
    print(f"\n结果已保存: {out}")


if __name__ == "__main__":
    main()
