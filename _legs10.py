"""第十阶段：低相关优先 —— 价格路径形态 + 成交量结构 + 期权持仓期限。

策略转变：不再追求最高 Sharpe，而是追求与已提交池（11 条 + X3）PnL 相关性 < 0.5。

池内 11 条集中在三类底层信号：
  1. 收益差分/反转（6 条，pv1）
  2. 会计科目水平（4 条，fundamental6/analyst4）
  3. 期权波动率曲面（2 条，option8）

本批全部避开这三类：只看「价格位置」「成交量分布」「期权持仓跨期配置」。
"""
import csv
import time
from datetime import datetime

import brain

SUB = "SUBINDUSTRY"

LEGS = [
    # P1 52 周高点距离（锚定效应）
    ("P1_52wk_high",
     "rank(ts_rank(close / ts_max(close, 252), 126))",
     {"neutralization": SUB, "decay": 20}),
    # P2 彩票效应 MAX（规避极端单日涨幅）
    ("P2_lottery",
     "rank(-ts_rank(ts_max(returns, 20) / ts_std_dev(returns, 20), 126))",
     {"neutralization": SUB, "decay": 20}),
    # P3 价量相关性（量价背离）
    ("P3_pv_corr",
     "rank(-ts_rank(ts_corr(close, volume, 20), 126))",
     {"neutralization": SUB, "decay": 20}),
    # P4 Amihud 非流动性
    ("P4_amihud",
     "rank(ts_rank(abs(returns) / (ts_mean(volume, 20) * close + 1), 126))",
     {"neutralization": SUB, "decay": 20}),
    # P5 异常成交量（规避资金异动）
    ("P5_abn_vol",
     "rank(-ts_rank(volume / ts_mean(volume, 60), 126))",
     {"neutralization": SUB, "decay": 20}),
    # P6 PCR 期限结构（长期 vs 短期悲观度）
    ("P6_pcr_term",
     "rank(ts_rank(pcr_oi_360 / pcr_oi_30, 126))",
     {"neutralization": SUB, "decay": 20}),
    # P7 距 52 周低点（P1 的镜像对照）
    ("P7_52wk_low",
     "rank(ts_rank(ts_min(close, 252) / close, 126))",
     {"neutralization": SUB, "decay": 20}),
    # P8 成交额水平（低流动性溢价）
    ("P8_dollar_vol",
     "rank(-ts_rank(ts_mean(volume * close, 20), 126))",
     {"neutralization": SUB, "decay": 20}),
]


def main():
    s = brain.load()
    if not brain.authenticated(s):
        print("cookie 失效，请重新登录")
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"results/legs10_{stamp}.csv"
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
            print(f'[{i}/{len(LEGS)}] {name:13s} {aid}  S={row["sharpe"]}  '
                  f'F={row["fitness"]}  T={row["turnover"]}  R={row["returns"]}  '
                  f'FAIL={bad}', flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{len(LEGS)}] {name:13s} FAILED: {str(e)[:300]}", flush=True)
            rows.append({"name": name, "alpha_id": "", "sharpe": "", "fitness": "",
                         "turnover": "", "returns": "", "fails": "ERROR"})
        flush()
        time.sleep(2)

    ok = [r for r in rows if isinstance(r["sharpe"], (int, float))]
    ok.sort(key=lambda r: r["sharpe"], reverse=True)
    print("\n=== 按 Sharpe 排序 ===")
    for r in ok:
        print(f'{r["sharpe"]:6.2f}  F={r["fitness"]:<5} T={r["turnover"]:<7} '
              f'{r["name"]:13s} {r["alpha_id"]}  {r["fails"]}')
    print(f"\n结果已保存: {out}")


if __name__ == "__main__":
    main()
