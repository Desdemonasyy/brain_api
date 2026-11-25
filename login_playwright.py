#!/usr/bin/env python3
"""打开可见浏览器，等你手动登录 BRAIN，然后自动把 cookie 保存到 .state/session.json。"""
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

STATE = Path(__file__).parent / ".state" / "session.json"
STATE.parent.mkdir(parents=True, exist_ok=True)


def launch_browser(p):
    """优先用系统已装的 Edge/Chrome，避免下载 Playwright 内置 Chromium。"""
    errors = []
    for channel in ("msedge", "chrome"):
        try:
            browser = p.chromium.launch(headless=False, channel=channel)
            print(f"已启动系统浏览器: {channel}", flush=True)
            return browser
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{channel}: {exc}")
    try:
        browser = p.chromium.launch(headless=False)
        print("已启动 Playwright 内置 Chromium", flush=True)
        return browser
    except Exception as exc:  # noqa: BLE001
        errors.append(f"chromium: {exc}")
    raise RuntimeError("没有可用的浏览器\n" + "\n".join(errors))


def main():
    with sync_playwright() as p:
        browser = launch_browser(p)
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://platform.worldquantbrain.com/sign-in", timeout=60000)
        print("已打开登录页，请在浏览器里完成登录（含验证码）……", flush=True)

        deadline = time.time() + 600
        while time.time() < deadline:
            if any(c["name"] == "t" and c.get("value") for c in context.cookies()):
                break
            time.sleep(2)
        else:
            print("等待超时，未检测到登录 cookie", flush=True)
            browser.close()
            return

        context.storage_state(path=str(STATE))
        print(f"登录成功，cookie 已保存到 {STATE}", flush=True)
        browser.close()


if __name__ == "__main__":
    main()
