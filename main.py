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
    print("---- 开始执行鉴权与登录检测 ----")
    cookie = os.environ.get('PTERODACTYL_COOKIE')
    email = os.environ.get('PTERODACTYL_EMAIL')
    pw = os.environ.get('PTERODACTYL_PASSWORD')

    if cookie:
        print("📦 正在注入保存的 Cookie...")
        c1 = {'name': COOKIE_NAME, 'value': cookie, 'domain': '.panel.godlike.host', 'path': '/', 'expires': int(time.time()) + 31536000, 'httpOnly': True, 'secure': True, 'sameSite': 'Lax'}
        c2 = c1.copy(); c2['domain'] = 'ultra.panel.godlike.host'
        page.context.add_cookies([c1, c2])

    print(f"🌐 访问目标控制台: {SERVER_URL}")
    page.goto(SERVER_URL, wait_until="domcontentloaded")
    
    print("⏳ 等待页面渲染和加载弹窗 (10秒)...")
    page.wait_for_timeout(10000)

    login_modal = page.get_by_text("Login to continue", exact=False).first
    if not login_modal.is_visible() and "login" not in page.url.lower(): 
        print("✅ 10秒内未检测到登录弹窗，Cookie 依然有效，已是登录状态！")
        return True

    print("⚠️ 检测到需要重新登录，准备自动输入账号密码...")
    if not (email and pw): return False

    try:
        page.get_by_text("login/password", exact=False).first.click(timeout=10000)
        page.wait_for_timeout(1500)
        page.get_by_placeholder("Username or Email", exact=False).fill(email)
        page.get_by_placeholder("Password", exact=True).fill(pw)
        page.locator('button:has-text("Login")').first.click()
        page.wait_for_timeout(8000)

        if page.get_by_text("Login to continue", exact=False).first.is_visible():
            page.screenshot(path="login_fail.png", full_page=True)
            send_tg_message("❌ 账号密码登录失败，请检查凭据。", "login_fail.png")
            return False
            
        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
        print("✅ 账号密码就地登录流程完成！")
        return True
    except Exception as e:
        print(f"❌ 登录过程中发生报错: {e}")
        page.screenshot(path="login_error.png", full_page=True)
        send_tg_message(f"❌ 登录代码异常: {e}", "login_error.png")
        return False

# ==================== 状态检查 ====================
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

# ==================== 核心续期任务 ====================
def add_time_task(page):
    try:
        if page.url != SERVER_URL:
            page.goto(SERVER_URL, wait_until="domcontentloaded")

        ensure_server_online(page)

        print("\n---- 开始执行时长续期 ----")
        
        # 【终极防御】：15秒智能弹窗巡逻雷达
        print("⏳ 开启智能弹窗巡逻模式 (持续15秒)，清剿一切拦路虎...")
        for i in range(1, 16):
            page.wait_for_timeout(1000)
            try:
                # 1. 拦截新手教程 (Skip for now)
                skip_btn = page.get_by_text("Skip for now", exact=False).first
                if skip_btn.is_visible():
                    print(f"  [{i}s] 💥 发现 '新手教程' 弹窗，点击 'Skip for now'...")
                    skip_btn.click(force=True)
                    page.wait_for_timeout(1500)
                
                # 2. 拦截 50% Off 广告 (I'm fine with waiting)
                ad_btn = page.get_by_text("fine with waiting", exact=False).first
                if ad_btn.is_visible():
                    print(f"  [{i}s] 💥 发现 '50% Off' 广告，点击底部拒绝...")
                    ad_btn.click(force=True)
                    page.wait_for_timeout(1500)
                    
                # 3. 拦截类似 Edit Server 的 Cancel 按钮
                cancel_btn = page.locator('button:has-text("Cancel")').first
                if cancel_btn.is_visible():
                    print(f"  [{i}s] 💥 发现 'Cancel' 按钮，关闭设置弹窗...")
                    cancel_btn.click(force=True)
                    page.wait_for_timeout(1500)
            except Exception:
                pass

        print("✅ 巡逻结束。盲发 ESC 键清理残余焦点...")
        for _ in range(3): 
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)

        print("步骤1: 查找并点击 'Renew' 按钮...")
        renew_button = page.locator('button:has-text("Renew")').first
        renew_button.wait_for(state='visible', timeout=15000)
        renew_button.scroll_into_view_if_needed()
        try:
            renew_button.click(timeout=5000)
        except:
            print("⚠️ 物理点击受阻，尝试无视遮盖强制点击...")
            renew_button.click(force=True)
            
        print("...已成功点击 'Renew'。")
        page.wait_for_timeout(3000)

        print("步骤2: 查找并点击 'Watch' 广告按钮...")
        watch_ad_button = page.locator('button:has-text("Watch")').first
        watch_ad_button.wait_for(state='visible', timeout=15000)
        watch_ad_button.scroll_into_view_if_needed()
        watch_ad_button.click(force=True)
        print("...已成功点击观看广告按钮。")

        print("步骤3: 正在后台静默播放广告 (等待125秒)...")
        time.sleep(125)
        
        print("🔄 刷新页面获取最新时长...")
        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(8000)
        
        page.screenshot(path="final_success.png", full_page=True)
        send_tg_message(f"🎉 Godlike 续期任务已执行完毕！\n时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", "final_success.png")
        return True

    except Exception as e:
        print(f"❌ 任务失败: {e}")
        page.screenshot(path="error.png", full_page=True)
        send_tg_message("❌ 续期任务失败，请检查截图情况。", "error.png")
        return False

def main():
    print("🚀 启动 Godlike 自动化任务...", flush=True)
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
