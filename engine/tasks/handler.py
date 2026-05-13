import os
import shutil
from engine.tasks.prompt_to_video import process_1_image_video_batch
from engine.tasks.srt_to_prompt import process_srt_to_prompt
from engine.tasks.prompt_to_image import process_prompt_to_image
import time
import re
import random
import config
from urllib.parse import urlparse

async def handle_1_image_prompt_video_async(context, file_batch, assets_path, prefix_prompt, url, log_callback):
    """
    Xử lý batch 1 image + prompt sang video (tự cấu hình timecode).
    """
    page = await context.new_page()
    await page.add_init_script("\n        Object.defineProperty(navigator, 'webdriver', {\n            get: () => undefined\n        });\n    ")
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
        log_callback(f'📦 Bắt đầu xử lý {total_items} video (1 Ảnh + Text), chia làm {total_chunks} chunk.')
        for i in range(0, total_items, CHUNK_SIZE):
            chunk = file_batch[i:i + CHUNK_SIZE]
            chunk_index = i // CHUNK_SIZE + 1
            log_callback(f'▶️ --- ĐANG CHẠY CHUNK {chunk_index}/{total_chunks} ---')
            is_chunk_ok, failed_in_chunk = await process_1_image_video_batch(page, chunk, assets_path, log_callback)
            all_failed_objects.extend(failed_in_chunk)

            if i + CHUNK_SIZE < total_items:
                cooldown = random.randint(5000, 7000)
                log_callback(f'💤 Xong Chunk {chunk_index}. Nghỉ giải lao {cooldown // 1000}s...')
                await page.wait_for_timeout(cooldown)
        if len(all_failed_objects) == total_items:
            log_callback('❌ Toàn bộ file trong lượt này đều thất bại.')
            return (False, all_failed_objects)
        return (True, all_failed_objects)
    except Exception as e:
        log_callback(f'❌ Lỗi ở handle_1_image_prompt_video: {e}')
        return (False, file_batch)
    finally:
        try:
            await page.close()
        except:
            pass

def handle_srt_to_prompt(driver, batch, assets_path, prefix_prompt, url, log_callback):
    try:
        if 'gemini.google.com' not in driver.current_url:
            driver.get(url)
            time.sleep(5)
    except Exception as e:
        log_callback(f'❌ Error opening Gemini page: {e}')
        return (False, batch)
    if 'accounts.google.com' in driver.current_url:
        log_callback('❌ Profile logged out -> Stopping.')
        return (False, batch)
    failed_list = list(batch)
    consecutive_errors = 0
    MAX_CONSECUTIVE_ERRORS = 3
    CHUNK_SIZE = config.global_settings['system']['loop_limit']
    chunks = [batch[i:i + CHUNK_SIZE] for i in range(0, len(batch), CHUNK_SIZE)]
    for chunk in chunks:
        chunk_ids = [item['STT'] for item in chunk]
        while True:
            try:
                success = process_srt_to_prompt(driver, chunk, log_callback)
                if success:
                    log_callback(f'✅ Xong chunk ID: {chunk_ids[0]} - {chunk_ids[-1]}')
                    for item in chunk:
                        if item in failed_list:
                            failed_list.remove(item)
                    consecutive_errors = 0
                    break
                else:
                    consecutive_errors += 1
                    log_callback(f'⚠️ Lỗi xử lý chunk {chunk_ids[0]}-{chunk_ids[-1]} (Lần {consecutive_errors}/{MAX_CONSECUTIVE_ERRORS})')
                    if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                        log_callback('💀 Gemini lỗi liên tiếp -> Đánh dấu Profile hỏng.')
                        return (False, failed_list)
                    log_callback('♻️ Refresh trang và thử lại chunk cũ...')
                    driver.refresh()
                    time.sleep(5)
            except Exception as e:
                log_callback(f'❌ Exception nghiêm trọng: {e}')
                consecutive_errors += 1
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    return (False, failed_list)
                driver.refresh()
                time.sleep(5)
    if len(failed_list) == len(batch):
        log_callback('❌ Thất bại toàn tập (0/{}) -> Profile hỏng.'.format(len(batch)))
        return (False, failed_list)
    return (True, failed_list)

def handle_prompt_to_image(driver, batch, assets_path, prefix_prompt, url, log_callback):
    """
    Xử lý Prompt -> Image. Quản lý vòng lặp và điều phối lỗi.
    """
    try:
        if 'gemini.google.com' not in driver.current_url:
            driver.get(url)
            time.sleep(5)
    except Exception as e:
        log_callback(f'❌ Lỗi mở trang: {e}')
        return (False, batch)
    if 'accounts.google.com' in driver.current_url:
        log_callback('❌ Profile bị logout -> Dừng.')
        return (False, batch)
    failed_total = list(batch)
    consecutive_errors = 0
    MAX_CONSECUTIVE_ERRORS = 7
    for item in batch:
        stt = item['id']
        log_callback(f'🎨 [Image] Đang tạo ảnh cho STT {stt}...')
        success = process_prompt_to_image(driver, item, log_callback)
        if success:
            log_callback(f'✅ Xong ảnh STT: {stt}')
            if item in failed_total:
                failed_total.remove(item)
            consecutive_errors = 0
        else:
            consecutive_errors += 1
            log_callback(f'⚠️ Lỗi xử lý STT {stt} ({consecutive_errors}/{MAX_CONSECUTIVE_ERRORS})')
            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                log_callback('💀 Profile lỗi liên tiếp quá nhiều -> Dừng.')
                return (False, failed_total)
            driver.refresh()
            time.sleep(5)
    if len(failed_total) == len(batch):
        log_callback('❌ Thất bại toàn bộ batch.')
        return (False, failed_total)
    return (True, failed_total)