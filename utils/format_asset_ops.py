"""
format_asset_ops.py — Logic nghiệp vụ cho tab Format Asset.

3 pha:
  1) split_and_build   — Tách Script_raw, clean JSON, gộp character → tong_hop_character/
  2) distribute_images — Phân phối ảnh tham chiếu về 0001_input/{ID}/character/
  3) deploy_to_input   — Đóng gói tài nguyên vào 0001_input/{ID}/
"""

import os
import re
import json
import shutil
from pathlib import Path

# ──────────────────────────────────────────────────────────────
# CONSTANTS
# ──────────────────────────────────────────────────────────────

# Split tags: AUTO-DETECT từ nội dung file, không hardcode.
# Extension tự suy từ hậu tố tên tag:
#   _json → .json  |  _srt → .srt  |  còn lại → .txt

# Mapping hậu tố tag → extension file
_EXT_RULES = {
    "_json": ".json",
    "_srt":  ".srt",
}

# Nguồn → đuôi file hợp lệ khi deploy sang 0001_input
DEPLOY_SOURCES = {
    "storyboard_json": "*.json",
    "character_json":  "*.json",
    "subtitle_srt":    "*.srt",
    "audio_script":    "*.mp3",
    "hook_json":       "*.json",
    "character_code":  "*.txt",
}


# ──────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────

def _smart_clean(content: str, file_type: str = "text") -> str:
    """Dọn rác AI: xóa code fences, thẻ XML lạ, chuẩn hoá JSON."""
    if not content:
        return ""

    # Xóa code fences (```json ... ```)
    content = re.sub(r"```[a-zA-Z]*\n?", "", content)
    content = re.sub(r"```", "", content)

    # Xóa thẻ XML wrapper
    content = re.sub(r"<[^>]+>", "", content)

    if file_type == "json":
        # Thử parse JSON chuẩn trước
        try:
            data = json.loads(content)
            if isinstance(data, list):
                return json.dumps(data, indent=2, ensure_ascii=False)
            return json.dumps([data], indent=2, ensure_ascii=False)
        except (json.JSONDecodeError, ValueError):
            pass

        # Fallback: JSONL (mỗi dòng 1 object) → convert sang array
        items = []
        for line in content.splitlines():
            line = line.strip()
            if not line or not line.startswith("{"):
                continue
            try:
                items.append(json.loads(line))
            except (json.JSONDecodeError, ValueError):
                continue

        if items:
            return json.dumps(items, indent=2, ensure_ascii=False)

        return content

    # Text / SRT: strip dòng trống
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    return "\n".join(lines)


def _parse_json_flexible(raw: str) -> list[dict]:
    """Parse JSON linh hoạt: hỗ trợ cả JSON chuẩn (array/object) và JSONL (mỗi dòng 1 object)."""
    cleaned = raw.strip()

    # Xoá code fences
    cleaned = re.sub(r"```[a-zA-Z]*\n?", "", cleaned)
    cleaned = re.sub(r"```", "", cleaned).strip()

    # Thử parse như JSON chuẩn trước
    try:
        data = json.loads(cleaned)
        return data if isinstance(data, list) else [data]
    except (json.JSONDecodeError, ValueError):
        pass

    # Thử parse như JSONL (mỗi dòng 1 object)
    items = []
    for line in cleaned.splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            items.append(json.loads(line))
        except (json.JSONDecodeError, ValueError):
            continue

    return items


def _extract_tag(text: str, tag: str) -> str | None:
    """Trích nội dung giữa <tag>...</tag>."""
    pattern = rf"<{tag}>(.*?)</{tag}>"
    match = re.search(pattern, text, re.DOTALL)
    return match.group(1).strip() if match else None


def _detect_tags(content: str) -> list[str]:
    """Tự phát hiện tất cả thẻ XML <tag>...</tag> trong nội dung."""
    return list(dict.fromkeys(re.findall(r"<([a-zA-Z_][a-zA-Z0-9_]*)>", content)))


def _infer_ext(tag: str) -> str:
    """Suy extension từ tên tag: _json→.json, _srt→.srt, mặc định .txt."""
    for suffix, ext in _EXT_RULES.items():
        if tag.lower().endswith(suffix):
            return ext
    return ".txt"


def _extract_4digit_id(filename: str) -> str | None:
    """Trích mã ID 4 chữ số đầu tiên từ tên file."""
    m = re.search(r"(\d{4})", filename)
    return m.group(1) if m else None


def _ensure_noneimg(character_dir: Path) -> None:
    """Tạo ảnh trắng NONEIMG.jpg nếu chưa có (sử dụng PIL hoặc bytes thủ công)."""
    noneimg = character_dir / "NONEIMG.jpg"
    if noneimg.exists():
        return

    character_dir.mkdir(parents=True, exist_ok=True)

    try:
        from PIL import Image
        img = Image.new("RGB", (100, 100), (255, 255, 255))
        img.save(str(noneimg), "JPEG")
    except ImportError:
        # Fallback: tạo file JPEG tối thiểu bằng raw bytes
        # Minimal valid JPEG: 1x1 white pixel
        _MINIMAL_WHITE_JPEG = bytes([
            0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46,
            0x00, 0x01, 0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00,
            0xFF, 0xDB, 0x00, 0x43, 0x00, 0x08, 0x06, 0x06, 0x07, 0x06,
            0x05, 0x08, 0x07, 0x07, 0x07, 0x09, 0x09, 0x08, 0x0A, 0x0C,
            0x14, 0x0D, 0x0C, 0x0B, 0x0B, 0x0C, 0x19, 0x12, 0x13, 0x0F,
            0x14, 0x1D, 0x1A, 0x1F, 0x1E, 0x1D, 0x1A, 0x1C, 0x1C, 0x20,
            0x24, 0x2E, 0x27, 0x20, 0x22, 0x2C, 0x23, 0x1C, 0x1C, 0x28,
            0x37, 0x29, 0x2C, 0x30, 0x31, 0x34, 0x34, 0x34, 0x1F, 0x27,
            0x39, 0x3D, 0x38, 0x32, 0x3C, 0x2E, 0x33, 0x34, 0x32, 0xFF,
            0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01, 0x00, 0x01, 0x01, 0x01,
            0x11, 0x00, 0xFF, 0xC4, 0x00, 0x1F, 0x00, 0x00, 0x01, 0x05,
            0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00,
            0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06,
            0x07, 0x08, 0x09, 0x0A, 0x0B, 0xFF, 0xC4, 0x00, 0xB5, 0x10,
            0x00, 0x02, 0x01, 0x03, 0x03, 0x02, 0x04, 0x03, 0x05, 0x05,
            0x04, 0x04, 0x00, 0x00, 0x01, 0x7D, 0x01, 0x02, 0x03, 0x00,
            0x04, 0x11, 0x05, 0x12, 0x21, 0x31, 0x41, 0x06, 0x13, 0x51,
            0x61, 0x07, 0x22, 0x71, 0x14, 0x32, 0x81, 0x91, 0xA1, 0x08,
            0x23, 0x42, 0xB1, 0xC1, 0x15, 0x52, 0xD1, 0xF0, 0x24, 0x33,
            0x62, 0x72, 0x82, 0x09, 0x0A, 0x16, 0x17, 0x18, 0x19, 0x1A,
            0x25, 0x26, 0x27, 0x28, 0x29, 0x2A, 0x34, 0x35, 0x36, 0x37,
            0x38, 0x39, 0x3A, 0x43, 0x44, 0x45, 0x46, 0x47, 0x48, 0x49,
            0x4A, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59, 0x5A, 0x63,
            0x64, 0x65, 0x66, 0x67, 0x68, 0x69, 0x6A, 0x73, 0x74, 0x75,
            0x76, 0x77, 0x78, 0x79, 0x7A, 0x83, 0x84, 0x85, 0x86, 0x87,
            0x88, 0x89, 0x8A, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98,
            0x99, 0x9A, 0xA2, 0xA3, 0xA4, 0xA5, 0xA6, 0xA7, 0xA8, 0xA9,
            0xAA, 0xB2, 0xB3, 0xB4, 0xB5, 0xB6, 0xB7, 0xB8, 0xB9, 0xBA,
            0xC2, 0xC3, 0xC4, 0xC5, 0xC6, 0xC7, 0xC8, 0xC9, 0xCA, 0xD2,
            0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8, 0xD9, 0xDA, 0xE1, 0xE2,
            0xE3, 0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9, 0xEA, 0xF1, 0xF2,
            0xF3, 0xF4, 0xF5, 0xF6, 0xF7, 0xF8, 0xF9, 0xFA, 0xFF, 0xDA,
            0x00, 0x08, 0x01, 0x01, 0x00, 0x00, 0x3F, 0x00, 0x7B, 0x94,
            0x11, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
            0x00, 0x00, 0x00, 0x00, 0x00, 0xFF, 0xD9,
        ])
        with open(noneimg, "wb") as f:
            f.write(_MINIMAL_WHITE_JPEG)


def scan_project(root: str) -> dict:
    """Quét thông tin cơ bản của project, trả về dict tóm tắt."""
    root_path = Path(root)
    info = {
        "root": root,
        "script_raw_count": 0,
        "script_ids": [],
        "has_tong_hop": False,
        "ref_image_count": 0,
        "input_ids": [],
    }

    # Script_raw
    script_raw = root_path / "Script_raw"
    if script_raw.exists():
        files = sorted(script_raw.glob("*.txt"))
        info["script_raw_count"] = len(files)
        for f in files:
            vid = _extract_4digit_id(f.name)
            if vid and vid not in info["script_ids"]:
                info["script_ids"].append(vid)

    # tong_hop_character
    thc = root_path / "tong_hop_character"
    info["has_tong_hop"] = thc.exists() and (thc / "tong_hop_character.json").exists()

    # tong_hop_thumbnail
    tht = root_path / "tong_hop_thumbnail"
    info["has_tong_hop_thumb"] = tht.exists() and (tht / "all_thumbnails.json").exists()

    # output_image count
    oi = thc / "output_image" if thc.exists() else None
    if oi and oi.exists():
        info["ref_image_count"] = len([
            f for f in oi.iterdir()
            if f.is_file() and f.suffix.lower() in (".jpg", ".png", ".jpeg")
        ])

    # 0001_input IDs
    input_dir = root_path / "0001_input"
    if input_dir.exists():
        info["input_ids"] = sorted([
            d.name for d in input_dir.iterdir()
            if d.is_dir() and d.name.isdigit()
        ])

    return info


# ──────────────────────────────────────────────────────────────
# PHA 1: SPLIT & BUILD
# ──────────────────────────────────────────────────────────────

def phase1_split_and_build(root: str, log) -> bool:
    """
    1. Tách Script_raw theo XML tags → thư mục thành phần
    2. Clean & format JSON
    3. Gộp character_json → tong_hop_character.json
    4. Gộp thumbnail_json → tong_hop_thumbnail/all_thumbnails.json
    5. Tạo NONEIMG.jpg
    """
    root_path = Path(root)
    script_raw = root_path / "Script_raw"

    if not script_raw.exists():
        log("❌ Không tìm thấy thư mục Script_raw/", "ERROR")
        return False

    txt_files = sorted(script_raw.glob("*.txt"))
    if not txt_files:
        log("❌ Script_raw/ trống — không có file .txt nào.", "ERROR")
        return False

    # ── Bước 1+2: Tách tag & clean ──
    log("━━━ BƯỚC 1: TÁCH SCRIPT_RAW ━━━", "INFO")
    split_count = 0
    for f in txt_files:
        try:
            content = f.read_text(encoding="utf-8")
        except Exception as e:
            log(f"  ❌ Không đọc được {f.name}: {e}", "ERROR")
            continue

        vid_id = _extract_4digit_id(f.name)
        log(f"  📄 {f.name} (ID: {vid_id or '?'})", "INFO")

        # Auto-detect tất cả thẻ XML trong file
        tags_found = _detect_tags(content)
        for tag in tags_found:
            data = _extract_tag(content, tag)
            if not data:
                continue

            ext = _infer_ext(tag)
            file_type = "json" if ext == ".json" else "text"
            cleaned = _smart_clean(data, file_type)

            # Lưu file — tên gọn: bỏ hậu tố trùng ext (storyboard_json → storyboard)
            folder = root_path / tag
            folder.mkdir(exist_ok=True)
            prefix = vid_id if vid_id else f.stem
            clean_tag = tag
            for suffix in _EXT_RULES:
                if tag.lower().endswith(suffix):
                    clean_tag = tag[:len(tag) - len(suffix)]
                    break
            out_name = f"{prefix}_{clean_tag}{ext}"
            out_file = folder / out_name
            out_file.write_text(cleaned, encoding="utf-8")
            log(f"    ✅ {tag} → {ext}", "SUCCESS")

        split_count += 1

    log(f"  📊 Đã tách {split_count} file script.", "INFO")

    # ── Bước 3: Gộp character_json → tong_hop_character ──
    log("━━━ BƯỚC 2: GỘP CHARACTER → TONG_HOP ━━━", "INFO")
    char_json_dir = root_path / "character_json"

    if not char_json_dir.exists():
        log("  ⚠️ Không có thư mục character_json/ — bỏ qua gộp.", "WARNING")
    else:
        merged = []
        for cf in sorted(char_json_dir.glob("*.json")):
            vid_id = _extract_4digit_id(cf.name)
            if not vid_id:
                continue
            try:
                raw = cf.read_text(encoding="utf-8")
                items = _parse_json_flexible(raw)

                if not items:
                    log(f"  ⚠️ Không parse được JSON trong {cf.name}", "WARNING")
                    continue

                for item in items:
                    # Sửa STT: thêm prefix ID nếu chưa có
                    stt = str(item.get("STT", ""))
                    char_name = str(item.get("character", ""))

                    if not stt.startswith(vid_id):
                        if char_name and char_name != "NONEIMG":
                            new_stt = f"{vid_id}_{char_name}"
                        else:
                            new_stt = f"{vid_id}_{stt}"
                        item["STT"] = new_stt

                    item["character"] = "NONEIMG"
                    merged.append(item)

            except Exception as e:
                log(f"  ⚠️ Lỗi parse {cf.name}: {e}", "WARNING")

        if merged:
            thc_dir = root_path / "tong_hop_character"
            thc_dir.mkdir(exist_ok=True)

            out_json = thc_dir / "tong_hop_character.json"
            out_json.write_text(
                json.dumps(merged, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
            log(f"  ✅ Gộp {len(merged)} nhân vật → tong_hop_character.json", "SUCCESS")

            # Tạo NONEIMG
            _ensure_noneimg(thc_dir / "character")
            log("  ✅ Tạo character/NONEIMG.jpg", "SUCCESS")
        else:
            log("  ⚠️ Không tìm thấy dữ liệu character_json hợp lệ.", "WARNING")

    # ── Bước 4: Gộp prompt Thumbnail → tong_hop_thumbnail ──
    log("━━━ BƯỚC 3: GỘP THUMBNAIL → TONG_HOP_THUMBNAIL ━━━", "INFO")
    merged_thumbs = []
    seen_ids = set()

    # Chỉ quét duy nhất từ 0001_input/ và các thư mục con chứa file *_thumb.json
    search_dirs = [
        root_path / "0001_input",
        root_path,
    ]

    for s_dir in search_dirs:
        if not s_dir.exists():
            continue
        try:
            found_files = sorted(s_dir.rglob("*_thumb.json"))
        except Exception:
            found_files = []

        for tf in found_files:
            # Bỏ qua nếu là file trong tong_hop_thumbnail
            if "tong_hop_thumbnail" in tf.parts:
                continue

            vid_id = _extract_4digit_id(tf.name)
            if not vid_id or vid_id in seen_ids:
                continue

            try:
                raw = tf.read_text(encoding="utf-8")
                items = _parse_json_flexible(raw)
                if items:
                    for item in items:
                        if isinstance(item, dict):
                            item["STT"] = f"{vid_id}_thumb"
                            merged_thumbs.append(item)
                            seen_ids.add(vid_id)
                            log(f"  📄 Tìm thấy {tf.name} (ID: {vid_id})", "INFO")
                            break
            except Exception as e:
                log(f"  ⚠️ Lỗi parse {tf.name}: {e}", "WARNING")

    if merged_thumbs:
        tht_dir = root_path / "tong_hop_thumbnail"
        tht_dir.mkdir(exist_ok=True)
        (tht_dir / "output_image").mkdir(exist_ok=True)
        (tht_dir / "character").mkdir(exist_ok=True)
        _ensure_noneimg(tht_dir / "character")

        out_json = tht_dir / "all_thumbnails.json"
        out_json.write_text(
            json.dumps(merged_thumbs, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        log(f"  ✅ Gộp {len(merged_thumbs)} prompt Thumbnail từ 0001_input/thư mục con → tong_hop_thumbnail/all_thumbnails.json", "SUCCESS")
        log("  ✅ Tạo thư mục character/ và NONEIMG.jpg cho tong_hop_thumbnail", "SUCCESS")
    else:
        log("  ⚠️ Không tìm thấy file *_thumb.json nào trong 0001_input/ hoặc thư mục con.", "WARNING")

    if merged_thumbs:
        tht_dir = root_path / "tong_hop_thumbnail"
        tht_dir.mkdir(exist_ok=True)
        (tht_dir / "output_image").mkdir(exist_ok=True)

        out_json = tht_dir / "all_thumbnails.json"
        out_json.write_text(
            json.dumps(merged_thumbs, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        log(f"  ✅ Gộp {len(merged_thumbs)} prompt Thumbnail → tong_hop_thumbnail/all_thumbnails.json", "SUCCESS")
    else:
        log("  ⚠️ Không tìm thấy prompt Thumbnail trong các dự án.", "WARNING")

    log("✨ PHA 1 HOÀN THÀNH — Sẵn sàng import tong_hop_character/ & tong_hop_thumbnail/ để tạo ảnh!", "SUCCESS")
    return True


# ──────────────────────────────────────────────────────────────
# PHA 2: PHÂN PHỐI ẢNH & DEPLOY TÀI NGUYÊN → 0001_INPUT
# ──────────────────────────────────────────────────────────────

def phase2_distribute_and_deploy(root: str, log) -> bool:
    """
    Gộp Pha 2 & 3:
    1. Đọc tong_hop_character/output_image/ → copy & rename về 0001_input/{ID}/character/
    2. Đọc tong_hop_thumbnail/output_image/ (hoặc tong_hop_thumbnail/) → copy về 0001_input/{ID}/{ID}_thumb.jpg
    3. Copy storyboard_json → 0001_input/{ID}/
    4. Copy tài nguyên phụ → 0001_input/{ID}/_resources/
    """
    root_path = Path(root)
    input_dir = root_path / "0001_input"
    input_dir.mkdir(exist_ok=True)

    # --- 1. Phân phối ảnh nhân vật tham chiếu ---
    log("━━━ BƯỚC 1: PHÂN PHỐI ẢNH THAM CHIẾU NHÂN VẬT ━━━", "INFO")
    output_img = root_path / "tong_hop_character" / "output_image"
    img_count = 0
    id_img_stats = {}

    if not output_img.exists():
        log("  ⚠️ Chưa thấy tong_hop_character/output_image/ — bỏ qua copy ảnh nhân vật.", "WARNING")
    else:
        img_files = [
            f for f in output_img.iterdir()
            if f.is_file() and f.suffix.lower() in (".jpg", ".png", ".jpeg")
            and f.name != "Thumbs.db"
        ]
        if not img_files:
            log("  ⚠️ tong_hop_character/output_image/ trống — chưa có ảnh nhân vật.", "WARNING")
        else:
            for img in sorted(img_files):
                vid_id = _extract_4digit_id(img.name)
                if not vid_id:
                    log(f"  ⚠️ Bỏ qua {img.name} — không có ID 4 số.", "WARNING")
                    continue

                prefix = f"{vid_id}_"
                new_name = img.name[len(prefix):] if img.name.startswith(prefix) else img.name

                char_dir = input_dir / vid_id / "character"
                char_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(img, char_dir / new_name)

                id_img_stats[vid_id] = id_img_stats.get(vid_id, 0) + 1
                img_count += 1

            for vid_id, cnt in sorted(id_img_stats.items()):
                log(f"  ✅ ID {vid_id}: {cnt} ảnh nhân vật → character/", "SUCCESS")

    # --- 2. Phân phối ảnh Thumbnail ({ID}_thumb.jpg) ---
    log("━━━ BƯỚC 2: PHÂN PHỐI ẢNH THUMBNAIL ━━━", "INFO")
    tht_img_dir = root_path / "tong_hop_thumbnail" / "output_image"
    if not tht_img_dir.exists():
        tht_img_dir = root_path / "tong_hop_thumbnail"

    if tht_img_dir.exists():
        thumb_files = [
            f for f in tht_img_dir.iterdir()
            if f.is_file() and f.suffix.lower() in (".jpg", ".png", ".jpeg")
            and f.name != "Thumbs.db"
        ]
        thumb_cnt = 0
        for t_img in sorted(thumb_files):
            vid_id = _extract_4digit_id(t_img.name)
            if not vid_id:
                continue

            target_folder = input_dir / vid_id
            target_folder.mkdir(parents=True, exist_ok=True)

            ext = t_img.suffix.lower()
            dst_path = target_folder / f"{vid_id}_thumb{ext}"
            shutil.copy2(t_img, dst_path)
            log(f"  ✅ ID {vid_id}: Phân phối {t_img.name} → {vid_id}_thumb{ext}", "SUCCESS")
            thumb_cnt += 1

        if thumb_cnt == 0:
            log("  ⚠️ Chưa có ảnh Thumbnail trong tong_hop_thumbnail/", "WARNING")
    else:
        log("  ⚠️ Chưa tạo tong_hop_thumbnail/ — bỏ qua phân phối thumbnail.", "WARNING")

    # --- 3. Deploy Storyboard & Tài nguyên phụ ---
    log("━━━ BƯỚC 3: DEPLOY STORYBOARD & TÀI NGUYÊN ━━━", "INFO")
    MAIN_JSON = "storyboard_json"
    EXTRA_SOURCES = {k: v for k, v in DEPLOY_SOURCES.items() if k != MAIN_JSON}

    all_ids = set(id_img_stats.keys())
    for folder_name in DEPLOY_SOURCES:
        folder = root_path / folder_name
        if folder.exists():
            for f in folder.iterdir():
                vid = _extract_4digit_id(f.name)
                if vid:
                    all_ids.add(vid)

    if not all_ids:
        log("❌ Không tìm thấy ID dự án nào để deploy.", "ERROR")
        return False

    total_count = 0
    for vid_id in sorted(all_ids):
        target = input_dir / vid_id
        target.mkdir(exist_ok=True)
        deployed = []

        # Copy JSON chính (storyboard)
        src_main = root_path / MAIN_JSON
        if src_main.exists():
            for f in src_main.glob(f"*{vid_id}*"):
                if f.suffix.lower() == ".json":
                    shutil.copy2(f, target / f.name)
                    deployed.append("storyboard_json")
                    break

        # Copy tài nguyên phụ → _resources/
        res_dir = target / "_resources"
        for folder_name, pattern in EXTRA_SOURCES.items():
            src_folder = root_path / folder_name
            if not src_folder.exists():
                continue
            expected_ext = pattern.replace("*", "")
            for f in src_folder.glob(f"*{vid_id}*"):
                if f.suffix.lower() == expected_ext.lower():
                    res_dir.mkdir(exist_ok=True)
                    shutil.copy2(f, res_dir / f.name)
                    deployed.append(folder_name)

        has_main = "storyboard_json" in deployed
        has_char = (target / "character").exists()
        status = "✅" if has_main and has_char else "⚠️"
        
        info_parts = []
        if deployed:
            info_parts.append(", ".join(sorted(set(deployed))))
        if has_char:
            info_parts.append("character/ ✅")
        else:
            info_parts.append("❌ character/ chưa có")

        log(f"  {status} ID {vid_id}: {' | '.join(info_parts)}",
            "SUCCESS" if has_main else "WARNING")
        total_count += 1

    log(f"✨ PHA 2 HOÀN THÀNH — Đã đóng gói {total_count} dự án vào 0001_input/ sẵn sàng Import!", "SUCCESS")
    return True

