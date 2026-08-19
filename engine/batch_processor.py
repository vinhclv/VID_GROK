# engine/batch_processor.py
import threading
import queue
import time
import os
import concurrent.futures

from config import DEFAULT_PROFILES
from utils.profile_state import ProfileStateManager
from utils.file_ops import (
    get_srt_prompt_status,
    get_prompt_image_status,
    get_1_image_prompt_video_status,
    get_stretch_video_status,
    get_image_to_video_status,
    get_task_status
)
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
        self.stt_fail_count = {}   # {stt_key: fail_count} — reset mỗi dự án
        self.stt_skipped   = []    # STT bỏ qua vĩnh viễn trong dự án hiện tại
        
        self.current_monitoring_info = None 
        self._metadata_projects = None  # (project_queue, runnable_indices, loop_type) — cho monitor track metadata

    def clear_task_queue(self):
        with self.task_queue.mutex:
            self.task_queue.queue.clear()

    def kill_profile_now(self, profile_name):
        """Force-dead profile trong run hiện tại.
        Runner tự return sau task hiện tại nhờ kiểm tra profile_health.
        Reset về alive khi Start run mới."""
        max_r = config.global_settings["system"]["max_retries"]
        self.profile_health[profile_name] = max_r + 999
        self.log(f"☠️ Profile '{profile_name}' bị kill. Sẽ dừng sau task hiện tại.", "ERROR")
        # Đồng thời cập nhật trạng thái trong ProfileStateManager
        ProfileStateManager().set_state(profile_name, "killed", "Bị người dùng ép dừng bằng nút Kill")
 
    def run_batch_logic(self, project_queue, loop_type, profiles, finished_callback):
        self.profile_health = {p: 0 for p in profiles}
        for p in profiles:
            ProfileStateManager().set_rate_limit_count(p, 0)
        
        self.log(f"🚀 BẮT ĐẦU CHẠY: {len(project_queue)} DỰ ÁN", "INFO")

        # === CHẾ ĐỘ ĐẶC BIỆT: Metadata — Gom batch, giữ profile mở ===
        if loop_type == "script_metadata":
            self._run_metadata_batch(project_queue, loop_type, profiles)
            self.current_monitoring_info = None
            finished_callback()
            return

        for idx, project in enumerate(project_queue):
            if self.stop_event.is_set(): break
            
            # Bỏ qua dự án nếu đã bị đánh dấu lỗi hoặc skip ở bước kiểm tra trước
            if project.get("status", "Waiting") in ["Failed ❌", "Skipped ⏭️"]:
                continue
                
            input_path = project["input"]
            input2_path = project.get("input2", "")
            output_path = project["output"]
            prompt = project["prompt"]
            url = project["url"]
            languages = project["languages"]
            shuffle_gems = project["shuffle_gems"]
            
            self.update_status(idx, "Running ⏳")
            self.log(f"=== DỰ ÁN {idx+1}/{len(project_queue)}: {os.path.basename(input_path)} ===", "INFO")
            
            success = self.process_one_folder(input_path, input2_path, output_path, prompt, url, languages, loop_type, profiles, shuffle_gems)
            
            if self.stop_event.is_set():
                self.update_status(idx, "Stopped 🛑")
                break
            elif not success:
                self.update_status(idx, "Failed ❌")
                self.log(f"🛑 Dừng hàng chờ chạy các dự án tiếp theo do không còn profile nào khỏe mạnh!", "ERROR")
                # Đánh dấu các dự án còn lại trong hàng chờ là Failed
                for remaining_idx in range(idx + 1, len(project_queue)):
                    self.update_status(remaining_idx, "Failed ❌")
                break
            else:
                # Hiển thị STT bỏ qua vào cột Trạng thái
                if self.stt_skipped:
                    stts_disp = ", ".join(self.stt_skipped[:6])
                    suffix    = f" +{len(self.stt_skipped)-6}" if len(self.stt_skipped) > 6 else ""
                    self.update_status(idx, f"Done ✅ | ⛔ skip: {stts_disp}{suffix}")
                else:
                    self.update_status(idx, "Done ✅")
                self.log(f"🏁 Xong dự án {idx+1}. Nghỉ 5s...", "SUCCESS")
                time.sleep(5)

        finished_callback()

    def process_one_folder(self, inp, inp2, out, prompt, url, languages, loop_type, profiles, shuffle_gems):
        self.current_monitoring_info = (inp, inp2, out, loop_type, languages, shuffle_gems)
        self.stt_fail_count = {}   # Reset cho mỗi dự án mới
        self.stt_skipped    = []   # Reset danh sách STT bỏ qua
        
        self.clear_task_queue()
        self.log(f"🔍 Bắt đầu xử lý: {os.path.basename(inp)}", "INFO")

        while not self.stop_event.is_set():
            pending, _ = get_task_status(loop_type, inp, inp2, out)

            if not pending:
                self.log(f"✅ Dự án {os.path.basename(inp)} hoàn thành!", "SUCCESS")
                if loop_type in ["stretch_video", "image_to_video"]:
                    from utils.stretch_video import merge_videos_ffmpeg
                    merge_videos_ffmpeg(inp, out, self.log)
                break 

            # Lọc bỏ STT đã bị skip vĩnh viễn khỏi danh sách chờ
            if self.stt_skipped:
                active_pending = [f for f in pending if str(f.get("STT", "")) not in self.stt_skipped]
                if not active_pending:
                    self.log(f"⛔ Tất cả STT còn lại đều đã bị bỏ qua vĩnh viễn. Kết thúc dự án.", "WARNING")
                    break
            else:
                active_pending = pending

            # Lọc các profile khỏe mạnh và không bị rate limit
            active_profiles = []
            has_rate_limited = False
            for p in profiles:
                # Nếu profile lỗi quá số lần tối đa thì coi như chết
                if self.profile_health.get(p, 0) >= config.global_settings["system"]["max_retries"]:
                    continue
                # Kiểm tra xem có đang bị rate limit hay lỗi hay không
                p_state = ProfileStateManager().get_state(p)
                status = p_state.get("status", "idle")
                rl_count = p_state.get("rate_limit_count", 0)
                max_rl_retries = config.global_settings["system"].get("max_rate_limit_retries", 3)
                
                if status in ["error", "killed", "failed"] or rl_count >= max_rl_retries:
                    continue
                if status == "rate_limited":
                    has_rate_limited = True
                    continue
                active_profiles.append(p)

            if not active_profiles:
                if has_rate_limited:
                    self.log("⏳ Tất cả profile khỏe mạnh đều đang bị giới hạn tạo ảnh (Rate Limit). Đang chờ 30 giây để kiểm tra lại...", "WARNING")
                    # Chờ 30 giây rồi tiếp tục vòng lặp
                    time.sleep(30)
                    continue
                else:
                    self.log("❌ Không còn profile nào khỏe mạnh (tất cả đều đã vượt quá số lần thử lại tối đa)!", "ERROR")
                    self.current_monitoring_info = None
                    return False

            while not self.task_queue.empty(): self.task_queue.get()
            for f in active_pending: self.task_queue.put(f)

            cur_threads = min(config.global_settings["system"]["max_threads"], len(active_profiles))
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=cur_threads) as executor:
                futures = []
                for p_name in active_profiles: # run multiple profiles
                    f = executor.submit(self.continuous_profile_runner, p_name, loop_type, inp, inp2, out, prompt, url, languages, shuffle_gems)
                    futures.append(f)
                
                concurrent.futures.wait(futures)

            if self.stop_event.is_set(): break
            time.sleep(3)
        
        self.current_monitoring_info = None
        
        # Sau khi kết thúc, kiểm tra xem còn STT nào thiếu không và log ra
        try:
            final_pending, _ = get_task_status(loop_type, inp, inp2, out)

            if final_pending:
                all_stts = [str(p.get('STT', '')) for p in final_pending if p.get('STT') is not None]
                nums = sorted([int(s) for s in all_stts if s.isdigit()])
                if nums:
                    ranges, start, end = [], nums[0], nums[0]
                    for n in nums[1:]:
                        if n == end + 1:
                            end = n
                        else:
                            ranges.append(str(start) if start == end else f"{start}-{end}")
                            start = end = n
                    ranges.append(str(start) if start == end else f"{start}-{end}")
                    stt_str = ", ".join(ranges)
                else:
                    stt_str = ", ".join(all_stts[:10])
                    if len(all_stts) > 10:
                        stt_str += f" (+{len(all_stts)-10} khác)"

                self.log(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", "TECH")
                self.log(f"  ⚠️  KHOẢNG TRỐNG CẦN XỬ LÝ", "WARNING")
                self.log(f"  📁  Dự án  : {os.path.basename(os.path.dirname(inp))}", "TECH")
                self.log(f"  📌  STT thiếu : {stt_str}", "TECH")
                self.log(f"  📊  Tổng cộng : {len(final_pending)} mục", "TECH")
                self.log(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", "TECH")
            else:
                self.log(f"✨ Dự án '{os.path.basename(os.path.dirname(inp))}' hoàn thành 100%!", "SUCCESS")
        except Exception as e:
            self.log(f"⚠️ Không kiểm tra được trạng thái cuối: {e}", "WARNING")

        return True

    def _run_metadata_batch(self, project_queue, loop_type, profiles):
        """
        Chế độ đặc biệt cho ScriptRaw ➡ Metadata:
        Gom tất cả file .txt vào 1 batch, mở profile 1 lần duy nhất,
        xử lý tuần tự với page.goto(url) giữa các file thay vì đóng/mở lại profile.
        """
        # 1. Gom tất cả pending items từ tất cả dự án
        all_pending = []
        runnable_indices = []
        url = ""
        prompt = ""

        for idx, project in enumerate(project_queue):
            if self.stop_event.is_set():
                break
            if project.get("status", "Waiting") in ["Failed ❌", "Skipped ⏭️"]:
                continue
            self.update_status(idx, "Running ⏳")
            runnable_indices.append(idx)

            pending, _ = get_task_status(loop_type, project["input"], project.get("input2", ""), project["output"])
            all_pending.extend(pending)

            if not url:
                url = project["url"]
                prompt = project.get("prompt", "")

        if not all_pending:
            for idx in runnable_indices:
                self.update_status(idx, "Done ✅")
            self.log("✅ Tất cả metadata đã hoàn thành!", "SUCCESS")
            return

        # 2. Lọc profile khỏe mạnh
        active_profiles = []
        for p in profiles:
            if self.profile_health.get(p, 0) >= config.global_settings["system"]["max_retries"]:
                continue
            p_state = ProfileStateManager().get_state(p)
            status = p_state.get("status", "idle")
            if status in ["error", "killed", "failed"]:
                continue
            active_profiles.append(p)

        if not active_profiles:
            self.log("❌ Không còn profile nào khỏe mạnh!", "ERROR")
            for idx in runnable_indices:
                self.update_status(idx, "Failed ❌")
            return

        profile_name = active_profiles[0]

        # 3. Checkout profile
        if not ProfileStateManager().checkout(profile_name, "in_batch"):
            self.log(f"⚠️ [{profile_name}] Profile đang bận.", "WARNING")
            for idx in runnable_indices:
                self.update_status(idx, "Failed ❌")
            return

        # Bật monitoring cho metadata (cho progress counter real-time)
        self._metadata_projects = (project_queue, runnable_indices, loop_type)

        try:
            self.log(f"▶️ [{profile_name}] Nhận {len(all_pending)} metadata tasks (1 session)...", "INFO")

            # 4. Chạy worker trong thread riêng để có thể cập nhật trạng thái real-time
            worker_result = [True, []]  # [is_healthy, failed_items]
            def _worker_fn():
                worker_result[0], worker_result[1] = run_worker_task(
                    profile_name, all_pending, loop_type, "", prompt, url,
                    DEFAULT_PROFILES, self.stop_event, self.log
                )

            worker_thread = threading.Thread(target=_worker_fn, daemon=True)
            worker_thread.start()

            # Theo dõi real-time: poll filesystem mỗi 3 giây để cập nhật status từng dự án
            while worker_thread.is_alive():
                if self.stop_event.is_set():
                    break
                for idx in runnable_indices:
                    project = project_queue[idx]
                    if project.get("status") == "Running ⏳":
                        p, _ = get_task_status(loop_type, project["input"], project.get("input2", ""), project["output"])
                        if not p:
                            self.update_status(idx, "Done ✅")
                            self.log(f"✅ Dự án {os.path.basename(project['input'])} hoàn thành!", "SUCCESS")
                time.sleep(3)

            worker_thread.join()
            is_healthy, failed_items = worker_result

            # 5. Retry failed items (mỗi lần retry mở 1 session mới)
            MAX_STT_FAILS = config.global_settings.get("system", {}).get("max_stt_retries", 5)
            retry_round = 0
            while failed_items and retry_round < MAX_STT_FAILS and not self.stop_event.is_set():
                retry_round += 1
                self.log(f"♻️ [{profile_name}] Retry {len(failed_items)} metadata items (lần {retry_round}/{MAX_STT_FAILS})...", "WARNING")

                # Retry cũng chạy trong thread riêng để tiếp tục poll status
                retry_result = [True, []]
                def _retry_fn(fr=failed_items):
                    retry_result[0], retry_result[1] = run_worker_task(
                        profile_name, fr, loop_type, "", prompt, url,
                        DEFAULT_PROFILES, self.stop_event, self.log
                    )

                rt = threading.Thread(target=_retry_fn, daemon=True)
                rt.start()
                while rt.is_alive():
                    if self.stop_event.is_set():
                        break
                    for idx in runnable_indices:
                        project = project_queue[idx]
                        if project.get("status") == "Running ⏳":
                            p, _ = get_task_status(loop_type, project["input"], project.get("input2", ""), project["output"])
                            if not p:
                                self.update_status(idx, "Done ✅")
                                self.log(f"✅ Dự án {os.path.basename(project['input'])} hoàn thành!", "SUCCESS")
                    time.sleep(3)
                rt.join()
                is_healthy, failed_items = retry_result

            if not is_healthy:
                self.profile_health[profile_name] = self.profile_health.get(profile_name, 0) + 1
            else:
                self.profile_health[profile_name] = 0

        finally:
            self._metadata_projects = None
            current_state = ProfileStateManager().get_state(profile_name)
            if current_state.get("status") in ["in_batch"]:
                ProfileStateManager().release(profile_name)

        # 6. Cập nhật trạng thái cuối cùng cho các dự án chưa được đánh dấu Done
        for idx in runnable_indices:
            project = project_queue[idx]
            if project.get("status") == "Running ⏳":
                pending, _ = get_task_status(loop_type, project["input"], project.get("input2", ""), project["output"])
                if not pending:
                    self.update_status(idx, "Done ✅")
                    self.log(f"✅ Dự án {os.path.basename(project['input'])} hoàn thành!", "SUCCESS")
                else:
                    self.update_status(idx, "Failed ❌")

    def continuous_profile_runner(self, profile_name, loop_type, inp_path, inp2_path, out_path, prompt, url, languages, shuffle_gems):
        # Checkout chiếm dụng profile trước khi bắt đầu chạy luồng
        if not ProfileStateManager().checkout(profile_name, "in_batch"):
            self.log(f"⚠️ [{profile_name}] Profile đang bận hoặc đang được setup. Bỏ qua luồng này.", "WARNING")
            return

        try:
            while not self.stop_event.is_set():
                # 1. Kiểm tra xem profile có bị đánh dấu rate_limited hoặc error từ bên ngoài (ví dụ do worker phát hiện lỗi API) không
                current_state = ProfileStateManager().get_state(profile_name)
                status = current_state.get("status", "idle")
                if status == "error":
                    self.log(f"💀 [{profile_name}] Profile bị lỗi hoặc dính Rate Limit quá số lần tối đa. Dừng chạy luồng.", "ERROR")
                    break
                elif status == "rate_limited":
                    self.log(f"⏸️ [{profile_name}] Phát hiện profile bị Rate Limited / Cooldown. Dừng chạy luồng để bảo vệ tài khoản.", "WARNING")
                    break

                fails = self.profile_health.get(profile_name, 0)
                if fails >= config.global_settings["system"]["max_retries"]:
                    self.log(f"💀 Profile '{profile_name}' chết.", "ERROR")
                    ProfileStateManager().set_state(profile_name, "error", f"Đã vượt quá số lần thử lại tối đa ({fails} lần)")
                    return 

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

                    actual_pending, _ = get_task_status(loop_type, inp_path, inp2_path, out_path)
                    if loop_type in ["srt_prompt", "srt_shuffle"]:
                        batch = actual_pending
                    else:
                        ap_stts = [i.get("STT") for i in actual_pending]
                        batch = [item for item in candidates if isinstance(item, dict) and item.get("STT") in ap_stts]
                    
                if not batch: continue

                self.log(f"▶️ [{profile_name}] Nhận {len(batch)} task...", "INFO")
                is_healthy, failed_items = run_worker_task(
                    profile_name, batch, loop_type, out_path, prompt, url, DEFAULT_PROFILES, self.stop_event, self.log
                )

                if failed_items:
                    MAX_STT_FAILS = config.global_settings.get("system", {}).get("max_stt_retries", 5)
                    retry_items = []
                    with self.file_lock:
                        for item in failed_items:
                            stt = str(item.get("STT", id(item)))
                            self.stt_fail_count[stt] = self.stt_fail_count.get(stt, 0) + 1
                            if self.stt_fail_count[stt] >= MAX_STT_FAILS:
                                if stt not in self.stt_skipped:
                                    self.stt_skipped.append(stt)  # Track cho cột Trạng thái
                                self.log(
                                    f"⛔ STT {stt} bỏ qua vĩnh viễn "
                                    f"(fail {self.stt_fail_count[stt]}/{MAX_STT_FAILS} lần — có thể do chính sách nội dung)",
                                    "WARNING"
                                )
                            else:
                                retry_items.append(item)
                        for item in retry_items:
                            self.task_queue.put(item)
                    if retry_items:
                        self.log(f"♻️ [{profile_name}] Retry {len(retry_items)} items.", "WARNING")

                # Kiểm tra trạng thái bị rate_limited ngay sau khi chạy xong worker
                current_state = ProfileStateManager().get_state(profile_name)
                status = current_state.get("status", "idle")
                if status == "error":
                    self.log(f"💀 [{profile_name}] Profile bị lỗi hoặc dính Rate Limit quá số lần tối đa. Thoát luồng chạy.", "ERROR")
                    break
                elif status == "rate_limited":
                    rl_count = current_state.get("rate_limit_count", 0)
                    max_rl = config.global_settings["system"].get("max_rate_limit_retries", 3)
                    self.log(f"⏸️ [{profile_name}] Phát hiện profile bị Rate Limited / Cooldown (Lần {rl_count}/{max_rl}). Thoát luồng chạy.", "WARNING")
                    break

                if is_healthy: 
                    self.profile_health[profile_name] = 0 
                else: 
                    self.profile_health[profile_name] += 1
                    # Tăng số lần lỗi của profile
                    ProfileStateManager().increment_error(profile_name, "Lỗi chạy worker task (is_healthy = False)")
        finally:
            # Giải phóng profile về idle nếu không bị lỗi/bị ép dừng
            current_state = ProfileStateManager().get_state(profile_name)
            if current_state.get("status") in ["in_batch"]:
                ProfileStateManager().release(profile_name)

    def monitor_loop(self, update_ui_callback):
        last_info = None   # cache để dùng cho final scan

        while not self.stop_event.is_set():
            # === Metadata batch monitoring: gom tiến độ từ tất cả dự án ===
            if self._metadata_projects:
                try:
                    pq, indices, lt = self._metadata_projects
                    total_p, total_c = 0, 0
                    for idx in indices:
                        p, c = get_task_status(lt, pq[idx]["input"], pq[idx].get("input2", ""), pq[idx]["output"])
                        total_p += len(p)
                        total_c += len(c)
                    update_ui_callback(total_p + total_c, total_p, total_c)
                except Exception as e:
                    print(f"Monitor Metadata Error: {e}")
            elif self.current_monitoring_info:
                last_info = self.current_monitoring_info   # ← luôn giữ bản mới nhất
                try:
                    inp, inp2, out, loop_type, languages, shuffle_gems = last_info
                    
                    pending, completed = get_task_status(loop_type, inp, inp2, out)

                    t = len(pending) + len(completed)
                    update_ui_callback(t, len(pending), len(completed))
                    
                except Exception as e:
                    print(f"Monitor Error: {e}")
            
            time.sleep(2)

        # Final scan sau Stop — dùng last_info đã cache, không sợ race condition
        if last_info:
            try:
                inp, inp2, out, loop_type, languages, shuffle_gems = last_info
                pending, completed = get_task_status(loop_type, inp, inp2, out)
                t = len(pending) + len(completed)
                update_ui_callback(t, len(pending), len(completed))
            except Exception as e:
                print(f"Monitor Final Scan Error: {e}")

