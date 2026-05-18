import os
import time
import random
import json
import re
import asyncio
from playwright.async_api import Page, Locator
import config

async def human_click(locator: Locator, page: Page, force: bool=False):
    """
    Mô phỏng click chuột của người thật bằng Virtual Mouse.
    Không chiếm chuột vật lý của máy tính.
    """
    try:
        await locator.scroll_into_view_if_needed(timeout=5000)
        await locator.hover(timeout=5000)
        await page.wait_for_timeout(random.uniform(100, 300))
        await locator.click(delay=random.randint(50, 150), force=force)
    except Exception as e:
        print(f'⚠️ Chuyển sang click dự phòng: {e}')
        await locator.click(delay=random.randint(50, 150), force=True)

async def human_type(locator: Locator, text: str, page: Page):
    """
    Mô phỏng gõ phím theo cụm (chunk) với tốc độ và nhịp thở của người thật.
    """
    await human_click(locator, page)
    await page.wait_for_timeout(random.uniform(200, 400))
    idx = 0
    while idx < len(text):
        chunk_size = random.randint(15, 30)
        chunk = text[idx:idx + chunk_size]
        await locator.press_sequentially(chunk, delay=random.randint(5, 10))
        idx += chunk_size
        await page.wait_for_timeout(random.uniform(20, 50))
        if random.random() < 0.05:
            await page.wait_for_timeout(random.uniform(100, 200))
    await page.wait_for_timeout(random.uniform(200, 400))

async def paste_images_to_chat(page: Page, image_paths: list):
    try:
        # CÁCH 1: NATIVE PLAYWRIGHT (Chuẩn nhất, KHÔNG BAO GIỜ BỊ NHÂN ĐÔI)
        file_input = page.locator("input[type='file']")
        if await file_input.count() > 0:
            # Upload toàn bộ danh sách ảnh trong 1 phát duy nhất
            await file_input.first.set_input_files(image_paths)
            return
    except Exception as e:
        pass

    # CÁCH 2: DÙNG JS BUBBLING GOM CHUNG (Chỉ chạy khi không có input file)
    import base64
    import os
    js_code = """
    (filesData) => {
        const dataTransfer = new DataTransfer();
        for (let i = 0; i < filesData.length; i++) {
            const fileObj = filesData[i];
            const byteCharacters = atob(fileObj.base64);
            const byteArrays = [];
            for (let offset = 0; offset < byteCharacters.length; offset += 512) {
                const slice = byteCharacters.slice(offset, offset + 512);
                const byteNumbers = new Array(slice.length);
                for (let j = 0; j < slice.length; j++) {
                    byteNumbers[j] = slice.charCodeAt(j);
                }
                const byteArray = new Uint8Array(byteNumbers);
                byteArrays.push(byteArray);
            }
            const blob = new Blob([new Uint8Array(byteArrays)], {type: fileObj.mime});
            const file = new File([blob], 'image_' + i + fileObj.ext, {type: fileObj.mime});
            dataTransfer.items.add(file);
        }
        
        const pasteEvent = new ClipboardEvent('paste', {
            clipboardData: dataTransfer,
            bubbles: true,
            cancelable: true
        });
        
        const target = document.querySelector("textarea") || document.activeElement;
        if(target) target.dispatchEvent(pasteEvent);
    }
    """
    files_data = []
    for img_path in image_paths:
        with open(img_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
        _, ext = os.path.splitext(img_path)
        mime_type = f"image/{ext.replace('.', '')}".lower()
        if mime_type == "image/jpg": mime_type = "image/jpeg"
        files_data.append({"base64": encoded_string, "mime": mime_type, "ext": ext})
        
    await page.evaluate(js_code, files_data)

def parse_duration_to_seconds(timecode_str: str) -> float:
    try:
        parts = timecode_str.split(' --> ')
        def to_sec(t):
            h, m, s_ms = t.split(':')
            s, ms = s_ms.split(',')
            return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000
        duration = to_sec(parts[1]) - to_sec(parts[0])
        return duration
    except:
        return 6.0

async def setup_video_duration_ui(page: Page, video_length: int):
    try:
        target_label = f'{video_length}s'
        btn = page.locator(f"button:has-text('{target_label}'), div:text-is('{target_label}')").last
        if await btn.is_visible(timeout=3000):
            await human_click(btn, page)
            print(f'✅ Đã click chọn thời lượng {target_label} qua UI')
    except Exception as e:
        print(f'⚠️ Chưa chọn được thời lượng qua UI (Bỏ qua)')

async def setup_video_format_ui(page: Page):
    """
    Tự động đọc cấu hình Aspect Ratio (Tỉ lệ) và Resolution (Độ phân giải) 
    từ file settings.json (nằm trong config.global_settings['system'])
    """
    # 0. Chuyển sang tab Video
    try:
        # Tìm chính xác nút có text là 'Video'
        btn_video = page.locator("button:text-is('Video'), button:has-text('Video')").first
        if await btn_video.is_visible(timeout=2000):
            await human_click(btn_video, page)
            print(f'✅ Đã click chuyển sang tab Video')
            await page.wait_for_timeout(1000)
    except Exception as e:
        pass

    system_cfg = config.global_settings.get('system', {})
    aspect_ratio = system_cfg.get('aspect_ratio', '16:9') # Mặc định 16:9
    resolution = system_cfg.get('resolution', '720p')     # Mặc định 720p

    # 1. Chọn Aspect Ratio (Dạng Dropdown có mũi tên)
    try:
        # Tìm nút dropdown hiện tại (chứa 16:9 hoặc 9:16 hoặc 1:1)
        dropdown_btn = page.locator("button:has-text('16:9'), button:has-text('9:16'), button:has-text('1:1')").first
        if await dropdown_btn.is_visible(timeout=2000):
            current_text = await dropdown_btn.inner_text()
            if aspect_ratio not in current_text:
                await human_click(dropdown_btn, page) # Mở menu thả xuống
                await page.wait_for_timeout(500)
                # Click chọn tỉ lệ mong muốn
                option_btn = page.locator(f"text='{aspect_ratio}'").last
                if await option_btn.is_visible(timeout=2000):
                    await human_click(option_btn, page)
                    print(f'✅ Đã đổi tỉ lệ khung hình thành: {aspect_ratio}')
    except Exception as e:
        print(f'⚠️ Bỏ qua chọn Tỉ lệ: {e}')

    # 2. Chọn Resolution
    try:
        res_btn = page.locator(f"button:has-text('{resolution}'), div:text-is('{resolution}')").last
        if await res_btn.is_visible(timeout=2000):
            await human_click(res_btn, page)
            print(f'✅ Đã chọn độ phân giải: {resolution}')
    except Exception as e:
        print(f'⚠️ Bỏ qua chọn Độ phân giải: {e}')

async def process_1_image_video_batch(page: Page, file_batch: list, output_folder: str, log_callback=print):
    """
    Hàm sinh video từ N Ảnh + Prompt theo cơ chế Playwright mô phỏng người thật.
    Chặn Request Network thay vì API ngầm để tránh Cloudflare chống bot.
    """
    tasks = {}
    downloaded_urls = set()
    
    # Thiết lập Interceptor mạng native của Playwright
    if not hasattr(page, 'grok_video_results'):
        page.grok_video_results = {}
        async def on_response(response):
            try:
                if "rest/app-chat/conversations/new" in response.url and response.request.method == "POST":
                    post_data = response.request.post_data
                    if post_data:
                        match_stt = re.search(r'\|\|(.*?)\|\|', post_data)
                        if match_stt:
                            stt = match_stt.group(1).strip()
                            page.grok_video_results[stt] = {'status': 'running'}
                            
                            try:
                                # Anti-hang: Đợi tối đa 180s cho luồng stream hoàn tất
                                text = await asyncio.wait_for(response.text(), timeout=180.0)
                                match_url = re.search(r'"videoUrl"\s*:\s*"([^"]+)"', text)
                                if match_url:
                                    page.grok_video_results[stt] = {'status': 'success', 'url': "https://assets.grok.com/" + match_url.group(1)}
                                else:
                                    page.grok_video_results[stt] = {'status': 'error', 'msg': 'Không tìm thấy videoUrl'}
                            except asyncio.TimeoutError:
                                page.grok_video_results[stt] = {'status': 'error', 'msg': 'Timeout chờ Stream (quá 3 phút)'}
                            except Exception as e:
                                page.grok_video_results[stt] = {'status': 'error', 'msg': f'Lỗi đọc stream: {e}'}
            except Exception as e:
                pass
        page.on("response", on_response)
    
    try:
        # Tìm chính xác nút Saved bằng aria-label hoặc text (không sợ nhầm sang nút + Upload ảnh)
        btn_saved = page.locator("button[aria-label='Saved'], button[aria-label='Đã lưu'], button:has-text('Saved'), button:has-text('Đã lưu')").first
        if await btn_saved.is_visible(timeout=3000):
            await human_click(btn_saved, page)
            log_callback(f'➡️ Đã click nút Đã lưu (Saved) để dọn context trước khi chạy')
        else:
            log_callback(f'⚠️ Không tìm thấy nút Saved trên UI lúc bắt đầu.')
    except Exception as e:
        log_callback(f'⚠️ Lỗi chuyển context lúc bắt đầu: {e}')
        await page.wait_for_timeout(random.uniform(2000, 3000))

    for idx, item in enumerate(file_batch):
        stt = str(item.get('STT', '')).strip()
        if not stt:
            continue
            
        timecode = item.get('Timecode', '00:00:00,000 --> 00:00:06,000')
        actual_seconds = parse_duration_to_seconds(timecode)
        video_length = 6 if actual_seconds <= 6 else 10
        
        video_path = item.get('video_path')
        raw_image_paths = item.get('image_paths', [])
        
        image_paths = []
        for p in raw_image_paths:
            if p not in image_paths:
                image_paths.append(p)
                
        prompt_text = item.get('visual_details', '')
        
        if os.path.exists(video_path):
            log_callback(f'⏭️ Bỏ qua STT {stt} (Đã có video)')
            continue
            
        id_tag = f'||{stt}||'
        tasks[stt] = {'video_path': video_path, 'id_tag': id_tag, 'done': False, 'original_item': item}
        
        try:
            if idx > 0:
                try:
                    await page.wait_for_timeout(random.uniform(2000, 3000))
                    # Tìm chính xác nút Saved bằng aria-label hoặc text (không sợ nhầm sang nút + Upload ảnh)
                    btn_saved = page.locator("button[aria-label='Saved'], button[aria-label='Đã lưu'], button:has-text('Saved'), button:has-text('Đã lưu')").first
                    if await btn_saved.is_visible(timeout=3000):
                        await human_click(btn_saved, page)
                        log_callback(f'➡️ Đã click nút Đã lưu (Saved) để chuyển context (STT {stt})')
                    else:
                        # Tuyệt đối KHÔNG dùng page.goto ở đây vì sẽ làm đứt Network của video trước đó.
                        # Nếu không tìm thấy nút, đành chấp nhận dính ParentID còn hơn mất video.
                        log_callback(f'⚠️ Không tìm thấy nút Saved trên UI. Chấp nhận dính Parent Context (STT {stt})')
                except Exception as e:
                    log_callback(f'⚠️ Lỗi chuyển context /saved: {e}')
                await page.wait_for_timeout(random.uniform(2000, 3000))

            # Lấy Textbox cực kỳ robust: Tìm textarea hoặc contenteditable nằm trong form
            textbox = page.locator("form textarea, form [contenteditable='true'], [role='textbox']").first
            await textbox.wait_for(state='visible', timeout=15000)
            
            # Click cấu hình thời lượng và định dạng video (Đã bao gồm click tab Video bên trong)
            await setup_video_duration_ui(page, video_length)
            await setup_video_format_ui(page)
            
            # Focus
            await human_click(textbox, page)
            await page.wait_for_timeout(500)

            # Dọn rác ảnh đính kèm (nếu bị kẹt từ phiên trước chưa kịp xóa) một lần duy nhất trước khi làm việc
            try:
                remove_btns = page.locator("button[aria-label='Remove image']")
                count = await remove_btns.count()
                if count > 0:
                    log_callback('🧹 Phát hiện ảnh kẹt từ phiên trước, đang dọn dẹp mặt bằng...')
                    for _ in range(count):
                        await remove_btns.nth(0).click(timeout=1000)
                        await page.wait_for_timeout(200)
            except:
                pass
            
            # Dán tất cả các ảnh 1 lần duy nhất
            if image_paths:
                log_callback(f'☁️ Đang upload 1 phát {len(image_paths)} ảnh nhân vật cho STT {stt}...')
                await paste_images_to_chat(page, image_paths)
                await page.wait_for_timeout(3000) # Đợi một lát cho ảnh load lên UI
            else:
                log_callback(f'⚠️ Không có ảnh nhân vật cho STT {stt}, render chỉ từ Prompt.')

            # Nhập Text (Xóa text cũ của bản nháp nếu có trước khi gõ)
            full_prompt = f"{id_tag} {prompt_text}"
            await textbox.fill("") 
            await human_type(textbox, full_prompt, page)
            await page.wait_for_timeout(random.uniform(1000, 2000))
            
            # Bấm gửi: Dựa theo cấu trúc Tailwind CSS bạn gửi (nằm trong div.absolute.right-2 của form)
            btn_gen = page.locator("form div.absolute.right-2 button, form button[type='submit']").last
            if await btn_gen.is_visible(timeout=2000):
                # Chờ nút Submit sáng lên (Đợi ảnh upload lên server Grok xong)
                submit_enabled = False
                for _ in range(15):
                    if await btn_gen.is_enabled():
                        submit_enabled = True
                        break
                    await page.wait_for_timeout(1000)
                
                if not submit_enabled:
                    log_callback(f'⚠️ Nút Gửi bị khóa quá 15s (STT {stt}) do ảnh kẹt/lỗi mạng. Bỏ qua STT này.')
                    tasks.pop(stt, None)
                    continue # Chuyển sang xử lý STT tiếp theo
                    
                await human_click(btn_gen, page)
            else:
                await textbox.press("Enter")
                
            log_callback(f'🚀 Đã Submit qua UI STT {stt} (Dự kiến {video_length}s)...')
            # Nghỉ 2-4 giây giữa các lần submit theo yêu cầu
            await page.wait_for_timeout(random.uniform(2000, 4000))
            
        except Exception as e:
            log_callback(f'❌ Lỗi gửi UI STT {stt}: {e}')
            tasks.pop(stt, None)
            
    if not tasks:
        return (False, file_batch)
        
    log_callback(f'⏳ Chờ render {len(tasks)} video qua luồng mạng...')
    start_time = time.time()
    wait_time_limit = config.global_settings['system']['wait_time']
    
    while time.time() - start_time < wait_time_limit:
        active_tasks = [uid for uid, info in tasks.items() if not info['done']]
        if not active_tasks:
            log_callback('✅ Tất cả video trong đợt này đã tải xong!')
            break
            
        js_results = page.grok_video_results
        
        for uid in active_tasks:
            info = tasks[uid]
            if uid in js_results:
                status_obj = js_results[uid]
                status = status_obj.get("status")
                if status == "success":
                    video_url = status_obj.get("url")
                    if video_url in downloaded_urls:
                        continue
                    os.makedirs(os.path.dirname(info['video_path']), exist_ok=True)
                    log_callback(f'💾 Bắt đầu tải Video xịn: STT {uid}')
                    try:
                        response = await page.request.get(video_url)
                        with open(info['video_path'], 'wb') as f:
                            f.write(await response.body())
                        if os.path.exists(info['video_path']) and os.path.getsize(info['video_path']) > 0:
                            log_callback(f'✅ Thành công: STT {uid}')
                            info['done'] = True
                            downloaded_urls.add(video_url)
                        else:
                            log_callback(f'⚠️ Lỗi tải file bị 0KB: STT {uid}')
                            info['done'] = True
                    except Exception as e:
                        log_callback(f'❌ Lỗi download MP4 STT {uid}: {e}')
                        info['done'] = True
                elif status == "error":
                    log_callback(f'❌ Lỗi Render Grok STT {uid}: {status_obj.get("msg")}')
                    info['done'] = True
        await page.wait_for_timeout(3000)
        
    failed_objects = []
    for uid, info in tasks.items():
        vp = info['video_path']
        if not (os.path.exists(vp) and os.path.getsize(vp) > 0):
            failed_objects.append(info['original_item'])
            
    return (len(failed_objects) == 0, failed_objects)