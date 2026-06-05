#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gaming4Free Auto Vote — DrissionPage + xvfb 版本
"""

import os
import sys
import time
import random
import subprocess
import json
import requests

try:
    from DrissionPage import ChromiumPage, ChromiumOptions
except ImportError as e:
    print(f"[ERROR] DrissionPage 导入失败: {e}", flush=True)
    sys.exit(1)

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


def send_tg_message(tg_token: str, chat_id: str, caption: str):
    if not tg_token or not chat_id:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{tg_token}/sendMessage",
            data={"chat_id": chat_id, "text": caption},
            timeout=30,
        )
    except Exception:
        pass


def send_tg_photo(tg_token: str, chat_id: str, photo_path: str, caption: str):
    if not tg_token or not chat_id:
        return
    if photo_path and os.path.exists(photo_path):
        try:
            with open(photo_path, "rb") as f:
                requests.post(
                    f"https://api.telegram.org/bot{tg_token}/sendPhoto",
                    data={"chat_id": chat_id, "caption": caption},
                    files={"photo": f},
                    timeout=30,
                )
                return
        except Exception:
            pass
    send_tg_message(tg_token, chat_id, caption)


def get_server_status() -> dict | None:
    panel_url = "https://control.gaming4free.net"
    api_key = os.environ.get("PANEL_API_TOKEN", "")
    srv_id = os.environ.get("SERVER_ID", "")
    if not api_key or not srv_id:
        return None
    try:
        auth_header = "Bearer " + api_key
        url = panel_url + "/api/client/servers/" + srv_id
        r = subprocess.run(
            ["curl", "-s", "-H", "Authorization: " + auth_header,
             "-H", "Accept: Application/vnd.pterodactyl.v1+json", url],
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
        if server_info.get("is_suspended"):
            lines.append("  ⚠️ 已暂停！")

    lines += ["", "Gaming4Free Auto Vote"]
    return "\n".join(lines)


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


def create_browser() -> ChromiumPage:
    co = ChromiumOptions()
    use_xvfb = os.environ.get("USE_XVFB", "")
    if not use_xvfb:
        co.set_argument("--headless=new")
    co.set_argument("--no-sandbox")
    co.set_argument("--disable-dev-shm-usage")
    co.set_argument("--disable-gpu")
    co.set_argument("--window-size=1280,900")
    co.set_argument("--disable-blink-features=AutomationControlled")
    co.set_argument("--disable-infobars")
    if SOCKS5_PROXY:
        log("SOCKS5 代理已配置但 DrissionPage 不支持，跳过", "WARN")
    ua = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/" + str(random.randint(120, 130)) + ".0.0.0 Safari/537.36"
    )
    co.set_user_agent(ua)
    co.auto_port()
    return ChromiumPage(co)


def wait_for_turnstile_token(page, timeout: int = 90) -> bool:
    """
    等待 Turnstile 验证通过。
    只有在以下情况才认为通过：
    1. vote-turnstile-token input 有值
    2. 页面出现了明确的成功/冷却消息
    不再用 no_iframe 判断（太容易误判）
    """
    log("等待 Turnstile 验证...")
    start = time.time()
    while time.time() - start < timeout:
        # 方法1: 检查隐藏 input 的 token 值（最可靠）
        try:
            token_val = page.run_js(
                "return document.getElementById('vote-turnstile-token')?.value || ''"
            )
            if token_val and len(token_val) > 20:
                log(f"Turnstile 已通过! (token 长度: {len(token_val)})")
                return True
        except Exception:
            pass

        # 方法2: 检查页面是否已跳转到结果页
        try:
            body = page.run_js("return document.body?.textContent || ''")
            body_lower = body.lower()
            # 只有明确的成功消息才算通过
            if any(kw in body_lower for kw in [
                "thank you for your vote", "vote recorded",
                "successfully voted", "90 minutes added"
            ]):
                log("检测到投票成功消息")
                return True
            # 冷却消息也算通过（说明之前的投票已经生效）
            if "cooldown" in body_lower or "already voted" in body_lower:
                log("检测到冷却消息（已有投票生效）")
                return True
        except Exception:
            pass

        # 方法3: 检查表单是否已提交（URL 变化或页面内容变化）
        try:
            current_url = page.url
            if current_url and "/vote" not in current_url.lower() and "g4f.gg" in current_url:
                # 可能已经跳转回主页（投票成功后的行为）
                body2 = page.run_js("return document.body?.textContent || ''")
                if any(kw in body2.lower() for kw in ["thank you", "success", "voted"]):
                    log("检测到页面跳转，投票可能成功")
                    return True
        except Exception:
            pass

        time.sleep(3)

    log("Turnstile 超时未通过", "WARN")
    return False


def check_vote_result(page) -> str:
    """检查投票结果 - 只在表单实际提交后调用"""
    try:
        body_text = page.run_js("return document.body?.textContent || ''")
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


def parse_timer(timer_str: str) -> int:
    """将倒计时字符串解析为秒数，如 '01:30:00' -> 5400"""
    try:
        parts = timer_str.strip().split(":")
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
    except Exception:
        pass
    return 0


def get_timer_text(page) -> str:
    try:
        return page.run_js(
            "return document.querySelector('.countdown-time')?.textContent?.trim() || ''"
        ) or ""
    except Exception:
        return ""


def attempt_vote(page, username: str) -> tuple[bool, str, str | None]:
    log(f"打开投票页面: {VOTE_URL}")
    page.get(VOTE_URL)
    time.sleep(5)

    try:
        actual_url = page.url
        log(f"实际 URL: {actual_url}")
    except Exception:
        pass

    try:
        body = page.run_js("return document.body?.textContent || ''")
        if "blocked" in body.lower() or "access denied" in body.lower():
            sc = screenshot(page, "blocked.png")
            return False, "blocked", sc
    except Exception:
        pass

    timer_before = get_timer_text(page)
    timer_before_secs = parse_timer(timer_before)
    log(f"投票前倒计时: {timer_before} ({timer_before_secs}s)")

    # 填写用户名
    try:
        name_input = None
        for sel in ["css:input[name='voter_name']", "css:input[placeholder*='Steve']", "css:input[type='text']", "css:input"]:
            try:
                name_input = page.ele(sel, timeout=3)
                if name_input:
                    log(f"找到输入框: {sel}")
                    break
            except Exception:
                pass
        if name_input:
            name_input.clear()
            name_input.input(username)
            log(f"已填写用户名: {username}")
        else:
            log("未找到用户名输入框", "WARN")
    except Exception as e:
        log(f"填写用户名失败: {e}", "WARN")

    screenshot(page, "before_vote.png")

    # 找到投票按钮
    vote_btn = None
    for selector in ["css:.vote-btn", "css:button.vote-btn", "css:button:contains('Vote')", "css:button:contains('ADD')", "css:button:contains('90')"]:
        try:
            vote_btn = page.ele(selector, timeout=3)
            if vote_btn:
                log(f"找到投票按钮: {selector}")
                break
        except Exception:
            pass

    if not vote_btn:
        try:
            for btn in page.eles("tag:button"):
                text = btn.text or ""
                if any(kw in text.upper() for kw in ["ADD 90", "90 MIN", "VOTE"]):
                    vote_btn = btn
                    log(f"找到投票按钮 (by text): {text[:50]}")
                    break
        except Exception:
            pass

    if not vote_btn:
        try:
            html = page.run_js("return document.body?.innerHTML?.substring(0, 5000) || ''")
            log(f"页面 HTML (前5000字符):\n{html}", "WARN")
        except Exception:
            pass
        log("未找到投票按钮!", "ERROR")
        return False, "unknown", screenshot(page, "no_button.png")

    try:
        log("点击投票按钮...")
        vote_btn.click()
        time.sleep(3)
    except Exception as e:
        log(f"点击投票按钮失败: {e}", "WARN")
        return False, "unknown", None

    # 等待 Turnstile（严格检测）
    turnstile_ok = wait_for_turnstile_token(page, timeout=90)

    if not turnstile_ok:
        sc = screenshot(page, "turnstile_failed.png")
        log("Turnstile 未通过，投票无法完成")
        return False, "turnstile_failed", sc

    log("Turnstile 已通过，等待表单提交...")
    time.sleep(10)

    sc_after = screenshot(page, "after_vote.png")
    result = check_vote_result(page)

    timer_after = get_timer_text(page)
    timer_after_secs = parse_timer(timer_after)
    log(f"投票后倒计时: {timer_after} ({timer_after_secs}s)")

    # 验证：倒计时是否增加了至少 60 分钟（3600秒）
    timer_diff = timer_after_secs - timer_before_secs
    log(f"倒计时变化: {timer_diff}s")

    if result == "success":
        return True, "success", sc_after
    elif result == "cooldown":
        return False, "cooldown", sc_after
    elif result == "blocked":
        return False, "blocked", sc_after
    else:
        # 只有倒计时增加了至少 60 分钟才算成功
        if timer_diff > 3600:
            log(f"倒计时增加了 {timer_diff}s，判定为成功")
            return True, "success", sc_after
        elif timer_diff > 0:
            log(f"倒计时只增加了 {timer_diff}s（可能是正常刷新），判定为未成功")
            return False, "unknown", sc_after
        else:
            log("倒计时未增加，投票未生效")
            return False, "unknown", sc_after


def screenshot(page, name: str) -> str | None:
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    path = os.path.join(SCREENSHOT_DIR, name)
    try:
        page.get_screenshot(path=path)
        log(f"截图已保存: {path}")
        return path
    except Exception as e:
        log(f"截图失败: {e}", "WARN")
        return None


def main():
    tg_token = os.environ.get("TG_BOT_TOKEN", "")
    tg_chat_id = os.environ.get("TG_CHAT_ID", "")

    log("=" * 50)
    log("Gaming4Free Auto Vote (DrissionPage + xvfb)")
    log("=" * 50)

    page = None
    for attempt in range(1, MAX_RETRIES + 1):
        log(f"\n--- 第 {attempt}/{MAX_RETRIES} 次尝试 ---")
        username = random_username()
        log(f"用户名: {username}")

        try:
            if page is None:
                page = create_browser()

            success, status, sc_path = attempt_vote(page, username)

            if success:
                log("✅ 投票成功！")
                srv = get_server_status()
                caption = build_caption("success", username, server_info=srv)
                send_tg_photo(tg_token, tg_chat_id, sc_path, caption)
                try:
                    page.quit()
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
                    page.quit()
                except Exception:
                    pass
                page = None
                restart_warp()
                time.sleep(5)
                continue

            log("❓ 未知结果，换 IP 重试...")
            try:
                page.quit()
            except Exception:
                pass
            page = None
            restart_warp()
            time.sleep(5)

        except Exception as e:
            log(f"异常: {e}", "ERROR")
            try:
                if page:
                    page.quit()
            except Exception:
                pass
            page = None
            restart_warp()
            time.sleep(5)

    log("❌ 所有重试都失败")
    caption = build_caption("failure", "N/A", str(MAX_RETRIES) + " 次重试均失败")
    send_tg_message(tg_token, tg_chat_id, caption)
    return 1


if __name__ == "__main__":
    sys.exit(main())
