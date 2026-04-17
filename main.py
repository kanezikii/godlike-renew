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
TASK_TIMEOUT_SECONDS = 300  # 5分钟

# ==================== TG 通知模块 ====================
def send_tg_message(text, image_path=None):
    """向 Telegram 发送消息和截图"""
    bot_token = os.environ.get('TG_BOT_TOKEN')
    chat_id = os.environ.get('TG_CHAT_ID')
    
    if not bot_token or not chat_id:
        print("未配置 TG_BOT_TOKEN 或 TG_CHAT_ID，跳过 TG 通知。")
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
        print(f"❌ TG 通知发送失败: {e}")

# ==================== 超时处理机制 ====================
class TaskTimeoutError(Exception): pass

def timeout_handler(signum, frame):
    raise TaskTimeoutError("任务执行时间超过设定的阈值")

if os.name != 'nt':
    signal.signal(signal.SIGALRM, timeout_handler)

# ==================== 功能1：验证代理出口 IP ====================
def verify_proxy_ip(page):
    socks5_proxy = os.environ.get('SOCKS5_PROXY')
    if not socks5_proxy: return True
    print("已启用 SOCKS5 代理，正在验证出口 IP...")
    try:
        page.goto("https://api.ipify.org?format=text", wait_until="domcontentloaded", timeout=20000)
        current_ip = page.locator("body").inner_text().strip()
        print(f"✅ 当前出口 IP: {current_ip}")
        return True
    except Exception as e:
        page.screenshot(path="proxy_error.png")
        send_tg_message(f"❌ 代理验证失败: {e}", "proxy_error.png")
        return False

# ==================== 功能2：就地登录逻辑 ====================
def login_with_playwright(page):
    remember_web_cookie = os.environ.get('PTERODACTYL_COOKIE')
    pterodactyl_email = os.environ.get('PTERODACTYL_EMAIL')
    pterodactyl_password = os.environ.get('PTERODACTYL_PASSWORD')

    if remember_web_cookie:
        session_cookie = {
            'name': COOKIE_NAME, 'value': remember_web_cookie, 'domain': '.panel.godlike.host',
            'path': '/', 'expires': int(time.time()) + 3600 * 24 * 365, 'httpOnly': True, 'secure': True, 'sameSite': 'Lax'
        }
        session_cookie_ultra = session_cookie.copy()
        session_cookie_ultra['domain'] = 'ultra.panel.godlike.host'
        page.context.add_cookies([session_cookie, session_cookie_ultra])

    page.goto(SERVER_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(3000)

    login_modal = page.get_by_text("Login to continue", exact=False).first
    if not login_modal.is_visible(): return True

    if not (pterodactyl_email and pterodactyl_password): return False

    try:
        page.get_by_text("login/password", exact=False).first.click(timeout=10000)
        page.wait_for_timeout(1000)

        email_input = page.get_by_placeholder("Username or Email", exact=False).first
        password_input = page.get_by_placeholder("Password", exact=True).first
        email_input.wait_for(state='visible', timeout=10000)
        password_input.wait_for(state='visible', timeout=10000)
        
        email_input.fill(pterodactyl_email)
        password_input.fill(pterodactyl_password)
        page.locator('button:has-text("Login")').first.click()

        try:
            login_modal.wait_for(state='hidden', timeout=15000)
        except PlaywrightTimeoutError:
            if login_modal.is_visible():
                page.screenshot(path="login_fail.png")
                send_tg_message("❌ 登录失败，账号密码可能被拒绝。", "login_fail.png")
                return False
        
        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        return True

    except Exception as e:
        page.screenshot(path="login_error.png")
        send_tg_message(f"❌ 登录代码异常: {e}", "login_error.png")
        return False

# ==================== 功能3：检查在线状态 ====================
def ensure_server_online(page):
    try:
        status_selector = '[class*="ServerConsole___StyledSpan4"]'
        page.wait_for_selector(status_selector, timeout=15000)
        start_time = time.time()
        while time.time() - start_time < 30:
            status_text = page.locator(status_selector).first.evaluate("el => el.childNodes[0].textContent.trim()")
            if status_text.lower() != "connecting...": break
            time.sleep(2)
        else:
            return True

        if status_text.lower() == "offline":
            start_button = page.get_by_role("button", name="Start", exact=True)
            try:
                start_button.wait_for(state='visible', timeout=10000)
                start_button.click()
                time.sleep(15)
            except PlaywrightTimeoutError: pass
        return True
    except Exception: return True

# ==================== 功能4：核心续期 ====================
def add_time_task(page):
    try:
        if page.url != SERVER_URL:
            page.goto(SERVER_URL, wait_until="domcontentloaded")

        ensure_server_online(page)

        # ---------------- 强力全自动清屏连招 (专治各种新旧弹窗) ----------------
        print("⏳ 扫描是否有弹窗遮挡 (广告、设置界面等)...")
        page.wait_for_timeout(3000)  # 等待异步组件和各种莫名其妙的弹窗加载

        # 招式1：连环 ESC 键
        print(" -> [招式1] 连按 ESC 键尝试退出模态框...")
        for _ in range(3):
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)

        # 招式2：针对包含 "Cancel" 按钮的设置弹窗 (如 Edit Server)
        try:
            cancel_btns = page.locator('button:has-text("Cancel")')
            if cancel_btns.count() > 0 and cancel_btns.first.is_visible(timeout=1000):
                print(" -> [招式2] 发现 'Cancel' 按钮，正在关闭设置弹窗...")
                cancel_btns.first.click(force=True)
                page.wait_for_timeout(1000)
        except Exception: pass

        # 招式3：针对 50% Off 广告弹窗的特定文字
        try:
            ad_texts = page.get_by_text("I'm fine with waiting", exact=False)
            if ad_texts.count() > 0 and ad_texts.first.is_visible(timeout=1000):
                print(" -> [招式3] 发现促销广告，正在点击关闭...")
                ad_texts.first.click(force=True)
                page.wait_for_timeout(1000)
        except Exception: pass

        # 招式4：盲点屏幕左上角边缘，解除焦点锁定
        print(" -> [招式4] 点击背景空白处解除焦点锁定...")
        page.mouse.click(10, 10)
        page.wait_for_timeout(1500)
        # -------------------------------------------------------------------

        print("步骤1: 查找并点击 'Renew' 按钮...")
        renew_button = page.locator('button:has-text("Renew")').first
        renew_button.wait_for(state='visible', timeout=15000)
        renew_button.click(force=True)
        print("...已成功点击 'Renew'。")

        print("步骤2: 查找并点击 'Watch' 广告按钮...")
        watch_ad_button = page.locator('button:has-text("Watch")').first
        watch_ad_button.wait_for(state='visible', timeout=15000)
        watch_ad_button.click(force=True)
        print("...已成功点击观看广告按钮。")

        print("步骤3: 正在观看广告 (等待120秒)...")
        time.sleep(120)
        
        # 截取最终续期完毕后的成果图
        page.screenshot(path="final_success.png", full_page=True)
        send_tg_message(f"🎉 Godlike 续期成功！\n时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", "final_success.png")
        return True

    except PlaywrightTimeoutError as e:
        page.screenshot(path="task_timeout.png", full_page=True)
        send_tg_message("❌ 续期找按钮超时被卡住，请查看截图排查原因。", "task_timeout.png")
        return False
    except Exception as e:
        page.screenshot(path="task_error.png", full_page=True)
        send_tg_message(f"❌ 续期未知异常: {e}", "task_error.png")
        return False

# ==================== 主函数 ====================
def main():
    print("启动 Godlike 自动化任务（终极防弹窗版）...", flush=True)

    socks5_proxy = os.environ.get('SOCKS5_PROXY')
    launch_args = [f"--proxy-server={socks5_proxy}"] if socks5_proxy else []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=launch_args)
        page = browser.new_page()
        page.set_default_timeout(60000)

        try:
            if not verify_proxy_ip(page): exit(1)
            if not login_with_playwright(page): exit(1)

            if os.name != 'nt': signal.alarm(TASK_TIMEOUT_SECONDS)

            success = add_time_task(page)

            if os.name != 'nt': signal.alarm(0)

            if not success: exit(1)

        except TaskTimeoutError as e:
            page.screenshot(path="force_timeout.png")
            send_tg_message("🔥🔥🔥 任务被强制掐断 (超5分钟)，面板可能处于死循环加载。", "force_timeout.png")
            exit(1)
        except Exception as e:
            page.screenshot(path="main_crash.png")
            send_tg_message(f"🚨 主程序崩溃: {e}", "main_crash.png")
            exit(1)
        finally:
            browser.close()

if __name__ == "__main__":
    main()
