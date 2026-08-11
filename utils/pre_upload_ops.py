"""
pre_upload_ops.py — Logic nghiệp vụ cho Pre-Upload Manager & Xuất bản YouTube (Phần 1 & 3).

Chức năng chính:
  1) merge_project_final_video: Ghép các file mp4 phân đoạn trong output/ thành {ID}.mp4 bằng FFmpeg (có validate 100% clip).
  2) extract_metadata_and_thumb_json: Trích xuất metadata.json (tags dấu phẩy) & thumb.json từ file kịch bản/JSON.
  3) scan_vid_done_status: Quét thư mục 0000_VID_DONE kiểm tra trạng thái 3/3 (Video Final {ID}.mp4, Metadata, Thumbnail).
"""

import os
import re
import json
import subprocess
from pathlib import Path

def extract_4digit_id(name: str) -> str | None:
    """Trích mã ID 4 chữ số đầu tiên từ tên file/folder."""
    m = re.search(r"(\d{4})", name)
    return m.group(1) if m else None

def parse_json_flexible(raw_content: str) -> list | dict | None:
    """Parse JSON linh hoạt từ chuỗi raw (xóa code fences, thẻ XML)."""
    if not raw_content:
        return None
        
    cleaned = raw_content.strip()
    cleaned = re.sub(r"```[a-zA-Z]*\n?", "", cleaned)
    cleaned = re.sub(r"```", "", cleaned).strip()

    try:
        return json.loads(cleaned)
    except Exception:
        pass

    m_arr = re.search(r"\[\s*\{.*\}\s*\]", cleaned, re.DOTALL)
    if m_arr:
        try: return json.loads(m_arr.group(0))
        except: pass

    m_obj = re.search(r"\{\s*\".*\"\s*:.*\}", cleaned, re.DOTALL)
    if m_obj:
        try: return json.loads(m_obj.group(0))
        except: pass

    return None

def extract_metadata_and_thumb_json(script_content_or_path: str, output_dir: str, vid_id: str) -> tuple[bool, str]:
    """
    Trích xuất từ kịch bản thô / JSON:
      1. metadata.json (title, description, tags dạng chuỗi phân cách bởi dấu phẩy)
      2. {vid_id}_thumb.json (giữ nguyên cấu trúc JSON thumbnail gốc)
    """
    try:
        os.makedirs(output_dir, exist_ok=True)

        content = script_content_or_path
        if os.path.exists(script_content_or_path) and os.path.isfile(script_content_or_path):
            with open(script_content_or_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

        data = parse_json_flexible(content)
        if not data:
            return False, "Không parse được dữ liệu JSON từ kịch bản"

        item = data[0] if isinstance(data, list) and len(data) > 0 else data
        if not isinstance(item, dict):
            return False, "Dữ liệu JSON kịch bản không đúng cấu trúc object"

        # 1. Trích xuất Metadata (lọc bỏ các tag có chứa ký tự @)
        title = str(item.get("title", "")).strip()
        description = str(item.get("description", "")).strip()
        raw_tags = item.get("tags", [])

        if isinstance(raw_tags, list):
            clean_tags = [
                str(t).strip() for t in raw_tags
                if str(t).strip() and "@" not in str(t)
            ]
            tags_str = ", ".join(clean_tags)
        else:
            raw_str_tags = str(raw_tags).split(",")
            clean_tags = [
                t.strip() for t in raw_str_tags
                if t.strip() and "@" not in t
            ]
            tags_str = ", ".join(clean_tags)

        metadata_dict = {
            "title": title,
            "description": description,
            "tags": tags_str
        }

        meta_path = os.path.join(output_dir, "metadata.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(metadata_dict, f, indent=2, ensure_ascii=False)

        # 2. Trích xuất Thumbnail JSON (Giữ nguyên cấu trúc gốc)
        thumb_obj = item.get("thumbnail", {})
        thumb_task_item = [{
            "STT": f"{vid_id}_thumb",
            "prompt": json.dumps(thumb_obj, ensure_ascii=False, indent=2) if isinstance(thumb_obj, dict) else str(thumb_obj),
            "thumbnail_data": thumb_obj
        }]

        thumb_path = os.path.join(output_dir, f"{vid_id}_thumb.json")
        with open(thumb_path, "w", encoding="utf-8") as f:
            json.dump(thumb_task_item, f, indent=2, ensure_ascii=False)

        return True, f"Đã tạo metadata.json và {vid_id}_thumb.json"

    except Exception as e:
        return False, f"Lỗi trích xuất: {e}"

def merge_project_final_video(project_folder: str, vid_id: str, log_callback=print) -> tuple[bool, str]:
    """
    Ghép các file mp4 phân đoạn trong output/ thành file {vid_id}.mp4 bằng FFmpeg.
    Có tiền kiểm tra Validate 100% đủ số lượng clip phân đoạn STT theo kịch bản.
    """
    if not os.path.exists(project_folder):
        return False, f"Thư mục không tồn tại: {project_folder}"

    output_dir = os.path.join(project_folder, "output")
    if not os.path.exists(output_dir):
        output_dir = project_folder # Fallback nếu mp4 nằm trực tiếp ở gốc

    output_final_mp4 = os.path.join(project_folder, f"{vid_id}.mp4")

    # Tìm các file mp4 phân đoạn (bỏ qua file final)
    mp4_files = [
        f for f in os.listdir(output_dir)
        if f.lower().endswith(".mp4") and f != f"{vid_id}.mp4" and f != "final.mp4"
    ]

    # Tìm file JSON kịch bản storyboard để đối chiếu số lượng cảnh (STT) mong muốn
    json_storyboard = None
    for f in os.listdir(project_folder):
        if f.endswith(".json") and not f.endswith("metadata.json") and not f.endswith("thumb.json"):
            json_storyboard = os.path.join(project_folder, f)
            break

    expected_stts = set()
    if json_storyboard:
        try:
            with open(json_storyboard, "r", encoding="utf-8", errors="ignore") as f:
                sb_data = json.load(f)
                if isinstance(sb_data, list):
                    for item in sb_data:
                        stt_val = item.get("STT")
                        if stt_val is not None and str(stt_val).isdigit():
                            expected_stts.add(int(stt_val))
        except Exception:
            pass

    # Sắp xếp chuẩn theo số (1.mp4, 2.mp4, ...)
    def extract_num(filename):
        m = re.search(r"(\d+)", filename)
        return int(m.group(1)) if m else 999999

    mp4_files.sort(key=extract_num)
    actual_stts = {extract_num(f) for f in mp4_files if extract_num(f) != 999999}

    # Tiền kiểm tra Validate số lượng: Nếu có file kịch bản JSON, kiểm tra xem đã tạo đủ 100% clip chưa
    if expected_stts:
        missing_stts = sorted(list(expected_stts - actual_stts))
        if missing_stts:
            miss_str = ", ".join(map(str, missing_stts[:5]))
            if len(missing_stts) > 5: miss_str += f" (và {len(missing_stts)-5} clip khác)"
            return False, f"Chưa đủ clip! Thiếu {len(missing_stts)}/{len(expected_stts)} clip phân đoạn STT: [{miss_str}]"
    elif len(mp4_files) == 0:
        return False, f"Không có file video phân đoạn nào trong {output_dir}"

    list_tmp = os.path.join(project_folder, f"concat_list_{vid_id}.txt")
    try:
        with open(list_tmp, "w", encoding="utf-8") as f:
            for fname in mp4_files:
                full_p = os.path.join(output_dir, fname).replace("\\", "/")
                clean_name = full_p.replace("'", "'\\''")
                f.write(f"file '{clean_name}'\n")

        log_callback(f"⏳ Ghép {len(mp4_files)} clip -> {vid_id}.mp4 bằng FFmpeg Concat...")

        # Thử ghép siêu tốc `-c copy`
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", list_tmp,
            "-c", "copy",
            output_final_mp4
        ]

        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            log_callback(f"⚠️ Concat '-c copy' lệch codec, tiến hành mã hóa lại libx264...")
            cmd_reencode = [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", list_tmp,
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                output_final_mp4
            ]
            res_re = subprocess.run(cmd_reencode, capture_output=True, text=True)
            if res_re.returncode != 0:
                return False, f"Lỗi FFmpeg re-encode: {res_re.stderr[:200]}"

        if os.path.exists(output_final_mp4) and os.path.getsize(output_final_mp4) > 1000:
            return True, output_final_mp4
        else:
            return False, "File đầu ra bị rỗng hoặc lỗi ghép."

    except Exception as e:
        return False, f"Exception khi ghép video: {e}"
    finally:
        if os.path.exists(list_tmp):
            try: os.remove(list_tmp)
            except: pass

def scan_vid_done_status(vid_done_dir: str) -> dict:
    """
    Quét thư mục 0000_VID_DONE và trả về thông tin trạng thái 3/3 của từng dự án.
    """
    results = {}
    if not os.path.exists(vid_done_dir) or not os.path.isdir(vid_done_dir):
        return results

    try:
        entries = sorted(os.listdir(vid_done_dir))
    except Exception:
        return results

    for entry in entries:
        folder_path = os.path.join(vid_done_dir, entry)
        if not os.path.isdir(folder_path):
            continue

        vid_id = extract_4digit_id(entry) or entry

        # 1. Kiểm tra Video Final: {ID}.mp4 hoặc final.mp4
        has_video = False
        video_path = ""
        possible_vids = [
            os.path.join(folder_path, f"{vid_id}.mp4"),
            os.path.join(folder_path, "final.mp4"),
            os.path.join(folder_path, "final", f"{vid_id}.mp4"),
        ]
        for v in possible_vids:
            if os.path.exists(v) and os.path.getsize(v) > 1000:
                has_video = True
                video_path = v
                break

        # 2. Kiểm tra Metadata: metadata.json
        has_metadata = False
        meta_path = os.path.join(folder_path, "metadata.json")
        if os.path.exists(meta_path) and os.path.getsize(meta_path) > 0:
            has_metadata = True

        # 3. Kiểm tra Thumbnail: {ID}_thumb.jpg, thumb.jpg, etc.
        has_thumb = False
        thumb_path = ""
        possible_thumbs = [
            os.path.join(folder_path, f"{vid_id}_thumb.jpg"),
            os.path.join(folder_path, f"{vid_id}_thumb.png"),
            os.path.join(folder_path, "thumb.jpg"),
            os.path.join(folder_path, "thumb.png"),
            os.path.join(folder_path, "output_image", "thumb.jpg"),
        ]
        for t in possible_thumbs:
            if os.path.exists(t) and os.path.getsize(t) > 1000:
                has_thumb = True
                thumb_path = t
                break

        is_complete = has_video and has_metadata and has_thumb

        results[entry] = {
            "folder_name": entry,
            "vid_id": vid_id,
            "folder_path": folder_path,
            "has_video": has_video,
            "video_path": video_path,
            "has_metadata": has_metadata,
            "metadata_path": meta_path if has_metadata else "",
            "has_thumb": has_thumb,
            "thumb_path": thumb_path,
            "is_complete": is_complete
        }

    return results


def transfer_to_vid_done(data: dict, target_vid_done_dir: str) -> tuple[bool, str]:
    """
    Chuyển 3 tệp tin tài nguyên hoàn thiện ({ID}.mp4, metadata.json, thumbnail)
    sang thư mục con {target_vid_done_dir}/{vid_id}/.
    """
    import shutil

    if not data.get("is_complete"):
        return False, "Chưa hoàn thiện đủ 3/3 tài nguyên!"

    vid_id = data["vid_id"]
    dest_dir = os.path.join(target_vid_done_dir, vid_id)
    os.makedirs(dest_dir, exist_ok=True)

    try:
        # 1. Video final ({ID}.mp4)
        vid_src = data["video_path"]
        vid_dst = os.path.join(dest_dir, f"{vid_id}.mp4")
        if os.path.abspath(vid_src) != os.path.abspath(vid_dst):
            shutil.copy2(vid_src, vid_dst)

        # 2. Metadata.json
        meta_src = data["metadata_path"]
        meta_dst = os.path.join(dest_dir, "metadata.json")
        if os.path.abspath(meta_src) != os.path.abspath(meta_dst):
            shutil.copy2(meta_src, meta_dst)

        # 3. Thumbnail ({ID}_thumb.jpg / thumb.jpg)
        thumb_src = data["thumb_path"]
        ext = os.path.splitext(thumb_src)[1] or ".jpg"
        thumb_dst = os.path.join(dest_dir, f"{vid_id}_thumb{ext}")
        if os.path.abspath(thumb_src) != os.path.abspath(thumb_dst):
            shutil.copy2(thumb_src, thumb_dst)

        # 4. Thư mục output/ chứa các file clip mp4 phân đoạn
        folder_path = data["folder_path"]
        output_src = os.path.join(folder_path, "output")
        if os.path.exists(output_src) and os.path.isdir(output_src):
            output_dst = os.path.join(dest_dir, "output")
            if os.path.abspath(output_src) != os.path.abspath(output_dst):
                shutil.copytree(output_src, output_dst, dirs_exist_ok=True)

        return True, dest_dir
    except Exception as e:
        return False, f"Lỗi chuyển tài nguyên: {e}"
