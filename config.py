import os
import json

# --- 1. ĐỊNH NGHĨA PATH & HẰNG SỐ ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PROFILES = os.path.join(BASE_DIR, "profiles")
DEFAULT_INPUT = os.path.join(BASE_DIR, "regen")
DEFAULT_OUTPUT = os.path.join(BASE_DIR, "assets")
SETTINGS_FILE = os.path.join(BASE_DIR, "settings.json")

# Đường dẫn Driver
ORBITA_PATH = os.path.join(BASE_DIR, "orbita-browser-141", "chrome.exe")
DRIVER_PATH = os.path.join(BASE_DIR, "orbita-browser-141", "chromedriver.exe")

# --- 2. CẤU HÌNH MẶC ĐỊNH ---
DEFAULT_CONFIG_DATA = {
    "system": {
        "max_threads": 3,
        "loop_limit": 5,
        "max_retries": 30,
        "wait_time": 30,
        "aspect_ratio": "16:9",
        "resolution": "720p"
    },
    "urls": {
        "gemini_url": "https://gemini.google.com",
        "videofx_url": "https://labs.google/fx/tools/video-fx"
    },
    "projects": [], # Danh sách dự án
    "gems": [],     # Danh sách Gem,
    # ---- THÊM ĐOẠN NÀY DÀNH CHO STANDARDIZE TAB ----
    "standardize": {
    "api_key": "YOUR_API_KEY_HERE",
    "languages": [
        {"name": "Anh", "code": "en"},
        {"name": "Hàn", "code": "ko"},
        {"name": "Trung", "code": "zh"},
        {"name": "Nhật", "code": "ja"},
        {"name": "Việt", "code": "vi"},
        {"name": "Pháp", "code": "fr"}
    ]
    }
}

# --- 3. BIẾN TOÀN CỤC (Lưu cấu hình trong RAM) ---
# Đây chính là "Single Source of Truth". Mọi nơi trong app sẽ đọc biến này.
global_settings = DEFAULT_CONFIG_DATA.copy()

# --- 4. CÁC HÀM XỬ LÝ ---

def load_config():
    """
    Đọc file settings.json và cập nhật vào biến global_settings.
    Chạy 1 lần duy nhất khi khởi động app.
    """
    global global_settings
    
    # 1. Reset về mặc định trước để đảm bảo đủ key
    current_config = json.loads(json.dumps(DEFAULT_CONFIG_DATA))

    # 2. Nếu file tồn tại, đọc và merge đè lên
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                saved_data = json.load(f)

            # Merge thông minh từng section
            if "system" in saved_data:
                current_config["system"].update(saved_data["system"])
            if "urls" in saved_data:
                current_config["urls"].update(saved_data["urls"])
            if "projects" in saved_data:
                current_config["projects"] = saved_data["projects"]
            if "gems" in saved_data:
                current_config["gems"] = saved_data["gems"]
                
        except Exception as e:
            print(f"⚠️ Lỗi đọc file config (Dùng mặc định): {e}")

    # 3. Cập nhật vào biến toàn cục
    global_settings = current_config
    return global_settings

def save_config():
    """
    Lưu nội dung từ biến global_settings (RAM) xuống file (Ổ cứng).
    """
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(global_settings, f, indent=4, ensure_ascii=False)
        print("💾 Đã lưu cấu hình xuống đĩa.")
        return True
    except Exception as e:
        print(f"❌ Lỗi lưu file config: {e}")
        return False

# --- 5. AUTO-LOAD ---
# Dòng này cực quan trọng: Nó sẽ chạy ngay lập tức khi bạn 'import config'
# Giúp các file khác luôn có data sẵn sàng mà không cần gọi hàm load thủ công.
load_config()