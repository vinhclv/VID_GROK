import os
import threading
import shutil # <--- [MỚI] Cần import cái này để xóa folder rác
import undetected_chromedriver as uc
import random 
import json

from config import ORBITA_PATH, DRIVER_PATH


DRIVER_INIT_LOCK = threading.Lock()
def clean_chrome_cache(profile_path):
    """
    Dọn dẹp triệt để rác, bao gồm cả Crashpad, File System và IndexedDB.
    """
    # 1. Các folder rác nằm ngay ngoài thư mục gốc profile (User Data)
    root_garbage = [
        "Crashpad",          # [QUAN TRỌNG] Nơi chứa file dump báo lỗi (rất nặng)
        "Safe Browsing",     # Dữ liệu check web độc hại (tải lại được)
        "GrShaderCache",     # Cache đồ họa
        "ShaderCache", 
    ]
    
    # 2. Các folder rác nằm trong thư mục Default (User Data/Default)
    default_dir = os.path.join(profile_path, "Default")
    
    default_garbage = [
        "Cache",
        "Code Cache",
        "GPUCache",
        "DawnCache",         # Cache WebGPU mới
        "Service Worker",    # [QUAN TRỌNG] Nơi lưu script chạy ngầm
        "File System",       # [QUAN TRỌNG] Nơi web app lưu video tạm
        "IndexedDB",         # [CẢNH BÁO] Lưu data web. Xóa cái này sạch nhất nhưng KÉM BỀN LOGOUT hơn. 
                             # Nếu bị logout, hãy comment dòng này lại.
        "Local Extension Settings", # Rác extension
        "Trace",             # Log trace
    ]

    # Các file rác lẻ tẻ
    files_to_delete = [
        "chrome_debug.log",  # Log debug (có thể lên tới vài GB)
    ]

    print(f"🧹 Bắt đầu dọn dẹp sâu profile: {os.path.basename(profile_path)}...")

    # Xóa folder ở root
    for folder in root_garbage:
        full_path = os.path.join(profile_path, folder)
        if os.path.exists(full_path):
            try:
                shutil.rmtree(full_path, ignore_errors=True)
            except: pass

    # Xóa folder trong Default
    for folder in default_garbage:
        full_path = os.path.join(default_dir, folder)
        if os.path.exists(full_path):
            try:
                shutil.rmtree(full_path, ignore_errors=True)
            except: pass

    # Xóa file lẻ
    for file in files_to_delete:
        full_path = os.path.join(profile_path, file)
        if os.path.exists(full_path):
            try:
                os.remove(full_path)
            except: pass

    print("✨ Đã dọn dẹp xong.")

def clean_preferences_bloat(profile_path):
    """
    Hàm dọn dẹp file Preferences nếu nó phình to quá 50MB.
    Đặc biệt xử lý Extension Orbita bị lỗi log.
    """
    pref_file = os.path.join(profile_path, "Default", "Preferences")
    
    if not os.path.exists(pref_file): return

    try:
        # 1. Chỉ xử lý nếu file lớn hơn 10MB (để tối ưu tốc độ)
        file_size_mb = os.path.getsize(pref_file) / (1024 * 1024)
        if file_size_mb < 10: 
            return 

        print(f"📉 Phát hiện file Preferences nặng {file_size_mb:.2f} MB. Đang nén lại...")

        with open(pref_file, 'r', encoding='utf-8', errors='ignore') as f:
            data = json.load(f)
        
        dirty = False # Cờ đánh dấu xem có thay đổi gì không

        # 2. Xử lý Extension rác (Orbita/Gologin)
        if 'extensions' in data and 'settings' in data['extensions']:
            settings = data['extensions']['settings']
            # ID của Orbita/Gologin và các extension hay gây lỗi
            target_ids = [
                "fignfifoniblkonapihmkfakmlgkbkcf", # Orbita
                # Thêm ID extension khác nếu sau này bị lại
            ]
            
            # Quét extension nào nặng > 1MB thì reset
            for ext_id in list(settings.keys()):
                # Check size string log extension
                if len(str(settings[ext_id])) > 1024 * 1024: # > 1MB text
                    settings[ext_id] = {} # Reset về rỗng
                    dirty = True
                    print(f"   🧹 Đã reset data extension: {ext_id}")

        # 3. Xóa DevTools & Metrics rác
        if 'devtools' in data:
            del data['devtools']
            dirty = True
        
        # 4. Lưu lại nếu có thay đổi
        if dirty or file_size_mb > 50: # Luôn lưu lại để nén dòng (remove whitespace)
            with open(pref_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, separators=(',', ':'))
            print(f"✅ Đã tối ưu xong Preferences.")

    except Exception as e:
        print(f"⚠️ Lỗi nhẹ khi dọn Preferences: {e}")

def init_driver_from_profile(profile_folder_path, log_callback=print):
    """
    Hàm khởi tạo Driver trực tiếp từ Folder Profile (Không cần JSON).
    """
    
    # 1. Xác định thư mục profile
    if not os.path.exists(profile_folder_path):
        os.makedirs(profile_folder_path, exist_ok=True)
        log_callback(f"⚠️ Folder chưa tồn tại, đã tạo mới: {profile_folder_path}")

    folder_name = os.path.basename(profile_folder_path)
    
    # --- GỌI HÀM DỌN DẸP TRƯỚC KHI MỞ ---
    log_callback(f"🧹 Đang dọn dẹp Cache cũ cho profile: {folder_name}...")
    clean_preferences_bloat(profile_folder_path)
    clean_chrome_cache(profile_folder_path)

    log_callback(f"🚀 Khởi động Orbita Profile: {folder_name}")

    # 2. CẤU HÌNH ORBITA OPTIONS
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
    
    # --- CHẶN CACHE MỚI ---
    options.add_argument("--disk-cache-size=1") 
    options.add_argument("--media-cache-size=1") 
    options.add_argument("--disable-application-cache") 
    options.add_argument("--disable-gpu-shader-disk-cache") 
    options.add_argument("--ash-no-nudges") 
    
    options.page_load_strategy = 'eager'

    # --- 3. CẤU HÌNH DOWNLOAD RIÊNG BIỆT (QUAN TRỌNG) ---
    # Tạo folder Downloads riêng cho từng profile
    profile_dl_dir = os.path.join(profile_folder_path, "Downloads")
    
    # Xóa sạch folder này mỗi lần khởi động để tránh rác cũ
    if os.path.exists(profile_dl_dir):
        try: shutil.rmtree(profile_dl_dir)
        except: pass
    os.makedirs(profile_dl_dir, exist_ok=True)

    # Cấu hình Prefs
    prefs = {
        "download.default_directory": profile_dl_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        
        # --- BỔ SUNG QUAN TRỌNG ĐỂ TẢI NHIỀU ẢNH ---
        "profile.default_content_settings.popups": 0,
        "profile.content_settings.exceptions.automatic_downloads.*.setting": 1, # Cho phép tải nhiều file
        "profile.default_content_setting_values.automatic_downloads": 1,        # 1 = Allow, 2 = Block
        
        # Tắt các lớp bảo vệ an toàn để không bị chặn file .exe hay ảnh lạ
        "safebrowsing.enabled": True, # Vẫn bật base nhưng tắt protection bên dưới
        "safebrowsing.disable_download_protection": True,
        
        # Tối ưu hiệu năng (giữ nguyên của bạn)
        "browser.cache.disk.enable": False,
        "browser.cache.memory.enable": False,
        "browser.cache.offline.enable": False,
        "network.http.use-cache": False,
    }
    options.add_experimental_option("prefs", prefs)

    # --- 4. KHỞI TẠO DRIVER ---
    with DRIVER_INIT_LOCK:
        try:
            driver = uc.Chrome(
                options=options,
                browser_executable_path=ORBITA_PATH,
                driver_executable_path=DRIVER_PATH,
                use_subprocess=True,
                headless=False,
            )
            driver.execute_cdp_cmd("Page.setDownloadBehavior", {
            "behavior": "allow",
            "downloadPath": profile_dl_dir
        })
            # --- [FIX LỖI QUAN TRỌNG] GÁN BIẾN SAU KHI TẠO DRIVER ---
            driver.my_download_dir = profile_dl_dir 
            
            return driver
            
        except Exception as e:
            log_callback(f"❌ Lỗi khởi tạo Chrome ({folder_name}): {e}")
            return None