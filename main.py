import os
import time
import signal
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from datetime import datetime

# --- 配置项 ---
SERVER_URL = "https://ultra.panel.godlike.host/server/1211ba98"
LOGIN_URL = "https://panel.godlike.host/auth/login"
COOKIE_NAME = "remember_web_59ba36addc2b2f9401580f014c7f58ea4e30989d"
TASK_TIMEOUT_SECONDS = 300  # 5分钟

# --- 超时处理机制 ---
class TaskTimeoutError(Exception):
    """自定义任务超时异常"""
    pass

def timeout_handler(signum, frame):
    """超时信号处理函数"""
    raise TaskTimeoutError("任务执行时间超过设定的阈值")

if os.name != 'nt':
    signal.signal(signal.SIGALRM, timeout_handler)


# ==================== 功能1：验证代理出口 IP ====================
def verify_proxy_ip(page):
    socks5_proxy = os.environ.get('SOCKS5_PROXY')
    if not socks5_proxy:
        print("未设置 SOCKS5_PROXY，跳过代理 IP 验证，使用默认出口。")
        return True

    print("已启用 SOCKS5 代理，正在验证出口 IP...")
    try:
        page.goto("https://api.ipify.org?format=text", wait_until="domcontentloaded", timeout=20000)
        current_ip = page.locator("body").inner_text().strip()
        print(f"✅ 当前出口 IP 验证成功: {current_ip}")
        return True
    except Exception as e:
        print(f"❌ 代理 IP 验证失败，无法访问 ipify: {e}", flush=True)
        page.screenshot(path="proxy_verify_error.png")
        return False
# ==============================================================


# ==================== 功能2：就地登录逻辑 ====================
def login_with_playwright(page):
    """处理登录逻辑，直接在目标页面处理弹窗登录，彻底解决跨域失效问题。"""
    remember_web_cookie = os.environ.get('PTERODACTYL_COOKIE')
    pterodactyl_email = os.environ.get('PTERODACTYL_EMAIL')
    pterodactyl_password = os.environ.get('PTERODACTYL_PASSWORD')

    if remember_web_cookie:
        print("检测到 PTERODACTYL_COOKIE，尝试注入 Cookie...")
        session_cookie = {
            'name': COOKIE_NAME, 'value': remember_web_cookie, 'domain': '.panel.godlike.host',
            'path': '/', 'expires': int(time.time()) + 3600 * 24 * 365, 'httpOnly': True,
            'secure': True, 'sameSite': 'Lax'
        }
        # 双重注入，防止子域名跨域隔离
        session_cookie_ultra = session_cookie.copy()
        session_cookie_ultra['domain'] = 'ultra.panel.godlike.host'
        page.context.add_cookies([session_cookie, session_cookie_ultra])

    print(f"正在直接访问目标服务器页面: {SERVER_URL}")
    page.goto(SERVER_URL, wait_until="domcontentloaded")
    
    print("等待页面和验证组件加载 (3秒)...")
    page.wait_for_timeout(3000)

    login_modal = page.get_by_text("Login to continue", exact=False).first
    if not login_modal.is_visible():
        print("✅ 页面未出现登录弹窗，Cookie 有效，当前已是登录状态！")
        return True

    print("⚠️ 出现登录弹窗，Cookie 失效或未覆盖。准备就在此页面使用账号密码...")
    if not (pterodactyl_email and pterodactyl_password):
        print("❌ 错误: 未提供 PTERODACTYL_EMAIL 或 PTERODACTYL_PASSWORD。", flush=True)
        return False

    try:
        print("正在点击 'Through login/password'...")
        page.get_by_text("login/password", exact=False).first.click(timeout=10000)
        page.wait_for_timeout(1000)

        print("等待表单元素 (使用所见即所得定位法)...")
        email_input = page.get_by_placeholder("Username or Email", exact=False).first
        password_input = page.get_by_placeholder("Password", exact=True).first
        
        email_input.wait_for(state='visible', timeout=10000)
        password_input.wait_for(state='visible', timeout=10000)
        
        print("填写账号密码...")
        email_input.fill(pterodactyl_email)
        password_input.fill(pterodactyl_password)
        
        print("点击登录提交按钮...")
        page.locator('button:has-text("Login")').first.click()

        print("等待弹窗消失...")
        try:
            login_modal.wait_for(state='hidden', timeout=15000)
            print("✅ 登录弹窗已消失！")
        except PlaywrightTimeoutError:
            if login_modal.is_visible():
                print("❌ 登录失败，弹窗依然存在。请检查账号密码，或是否触发了拦截。", flush=True)
                page.screenshot(path="login_fail_error.png")
                return False
        
        print("刷新页面同步状态...")
        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        
        if page.get_by_text("Login to continue", exact=False).first.is_visible():
            print("❌ 刷新后依然要求登录，会话未能维持。")
            page.screenshot(path="login_fail_refresh_error.png")
            return False

        print("✅ 账号密码就地登录流程完成！")
        return True

    except Exception as e:
        print(f"❌ 登录处理中发生错误: {e}", flush=True)
        page.screenshot(path="login_process_error.png")
        return False
# ==============================================================


# ==================== 功能3：检查并处理 offline 状态 ====================
def ensure_server_online(page):
    """续期前检查服务器状态，离线则点击启动。"""
    print("正在检查服务器运行状态...")
    try:
        status_selector = '[class*="ServerConsole___StyledSpan4"]'
        page.wait_for_selector(status_selector, timeout=15000)

        print("等待 WebSocket 连接完成...")
        start_time = time.time()
        while time.time() - start_time < 30:
            status_text = page.locator(status_selector).first.evaluate("el => el.childNodes[0].textContent.trim()")
            if status_text.lower() != "connecting...":
                break
            time.sleep(2)
        else:
            print("⚠️  WebSocket 连接超时（30秒），跳过状态检查，继续执行续期。", flush=True)
            return True

        print(f"当前服务器状态: {status_text}")

        if status_text.lower() == "offline":
            print("⚠️  检测到服务器状态为 Offline，正在查找 Start 按钮...")
            start_button = page.get_by_role("button", name="Start", exact=True)
            try:
                start_button.wait_for(state='visible', timeout=10000)
                start_button.click()
                print("✅ 已点击 Start 按钮，等待服务器启动...")
                time.sleep(15)  # 简单等待15秒让其启动，不阻挡后续续期
            except PlaywrightTimeoutError:
                print("❌ 未找到可点击的 Start 按钮，将尝试直接续期。", flush=True)
            return True
        else:
            print(f"✅ 服务器状态正常: {status_text}，无需启动。")
            return True

    except Exception as e:
        print(f"⚠️  检查状态时报错跳过: {e}，继续执行续期。", flush=True)
        return True
# ======================================================================


# ==================== 功能4：核心续期与广告清理 ====================
def add_time_task(page):
    """清理广告弹窗并执行增加服务器时长。"""
    try:
        print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始执行增加时长任务...")

        if page.url != SERVER_URL:
            page.goto(SERVER_URL, wait_until="domcontentloaded")

        ensure_server_online(page)

        # ---------------- 强力清除广告弹窗 (等满10秒防伏击) ----------------
        print("⏳ 扫描是否有促销广告弹窗 (等待10秒)...")
        try:
            # 专门等这行标题出现，最长等10秒
            ad_modal = page.get_by_text("Do you love Godlike", exact=False).first
            ad_modal.wait_for(state='visible', timeout=10000)
            print("💥 发现 50% Off 广告弹窗！启动三联绝杀清理程序...")
            
            # 方法 1：尝试找出类似右上角的 X 按钮并强点
            print(" -> [方法1] 尝试点击弹窗右上角 'X' 关闭按键...")
            close_buttons = page.locator('button:not(:has-text("Claim")):not(:has-text("Renew")):not(:has-text("Login"))')
            for i in range(close_buttons.count()):
                try:
                    close_buttons.nth(i).click(force=True, timeout=1000)
                except:
                    pass
            page.wait_for_timeout(1000)

            # 方法 2：尝试点击底部灰色拒绝文字
            if ad_modal.is_visible():
                try:
                    print(" -> [方法2] 尝试点击底部的 'I'm fine with waiting'...")
                    page.get_by_text("I'm fine with waiting", exact=False).first.click(force=True, timeout=2000)
                    page.wait_for_timeout(1000)
                except:
                    pass

            # 方法 3：盲点背景和狂按 ESC
            if ad_modal.is_visible():
                print(" -> [方法3] 尝试按下 ESC 键和盲点背景左上角...")
                page.keyboard.press("Escape")
                page.mouse.click(10, 10)  # 点一下页面最边缘的背景遮罩
                page.wait_for_timeout(1000)
                
        except PlaywrightTimeoutError:
            print("✅ 10秒内未检测到广告弹窗，安全通过。")
        # ---------------------------------------------------------------

        # 步骤 1：寻找 Renew
        print("步骤1: 查找并点击 'Renew' 按钮...")
        renew_button = page.locator('button:has-text("Renew")').first
        # 注意这里用的是 attached（只要在DOM里就算），无视遮挡
        renew_button.wait_for(state='attached', timeout=30000)
        try:
            renew_button.click(force=True, timeout=3000)
        except Exception:
            print(" -> 常规点击受阻，使用 JS 降维打击强制点击 'Renew'...")
            # 浏览器底层 JavaScript 直接执行点击事件，任何遮罩都会被无视
            renew_button.evaluate("node => node.click()")
        print("...已成功点击 'Renew'。")

        # 步骤 2：寻找 Watch 广告按钮
        print("步骤2: 查找并点击 'Watch' (观看广告) 按钮...")
        watch_ad_button = page.locator('button:has-text("Watch")').first
        watch_ad_button.wait_for(state='attached', timeout=30000)
        try:
            watch_ad_button.click(force=True, timeout=3000)
        except Exception:
            print(" -> 常规点击受阻，使用 JS 降维打击强制点击 'Watch'...")
            watch_ad_button.evaluate("node => node.click()")
        print("...已成功点击观看广告按钮。")

        print("步骤3: 开始固定等待2分钟 (等待广告后台播放完毕)...")
        time.sleep(120)
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✅ 已等待2分钟，本轮自动化续期圆满完成！")

        return True

    except PlaywrightTimeoutError as e:
        print(f"❌ 任务执行超时: 未在规定时间内找到核心元素。", flush=True)
        page.screenshot(path="task_element_timeout_error.png")
        return False
    except Exception as e:
        print(f"❌ 任务执行过程中发生未知错误: {e}", flush=True)
        page.screenshot(path="task_general_error.png")
        return False


# ==================== 主函数 ====================
def main():
    print("启动 Godlike 自动化任务（防弹窗强化版）...", flush=True)

    socks5_proxy = os.environ.get('SOCKS5_PROXY')
    launch_args = []
    if socks5_proxy:
        local_proxy = socks5_proxy
        launch_args = [f"--proxy-server={local_proxy}"]
        print(f"已启用 SOCKS5 代理，浏览器出口: {local_proxy}")
    else:
        print("未启用代理，使用 GitHub Actions 默认出口 IP。")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=launch_args)
        page = browser.new_page()
        page.set_default_timeout(60000)
        print("浏览器启动成功。", flush=True)

        try:
            if not verify_proxy_ip(page):
                print("代理 IP 验证失败，程序终止。", flush=True)
                exit(1)

            if not login_with_playwright(page):
                print("登录失败，程序终止。", flush=True)
                exit(1)

            if os.name != 'nt':
                signal.alarm(TASK_TIMEOUT_SECONDS)

            print("\n----------------------------------------------------")
            success = add_time_task(page)

            if os.name != 'nt':
                signal.alarm(0)

            if success:
                print("本轮任务成功完成。", flush=True)
            else:
                print("本轮任务失败。", flush=True)
                exit(1)

        except TaskTimeoutError as e:
            print(f"🔥🔥🔥 任务强制超时（{TASK_TIMEOUT_SECONDS}秒）！🔥🔥🔥", flush=True)
            print(f"错误信息: {e}", flush=True)
            page.screenshot(path="task_force_timeout_error.png")
            exit(1)
        except Exception as e:
            print(f"主程序发生严重错误: {e}", flush=True)
            page.screenshot(path="main_critical_error.png")
            exit(1)
        finally:
            print("关闭浏览器，程序结束。", flush=True)
            browser.close()

if __name__ == "__main__":
    main()
    print("脚本执行完毕。")
    exit(0)
