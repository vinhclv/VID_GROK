# utils/validators.py
# Chứa các hàm kiểm tra / validate dữ liệu đầu vào trước khi chạy batch

import json
import re
import os

# Chuẩn timecode SRT: HH:MM:SS,mmm --> HH:MM:SS,mmm
_TC_PATTERN = re.compile(r'^\d{2}:\d{2}:\d{2},\d{3}\s*-->\s*\d{2}:\d{2}:\d{2},\d{3}$')


def validate_timecodes(json_path: str) -> tuple[bool, str]:
    """
    Đọc file JSON và kiểm tra toàn bộ timecode có đúng định dạng không.

    Returns:
        (True, "")              — Tất cả hợp lệ
        (False, message)        — Có STT sai, message chứa danh sách lỗi để hiển thị popup
    """
    try:
        with open(json_path, encoding="utf-8") as f:
            items = json.load(f)
    except Exception as e:
        return False, f"Không đọc được file JSON:\n{os.path.basename(json_path)}\n{e}"

    bad_stts = []
    for item in items:
        tc = item.get("timecode", "").strip()
        if tc and not _TC_PATTERN.match(tc):
            bad_stts.append(f"  STT {item.get('STT', '?')}: '{tc}'")

    if bad_stts:
        detail = "\n".join(bad_stts)
        msg = (
            f"Timecode không đúng chuẩn  HH:MM:SS,mmm --> HH:MM:SS,mmm\n"
            f"File: {os.path.basename(json_path)}\n\n"
            f"{detail}\n\n"
            f"Vui lòng sửa trước khi chạy."
        )
        return False, msg

    return True, ""


def validate_characters(json_path: str, img_dir: str) -> tuple[bool, str, list[str]]:
    """
    Kiểm tra xem tất cả các nhân vật được liệt kê trong file JSON
    có file ảnh tương ứng (jpg/png) trong thư mục img_dir hay không.

    Returns:
        (True, "", [])                       - Tất cả hợp lệ
        (False, detail_message, bad_stts)    - Thiếu ảnh nhân vật
    """
    try:
        with open(json_path, encoding="utf-8") as f:
            items = json.load(f)
    except Exception as e:
        return False, f"Không đọc được file JSON:\n{os.path.basename(json_path)}\n{e}", []

    bad_stts = []
    missing_chars = set()
    
    for item in items:
        stt = str(item.get("STT", "?")).strip()
        characters_str = item.get("character", "").strip()
        
        if characters_str and characters_str != "0":
            chars = [c.strip() for c in characters_str.split(',')]
            for c in chars:
                if not c:
                    continue
                # Kiểm tra cả .jpg và .png
                img_p_jpg = os.path.join(img_dir, f"{c}.jpg")
                img_p_png = os.path.join(img_dir, f"{c}.png")
                if not os.path.exists(img_p_jpg) and not os.path.exists(img_p_png):
                    missing_chars.add(c)
                    bad_stts.append(f"  STT {stt}: thiếu ảnh '{c}'")

    if missing_chars:
        detail = "\n".join(bad_stts)
        chars_list = ", ".join(sorted(missing_chars))
        msg = (
            f"Thiếu ảnh nhân vật: {chars_list}\n"
            f"Thư mục: {os.path.basename(img_dir)}/\n\n"
            f"{detail}\n\n"
            f"Vui lòng thêm ảnh nhân vật tương ứng vào thư mục character/."
        )
        return False, msg, list(missing_chars)

    return True, "", []

