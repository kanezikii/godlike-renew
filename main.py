import os
import time
import signal
import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from datetime import datetime

# --- 动态配置项 ---
SERVER_URL = os.environ.get('SERVER_URL', '').strip()
LOGIN_URL = "https://panel.godlike.host/auth/login"
COOKIE_NAME = "remember_web_59ba36addc2b2f9401580f014c7f58ea4e30989d"
TASK_TIMEOUT_SECONDS = 400

def send_tg_message(text, image_path=None):
    bot_token = os.environ.get('TG_BOT_TOKEN', '').strip()
    chat_id = os.environ.get('TG_CHAT_ID', '').strip()
    email_display = os.environ.get('PTERODACTYL_EMAIL', '未知账号').strip()
    
    full_text = f"👤 账号: {email_display}\n{text}"
    if not bot_token or not chat_id: return
    try:
        if image_path and os.path.exists(image_path):
            url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
            with open(image_path, 'rb') as photo:
                requests.post(url, data={'chat_id': chat_id, 'caption': full_text}, files={'photo': photo})
        else:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            requests.post(url, data={'chat_id': chat_id, 'text': full_text})
    except: pass

class TaskTimeoutError(Exception): pass
def timeout_handler(signum, frame): raise TaskTimeoutError("任务超时")
if os.name != 'nt': signal.signal(signal.SIGALRM, timeout_handler)

def verify_proxy_ip(page):
    proxy = os.environ.get('SOCKS5_PROXY', '').strip()
    if not proxy: return True
    try:
        page.goto("https://api.ipify.org?format=text", timeout=20000)
        print(f"✅ 当前出口 IP: {page.locator('body').inner_text().strip()}")
        return True
    except: return False

def login_with_playwright(page):
    email = os.environ.get('PTERODACTYL_EMAIL', '').strip()
    pw = os.environ.get('PTERODACTYL_PASSWORD', '').strip()
    print(f"🌐 正在为账号 {email} 执行登录...")
    
    page.goto(SERVER_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(10000)

    if not page.get_by_text("Login to continue", exact=False).first.is_visible() and "login" not in page.url.lower(): 
        print("✅ 检测到已处于登录状态。")
        return True

    try:
        page.get_by_text("login/password", exact=False).first.click(timeout=10000)
        page.wait_for_timeout(1500)
        page.get_by_placeholder("Username or Email", exact=False).fill(email)
        page.get_by_placeholder("Password", exact=True).fill(pw)
        page.locator('button:has-text("Login")').first.click()
        page.wait_for_timeout(8000)
        
        print(f"🚀 登录完毕，强制跳转至专属控制台: {SERVER_URL}")
        page.goto(SERVER_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
        return True
    except Exception as e:
        print(f"❌ 登录失败: {e}")
        return False

def add_time_task(page):
    try:
        if page.url != SERVER_URL:
            page.goto(SERVER_URL, wait_until="domcontentloaded")
            page.wait_for_timeout(5000)

        print("\n---- 开始执行时长续期巡逻 ----")
        page.wait_for_timeout(8000)
        
        # 【修复】：换回最强弹窗杀手逻辑
        print("⏳ 巡逻清理杂鱼弹窗...")
        for _ in range(3):
            try:
                skip_btn = page.locator('button:has-text("Skip for now")').first
                if skip_btn.is_visible(timeout=1000): skip_btn.click()
            except: pass
            
            try:
                ad_text = page.get_by_text("fine with waiting", exact=False).first
                if ad_text.is_visible(timeout=1000):
                    ad_btn = page.locator('button').filter(has=ad_text).first
                    if ad_btn.is_visible(): ad_btn.click()
                    else: ad_text.click(force=True)
            except: pass
            
            try:
                cancel_btn = page.locator('button:has-text("Cancel"):visible').first
                if cancel_btn.is_visible(timeout=1000): cancel_btn.click()
            except: pass

        for _ in range(2): page.keyboard.press("Escape")
        page.wait_for_timeout(2000)

        # 【新增】：智能检测面板冷却时间
        print("🔍 检查续期冷却状态...")
        try:
            cooldown_text = page.get_by_text("Video will be available in", exact=False).first
            if cooldown_text.is_visible(timeout=3000):
                cd_time = cooldown_text.inner_text()
                print(f"⚠️ 服务器处于冷却中: {cd_time}")
                page.screenshot(path="cooldown.png", full_page=True)
                send_tg_message(f"⏳ 任务跳过：服务器续期处于冷却中。\n面板提示: {cd_time}", "cooldown.png")
                return True # 优雅退出，不当作错误处理
        except:
            pass

        print("步骤1: 寻找并点击 'Renew'...")
        renew_btn = page.locator('button:has-text("Renew"):visible').first
        renew_btn.wait_for(state='visible', timeout=15000)
        renew_btn.click()
        page.wait_for_timeout(3000)

        print("步骤2: 唤出并点击红色播放按钮...")
        watch_btn = page.locator('button:has-text("Watch"):visible').first
        watch_btn.wait_for(state='visible', timeout=10000)
        watch_btn.click()
        
        page.wait_for_timeout(6000)
        try:
            yt_play = page.frame_locator("iframe").locator(".ytp-large-play-button")
            yt_play.click(timeout=8000)
            print("💥 成功点下红色播放键！")
        except:
            page.mouse.click(1920/2, 1080/2)
        
        print("步骤3: 强制挂机 250 秒播放广告...")
        time.sleep(250)
        
        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(8000)
        page.screenshot(path="final_result.png", full_page=True)
        send_tg_message("🎉 续期任务已完成，请核对截图时间。", "final_result.png")
        return True
    except Exception as e:
        page.screenshot(path="error.png", full_page=True)
        send_tg_message(f"❌ 任务出错: {e}", "error.png")
        return False

def main():
    if not SERVER_URL or not SERVER_URL.startswith("http"):
        print(f"❌ 致命错误: SERVER_URL 缺失或格式不合法！当前值: '{SERVER_URL}'")
        return
    
    proxy = os.environ.get('SOCKS5_PROXY', '').strip()
    args = ["--disable-blink-features=AutomationControlled"]
    if proxy: args.append(f"--proxy-server={proxy}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=args)
        context = browser.new_context(viewport={"width": 1920, "height": 1080}, user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36")
        page = context.new_page()
        try:
            if not verify_proxy_ip(page): pass
            if login_with_playwright(page):
                if os.name != 'nt': signal.alarm(TASK_TIMEOUT_SECONDS)
                add_time_task(page)
        finally:
            browser.close()

if __name__ == "__main__":
    main()
