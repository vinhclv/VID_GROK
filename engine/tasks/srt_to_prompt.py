import os
import time
import json
import re
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import config

def process_srt_to_prompt(driver, chunk, log_callback=print):
    """
    Cơ chế tối giản:
    1. Chỉ trích xuất nội dung bên trong Code Block.
    2. Thử parse JSON trước (để lấy mọi trường dữ liệu GEM trả ra).
    3. Nếu không phải JSON, dùng Regex lấy ID: Prompt.
    4. Ghi thẳng vào file JSON (không kiểm tra trùng, không sắp xếp).
    """
    try:
        wait = WebDriverWait(driver, 30)
        
        json_output_path = chunk[0].get('json_path') #Lấy đường dẫn file json từ chunk
        if not json_output_path:
            log_callback("❌ Không tìm thấy đường dẫn json_path.")
            return False

        # --- 1. TẠO PROMPT ---
        srt_content_block = ""
        for item in chunk:
            srt_content_block += f"STT {item['STT']} - Timecode {item['Timecode']}: {item['text']}\n"

        prefix_instruction = (
            "COMMAND: You must output the result strictly inside a Markdown code block (```json ... ```).\n"
            "Include KEY: STT and all visual details. Do not include any text outside the code block."
        )

        user_prompt = f"{prefix_instruction}\n\nList:\n{srt_content_block}"

        # --- 2. GỬI TIN NHẮN ---
        try:
            input_box = wait.until(EC.presence_of_element_located((By.XPATH, "//div[@contenteditable='true']")))
            input_box.clear()
            driver.execute_script("arguments[0].textContent = arguments[1];", input_box, user_prompt)
            
            # Gõ một dấu cách để kích hoạt nút Send của Angular/React
            input_box.send_keys(" ") 
            time.sleep(1)
            
            send_button = driver.find_element(By.XPATH, "//button[contains(@class, 'send-button')]")
            driver.execute_script("arguments[0].click();", send_button)
        except Exception as e:
            log_callback(f"❌ Lỗi khi gửi tin nhắn: {e}")
            return False

        # --- 3. ĐỢI PHẢN HỒI XONG ---
        log_callback("⏳ Đang đợi Gemini trả lời...")
        RESPONSE_SELECTOR = "div.markdown-main-panel[id^='model-response-message-content']"
        old_count = len(driver.find_elements(By.CSS_SELECTOR, RESPONSE_SELECTOR))
        wait.until(lambda d: len(d.find_elements(By.CSS_SELECTOR, RESPONSE_SELECTOR)) > old_count)
        
        last_response_el = driver.find_elements(By.CSS_SELECTOR, RESPONSE_SELECTOR)[-1]
        
        last_len = -1
        start_wait = time.time()
        while True:
            curr_len = len(last_response_el.text)
            if curr_len == last_len and curr_len > 0: break
            last_len = curr_len
            time.sleep(2)
            if time.time() - start_wait > config.global_settings["system"]["wait_time"]: break

        # --- 4. TRÍCH XUẤT CODE BLOCK ---
        code_elements = last_response_el.find_elements(By.XPATH, ".//pre/code")
        if not code_elements:
            log_callback("❌ False: Không có Code Block.")
            return False

        full_code_content = "\n".join([el.text for el in code_elements]).strip()

        # --- 5. PARSE DỮ LIỆU (JSON HOẶC REGEX) ---
        new_entries = []

        # Thử parse JSON (Lấy tất cả các trường GEM trả ra)
        try:
            # Làm sạch chuỗi block code
            clean_str = full_code_content
            if "```" in clean_str:
                clean_str = re.sub(r'```[a-z]*', '', clean_str).replace('```', '').strip()
            
            data = json.loads(clean_str)
            if isinstance(data, list):
                new_entries = data
            elif isinstance(data, dict):
                new_entries = [data]
            log_callback("✅ Đã lấy dữ liệu định dạng JSON.")
        except:
            # Nếu lỗi JSON, dùng Regex (Dự phòng cho text thường)
            log_callback("ℹ️ Parse JSON lỗi, chuyển sang Regex...")
            matches = re.findall(r'ID\s*(\d+)[:\- ]+(.*?)(?=(?:\n\s*ID\s*\d+)|$)', full_code_content, re.DOTALL | re.IGNORECASE)
            for m in matches:
                new_entries.append({"STT": m[0].strip(), "Prompt": m[1].strip()})

        if not new_entries:
            log_callback("⚠️ Code Block rỗng hoặc không đúng cấu trúc.")
            return False

        # --- 6. LƯU DỒN (APPEND) VÀO FILE ---
        try:
            current_data = []
            if os.path.exists(json_output_path):
                try:
                    with open(json_output_path, 'r', encoding='utf-8') as f:
                        current_data = json.load(f)
                except: current_data = []

            current_data.extend(new_entries)

            with open(json_output_path, 'w', encoding='utf-8') as f:
                json.dump(current_data, f, ensure_ascii=False, indent=4)

            log_callback(f"💾 Đã nối thêm {len(new_entries)} mục vào file JSON.")
            return True

        except Exception as e:
            log_callback(f"❌ Lỗi lưu file: {e}")
            return False

    except Exception as e:
        log_callback(f"❌ Lỗi hệ thống: {e}")
        return False