import os
import shutil
import json
from playwright.async_api import async_playwright

# ==========================================
# CẤU HÌNH ĐƯỜNG DẪN IXBROWSER CORE
# ==========================================
# Tự động trỏ vào thư mục 142-0102 nằm ở gốc dự án (ngang hàng với thư mục engine)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IXBROWSER_EXE_PATH = os.path.join(BASE_DIR, "142-0102", "chrome.exe")

def clean_chrome_cache(profile_path):
    """
    Dọn dẹp rác cache để trình duyệt nhẹ hơn.
    Cũng xóa Local State / stale lock gây crash khi mở profile lấy từ ixBrowser.
    """
    root_garbage = ["Crashpad", "Safe Browsing", "GrShaderCache", "ShaderCache", "GraphiteDawnCache"]
    default_dir = os.path.join(profile_path, "Default")
    default_garbage = [
        "Cache", "Code Cache", "GPUCache", "DawnCache",
        "DawnGraphiteCache", "DawnWebGPUCache", "Trace"
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

    # --- Xóa file ixBrowser-specific gây crash STATUS_BREAKPOINT ---
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
    """Đọc proxy từ proxy_map.json theo profile_id (ưu tiên hơn proxy.txt)"""
    profile_id   = os.path.basename(profile_folder_path)
    profiles_dir = os.path.dirname(profile_folder_path)
    proxy_map_path = os.path.join(profiles_dir, "proxy_map.json")
    try:
        with open(proxy_map_path, "r", encoding="utf-8") as f:
            return json.load(f).get(profile_id, "")
    except:
        return ""

async def init_driver_from_profile_playwright(profile_folder_path, log_callback=print):
    """
    Hàm Playwright ASYNC khởi tạo ixBrowser — dùng cho batch processing và Setup UI.
    Hỗ trợ proxy tự động từ proxy_map.json.
    """
    if not os.path.exists(profile_folder_path):
        os.makedirs(profile_folder_path, exist_ok=True)
        log_callback(f"⚠️ Folder chưa tồn tại, đã tạo mới: {profile_folder_path}")

    folder_name = os.path.basename(profile_folder_path)

    log_callback(f"🧹 Đang dọn dẹp Cache cũ cho profile ixBrowser: {folder_name}...")
    clean_preferences_bloat(profile_folder_path)
    clean_chrome_cache(profile_folder_path)

    log_callback(f"🚀 Khởi động ixBrowser Profile bằng Playwright: {folder_name}")

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

    # --- Đọc proxy từ proxy_map.json ---
    proxy_config = None
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
        launch_kwargs = dict(
            user_data_dir=profile_folder_path,
            executable_path=IXBROWSER_EXE_PATH,
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
        return context

    except Exception as e:
        log_callback(f"❌ Lỗi khởi tạo ixBrowser Playwright ({folder_name}): {e}")
        return None
