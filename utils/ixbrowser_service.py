import requests
import config
import threading

class IxBrowserService:
    _open_lock = threading.Lock()
    @staticmethod
    def get_api_url():
        return config.global_settings["system"].get("ixbrowser_api_url", "http://127.0.0.1:53200")

    @classmethod
    def get_profiles(cls):
        """
        Lấy danh sách profile từ Local API.
        Trả về: (success: bool, error_msg: str, profiles: list)
        """
        api_url = cls.get_api_url()
        try:
            payload = {"page": 1, "limit": 1000}
            headers = {"Content-Type": "application/json"}
            r = requests.post(f"{api_url}/api/v2/profile-list", json=payload, headers=headers, timeout=15)
            if r.status_code == 200:
                data = r.json()
                if data.get("error", {}).get("code") == 0:
                    profiles_data = data.get("data", {}).get("data", [])
                    return True, None, profiles_data
                else:
                    msg = data.get("error", {}).get("message", "Lỗi phản hồi từ API")
                    return False, msg, []
            else:
                return False, f"HTTP {r.status_code} từ API", []
        except Exception as e:
            return False, f"Không thể kết nối tới ixBrowser Local API ({api_url}). Vui lòng kiểm tra xem ứng dụng ixBrowser đã được mở và bật Local API chưa.", []

    @classmethod
    def get_groups(cls):
        """
        Lấy danh sách nhóm (group-list) từ ixBrowser Local API.
        Trả về: (success: bool, error_msg: str, groups: list)
        """
        api_url = cls.get_api_url()
        try:
            payload = {"page": 1, "limit": 1000, "title": ""}
            headers = {"Content-Type": "application/json"}
            r = requests.post(f"{api_url}/api/v2/group-list", json=payload, headers=headers, timeout=15)
            if r.status_code == 200:
                data = r.json()
                if data.get("error", {}).get("code") == 0:
                    groups_data = data.get("data", {}).get("data", [])
                    return True, None, groups_data
                else:
                    msg = data.get("error", {}).get("message", "Lỗi lấy danh sách nhóm")
                    return False, msg, []
            else:
                return False, f"HTTP {r.status_code} từ API", []
        except Exception as e:
            return False, str(e), []

    @staticmethod
    def reset_profile_status(profile_id):
        """
        Reset trạng thái mở của profile trong database của ixBrowser.
        """
        api_url = IxBrowserService.get_api_url()
        try:
            payload = {"profile_id": profile_id}
            headers = {"Content-Type": "application/json"}
            requests.post(f"{api_url}/api/v2/profile-open-state-reset", json=payload, headers=headers, timeout=15)
            return True
        except:
            return False

    @staticmethod
    def get_opened_profiles():
        """
        Lấy danh sách các profile đang mở thực tế từ local API.
        """
        api_url = IxBrowserService.get_api_url()
        try:
            headers = {"Content-Type": "application/json"}
            r = requests.post(f"{api_url}/api/v2/native-client-profile-opened-list", json={}, headers=headers, timeout=15)
            if r.status_code == 200:
                data = r.json()
                if data.get("error", {}).get("code") == 0:
                    return data.get("data", [])
            return []
        except:
            return []

    @classmethod
    def open_profile(cls, profile_id):
        """
        Gọi API mở profile và trả về WebSocket URL để điều khiển CDP (Có khóa đồng bộ).
        """
        with cls._open_lock:
            return cls._open_profile_internal(profile_id)

    @classmethod
    def _open_profile_internal(cls, profile_id):
        """
        Thực hiện xử lý mở profile từ API dưới nền.
        Không chờ/ngủ khi dính "backed up" để luồng chính skip nhanh không bị kẹt.
        """
        api_url = cls.get_api_url()
        payload = {
            "profile_id": profile_id,
            "args": ["--disable-extension-welcome-page"],
            "load_extensions": True,
            "load_profile_info_page": True,
            "cookies_backup": False
        }
        headers = {"Content-Type": "application/json"}

        try:
            r = requests.post(f"{api_url}/api/v2/profile-open", json=payload, headers=headers, timeout=60)
            if r.status_code == 200:
                data = r.json()
                err_code = data.get("error", {}).get("code")
                err_msg = data.get("error", {}).get("message", "")
                
                if err_code == 0:
                    ws_url = data.get("data", {}).get("ws")
                    if ws_url:
                        return True, None, ws_url
                
                # 1. Nếu dính lỗi đang đồng bộ đám mây (backed up) -> trả về lỗi lập tức để skip luôn
                if "backed up" in err_msg.lower():
                    return False, "Trình duyệt đang đồng bộ đám mây (backed up), vui lòng thử lại sau.", None
                
                # 2. Xử lý khi báo lỗi "already open"
                if "already open" in err_msg.lower():
                    # Kiểm tra xem profile có thực sự đang mở không
                    opened_list = cls.get_opened_profiles()
                    for op in opened_list:
                        if op.get("profile_id") == profile_id:
                            ws_url = op.get("ws")
                            if ws_url:
                                return True, None, ws_url
                    
                    # Nếu không có trong danh sách đang mở thực tế -> Bị kẹt DB -> Reset và thử lại
                    cls.reset_profile_status(profile_id)
                    
                    # Thử mở lại lần 2
                    r_retry = requests.post(f"{api_url}/api/v2/profile-open", json=payload, headers=headers, timeout=60)
                    if r_retry.status_code == 200:
                        data_retry = r_retry.json()
                        if data_retry.get("error", {}).get("code") == 0:
                            ws_url = data_retry.get("data", {}).get("ws")
                            if ws_url:
                                return True, None, ws_url
                        err_msg = data_retry.get("error", {}).get("message", "Thử mở lại thất bại sau khi reset")
                
                return False, err_msg, None
            else:
                return False, f"HTTP {r.status_code} từ API", None
        except Exception as e:
            return False, str(e), None

    @classmethod
    def close_profile(cls, profile_id):
        """
        Gửi yêu cầu đóng profile đến ixBrowser Local API.
        Trả về: (success: bool, error_msg: str)
        """
        api_url = cls.get_api_url()
        try:
            payload = {"profile_id": profile_id}
            headers = {"Content-Type": "application/json"}
            r = requests.post(f"{api_url}/api/v2/profile-close", json=payload, headers=headers, timeout=15)
            if r.status_code == 200:
                data = r.json()
                if data.get("error", {}).get("code") == 0:
                    return True, None
                else:
                    msg = data.get("error", {}).get("message", "Lỗi đóng profile từ API")
                    return False, msg
            else:
                return False, f"HTTP {r.status_code} từ API"
        except Exception as e:
            return False, str(e)
