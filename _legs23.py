"""第二十三阶段：纯期权微观结构（option9）。

目的：Challenge 按 Pyramid（数据领域）去重，用户 8 条高分 alpha 全部落在
"基本面+期权+分析师复合" 这同一个里，名额被 legprrG8(F2.60) 占住。

本批刻意只用 option9 字段（pcr_oi / pcr_vol / call|put_breakeven / forward_price），
不掺基本面、分析师、价格反转，目标是落入全新 Pyramid 并拿到该领域唯一计分名额。

约束：Sharpe>=1.25, Fitness>=1.0, 2%<=T<=70%, 子池 Sharpe 达标。
全用 rank() 保证持仓均匀（规避 CONCENTRATED_WEIGHT），MARKET 中性化避免双重中性化。
"""
import csv
import time
from datetime import datetime

import brain

# option9 字段
PCR_OI = "ts_backfill(pcr_oi_90, 20)"
PCR_VOL = "ts_backfill(pcr_vol_90, 20)"
CALL_BE = "ts_backfill(call_breakeven_120, 20)"
PUT_BE = "ts_backfill(put_breakeven_120, 20)"
FWD = "ts_backfill(forward_price_120, 20)"

LEGS = [
    # Q1 持仓比率期限结构
    ("Q1_term", f"rank(ts_rank({PCR_OI} / ts_backfill(pcr_oi_360, 20), 126))"),
    # Q2 持仓变化反向（已验证基线）
    ("Q2_chg", f"rank(-ts_delta({PCR_OI}, 20))"),
    # Q3 成交量拥挤反向
    ("Q3_vol", f"rank(-ts_rank({PCR_VOL}, 126))"),
    # Q4 看涨盈亏平衡溢价
    ("Q4_call_be", f"rank(ts_rank({CALL_BE} / close - 1, 126))"),
    # Q5 看跌盈亏平衡折价
    ("Q5_put_be", f"rank(ts_rank(1 - {PUT_BE} / close, 126))"),
    # Q6 合成远期溢价
    ("Q6_fwd", f"rank(ts_rank({FWD} / close - 1, 126))"),
    # Q7 持仓+成交量双维度
    ("Q7_dual", f"rank(-ts_rank({PCR_OI}, 126)) + 0.5 * rank(-ts_rank({PCR_VOL}, 126))"),
    # Q8 持仓变化 + 定价空间
    ("Q8_chg_be", f"rank(-ts_delta({PCR_OI}, 20)) + 0.5 * rank(ts_rank({CALL_BE} / close - 1, 126))"),
]

SET = {"neutralization": "MARKET", "decay": 15, "universe": "TOP3000"}


def main():
    s = brain.load()
    if not brain.authenticated(s):
        print("cookie 失效，请重新登录")
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"results/legs23_{stamp}.csv"
    fields = ["name", "alpha_id", "sharpe", "fitness", "turnover", "returns", "fails"]
    rows = []

    def flush():
        with open(out, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)

    for i, (name, expr) in enumerate(LEGS, 1):
        try:
            sim_id, retry_after = brain.simulate(s, expr, **SET)
            time.sleep(retry_after)
            d = brain.wait(s, sim_id, timeout=480)
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
            print(f'[{i}/{len(LEGS)}] {name:11s} {aid}  S={row["sharpe"]}  '
                  f'F={row["fitness"]}  T={row["turnover"]}  R={row["returns"]}  '
                  f'FAIL={bad}', flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{len(LEGS)}] {name:11s} FAILED: {str(e)[:150]}", flush=True)
            rows.append({"name": name, "alpha_id": "", "sharpe": "", "fitness": "",
                         "turnover": "", "returns": "", "fails": "ERROR"})
        flush()
        time.sleep(2)

    ok = [r for r in rows
          if isinstance(r["sharpe"], (int, float)) and isinstance(r["fitness"], (int, float))]
    ok.sort(key=lambda r: r["fitness"], reverse=True)
    print("\n=== 按 Fitness 排序（目标：零 FAIL 且 S>=1.25 F>=1.0）===")
    for r in ok:
        print(f'{r["sharpe"]:6.2f}  F={r["fitness"]:<5} T={r["turnover"]:<7} '
              f'R={r["returns"]:<7} {r["name"]:11s} {r["alpha_id"]}  {r["fails"]}')
    print(f"\n结果已保存: {out}")


if __name__ == "__main__":
    main()
