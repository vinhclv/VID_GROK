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
