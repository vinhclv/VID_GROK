import os
import time
import requests
import base64
from PIL import Image # Thêm thư viện này
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import glob
import shutil
import config


def download_via_native_button(driver, save_path, download_dir_chrome, log_callback=print):
    """ 
    Logic: Dọn file rác -> Bấm tải -> Chờ file -> Check ảnh -> Move. 
    """
    try:
        wait = WebDriverWait(driver, 15)
        
        # --- 0. DỌN SẠCH THƯ MỤC TEMP TRƯỚC KHI TẢI ---
        if os.path.exists(download_dir_chrome):
            # Xóa từng file để tránh lỗi Access Denied với Folder
            for f in glob.glob(os.path.join(download_dir_chrome, "*")):
                try: os.remove(f) 
                except: pass 
        else:
            os.makedirs(download_dir_chrome, exist_ok=True)

        # --- 1. TÌM VÀ CLICK NÚT DOWNLOAD ---

        containers = driver.find_elements(By.XPATH, "//generated-image")
        if not containers: 
            log_callback("⚠️ Không tìm thấy thẻ <generated-image>.")
            return False
        
        target = containers[-1]
        
        # Bước 1: Cuộn tới phần tử
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", target)
        time.sleep(0.5)

        # Bước 2: Dùng JS để ép CSS hiển thị lớp phủ chứa nút bấm
        # Thông thường Gemini/Google dùng opacity hoặc visibility để ẩn nút
        driver.execute_script("""
            var container = arguments[0];
            // Tìm tất cả các lớp phủ hoặc overlay bên trong container
            var overlays = container.querySelectorAll('div, button');
            overlays.forEach(el => {
                if (getComputedStyle(el).opacity == '0') {
                    el.style.opacity = '1';
                    el.style.visibility = 'visible';
                    el.style.display = 'block';
                }
            });
        """, target)
        time.sleep(0.5)

        # Bước 3: Tìm nút dựa trên thuộc tính đặc trưng
        xpath_btn = ".//button[@data-test-id='download-generated-image-button' or .//mat-icon[contains(text(), 'download')]]"
        
        try:
            # Ưu tiên tìm nút đang hiển thị
            btn = target.find_element(By.XPATH, xpath_btn)
            
            # Click bằng JavaScript (Xuyên qua mọi lớp chặn/chiếm chuột)
            driver.execute_script("arguments[0].click();", btn)
            log_callback("🖱️ Đã ép click Download bằng JS thành công.")
            
        except Exception as e:
            # Nếu vẫn không thấy, thử tìm nút trong toàn bộ DOM của target
            log_callback(f"⚠️ Thử phương án dự phòng cho nút download...")
            try:
                btn_fallback = driver.execute_script(f"return arguments[0].querySelector('button[data-test-id*=\"download\"]');", target)
                driver.execute_script("arguments[0].click();", btn_fallback)
            except:
                log_callback("❌ Thất bại: Nút download không tồn tại hoặc bị ẩn sâu.")
                return False

        # --- 2. CHỜ FILE TẢI VỀ ---
        log_callback("⏳ Đang chờ file tải xuống...")
        downloaded_file = None
        start_wait = time.time()
        
        MIN_SIZE_BYTES = 100 * 1024 

        while time.time() - start_wait < 60: # Timeout 60s
            # 1. Lấy danh sách file đã bỏ đuôi .crdownload
            files = [f for f in glob.glob(os.path.join(download_dir_chrome, "*")) 
                     if not f.endswith(('.crdownload', '.tmp')) and os.path.isfile(f)]
            
            if files:
                # Lấy file mới nhất
                latest_file = max(files, key=os.path.getmtime)
                
                try:
                    current_size = os.path.getsize(latest_file)
                    
                    # 2. Check sơ bộ: Phải lớn hơn 200KB mới bắt đầu xét
                    if current_size > MIN_SIZE_BYTES:
                        
                        time.sleep(1)
                        new_size = os.path.getsize(latest_file)
                        
                        if new_size == current_size:
                            downloaded_file = latest_file
                            break
                        else:
                            pass
                except: 
                    pass # File đang bị lock hoặc lỗi truy cập, thử lại ở vòng sau
            
            time.sleep(1)

        if not downloaded_file:
            log_callback("❌ Timeout: File không xuất hiện hoặc tải lỗi.")
            return False

        # --- 3. KIỂM TRA CHẤT LƯỢNG ẢNH (PILLOW) ---
        # Logic: Check ngay tại thư mục temp trước khi move
        try:
            with Image.open(downloaded_file) as img:
                width, height = img.size
                
                if height == 0: raise ValueError("Height = 0")
                
                aspect_ratio = width / height
                # 16:9 = 1.777. Chấp nhận sai số từ 1.7 đến 1.85
                if aspect_ratio < 1.7 or aspect_ratio > 1.85:
                    log_callback(f"⚠️ Sai tỉ lệ ({width}x{height} - {aspect_ratio:.2f}). Hủy.")
                    return False 
                
                # Kiểm tra độ phân giải tối thiểu (tránh ảnh thumbnail/icon lỗi)
                if width < 500 or height < 300:
                    log_callback(f"⚠️ Ảnh quá nhỏ ({width}x{height}). Hủy.")
                    return False

        except Exception as e:
            log_callback(f"❌ Lỗi file ảnh (Hỏng/Không đọc được): {e}")
            try: os.remove(downloaded_file)
            except: pass
            return False

        # --- 4. MOVE & RENAME ---
        try:
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            
            # Xử lý đuôi file nếu save_path chưa có
            filename, ext = os.path.splitext(save_path)
            if not ext:
                src_ext = os.path.splitext(downloaded_file)[1]
                save_path = f"{filename}{src_ext}"

            # Xóa file đích cũ nếu tồn tại (để overwrite)
            if os.path.exists(save_path):
                os.remove(save_path)

            # Move file
            shutil.move(downloaded_file, save_path)
            # log_callback(f"✅ Đã lưu: {os.path.basename(save_path)}")
            return True

        except Exception as e:
            log_callback(f"❌ Lỗi Move file: {e}")
            return False

    except Exception as e:
        log_callback(f"❌ Lỗi ngoại lệ Download: {e}")
        return False

def process_prompt_to_image(driver, item, log_callback=print):
    try:
        wait = WebDriverWait(driver, config.global_settings["system"]["wait_time"])
        stt = item['id']
        prompt_text = item['prompt']
        save_path = item['save_path']
        output_folder = item['output_folder']

        os.makedirs(output_folder, exist_ok=True)

        # --- 1. ĐỊNH NGHĨA XPATH VÀ ĐẾM ẢNH CŨ ---
        IMG_XPATH = "//generated-image//single-image//img"
        old_images = driver.find_elements(By.XPATH, IMG_XPATH)
        old_count = len(old_images)

        # --- 1.1. CHỌN MODEL PRO (Giữ nguyên logic của bạn) ---
        try:
            xpath_model_menu = "//bard-mode-switcher//button"
            btn_model_menu = wait.until(EC.presence_of_element_located((By.XPATH, xpath_model_menu)))
            driver.execute_script("arguments[0].click();", btn_model_menu)
            time.sleep(1.5)
            xpath_pro = "//div[@role='menu']//button[.//span[contains(text(), 'Advanced') or contains(text(), 'Pro')]]"
            btn_pro = wait.until(EC.presence_of_element_located((By.XPATH, xpath_pro)))
            driver.execute_script("arguments[0].click();", btn_pro)
            time.sleep(2)
        except: pass

        # --- 2. NHẬP PROMPT VÀ GỬI ---
        input_box = wait.until(EC.presence_of_element_located((By.XPATH, "//div[@contenteditable='true']")))

        driver.execute_script("arguments[0].textContent = arguments[1];", input_box, prompt_text)
        input_box.send_keys(" ") 
        time.sleep(1)
        
        send_button = driver.find_element(By.XPATH, "//button[contains(@class, 'send-button')]")
        driver.execute_script("arguments[0].click();", send_button)

        # --- 3. ĐỢI ẢNH MỚI ---
        log_callback(f"⏳ Đang tạo ảnh STT {stt}...")
        try:
            wait.until(lambda d: len(d.find_elements(By.XPATH, IMG_XPATH)) > old_count)
        except:
            log_callback(f"❌ Timeout: Không thấy ảnh mới cho STT {stt}.")
            return False

        time.sleep(6)

        if  download_via_native_button(driver, save_path, driver.my_download_dir) == False:
            log_callback("Lỗi tải về:", stt)
            return False

        # --- 7. KIỂM TRA CHẤT LƯỢNG ẢNH (TỈ LỆ 16:9) ---
        try:
            with Image.open(save_path) as img:
                width, height = img.size
                if height == 0: raise ValueError("Height = 0")
                
                aspect_ratio = width / height
                # 16:9 = 1.777
                # Chấp nhận sai số từ 1.7 đến 1.85
                if aspect_ratio < 1.7 or aspect_ratio > 1.85:
                    log_callback(f"⚠️ Sai tỉ lệ ({width}x{height} - {aspect_ratio:.2f}). Đang xóa để retry...")
                    # Đóng file trước khi xóa (quan trọng trên Windows)
                    del img 
                    if os.path.exists(save_path):
                        os.remove(save_path)
                    return False 
                
                # Kiểm tra thêm: Nếu ảnh quá nhỏ (VD: icon lỗi) -> Xóa
                if width < 500 or height < 300:
                    log_callback(f"⚠️ Ảnh quá nhỏ ({width}x{height}). Xóa...")
                    if os.path.exists(save_path): os.remove(save_path)
                    return False

                # log_callback(f"✅ Ảnh OK: {width}x{height}")
        except Exception as e:
            log_callback(f"⚠️ Lỗi check ảnh (Pillow): {e}")
            # Nếu lỗi mở file (file hỏng), return False để tải lại
            return False

        log_callback(f"✅ Hoàn thành STT {stt}")
        return True


    except Exception as e:
        log_callback(f"❌ Lỗi xử lý STT {item.get('id')}: {str(e)}")
        return False