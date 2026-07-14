import os
import json
import threading
import time
import config

class RateLimitException(Exception):
    def __init__(self, message="Tài khoản bị giới hạn lượt tạo (Rate Limit / Cooldown)", cooldown_seconds=7200):
        super().__init__(message)
        self.cooldown_seconds = cooldown_seconds

class ProfileStateManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(ProfileStateManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.profiles_dir = config.DEFAULT_PROFILES
        self.states_file = os.path.join(self.profiles_dir, "profile_states.json")
        self.lock = threading.Lock()
        self.states = {}
        self.sync_with_disk()
        self._migrate_old_proxies()
        self._initialized = True

    def sync_with_disk(self):
        """Đồng bộ hóa danh sách profile với thư mục trên ổ cứng hoặc ixBrowser API"""
        with self.lock:
            if not os.path.exists(self.profiles_dir):
                os.makedirs(self.profiles_dir)

            browser_type = config.global_settings["system"].get("browser_type", "ixBrowser")
            folders = []
            error_msg = None

            profile_groups = {}
            if browser_type == "ixBrowser (Local API)":
                from utils.ixbrowser_service import IxBrowserService
                success, err, profiles_data = IxBrowserService.get_profiles()
                if success:
                    for p in profiles_data:
                        p_id = p.get("profile_id")
                        p_name = p.get("name", "Unnamed")
                        folder_name = f"{p_id} - {p_name}"
                        folders.append(folder_name)
                        profile_groups[folder_name] = {
                            "group_id": p.get("group_id"),
                            "group_name": p.get("group_name", "").strip()
                        }
                else:
                    error_msg = err
            else:
                try:
                    folders = [
                        f for f in os.listdir(self.profiles_dir)
                        if os.path.isdir(os.path.join(self.profiles_dir, f))
                    ]
                except Exception as e:
                    error_msg = str(e)

            if error_msg and browser_type == "ixBrowser (Local API)":
                return False, error_msg

            # Đọc file states cũ nếu có
            disk_states = {}
            if os.path.exists(self.states_file):
                try:
                    with open(self.states_file, "r", encoding="utf-8") as f:
                        disk_states = json.load(f)
                except:
                    pass

            new_states = {}
            for folder in folders:
                old_state = disk_states.get(folder, self.states.get(folder, {}))
                status = old_state.get("status", "idle")
                rate_limit_until = old_state.get("rate_limit_until", 0.0)

                g_info = profile_groups.get(folder, {})
                group_id = g_info.get("group_id", old_state.get("group_id"))
                group_name = g_info.get("group_name", old_state.get("group_name", ""))

                new_states[folder] = {
                    "status": status,
                    "error_count": old_state.get("error_count", 0),
                    "rate_limit_count": old_state.get("rate_limit_count", 0),
                    "selected": old_state.get("selected", True),
                    "proxy": old_state.get("proxy", ""),
                    "rate_limit_until": rate_limit_until,
                    "last_error": old_state.get("last_error", None),
                    "group_id": group_id,
                    "group_name": group_name
                }

            self.states = new_states
            self._save_to_disk()
            return True, None

    def _migrate_old_proxies(self):
        old_proxy_file = os.path.join(self.profiles_dir, "proxy_map.json")
        if os.path.exists(old_proxy_file):
            try:
                with open(old_proxy_file, "r", encoding="utf-8") as f:
                    old_proxies = json.load(f)
                if old_proxies:
                    with self.lock:
                        for p_name, proxy_str in old_proxies.items():
                            if p_name in self.states and not self.states[p_name].get("proxy"):
                                self.states[p_name]["proxy"] = proxy_str
                        self._save_to_disk()
                os.remove(old_proxy_file)
            except Exception as e:
                print(f"⚠️ Lỗi migrate proxy cũ: {e}")

    def _save_to_disk(self):
        try:
            with open(self.states_file, "w", encoding="utf-8") as f:
                json.dump(self.states, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"❌ Lỗi ghi file profile_states.json: {e}")

    def get_state(self, profile_name):
        with self.lock:
            self._load_from_disk_no_lock()
            state = self.states.get(profile_name, {"status": "idle", "error_count": 0, "rate_limit_count": 0, "selected": True, "proxy": "", "rate_limit_until": 0.0})
            # Tự động giải phóng nếu đã hết thời gian rate limit
            if state.get("status") == "rate_limited":
                until = state.get("rate_limit_until", 0.0)
                if time.time() >= until:
                    state["status"] = "idle"
                    state["rate_limit_until"] = 0.0
                    if profile_name in self.states:
                        self.states[profile_name]["status"] = "idle"
                        self.states[profile_name]["rate_limit_until"] = 0.0
                        self._save_to_disk()
            return state

    def get_proxy(self, profile_name):
        with self.lock:
            self._load_from_disk_no_lock()
            return self.states.get(profile_name, {}).get("proxy", "")

    def get_all_states(self):
        with self.lock:
            self._load_from_disk_no_lock()
            changed = False
            for p_name, state in self.states.items():
                if state.get("status") == "rate_limited":
                    until = state.get("rate_limit_until", 0.0)
                    if time.time() >= until:
                        state["status"] = "idle"
                        state["rate_limit_until"] = 0.0
                        changed = True
            if changed:
                self._save_to_disk()
            return dict(self.states)

    def _load_from_disk_no_lock(self):
        if os.path.exists(self.states_file):
            try:
                with open(self.states_file, "r", encoding="utf-8") as f:
                    self.states = json.load(f)
            except:
                pass

    def checkout(self, profile_name, activity):
        """Atomically locks the profile for activity ('in_setup' or 'in_batch') and resets error_count to 0"""
        with self.lock:
            self._load_from_disk_no_lock()
            if profile_name not in self.states:
                self.states[profile_name] = {
                    "status": "idle",
                    "error_count": 0,
                    "rate_limit_count": 0,
                    "selected": True,
                    "proxy": "",
                    "rate_limit_until": 0.0,
                    "last_error": None
                }
            
            current_status = self.states[profile_name].get("status", "idle")
            rate_limit_until = self.states[profile_name].get("rate_limit_until", 0.0)
            
            # Kiểm tra xem có đang bị rate limit không
            if current_status == "rate_limited":
                if time.time() < rate_limit_until:
                    return False  # Vẫn đang trong thời gian chờ rate limit
                else:
                    self.states[profile_name]["status"] = "idle"
                    self.states[profile_name]["rate_limit_until"] = 0.0
                    current_status = "idle"

            if current_status in ["in_setup", "in_batch"]:
                return False  # Profile đang bận
            
            self.states[profile_name]["status"] = activity
            self.states[profile_name]["error_count"] = 0  # Reset lỗi mỗi khi bắt đầu chạy mới
            self.states[profile_name]["rate_limit_until"] = 0.0
            self._save_to_disk()
            return True

    def set_state(self, profile_name, status, error_msg=None):
        """Đặt trạng thái trực tiếp (Ví dụ: khi bị ép dừng hoặc gặp lỗi)"""
        with self.lock:
            self._load_from_disk_no_lock()
            if profile_name in self.states:
                self.states[profile_name]["status"] = status
                if error_msg:
                    self.states[profile_name]["last_error"] = error_msg
                self._save_to_disk()

    def set_selected(self, profile_name, selected):
        """Lưu lựa chọn checkbox của profile"""
        with self.lock:
            self._load_from_disk_no_lock()
            if profile_name in self.states:
                self.states[profile_name]["selected"] = selected
                self._save_to_disk()

    def set_proxy(self, profile_name, proxy_str):
        """Lưu proxy của profile"""
        with self.lock:
            self._load_from_disk_no_lock()
            if profile_name in self.states:
                self.states[profile_name]["proxy"] = proxy_str
                self._save_to_disk()

    def set_proxies(self, proxy_map):
        """Lưu hàng loạt proxy (từ tính năng import danh sách proxy)"""
        with self.lock:
            self._load_from_disk_no_lock()
            for p_name, proxy_str in proxy_map.items():
                if p_name in self.states:
                    self.states[p_name]["proxy"] = proxy_str
            self._save_to_disk()

    def set_rate_limit_count(self, profile_name, count=0):
        """Đặt trực tiếp số lần dính rate limit của profile"""
        with self.lock:
            self._load_from_disk_no_lock()
            if profile_name in self.states:
                self.states[profile_name]["rate_limit_count"] = count
                self._save_to_disk()

    def set_rate_limited(self, profile_name, cooldown_seconds=7200):
        """Đặt trạng thái bị rate limit cho profile với thời gian chờ"""
        with self.lock:
            self._load_from_disk_no_lock()
            if profile_name in self.states:
                rl_count = self.states[profile_name].get("rate_limit_count", 0) + 1
                self.states[profile_name]["rate_limit_count"] = rl_count
                
                max_rl_retries = config.global_settings["system"].get("max_rate_limit_retries", 3)
                if rl_count >= max_rl_retries:
                    self.states[profile_name]["status"] = "error"
                    self.states[profile_name]["rate_limit_until"] = 0.0
                    self.states[profile_name]["last_error"] = f"Dính Rate Limit quá {max_rl_retries} lần. Coi như hỏng."
                else:
                    self.states[profile_name]["status"] = "rate_limited"
                    self.states[profile_name]["rate_limit_until"] = time.time() + cooldown_seconds
                self._save_to_disk()

    def increment_error(self, profile_name, error_msg=None):
        """Tăng số lần lỗi của profile"""
        with self.lock:
            self._load_from_disk_no_lock()
            if profile_name in self.states:
                self.states[profile_name]["error_count"] = self.states[profile_name].get("error_count", 0) + 1
                if error_msg:
                    self.states[profile_name]["last_error"] = error_msg
                self._save_to_disk()

    def release(self, profile_name):
        """Giải phóng profile về trạng thái idle"""
        with self.lock:
            self._load_from_disk_no_lock()
            if profile_name in self.states:
                # Nếu đang bị lỗi hoặc bị ép dừng hoặc rate limited thì giữ nguyên trạng thái
                current_status = self.states[profile_name].get("status", "idle")
                if current_status in ["in_setup", "in_batch"]:
                    self.states[profile_name]["status"] = "idle"
                self._save_to_disk()

    def reset_all(self):
        """Reset các trạng thái về idle khi khởi động ứng dụng hoặc bấm Refresh"""
        with self.lock:
            self._load_from_disk_no_lock()
            for profile_name in self.states:
                self.states[profile_name]["status"] = "idle"
                self.states[profile_name]["error_count"] = 0
                self.states[profile_name]["rate_limit_count"] = 0
                self.states[profile_name]["rate_limit_until"] = 0.0
                self.states[profile_name]["last_error"] = None
            self._save_to_disk()
