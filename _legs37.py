"""BRAIN 算子名直接测试 + STD_VOL 深化 + 价格因子变体。
之前 legs36 第一条 ERROR 可能导致脚本异常退出，这次每条独立 try。
"""
import csv, time
from datetime import datetime
import brain

BASE = {"neutralization": "SUBINDUSTRY", "decay": 10, "universe": "TOP3000", "truncation": 0.02}

# ---- Part 1: 算子名探测 ----
OP_PROBES = [
    ("P1_ts_corr", "ts_corr(close, volume, 20)", {}),
    ("P2_ts_corr_returns", "ts_corr(close/lag(close,1), volume/lag(volume,1), 20)", {}),
    ("P3_group_rank_volcov", "-group_rank(ts_corr(close, volume, 20), subindustry)", {}),
    ("P4_simple_rank", "rank(close / lag(close, 5))", {}),
    ("P5_simple_decay", "rank(close / lag(close, 5))", {"decay": 20}),
    ("P6_price_decay", "-group_rank(close / lag(close, 5), subindustry)", {"decay": 20}),
]

# ---- Part 2: STD_VOL20 深化（已确认算子支持） ----
STD = "-group_rank(ts_std_dev(volume, 20) / ts_mean(volume, 20), subindustry)"

STD_VARIANTS = [
    ("SV1_decay20", STD, {"decay": 20}),
    ("SV2_decay30", STD, {"decay": 30}),
    ("SV3_decay5", STD, {"decay": 5}),
    ("SV4_t005", STD, {"truncation": 0.005}),
    ("SV5_t005_d20", STD, {"truncation": 0.005, "decay": 20}),
    ("SV6_decay40", STD, {"decay": 40}),
    ("SV7_decay60", STD, {"decay": 60}),
]

# ---- Part 3: 价格类新因子（用已确认的 BRAIN 算子）----
# 5 日动量（纯价格）
MOM5 = "-group_rank(ts_rank(close, 5) - ts_rank(close, 20), subindustry)"  # 短期超卖
# 成交量变化率（放量 + 跌 = 反转信号）
VOL_CHG = "-group_rank(ts_mean(volume, 5) / ts_mean(volume, 20), subindustry)"  # 放量反向
# 波动率变化
VOL_EXP = "-group_rank(ts_std_dev(close, 5) / ts_std_dev(close, 20), subindustry)"  # 波动压缩后
# 合成：放量跌 + 低波动 + 低成交量波动（三个都是"价格"数据源，低相关）
COMBO = (f"-group_rank(close / lag(close, 5), subindustry) "
         f"-group_rank(ts_mean(volume, 5) / ts_mean(volume, 20), subindustry) "
         f"-group_rank(ts_std_dev(volume, 20) / ts_mean(volume, 20), subindustry)")

PRICE_NEW = [
    ("PN1_rev5", "-group_rank(close / lag(close, 5), subindustry)", {"decay": 20}),
    ("PN2_volchg", VOL_CHG, {"decay": 20}),
    ("PN3_vol_exp", VOL_EXP, {"decay": 20}),
    ("PN4_3leg", COMBO, {"decay": 20}),
    ("PN4b_3leg_d30", COMBO, {"decay": 30}),
    ("PN4c_3leg_d10", COMBO, {"decay": 10}),
]

ALL = OP_PROBES + STD_VARIANTS + PRICE_NEW


def main():
    s = brain.load()
    if not brain.authenticated(s):
        print("cookie 失效，请重新登录")
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"results/legs37_{stamp}.csv"
    fields = ["name", "alpha_id", "sharpe", "fitness", "turnover", "returns", "fails"]
    rows = []

    def flush():
        with open(out, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)

    for i, (name, expr, over) in enumerate(ALL, 1):
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
            status = "✓" if aid else "✗"
            print(f'[{i}/{len(ALL)}] {name:20s} {status} {aid} S={row["sharpe"]} F={row["fitness"]} '
                  f'T={row["turnover"]} R={row["returns"]} FAIL={bad}', flush=True)
        except Exception as e:  # noqa: BLE001
            err = str(e)
            print(f"[{i}/{len(ALL)}] {name:20s} ✗ {err[:100]}", flush=True)
            rows.append({"name": name, "alpha_id": "", "sharpe": "", "fitness": "",
                         "turnover": "", "returns": "", "fails": err[:100]})
        flush()
        time.sleep(1.5)

    ok = [r for r in rows if isinstance(r["sharpe"], (int, float)) and r["sharpe"] is not None]
    ok.sort(key=lambda r: r["sharpe"], reverse=True)
    print("\n=== 排序（纯价格源，基准 STD_VOL20_d10 S0.96）===")
    for r in ok:
        print(f'{r["sharpe"]:6.2f}  F={r["fitness"]:<5} T={r["turnover"]:<7} '
              f'R={r["returns"]:<7} {r["name"]:20s} {r["alpha_id"]}  {r["fails"]}')
    print(f"\n结果已保存: {out}")


if __name__ == "__main__":
    main()
