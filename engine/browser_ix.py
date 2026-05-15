import os
import threading
import shutil
import undetected_chromedriver as uc
import json

# ==========================================
# CẤU HÌNH ĐƯỜNG DẪN IXBROWSER CORE
# ==========================================
# Tự động trỏ vào thư mục 142-0102 nằm ở gốc dự án (ngang hàng với thư mục engine)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IXBROWSER_EXE_PATH = os.path.join(BASE_DIR, "142-0102", "chrome.exe")
IX_DRIVER_PATH = os.path.join(BASE_DIR, "142-0102", "chromedriver.exe")

DRIVER_INIT_LOCK = threading.Lock()

def create_proxy_extension(proxy_string, dest_folder):
    """
    Tạo extension proxy ảo cho Chrome
    Đọc proxy dạng IP:Port hoặc IP:Port:User:Pass
    """
    parts = proxy_string.strip().split(':')
    if len(parts) == 4:
        host, port, user, password = parts
    elif len(parts) == 2:
        host, port = parts
        user, password = "", ""
    else:
        return None

    manifest_json = """
    {
        "version": "1.0.0",
        "manifest_version": 3,
        "name": "Chrome Proxy",
        "permissions": [
            "proxy",
            "tabs",
            "unlimitedStorage",
            "storage",
            "webRequest",
            "webRequestAuthProvider"
        ],
        "host_permissions": [
            "<all_urls>"
        ],
        "background": {
            "service_worker": "background.js"
        },
        "minimum_chrome_version":"88.0.0"
    }
    """

    background_js = """
    var config = {
            mode: "fixed_servers",
            rules: {
              singleProxy: {
                scheme: "http",
                host: "%s",
                port: parseInt(%s)
              },
              bypassList: ["localhost"]
            }
          };

    chrome.proxy.settings.set({value: config, scope: "regular"}, function() {});

    function callbackFn(details) {
        return {
            authCredentials: {
                username: "%s",
                password: "%s"
            }
        };
    }

    chrome.webRequest.onAuthRequired.addListener(
                callbackFn,
                {urls: ["<all_urls>"]},
                ['blocking']
    );
    """ % (host, port, user, password)

    ext_path = os.path.join(dest_folder, "proxy_ext_ix")
    os.makedirs(ext_path, exist_ok=True)
    with open(os.path.join(ext_path, "manifest.json"), "w", encoding="utf-8") as f:
        f.write(manifest_json)
    with open(os.path.join(ext_path, "background.js"), "w", encoding="utf-8") as f:
        f.write(background_js)
    return ext_path

def clean_chrome_cache(profile_path):
    """
    Dọn dẹp rác cache để trình duyệt nhẹ hơn
    """
    root_garbage = ["Crashpad", "Safe Browsing", "GrShaderCache", "ShaderCache"]
    default_dir = os.path.join(profile_path, "Default")
    default_garbage = [
        "Cache", "Code Cache", "GPUCache", "DawnCache", 
        "Service Worker", "File System", "IndexedDB", "Trace"
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


def init_driver_from_profile(profile_folder_path, log_callback=print):
    """
    Hàm khởi tạo Driver dành riêng cho profile của ixBrowser (Offline Mode)
    """
    if not os.path.exists(profile_folder_path):
        os.makedirs(profile_folder_path, exist_ok=True)
        log_callback(f"⚠️ Folder chưa tồn tại, đã tạo mới: {profile_folder_path}")

    folder_name = os.path.basename(profile_folder_path)
    
    log_callback(f"🧹 Đang dọn dẹp Cache cũ cho profile ixBrowser: {folder_name}...")
    clean_preferences_bloat(profile_folder_path)
    clean_chrome_cache(profile_folder_path)

    log_callback(f"🚀 Khởi động ixBrowser Profile: {folder_name}")

    options = uc.ChromeOptions()
    options.add_argument(f"--user-data-dir={profile_folder_path}")
    options.add_argument(f"--profile-directory=Default")
    
    # --- Cấu hình tối ưu & CHẶN CACHE ---
    options.add_argument("--disable-backgrounding-occluded-windows")
    options.add_argument("--disable-background-timer-throttling")
    options.add_argument("--disable-renderer-backgrounding")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-client-side-phishing-detection")
    options.add_argument('--no-first-run')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-popup-blocking')
    
    options.add_argument("--disk-cache-size=1") 
    options.add_argument("--media-cache-size=1") 
    options.add_argument("--disable-application-cache") 
    options.add_argument("--disable-gpu-shader-disk-cache") 
    options.add_argument("--ash-no-nudges") 
    
    options.page_load_strategy = 'eager'

    # --- TỰ ĐỘNG GẮN PROXY TỪ FILE proxy.txt ---
    proxy_txt_path = os.path.join(profile_folder_path, "proxy.txt")
    if os.path.exists(proxy_txt_path):
        try:
            with open(proxy_txt_path, "r", encoding="utf-8") as f:
                proxy_str = f.read().strip()
            if proxy_str:
                ext_path = create_proxy_extension(proxy_str, profile_folder_path)
                if ext_path:
                    options.add_argument(f"--load-extension={ext_path}")
                    log_callback(f"🌐 Đã gắn Proxy ảo từ file proxy.txt")
        except Exception as e:
            log_callback(f"⚠️ Không thể đọc/gắn proxy.txt: {e}")

    # --- TẠO THƯ MỤC DOWNLOADS ---
    profile_dl_dir = os.path.join(profile_folder_path, "Downloads")
    if os.path.exists(profile_dl_dir):
        try: shutil.rmtree(profile_dl_dir)
        except: pass
    os.makedirs(profile_dl_dir, exist_ok=True)

    prefs = {
        "download.default_directory": profile_dl_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "profile.default_content_settings.popups": 0,
        "profile.content_settings.exceptions.automatic_downloads.*.setting": 1, 
        "profile.default_content_setting_values.automatic_downloads": 1,        
        "safebrowsing.enabled": True, 
        "safebrowsing.disable_download_protection": True,
        "browser.cache.disk.enable": False,
        "browser.cache.memory.enable": False,
        "browser.cache.offline.enable": False,
        "network.http.use-cache": False,
    }
    options.add_experimental_option("prefs", prefs)

    with DRIVER_INIT_LOCK:
        try:
            # SỬ DỤNG NHÂN CỦA IXBROWSER
            driver = uc.Chrome(
                options=options,
                browser_executable_path=IXBROWSER_EXE_PATH,
                driver_executable_path=IX_DRIVER_PATH,
                use_subprocess=True,
                headless=False,
            )
            driver.execute_cdp_cmd("Page.setDownloadBehavior", {
                "behavior": "allow",
                "downloadPath": profile_dl_dir
            })
            driver.my_download_dir = profile_dl_dir 
            
            return driver
            
        except Exception as e:
            log_callback(f"❌ Lỗi khởi tạo ixBrowser ({folder_name}): {e}")
            return None
