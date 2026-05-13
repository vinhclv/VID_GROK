import os
import shutil 
import json
import asyncio
# SỬA LẠI: Import bản Async của Playwright
from playwright.async_api import async_playwright 
from config import ORBITA_PATH

# ĐÃ XÓA DRIVER_INIT_LOCK VÌ KHÔNG CẦN THIẾT VÀ GÂY LỖI CHO ASYNC LOOP

def clean_chrome_cache(profile_path):
    """
    Dọn dẹp triệt để rác, bao gồm cả Crashpad, File System và IndexedDB.
    """
    root_garbage = ["Crashpad", "Safe Browsing", "GrShaderCache", "ShaderCache"]
    default_dir = os.path.join(profile_path, "Default")
    default_garbage = [
        "Cache", "Code Cache", "GPUCache", "DawnCache", 
        "Service Worker", "File System", "IndexedDB", 
        "Local Extension Settings", "Trace"
    ]
    files_to_delete = ["chrome_debug.log"]

    print(f"🧹 Bắt đầu dọn dẹp sâu profile: {os.path.basename(profile_path)}...")

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

    for file in files_to_delete:
        full_path = os.path.join(profile_path, file)
        if os.path.exists(full_path):
            try: os.remove(full_path)
            except: pass

    print("✨ Đã dọn dẹp xong.")


def clean_preferences_bloat(profile_path):
    """
    Hàm dọn dẹp file Preferences.
    """
    pref_file = os.path.join(profile_path, "Default", "Preferences")
    if not os.path.exists(pref_file): return

    try:
        file_size_mb = os.path.getsize(pref_file) / (1024 * 1024)
        if file_size_mb < 10: return 

        print(f"📉 Phát hiện file Preferences nặng {file_size_mb:.2f} MB. Đang nén lại...")

        with open(pref_file, 'r', encoding='utf-8', errors='ignore') as f:
            data = json.load(f)
        
        dirty = False

        if 'extensions' in data and 'settings' in data['extensions']:
            settings = data['extensions']['settings']
            for ext_id in list(settings.keys()):
                if len(str(settings[ext_id])) > 1024 * 1024: 
                    settings[ext_id] = {} 
                    dirty = True
                    print(f"   🧹 Đã reset data extension: {ext_id}")

        if 'devtools' in data:
            del data['devtools']
            dirty = True
        
        if dirty or file_size_mb > 50:
            with open(pref_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, separators=(',', ':'))
            print(f"✅ Đã tối ưu xong Preferences.")

    except Exception as e:
        print(f"⚠️ Lỗi nhẹ khi dọn Preferences: {e}")


async def init_driver_from_profile_playwright(profile_folder_path, log_callback=print):
    """
    Khởi tạo Browser Context bằng Playwright (Phiên bản Async CHUẨN).
    """
    if not os.path.exists(profile_folder_path):
        os.makedirs(profile_folder_path, exist_ok=True)
        log_callback(f"⚠️ Folder chưa tồn tại, đã tạo mới: {profile_folder_path}")

    folder_name = os.path.basename(profile_folder_path)
    
    log_callback(f"🧹 Đang dọn dẹp Cache cũ cho profile: {folder_name}...")
    clean_preferences_bloat(profile_folder_path)
    clean_chrome_cache(profile_folder_path)

    log_callback(f"🚀 Khởi động Orbita Profile bằng Playwright Async: {folder_name}")

    profile_dl_dir = os.path.join(profile_folder_path, "Downloads")
    if os.path.exists(profile_dl_dir):
        try: shutil.rmtree(profile_dl_dir)
        except: pass
    os.makedirs(profile_dl_dir, exist_ok=True)

    chrome_args = [
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
        "--disable-gpu-shader-disk-cache",
        "--ash-no-nudges"
    ]

    try:
        # SỬA LẠI: Dùng async_playwright và bắt buộc có chữ 'await'
        p = await async_playwright().start()
        
        # SỬA LẠI: Bắt buộc có chữ 'await' khi mở context
        context = await p.chromium.launch_persistent_context(
            user_data_dir=profile_folder_path,
            executable_path=ORBITA_PATH,
            headless=False,
            args=chrome_args,
            no_viewport=True,
            accept_downloads=True,
            downloads_path=profile_dl_dir,
        )
        context.my_download_dir = profile_dl_dir 
        context.playwright_instance = p  
        return context
        
    except Exception as e:
        log_callback(f"❌ Lỗi khởi tạo Playwright: {e}")
        return None