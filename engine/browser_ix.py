import os
import shutil
import json
import asyncio
import threading
from playwright.async_api import async_playwright
import config

_ix_api_open_lock = threading.Lock()

# ==========================================
# CẤU HÌNH ĐƯỜNG DẪN IXBROWSER & GOLOGIN CORE
# ==========================================
# Tự động trỏ vào thư mục 142-0102 nằm ở gốc dự án (ngang hàng với thư mục engine)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IXBROWSER_EXE_PATH = os.path.join(BASE_DIR, "142-0102", "chrome.exe")
ORBITA_EXE_PATH = config.ORBITA_PATH

# Flag để đảm bảo chỉ tự động phân quyền Sandbox 1 lần duy nhất mỗi lần chạy ứng dụng
_permissions_fixed = False

def clean_chrome_cache(profile_path):
    """
    Dọn dẹp rác cache để trình duyệt nhẹ hơn.
    Cũng xóa Local State / stale lock gây crash khi mở profile lấy từ ixBrowser.
    """
    root_garbage = ["Crashpad", "Safe Browsing", "GrShaderCache", "ShaderCache", "GraphiteDawnCache", "lock_cookies"]
    default_dir = os.path.join(profile_path, "Default")
    default_garbage = [
        "Cache", "Code Cache", "GPUCache", "DawnCache",
        "DawnGraphiteCache", "DawnWebGPUCache", "Trace", "Sync Data"
    ]

    for folder in root_garbage:
        full_path = os.path.join(profile_path, folder)
        if os.path.exists(full_path):
            try: shutil.rmtree(full_path, ignore_errors=True)
            except: pass

    for folder in default_garbage:
        full_path = os.path.join(default_dir, folder)
        if os.path.exists(full_path):
            try: shutil.rmtree(full_path, ignore_errors=True)
            except: pass

    # Cookie/Login data được bảo lưu bằng cách giữ nguyên Local State chứa khóa DPAPI.
    # File Local State của ixBrowser cũ đã được xóa một lần duy nhất lúc Import.
    ix_crash_files = ["Last Browser", "Last Version", "Variations", "extension_setting.txt"]
    for fname in ix_crash_files:
        fpath = os.path.join(profile_path, fname)
        if os.path.exists(fpath):
            try: os.remove(fpath)
            except: pass

    # --- Xóa stale lock files (còn sót sau khi ixBrowser đóng profile) ---
    stale_locks = [
        os.path.join(default_dir, "LOCK"),
        os.path.join(profile_path, "Singleton"),
        os.path.join(profile_path, "SingletonLock"),
        os.path.join(profile_path, "SingletonCookie"),
    ]
    for lpath in stale_locks:
        if os.path.exists(lpath):
            try: os.remove(lpath)
            except: pass

def clean_preferences_bloat(profile_path):
    """
    Hàm dọn dẹp file Preferences nếu nó phình to.
    """
    pref_file = os.path.join(profile_path, "Default", "Preferences")
    
    if not os.path.exists(pref_file): return

    try:
        file_size_mb = os.path.getsize(pref_file) / (1024 * 1024)
        if file_size_mb < 10: 
            return 

        print(f"📉 Phát hiện file Preferences nặng {file_size_mb:.2f} MB. Đang nén lại...")

        with open(pref_file, 'r', encoding='utf-8', errors='ignore') as f:
            data = json.load(f)
        
        dirty = False 

        if 'devtools' in data:
            del data['devtools']
            dirty = True
        
        if dirty or file_size_mb > 50:
            with open(pref_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, separators=(',', ':'))
            print(f"✅ Đã tối ưu xong Preferences.")

    except Exception as e:
        print(f"⚠️ Lỗi nhẹ khi dọn Preferences: {e}")

def _load_proxy_from_map(profile_folder_path):
    """Đọc proxy từ ProfileStateManager theo profile_id (ưu tiên hơn proxy.txt)"""
    profile_id = os.path.basename(profile_folder_path)
    from utils.profile_state import ProfileStateManager
    return ProfileStateManager().get_proxy(profile_id)

async def init_driver_from_profile_playwright(profile_folder_path, log_callback=print):
    """
    Hàm Playwright ASYNC khởi tạo Trình duyệt — hỗ trợ song song ixBrowser (Cục bộ), GoLogin (Cục bộ) và ixBrowser (Local API).
    """
    global _permissions_fixed
    browser_type = config.global_settings["system"].get("browser_type", "ixBrowser")
    folder_name = os.path.basename(profile_folder_path)

    # =========================================================================
    # CHẾ ĐỘ 1: IXBROWSER LOCAL API (Kết nối qua Local API & CDP)
    # =========================================================================
    if browser_type == "ixBrowser (Local API)":
        parts = folder_name.split(" - ")
        if not parts[0].isdigit():
            log_callback(f"❌ Tên profile không hợp lệ cho ixBrowser API: {folder_name}")
            return None
        profile_id = int(parts[0])

        from utils.ixbrowser_service import IxBrowserService
        
        # Đồng bộ hóa toàn bộ tiến trình mở và kết nối để tránh nghẽn CPU/CDP port khi click mở liên tục
        with _ix_api_open_lock:
            log_callback(f"🌐 Đang gọi ixBrowser API để mở profile {profile_id}...")
            success, err, ws_url = IxBrowserService.open_profile(profile_id)
            if not success:
                log_callback(f"❌ ixBrowser API báo lỗi: {err}")
                return None
                
            try:
                p = await async_playwright().start()
                log_callback(f"🔌 Kết nối Playwright tới CDP: {ws_url}")
                
                browser = None
                cdp_retries = 3
                while cdp_retries > 0:
                    try:
                        browser = await p.chromium.connect_over_cdp(ws_url)
                        break
                    except Exception as cdp_err:
                        cdp_retries -= 1
                        if cdp_retries == 0:
                            raise cdp_err
                        log_callback(f"⚠️ Cổng CDP chưa sẵn sàng ({cdp_err}). Đang thử kết nối lại sau 1.5s...")
                        await asyncio.sleep(1.5)
                
                if not browser.contexts:
                    log_callback("❌ Trình duyệt không có context nào")
                    await browser.close()
                    await p.stop()
                    return None
                    
                context = browser.contexts[0]
                context.browser_instance = browser
                context.playwright_instance = p
                context.ix_profile_id = profile_id
                
                # Rút gọn tên hiển thị
                display_name = parts[1] if len(parts) > 1 else str(profile_id)
                if len(display_name) > 12:
                    display_name = f"{display_name[:4]}...{display_name[-8:]}"
                
                init_js = f"""
                (function() {{
                    const profileName = "{display_name}";
                    function updateTitle() {{
                        if (document.title && !document.title.startsWith('[' + profileName + ']')) {{
                            document.title = '[' + profileName + '] ' + document.title;
                        }}
                    }}
                    setInterval(updateTitle, 1000);
                    const observer = new MutationObserver(updateTitle);
                    observer.observe(document.documentElement, {{ childList: true, subtree: true }});
                    updateTitle();
                }})();
                """
                await context.add_init_script(init_js)

                # Tự động dọn dẹp các tab cũ tồn đọng từ phiên trước và đẩy cửa sổ lên trước mặt
                try:
                    clean_page = await context.new_page()
                    for old_page in list(context.pages):
                        if old_page != clean_page:
                            try:
                                await old_page.close()
                            except:
                                pass

                    await clean_page.bring_to_front()
                    # Khôi phục trạng thái cửa sổ về bình thường (unminimize) nếu đang ẩn dưới Taskbar
                    client = await context.new_cdp_session(clean_page)
                    win_info = await client.send("Browser.getWindowForTarget")
                    win_id = win_info.get("windowId")
                    if win_id:
                        await client.send("Browser.setWindowBounds", {
                            "windowId": win_id,
                            "bounds": {"windowState": "normal"}
                        })
                except Exception as ex_clean:
                    log_callback(f"⚠️ Lỗi nhỏ khi dọn dẹp tab: {ex_clean}")

                return context
                
            except Exception as e:
                log_callback(f"❌ Lỗi khởi chạy/kết nối qua ixBrowser API: {e}")
                return None

    # =========================================================================
    # CHẾ ĐỘ 2: KHỞI CHẠY CỤC BỘ (Offline folders - ixBrowser hoặc GoLogin)
    # =========================================================================
    if not _permissions_fixed and os.name == 'nt':
        try:
            import subprocess
            # Tự động phân quyền thư mục 142-0102 (ixBrowser) và orbita-browser-141 (GoLogin)
            for path_name in ["142-0102", "orbita-browser-141"]:
                dir_path = os.path.join(BASE_DIR, path_name)
                if os.path.exists(dir_path):
                    log_callback(f"🛡️ Đang tự động phân quyền Sandbox cho thư mục {path_name}...")
                    subprocess.run(
                        f'icacls "{dir_path}" /grant *S-1-15-2-1:(OI)(CI)(RX) /T',
                        shell=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
            _permissions_fixed = True
        except Exception as ex:
            log_callback(f"⚠️ Lỗi phân quyền tự động: {ex}")

    if not os.path.exists(profile_folder_path):
        os.makedirs(profile_folder_path, exist_ok=True)
        log_callback(f"⚠️ Folder chưa tồn tại, đã tạo mới: {profile_folder_path}")

    log_callback(f"🧹 Đang dọn dẹp Cache cũ cho profile {browser_type}: {folder_name}...")
    clean_preferences_bloat(profile_folder_path)
    clean_chrome_cache(profile_folder_path)

    log_callback(f"🚀 Khởi động {browser_type} Profile bằng Playwright: {folder_name}")

    profile_dl_dir = os.path.join(profile_folder_path, "Downloads")
    if os.path.exists(profile_dl_dir):
        try: shutil.rmtree(profile_dl_dir)
        except: pass
    os.makedirs(profile_dl_dir, exist_ok=True)

    chrome_args = [
        "--profile-directory=Default",
        "--disable-blink-features=AutomationControlled",
        "--disable-backgrounding-occluded-windows",
        "--disable-background-timer-throttling",
        "--disable-renderer-backgrounding",
        "--disable-client-side-phishing-detection",
        "--no-first-run",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-popup-blocking",
        "--disk-cache-size=1",
        "--media-cache-size=1",
        "--disable-application-cache",
        "--disable-gpu",                   # Fix crash STATUS_BREAKPOINT do GPU driver lỗi
        "--disable-gpu-shader-disk-cache",
        "--ash-no-nudges",
    ]

    # --- Nạp và gắn proxy cho cả hai chế độ chạy cục bộ ---
    proxy_config = None
    if browser_type in ["ixBrowser", "GoLogin"]:
        proxy_str = _load_proxy_from_map(profile_folder_path)
        if not proxy_str:
            proxy_txt = os.path.join(profile_folder_path, "proxy.txt")
            if os.path.exists(proxy_txt):
                try:
                    with open(proxy_txt, "r", encoding="utf-8") as f:
                        proxy_str = f.read().strip()
                except: pass

        if proxy_str:
            parts = proxy_str.strip().split(":")
            if len(parts) == 4:
                host, port, user, pw = parts
                proxy_config = {"server": f"http://{host}:{port}", "username": user, "password": pw}
            elif len(parts) == 2:
                host, port = parts
                proxy_config = {"server": f"http://{host}:{port}"}
            if proxy_config:
                log_callback(f"🌐 Đã gắn Proxy: {parts[0]}:***")

    try:
        p = await async_playwright().start()
        exe_path = ORBITA_EXE_PATH if browser_type == "GoLogin" else IXBROWSER_EXE_PATH
        
        launch_kwargs = dict(
            user_data_dir=profile_folder_path,
            executable_path=exe_path,
            headless=False,
            args=chrome_args,
            no_viewport=True,
            accept_downloads=True,
            downloads_path=profile_dl_dir,
        )
        if proxy_config:
            launch_kwargs["proxy"] = proxy_config

        context = await p.chromium.launch_persistent_context(**launch_kwargs)
        context.my_download_dir = profile_folder_path
        context.playwright_instance = p

        # Rút gọn tên profile
        if len(folder_name) > 12:
            display_name = f"{folder_name[:4]}...{folder_name[-8:]}"
        else:
            display_name = folder_name

        init_js = f"""
        (function() {{
            const profileName = "{display_name}";
            function updateTitle() {{
                if (document.title && !document.title.startsWith('[' + profileName + ']')) {{
                    document.title = '[' + profileName + '] ' + document.title;
                }}
            }}
            setInterval(updateTitle, 1000);
            const observer = new MutationObserver(updateTitle);
            observer.observe(document.documentElement, {{ childList: true, subtree: true }});
            updateTitle();
        }})();
        """
        await context.add_init_script(init_js)

        # Dọn dẹp tab cũ tồn đọng từ phiên làm việc trước
        try:
            clean_page = await context.new_page()
            for old_page in list(context.pages):
                if old_page != clean_page:
                    try:
                        await old_page.close()
                    except:
                        pass
        except:
            pass

        return context

    except Exception as e:
        log_callback(f"❌ Lỗi khởi tạo trình duyệt ({folder_name}): {e}")
        return None


async def close_context_playwright(context, log_callback=print):
    """
    Dọn dẹp trình duyệt sạch sẽ: đóng CDP connection, tắt playwright,
    và gửi lệnh API đóng profile tới ixBrowser nếu sử dụng Local API.
    """
    if not context:
        return
    try:
        ix_profile_id = getattr(context, "ix_profile_id", None)
        log_callback("🧹 Đang dọn dẹp trình duyệt Playwright...")
        
        try: await context.close()
        except: pass
        
        if hasattr(context, "browser_instance"):
            try: await context.browser_instance.close()
            except: pass
            
        if hasattr(context, "playwright_instance"):
            try: await context.playwright_instance.stop()
            except: pass
            
        if ix_profile_id:
            from utils.ixbrowser_service import IxBrowserService
            log_callback(f"🔌 Đang gọi ixBrowser API để đóng profile {ix_profile_id}...")
            success, err = IxBrowserService.close_profile(ix_profile_id)
            if not success:
                log_callback(f"⚠️ Lỗi gửi yêu cầu đóng profile tới ixBrowser: {err}")
    except Exception as e:
        log_callback(f"⚠️ Lỗi dọn dẹp trình duyệt: {e}")


def fix_sandbox_permissions_async(log_callback=print):
    """
    Chạy icacls trong luồng phụ (background thread) để tránh làm treo ứng dụng lúc khởi động.
    """
    def run_fix():
        global _permissions_fixed
        if _permissions_fixed or os.name != 'nt':
            return
        try:
            import subprocess
            for path_name in ["142-0102", "orbita-browser-141"]:
                dir_path = os.path.join(BASE_DIR, path_name)
                if os.path.exists(dir_path):
                    log_callback(f"🛡️ [Background] Đang phân quyền Sandbox cho thư mục {path_name}...")
                    subprocess.run(
                        f'icacls "{dir_path}" /grant *S-1-15-2-1:(OI)(CI)(RX) /T',
                        shell=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
            _permissions_fixed = True
            log_callback("🛡️ [Background] Hoàn tất phân quyền Sandbox!")
        except Exception as ex:
            log_callback(f"⚠️ [Background] Lỗi phân quyền Sandbox: {ex}")

    import threading
    threading.Thread(target=run_fix, daemon=True).start()

