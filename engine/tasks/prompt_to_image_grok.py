import os
import time
import random
import asyncio
import re
import base64
from PIL import Image
from playwright.async_api import Page
import config
from engine.tasks.prompt_to_video import human_click, human_type, paste_images_to_chat

async def setup_image_format_ui(page: Page):
    """
    Tự động chọn tab Hình ảnh (Image) và cấu hình tỉ lệ khung hình (Aspect Ratio)
    từ settings.json.
    """
    # 0. Chuyển sang tab Hình ảnh (Image)
    try:
        btn_img = page.locator("button:text-is('Hình ảnh'), button:has-text('Hình ảnh'), button:text-is('Image'), button:has-text('Image')").first
        if await btn_img.is_visible(timeout=2000):
            await human_click(btn_img, page)
            await page.wait_for_timeout(1000)
    except:
        pass

    # 1. Chọn Aspect Ratio (Dạng Dropdown có tỉ lệ hiện tại, e.g. 2:3, 16:9, 1:1, 9:16, v.v.)
    system_cfg = config.global_settings.get('system', {})
    aspect_ratio = system_cfg.get('aspect_ratio', '16:9') # Mặc định 16:9

    try:
        # Tìm nút dropdown tỉ lệ khung hình (chứa dấu hai chấm như 16:9, 9:16, 1:1, 2:3, 3:2, 4:3, v.v.)
        dropdown_btn = page.locator("button:has-text(':')").first
        if await dropdown_btn.is_visible(timeout=2000):
            current_text = await dropdown_btn.inner_text()
            if aspect_ratio not in current_text:
                await human_click(dropdown_btn, page) # Mở menu thả xuống
                await page.wait_for_timeout(800)
                
                # Ưu tiên tìm trong popup menu nổi để tránh click nhầm vào background cards
                options = page.locator("[role='menu'] *, [role='listbox'] *, [role='dialog'] *, [class*='menu'] *, [class*='popover'] *, .popover *").filter(has_text=re.compile(rf"^{aspect_ratio}")).filter(has_not=dropdown_btn)
                count = await options.count()
                
                if count == 0:
                    options = page.locator(f"button:has-text('{aspect_ratio}'), div:has-text('{aspect_ratio}'), span:has-text('{aspect_ratio}')").filter(has_not=dropdown_btn)
                    count = await options.count()
                
                clicked = False
                suffixes = ["Dọc", "Portrait", "Rộng", "Wide", "Vuông", "Square", "Cao", "Tall", "Màn hình rộng", "Widescreen"]
                
                for i in range(count):
                    opt = options.nth(i)
                    if await opt.is_visible(timeout=500):
                        text_val = await opt.inner_text()
                        text_strip = text_val.strip()
                        if len(text_strip) < 30 and (any(s in text_strip for s in suffixes) or count > 0):
                            await human_click(opt, page)
                            print(f'✅ Đã đổi tỉ lệ khung hình ảnh thành: {aspect_ratio} ({text_strip})')
                            clicked = True
                            break
                
                # Fallback dùng XPath tìm mọi thẻ chứa text tỉ lệ nhưng có chữ ngắn
                if not clicked:
                    fallbacks = page.locator(f"xpath=//*[contains(text(), '{aspect_ratio}')]").filter(has_not=dropdown_btn)
                    f_count = await fallbacks.count()
                    for i in range(f_count):
                        fb = fallbacks.nth(i)
                        if await fb.is_visible(timeout=500):
                            t_val = await fb.inner_text()
                            t_strip = t_val.strip()
                            if len(t_strip) < 30:
                                await human_click(fb, page)
                                print(f'✅ Đã đổi tỉ lệ bằng fallback thành: {aspect_ratio} ({t_strip})')
                                clicked = True
                                break
    except Exception as e:
        print(f'⚠️ Bỏ qua chọn Tỉ lệ ảnh: {e}')

async def process_prompt_to_image_grok_async(page: Page, item: dict, log_callback=print) -> bool:
    """
    Xử lý tạo ảnh bằng Playwright:
    1. Chọn model Advanced/Pro nếu có.
    2. Chọn tab Hình ảnh và Tỉ lệ khung hình từ cấu hình.
    3. Upload ảnh nhân vật/tham chiếu (nếu có).
    4. Nhập Prompt mô phỏng người thật.
    5. Nhấp nút Generate và chờ ảnh mới xuất hiện.
    6. Đánh chặn download của Playwright để lưu file trực tiếp.
    7. Kiểm tra kích thước và tỉ lệ ảnh bằng Pillow.
    """
    JS_GET_STT_IMAGE = """
    (stt) => {
        const tag = `||${stt}||`;
        const userMsg = Array.from(document.querySelectorAll('*')).find(el => 
            el.children.length === 0 && el.textContent && el.textContent.includes(tag)
        ) || Array.from(document.querySelectorAll('*')).find(el => 
            el.textContent && el.textContent.includes(tag) && el.textContent.length < 300
        );
        if (!userMsg) return null;
        
        let userBox = userMsg;
        while (userBox && userBox.parentElement && userBox.tagName !== 'BODY') {
            const cl = (userBox.className && typeof userBox.className === 'string') ? userBox.className.toLowerCase() : '';
            if (cl.includes('message') || userBox.getAttribute('message-id') || userBox.tagName === 'ARTICLE') break;
            userBox = userBox.parentElement;
        }
        
        let current = userBox;
        while (current = current.nextElementSibling) {
            const img = Array.from(current.querySelectorAll('img')).find(im => {
                const src = (im.src || '').toLowerCase();
                const alt = (im.alt || '').toLowerCase();
                const isGen = alt.includes("generated") || src.includes("/generated/") || src.startsWith("data:image/");
                const isRefOrPart = src.includes("/content") || src.includes("-part-") || src.includes("preview_image");
                const isLarge = (im.naturalWidth || 0) >= 300 && (im.naturalHeight || 0) >= 300;
                return isGen && !isRefOrPart && isLarge;
            });
            if (img) return img.src;
            
            const cl = (current.className && typeof current.className === 'string') ? current.className.toLowerCase() : '';
            const isMsg = cl.includes('message') || current.getAttribute('message-id') || current.tagName === 'ARTICLE';
            if (isMsg) break;
        }
        return null;
    }
    """

    try:
        stt = item.get("STT")
        prompt_text = item.get("prompt")
        save_path = item.get("save_path")
        output_folder = item.get("output_folder")
        image_paths = item.get("image_paths", [])

        os.makedirs(output_folder, exist_ok=True)

        # --- 0. CLICK NÚT SAVED ĐỂ DỌN CONTEXT / PARENT ID TRANH BỊ DÍNH ---
        try:
            btn_saved = page.locator("button[aria-label='Saved'], button[aria-label='Đã lưu'], button:has-text('Saved'), button:has-text('Đã lưu')").first
            if await btn_saved.is_visible(timeout=3000):
                await human_click(btn_saved, page)
                log_callback(f"➡️ Đã click nút Đã lưu (Saved)(STT {stt})")
                await page.wait_for_timeout(random.uniform(2000, 3000))
            else:
                log_callback(f"⚠️ Không tìm thấy nút Saved trên UI (STT {stt}).")
        except Exception as e:
            log_callback(f"⚠️ Lỗi click chuyển context /saved (STT {stt}): {e}")

        # --- ĐĂNG KÝ BỘ CHẶN NETWORK NATIVE ĐỂ TỰ ĐỘNG BẮT ẢNH ---
        if not hasattr(page, 'grok_image_urls'):
            page.grok_image_urls = []
        if not hasattr(page, 'grok_image_results'):
            page.grok_image_results = {}
            
            async def on_response(response):
                try:
                    # 1. Chặn phản hồi assets.grok.com để lưu các ảnh thực tế được sinh ra (bỏ qua preview_image, content, part)
                    if "assets.grok.com" in response.url:
                        if "/generated/" in response.url and "/content" not in response.url and "-part-" not in response.url and "preview_image" not in response.url:
                            if response.url not in page.grok_image_urls:
                                page.grok_image_urls.append(response.url)
                                
                    # 2. Chặn các luồng nhắn tin (giống bên Video) để bắt ảnh theo STT tag cực kỳ chuẩn xác
                    elif ("rest/app-chat/conversations/new" in response.url or "/messages/new" in response.url) and response.request.method == "POST":
                        post_data = response.request.post_data
                        if post_data:
                            match_stt = re.search(r'\|\|(.*?)\|\|', post_data)
                            if match_stt:
                                stt_key = match_stt.group(1).strip()
                                page.grok_image_results[stt_key] = {'status': 'running'}
                                try:
                                    text = await asyncio.wait_for(response.text(), timeout=120.0)
                                    
                                    # Lấy relative imageUrl trong stream JSON (chỉ lấy image.jpg, loại bỏ preview_image.jpg, -part-)
                                    matches = re.findall(r'"imageUrl"\s*:\s*"([^"]+)"', text)
                                    valid_rel_urls = []
                                    for rel in matches:
                                        if "preview_image" not in rel and "-part-" not in rel and "/content" not in rel:
                                            valid_rel_urls.append(rel)
                                    
                                    if valid_rel_urls:
                                        abs_url = "https://assets.grok.com/" + valid_rel_urls[-1]
                                        page.grok_image_results[stt_key] = {'status': 'success', 'url': abs_url}
                                        if abs_url not in page.grok_image_urls:
                                            page.grok_image_urls.append(abs_url)
                                        return
                                            
                                    # Thử tìm kiếm absolute url trong text stream
                                    found_abs = re.findall(r'https://assets\.grok\.com/([^\s"\'}]+)', text)
                                    valid_abs_paths = []
                                    for path in found_abs:
                                        if "generated" in path and "preview_image" not in path and "-part-" not in path and "content" not in path:
                                            valid_abs_paths.append(path)
                                            
                                    if valid_abs_paths:
                                        abs_url = "https://assets.grok.com/" + valid_abs_paths[-1]
                                        page.grok_image_results[stt_key] = {'status': 'success', 'url': abs_url}
                                        if abs_url not in page.grok_image_urls:
                                            page.grok_image_urls.append(abs_url)
                                        return
                                    page.grok_image_results[stt_key] = {'status': 'error', 'msg': 'Không tìm thấy imageUrl'}
                                except Exception as e:
                                    page.grok_image_results[stt_key] = {'status': 'error', 'msg': str(e)}
                except:
                    pass
            page.on("response", on_response)




        # --- 3. LẤY TEXTBOX VÀ TẬP TRUNG ---
        textbox = page.locator("form textarea, form [contenteditable='true'], [role='textbox']").first
        await textbox.wait_for(state='visible', timeout=15000)
        await human_click(textbox, page)
        await page.wait_for_timeout(500)

        # Tự động cấu hình Tab Hình ảnh và Aspect Ratio
        await setup_image_format_ui(page)

        # --- 4. DỌN SẠCH CÁC ẢNH ĐÍNH KÈM CŨ (NẾU CÓ KẸT) ---
        try:
            remove_btns = page.locator("button[aria-label='Remove image']")
            count = await remove_btns.count()
            if count > 0:
                for _ in range(count):
                    await remove_btns.nth(0).click(timeout=1000)
                    await page.wait_for_timeout(200)
        except:
            pass

        # --- 5. TẢI LÊN ẢNH THAM CHIẾU (NẾU CÓ) ---
        if image_paths:
            log_callback(f"☁️ Đang upload {len(image_paths)} ảnh tham chiếu nhân vật cho STT {stt}...")
            await paste_images_to_chat(page, image_paths)
            await page.wait_for_timeout(3000) # Đợi một lát cho ảnh load lên UI


        
        # --- 6. NHẬP PROMPT ---
        id_tag = f"||{stt}||"
        full_prompt = f"{id_tag} {prompt_text}"
        await textbox.fill("")
        await human_type(textbox, full_prompt, page)
        await page.wait_for_timeout(random.uniform(1000, 2000))

        # --- 6.5. ĐỊNH DẠNG TỈ LỆ ẢNH THAM CHIẾU (CHỈ KHI CÓ ĐÚNG 1 ẢNH) ---
        if image_paths and len(image_paths) == 1:
            try:
                system_cfg = config.global_settings.get('system', {})
                aspect_ratio = system_cfg.get('aspect_ratio', '16:9') # Mặc định 16:9
                
                # Tìm tất cả các nút Aspect Ratio của ảnh tham chiếu
                ratio_selectors = page.locator("button[aria-label='Aspect Ratio'], button[aria-label='Tỷ lệ khung hình']")
                count = await ratio_selectors.count()
                
                if count > 0:
                    log_callback(f"🖼️ [Grok] Phát hiện {count} ảnh tham chiếu. Tiến hành chọn tỉ lệ {aspect_ratio}...")
                    for i in range(count):
                        btn = ratio_selectors.nth(i)
                        if await btn.is_visible(timeout=2000):
                            await human_click(btn, page)
                            await page.wait_for_timeout(800)
                            
                            # Ưu tiên tìm các phần tử tỉ lệ nằm trong popup menu nổi để tránh click nhầm vào các thẻ/card ở nền
                            options = page.locator("[role='menu'] *, [role='listbox'] *, [role='dialog'] *, [class*='menu'] *, [class*='popover'] *, .popover *").filter(has_text=re.compile(rf"^{aspect_ratio}"))
                            count_opt = await options.count()
                            
                            # Nếu không tìm thấy trong menu nổi, fallback tìm tất cả các thẻ chứa tỉ lệ có hậu tố Dọc/Ngang/Vuông...
                            if count_opt == 0:
                                options = page.locator(f"button:has-text('{aspect_ratio}'), div:has-text('{aspect_ratio}'), span:has-text('{aspect_ratio}')").filter(has_not=btn)
                                count_opt = await options.count()
                            
                            clicked_opt = False
                            suffixes = ["Dọc", "Portrait", "Rộng", "Wide", "Vuông", "Square", "Cao", "Tall", "Màn hình rộng", "Widescreen"]
                            
                            for j in range(count_opt):
                                opt = options.nth(j)
                                if await opt.is_visible(timeout=500):
                                    text_val = await opt.inner_text()
                                    text_strip = text_val.strip()
                                    # Chỉ click nếu là option của menu (chứa hậu tố tỉ lệ hoặc nằm trong menu nổi)
                                    if len(text_strip) < 30 and (any(s in text_strip for s in suffixes) or count_opt > 0):
                                        await human_click(opt, page)
                                        log_callback(f"✅ [Grok] Đã định dạng ảnh tham chiếu thứ {i+1} về tỉ lệ {aspect_ratio} ({text_strip}).")
                                        await page.wait_for_timeout(500)
                                        clicked_opt = True
                                        break
                            
                            # Cực kỳ dự phòng: click phần tử đầu tiên thỏa mãn nếu không cái nào khớp hậu tố
                            if not clicked_opt and count_opt > 0:
                                for j in range(count_opt):
                                    opt = options.nth(j)
                                    if await opt.is_visible(timeout=500):
                                        text_strip = (await opt.inner_text()).strip()
                                        if len(text_strip) < 30:
                                            await human_click(opt, page)
                                            log_callback(f"✅ [Grok] Click dự phòng tỉ lệ: {text_strip}")
                                            await page.wait_for_timeout(500)
                                            break
            except Exception as e:
                log_callback(f"⚠️ [Grok] Lỗi thiết lập tỉ lệ ảnh tham chiếu: {e}")
                pass

        # --- 7. BẤM GỬI ---
        btn_gen = page.locator("form div.absolute.right-2 button, form button[type='submit']").last
        if await btn_gen.is_visible(timeout=2000):
            # Chờ nút Submit sáng lên (Đợi ảnh upload lên server xong)
            submit_enabled = False
            for _ in range(15):
                if await btn_gen.is_enabled():
                    submit_enabled = True
                    break
                await page.wait_for_timeout(1000)
            
            if not submit_enabled:
                log_callback(f"⚠️ Nút Gửi bị khóa quá 15s (STT {stt}) do ảnh kẹt/lỗi mạng.")
                return False
                
            await human_click(btn_gen, page)
        else:
            await textbox.press("Enter")

        log_callback(f"🚀 Đã gửi yêu cầu vẽ ảnh STT {stt}...")
        
        # Đợi một chút ngắn để request thực sự được gửi đi và thiết lập baseline chuẩn xác nhất
        await page.wait_for_timeout(1000)

        # Baseline danh sách URL bắt được và DOM trước khi ảnh mới thực sự bắt đầu sinh
        old_captured_urls = list(page.grok_image_urls)
        
        old_dom_urls = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('img')).map(img => ({
                src: img.src || '',
                alt: img.alt || '',
                nw: img.naturalWidth || 0,
                nh: img.naturalHeight || 0
            })).filter(info => {
                const src = info.src.toLowerCase();
                const alt = info.alt.toLowerCase();
                const isGen = (alt.includes("generated") || src.includes("/generated/") || src.startsWith("data:image/"));
                const isRefOrPart = (src.includes("/content") || src.includes("-part-"));
                const isLarge = info.nw >= 300 && info.nh >= 300;
                return isGen && !isRefOrPart && isLarge;
            }).map(info => info.src);
        }""")
        old_dom_set = set(old_dom_urls)
        
        # --- 8. CHỜ ĐỢI ẢNH MỚI XUẤT HIỆN ---
        image_generated = False
        wait_limit = max(60, config.global_settings['system']['wait_time'])
        start_wait = time.time()
        
        captured_url = None
        
        while time.time() - start_wait < wait_limit:
            elapsed = time.time() - start_wait
            
            # 8.1. Kiểm tra kết quả bắt từ Request Stream (Ưu tiên số 1 tuyệt đối)
            if elapsed >= 5 and stt in page.grok_image_results:
                status_obj = page.grok_image_results[stt]
                if status_obj.get("status") == "success":
                    captured_url = status_obj.get("url")
                    image_generated = True
                    log_callback(f"🌐 Phát hiện ảnh mới qua Stream API: {captured_url[:80]}...")
                    break
                    
            # 8.2. Kiểm tra URL mới từ Network (Ưu tiên số 2)
            if elapsed >= 5:
                new_urls = [u for u in page.grok_image_urls if u not in old_captured_urls]
                if new_urls:
                    captured_url = new_urls[-1]
                    image_generated = True
                    log_callback(f"🌐 Phát hiện ảnh mới qua Network API: {captured_url[:80]}...")
                    break
                 
            # 8.3. Kiểm tra thẻ img qua DOM bằng liên kết khối tin nhắn STT (Ưu tiên số 3 cho tính chính xác tuyệt đối)
            if elapsed >= 5:
                try:
                    captured_url = await page.evaluate(f"""() => {{
                        const get_img = {JS_GET_STT_IMAGE};
                        return get_img("{stt}");
                    }}""")
                    if captured_url:
                        image_generated = True
                        log_callback(f"📸 Phát hiện ảnh mới qua DOM liên kết STT {stt}: {captured_url[:100]}...")
                        if not image_paths:
                            log_callback("⏳ Ảnh không tham chiếu: Đợi thêm 3 giây cho ảnh sinh xong hoàn toàn...")
                            await page.wait_for_timeout(3000)
                            captured_url = await page.evaluate(f"""() => {{
                                const get_img = {JS_GET_STT_IMAGE};
                                return get_img("{stt}");
                            }}""")
                            log_callback("✅ Đã cập nhật captured_url mới nhất sau khi đợi.")
                        break
                except Exception as e:
                    pass
                 
            # 8.4. Kiểm tra thẻ img qua DOM chung (Dự phòng cuối cùng)
            if elapsed >= 5:
                # Nếu không có ảnh tham chiếu (ảnh chay), ta đợi thêm 3s rồi mới quét DOM để ảnh sinh hoàn chỉnh hoàn toàn
                if not image_paths:
                    # Quét nhanh xem có ảnh nháp mới xuất hiện chưa
                    has_new = await page.evaluate(f"""() => {{
                        const srcs = Array.from(document.querySelectorAll('img')).map(img => img.src || '');
                        const old_set = new Set({list(old_dom_set)});
                        return srcs.some(src => {{
                            const s = src.toLowerCase();
                            const isGen = s.includes("/generated/") || s.startsWith("data:image/");
                            const isRef = s.includes("/content") || s.includes("-part-");
                            return isGen && !isRef && !old_set.has(src);
                        }});
                    }}""")
                    if has_new:
                        log_callback("⏳ Phát hiện ảnh nháp mới: Đợi thêm 3 giây cho ảnh sinh xong hoàn chỉnh...")
                        await page.wait_for_timeout(3000)
                
                # Quét DOM lấy danh sách ảnh sinh
                current_gen_images = []
                try:
                    current_gen_images = await page.evaluate("""() => {
                        return Array.from(document.querySelectorAll('img')).map(img => ({
                            src: img.src || '',
                            alt: img.alt || '',
                            nw: img.naturalWidth || 0,
                            nh: img.naturalHeight || 0
                        })).filter(info => {
                            const src = info.src.toLowerCase();
                            const alt = info.alt.toLowerCase();
                            const isGen = (alt.includes("generated") || src.includes("/generated/") || src.startsWith("data:image/"));
                            const isRefOrPart = (src.includes("/content") || src.includes("-part-") || src.includes("preview_image"));
                            const isLarge = info.nw >= 300 && info.nh >= 300;
                            return isGen && !isRefOrPart && isLarge;
                        }).map(info => info.src);
                    }""")
                except:
                    pass
                
                new_dom_images = [src for src in current_gen_images if src not in old_dom_set]
                if new_dom_images:
                    image_generated = True
                    captured_url = new_dom_images[0]
                    log_callback(f"📸 Phát hiện ảnh mới qua DOM dự phòng: {captured_url[:80]}...")
                    break
                
            # Diagnostic: In danh sách ảnh trên màn hình định kỳ 15 giây để gỡ lỗi
            if int(time.time() - start_wait) % 15 == 0:
                try:
                    c_count = await page.locator("img").count()
                    log_callback(f"🔍 [Diagnostic] Hiện có {c_count} ảnh trên trang.")
                except:
                    pass
                
            await page.wait_for_timeout(2000)

        if not image_generated:
            log_callback(f"❌ Timeout: Không thấy ảnh mới sinh cho STT {stt}.")
            return False

        # --- 9. TẢI ẢNH BẰNG HỆ THỐNG PHÁT HIỆN & GIẢI MÃ DOM SIÊU GỌN ---
        download_success = False
        download_method = "Unknown"
        
        # Thử giải mã trực tiếp nếu captured_url là base64
        if captured_url and captured_url.startswith("data:image/"):
            try:
                log_callback(f"🔮 Giải mã và lưu ảnh base64 trực tiếp từ captured_url...")
                if "," in captured_url:
                    encoded = captured_url.split(",", 1)[1]
                    with open(save_path, "wb") as f:
                        f.write(base64.b64decode(encoded))
                    log_callback(f"✅ Giải mã và lưu ảnh base64 thành công.")
                    download_success = True
                    download_method = "Base64_Direct"
            except Exception as e:
                log_callback(f"⚠️ Giải mã base64 trực tiếp thất bại: {e}")

        # Thử tải từ URL bắt được từ Network (nếu không phải base64 và chưa tải thành công)
        if not download_success and captured_url and not captured_url.startswith("data:"):
            try:
                log_callback(f"⏳ Đang tải ảnh trực tiếp từ URL: {captured_url[:80]}...")
                resp = await page.request.get(captured_url, timeout=15000)
                if resp.status == 200:
                    with open(save_path, "wb") as f:
                        f.write(await resp.body())
                    log_callback(f"✅ Tải ảnh từ URL thành công.")
                    download_success = True
                    download_method = "Playwright_HTTP"
            except Exception as e:
                log_callback(f"⚠️ Thử tải URL trực tiếp thất bại: {e}")

        # Thử trích xuất giải mã qua DOM (Đầy đủ và tối giản, giải quyết cả Grid base64 và HTTP fetch)
        if not download_success:
            await page.wait_for_timeout(4000) # Đợi ảnh hiển thị đầy đủ
            try:
                log_callback(f"🔮 Đang trích xuất ảnh sinh mới qua DOM...")
                fallback_src = captured_url if captured_url else ""
                result_obj = await page.evaluate(f"""async () => {{
                    const get_img = {JS_GET_STT_IMAGE};
                    let src_val = get_img("{stt}");
                    if (!src_val) {{
                        src_val = "{fallback_src}";
                    }}
                    if (!src_val) return null;
                    if (src_val.startsWith('data:image/')) {{
                        return {{ data: src_val, method: "DOM_Base64" }};
                    }}
                    
                    // Cách 1: Thử trích xuất bằng Canvas trực tiếp (Không tốn băng thông, tránh lỗi mạng/proxy)
                    try {{
                        const img = Array.from(document.querySelectorAll('img')).find(i => i.src === src_val);
                        if (img) {{
                            const canvas = document.createElement("canvas");
                            canvas.width = img.naturalWidth || img.width;
                            canvas.height = img.naturalHeight || img.height;
                            const ctx = canvas.getContext("2d");
                            ctx.drawImage(img, 0, 0);
                            const canvasData = canvas.toDataURL("image/jpeg", 0.95);
                            if (canvasData && canvasData.startsWith('data:image/')) {{
                                return {{ data: canvasData, method: "DOM_Canvas" }};
                            }}
                        }}
                    }} catch (e_canvas) {{
                        // Bỏ qua lỗi canvas để chuyển sang cách 2
                    }}
                    
                    // Cách 2: Tải thủ công trong trình duyệt và xuất sang Base64
                    try {{
                        const response = await fetch(src_val);
                        const blob = await response.blob();
                        return new Promise((resolve, reject) => {{
                            const reader = new FileReader();
                            reader.onloadend = () => resolve({{ data: reader.result, method: "DOM_Fetch" }});
                            reader.onerror = reject;
                            reader.readAsDataURL(blob);
                        }});
                    }} catch (e) {{
                        return null;
                    }}
                }}""")
                
                if result_obj and isinstance(result_obj, dict):
                    base64_data = result_obj.get("data")
                    dom_method = result_obj.get("method", "DOM_Extraction")
                    
                    if base64_data and "," in base64_data:
                        encoded = base64_data.split(",", 1)[1]
                        with open(save_path, "wb") as f:
                            f.write(base64.b64decode(encoded))
                        log_callback(f"✅ Giải mã và lưu ảnh thành công qua DOM [{dom_method}].")
                        download_success = True
                        download_method = dom_method
            except Exception as e:
                log_callback(f"⚠️ Trích xuất DOM thất bại: {e}")

        if not download_success:
            log_callback(f"❌ Lỗi: Không thể lưu được ảnh STT {stt} bằng bất kỳ phương thức nào.")
            return False

        # --- 10. KIỂM TRA CHẤT LƯỢNG ẢNH BẰNG PILLOW ---
        is_ok = False
        reason = ""
        width, height = 0, 0
        try:
            if not os.path.exists(save_path) or os.path.getsize(save_path) == 0:
                log_callback(f"❌ File ảnh không tồn tại hoặc rỗng sau khi tải.")
                return False

            with Image.open(save_path) as img:
                width, height = img.size
                if height == 0:
                    raise ValueError("Chiều cao ảnh bằng 0")
                
                actual_ratio = width / height
                
                # Lấy tỉ lệ mong muốn từ cấu hình để kiểm định động
                system_cfg = config.global_settings.get('system', {})
                cfg_ratio_str = system_cfg.get('aspect_ratio', '16:9')
                try:
                    rw, rh = map(float, cfg_ratio_str.split(':'))
                    expected_ratio = rw / rh
                except:
                    expected_ratio = 16.0 / 9.0
                    
                # Sai số cho phép đối với sản phẩm từ AI (±20%)
                lower_bound = expected_ratio * 0.8
                upper_bound = expected_ratio * 1.2
                
                if actual_ratio < lower_bound or actual_ratio > upper_bound:
                    reason = f"sai tỉ lệ khung hình ({cfg_ratio_str}) thực tế ({width}x{height} - {actual_ratio:.2f})"
                elif width < 300 or height < 300:
                    reason = f"kích thước quá nhỏ ({width}x{height})"
                else:
                    is_ok = True

            if not is_ok:
                log_callback(f"⚠️ Ảnh STT {stt} không đạt chuẩn: {reason}. Xóa ảnh lỗi.")
                if os.path.exists(save_path):
                    os.remove(save_path)
                return False

            log_callback(f"✅ Hoàn thành xuất sắc STT {stt} ({width}x{height}) [Phương pháp: {download_method}]")
            return True

        except Exception as e:
            log_callback(f"⚠️ Lỗi check ảnh (Pillow) STT {stt}: {e}")
            if os.path.exists(save_path):
                try:
                    os.remove(save_path)
                except Exception as ex:
                    log_callback(f"⚠️ Không thể xóa file ảnh lỗi: {ex}")
            return False

    except Exception as e:
        log_callback(f"❌ Lỗi ngoại lệ hệ thống xử lý STT {item.get('STT')}: {e}")
        if save_path and os.path.exists(save_path):
            try: os.remove(save_path)
            except: pass
        return False