"""第二十六阶段：注意力维度 + 结构关系（三个新领域的最后尝试）。

已证伪的维度：
  option9     水平/期限结构/20日变化 -> 最高 0.87
  socialmedia 波动率                 -> 最高 0.78
  news18      情绪均值/波动          -> 最高 0.42

本批换两个从未测过的维度：
  1. 注意力（Barber & Odean attention effect）：新闻条数/讨论量激增 -> 散户集中买入
     -> 短期高估 -> 负漂移。信源是"量"不是"情绪方向"。
  2. 结构关系：期权对称性、热度-情绪一致性。
"""
import csv
import time
from datetime import datetime

import brain

BUZZ = "ts_backfill(scl12_buzz, 20)"
SENT = "ts_backfill(scl12_sentiment, 20)"
NEWS_CNT = "vec_count(nws18_ssc)"

LEGS = [
    # --- 注意力：讨论量 / 新闻条数 ---
    ("R1_buzz_spike", f"rank(-ts_delta(ts_mean({BUZZ}, 5), 20))"),
    ("R2_buzz_rel", f"rank(-(ts_mean({BUZZ}, 5) / ts_mean({BUZZ}, 60)))"),
    ("R3_news_spike", f"rank(-ts_delta(ts_sum({NEWS_CNT}, 5), 20))"),
    ("R4_news_rel", f"rank(-(ts_sum({NEWS_CNT}, 5) / ts_sum({NEWS_CNT}, 60)))"),
    # --- 结构关系 ---
    ("R5_be_skew",
     "rank(ts_rank((ts_backfill(call_breakeven_120, 20) - ts_backfill(put_breakeven_120, 20))"
     " / close, 126))"),
    ("R6_pcr_slow", "rank(-ts_delta(ts_backfill(pcr_oi_90, 20), 60))"),
    ("R7_consist", f"rank(ts_corr({BUZZ}, {SENT}, 60))"),
    ("R8_sent_trend", f"rank(-ts_delta(ts_mean({SENT}, 5), 60))"),
]

SET = {"neutralization": "SUBINDUSTRY", "decay": 15, "universe": "TOP3000"}


def main():
    s = brain.load()
    if not brain.authenticated(s):
        print("cookie 失效，请重新登录")
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"results/legs26_{stamp}.csv"
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
            print(f'[{i}/{len(LEGS)}] {name:14s} {aid}  S={row["sharpe"]}  '
                  f'F={row["fitness"]}  T={row["turnover"]}  R={row["returns"]}  '
                  f'FAIL={bad}', flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{len(LEGS)}] {name:14s} FAILED: {str(e)[:150]}", flush=True)
            rows.append({"name": name, "alpha_id": "", "sharpe": "", "fitness": "",
                         "turnover": "", "returns": "", "fails": "ERROR"})
        flush()
        time.sleep(2)

    ok = [r for r in rows
          if isinstance(r["sharpe"], (int, float)) and isinstance(r["fitness"], (int, float))]
    ok.sort(key=lambda r: r["fitness"], reverse=True)
    print("\n=== 按 Fitness 排序（门槛 S>=1.25 F>=1.0）===")
    for r in ok:
        print(f'{r["sharpe"]:6.2f}  F={r["fitness"]:<5} T={r["turnover"]:<7} '
              f'R={r["returns"]:<7} {r["name"]:14s} {r["alpha_id"]}  {r["fails"]}')
    print(f"\n结果已保存: {out}")


if __name__ == "__main__":
    main()
