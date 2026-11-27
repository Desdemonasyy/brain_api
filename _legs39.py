"""第三十九阶段：B2a 修正系列 —— 纯 pv1 数据源弱腿组合优化。

基线 B2a：ts_corr20 + STD_VOL20 → S1.17 / F0.78 / T13.93% / R6.26%
目标：S≥1.25 且 F≥1.0（Returns 需要从 6.26% 冲到 ~7.5%）

修正方向：
1. decay 调低（高换手 → Returns 升高）
2. 加 pv1 反转腿（已验证 S2.00，数据源正交）
3. 加低换手腿（压低整体 T，让 Fitness 分母锁定）
4. trunc 放宽（提高集中度 → Sharpe 提升）
5. ts_corr 窗口中间值（30 日）
"""
import csv, time
from datetime import datetime
import brain

BASE = {"neutralization": "SUBINDUSTRY", "decay": 10, "universe": "TOP3000", "truncation": 0.02}

# ------ 确认有效的腿 ------
CORR20_NEG = "group_rank(-ts_corr(close, volume, 20), subindustry)"
CORR30_NEG = "group_rank(-ts_corr(close, volume, 30), subindustry)"
STD_VOL20_NEG = "group_rank(-ts_std_dev(volume, 20) / ts_mean(volume, 20), subindustry)"

# 池内最强 pv1 反转腿（之前 R 系列用的 -ts_rank(returns,5) 但那是跨数据源的，这里用纯 pv1 窗口版）
REV_PV1 = "group_rank(-ts_rank(close / lag(close, 5), 60), sector)"

# 低换手腿（pv1 历史波动，方向待验证）
LOW_VOL = "group_rank(-ts_std_dev(close / lag(close, 1), 60), subindustry)"  # 低波动溢价（BAB）

LEGS = [
    # === 衰减/换手调整 ===
    ("BA1_decay0", f"{CORR20_NEG} + {STD_VOL20_NEG}", {"decay": 0}),
    ("BA2_decay5", f"{CORR20_NEG} + {STD_VOL20_NEG}", {"decay": 5}),

    # === 窗口中间值 ===
    ("BA3_corr30_vol20_decay10", f"{CORR30_NEG} + {STD_VOL20_NEG}", {"decay": 10}),
    ("BA4_corr30_vol20_decay5", f"{CORR30_NEG} + {STD_VOL20_NEG}", {"decay": 5}),

    # === 加反转腿（pv1 三腿，数据源全独立） ===
    ("BA5_plus_rev", 
     f"{CORR20_NEG} + {STD_VOL20_NEG} + 0.5 * {REV_PV1}",
     {"decay": 10}),
    ("BA6_plus_rev_decay5",
     f"{CORR20_NEG} + {STD_VOL20_NEG} + 0.5 * {REV_PV1}",
     {"decay": 5}),

    # === 加低波动腿 ===
    ("BA7_plus_lowvol",
     f"{CORR20_NEG} + {STD_VOL20_NEG} + {LOW_VOL}",
     {"decay": 10}),
    ("BA8_plus_lowvol_decay5",
     f"{CORR20_NEG} + {STD_VOL20_NEG} + {LOW_VOL}",
     {"decay": 5}),

    # === trunc 放宽 ===
    ("BA9_t004_decay10", f"{CORR20_NEG} + {STD_VOL20_NEG}", {"decay": 10, "truncation": 0.04}),
    ("BA10_t004_decay5", f"{CORR20_NEG} + {STD_VOL20_NEG}", {"decay": 5, "truncation": 0.04}),

    # === 基线（同 legs38 的 B2a）做对照 ===
    ("BA0_baseline", f"{CORR20_NEG} + {STD_VOL20_NEG}", {"decay": 10}),
]


def main():
    s = brain.load()
    if not brain.authenticated(s):
        print("cookie 失效，请重新登录")
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"results/legs39_{stamp}.csv"
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
            print(f'[{i}/{len(LEGS)}] {name:24s} {aid} S={row["sharpe"]} F={row["fitness"]} '
                  f'T={row["turnover"]} R={row["returns"]} FAIL={bad}', flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{len(LEGS)}] {name:24s} FAILED {str(e)[:130]}", flush=True)
            rows.append({"name": name, "alpha_id": "", "sharpe": "", "fitness": "",
                         "turnover": "", "returns": "", "fails": "ERROR"})
        flush()
        time.sleep(1.5)

    ok = [r for r in rows
          if isinstance(r["sharpe"], (int, float)) and isinstance(r["fitness"], (int, float))]
    ok.sort(key=lambda r: r["sharpe"], reverse=True)
    print("\n=== 排序（目标 S≥1.25 且 F≥1.0）===")
    for r in ok:
        flag = " ★" if r["sharpe"] >= 1.25 and r["fitness"] >= 1.0 else ""
        print(f'{r["sharpe"]:6.2f}  F={r["fitness"]:<5} T={r["turnover"]:<7} '
              f'R={r["returns"]:<7} {r["name"]:24s} {r["alpha_id"]}{flag}  {r["fails"]}')
    print(f"\n结果已保存: {out}")


if __name__ == "__main__":
    main()
