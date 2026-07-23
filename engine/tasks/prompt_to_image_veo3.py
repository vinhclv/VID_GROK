import os
import time
import random
import json
import re
from PIL import Image
from playwright.async_api import Page, Locator
import config

# ==========================================
# 🤖 HỆ THỐNG MÔ PHỎNG HÀNH VI NGƯỜI THẬT
# ==========================================

async def human_click(locator: Locator, page: Page, force: bool = False):
    """
    Mô phỏng click chuột của người thật bằng Virtual Mouse.
    """
    try:
        await locator.scroll_into_view_if_needed(timeout=5000)
        await locator.hover(timeout=5000)
        await page.wait_for_timeout(random.uniform(100, 300))
        await locator.click(delay=random.randint(50, 150), force=force)
    except Exception as e:
        print(f"⚠️ Chuyển sang click dự phòng: {e}")
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
        chunk = text[idx:idx+chunk_size]
        await locator.press_sequentially(chunk, delay=random.randint(5, 10))
        idx += chunk_size
        await page.wait_for_timeout(random.uniform(20, 50))
        if random.random() < 0.05:
            await page.wait_for_timeout(random.uniform(100, 200))
    await page.wait_for_timeout(random.uniform(200, 400))


# ==========================================
# ⚙️ CẤU HÌNH GIAO DIỆN & TIÊM RADAR JS VEO3
# ==========================================

async def setup_image_creation_mode_veo3(page: Page) -> Page:
    """
    Cấu hình giao diện vẽ ảnh Google Labs ImageFX và thiết lập Authorization Interceptor.
    Tự động dọn dẹp các tab thừa và chuyển sang tab mới khi bấm Tạo dự án.
    """
    print("⚙️ [Veo3] Đang cấu hình giao diện vẽ ảnh (Aspect Ratio / Model)...")
    
    # Dọn dẹp tất cả các tab rác trước đó trong context
    try:
        pages = list(page.context.pages)
        for p in pages:
            if p != page and not p.is_closed():
                try: await p.close()
                except: pass
    except Exception:
        pass

    # Thiết lập gián điệp để chộp lấy Header Auth của Google
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
        # 1. Tạo dự án (Chỉ bấm nếu nút add_2 hiển thị trên dashboard)
        create_btn = page.locator("i:has-text('add_2')").first
        if await create_btn.is_visible(timeout=5000):
            await human_click(create_btn, page)
            await page.wait_for_timeout(2500)

            # Nếu bấm nút add_2 mở ra Tab mới trong Chrome -> đóng tab cũ và lấy tab mới nhất
            all_pages = list(page.context.pages)
            if len(all_pages) > 1:
                new_active_page = all_pages[-1]
                for p in all_pages:
                    if p != new_active_page and not p.is_closed():
                        try: await p.close()
                        except: pass
                page = new_active_page
                print("✅ [Veo3] Đã chuyển sang Tab dự án mới và dọn dẹp Tab cũ.")

        # 2. Huỷ option tác nhân
        close_btn = page.locator("xpath=/html/body/div[1]/div[1]/div[5]/div/div/div/div/div[2]/div[1]/div/button[2]").first
        if await close_btn.is_visible(timeout=5000):
            aria_pressed = await close_btn.get_attribute("aria-pressed")
            if aria_pressed == "true":
                await human_click(close_btn, page)
                await page.wait_for_timeout(500)
                print("✅ [Veo3] Đã huỷ option tác nhân thành công.")
		
        # 3. Chọn chế độ
        mode_btn = page.locator("xpath=/html/body/div[1]/div[1]/div[5]/div/div/div/div/div[2]/div[2]/button[1]").last
        if await mode_btn.is_visible(timeout=5000):
            await human_click(mode_btn, page)
            await page.wait_for_timeout(500)

        # 4. Chọn hình ảnh
        image_btn = page.locator("i:has-text('image')").last
        if await image_btn.is_visible(timeout=5000):
            await human_click(image_btn, page)
            await page.wait_for_timeout(500)
        
        # 5. Tự động chọn Aspect Ratio từ cấu hình
        system_cfg = config.global_settings.get('system', {})
        aspect_ratio = system_cfg.get('aspect_ratio', '9:16') # Mặc định 16:9
        
        ratio_btn = page.locator("button", has_text=re.compile(rf"{aspect_ratio}$", re.IGNORECASE)).first
        if await ratio_btn.is_visible(timeout=5000):
            await human_click(ratio_btn, page)
            print(f"✅ [Veo3] Đã cấu hình Aspect Ratio qua UI: {aspect_ratio}")
            await page.wait_for_timeout(500)

        # 6. Tự động chọn số lượng ảnh là 1 (1x)
        qty_btn = page.locator("button", has_text=re.compile(r"1x$", re.IGNORECASE)).first
        if await qty_btn.is_visible(timeout=5000):
            await human_click(qty_btn, page)
            print("✅ [Veo3] Đã cấu hình số lượng ảnh tự động: 1x")
            await page.wait_for_timeout(500)

    except Exception as e:
        print(f"⚠️ [Veo3] Bỏ qua thiết lập Aspect Ratio / Số lượng: {e}")

    return page


async def inject_radar_js_veo3(page: Page):
    """
    Tiêm radar JS tối giản cướp cò API batchGenerateImages để bắt sống FifeURL ảnh chất lượng gốc.
    """
    js_interceptor = r"""
    (function() {
        window._python_results = window._python_results || {};
        window._completedSTTs = window._completedSTTs || new Set(); 
        window._isInterceptorInjected = window._isInterceptorInjected || false;

        if (window._isInterceptorInjected) return;
        window._isInterceptorInjected = true;
        console.log("%c[RADAR IMAGE] 🚀 ĐÃ BƠM RADAR BẮT FIFEURL VEO3...", "color: #00ffff; font-size: 16px; font-weight: bold;");

        // 1. CHẶN XHR
        const origSend = XMLHttpRequest.prototype.send;
        XMLHttpRequest.prototype.send = function() {
            this.addEventListener('load', function() {
                if (this._intercept_url && (this._intercept_url.includes("batchGenerateImages") || this._intercept_url.includes("flowMedia"))) {
                    try {
                        let text = this.responseText.replace(/^\)\]\}'\n/, '');
                        let data = JSON.parse(text);
                        let mediaArr = data.media || (data.result && data.result.media) || [];
                        
                        mediaArr.forEach(item => {
                            let genImage = item?.image?.generatedImage;
                            let raw = genImage?.requestData?.promptInputs?.[0]?.textInput || "";
                            let rawPart = genImage?.requestData?.promptInputs?.[0]?.structuredPrompt?.parts?.[0]?.text || "";
                            let gen = genImage?.prompt || "";
                            
                            let match = (`${raw} | ${rawPart} | ${gen}`).match(/\|\|(.*?)\|\|/);

                            if (match) {
                                let stt = (match[1] || "").trim();
                                let fifeUrl = genImage?.fifeUrl;
                                if (fifeUrl && stt && !window._completedSTTs.has(stt)) {
                                    window._completedSTTs.add(stt);
                                    window._python_results[stt] = fifeUrl;
                                    console.log("[RADAR IMAGE] 🎯 Tóm được FifeURL ảnh gốc cho STT " + stt + ": " + fifeUrl.substring(0, 80));
                                }
                            }
                        });
                    } catch(e) {}
                }
            });
            origSend.apply(this, arguments);
        };

        // 2. CHẶN FETCH
        const origFetch = window.fetch;
        window.fetch = async function(...args) {
            const url = args[0]?.url || args[0] || "";
            const response = await origFetch.apply(this, args);
            
            if (typeof url === 'string' && (url.includes("batchGenerateImages") || url.includes("flowMedia"))) {
                const clone = response.clone();
                clone.text().then(text => {
                    try {
                        let cleaned = text.replace(/^\)\]\}'\n/, '');
                        let data = JSON.parse(cleaned);
                        let mediaArr = data.media || [];
                        mediaArr.forEach(item => {
                            let genImage = item?.image?.generatedImage;
                            let raw = genImage?.requestData?.promptInputs?.[0]?.textInput || "";
                            let rawPart = genImage?.requestData?.promptInputs?.[0]?.structuredPrompt?.parts?.[0]?.text || "";
                            let gen = genImage?.prompt || "";
                            
                            let match = (`${raw} | ${rawPart} | ${gen}`).match(/\|\|(.*?)\|\|/);
                            if (match) {
                                let stt = (match[1] || "").trim();
                                let fifeUrl = genImage?.fifeUrl;
                                if (fifeUrl && stt && !window._completedSTTs.has(stt)) {
                                    window._completedSTTs.add(stt);
                                    window._python_results[stt] = fifeUrl;
                                    console.log("[RADAR IMAGE] 🎯 Tóm được FifeURL ảnh gốc qua Fetch cho STT " + stt + ": " + fifeUrl.substring(0, 80));
                                }
                            }
                        });
                    } catch(e) {}
                }).catch(e=>{});
            }
            return response;
        };

        // Tự động override phương thức open của XHR để lưu lại URL phục vụ so khớp trong send
        const origOpen = XMLHttpRequest.prototype.open;
        XMLHttpRequest.prototype.open = function(method, url) {
            this._intercept_url = typeof url === 'string' ? url : url.toString();
            origOpen.apply(this, arguments);
        };

    })();
    """
    await page.evaluate(js_interceptor)


# ==========================================
# 🚀 CORE ENGINE: BATCH SUBMIT & RADAR COLLECT
# ==========================================

async def process_image_veo3_batch(page: Page, file_batch: list, output_folder: str, log_callback=print):
    """
    Hàm sinh ảnh theo cơ chế Chunking của Flow (Google Labs ImageFX):
    - Submit 4 prompts liên tiếp bằng nhãn định danh ||STT||.
    - Quét và tải đồng thời 4 kết quả thông qua Radar JS.
    - Xác thực Pillow độ phân giải & Aspect Ratio.
    """
    tasks = {}
    downloaded_urls = set()

    # --- GIAI ĐOẠN 1: SUBMIT HÀNG LOẠT ---
    for item in file_batch:
        stt = str(item.get("STT", "")).strip()
        if not stt: continue

        save_path = item.get("save_path")
        prompt_text = item.get("prompt", "")
        
        if os.path.exists(save_path):
            log_callback(f"⏭️ Bỏ qua STT {stt} (Đã có ảnh)")
            continue

        id_tag = f"||{stt}||"
        tasks[stt] = {
            "save_path": save_path,
            "id_tag": id_tag,
            "done": False,
            "original_item": item
        }
        try:
            # 1. Định vị Textbox vẽ ảnh (Robust selectors matching VideoFX)
            textbox = page.locator("[role='textbox'], textarea, [contenteditable='true']").first
            await textbox.wait_for(state="visible", timeout=15000)

            # 1.5. Xử lý ảnh tham chiếu (Upload / Dọn dẹp cũ)
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
                log_callback(f"☁️ [Veo3] Đang tải lên {len(image_paths)} ảnh tham chiếu cho STT {stt}...")
                try:
                    file_input = page.locator("input[type='file']").first
                    await file_input.wait_for(state="attached", timeout=10000)
                    
                    valid_paths = [p for p in image_paths if os.path.exists(p)]
                    if valid_paths:
                        await file_input.set_input_files(valid_paths)
                        await page.wait_for_timeout(3000) # Đợi ảnh tải lên hiển thị
                        log_callback(f"✅ [Veo3] Đã upload ảnh tham chiếu thành công cho STT {stt}.")
                    else:
                        log_callback(f"⚠️ [Veo3] Không tìm thấy file vật lý cho ảnh tham chiếu: {image_paths}")
                except Exception as ex:
                    log_callback(f"❌ [Veo3] Lỗi khi upload ảnh tham chiếu STT {stt}: {ex}")

            # 2. Gõ Prompt mô phỏng người thật
            full_prompt = f"{id_tag} {prompt_text}"
            await textbox.fill("") 
            await human_type(textbox, full_prompt, page)
            await page.wait_for_timeout(random.uniform(1000, 2000))
            
            # 3. Bấm Submit (Generate) - Robust icon selectors matching VideoFX
            btn_gen = page.locator("i:has-text('arrow_forward'), button:has-text('arrow_forward'), button[type='submit']").first
            await btn_gen.wait_for(state="visible", timeout=15000)
            
            await human_click(btn_gen, page)
            log_callback(f"🚀 [Veo3] Đã gửi yêu cầu vẽ ảnh STT {stt}...")
            
            # Nghỉ ngơi ngắn chống spam giữa các lần bấm
            await page.wait_for_timeout(random.uniform(5000, 6000))
            
        except Exception as e:
            log_callback(f"❌ Lỗi gửi STT {stt}: {e}")
            tasks.pop(stt, None)

    if not tasks:
        return False, file_batch

    # --- GIAI ĐOẠN 2: THU HOẠCH ĐỒNG THỜI QUA RADAR JS ---
    log_callback(f"⏳ [Veo3] Chờ render {len(tasks)} ảnh qua Radar JS...")
    start_time = time.time()
    wait_time_limit = config.global_settings["system"]["wait_time"]
    
    while time.time() - start_time < wait_time_limit:
        # Check for rate limit
        limit_keywords = [
            "reached the limit", "reached your limit", "rate limit", "try again in",
            "limit of image", "standard limit", "quota exceeded", "out of credits", "too many requests",
            "đạt giới hạn", "vượt quá giới hạn", "thử lại sau", "đã hết lượt", "giới hạn tạo ảnh"
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
            log_callback("⚠️ [Veo3] Phát hiện thông báo giới hạn tạo ảnh (Rate Limit) trên trang Google Labs!", "WARNING")
            from utils.profile_state import RateLimitException
            cooldown_mins = config.global_settings["system"].get("rate_limit_cooldown_minutes", 120)
            raise RateLimitException("Dính giới hạn tạo ảnh trên Google Labs", cooldown_seconds=cooldown_mins * 60)

        active_tasks = [uid for uid, info in tasks.items() if not info["done"]]
        if not active_tasks:
            log_callback("✅ [Veo3] Tất cả ảnh trong chunk này đã tải xong!")
            break

        # Đọc dữ liệu từ Radar JS trong RAM trình duyệt
        js_results_str = await page.evaluate("JSON.stringify(window._python_results || {})")
        js_results = json.loads(js_results_str)

        for uid in active_tasks:
            info = tasks[uid]
            
            if uid in js_results:
                image_url = js_results[uid]
                
                if image_url in downloaded_urls:
                    continue
                
                os.makedirs(os.path.dirname(info["save_path"]), exist_ok=True)
                log_callback(f"💾 [Veo3] Phát hiện link ảnh, bắt đầu tải: STT {uid}")
                
                download_success = False

                # Tải ảnh gốc trực tiếp qua Playwright HTTP Request Context (Nhanh, xịn, gốc)
                try:
                    response = await page.request.get(image_url, timeout=15000)
                    if response.status == 200:
                        with open(info["save_path"], "wb") as f:
                            f.write(await response.body())
                        download_success = True
                except Exception as e:
                    log_callback(f"⚠️ [Veo3] Lỗi tải HTTP ảnh STT {uid}: {e}")

                # --- KIỂM TRA CHẤT LƯỢNG ẢNH BẰNG PILLOW ---
                if download_success:
                    try:
                        is_ok = False
                        reason = ""
                        with Image.open(info["save_path"]) as img:
                            w, h = img.size
                            if h > 0 and w >= 300 and h >= 300:
                                # Kiểm định Aspect Ratio
                                actual_ratio = w / h
                                system_cfg = config.global_settings.get('system', {})
                                cfg_ratio_str = system_cfg.get('aspect_ratio', '16:9')
                                try:
                                    rw, rh = map(float, cfg_ratio_str.split(':'))
                                    expected_ratio = rw / rh
                                except:
                                    expected_ratio = 16.0 / 9.0
                                    
                                lower_bound = expected_ratio * 0.8
                                upper_bound = expected_ratio * 1.2
                                
                                if actual_ratio < lower_bound or actual_ratio > upper_bound:
                                    reason = f"sai tỉ lệ ({cfg_ratio_str}) thực tế ({w}x{h})"
                                else:
                                    is_ok = True
                            else:
                                reason = f"kích thước quá nhỏ ({w}x{h})"
                                
                        if is_ok:
                            log_callback(f"✅ [Veo3] Thành công STT {uid} ({w}x{h})")
                            info["done"] = True
                            downloaded_urls.add(image_url)
                        else:
                            log_callback(f"⚠️ [Veo3] Ảnh STT {uid} lỗi: {reason}. Tiến hành xóa file.")
                            if os.path.exists(info["save_path"]):
                                os.remove(info["save_path"])
                    except Exception as ex:
                        log_callback(f"❌ [Veo3] Lỗi mở file Pillow STT {uid}: {ex}")
                        if os.path.exists(info["save_path"]):
                            os.remove(info["save_path"])
                else:
                    log_callback(f"❌ [Veo3] Không tải được ảnh cho STT {uid}")

        await page.wait_for_timeout(3000)

    # --- TỔNG KẾT BATCH ---
    failed_objects = [v["original_item"] for k, v in tasks.items() if not v["done"]]
    return len(failed_objects) == 0, failed_objects


