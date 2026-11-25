#!/usr/bin/env python3
"""WorldQuant BRAIN 最小 API 客户端：登录 / 模拟 / 轮询 / 指标 / 自动提交。

用法：
    python brain.py login                      # 账号密码登录，保存 cookie
    python brain.py "<表达式>"                  # 跑一次模拟并打印指标
    python brain.py "<表达式>" --decay 25 --truncation 0.02
    python brain.py @exprs/triple.txt --decay 30     # 从文件读表达式
    python brain.py sweep @exprs/triple.txt          # decay/truncation 固定网格
    python brain.py scan @exprs/triple_tpl.txt \
        --grid "w_n=1.0,1.25,1.5" --grid "decay=25,30,35"
"""
import base64
import csv
import getpass
import itertools
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

API = "https://api.worldquantbrain.com"
HEADERS = {"Accept": "application/json;version=2.0", "Content-Type": "application/json"}
STATE = Path(__file__).parent / ".state" / "session.json"

BASE_SETTINGS = {
    "instrumentType": "EQUITY",
    "region": "USA",
    "universe": "TOP3000",
    "delay": 1,
    "decay": 30,
    "neutralization": "INDUSTRY",
    "truncation": 0.01,
    "pasteurization": "ON",
    "nanHandling": "OFF",
    "unitHandling": "VERIFY",
    "language": "FASTEXPR",
    "visualization": False,
}


def save(session):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    cookies = [
        {"name": c.name, "value": c.value, "domain": c.domain, "path": c.path}
        for c in session.cookies
    ]
    STATE.write_text(json.dumps({"cookies": cookies}, ensure_ascii=False, indent=2))
    print(f"cookie 已保存到 {STATE}")


def load():
    session = requests.Session()
    if STATE.exists():
        for c in json.loads(STATE.read_text())["cookies"]:
            session.cookies.set(c["name"], c["value"], domain=c["domain"].lstrip("."), path=c.get("path", "/"))
    return session


def authenticated(session):
    """用 /users/self 判定：/authentication 对匿名请求也返回 204，会误判。"""
    try:
        resp = session.get(f"{API}/users/self", headers=HEADERS, timeout=30)
        return resp.status_code == 200
    except requests.RequestException:
        return False


def login():
    email = input("BRAIN 邮箱: ").strip()
    password = getpass.getpass("密码（不会回显）: ")
    cred = base64.b64encode(f"{email}:{password}".encode()).decode()
    session = requests.Session()
    resp = session.post(
        f"{API}/authentication",
        headers={"Authorization": f"Basic {cred}", **HEADERS},
        timeout=60,
    )
    print("状态码:", resp.status_code)
    if resp.status_code == 204:
        save(session)
        print("登录成功")
    else:
        print("登录失败，返回：", resp.text[:500])
        print("若被 reCAPTCHA 拦截，请改用浏览器 Application 面板复制 cookie，或 Network 里 Copy as cURL 取 Cookie 头。")


def simulate(session, expr, **overrides):
    settings = dict(BASE_SETTINGS)
    settings.update({k: v for k, v in overrides.items() if v is not None})
    resp = session.post(
        f"{API}/simulations",
        headers=HEADERS,
        json={"type": "REGULAR", "settings": settings, "regular": expr},
        timeout=60,
    )
    if resp.status_code != 201:
        raise RuntimeError(f"模拟提交失败 {resp.status_code}: {resp.text[:500]}")
    sim_id = resp.headers["Location"].rstrip("/").split("/")[-1]
    retry_after = float(resp.headers.get("Retry-After", 5))
    return sim_id, retry_after


def wait(session, sim_id, timeout=900):
    start = time.time()
    while time.time() - start < timeout:
        data = session.get(f"{API}/simulations/{sim_id}", headers=HEADERS, timeout=60).json()
        status = data.get("status")
        if status == "COMPLETE":
            return data
        if status == "ERROR":
            raise RuntimeError(f"模拟出错: {data}")
        time.sleep(8)
    raise TimeoutError(f"模拟 {sim_id} 超时")


def report(session, alpha_id):
    alpha = session.get(f"{API}/alphas/{alpha_id}", headers=HEADERS, timeout=60).json()
    stats = alpha.get("is", {})
    print(
        f'{alpha_id}  S={stats.get("sharpe", 0):.2f}  F={stats.get("fitness", 0):.2f}  '
        f'T={stats.get("turnover", 0) * 100:.1f}%  R={stats.get("returns", 0) * 100:.1f}%'
    )
    for check in stats.get("checks", []):
        value = check.get("value", "")
        limit = check.get("limit", "")
        print(f'   {check["name"]:26s} {check["result"]:9s} value={value} limit={limit}')
    return alpha


def run(session, expr, **settings):
    sim_id, retry_after = simulate(session, expr, **settings)
    time.sleep(retry_after)
    data = wait(session, sim_id)
    return report(session, data["alpha"])


def sweep(session, expr):
    for decay in (25, 30, 35, 40):
        for truncation in (0.01, 0.02):
            print(f"\n--- decay={decay} truncation={truncation} ---")
            try:
                run(session, expr, decay=decay, truncation=truncation)
            except Exception as exc:  # noqa: BLE001
                print("失败:", exc)
            time.sleep(3)


def _cast(value):
    if isinstance(value, (int, float)):
        return value
    text = str(value).strip()
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        return text


def parse_scan_args(argv):
    """解析 --grid key=v1,v2 与普通 --key value 设置覆盖。"""
    grids = {}
    settings = {}
    idx = 0
    while idx < len(argv):
        arg = argv[idx]
        if arg == "--grid":
            key, values = argv[idx + 1].split("=", 1)
            grids[key] = [_cast(v) for v in values.split(",")]
            idx += 2
        elif arg.startswith("--"):
            settings[arg[2:]] = _cast(argv[idx + 1])
            idx += 2
        else:
            idx += 1
    return grids, settings


def _check(stats, name):
    for item in stats.get("checks", []):
        if item.get("name") == name:
            return item.get("value"), item.get("limit")
    return None, None


def scan(session, expr_template, grids, base_settings, pause=2):
    """按网格批量模拟，结果写入 results/scan_*.csv。"""
    keys = list(grids)
    combos = list(itertools.product(*[grids[k] for k in keys])) if keys else [()]
    total = len(combos)
    if total > 60:
        print(f"注意：共 {total} 组，预计耗时很长，随时可 Ctrl+C 中断（已完成的结果仍会写入 CSV）")

    out_dir = Path(__file__).parent / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"scan_{datetime.now():%Y%m%d_%H%M%S}.csv"
    rows = []

    for index, combo in enumerate(combos, 1):
        values = dict(zip(keys, combo))
        expr = expr_template
        settings = dict(base_settings)
        for key, value in values.items():
            if key in BASE_SETTINGS:
                settings[key] = _cast_setting(key, value)
            else:
                expr = expr.replace("{" + key + "}", str(value))
        label = " ".join(f"{k}={v}" for k, v in values.items())
        print(f"[{index}/{total}] {label}", flush=True)
        try:
            sim_id, retry_after = simulate(session, expr, **settings)
            time.sleep(retry_after)
            data = wait(session, sim_id)
            alpha = session.get(f"{API}/alphas/{data['alpha']}", headers=HEADERS, timeout=60).json()
            stats = alpha.get("is", {})
            sub_value, sub_limit = _check(stats, "LOW_SUB_UNIVERSE_SHARPE")
            sharpe = stats.get("sharpe") or 0
            fitness = stats.get("fitness") or 0
            turnover = stats.get("turnover") or 0
            row = {
                "params": label,
                "alpha_id": alpha.get("id"),
                "sharpe": round(sharpe, 3),
                "fitness": round(fitness, 3),
                "turnover": round(turnover, 4),
                "returns": round(stats.get("returns") or 0, 4),
                "drawdown": round(stats.get("drawdown") or 0, 4),
                "margin": stats.get("margin"),
                "sub_universe_sharpe": sub_value,
                "sub_universe_limit": sub_limit,
                "pass_basic": bool(
                    sharpe >= 1.25 and fitness >= 1.0 and 0.01 <= turnover <= 0.7
                ),
            }
            print(
                f"    S={sharpe:.2f} F={fitness:.2f} T={turnover * 100:.1f}% "
                f"R={(stats.get('returns') or 0) * 100:.1f}%"
                + ("  <== 通过基础检查" if row["pass_basic"] else ""),
                flush=True,
            )
            rows.append(row)
        except Exception as exc:  # noqa: BLE001
            print("    失败:", exc, flush=True)
        time.sleep(pause)

    if rows:
        with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        passed = [r for r in rows if r["pass_basic"]]
        print(f"\n完成 {len(rows)}/{total} 组，基础检查通过 {len(passed)} 组")
        print(f"结果已写入 {csv_path}")
        for row in passed:
            print(f"  {row['alpha_id']}  {row['params']}  S={row['sharpe']} F={row['fitness']}")
    else:
        print("没有任何成功结果")


def _cast_setting(key, value):
    if key in ("decay", "delay"):
        return int(value)
    if key == "truncation":
        return float(value)
    return value


def parse_overrides(argv):
    settings = {}
    idx = 0
    while idx < len(argv):
        if argv[idx].startswith("--"):
            key = argv[idx][2:]
            settings[key] = _cast_setting(key, argv[idx + 1])
            idx += 2
        else:
            idx += 1
    return settings


def read_expr(arg):
    return Path(arg[1:]).read_text(encoding="utf-8") if arg.startswith("@") else arg


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    command = sys.argv[1]
    if command == "login":
        login()
        return

    session = load()
    if not authenticated(session):
        print("cookie 无效或已过期，先运行: python brain.py login")
        return

    if command == "sweep":
        sweep(session, read_expr(sys.argv[2]))
    elif command == "scan":
        grids, settings = parse_scan_args(sys.argv[3:])
        if not grids:
            print('scan 至少需要一个 --grid，例如 --grid "decay=25,30,35"')
            return
        scan(session, read_expr(sys.argv[2]), grids, settings)
    else:
        run(session, read_expr(command), **parse_overrides(sys.argv[2:]))


if __name__ == "__main__":
    main()
