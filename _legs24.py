"""第二十四阶段：社交媒体情绪波动率。

Q 系列（legs23）证明 option9 纯单腿不可行（最高 S0.87）。

转向 docs/12 实测样本中的高分信号：
  -ts_std_dev(scl12_buzz, 18)  -> S1.47 F1.67 T13.5%
  -ts_std_dev(scl12_buzz, 20)  -> F1.77

经济逻辑：讨论热度剧烈波动 = 信息环境不稳定、投资者分歧大 = 后续负漂移。
Pyramid 归属：纯社交媒体情绪（用户目前几乎为空，仅 pwa9rPoj 沾过 news）。
"""
import csv
import time
from datetime import datetime

import brain

BUZZ = "scl12_buzz"
SENT = "scl12_sentiment"

LEGS = [
    # S1 docs/12 原式
    ("S1_buzz20", f"-ts_std_dev(ts_backfill({BUZZ}, 20), 20)"),
    # S2 加横截面归一化，防权重集中
    ("S2_buzz20_rank", f"rank(-ts_std_dev(ts_backfill({BUZZ}, 20), 20))"),
    # S3 情绪波动（与声量波动不同维度）
    ("S3_sent20", f"-ts_std_dev(ts_backfill({SENT}, 20), 20)"),
    # S4 双维度组合
    ("S4_dual", f"rank(-ts_std_dev(ts_backfill({BUZZ}, 20), 20))"
                f" + rank(-ts_std_dev(ts_backfill({SENT}, 20), 20))"),
]

SET = {"neutralization": "SUBINDUSTRY", "decay": 10, "universe": "TOP3000"}


def main():
    s = brain.load()
    if not brain.authenticated(s):
        print("cookie 失效，请重新登录")
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"results/legs24_{stamp}.csv"
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
            print(f'[{i}/{len(LEGS)}] {name:15s} {aid}  S={row["sharpe"]}  '
                  f'F={row["fitness"]}  T={row["turnover"]}  R={row["returns"]}  '
                  f'FAIL={bad}', flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{len(LEGS)}] {name:15s} FAILED: {str(e)[:150]}", flush=True)
            rows.append({"name": name, "alpha_id": "", "sharpe": "", "fitness": "",
                         "turnover": "", "returns": "", "fails": "ERROR"})
        flush()
        time.sleep(2)

    ok = [r for r in rows
          if isinstance(r["sharpe"], (int, float)) and isinstance(r["fitness"], (int, float))]
    ok.sort(key=lambda r: r["fitness"], reverse=True)
    print("\n=== 按 Fitness 排序（docs/12 参照: S1.47 F1.67 T13.5%）===")
    for r in ok:
        print(f'{r["sharpe"]:6.2f}  F={r["fitness"]:<5} T={r["turnover"]:<7} '
              f'R={r["returns"]:<7} {r["name"]:15s} {r["alpha_id"]}  {r["fails"]}')
    print(f"\n结果已保存: {out}")


if __name__ == "__main__":
    main()
