#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gaming4Free Auto Vote — undetected-chromedriver 版本
用 undetected-chromedriver 绕过 Cloudflare Turnstile 检测。
"""

import os
import sys
import time
import random
import subprocess
import json
import requests

# ============================================================
# 配置
# ============================================================
VOTE_URL = "https://g4f.gg/yousb"
MAX_RETRIES = 5
SCREENSHOT_DIR = "output/screenshots"
SOCKS5_PROXY = os.environ.get("SOCKS5_PROXY", "")

FIRST_NAMES = [
    "Alex", "Blake", "Casey", "Dana", "Ellis",
    "Finn", "Gray", "Harper", "Indigo", "Jordan",
    "Kai", "Lane", "Morgan", "Nova", "Owen",
    "Parker", "Quinn", "Reese", "Sage", "Taylor",
    "Uma", "Vale", "Wren", "Xander", "Yael", "Zion",
    "Liam", "Emma", "Noah", "Olivia", "Ethan",
    "Ava", "Mason", "Sophia", "Logan", "Isabella",
]


def random_username() -> str:
    name = random.choice(FIRST_NAMES)
    suffix = str(random.randint(1, 9999))
    return (name + suffix)[:16]


def log(msg: str, level: str = "INFO"):
    tag = {"INFO": "[INFO]", "WARN": "[WARN]", "ERROR": "[ERROR]"}.get(level, "[INFO]")
    print(f"{tag} {msg}", flush=True)


# ============================================================
# Telegram 通知
# ============================================================
def send_tg_message(token: str, chat_id: str, caption: str):
    if not token or not chat_id:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": caption},
            timeout=30,
        )
    except Exception:
        pass


def send_tg_photo(token: str, chat_id: str, photo_path: str, caption: str):
    if not token or not chat_id:
        return
    if photo_path and os.path.exists(photo_path):
        try:
            with open(photo_path, "rb") as f:
                requests.post(
                    f"https://api.telegram.org/bot{token}/sendPhoto",
                    data={"chat_id": chat_id, "caption": caption},
                    files={"photo": f},
                    timeout=30,
                )
                return
        except Exception:
            pass
    send_tg_message(token, chat_id, caption)


# ============================================================
# 服务器状态
# ============================================================
def get_server_status() -> dict | None:
    panel_url = "https://control.gaming4free.net"
    api_token = os.environ.get("PANEL_API_TOKEN", "")
    server_id = os.environ.get("SERVER_ID", "")
    if not api_token or not server_id:
        return None
    try:
        r = subprocess.run(
            ["curl", "-s", "-H", f"Authorization: Bearer {api_token}",
             "-H", "Accept: Application/vnd.pterodactyl.v1+json",
             f"{panel_url}/api/client/servers/{server_id}"],
            capture_output=True, text=True, timeout=15
        )
        data = json.loads(r.stdout)
        attrs = data.get("attributes", {})
        limits = attrs.get("limits", {})
        renewal = attrs.get("renewal") or {}
        return {
            "name": attrs.get("name", "unknown"),
            "memory": limits.get("memory", 0),
            "disk": limits.get("disk", 0),
            "cpu": limits.get("cpu", 0),
            "expires": renewal.get("expires_at", ""),
            "seconds_remaining": renewal.get("seconds_remaining", 0),
            "is_suspended": renewal.get("is_suspended", False),
            "node": attrs.get("node", ""),
        }
    except Exception:
        return None


def build_caption(status: str, username: str, reason: str = "", server_info: dict | None = None) -> str:
    if status == "success":
        title = "✅ 投票成功 (+90分钟)"
    elif status == "cooldown":
        title = "⏳ 冷却期"
    else:
        title = "❌ 投票失败"

    lines = [title, "", f"URL: {VOTE_URL}", f"用户名: {username}"]
    if reason:
        lines.append(f"原因: {reason}")

    if server_info:
        lines.append("")
        lines.append("🖥️ 服务器状态")
        lines.append(f"  名称: {server_info.get('name', 'N/A')}")
        lines.append(f"  节点: {server_info.get('node', 'N/A')}")
        seconds_remaining = server_info.get("seconds_remaining", 0)
        if seconds_remaining > 0:
            hours = int(seconds_remaining // 3600)
            minutes = int((seconds_remaining % 3600) // 60)
            lines.append(f"  剩余: {hours}小时{minutes}分钟")
        expires = server_info.get("expires", "")
        if expires:
            from datetime import datetime, timezone, timedelta
            try:
                exp_dt = datetime.fromisoformat(expires.replace("Z", "+00:00"))
                cst = timezone(timedelta(hours=8))
                exp_cst = exp_dt.astimezone(cst)
                lines.append(f"  到期: {exp_cst.strftime('%Y-%m-%d %H:%M')} CST")
            except Exception:
                lines.append(f"  到期: {expires}")
        if server_info.get("is_suspended"):
            lines.append("  ⚠️ 已暂停！")

    lines += ["", "Gaming4Free Auto Vote"]
    return "\n".join(lines)


# ============================================================
# WARP 换 IP
# ============================================================
def restart_warp() -> bool:
    log("正在重启 WARP 更换 IP...")
    try:
        old_ip = requests.get("https://api.ipify.org", timeout=10).text.strip()
        log(f"当前 IP: {old_ip}")
    except Exception:
        old_ip = "未知"

    for cmd in [
        ["sudo", "warp-cli", "--accept-tos", "disconnect"],
        ["sudo", "warp-cli", "--accept-tos", "registration", "delete"],
        ["sudo", "warp-cli", "--accept-tos", "registration", "new"],
        ["sudo", "warp-cli", "--accept-tos", "connect"],
    ]:
        try:
            subprocess.run(cmd, check=True, timeout=30, capture_output=True)
        except subprocess.CalledProcessError:
            pass
        time.sleep(3)

    time.sleep(10)
    try:
        new_ip = requests.get("https://api.ipify.org", timeout=10).text.strip()
        log(f"WARP 重连完成，新 IP: {new_ip}")
        return new_ip != old_ip
    except Exception:
        return False


# ============================================================
# 浏览器初始化 (undetected-chromedriver)
# ============================================================
def create_browser():
    import undetected_chromedriver as uc

    options = uc.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1280,900")
    options.add_argument("--lang=en-US")

    if SOCKS5_PROXY:
        options.add_argument(f"--proxy-server={SOCKS5_PROXY}")
        log(f"使用 SOCKS5 代理: {SOCKS5_PROXY}")

    driver = uc.Chrome(headless=True, options=options)
    driver.set_page_load_timeout(30)
    log("浏览器启动成功 (undetected-chromedriver)")
    return driver


def screenshot(driver, name: str) -> str | None:
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    path = os.path.join(SCREENSHOT_DIR, name)
    try:
        driver.save_screenshot(path)
        log(f"截图已保存: {path}")
        return path
    except Exception as e:
        log(f"截图失败: {e}", "WARN")
        return None


# ============================================================
# Turnstile 等待
# ============================================================
def wait_for_turnstile_token(driver, timeout: int = 90) -> bool:
    """等待 Turnstile 验证通过（token 写入 #vote-turnstile-token）"""
    log("等待 Turnstile 验证...")
    start = time.time()
    while time.time() - start < timeout:
        try:
            token = driver.execute_script(
                "return document.getElementById('vote-turnstile-token')?.value || ''"
            )
            if token and len(token) > 20:
                log(f"Turnstile 已通过! (token 长度: {len(token)})")
                return True
        except Exception:
            pass

        # 检查 iframe 中的 Turnstile 是否有结果
        try:
            # Turnstile 通过后有时会自动提交表单
            body = driver.execute_script("return document.body?.textContent || ''")
            if any(kw in body.lower() for kw in ["thank you", "vote recorded", "successfully", "+90 minutes"]):
                log("检测到投票成功消息（Turnstile 自动提交）")
                return True
            if "cooldown" in body.lower() or "already voted" in body.lower():
                log("检测到冷却消息")
                return True
        except Exception:
            pass

        time.sleep(3)

    log("Turnstile 超时未通过", "WARN")
    return False


# ============================================================
# 检查投票结果
# ============================================================
def check_vote_result(driver) -> str:
    try:
        body_text = driver.execute_script("return document.body?.textContent || ''")
    except Exception:
        return "unknown"

    body_lower = body_text.lower()

    for phrase in ["thank you for your vote", "vote recorded", "successfully voted", "+90 minutes", "90 minutes added"]:
        if phrase in body_lower:
            return "success"

    for phrase in ["cooldown", "already voted", "please wait", "try again later"]:
        if phrase in body_lower:
            return "cooldown"

    if "blocked" in body_lower or "access denied" in body_lower:
        return "blocked"

    return "unknown"


def get_timer_text(driver) -> str:
    try:
        return driver.execute_script(
            "return document.querySelector('.countdown-time')?.textContent?.trim() || ''"
        ) or ""
    except Exception:
        return ""


# ============================================================
# 单次投票尝试
# ============================================================
def attempt_vote(driver, username: str) -> tuple[bool, str, str | None]:
    log(f"打开投票页面: {VOTE_URL}")
    driver.get(VOTE_URL)
    time.sleep(5)

    # 检查封锁
    try:
        body = driver.execute_script("return document.body?.textContent || ''")
        if "blocked" in body.lower() or "access denied" in body.lower() or "error 1020" in body.lower():
            sc = screenshot(driver, "blocked.png")
            return False, "blocked", sc
    except Exception:
        pass

    timer_before = get_timer_text(driver)
    log(f"投票前倒计时: {timer_before}")

    # 填写用户名
    try:
        name_input = driver.find_element("css selector", "input[name='voter_name']")
        name_input.clear()
        name_input.send_keys(username)
        log(f"已填写用户名: {username}")
    except Exception as e:
        log(f"填写用户名失败: {e}", "WARN")

    screenshot(driver, "before_vote.png")

    # 找到并点击投票按钮
    vote_btn = None
    for selector in [".vote-btn", "button.vote-btn"]:
        try:
            vote_btn = driver.find_element("css selector", selector)
            if vote_btn.is_displayed():
                log(f"找到投票按钮: {selector}")
                break
            vote_btn = None
        except Exception:
            pass

    if not vote_btn:
        log("未找到投票按钮!", "ERROR")
        screenshot(driver, "no_button.png")
        return False, "unknown", None

    try:
        log("点击投票按钮...")
        vote_btn.click()
        time.sleep(3)
    except Exception as e:
        log(f"点击投票按钮失败: {e}", "WARN")
        return False, "unknown", None

    # 等待 Turnstile
    turnstile_ok = wait_for_turnstile_token(driver, timeout=90)

    if not turnstile_ok:
        sc = screenshot(driver, "turnstile_failed.png")
        log("Turnstile 未通过，投票无法完成")
        return False, "turnstile_failed", sc

    log("Turnstile 已通过，等待表单提交...")
    time.sleep(8)

    sc_after = screenshot(driver, "after_vote.png")
    result = check_vote_result(driver)

    timer_after = get_timer_text(driver)
    log(f"投票后倒计时: {timer_after}")

    if result == "success":
        return True, "success", sc_after
    elif result == "cooldown":
        return False, "cooldown", sc_after
    elif result == "blocked":
        return False, "blocked", sc_after
    else:
        if timer_before and timer_after and timer_before != timer_after:
            log("倒计时变化，判定为成功")
            return True, "success", sc_after
        return False, "unknown", sc_after


# ============================================================
# 主程序
# ============================================================
def main():
    tg_token = os.environ.get("TG_BOT_TOKEN", "")
    tg_chat_id = os.environ.get("TG_CHAT_ID", "")

    log("=" * 50)
    log("Gaming4Free Auto Vote (undetected-chromedriver)")
    log("=" * 50)

    driver = None
    for attempt in range(1, MAX_RETRIES + 1):
        log(f"\n--- 第 {attempt}/{MAX_RETRIES} 次尝试 ---")
        username = random_username()
        log(f"用户名: {username}")

        try:
            if driver is None:
                driver = create_browser()

            success, status, sc_path = attempt_vote(driver, username)

            if success:
                log("✅ 投票成功！")
                srv = get_server_status()
                caption = build_caption("success", username, server_info=srv)
                send_tg_photo(tg_token, tg_chat_id, sc_path, caption)
                try:
                    driver.quit()
                except Exception:
                    pass
                return 0

            if status == "cooldown":
                log("⏳ 冷却期")
                srv = get_server_status()
                caption = build_caption("cooldown", username, server_info=srv)
                send_tg_photo(tg_token, tg_chat_id, sc_path, caption)
                time.sleep(random.randint(60, 120))
                continue

            if status in ("blocked", "turnstile_failed"):
                log(f"🔐 {status}，换 IP 重试...")
                try:
                    driver.quit()
                except Exception:
                    pass
                driver = None
                restart_warp()
                time.sleep(5)
                continue

            log("❓ 未知结果，换 IP 重试...")
            try:
                driver.quit()
            except Exception:
                pass
            driver = None
            restart_warp()
            time.sleep(5)

        except Exception as e:
            log(f"异常: {e}", "ERROR")
            try:
                if driver:
                    driver.quit()
            except Exception:
                pass
            driver = None
            restart_warp()
            time.sleep(5)

    log("❌ 所有重试都失败")
    caption = build_caption("failure", "N/A", f"{MAX_RETRIES} 次重试均失败")
    send_tg_message(tg_token, tg_chat_id, caption)
    return 1


if __name__ == "__main__":
    sys.exit(main())
