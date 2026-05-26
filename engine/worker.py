import os
import time
import asyncio
from engine.browser_ix import init_driver_from_profile_playwright
from engine.tasks.handler import (
    handle_1_image_prompt_video_async,
    handle_srt_to_prompt_async,
    handle_prompt_to_image_async
)

def run_worker_task(profile_folder, batch, task_type, assets_path, prompt, url, profiles_dir, stop_event, log_callback):
    """
    Worker đa năng: Chỉ lo việc quản lý vòng đời (Lifecycle) của Driver.
    Toàn bộ tác vụ chạy bằng Playwright (trừ Stretch Video chạy local bằng FFmpeg).
    """
    p_path = os.path.join(profiles_dir, profile_folder)
    
    def task_log(msg, level="INFO"):
        log_callback(f"[{profile_folder}] {msg}", level)

    task_log(f"🚀 Khởi động (Task: {task_type})...")

    # --- NẾU LÀ STRETCH VIDEO HOẶC IMAGE TO VIDEO: CHẠY LOCAL FFMPEG VÀ RETURN LUÔN ---
    if task_type == "stretch_video":
        from utils.stretch_video import handle_stretch_video
        is_healthy, failed_items = handle_stretch_video(batch, assets_path, task_log)
        return is_healthy, failed_items

    if task_type == "image_to_video":
        from utils.stretch_video import handle_image_to_video
        is_healthy, failed_items = handle_image_to_video(batch, assets_path, task_log)
        return is_healthy, failed_items

    # --- NẾU LÀ CÁC TÁC VỤ DUYỆT WEB: CHẠY PLAYWRIGHT VÀ RETURN LUÔN ---
    if task_type in ["1_image_prompt_video", "srt_prompt", "prompt_image"]:
        is_healthy, failed_items = run_playwright_batch_sync(
            p_path, batch, assets_path, prompt, url, task_log, task_type
        )
        task_log("Đóng trình duyệt Playwright.", "INFO")
        return is_healthy, failed_items

    # Hỗ trợ dự phòng các task không xác định
    task_log(f"❌ Loại task '{task_type}' chưa được hỗ trợ!", "ERROR")
    return True, list(batch)


async def playwright_lifecycle_manager(profile_path, file_batch, assets_path, prefix_prompt, url, log_callback, task_type):
    """
    Hàm quản lý vòng đời Playwright: Khởi tạo -> Điều phối tác vụ -> Đóng dọn dẹp.
    """
    # Bước 1: Khởi tạo Context (Driver)
    context = await init_driver_from_profile_playwright(profile_path, log_callback)
    if not context:
        return False, list(file_batch) # Lỗi ngay từ lúc bật profile

    try:
        # Bước 2: Định tuyến và truyền context vào Handler thích hợp
        if task_type == "1_image_prompt_video":
            is_healthy, failed_items = await handle_1_image_prompt_video_async(
                context, file_batch, assets_path, prefix_prompt, url, log_callback
            )
        elif task_type == "srt_prompt":
            is_healthy, failed_items = await handle_srt_to_prompt_async(
                context, file_batch, assets_path, prefix_prompt, url, log_callback
            )
        elif task_type == "prompt_image":
            is_healthy, failed_items = await handle_prompt_to_image_async(
                context, file_batch, assets_path, prefix_prompt, url, log_callback
            )
        else:
            is_healthy, failed_items = True, list(file_batch)

        return is_healthy, failed_items
        
    except Exception as e:
        log_callback(f"🔥 CRASH PLAYWRIGHT WORKER: {e}", "ERROR")
        return False, list(file_batch)
        
    finally:
        # Bước 3: Dọn dẹp trình duyệt sạch sẽ
        try: 
            await context.close()
            if hasattr(context, 'playwright_instance'):
                await context.playwright_instance.stop()
        except: 
            pass


def run_playwright_batch_sync(profile_path, file_batch, assets_path, prefix_prompt, url, log_callback, task_type):
    """HÀM CẦU NỐI: Chuyển đổi môi trường Async sang Sync cho Bể luồng ThreadPool"""
    try:
        return asyncio.run(
            playwright_lifecycle_manager(profile_path, file_batch, assets_path, prefix_prompt, url, log_callback, task_type)
        )
    except Exception as e:
        log_callback(f"🔥 CẦU NỐI PLAYWRIGHT CRASH: {e}", "ERROR")
        return False, list(file_batch)