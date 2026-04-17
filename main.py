import os
import time
import signal
import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from datetime import datetime

# --- 配置项 ---
SERVER_URL = "https://ultra.panel.godlike.host/server/1211ba98"
LOGIN_URL = "https://panel.godlike.host/auth/login"
COOKIE_NAME = "remember_web_59ba36addc2b2f9401580f014c7f58ea4e30989d"
TASK_TIMEOUT_SECONDS = 300

# ==================== TG 通知模块 ====================
def send_tg_message(text, image_path=None):
    bot_token = os.environ.get('TG_BOT_TOKEN')
    chat_id = os.environ.get('TG_CHAT_ID')
    if not bot_token or not chat_id:
        print("⚠️ 未配置 TG 变量，跳过通知。")
        return
    try:
        if image_path and os.path.exists(image_path):
            url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
            with open(image_path, 'rb') as photo:
                requests.post(url, data={'chat_id': chat_id, 'caption': text}, files={'photo': photo})
        else:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            requests.post(url, data={'chat_id': chat_id, 'text': text})
        print("✅ TG 通知发送完毕。")
    except Exception as e:
        print(f"❌ TG 发送失败: {e}")

# ==================== 超时处理 ====================
class TaskTimeoutError(Exception): pass
def timeout_handler(signum, frame): raise TaskTimeoutError("任务超时")
if os.name != 'nt': signal.signal(signal.SIGALRM, timeout_handler)

# ==================== 验证代理 ====================
def verify_proxy_ip(page):
    socks5_proxy = os.environ.get('SOCKS5_PROXY')
    if not socks5_proxy: return True
    try:
        page.goto("https://api.ipify.org?format=text", wait_until="domcontentloaded", timeout=20000)
        current_ip = page.locator("body").inner_text().strip()
        print(f"✅ 当前出口 IP: {current_ip}")
        return True
    except Exception as e:
        print(f"❌ 代理异常: {e}")
        return False

# ==================== 登录逻辑 ====================
def login_with_playwright(page):
    cookie = os.environ.get('PTERODACTYL_COOKIE')
    email = os.environ.get('PTERODACTYL_EMAIL')
    pw = os.environ.get('PTERODACTYL_PASSWORD')

    if cookie:
        c1 = {'name': COOKIE_NAME, 'value': cookie, 'domain': '.panel.godlike.host', 'path': '/', 'expires': int(time.time()) + 31536000, 'httpOnly': True, 'secure': True, 'sameSite': 'Lax'}
        c2 = c1.copy(); c2['domain'] = 'ultra.panel.godlike.host'
        page.context.add_cookies([c1, c2])

    page.goto(SERVER_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    if not page.get_by_text("Login to continue", exact=False).first.is_visible(): return True

    try:
        page.get_by_text("login/password", exact=False).first.click()
        page.get_by_placeholder("Username or Email", exact=False).fill(email)
        page.get_by_placeholder("Password", exact=True).fill(pw)
        page.locator('button:has-text("Login")').first.click()
        page.wait_for_timeout(5000)
        page.reload(wait_until="domcontentloaded")
        return True
    except Exception as e:
        print(f"❌ 登录报错: {e}")
        return False

# ==================== 核心续期任务 ====================
def add_time_task(page):
    try:
        # 强制清理：直接从 DOM 层面杀掉所有潜在的弹窗遮罩
        print("🪄 正在清理页面残留遮罩和弹窗...")
        page.evaluate("""
            () => {
                const selectors = ['.modal', '.backdrop', '[class*="Overlay"]', '[class*="Modal"]'];
                selectors.forEach(s => {
                    document.querySelectorAll(s).forEach(el => el.remove());
                });
                document.body.style.overflow = 'auto';
            }
        """)
        
        # 再次尝试物理按键清除
        for _ in range(2): page.keyboard.press("Escape")

        print("步骤1: 查找并点击 'Renew' 按钮...")
        renew_button = page.locator('button:has-text("Renew")').first
        renew_button.wait_for(state='visible', timeout=15000)
        
        # 物理模拟：先移动再点击
        renew_button.hover()
        try:
            renew_button.click(timeout=5000)
        except:
            print("⚠️ 物理点击受阻，尝试强制穿透...")
            renew_button.click(force=True)
            
        print("...已成功点击 'Renew'。")
        page.wait_for_timeout(3000)

        print("步骤2: 查找并点击 'Watch' 广告按钮...")
        watch_ad_button = page.locator('button:has-text("Watch")').first
        watch_ad_button.wait_for(state='visible', timeout=15000)
        watch_ad_button.hover()
        watch_ad_button.click(force=True)
        print("...已成功点击观看广告按钮。")

        print("步骤3: 正在观看广告 (等待125秒)...")
        time.sleep(125)
        
        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
        
        page.screenshot(path="final_success.png", full_page=True)
        send_tg_message(f"🎉 Godlike 续期任务已执行完毕！\n请检查截图中的剩余时间。", "final_success.png")
        return True

    except Exception as e:
        page.screenshot(path="error.png", full_page=True)
        send_tg_message(f"❌ 任务失败: {e}", "error.png")
        return False

def main():
    print("启动 Godlike 自动化任务...", flush=True)
    proxy = os.environ.get('SOCKS5_PROXY')
    launch_args = [f"--proxy-server={proxy}"] if proxy else []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=launch_args)
        page = browser.new_page()
        try:
            if not verify_proxy_ip(page): exit(1)
            if not login_with_playwright(page): exit(1)
            if os.name != 'nt': signal.alarm(TASK_TIMEOUT_SECONDS)
            add_time_task(page)
        finally:
            browser.close()

if __name__ == "__main__":
    main()
