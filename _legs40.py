"""第四十阶段：BA1(decay0, S1.30/T29.17%/F0.63) 提升 —— 压换手 + 提收益。

核心矛盾：
  decay0  Sharpe 1.30（过 1.25）但 Turnover 29.17% -> Fitness 分母 0.2917 -> F0.63
  decay10 Sharpe 1.17（不过） 但 Turnover 13.93% -> F0.78
  说明信号的有效成分是高频的，decay 会杀 alpha。

三条数学路径：
  路径A（压 T 到 12.5% 以下）：F = S x sqrt(R/0.125)，需 S>=1.4 且 R>=7%
  路径B（加慢腿配平）：0.7*fast(T29%) + 0.3*slow(T3%) -> 整体 T~16%
  路径C（提集中度）：trunc 0.02 -> 0.05/0.08 提 Sharpe

关键修正：BRAIN 不支持 lag()，必须用 ts_delay()（BA5-BA8 ERROR 的根因）。
"""
import csv, time
from datetime import datetime
import brain

BASE = {"neutralization": "SUBINDUSTRY", "decay": 0, "universe": "TOP3000", "truncation": 0.02}

# ---------------- 快腿（BA1 原式，decay0 下 S1.30） ----------------
FAST = ("group_rank(-ts_corr(close, volume, 20), subindustry) "
        "+ group_rank(-ts_std_dev(volume, 20) / ts_mean(volume, 20), subindustry)")

# ---------------- 慢腿候选（压整体换手，纯 pv1 保持数据源纯度） ----------------
SLOW_REV60 = "group_rank(-ts_mean(returns, 60), subindustry)"          # 60日反转（慢）
SLOW_LOWVOL = "group_rank(-ts_std_dev(returns, 60), subindustry)"      # 低波动溢价（慢）
SLOW_REV120 = "group_rank(-ts_mean(returns, 120), subindustry)"        # 半年反转（更慢）

# ---------------- 反转腿（修正 lag -> ts_delay） ----------------
REV5_PV1 = "group_rank(-ts_rank(close / ts_delay(close, 5), 60), sector)"

LEGS = [
    # === A 组：提集中度（trunc 阶梯）===
    ("A1_t005", FAST, {"truncation": 0.05}),
    ("A2_t008", FAST, {"truncation": 0.08}),
    ("A3_t010", FAST, {"truncation": 0.10}),

    # === B 组：换中性化（降换手）===
    ("B1_industry", FAST, {"neutralization": "INDUSTRY"}),
    ("B2_market", FAST, {"neutralization": "MARKET"}),

    # === C 组：加慢腿配平换手 ===
    ("C1_f07_s03_rev60", f"0.7 * ({FAST}) + 0.3 * ({SLOW_REV60})", {}),
    ("C2_f05_s05_rev60", f"0.5 * ({FAST}) + 0.5 * ({SLOW_REV60})", {}),
    ("C3_f07_s03_lowvol", f"0.7 * ({FAST}) + 0.3 * ({SLOW_LOWVOL})", {}),
    ("C4_f06_s04_rev120", f"0.6 * ({FAST}) + 0.4 * ({SLOW_REV120})", {}),

    # === D 组：结构变体 ===
    ("D1_t006_ts_delay_rev", f"{FAST} + 0.5 * {REV5_PV1}", {"truncation": 0.06}),
    ("D2_corr10", "group_rank(-ts_corr(close, volume, 10), subindustry) "
                  "+ group_rank(-ts_std_dev(volume, 20) / ts_mean(volume, 20), subindustry)", {}),
    ("D3_sector_t006", ("group_rank(-ts_corr(close, volume, 20), sector) "
                        "+ group_rank(-ts_std_dev(volume, 20) / ts_mean(volume, 20), sector)"),
     {"truncation": 0.06}),

    # === E 组：慢腿单腿基线（验证慢腿本身强度，用于配平判断）===
    ("E1_slow_rev60", SLOW_REV60, {"decay": 10}),
    ("E2_slow_lowvol", SLOW_LOWVOL, {"decay": 10}),
]


def main():
    s = brain.load()
    if not brain.authenticated(s):
        print("cookie 失效，请重新登录")
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"results/legs40_{stamp}.csv"
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
            print(f'[{i}/{len(LEGS)}] {name:22s} {aid} S={row["sharpe"]} F={row["fitness"]} '
                  f'T={row["turnover"]} R={row["returns"]} FAIL={bad}', flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{len(LEGS)}] {name:22s} FAILED {str(e)[:130]}", flush=True)
            rows.append({"name": name, "alpha_id": "", "sharpe": "", "fitness": "",
                         "turnover": "", "returns": "", "fails": f"ERROR: {str(e)[:180]}"})
        flush()
        time.sleep(1.5)

    ok = [r for r in rows
          if isinstance(r["sharpe"], (int, float)) and isinstance(r["fitness"], (int, float))]
    ok.sort(key=lambda r: (r["fitness"] if isinstance(r["fitness"], (int, float)) else -9),
            reverse=True)
    print("\n=== 按 Fitness 排序（目标 S>=1.25 且 F>=1.0）===")
    for r in ok:
        flag = " ★可提交" if r["sharpe"] >= 1.25 and r["fitness"] >= 1.0 else ""
        print(f'S={r["sharpe"]:<5} F={r["fitness"]:<5} T={r["turnover"]:<7} '
              f'R={r["returns"]:<7} {r["name"]:22s} {r["alpha_id"]}{flag}  {r["fails"]}')
    print(f"\n结果已保存: {out}")


if __name__ == "__main__":
    main()
