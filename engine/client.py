"""BRAIN REST 客户端：会话、模拟、轮询、alpha 详情、年度统计。

与 brain.py 的区别：这里是可复用的类，带限速、429 重试、错误分类，
供 runner/audit 在并发场景调用。
"""

from __future__ import annotations

import base64
import getpass
import json
import threading
import time
from pathlib import Path

import requests

from . import config
from .records import parse_records


class AuthError(RuntimeError):
    """cookie 失效或被平台拒绝。"""


class SimulationRejected(RuntimeError):
    """平台明确拒绝模拟请求（4xx，表达式/设置错误，可安全重试修正）。"""

    def __init__(self, status_code: int, text: str):
        super().__init__(f"模拟请求被拒 {status_code}: {text[:300]}")
        self.status_code = status_code
        self.text = text


class ConcurrencyLimit(RuntimeError):
    """平台并发槽已满（429 CONCURRENT_SIMULATION_LIMIT_EXCEEDED），应等待后重试。"""

    def __init__(self, retry_after: float, text: str = ""):
        super().__init__(f"并发模拟槽已满，等待 {retry_after:.0f}s 后重试: {text[:200]}")
        self.retry_after = retry_after


class AmbiguousSubmit(RuntimeError):
    """请求已发出但结果未知（超时/连接中断），重试可能产生重复模拟。"""


class SimulationFailed(RuntimeError):
    """模拟状态为 ERROR。"""

    def __init__(self, payload: dict):
        super().__init__(f"模拟出错: {json.dumps(payload, ensure_ascii=False)[:300]}")
        self.payload = payload


class SimulationTimeout(RuntimeError):
    """轮询超时；模拟可能仍在运行，应按 sim_id 续跑。"""

    def __init__(self, sim_id: str):
        super().__init__(f"模拟 {sim_id} 轮询超时")
        self.sim_id = sim_id


def _json_or_none(response) -> dict | list | None:
    """平台在计算中可能返回 200 + 空 body，统一按 None 处理。"""
    if not response.content or not response.content.strip():
        return None
    try:
        return response.json()
    except ValueError:
        return None


class BrainClient:
    def __init__(self, state_path: Path | None = None, min_interval: float = 0.25):
        self.state_path = state_path or (config.STATE_DIR / "session.json")
        self.min_interval = min_interval
        self.session = requests.Session()
        self._lock = threading.Lock()
        self._last_request = 0.0
        self._load_cookies()

    # ---------- 会话 ----------
    def _load_cookies(self) -> None:
        if not self.state_path.exists():
            return
        payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        for cookie in payload.get("cookies", []):
            self.session.cookies.set(
                cookie["name"],
                cookie["value"],
                domain=cookie["domain"].lstrip("."),
                path=cookie.get("path", "/"),
            )

    def _save_cookies(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        cookies = [
            {
                "name": c.name,
                "value": c.value,
                "domain": c.domain,
                "path": c.path,
            }
            for c in self.session.cookies
        ]
        self.state_path.write_text(
            json.dumps({"cookies": cookies}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def login(self) -> bool:
        email = input("BRAIN 邮箱: ").strip()
        password = getpass.getpass("密码（不会回显）: ")
        credential = base64.b64encode(f"{email}:{password}".encode()).decode()
        response = requests.post(
            f"{config.API}/authentication",
            headers={"Authorization": f"Basic {credential}", **config.HEADERS},
            timeout=60,
        )
        print("状态码:", response.status_code)
        # BRAIN 新版 API 返回 201 Created（body 带 token），旧版是 204 No Content（set-cookie）
        if response.status_code not in (201, 204):
            print("登录失败，返回：", response.text[:500])
            print("若被 reCAPTCHA 拦截，改用浏览器复制 cookie 到 .state/session.json。")
            return False
        for cookie in response.cookies:
            self.session.cookies.set(cookie.name, cookie.value)
        # 201 时 token 在 JSON body 里（不是 set-cookie）
        if response.status_code == 201:
            try:
                body = response.json()
                token_val = None
                if isinstance(body.get("token"), dict):
                    token_val = body["token"].get("token") or body["token"].get("value") or body["token"].get("jwt")
                elif isinstance(body.get("token"), str):
                    token_val = body["token"]
                if token_val:
                    self.session.cookies.set("t", token_val, domain="api.worldquantbrain.com", path="/")
                    print(f"已从 body 提取 token (len={len(token_val)})")
                else:
                    print(f"WARNING: 201 但 body 无 token 字段。body keys: {list(body.keys())}")
                    print(f"  full body: {json.dumps(body, ensure_ascii=False)[:300]}")
            except Exception as e:
                print(f"WARNING: 解析 201 body 失败: {e}")
        self._save_cookies()
        print(f"登录成功，cookie 已保存到 {self.state_path}")
        return True

    def authenticated(self) -> bool:
        try:
            response = self._request("GET", "/users/self", timeout=30)
            return response.status_code == 200
        except (requests.RequestException, AuthError):
            return False

    # ---------- HTTP ----------
    def _pace(self) -> None:
        with self._lock:
            wait = self.min_interval - (time.time() - self._last_request)
            if wait > 0:
                time.sleep(wait)
            self._last_request = time.time()

    def _request(self, method: str, path: str, *, retries: int = 0, timeout: int = 60, **kwargs):
        url = path if path.startswith("http") else f"{config.API}{path}"
        attempt = 0
        while True:
            self._pace()
            response = self.session.request(
                method, url, headers=config.HEADERS, timeout=timeout, **kwargs
            )
            if response.status_code in (401, 403):
                raise AuthError(f"{response.status_code}: cookie 失效或无权访问 {url}")
            if response.status_code == 429:
                if "CONCURRENT_SIMULATION_LIMIT_EXCEEDED" in response.text:
                    return response
                wait = float(response.headers.get("Retry-After", 5))
                attempt += 1
                if attempt > max(retries, 5):
                    return response
                time.sleep(wait)
                continue
            if response.status_code >= 500 and method == "GET" and attempt < retries:
                attempt += 1
                time.sleep(2 ** attempt)
                continue
            return response

    # ---------- 模拟 ----------
    def simulate(self, expression: str, settings: dict) -> tuple[str, float]:
        payload = {"type": "REGULAR", "settings": settings, "regular": expression}
        try:
            response = self._request("POST", "/simulations", json=payload, retries=5)
        except (requests.Timeout, requests.ConnectionError) as exc:
            raise AmbiguousSubmit(f"提交模拟时网络中断: {exc}") from exc
        if response.status_code != 201:
            if response.status_code == 429:
                retry_after = float(response.headers.get("Retry-After", 30))
                raise ConcurrencyLimit(retry_after, response.text)
            raise SimulationRejected(response.status_code, response.text)
        location = response.headers.get("Location", "")
        sim_id = location.rstrip("/").split("/")[-1]
        if not sim_id:
            raise AmbiguousSubmit(f"201 但缺少 Location: {response.headers}")
        retry_after = float(response.headers.get("Retry-After", 5))
        return sim_id, retry_after

    def wait_simulation(self, sim_id: str, timeout: int = 900, interval: float = 8.0) -> dict:
        start = time.time()
        while time.time() - start < timeout:
            response = self._request("GET", f"/simulations/{sim_id}", timeout=60, retries=3)
            if response.status_code == 404:
                time.sleep(interval)
                continue
            data = response.json()
            status = data.get("status")
            if status in ("COMPLETE", "WARNING"):
                # WARNING 也是终态：可能带 alpha 但存在平台告警，交给审计判断，
                # 不能继续轮询，否则会一直“没反应”。
                return data
            if status == "ERROR":
                raise SimulationFailed(data)
            time.sleep(interval)
        raise SimulationTimeout(sim_id)

    def get_alpha(self, alpha_id: str) -> dict:
        last_status = None
        for attempt in range(3):
            response = self._request("GET", f"/alphas/{alpha_id}", timeout=60, retries=3)
            last_status = response.status_code
            if response.status_code == 200:
                payload = _json_or_none(response)
                if isinstance(payload, dict):
                    return payload
            time.sleep(2 + attempt * 2)
        raise RuntimeError(f"获取 alpha {alpha_id} 失败: {last_status}")

    def get_recordset(self, alpha_id: str, name: str) -> dict | None:
        response = self._request(
            "GET", f"/alphas/{alpha_id}/recordsets/{name}", timeout=60, retries=3
        )
        if response.status_code in (204, 404):
            return None
        if response.status_code != 200:
            raise RuntimeError(
                f"获取 {alpha_id}/{name} 失败: {response.status_code} {response.text[:200]}"
            )
        payload = _json_or_none(response)
        return payload if isinstance(payload, dict) else None

    def get_yearly_stats(self, alpha_id: str, attempts: int = 3) -> dict | None:
        payload = None
        for attempt in range(attempts):
            payload = self.get_recordset(alpha_id, "yearly-stats")
            if payload and parse_records(payload):
                return payload
            if attempt + 1 < attempts:
                time.sleep(1.5 + attempt * 1.5)
        return payload

    def get_pnl(self, alpha_id: str) -> dict | None:
        return self.get_recordset(alpha_id, "pnl")

    def get_pnl_records(self, alpha_id: str, attempts: int = 3) -> list[dict]:
        for attempt in range(attempts):
            payload = self.get_pnl(alpha_id)
            if payload:
                records = parse_records(payload)
                if records:
                    return records
            time.sleep(2 + attempt * 2)
        return []

    def get_self_correlation(self, alpha_id: str) -> list[dict]:
        response = self._request(
            "GET", f"/alphas/{alpha_id}/correlations/self", timeout=60, retries=3
        )
        if response.status_code != 200:
            return []
        payload = _json_or_none(response)
        return parse_records(payload) if payload else []

    def get_prod_correlation(self, alpha_id: str) -> float | None:
        alpha = self.get_alpha(alpha_id)
        value = (alpha.get("is") or {}).get("prodCorrelation")
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def submit_alpha(self, alpha_id: str) -> dict:
        response = self._request("POST", f"/alphas/{alpha_id}/submit", json={}, timeout=60)
        if response.status_code not in (200, 201, 202, 204):
            raise RuntimeError(
                f"提交 alpha {alpha_id} 失败: {response.status_code} {response.text[:300]}"
            )
        payload = _json_or_none(response)
        return payload if isinstance(payload, dict) else {"status_code": response.status_code}

    def list_user_alphas(self, limit: int = 50, offset: int = 0) -> list[dict]:
        response = self._request(
            "GET",
            "/users/self/alphas",
            params={
                "limit": limit,
                "offset": offset,
                "order": "-dateSubmitted",
                "hidden": "false",
            },
            timeout=60,
            retries=3,
        )
        if response.status_code != 200:
            raise RuntimeError(f"获取 alpha 列表失败: {response.status_code} {response.text[:200]}")
        payload = _json_or_none(response)
        if isinstance(payload, dict):
            return payload.get("results", [])
        return payload if isinstance(payload, list) else []

    def get_operators(self) -> list[dict]:
        response = self._request("GET", "/operators", timeout=60, retries=3)
        if response.status_code != 200:
            raise RuntimeError(f"获取算子列表失败: {response.status_code}")
        payload = _json_or_none(response)
        if isinstance(payload, dict):
            return payload.get("results", [])
        return payload if isinstance(payload, list) else []
