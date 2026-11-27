"""第四十一阶段：C1/C2 突破后精调 —— 目标 F >= 1.0。

现状：
  C1 (0.7快+0.3慢, decay0) S1.51 F0.86 T28.87% R9.35%
  C2 (0.5快+0.5慢, decay0) S1.43 F0.91 T27.81% R11.36%
  E1 慢腿单腿             S0.73 F0.58 T7.18%  R7.96%

瓶颈：Turnover 27.8-28.9%，Fitness 分母未锁定。
数学：T=20% -> F1.08；T=15% -> F1.24（只要 Sharpe 不大幅下滑）

三条降 T 手段叠加：
  1) 提高慢腿权重（0.5->0.6->0.7）
  2) 提高 decay（0->5->10）
  3) INDUSTRY 中性化 / trunc 提升
"""
import csv, time
from datetime import datetime
import brain

BASE = {"neutralization": "SUBINDUSTRY", "decay": 0, "universe": "TOP3000", "truncation": 0.02}

FAST = ("group_rank(-ts_corr(close, volume, 20), subindustry) "
        "+ group_rank(-ts_std_dev(volume, 20) / ts_mean(volume, 20), subindustry)")
SLOW = "group_rank(-ts_mean(returns, 60), subindustry)"

LEGS = [
    # === 第一组：decay 阶梯（固定 0.5/0.5）===
    ("D1_c2_d05", f"0.5 * ({FAST}) + 0.5 * ({SLOW})", {"decay": 5}),
    ("D2_c2_d10", f"0.5 * ({FAST}) + 0.5 * ({SLOW})", {"decay": 10}),
    ("D3_c2_d15", f"0.5 * ({FAST}) + 0.5 * ({SLOW})", {"decay": 15}),
    ("D4_c2_d20", f"0.5 * ({FAST}) + 0.5 * ({SLOW})", {"decay": 20}),

    # === 第二组：慢腿加权阶梯（固定 decay0）===
    ("E1_f04_s06", f"0.4 * ({FAST}) + 0.6 * ({SLOW})", {"decay": 0}),
    ("E2_f03_s07", f"0.3 * ({FAST}) + 0.7 * ({SLOW})", {"decay": 0}),
    ("E3_f02_s08", f"0.2 * ({FAST}) + 0.8 * ({SLOW})", {"decay": 0}),

    # === 第三组：组合最优猜测（慢腿加权 + 小 decay）===
    ("F1_f04_s06_d05", f"0.4 * ({FAST}) + 0.6 * ({SLOW})", {"decay": 5}),
    ("F2_f03_s07_d05", f"0.3 * ({FAST}) + 0.7 * ({SLOW})", {"decay": 5}),
    ("F3_f04_s06_d10", f"0.4 * ({FAST}) + 0.6 * ({SLOW})", {"decay": 10}),

    # === 第四组：中性化 / trunc 变体（固定 0.5/0.5 decay5）===
    ("G1_ind_d05", f"0.5 * ({FAST}) + 0.5 * ({SLOW})",
     {"decay": 5, "neutralization": "INDUSTRY"}),
    ("G2_t006_d05", f"0.5 * ({FAST}) + 0.5 * ({SLOW})",
     {"decay": 5, "truncation": 0.06}),
]


def main():
    s = brain.load()
    if not brain.authenticated(s):
        print("cookie 失效，请重新登录")
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"results/legs41_{stamp}.csv"
    fields = ["name", "alpha_id", "sharpe", "fitness", "turnover", "returns", "fails"]
    rows = []

    def flush():
        with open(out, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)

    for i, (name, expr, over) in enumerate(LEGS, 1):
        cfg = dict(BASE)
        cfg.update(over)
        try:
            sim_id, ra = brain.simulate(s, expr, **cfg)
            time.sleep(ra)
            d = brain.wait(s, sim_id, timeout=520)
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
            mark = " ★" if (isinstance(st.get("sharpe"), (int, float))
                           and st["sharpe"] >= 1.25
                           and isinstance(st.get("fitness"), (int, float))
                           and st["fitness"] >= 1.0) else ""
            print(f'[{i}/{len(LEGS)}] {name:18s} {aid} S={row["sharpe"]} F={row["fitness"]} '
                  f'T={row["turnover"]} R={row["returns"]} FAIL={bad}{mark}', flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{len(LEGS)}] {name:18s} FAILED {str(e)[:130]}", flush=True)
            rows.append({"name": name, "alpha_id": "", "sharpe": "", "fitness": "",
                         "turnover": "", "returns": "", "fails": f"ERROR: {str(e)[:180]}"})
        flush()
        time.sleep(1.5)

    ok = [r for r in rows
          if isinstance(r["fitness"], (int, float))]
    ok.sort(key=lambda r: r["fitness"], reverse=True)
    print("\n=== 按 Fitness 排序 ===")
    for r in ok:
        flag = " ★可提交" if r["sharpe"] >= 1.25 and r["fitness"] >= 1.0 else ""
        print(f'S={r["sharpe"]:<5} F={r["fitness"]:<5} T={r["turnover"]:<7} '
              f'R={r["returns"]:<7} {r["name"]:18s} {r["alpha_id"]}{flag}  {r["fails"]}')
    print(f"\n结果已保存: {out}")


if __name__ == "__main__":
    main()
