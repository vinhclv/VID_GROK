import os
import time
import random
import json
import re
from PIL import Image
from playwright.async_api import Page, Locator
import config
from flow_captcha_solver.stealth import STEALTH_SCRIPT
from engine.tasks.helpers import human_click, human_type


# ==========================================
# ⚙️ CẤU HÌNH GIAO DIỆN VEO3 IMAGE
# ==========================================

async def setup_image_creation_mode_veo3(page: Page, log_callback=print) -> Page:
    log_callback("⚙️ [Veo3 Image] Đang kiểm tra giao diện làm việc...")
    
    try:
        pages = list(page.context.pages)
        for p in pages:
            if p != page and not p.is_closed():
                try: await p.close()
                except: pass
    except Exception:
        pass

    if not hasattr(page, 'auth_cache'):
        page.auth_cache = {}
        
    async def intercept_auth(request):
        if "aisandbox-pa.googleapis.com" in request.url:
            headers = request.headers
            if "authorization" in headers:
                page.auth_cache["authorization"] = headers["authorization"]
            if "x-goog-api-key" in headers:
                page.auth_cache["x-goog-api-key"] = headers["x-goog-api-key"]
    
    page.on("request", intercept_auth)

    try:
        if "/project/" not in page.url:
            create_btn = page.locator(
                "button:has-text('New project'), a:has-text('New project'), "
                "button:has-text('Dự án mới'), a:has-text('Dự án mới'), "
                "button:has-text('Tạo dự án'), a:has-text('Tạo dự án'), "
                "button:has-text('Create project'), a:has-text('Create project'), "
                "[aria-label*='New project'], [aria-label*='Dự án mới']"
            ).first
            try:
                if await create_btn.is_visible(timeout=10000):
                    log_callback("➡️ [Veo3 Image] Mở dự án mới trên Dashboard...")
                    await human_click(create_btn, page)
                    await page.wait_for_timeout(3000)

                    all_pages = list(page.context.pages)
                    if len(all_pages) > 1:
                        new_active_page = all_pages[-1]
                        for p in all_pages:
                            if p != new_active_page and not p.is_closed():
                                try: await p.close()
                                except: pass
                        page = new_active_page
            except Exception:
                pass

        textbox = page.locator("[role='textbox'], textarea, [contenteditable='true']").first
        try:
            await textbox.wait_for(state="visible", timeout=20000)
            log_callback("✅ [Veo3 Image] Giao diện dự án đã sẵn sàng!")
        except Exception:
            pass

        try:
            close_btn = page.locator("button:has-text('Agent'), button[aria-label*='Agent']").first
            if await close_btn.is_visible(timeout=1000):
                aria_pressed = await close_btn.get_attribute("aria-pressed")
                if aria_pressed == "true":
                    await human_click(close_btn, page)
                    log_callback("✅ [Veo3 Image] Đã tắt chế độ Agent.")
                    await page.wait_for_timeout(1000)
        except Exception:
            pass

        settings_pill_btn = page.locator("form button.ldbhld, button.ldbhld, button:has-text('Video -'), button:has-text('Image -')").first
        if await settings_pill_btn.is_visible(timeout=3000):
            await human_click(settings_pill_btn, page)
            await page.wait_for_timeout(1000)

            mode_btn = page.locator("button:has-text('Image'), [role='tab']:has-text('Image'), [id*='trigger-IMAGE']").first
            if await mode_btn.is_visible(timeout=2000):
                await human_click(mode_btn, page)
                log_callback("⚙️ [Veo3 Image] Tab: Image")
                await page.wait_for_timeout(500)

            # 2. Tự động chọn Aspect Ratio (16:9 / 9:16 / 1:1) từ cấu hình hệ thống
            system_cfg = config.global_settings.get('system', {})
            aspect_ratio = str(system_cfg.get('aspect_ratio', '16:9')).strip()

            ratio_btn = page.locator(f"button:has-text('{aspect_ratio}')").first
            try:
                if await ratio_btn.is_visible(timeout=2000):
                    await human_click(ratio_btn, page)
                    log_callback(f"⚙️ [Veo3 Image] Tỉ lệ: {aspect_ratio}")
                    await page.wait_for_timeout(800)
            except Exception:
                pass

            # 3. Tự động chọn số lượng x1
            qty_btn = page.locator("button:has-text('x1'), button:has-text('1x')").first
            try:
                if await qty_btn.is_visible(timeout=2000):
                    await human_click(qty_btn, page)
                    log_callback("⚙️ [Veo3 Image] Số lượng: x1")
                    await page.wait_for_timeout(800)
            except Exception:
                pass

            # 4. Kiểm tra và xuất log Model Tạo Ảnh
            try:
                model_menu_btn = page.locator("xpath=/html/body/div[3]/div/button").first
                if not await model_menu_btn.is_visible(timeout=1500):
                    model_menu_btn = page.locator("button:has-text('Imagen'), button:has-text('Veo'), button:has(i:has-text('arrow_drop_down'))").first

                if await model_menu_btn.is_visible(timeout=2000):
                    current_model = await model_menu_btn.text_content() or ""
                    log_callback(f"⚙️ [Veo3 Image] Model UI: {current_model.strip()}")
            except Exception:
                pass

    except Exception as e:
        log_callback(f"⚠️ [Veo3 Image] Bỏ qua cấu hình phụ UI: {e}")

    return page


# ==========================================
# 🛰️ RADAR JS INTERCEPTOR IMAGE
# ==========================================

async def inject_radar_js_veo3_image(page: Page):
    raw_interceptor = r"""
    (function() {
        window._python_results = window._python_results || {};
        window._completedSTTs = window._completedSTTs || new Set(); 
        window._activeMediaTasks = window._activeMediaTasks || {};
        window._authToken = window._authToken || "";
        window._isInterceptorInjected = window._isInterceptorInjected || false;

        if (window._isInterceptorInjected) return;
        window._isInterceptorInjected = true;
        console.log("%c[RADAR IMAGE] 🚀 ĐÃ BƠM RADAR BẮT TOKEN VÀ LINK ẢNH VEO3...", "color: #00ffff; font-size: 16px; font-weight: bold;");

        function processMediaData(data) {
            if (!data) return;
            let mediaArr = data.media || (data.result && data.result.media) || (data.workflows && data.workflows[0] && data.workflows[0].media) || [];
            if (!Array.isArray(mediaArr) && typeof mediaArr === 'object') mediaArr = [mediaArr];

            mediaArr.forEach(item => {
                let name = item?.name;
                let projectId = item?.projectId;
                let genObj = item?.image?.generatedImage || item?.generatedImage || item?.image || item;
                let meta = item?.mediaMetadata || {};
                let reqData = genObj?.requestData || meta?.requestData || {};
                
                let raw = reqData?.promptInputs?.[0]?.textInput || "";
                let rawPart = reqData?.promptInputs?.[0]?.structuredPrompt?.parts?.[0]?.text || "";
                let gen = genObj?.prompt || item?.prompt || meta?.mediaTitle || "";
                let fullText = `${raw} | ${rawPart} | ${gen}`;
                
                let match = fullText.match(/\|\|(.*?)\|\|/);
                let stt = match ? (match[1] || "").trim() : null;

                if (name && stt && projectId) {
                    window._activeMediaTasks[name] = { name: name, projectId: projectId, stt: stt };
                }

                let currentStt = stt || (name && window._activeMediaTasks[name]?.stt);

                let fileUrl = genObj?.servingUrl || genObj?.fifeUrl || genObj?.downloadUrl || 
                              item?.image?.servingUrl || item?.image?.fifeUrl || item?.servingUrl || meta?.servingUrl;

                if (fileUrl && currentStt && !window._completedSTTs.has(currentStt)) {
                    window._completedSTTs.add(currentStt);
                    window._python_results[currentStt] = fileUrl;
                    console.log("[RADAR IMAGE] 🎯 Tóm thành công URL Ảnh cho STT " + currentStt + ": " + fileUrl);
                }
            });
        }

        const origSend = XMLHttpRequest.prototype.send;
        XMLHttpRequest.prototype.send = function() {
            this.addEventListener('load', function() {
                const u = (this._intercept_url || "").toLowerCase();
                if (u.includes("image") || u.includes("media") || u.includes("batch") || u.includes("flow")) {
                    try {
                        let text = this.responseText.replace(/^\)\]\}'\n/, '');
                        let data = JSON.parse(text);
                        processMediaData(data);
                    } catch(e) {}
                }
            });
            origSend.apply(this, arguments);
        };

        const origFetch = window.fetch;
        window.fetch = async function(...args) {
            const rawUrl = args[0]?.url || args[0] || "";
            const u = (typeof rawUrl === 'string' ? rawUrl : rawUrl.toString()).toLowerCase();
            const response = await origFetch.apply(this, args);
            if (u.includes("image") || u.includes("media") || u.includes("batch") || u.includes("flow")) {
                const clone = response.clone();
                clone.text().then(text => {
                    try {
                        let cleaned = text.replace(/^\)\]\}'\n/, '');
                        let data = JSON.parse(cleaned);
                        processMediaData(data);
                    } catch(e) {}
                }).catch(e=>{});
            }
            return response;
        };

        const origOpen = XMLHttpRequest.prototype.open;
        XMLHttpRequest.prototype.open = function(method, url) {
            this._intercept_url = typeof url === 'string' ? url : url.toString();
            origOpen.apply(this, arguments);
        };
    })();
    """
    await page.evaluate(raw_interceptor)


# ==========================================
# 🚀 CORE ENGINE: BATCH SUBMIT & RADAR IMAGE
# ==========================================

async def process_image_veo3_batch(page: Page, file_batch: list, output_folder: str, log_callback=print):
    tasks = {}
    downloaded_urls = set()

    for item in file_batch:
        stt = str(item.get("STT", "")).strip()
        if not stt: continue

        save_path = item.get("save_path") or item.get("image_path") or ""
        raw_prompt = item.get("prompt") or item.get("visual_details") or ""
        prompt_text = re.sub(r"[\r\n]+", " ", str(raw_prompt)).strip()
        
        if os.path.exists(save_path):
            log_callback(f"⏭️ Bỏ qua STT {stt} (Đã có file ảnh output)")
            continue

        id_tag = f"||{stt}||"
        tasks[stt] = {
            "save_path": save_path,
            "id_tag": id_tag,
            "done": False,
            "original_item": item
        }
        try:
            textbox = page.locator("[role='textbox'], textarea, [contenteditable='true']").first
            await textbox.wait_for(state="visible", timeout=15000)

            try:
                remove_btns = page.locator("button:has(i:has-text('close')), button:has(i:has-text('clear')), button[aria-label*='Remove'], button[aria-label*='Clear']").first
                for _ in range(5):
                    if await remove_btns.is_visible(timeout=1000):
                        await human_click(remove_btns, page)
                        await page.wait_for_timeout(300)
                    else:
                        break
            except Exception:
                pass

            image_paths = item.get("image_paths", [])
            if image_paths:
                try:
                    file_input = page.locator("input[type='file']").first
                    await file_input.wait_for(state="attached", timeout=10000)
                    valid_paths = [p for p in image_paths if os.path.exists(p)]
                    if valid_paths:
                        log_callback(f"☁️ [Veo3 Image] Đang nạp {len(valid_paths)} ảnh tham chiếu STT {stt}, chờ Google xử lý...")
                        
                        upload_responses = []
                        def handle_upload_res(res):
                            if ("uploadImage" in res.url or "upload" in res.url) and res.status == 200:
                                upload_responses.append(res)

                        page.on("response", handle_upload_res)
                        try:
                            await file_input.set_input_files(valid_paths)
                            
                            # Vòng lặp chờ đếm đủ số response 200 OK từ Google (Tối đa 35s)
                            start_wait = time.time()
                            while len(upload_responses) < len(valid_paths) and time.time() - start_wait < 35:
                                await page.wait_for_timeout(500)
                                
                            await page.wait_for_timeout(2000)  # Đợi 2s để React commit mediaId vào Form State
                            log_callback(f"✅ [Veo3 Image] Đã hoàn tất upload {len(upload_responses)}/{len(valid_paths)} ảnh tham chiếu lên Google Flow!")
                        finally:
                            try: page.remove_listener("response", handle_upload_res)
                            except: pass
                except Exception as ex:
                    log_callback(f"❌ [Veo3 Image] Lỗi upload ảnh tham chiếu STT {stt}: {ex}")

            full_prompt = f"{id_tag} {prompt_text}"
            await textbox.fill("") 
            await human_type(textbox, full_prompt, page)
            await page.wait_for_timeout(random.uniform(1000, 2000))
            
            # Gửi yêu cầu chuẩn bằng duy nhất phím Enter
            await textbox.press("Enter")
            log_callback(f"🚀 [Veo3 Image] Đã gửi STT {stt}")
            await page.wait_for_timeout(random.uniform(4000, 5000))
            
        except Exception as e:
            log_callback(f"❌ Lỗi gửi Ảnh STT {stt}: {e}")
            tasks.pop(stt, None)

    if not tasks:
        return False, file_batch

    log_callback(f"⏳ [Veo3 Image] Chờ render {len(tasks)} ảnh qua Radar JS...")
    start_time = time.time()
    wait_time_limit = config.global_settings["system"]["wait_time"]
    
    while time.time() - start_time < wait_time_limit:
        limit_keywords = [
            "reached the limit", "reached your limit", "rate limit", "try again in",
            "quota exceeded", "out of credits", "too many requests", "đạt giới hạn", "vượt quá giới hạn"
        ]
        
        has_limit = await page.evaluate("""(keywords) => {
            const els = Array.from(document.querySelectorAll('div, p, span, h1, h2, h3, li, button'));
            return els.some(el => {
                if (el.children.length > 0) return false;
                const text = (el.textContent || '').toLowerCase();
                return keywords.some(kw => text.includes(kw));
            });
        }""", limit_keywords)
        
        if has_limit:
            log_callback("⚠️ [Veo3 Image] Phát hiện thông báo giới hạn (Rate Limit) trên Google Labs!", "WARNING")
            from utils.profile_state import RateLimitException
            cooldown_mins = config.global_settings["system"].get("rate_limit_cooldown_minutes", 120)
            raise RateLimitException("Dính giới hạn tạo ảnh trên Google Labs", cooldown_seconds=cooldown_mins * 60)

        active_tasks = [uid for uid, info in tasks.items() if not info["done"]]
        if not active_tasks:
            log_callback("✅ [Veo3 Image] Tất cả ảnh trong chunk này đã tải xong!")
            break

        js_results_str = await page.evaluate("JSON.stringify(window._python_results || {})")
        js_results = json.loads(js_results_str)

        for uid in active_tasks:
            info = tasks[uid]
            if uid in js_results:
                image_url = js_results[uid]
                if image_url in downloaded_urls: continue
                
                os.makedirs(os.path.dirname(info["save_path"]), exist_ok=True)
                log_callback(f"💾 [Veo3 Image] Bắt đầu tải file: STT {uid}")
                
                download_success = False
                try:
                    response = await page.request.get(image_url, timeout=30000)
                    if response.status == 200:
                        with open(info["save_path"], "wb") as f:
                            f.write(await response.body())
                        download_success = True
                except Exception as e:
                    log_callback(f"⚠️ [Veo3 Image] Lỗi tải HTTP STT {uid}: {e}")

                if download_success:
                    try:
                        is_ok = False
                        reason = ""
                        with Image.open(info["save_path"]) as img:
                            w, h = img.size
                            if h > 0 and w >= 300 and h >= 300:
                                is_ok = True
                            else:
                                reason = f"kích thước quá nhỏ ({w}x{h})"
                                
                        if is_ok:
                            log_callback(f"✅ [Veo3 Image] Tải thành công ảnh STT {uid} ({w}x{h}) -> {info['save_path']}")
                            info["done"] = True
                            downloaded_urls.add(image_url)
                        else:
                            log_callback(f"⚠️ [Veo3 Image] Ảnh STT {uid} lỗi: {reason}. Xóa file tải lại...")
                            if os.path.exists(info["save_path"]):
                                os.remove(info["save_path"])
                    except Exception as ex:
                        log_callback(f"❌ [Veo3 Image] Lỗi mở file Pillow STT {uid}: {ex}")
                        if os.path.exists(info["save_path"]):
                            os.remove(info["save_path"])

        await page.wait_for_timeout(3000)

    failed_objects = [v["original_item"] for k, v in tasks.items() if not v["done"]]
    return len(failed_objects) == 0, failed_objects


async def handle_prompt_to_image_veo3_async(context, file_batch, assets_path, prefix_prompt, url, log_callback):
    """
    Hàm Handler riêng biệt 100% chuyên xử lý TẠO ẢNH bằng Veo3 (Google Flow Image).
    """
    page = await context.new_page()
    await page.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => undefined });")
    
    try:
        await page.goto(url, timeout=60000)
        await page.wait_for_timeout(5000)
        if 'accounts.google.com' in page.url:
            log_callback('❌ Profile bị logout -> Dừng.')
            return (False, file_batch)

        CHUNK_SIZE = 4
        all_failed_objects = []
        total_items = len(file_batch)
        total_chunks = (total_items + CHUNK_SIZE - 1) // CHUNK_SIZE

        log_callback(f"📦 [Veo3 Image] Bắt đầu xử lý {total_items} image task, chia làm {total_chunks} chunk.")

        page = await setup_image_creation_mode_veo3(page, log_callback=log_callback)
        await inject_radar_js_veo3_image(page)
        await page.context.add_init_script(STEALTH_SCRIPT)

        for i in range(0, total_items, CHUNK_SIZE):
            chunk = file_batch[i:i + CHUNK_SIZE]
            chunk_index = (i // CHUNK_SIZE) + 1
            log_callback(f"▶️ --- [Veo3 Image] ĐANG CHẠY CHUNK {chunk_index}/{total_chunks} ---")

            is_chunk_ok, failed_in_chunk = await process_image_veo3_batch(page, chunk, assets_path, log_callback)
            all_failed_objects.extend(failed_in_chunk)

            if len(failed_in_chunk) > 1:
                log_callback("⚠️ [Veo3 Image] Phát hiện kẹt render! Reload trang...")
                await page.evaluate("localStorage.removeItem('_grecaptcha'); sessionStorage.clear();")
                await page.reload(timeout=60000)
                await page.wait_for_timeout(4000)
                page = await setup_image_creation_mode_veo3(page, log_callback=log_callback)
                await inject_radar_js_veo3_image(page)
                await page.context.add_init_script(STEALTH_SCRIPT)

            if i + CHUNK_SIZE < total_items:
                cooldown = random.randint(5000, 7000)
                log_callback(f"💤 Xong Chunk {chunk_index}. Nghỉ giải lao {cooldown//1000}s...")
                await page.wait_for_timeout(cooldown)

        if len(all_failed_objects) == total_items:
            log_callback("❌ [Veo3 Image] Toàn bộ ảnh trong lượt này đều thất bại.")
            return (False, all_failed_objects)

        return (True, all_failed_objects)
    except Exception as e:
        if e.__class__.__name__ == "RateLimitException":
            raise e
        log_callback(f'❌ Lỗi ở handle_prompt_to_image_veo3_async: {e}')
        return (False, file_batch)
    finally:
        try: await page.close()
        except: pass
