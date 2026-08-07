import os
import time
import random
import json
import base64
import re
from playwright.async_api import Page, Locator
import config
from flow_captcha_solver.stealth import STEALTH_SCRIPT
from engine.tasks.helpers import human_click, human_type

# ==========================================
# ⚙️ CẤU HÌNH GIAO DIỆN VEO3 VIDEO
# ==========================================

async def setup_video_creation_mode_veo3(page: Page, log_callback=print) -> Page:
    system_cfg = config.global_settings.get('system', {})
    target_model = system_cfg.get('veo3_model', 'Omni Flash')
    duration = system_cfg.get('veo3_duration', '10s')
    aspect_ratio = str(system_cfg.get('aspect_ratio', '16:9')).strip()
    video_count = 1

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
        # 1. Điều hướng tới Flow nếu chưa mở
        if "labs.google/fx/tools/flow" not in page.url:
            log_callback("➡️ [Veo3 Video] Đang điều hướng tới Google Flow...")
            await page.goto("https://labs.google/fx/tools/flow", wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(3000)

        # 2. Tạo dự án mới trên Dashboard nếu chưa vào /project/
        if "/project/" not in page.url:
            create_btn = page.locator(
                "button:has-text('New project'), a:has-text('New project'), "
                "button:has-text('Dự án mới'), a:has-text('Dự án mới'), "
                "button:has-text('Tạo dự án'), a:has-text('Tạo dự án'), "
                "button:has-text('Create project'), a:has-text('Create project'), "
                "[aria-label*='New project'], [aria-label*='Dự án mới']"
            ).first
            try:
                if await create_btn.is_visible(timeout=5000):
                    log_callback("➡️ [Veo3 Video] Mở dự án mới trên Dashboard...")
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

        textbox = page.locator("textarea, [contenteditable='true']").first
        try:
            await textbox.wait_for(state="visible", timeout=15000)
            log_callback("✅ [Veo3 Video] Giao diện dự án đã sẵn sàng!")
        except Exception:
            pass

        # 3. Tắt Agent nếu đang bật
        try:
            close_btn = page.locator("button:has-text('Agent'), button[aria-label*='Agent']").first
            if await close_btn.is_visible(timeout=1500):
                aria_pressed = await close_btn.get_attribute("aria-pressed")
                if aria_pressed == "true":
                    await human_click(close_btn, page)
                    log_callback("✅ [Veo3 Video] Đã tắt chế độ Agent.")
                    await page.wait_for_timeout(1000)
        except Exception:
            pass

        # 4. Mở Settings Pill & Cấu hình tuần tự
        settings_pill_btn = page.locator("form button.ldbhld, button.ldbhld, button:has-text('Video -'), button:has-text('Image -'), button:has-text('Video ·'), button:has-text('Image ·')").first
        if await settings_pill_btn.is_visible(timeout=3000):
            await human_click(settings_pill_btn, page)
            await page.wait_for_timeout(1500)

            # A. Tab Video via Radix ID
            mode_btn = page.locator("[id$='trigger-VIDEO']:not([id*='VIDEO_REFERENCES'])").first
            if await mode_btn.is_visible(timeout=2000):
                await human_click(mode_btn, page)
                log_callback("⚙️ [Veo3 Video] ✅ Tab: Video")
                await page.wait_for_timeout(600)
            else:
                # Fallback text
                fallback_mode = page.locator("button, [role='tab']").filter(has_text=re.compile(r"^Video$", re.I)).first
                if await fallback_mode.is_visible(timeout=1000):
                    await human_click(fallback_mode, page)
                    log_callback("⚙️ [Veo3 Video] ✅ Tab: Video (Fallback)")
                    await page.wait_for_timeout(600)

            # B. Aspect Ratio via Radix ID Map (LANDSCAPE = 16:9, PORTRAIT = 9:16)
            ratio_map = {'16:9': 'LANDSCAPE', '9:16': 'PORTRAIT'}
            ratio_trigger_id = ratio_map.get(aspect_ratio)
            ratio_success = False
            if ratio_trigger_id:
                ratio_btn = page.locator(f"[id*='trigger-{ratio_trigger_id}']").first
                try:
                    if await ratio_btn.is_visible(timeout=2000):
                        await human_click(ratio_btn, page)
                        log_callback(f"⚙️ [Veo3 Video] ✅ Tỉ lệ: {aspect_ratio}")
                        await page.wait_for_timeout(600)
                        ratio_success = True
                except Exception:
                    pass

            if not ratio_success:
                fallback_ratio = page.locator("button, [role='tab']").filter(has_text=re.compile(rf"^{re.escape(aspect_ratio)}$", re.I)).first
                try:
                    if await fallback_ratio.is_visible(timeout=1500):
                        await human_click(fallback_ratio, page)
                        log_callback(f"⚙️ [Veo3 Video] ✅ Tỉ lệ: {aspect_ratio} (Fallback)")
                        await page.wait_for_timeout(600)
                except Exception:
                    pass

            # C. Model Dropdown
            model_dropdown_btn = page.locator("xpath=/html/body/div[3]/div/button").first
            if not await model_dropdown_btn.is_visible(timeout=1500):
                model_dropdown_btn = page.locator("button:has-text('Veo'), button:has-text('Omni'), button:has(i:has-text('arrow_drop_down'))").first

            try:
                if await model_dropdown_btn.is_visible(timeout=2000):
                    await human_click(model_dropdown_btn, page)
                    await page.wait_for_timeout(800)

                    model_opt = page.locator("div[role='menuitem'] span").filter(has_text=re.compile(re.escape(target_model), re.I)).first
                    if not await model_opt.is_visible(timeout=1500):
                        model_opt = page.locator("div[role='menuitem'] button").filter(has_text=re.compile(re.escape(target_model), re.I)).first
                    if not await model_opt.is_visible(timeout=1500):
                        model_opt = page.locator("xpath=/html/body/div[4]/div/div[1]/div/button").first

                    if await model_opt.is_visible(timeout=2000):
                        await human_click(model_opt, page, force=True)
                        log_callback(f"⚙️ [Veo3 Video] ✅ Model UI: {target_model}")
                        await page.wait_for_timeout(600)
                    else:
                        await page.keyboard.press("Escape")
                        await page.wait_for_timeout(300)
            except Exception:
                pass

            # D. Duration
            dur_btn = page.locator("button.flow_tab_slider_trigger, button, [role='tab']").filter(has_text=re.compile(rf"^{re.escape(duration)}$", re.I)).first
            try:
                if await dur_btn.is_visible(timeout=2000):
                    await human_click(dur_btn, page)
                    log_callback(f"⚙️ [Veo3 Video] ✅ Thời lượng: {duration}")
                    await page.wait_for_timeout(600)
            except Exception:
                pass

            # E. Quantity x1 (Focus + Enter)
            target_qty_text = f"x{video_count}"
            qty_btn = page.locator("button.flow_tab_slider_trigger, button, [role='tab']").filter(has_text=re.compile(rf"^{re.escape(target_qty_text)}$", re.I)).first
            try:
                if await qty_btn.is_visible(timeout=2000):
                    await qty_btn.focus()
                    await page.keyboard.press("Enter")
                    log_callback(f"⚙️ [Veo3 Video] ✅ Số lượng: {target_qty_text}")
                    await page.wait_for_timeout(600)
            except Exception:
                pass

            # Đóng popup settings
            try:
                await page.keyboard.press("Escape")
                await page.wait_for_timeout(500)
            except Exception:
                pass

    except Exception as e:
        log_callback(f"⚠️ [Veo3 Video] Bỏ qua cấu hình phụ UI: {e}")

    return page


# ==========================================
# 🛰️ RADAR JS INTERCEPTOR VIDEO (OVERRIDE LITE)
# ==========================================

async def inject_radar_js_veo3_video(page: Page):
    system_cfg = config.global_settings.get('system', {})
    aspect_ratio_cfg = system_cfg.get('aspect_ratio', '16:9')

    raw_interceptor = r"""
    (function() {
        window._python_results = window._python_results || {};
        window._completedSTTs = window._completedSTTs || new Set(); 
        window._activeMediaTasks = window._activeMediaTasks || {};
        window._authToken = window._authToken || "";
        window._python_cfg_ratio = "__ASPECT_RATIO__";
        window._isInterceptorInjected = window._isInterceptorInjected || false;

        if (window._isInterceptorInjected) return;
        window._isInterceptorInjected = true;
        console.log("%c[RADAR VIDEO] 🚀 ĐÃ BƠM RADAR BẮT TOKEN & OVERRIDE PAYLOAD VIDEO (veo_3_1_lite)...", "color: #00ffff; font-size: 16px; font-weight: bold;");

        function processMediaData(data) {
            if (!data) return;
            let mediaArr = data.media || (data.result && data.result.media) || (data.workflows && data.workflows[0] && data.workflows[0].media) || [];
            if (!Array.isArray(mediaArr) && typeof mediaArr === 'object') mediaArr = [mediaArr];

            mediaArr.forEach(item => {
                let name = item?.name;
                let projectId = item?.projectId;
                let genObj = item?.video?.generatedVideo || item?.generatedVideo || item?.video || item;
                let meta = item?.mediaMetadata || {};
                let reqData = genObj?.requestData || meta?.requestData || {};
                let status = meta?.mediaStatus?.mediaGenerationStatus || "";
                
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

                let fileUrl = genObj?.servingUrl || genObj?.videoUrl || genObj?.downloadUrl || genObj?.fifeUrl || 
                              item?.video?.servingUrl || item?.video?.downloadUrl || item?.video?.fifeUrl || item?.videoUrl ||
                              item?.fifeUrl || item?.downloadUrl || meta?.servingUrl;

                if (!fileUrl && name && (status === "MEDIA_GENERATION_STATUS_SUCCESSFUL" || meta?.mediaBlobSize)) {
                    fileUrl = "https://labs.google/fx/api/trpc/media.getMediaUrlRedirect?name=" + name;
                }

                if (fileUrl && currentStt && !window._completedSTTs.has(currentStt)) {
                    window._completedSTTs.add(currentStt);
                    window._python_results[currentStt] = fileUrl;
                    console.log("[RADAR VIDEO] 🎯 Tóm thành công Video URL cho STT " + currentStt + ": " + fileUrl);
                }
            });
        }

        setInterval(async () => {
            const pendingIds = Object.keys(window._activeMediaTasks).filter(id => {
                const stt = window._activeMediaTasks[id].stt;
                return stt && !window._completedSTTs.has(stt);
            });
            if (pendingIds.length === 0) return;

            const payloadMedia = pendingIds.map(id => ({
                name: id,
                projectId: window._activeMediaTasks[id].projectId
            }));

            const reqHeaders = { "content-type": "text/plain;charset=UTF-8" };
            if (window._authToken) reqHeaders["authorization"] = window._authToken;

            try {
                const response = await fetch("https://aisandbox-pa.googleapis.com/v1/video:batchCheckAsyncVideoGenerationStatus", {
                    method: "POST",
                    headers: reqHeaders,
                    body: JSON.stringify({ media: payloadMedia })
                });

                if (response.ok) {
                    const text = await response.text();
                    const cleaned = text.replace(/^\)\]\}'\n/, '');
                    const data = JSON.parse(cleaned);
                    processMediaData(data);
                }
            } catch(e) {}
        }, 4000);

        const origSend = XMLHttpRequest.prototype.send;
        XMLHttpRequest.prototype.send = function() {
            this.addEventListener('load', function() {
                const u = (this._intercept_url || "").toLowerCase();
                if (u.includes("video") || u.includes("media") || u.includes("batch") || u.includes("flow") || u.includes("checkasync")) {
                    try {
                        let text = this.responseText.replace(/^\)\]\}'\n/, '');
                        let data = JSON.parse(text);
                        processMediaData(data);
                    } catch(e) {}
                }
            });
            origSend.apply(this, arguments);
        };

        const origSetHeader = XMLHttpRequest.prototype.setRequestHeader;
        XMLHttpRequest.prototype.setRequestHeader = function(header, value) {
            if (header && header.toLowerCase() === 'authorization') {
                window._authToken = value;
            }
            origSetHeader.apply(this, arguments);
        };

        const origFetch = window.fetch;
        window.fetch = async function(...args) {
            const rawUrl = args[0]?.url || args[0] || "";
            const options = args[1] || {};
            const u = (typeof rawUrl === 'string' ? rawUrl : rawUrl.toString()).toLowerCase();

            if (options.headers) {
                let authHeader = options.headers['authorization'] || options.headers['Authorization'];
                if (authHeader) window._authToken = authHeader;
            }

            if (options.body && (u.includes("video:batchasyncgeneratevideotext") || u.includes("video:batchasyncgeneratevideoreferenceimages"))) {
                try {
                    let payload = JSON.parse(options.body);
                    console.log("%c[RADAR VIDEO] 📡 Phát hiện request tạo Video, model UI giữ nguyên.", "color: #00ffff; font-weight: bold;");
                } catch(e) {}
            }

            const response = await origFetch.apply(this, args);
            if (u.includes("video") || u.includes("media") || u.includes("batch") || u.includes("flow") || u.includes("checkasync")) {
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
    js_interceptor = raw_interceptor.replace("__ASPECT_RATIO__", aspect_ratio_cfg)
    await page.evaluate(js_interceptor)


# ==========================================
# ☁️ PURE API IMAGE UPLOAD
# ==========================================

async def upload_pure_api_image(page: Page, file_path: str, project_id: str, log_callback=print) -> str:
    """Upload ảnh lên Google Flow qua Pure API, trả về mediaId."""
    try:
        if not os.path.exists(file_path):
            return None

        with open(file_path, "rb") as f:
            file_bytes = f.read()
        base64_content = base64.b64encode(file_bytes).decode("utf-8")

        file_name = os.path.basename(file_path)
        ext = os.path.splitext(file_path)[1].lower()
        mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
        mime_type = mime_map.get(ext, "image/png")

        payload = {
            "clientContext": {
                "projectId": project_id,
                "tool": "PINHOLE"
            },
            "imageBytes": base64_content,
            "isUserUploaded": True,
            "isHidden": False,
            "mimeType": mime_type,
            "fileName": file_name
        }

        headers = {
            "content-type": "text/plain;charset=UTF-8",
            "origin": "https://labs.google",
            "referer": "https://labs.google/"
        }

        if hasattr(page, 'auth_cache'):
            if "authorization" in page.auth_cache:
                headers["authorization"] = page.auth_cache["authorization"]
            if "x-goog-api-key" in page.auth_cache:
                headers["x-goog-api-key"] = page.auth_cache["x-goog-api-key"]

        response = await page.request.post(
            "https://aisandbox-pa.googleapis.com/v1/flow/uploadImage",
            headers=headers,
            data=json.dumps(payload)
        )

        if response.ok:
            text = await response.text()
            cleaned = text.lstrip(")]}'\n")
            data = json.loads(cleaned)
            media_id = None
            if "media" in data and "name" in data["media"]:
                media_id = data["media"]["name"]
            elif "workflow" in data and "metadata" in data.get("workflow", {}):
                media_id = data["workflow"]["metadata"].get("primaryMediaId")
            return media_id

        return None
    except Exception as e:
        log_callback(f"⚠️ [Veo3 Video] Lỗi Pure API upload: {e}")
        return None


# ==========================================
# 🚀 CORE ENGINE: BATCH SUBMIT & RADAR VIDEO
# ==========================================

async def process_video_veo3_batch(page: Page, file_batch: list, output_folder: str, log_callback=print):
    tasks = {}
    downloaded_urls = set()

    for item in file_batch:
        stt = str(item.get("STT", "")).strip()
        if not stt: continue

        save_path = item.get("save_path") or item.get("video_path") or ""
        raw_prompt = item.get("prompt") or item.get("visual_details") or ""
        prompt_text = re.sub(r"[\r\n]+", " ", str(raw_prompt)).strip()
        
        if os.path.exists(save_path):
            log_callback(f"⏭️ Bỏ qua STT {stt} (Đã có file video output)")
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

            # Upload ảnh tham chiếu qua UI input[type='file'] và bắt chính xác Network Response 200 OK từ Google
            image_paths = item.get("image_paths", [])
            valid_image_count = 0

            if image_paths:
                try:
                    file_input = page.locator("input[type='file']").first
                    await file_input.wait_for(state="attached", timeout=10000)
                    valid_paths = [p for p in image_paths if os.path.exists(p)]
                    if valid_paths:
                        log_callback(f"☁️ [Veo3 Video] Đang nạp {len(valid_paths)} ảnh tham chiếu STT {stt}, chờ Google xử lý...")
                        
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
                            valid_image_count = len(upload_responses)
                            if valid_image_count > 0:
                                log_callback(f"✅ [Veo3 Video] Đã hoàn tất upload {valid_image_count}/{len(valid_paths)} ảnh tham chiếu lên Google Flow!")
                            else:
                                log_callback(f"⚠️ [Veo3 Video] Không nhận được phản hồi upload ảnh từ Server Google (Timeout).")
                        finally:
                            try: page.remove_listener("response", handle_upload_res)
                            except: pass
                except Exception as ex:
                    log_callback(f"❌ [Veo3 Video] Lỗi nạp ảnh tham chiếu STT {stt} lên UI: {ex}")

            full_prompt = f"{id_tag} {prompt_text}"
            await textbox.fill("") 
            await human_type(textbox, full_prompt, page)
            await page.wait_for_timeout(random.uniform(1000, 2000))

            # Gửi qua UI: Click nút Submit Arrow
            submit_btn = page.locator("form button[type='submit'], button:has(i:has-text('arrow_forward')), form button:has(svg), button[aria-label*='Send'], button[aria-label*='Submit'], button[aria-label*='Generate']").last
            try:
                if await submit_btn.is_visible(timeout=2000):
                    # Chờ nút Submit sáng lên hẳn (nếu ảnh còn đang xử lý ngầm, nút sẽ bị disabled)
                    submit_ready = False
                    for _ in range(20):
                        if await submit_btn.is_enabled():
                            submit_ready = True
                            break
                        await page.wait_for_timeout(1000)

                    if not submit_ready:
                        log_callback(f"⚠️ [Veo3 Video] Nút Gửi bị khóa quá 20s (STT {stt}) do ảnh chưa xử lý xong.")
                        tasks.pop(stt, None)
                        continue

                    await human_click(submit_btn, page)
                    img_note = f" (kèm {valid_image_count} ảnh tham chiếu)" if valid_image_count else ""
                    log_callback(f"🚀 [Veo3 Video] Đã bấm Nút Gửi STT {stt}{img_note}")
                else:
                    await page.keyboard.press("Control+Enter")
                    await page.wait_for_timeout(500)
                    await textbox.press("Enter")
                    log_callback(f"🚀 [Veo3 Video] Đã gửi STT {stt} qua phím Enter")
            except Exception:
                await textbox.press("Enter")
                log_callback(f"🚀 [Veo3 Video] Đã gửi STT {stt}")
            await page.wait_for_timeout(random.uniform(3000, 5000))
            
        except Exception as e:
            log_callback(f"❌ Lỗi gửi Video STT {stt}: {e}")
            tasks.pop(stt, None)

    if not tasks:
        return False, file_batch

    log_callback(f"⏳ [Veo3 Video] Chờ render {len(tasks)} video qua Radar JS...")
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
            log_callback("⚠️ [Veo3 Video] Phát hiện thông báo giới hạn (Rate Limit) trên Google Labs!", "WARNING")
            from utils.profile_state import RateLimitException
            cooldown_mins = config.global_settings["system"].get("rate_limit_cooldown_minutes", 120)
            raise RateLimitException("Dính giới hạn tạo video trên Google Labs", cooldown_seconds=cooldown_mins * 60)

        active_tasks = [uid for uid, info in tasks.items() if not info["done"]]
        if not active_tasks:
            log_callback("✅ [Veo3 Video] Tất cả video trong chunk này đã tải xong!")
            break

        js_results_str = await page.evaluate("JSON.stringify(window._python_results || {})")
        js_results = json.loads(js_results_str)

        for uid in active_tasks:
            info = tasks[uid]
            if uid in js_results:
                image_url = js_results[uid]
                if image_url in downloaded_urls: continue
                
                os.makedirs(os.path.dirname(info["save_path"]), exist_ok=True)
                log_callback(f"💾 [Veo3 Video] Bắt đầu tải file: STT {uid}")
                
                download_success = False
                try:
                    response = await page.request.get(image_url, timeout=30000)
                    if response.status == 200:
                        with open(info["save_path"], "wb") as f:
                            f.write(await response.body())
                        download_success = True
                except Exception as e:
                    log_callback(f"⚠️ [Veo3 Video] Lỗi tải HTTP STT {uid}: {e}")

                if download_success and os.path.exists(info["save_path"]) and os.path.getsize(info["save_path"]) > 1000:
                    file_size = os.path.getsize(info["save_path"])
                    file_mb = round(file_size / (1024 * 1024), 2)
                    log_callback(f"✅ [Veo3 Video] Tải thành công video STT {uid} ({file_mb} MB) -> {info['save_path']}")
                    info["done"] = True
                    downloaded_urls.add(image_url)
                else:
                    log_callback(f"⏳ [Veo3 Video] Đang chờ Server xuất video hoàn chỉnh cho STT {uid}...")

        await page.wait_for_timeout(3000)

    failed_objects = [v["original_item"] for k, v in tasks.items() if not v["done"]]
    return len(failed_objects) == 0, failed_objects


async def handle_prompt_to_video_veo3_async(context, file_batch, assets_path, prefix_prompt, url, log_callback):
    """
    Hàm Handler riêng biệt 100% chuyên xử lý TẠO VIDEO bằng Veo3 (Google Flow).
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

        log_callback(f"📦 [Veo3 Video] Bắt đầu xử lý {total_items} video task, chia làm {total_chunks} chunk.")

        page = await setup_video_creation_mode_veo3(page, log_callback=log_callback)
        await inject_radar_js_veo3_video(page)
        await page.context.add_init_script(STEALTH_SCRIPT)

        for i in range(0, total_items, CHUNK_SIZE):
            chunk = file_batch[i:i + CHUNK_SIZE]
            chunk_index = (i // CHUNK_SIZE) + 1
            log_callback(f"▶️ --- [Veo3 Video] ĐANG CHẠY CHUNK {chunk_index}/{total_chunks} ---")

            is_chunk_ok, failed_in_chunk = await process_video_veo3_batch(page, chunk, assets_path, log_callback)
            all_failed_objects.extend(failed_in_chunk)

            if len(failed_in_chunk) > 1:
                log_callback("⚠️ [Veo3 Video] Phát hiện kẹt render! Reload trang...")
                await page.evaluate("localStorage.removeItem('_grecaptcha'); sessionStorage.clear();")
                await page.reload(timeout=60000)
                await page.wait_for_timeout(4000)
                page = await setup_video_creation_mode_veo3(page, log_callback=log_callback)
                await inject_radar_js_veo3_video(page)
                await page.context.add_init_script(STEALTH_SCRIPT)

            if i + CHUNK_SIZE < total_items:
                cooldown = random.randint(5000, 7000)
                log_callback(f"💤 Xong Chunk {chunk_index}. Nghỉ giải lao {cooldown//1000}s...")
                await page.wait_for_timeout(cooldown)

        if len(all_failed_objects) == total_items:
            log_callback("❌ [Veo3 Video] Toàn bộ video trong lượt này đều thất bại.")
            return (False, all_failed_objects)

        return (True, all_failed_objects)
    except Exception as e:
        if e.__class__.__name__ == "RateLimitException":
            raise e
        log_callback(f'❌ Lỗi ở handle_prompt_to_video_veo3_async: {e}')
        return (False, file_batch)
    finally:
        try: await page.close()
        except: pass
