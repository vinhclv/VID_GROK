import os
import shutil
import json
from playwright.async_api import async_playwright
import config

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
    Hàm Playwright ASYNC khởi tạo Trình duyệt — hỗ trợ song song ixBrowser và GoLogin.
    Chỉ gắn proxy cho ixBrowser theo đúng quy ước thực tế.
    """
    global _permissions_fixed
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

    folder_name = os.path.basename(profile_folder_path)
    browser_type = config.global_settings["system"].get("browser_type", "ixBrowser")

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

    # --- Chỉ nạp và gắn proxy cho chế độ ixBrowser ---
    proxy_config = None
    if browser_type == "ixBrowser":
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

        # Rút gọn tên profile nếu quá dài để hiển thị rõ phần đầu và phần đuôi (tail) trên thanh tiêu đề Chrome
        if len(folder_name) > 12:
            display_name = f"{folder_name[:4]}...{folder_name[-8:]}"
        else:
            display_name = folder_name

        # Tự động chèn script đổi tiêu đề Tab chứa tên profile để người dùng phân biệt các cửa sổ trình duyệt khi chạy đa luồng
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

        return context

    except Exception as e:
        log_callback(f"❌ Lỗi khởi tạo ixBrowser Playwright ({folder_name}): {e}")
        return None
