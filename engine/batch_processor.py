# engine/batch_processor.py
import threading
import queue
import time
import os
import concurrent.futures

from config import DEFAULT_PROFILES
from utils.file_ops import get_srt_prompt_status, get_prompt_image_status, get_1_image_prompt_video_status, get_stretch_video_status
from engine.worker import run_worker_task
import config
class BatchProcessor:
    def __init__(self, stop_event, log_callback, update_status_callback):
        self.stop_event = stop_event
        self.log = log_callback
        self.update_status = update_status_callback
        
        self.task_queue = queue.Queue()
        self.file_lock = threading.Lock()
        self.profile_health = {}
        
        self.current_monitoring_info = None 

    def clear_task_queue(self):
        with self.task_queue.mutex:
            self.task_queue.queue.clear()
 
    def run_batch_logic(self, project_queue, loop_type, profiles, finished_callback):
        self.profile_health = {p: 0 for p in profiles}
        
        self.log(f"🚀 BẮT ĐẦU CHẠY: {len(project_queue)} DỰ ÁN", "INFO")

        for idx, project in enumerate(project_queue):
            if self.stop_event.is_set(): break
            
            input_path = project["input"]
            input2_path = project.get("input2", "")
            output_path = project["output"]
            prompt = project["prompt"]
            url = project["url"]
            languages = project["languages"]
            shuffle_gems = project["shuffle_gems"]
            
            self.update_status(idx, "Running ⏳")
            self.log(f"=== DỰ ÁN {idx+1}/{len(project_queue)}: {os.path.basename(input_path)} ===", "INFO")
            
            self.process_one_folder(input_path, input2_path, output_path, prompt, url, languages, loop_type, profiles, shuffle_gems)
            
            if self.stop_event.is_set():
                self.update_status(idx, "Stopped 🛑")
            else:
                self.update_status(idx, "Done ✅")
                self.log(f"🏁 Xong dự án {idx+1}. Nghỉ 5s...", "SUCCESS")
                time.sleep(5)

        finished_callback()

    def process_one_folder(self, inp, inp2, out, prompt, url, languages, loop_type, profiles, shuffle_gems):
        self.current_monitoring_info = (inp, inp2, out, loop_type, languages, shuffle_gems)
        
        self.clear_task_queue()
        self.log(f"🔍 Bắt đầu xử lý: {os.path.basename(inp)}", "INFO")

        while not self.stop_event.is_set():
            match loop_type:
                case "srt_prompt":
                    pending, _ = get_srt_prompt_status(inp, out)
                case "prompt_image":
                    pending, _ = get_prompt_image_status(inp, out)
                case "1_image_prompt_video":
                    pending, _ = get_1_image_prompt_video_status(inp, inp2, out)
                case "stretch_video":
                    pending, _ = get_stretch_video_status(inp, inp2, out)
                case _:
                    pending, _ = [], []

            if not pending:
                self.log(f"✅ Dự án {os.path.basename(inp)} hoàn thành!", "SUCCESS")
                if loop_type == "stretch_video":
                    from utils.stretch_video import merge_videos_ffmpeg
                    merge_videos_ffmpeg(inp, out, self.log)
                break 

            living_profiles = [p for p in profiles if self.profile_health.get(p, 0) < config.global_settings["system"]["max_retries"]]
            if not living_profiles:
                self.log("❌ Hết Profile sống!", "ERROR"); break

            while not self.task_queue.empty(): self.task_queue.get()
            for f in pending: self.task_queue.put(f)

            cur_threads = min(config.global_settings["system"]["max_threads"], len(living_profiles))
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=cur_threads) as executor:
                futures = []
                for p_name in living_profiles: # run multiple profiles
                    f = executor.submit(self.continuous_profile_runner, p_name, loop_type, inp, inp2, out, prompt, url, languages, shuffle_gems)
                    futures.append(f)
                
                concurrent.futures.wait(futures)

            if self.stop_event.is_set(): break
            time.sleep(3)
        
        self.current_monitoring_info = None
        
        # Sau khi kết thúc, kiểm tra xem còn STT nào thiếu không và log ra
        try:
            match loop_type:
                case "srt_prompt":
                    final_pending, _ = get_srt_prompt_status(inp, out)
                case "prompt_image":
                    final_pending, _ = get_prompt_image_status(inp, out)
                case "1_image_prompt_video":
                    final_pending, _ = get_1_image_prompt_video_status(inp, inp2, out)
                case "stretch_video":
                    final_pending, _ = get_stretch_video_status(inp, inp2, out)
                case _:
                    final_pending = []

            if final_pending:
                # Gộp các số liên tiếp thành dải (1,2,3,5 -> '1-3, 5')
                nums = sorted([int(p.get('STT', 0)) for p in final_pending if str(p.get('STT', '')).isdigit()])
                ranges, start, end = [], nums[0], nums[0]
                for n in nums[1:]:
                    if n == end + 1:
                        end = n
                    else:
                        ranges.append(str(start) if start == end else f"{start}-{end}")
                        start = end = n
                ranges.append(str(start) if start == end else f"{start}-{end}")
                
                stt_str = ", ".join(ranges)
                self.log(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", "TECH")
                self.log(f"  ⚠️  KHOẢNG TRỐNG CẦN XỬ LÝ", "WARNING")
                self.log(f"  📁  Dự án  : {os.path.basename(inp)}", "TECH")
                self.log(f"  📌  STT thiếu : {stt_str}", "TECH")
                self.log(f"  📊  Tổng cộng : {len(final_pending)} mục", "TECH")
                self.log(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", "TECH")
            else:
                self.log(f"✨ Dự án '{os.path.basename(inp)}' hoàn thành 100%!", "SUCCESS")
        except Exception as e:
            self.log(f"⚠️ Không kiểm tra được trạng thái cuối: {e}", "WARNING")

    def continuous_profile_runner(self, profile_name, loop_type, inp_path, inp2_path, out_path, prompt, url, languages, shuffle_gems):
        while not self.stop_event.is_set():
            fails = self.profile_health.get(profile_name, 0)
            if fails >= config.global_settings["system"]["max_retries"]:
                self.log(f"💀 Profile '{profile_name}' chết.", "ERROR"); return 

            candidates = []
            #srt->prompt có thể chạy nhanh nên không chia ra limit làm gì để phức tạp, chia chunk là được
            with self.file_lock:  
                if loop_type == "srt_prompt" or loop_type == "srt_shuffle":
                    while not self.task_queue.empty():
                        candidates.append(self.task_queue.get())
                else:
                    for _ in range(config.global_settings["system"]["loop_limit"]):
                        if not self.task_queue.empty(): candidates.append(self.task_queue.get())
                        else: break
                
                if not candidates: return

                match loop_type:
                    case "srt_prompt":
                        actual_pending, _ = get_srt_prompt_status(inp_path, out_path)
                        batch = actual_pending # Ném cả file vào luôn vì srt rất nhỏ
                    case "prompt_image":
                        actual_pending, _ = get_prompt_image_status(inp_path, out_path)
                        batch = [item for item in candidates if item in actual_pending]
                    case "1_image_prompt_video":
                        actual_pending, _ = get_1_image_prompt_video_status(inp_path, inp2_path, out_path)
                        ap_stts = [i.get("STT") for i in actual_pending]
                        batch = [item for item in candidates if isinstance(item, dict) and item.get("STT") in ap_stts]
                    case "stretch_video":
                        actual_pending, _ = get_stretch_video_status(inp_path, inp2_path, out_path)
                        ap_stts = [i.get("STT") for i in actual_pending]
                        batch = [item for item in candidates if isinstance(item, dict) and item.get("STT") in ap_stts]
                    case _:
                        actual_pending, _ = [], []
                        batch = []
                
            if not batch: continue

            self.log(f"▶️ [{profile_name}] Nhận {len(batch)} task...", "INFO")
            is_healthy, failed_items = run_worker_task(
                profile_name, batch, loop_type, out_path, prompt, url, DEFAULT_PROFILES, self.stop_event, self.log
            )

            if failed_items:
                self.log(f"♻️ [{profile_name}] Retry {len(failed_items)} items.", "WARNING")
                with self.file_lock:
                    for item in failed_items: self.task_queue.put(item) 

            if is_healthy: self.profile_health[profile_name] = 0 
            else: self.profile_health[profile_name] += 1

    def monitor_loop(self, update_ui_callback):
        while True:
            if self.current_monitoring_info:
                try:
                    inp, inp2, out, loop_type, languages, shuffle_gems = self.current_monitoring_info
                    
                    match loop_type:
                        case "srt_prompt":
                            pending, completed = get_srt_prompt_status(inp, out)
                        case "prompt_image":
                            pending, completed = get_prompt_image_status(inp, out)
                        case "1_image_prompt_video":
                            pending, completed = get_1_image_prompt_video_status(inp, inp2, out)
                        case "stretch_video":
                            pending, completed = get_stretch_video_status(inp, inp2, out)
                        case _:
                            pending, completed = [], []

                    t = len(pending) + len(completed)
                    update_ui_callback(t, len(pending), len(completed))
                    
                except Exception as e:
                    print(f"Monitor Error: {e}")
            
            time.sleep(2)