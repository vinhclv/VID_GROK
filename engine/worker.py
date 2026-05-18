import os

from engine.browser  import init_driver_from_profile

from engine.browser_playright import init_driver_from_profile_playwright
import time
from engine.tasks.handler import handle_srt_to_prompt, handle_prompt_to_image, handle_1_image_prompt_video_async
import asyncio

def run_worker_task(profile_folder, batch, task_type, assets_path, prompt, url, profiles_dir, stop_event, log_callback):
    """
    Worker đa năng: Chỉ lo việc quản lý vòng đời (Lifecycle) của Driver.
    Logic nghiệp vụ đẩy sang tasks_handler.
    """
    p_path = os.path.join(profiles_dir, profile_folder)
    
    def task_log(msg, level="INFO"):
        log_callback(f"[{profile_folder}] {msg}", level)

    task_log(f"🚀 Khởi động (Task: {task_type})...")

    # --- NẾU LÀ STRETCH VIDEO: CHẠY LOCAL FFMPEG VÀ RETURN LUÔN ---
    if task_type == "stretch_video":
        from utils.stretch_video import handle_stretch_video
        is_healthy, failed_items = handle_stretch_video(batch, assets_path, task_log)
        return is_healthy, failed_items

    # --- NẾU LÀ PLAYWRIGHT: ĐẨY SANG CẦU NỐI VÀ RETURN LUÔN ---
    if task_type in ["1_image_prompt_video"]:
        is_healthy, failed_items = run_playwright_batch_sync(
            p_path, batch, assets_path, prompt, url, task_log, task_type
        )
        task_log("Đóng trình duyệt Playwright.", "INFO")
        return is_healthy, failed_items


    # --- NẾU LÀ SELENIUM: GIỮ NGUYÊN LOGIC CŨ ---
    driver = init_driver_from_profile(p_path, log_callback=lambda m: task_log(m))
    if not driver:
        return False, list(batch) 

    failed_items = list(batch)
    is_healthy = True
    prompt = prompt or ""
    try:
        # 2. ĐIỀU HƯỚNG CHIẾN LƯỢC (ROUTING)
        # Đây là chỗ giúp bạn mở rộng dễ dàng. Thêm task mới chỉ cần thêm if/else
        
        if task_type == "srt_prompt": 
            is_healthy, failed_items = handle_srt_to_prompt(driver, batch, assets_path, prompt, url, task_log)

        elif task_type == "prompt_image":
            is_healthy, failed_items = handle_prompt_to_image(driver, batch, assets_path, prompt, url, task_log)
        else:
            task_log(f"❌ Loại task '{task_type}' chưa được hỗ trợ!", "ERROR")
            return True, failed_items # Trả về nhưng không đánh dấu hỏng profile

    except Exception as e:
        task_log(f"🔥 CRASH WORKER: {e}", "ERROR")
        is_healthy = False
        failed_items = list(batch) # Coi như hỏng hết batch này
        
    finally:
        try: driver.quit()
        except: pass
        task_log("Đóng trình duyệt.", "INFO")

    return is_healthy, failed_items


async def playwright_lifecycle_manager(profile_path, file_batch, assets_path, prefix_prompt, url, log_callback, task_type):
    """
    Hàm này lo vòng đời của Playwright: Khởi tạo -> Chạy Logic -> Đóng dọn.
    Nó giống hệt cái khung try...finally của Selenium bên dưới.
    """
    # Bước 1: Khởi tạo Context (Driver)
    context = await init_driver_from_profile_playwright(profile_path, log_callback)
    if not context:
        return False, list(file_batch) # Lỗi ngay từ lúc bật profile

    try:
        # Bước 2: Truyền context vào Handler để làm nghiệp vụ chính
        # (Lưu ý: handle_prompt_to_video của Playwright giờ cũng phải là async def)
        if task_type == "1_image_prompt_video":
            is_healthy, failed_items = await handle_1_image_prompt_video_async(
                context, file_batch, assets_path, prefix_prompt, url, log_callback
            )
        return is_healthy, failed_items
        
    except Exception as e:
        log_callback(f"🔥 CRASH PLAYWRIGHT WORKER: {e}", "ERROR")
        return False, list(file_batch)
        
    finally:
        # Bước 3: Dọn dẹp
        try: 
            await context.close()
            if hasattr(context, 'playwright_instance'):
                await context.playwright_instance.stop()
        except: 
            pass


def run_playwright_batch_sync(profile_path, file_batch, assets_path, prefix_prompt, url, log_callback, task_type):
    """HÀM CẦU NỐI: Bọc Async vào Sync"""
    try:
        return asyncio.run(
            playwright_lifecycle_manager(profile_path, file_batch, assets_path, prefix_prompt, url, log_callback, task_type)
        )
    except Exception as e:
        # BẮT BUỘC PHẢI CÓ DÒNG NÀY ĐỂ BẮT ĐƯỢC BỆNH
        log_callback(f"🔥 CẦU NỐI PLAYWRIGHT CRASH: {e}", "ERROR")
        return False, list(file_batch)