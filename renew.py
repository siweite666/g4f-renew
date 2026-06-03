#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gaming4Free Public Page Renewal
通过 g4f.gg 公开续期页面投票续期，每次投票 +90 分钟。
Cloudflare Turnstile 通过浏览器自动化解决，IP 被封时用 WARP 换 IP 重试。
"""

import os
import sys
import time
import random
import subprocess
import requests

try:
    from DrissionPage import ChromiumPage, ChromiumOptions
except ImportError as e:
    print(f"[ERROR] DrissionPage 导入失败: {e}", flush=True)
    sys.exit(1)

# ============================================================
# 配置
# ============================================================
VOTE_URL = "https://g4f.gg/yousb"
MAX_RETRIES = 5             # 最大重试次数
SCREENSHOT_DIR = "output/screenshots"
SOCKS5_PROXY = os.environ.get("SOCKS5_PROXY", "")  # socks5://user:pass@host:port

# ============================================================
# 随机用户名
# ============================================================
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


# ============================================================
# 日志
# ============================================================
def log(msg: str, level: str = "INFO"):
    tag = {"INFO": "[INFO]", "WARN": "[WARN]", "ERROR": "[ERROR]"}.get(level, "[INFO]")
    print(f"{tag} {msg}", flush=True)


# ============================================================
# Telegram 通知
# ============================================================
def send_tg_message(token: str, chat_id: str, caption: str):
    if not token or not chat_id:
        log("未配置 TG_BOT_TOKEN / TG_CHAT_ID，跳过通知", "WARN")
        return
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": caption},
            timeout=30,
        )
        resp.raise_for_status()
        log("Telegram 通知已发送")
    except Exception as e:
        log(f"Telegram 通知失败: {e}", "ERROR")


def send_tg_photo(token: str, chat_id: str, photo_path: str, caption: str):
    if not token or not chat_id:
        return
    if photo_path and os.path.exists(photo_path):
        try:
            with open(photo_path, "rb") as f:
                resp = requests.post(
                    f"https://api.telegram.org/bot{token}/sendPhoto",
                    data={"chat_id": chat_id, "caption": caption},
                    files={"photo": f},
                    timeout=30,
                )
            resp.raise_for_status()
            log("Telegram 图片通知已发送")
            return
        except Exception as e:
            log(f"Telegram 图片通知失败: {e}", "WARN")
    send_tg_message(token, chat_id, caption)


# ============================================================
# Pterodactyl 服务器状态查询
# ============================================================
def get_server_status() -> dict | None:
    """查询服务器剩余时间等信息"""
    panel_url = "https://control.gaming4free.net"
    api_token = os.environ.get("PANEL_API_TOKEN", "")
    server_id = os.environ.get("SERVER_ID", "")
    if not api_token or not server_id:
        log("未配置 PANEL_API_TOKEN / SERVER_ID，跳过状态查询", "WARN")
        return None
    try:
        import subprocess
        auth_val = "Bearer " + api_token
        r = subprocess.run(
            ["curl", "-s", "-H", "Authorization: " + auth_val,
             "-H", "Accept: Application/vnd.pterodactyl.v1+json",
             panel_url + "/api/client/servers/" + server_id],
            capture_output=True, text=True, timeout=15
        )
        data = json.loads(r.stdout)
        attrs = data.get("attributes", {})
        limits = attrs.get("limits", {})
        renewal = attrs.get("renewal") or {}
        expires = renewal.get("expires_at", "")
        seconds_remaining = renewal.get("seconds_remaining", 0)
        is_suspended = renewal.get("is_suspended", False)
        return {
            "name": attrs.get("name", "unknown"),
            "memory": limits.get("memory", 0),
            "disk": limits.get("disk", 0),
            "cpu": limits.get("cpu", 0),
            "expires": expires,
            "seconds_remaining": seconds_remaining,
            "is_suspended": is_suspended,
            "node": attrs.get("node", ""),
            "suspended": attrs.get("is_suspended", False),
        }
    except Exception as e:
        log(f"查询服务器状态失败: {e}", "WARN")
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
        expires = server_info.get("expires", "")
        seconds_remaining = server_info.get("seconds_remaining", 0)
        if seconds_remaining > 0:
            hours = int(seconds_remaining // 3600)
            minutes = int((seconds_remaining % 3600) // 60)
            lines.append(f"  剩余: {hours}小时{minutes}分钟")
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
            lines.append(f"  ⚠️ 已暂停！")
        elif seconds_remaining <= 0:
            lines.append(f"  ⚠️ 已到期！")
        lines.append(f"  内存: {server_info.get('memory', 'N/A')}MB")
        lines.append(f"  磁盘: {server_info.get('disk', 'N/A')}MB")
        lines.append(f"  CPU: {server_info.get('cpu', 'N/A')}%")

    lines += ["", "Gaming4Free Auto Vote"]
    return "\n".join(lines)


# ============================================================
# 截图
# ============================================================
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

    cmds = [
        ["sudo", "warp-cli", "--accept-tos", "disconnect"],
        ["sudo", "warp-cli", "--accept-tos", "registration", "delete"],
        ["sudo", "warp-cli", "--accept-tos", "registration", "new"],
        ["sudo", "warp-cli", "--accept-tos", "connect"],
    ]
    for cmd in cmds:
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
    except Exception as e:
        log(f"获取新 IP 失败: {e}", "WARN")
        return False


# ============================================================
# 浏览器初始化
# ============================================================
def create_browser() -> ChromiumPage:
    co = ChromiumOptions()
    co.set_argument("--headless=new")
    co.set_argument("--no-sandbox")
    co.set_argument("--disable-dev-shm-usage")
    co.set_argument("--disable-gpu")
    co.set_argument("--window-size=1280,900")
    co.set_argument("--disable-blink-features=AutomationControlled")
    co.set_argument("--disable-infobars")
    # 代理
    if SOCKS5_PROXY:
        co.set_proxy(SOCKS5_PROXY)
        log(f"已配置代理: {SOCKS5_PROXY[:30]}...")
    # 使用随机 User-Agent
    ua = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        f"AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{random.randint(120, 130)}.0.0.0 Safari/537.36"
    )
    co.set_user_agent(ua)
    co.auto_port()
    return ChromiumPage(co)


# ============================================================
# Turnstile 检测
# ============================================================
def wait_for_turnstile(page, timeout: int = 30) -> bool:
    """等待 Cloudflare Turnstile 验证完成"""
    log("等待 Turnstile 加载...")
    start = time.time()
    while time.time() - start < timeout:
        try:
            # 检查 turnstile 是否已生成 token
            token = page.run_js(
                "return document.querySelector("
                "\"input[name='cf-turnstile-response']\")?.value || ''"
            )
            if token and len(token) > 20:
                log(f"Turnstile 已通过 (token 长度: {len(token)})")
                return True
        except Exception:
            pass

        # 检查是否有 turnstile iframe
        try:
            frames = page.get_frames()
            for frame in frames:
                url = frame.url or ""
                if "challenges.cloudflare" in url or "turnstile" in url:
                    log("检测到 Turnstile iframe，尝试交互...")
                    # 尝试点击 turnstile checkbox
                    try:
                        checkbox = frame.ele("css:input[type='checkbox']", timeout=2)
                        if checkbox:
                            checkbox.click()
                            time.sleep(3)
                    except Exception:
                        pass
                    # 也尝试点击 body
                    try:
                        body = frame.ele("css:body", timeout=2)
                        if body:
                            body.click()
                            time.sleep(2)
                    except Exception:
                        pass
        except Exception:
            pass

        time.sleep(2)

    log("Turnstile 超时未通过", "WARN")
    return False


def is_turnstile_blocked(page) -> bool:
    """检测是否被 Turnstile 封锁"""
    try:
        blocked = page.run_js("""
            const body = document.body?.textContent || '';
            return body.includes('blocked') || body.includes('Access denied') ||
                   body.includes('Error 1020') || body.includes('cf-error');
        """)
        return bool(blocked)
    except Exception:
        return False


# ============================================================
# 检测投票结果
# ============================================================
def check_vote_result(page) -> str:
    """检查投票结果: success / cooldown / blocked / unknown"""
    try:
        body_text = page.run_js("return document.body?.textContent || ''")
    except Exception:
        body_text = ""

    body_lower = body_text.lower()

    if "thank you" in body_lower or "voted" in body_lower or "success" in body_lower:
        return "success"
    if "cooldown" in body_lower or "wait" in body_lower or "too many" in body_lower:
        return "cooldown"
    if "blocked" in body_lower or "access denied" in body_lower:
        return "blocked"

    # 检查 URL 是否变化（成功后可能重定向）
    try:
        current_url = page.url
        if current_url and "vote" not in current_url.lower():
            # 可能是成功后重定向
            return "success"
    except Exception:
        pass

    return "unknown"


# ============================================================
# 主投票逻辑
# ============================================================
def attempt_vote(page, username: str) -> tuple[bool, str, str | None]:
    """
    尝试一次投票。
    返回 (成功, 状态, 截图路径)
    """
    log(f"打开投票页面: {VOTE_URL}")
    page.get(VOTE_URL)
    time.sleep(3)

    # 检查是否被封锁
    if is_turnstile_blocked(page):
        sc = screenshot(page, "blocked.png")
        return False, "blocked", sc

    # 填写用户名
    try:
        name_input = page.ele("css:input[name='voter_name']", timeout=10)
        if name_input:
            name_input.clear()
            name_input.input(username)
            log(f"已填写用户名: {username}")
    except Exception as e:
        log(f"填写用户名失败: {e}", "WARN")

    # 等待 Turnstile 验证
    turnstile_ok = wait_for_turnstile(page, timeout=45)

    if not turnstile_ok:
        # 尝试直接提交看看
        log("Turnstile 未通过，尝试直接提交...")

    # 截图
    sc = screenshot(page, "before_vote.png")

    # 点击投票按钮
    try:
        vote_btn = page.ele("css:.vote-btn", timeout=5)
        if vote_btn:
            log("点击投票按钮...")
            vote_btn.click()
            time.sleep(5)
        else:
            # 尝试直接提交表单
            log("未找到投票按钮，尝试提交表单...")
            page.run_js("document.getElementById('vote-form')?.submit()")
            time.sleep(5)
    except Exception as e:
        log(f"点击投票按钮失败: {e}", "WARN")
        try:
            page.run_js("document.getElementById('vote-form')?.submit()")
            time.sleep(5)
        except Exception:
            pass

    # 检查结果
    result = check_vote_result(page)
    sc_after = screenshot(page, "after_vote.png")

    if result == "success":
        return True, "success", sc_after
    elif result == "cooldown":
        return False, "cooldown", sc_after
    elif result == "blocked":
        return False, "blocked", sc_after
    else:
        return False, "unknown", sc_after


# ============================================================
# 主程序
# ============================================================
def main():
    tg_token = os.environ.get("TG_BOT_TOKEN", "")
    tg_chat_id = os.environ.get("TG_CHAT_ID", "")

    log("=" * 50)
    log("Gaming4Free Auto Vote")
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
                log("⏳ 冷却期，等待后重试...")
                srv = get_server_status()
                caption = build_caption("cooldown", username, server_info=srv)
                send_tg_photo(tg_token, tg_chat_id, sc_path, caption)
                # 冷却期不需要换 IP，等几分钟再试
                time.sleep(random.randint(60, 120))
                continue

            if status == "blocked":
                log("🔒 IP 被封锁，换 IP 重试...")
                try:
                    page.quit()
                except Exception:
                    pass
                page = None
                restart_warp()
                time.sleep(5)
                continue

            # unknown - 换 IP 重试
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

    # 所有重试都失败了
    log("❌ 所有重试都失败")
    caption = build_caption("failure", "N/A", f"{MAX_RETRIES} 次重试均失败")
    send_tg_message(tg_token, tg_chat_id, caption)
    return 1


if __name__ == "__main__":
    sys.exit(main())
