import os
import time
import json
import re
from playwright.async_api import Page, Locator
import config
from engine.tasks.prompt_to_video import human_click, human_type

async def process_srt_to_prompt_async(page: Page, chunk: list, log_callback=print) -> bool:
    """
    Xử lý chuyển đổi SRT sang Prompt bằng Playwright:
    1. Tập hợp kịch bản của chunk thành văn bản yêu cầu.
    2. Điền prompt mô phỏng người thật vào textbox và bấm gửi.
    3. Lắng nghe câu trả lời ổn định độ dài văn bản.
    4. Trích xuất code block markdown, chuyển đổi sang JSON hoặc Regex.
    5. Lưu dồn (hoặc ghi đè trùng lặp) vào file JSON và sắp xếp tăng dần theo STT.
    """
    try:
        json_output_path = chunk[0].get('json_path')
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

        # --- 2. GỬI TIN NHẮN BẰNG PLAYWRIGHT ---
        try:
            textbox = page.locator("form textarea, form [contenteditable='true'], [role='textbox']").first
            await textbox.wait_for(state='visible', timeout=15000)
            await textbox.fill("")
            await human_type(textbox, user_prompt, page)
            await page.wait_for_timeout(1000)

            # Bấm gửi
            btn_send = page.locator("form div.absolute.right-2 button, form button[type='submit']").last
            if await btn_send.is_visible(timeout=2000):
                await human_click(btn_send, page)
            else:
                await textbox.press("Enter")
        except Exception as e:
            log_callback(f"❌ Lỗi khi gửi tin nhắn: {e}")
            return False

        # --- 3. ĐỢI PHẢN HỒI XONG ---
        log_callback("⏳ Đang đợi Gemini/Grok trả lời...")
        
        # Chọn tất cả các thẻ nội dung tin nhắn phản hồi phổ biến của Gemini/Grok
        RESPONSE_SELECTOR = "div.markdown-main-panel[id^='model-response-message-content'], div.message-content, [role='log'] div.prose, div.markdown"
        
        # Đợi cho phần tử phản hồi xuất hiện
        await page.locator(RESPONSE_SELECTOR).last.wait_for(state='visible', timeout=20000)
        last_response_el = page.locator(RESPONSE_SELECTOR).last
        
        # Vòng lặp chờ phản hồi hoàn tất (khi độ dài văn bản không đổi)
        last_len = -1
        start_wait = time.time()
        wait_limit = config.global_settings["system"]["wait_time"]
        
        while time.time() - start_wait < wait_limit:
            try:
                curr_text = await last_response_el.inner_text()
                curr_len = len(curr_text.strip())
                if curr_len == last_len and curr_len > 0:
                    break
                last_len = curr_len
            except:
                pass
            await page.wait_for_timeout(2000)

        # --- 4. TRÍCH XUẤT CODE BLOCK ---
        code_elements = last_response_el.locator("pre code, code")
        code_count = await code_elements.count()
        if code_count == 0:
            log_callback("❌ Lỗi: Không tìm thấy Code Block trong phản hồi.")
            return False

        # Thu thập toàn bộ nội dung trong code block
        code_contents = []
        for i in range(code_count):
            txt = await code_elements.nth(i).inner_text()
            code_contents.append(txt)
            
        full_code_content = "\n".join(code_contents).strip()

        # --- 5. PARSE DỮ LIỆU (JSON HOẶC REGEX FALLBACK) ---
        new_entries = []

        # A. Thử parse JSON
        try:
            clean_str = full_code_content
            if "```" in clean_str:
                clean_str = re.sub(r'```[a-z]*', '', clean_str).replace('```', '').strip()
            
            data = json.loads(clean_str)
            if isinstance(data, list):
                new_entries = data
            elif isinstance(data, dict):
                new_entries = [data]
            log_callback("✅ Đã lấy và parse thành công dữ liệu định dạng JSON.")
        except:
            # B. Nếu lỗi JSON, dùng Regex dự phòng
            log_callback("ℹ️ Parse JSON lỗi, chuyển sang Regex dự phòng...")
            matches = re.findall(r'ID\s*(\d+)[:\- ]+(.*?)(?=(?:\n\s*ID\s*\d+)|$)', full_code_content, re.DOTALL | re.IGNORECASE)
            for m in matches:
                new_entries.append({"STT": m[0].strip(), "Prompt": m[1].strip()})

        if not new_entries:
            log_callback("⚠️ Phản hồi trống hoặc không đúng cấu trúc.")
            return False

        # --- 6. LƯU DỒN (APPEND VÀ OVERWRITE TRÙNG) VÀO FILE ---
        try:
            current_data = []
            if os.path.exists(json_output_path):
                try:
                    with open(json_output_path, 'r', encoding='utf-8') as f:
                        current_data = json.load(f)
                except:
                    current_data = []

            # Ghi đè các bản ghi cũ có cùng STT
            new_stts = {str(item.get("STT")) for item in new_entries}
            current_data = [item for item in current_data if str(item.get("STT")) not in new_stts]
            current_data.extend(new_entries)

            # Sắp xếp lại danh sách theo STT tăng dần để file đầu ra luôn gọn gàng
            try:
                current_data.sort(key=lambda x: int(x.get("STT", 0)))
            except:
                pass

            # Lưu lại
            with open(json_output_path, 'w', encoding='utf-8') as f:
                json.dump(current_data, f, ensure_ascii=False, indent=4)

            log_callback(f"💾 Đã cập nhật và lưu dồn {len(new_entries)} mục vào: {os.path.basename(json_output_path)}")
            return True

        except Exception as e:
            log_callback(f"❌ Lỗi ghi file JSON: {e}")
            return False

    except Exception as e:
        log_callback(f"❌ Lỗi hệ thống khi trích kịch bản: {e}")
        return False