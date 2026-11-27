"""第三十六阶段：BRAIN 算子名最小测试 + STD_VOL20 深化。"""
import csv
import time
from datetime import datetime
import brain

BASE = {"neutralization": "SUBINDUSTRY", "decay": 10, "universe": "TOP3000",
        "truncation": 0.02}

# ------ 算子名最小测试 ------
OP_TESTS = [
    ("test_argmax", "ts_argmax(high, 20)", {}),
    ("test_arg_max", "ts_arg_max(high, 20)", {}),
    ("test_corr", "ts_corr(close, volume, 20)", {}),
    ("test_corr_ln", "ts_corr(close, ln(volume+1), 20)", {}),
    ("test_cond", "ts_mean(close > lag(close, 1), 20)", {}),
    ("test_sum_cond", "ts_sum(close > lag(close, 1), 20)", {}),
    ("test_log", "ln(volume)", {}),
    ("test_rank_simple", "rank(ts_std_dev(volume, 20) / ts_mean(volume, 20))", {}),
]

# ------ STD_VOL20 深化（目前纯价格源最强 S0.96）------
STD_VOL = "ts_std_dev(volume, 20) / ts_mean(volume, 20)"

STD_DEEP = [
    ("sv_decay20", f"-group_rank({STD_VOL}, subindustry)", {"decay": 20}),
    ("sv_decay30", f"-group_rank({STD_VOL}, subindustry)", {"decay": 30}),
    ("sv_decay5", f"-group_rank({STD_VOL}, subindustry)", {"decay": 5}),
    ("sv_t005", f"-group_rank({STD_VOL}, subindustry)", {"truncation": 0.005}),
    ("sv_t005_d20", f"-group_rank({STD_VOL}, subindustry)", {"truncation": 0.005, "decay": 20}),
    ("sv_top2k", f"-group_rank({STD_VOL}, subindustry)", {"universe": "TOP2000"}),
    # 加动量交叉：STD_VOL + 5 日动量（之前 ERROR 是 lag 不对？用 BRAIN 的 lag）
    ("sv_mom5", f"-group_rank({STD_VOL}, subindustry) + rank(-ts_rank(close/lag(close,5), 60))", {}),
    # 加极值位置交叉（如果 argmax 被证实）
]

LEGS = OP_TESTS + STD_DEEP


def main():
    s = brain.load()
    if not brain.authenticated(s):
        print("cookie 失效，请重新登录")
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"results/legs36_{stamp}.csv"
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
            print(f'[{i}/{len(LEGS)}] {name:20s} {aid} S={row["sharpe"]} F={row["fitness"]} '
                  f'T={row["turnover"]} R={row["returns"]} FAIL={bad}', flush=True)
        except Exception as e:  # noqa: BLE001
            err = str(e)
            print(f"[{i}/{len(LEGS)}] {name:20s} ERROR {err[:150]}", flush=True)
            rows.append({"name": name, "alpha_id": "", "sharpe": "", "fitness": "",
                         "turnover": "", "returns": "", "fails": err[:80]})
        flush()
        time.sleep(2)

    ok = [r for r in rows
          if isinstance(r["sharpe"], (int, float))]
    ok.sort(key=lambda r: r["sharpe"] if isinstance(r["sharpe"], (int, float)) else -999,
            reverse=True)
    print("\n=== 算子测试结果 ===")
    for r in rows[:8]:
        if r["alpha_id"]:
            print(f'  ✓ {r["name"]:20s} 算子支持，S={r["sharpe"]}')
        else:
            print(f'  ✗ {r["name"]:20s} ERROR: {r["fails"][:60]}')
    print("\n=== STD_VOL20 深化排序 ===")
    for r in ok:
        if r["sharpe"] is not None:
            print(f'{r["sharpe"]:6.2f}  F={r["fitness"]:<5} T={r["turnover"]:<7} '
                  f'R={r["returns"]:<7} {r["name"]:20s} {r["alpha_id"]}  {r["fails"]}')
    print(f"\n结果已保存: {out}")


if __name__ == "__main__":
    main()
