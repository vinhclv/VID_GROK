"""
script_to_metadata.py — Tác vụ tự động hóa Playwright đưa Script_raw/*.txt lên Gemini Gem AI 
để trích xuất metadata.json và {ID}_thumb.json.
"""

import os
import time
import json
import re
from playwright.async_api import Page, Locator
import config
from engine.tasks.helpers import human_click, human_type
from utils.pre_upload_ops import extract_metadata_and_thumb_json

async def process_script_to_metadata_async(page: Page, item: dict, log_callback=print) -> bool:
    """
    Xử lý 1 kịch bản thô Script_raw/*.txt qua Gemini AI:
    1. Đọc nội dung file .txt.
    2. Điền kịch bản vào khung chat Gemini Gem AI và bấm gửi.
    3. Lắng nghe phản hồi từ Gemini (chờ văn bản ổn định độ dài).
    4. Trích xuất Code Block Markdown JSON.
    5. Gọi extract_metadata_and_thumb_json để tạo metadata.json & {ID}_thumb.json.
    """
    script_path = item.get("script_path") or item.get("inp")
    output_dir = item.get("output_dir") or item.get("out")
    vid_id = item.get("vid_id", "0000")

    if not script_path or not os.path.exists(script_path):
        log_callback(f"❌ File kịch bản không tồn tại: {script_path}")
        return False

    try:
        with open(script_path, "r", encoding="utf-8", errors="ignore") as f:
            script_text = f.read().strip()

        if not script_text:
            log_callback(f"❌ File kịch bản bị rỗng: {os.path.basename(script_path)}")
            return False

        # --- 1. UPLOAD ĐÍNH KÈM FILE KỊCH BẢN .TXT LÊN GEMINI ---
        log_callback(f"📎 Đang đính kèm file kịch bản {os.path.basename(script_path)} lên Gemini Gem AI...")
        
        file_uploaded = False
        file_inputs = page.locator("input[type='file']")

        if await file_inputs.count() > 0:
            try:
                await file_inputs.first.set_input_files(script_path)
                await page.wait_for_timeout(3000) # Đợi chip file xuất hiện trong khung Gemini
                file_uploaded = True
                log_callback(f"✅ Đã đính kèm tệp {os.path.basename(script_path)} thành công!")
            except Exception as e_file:
                log_callback(f"⚠️ Lỗi khi đính kèm file qua input: {e_file}")

        if not file_uploaded:
            # Fallback: Điền nhanh text vào khung chat nếu không đính kèm file được
            textbox = page.locator("form textarea, form [contenteditable='true'], [role='textbox']").first
            await textbox.wait_for(state='visible', timeout=15000)
            await human_click(textbox, page)
            await page.wait_for_timeout(200)
            await textbox.fill(script_text.replace("@", ""))
            await page.wait_for_timeout(500)

        # --- 2. BẤM GỬI TIN NHẮN ---
        btn_send = page.locator("button[aria-label*='Send'], button[aria-label*='Gửi'], form div.absolute.right-2 button, form button[type='submit'], button.send-button").last
        try:
            await btn_send.wait_for(state='visible', timeout=3000)
            await human_click(btn_send, page)
        except Exception:
            textbox = page.locator("form textarea, form [contenteditable='true'], [role='textbox']").first
            await textbox.press("Enter")

        # --- 2. LẮNG NGHE PHẢN HỒI GEMINI ---
        log_callback("⏳ Đang chờ Gemini AI sinh Metadata & Thumbnail JSON...")
        RESPONSE_SELECTOR = "div.markdown-main-panel[id^='model-response-message-content'], div.message-content, [role='log'] div.prose, div.markdown"
        
        resp_locator = page.locator(RESPONSE_SELECTOR).last
        await resp_locator.wait_for(state='visible', timeout=30000)

        last_len = -1
        start_wait = time.time()
        wait_limit = config.global_settings["system"].get("wait_time", 120)

        while time.time() - start_wait < wait_limit:
            try:
                curr_text = await resp_locator.inner_text()
                curr_len = len(curr_text.strip())
                if curr_len == last_len and curr_len > 0:
                    break
                last_len = curr_len
            except Exception as e_poll:
                log_callback(f"⚠️ Polling response lỗi: {e_poll}")
                resp_locator = page.locator(RESPONSE_SELECTOR).last
            await page.wait_for_timeout(2000)

        # --- 3. TRÍCH XUẤT CODE BLOCK MARKDOWN JSON ---
        full_response_text = await resp_locator.inner_text()
        
        # Thử tìm Code Block ````json ... ```` trước
        code_elements = resp_locator.locator("pre code, code")
        code_count = await code_elements.count()
        
        json_payload_text = ""
        if code_count > 0:
            code_contents = []
            for i in range(code_count):
                txt = await code_elements.nth(i).inner_text()
                code_contents.append(txt)
            json_payload_text = "\n".join(code_contents).strip()
        else:
            json_payload_text = full_response_text.strip()

        # --- 4. TÁCH VÀ GHI FILE METADATA.JSON & THUMB.JSON ---
        ok, msg = extract_metadata_and_thumb_json(json_payload_text, output_dir, vid_id)
        if ok:
            log_callback(f"✅ Hoàn tất STT/Dự án {vid_id}: {msg}")
            return True
        else:
            log_callback(f"⚠️ Trích xuất JSON thất bại cho {vid_id}: {msg}")
            return False

    except Exception as e:
        log_callback(f"❌ Lỗi xử lý kịch bản {os.path.basename(script_path)}: {e}")
        return False
