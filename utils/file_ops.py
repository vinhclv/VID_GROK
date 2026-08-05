import os
import re
import json

def get_srt_prompt_status(srt_path, output_dir):
    """
    Đọc file .srt và kiểm tra trạng thái dựa trên file JSON tổng nằm trong output_dir.
    File JSON tổng có tên giống file SRT.
    Ví dụ: input là 'movie.srt' -> output check 'output_dir/movie.json'
    """
    pending = []
    completed = []
    
    if not os.path.exists(srt_path):
        return [], []

    try:
        # 1. Đọc nội dung SRT
        with open(srt_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Regex tách các đoạn sub
        pattern = re.compile(r'(\d+)\n(\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3})\n(.*?)(?=\n\d+\n|\Z)', re.DOTALL)
        matches = pattern.findall(content)

        # 2. Xác định file JSON Output
        srt_name = os.path.splitext(os.path.basename(srt_path))[0]
        json_output_path = os.path.join(output_dir, f"{srt_name}.json")

        # 3. Lấy danh sách các STT đã làm xong từ file JSON tổng (nếu có)
        completed_ids = set()
        if os.path.exists(json_output_path):
            try:
                with open(json_output_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Giả sử cấu trúc: [{"STT": "1", "Prompt": "..."}, ...]
                    if isinstance(data, list):
                        for item in data:
                            if "STT" in item:
                                completed_ids.add(str(item["STT"]))
            except Exception as e:
                print(f"⚠️ Lỗi đọc file JSON output hiện tại: {e}")

        # 4. Phân loại Task
        for idx, time_range, text in matches:
            idx = str(idx).strip()
            text = text.strip().replace('\n', ' ')
            
            task_item = {
                "STT": idx,           
                "text": text,
                "Timecode": time_range,
                "json_path": json_output_path, 
            }

            if idx in completed_ids:
                completed.append(task_item)
            else:
                pending.append(task_item)

    except Exception as e:
        print(f"❌ Lỗi xử lý SRT: {e}")
        
    return pending, completed

def get_prompt_image_status(json_path, img_dir, out_dir):
    """
    Đọc file JSON và đối chiếu với thư mục ảnh đầu ra out_dir,
    đồng thời nạp các ảnh tham chiếu trong thư mục img_dir (nếu có).
    """
    pending = []
    completed = []
    
    if not os.path.exists(json_path):
        return [], []
        
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        for item in data:
            stt = str(item.get("STT", "")).strip()
            if not stt:
                continue
                
            prompt_text = item.get("prompt", item.get("Prompt", "")).strip()
            characters_str = item.get("character", "").strip()
            
            expected_image_path = os.path.join(out_dir, f"{stt}.jpg")
            
            image_paths = []
            skip_item = False
            if characters_str and characters_str != "0":
                chars = [c.strip() for c in characters_str.split(',')]
                for c in chars:
                    if not c: continue
                    img_p = os.path.join(img_dir, f"{c}.jpg")
                    if not os.path.exists(img_p):
                        img_p = os.path.join(img_dir, f"{c}.png")
                    if not os.path.exists(img_p):
                        skip_item = True
                        break
                    image_paths.append(img_p)
                    
            if skip_item:
                continue
                
            task_item = {
                "STT": stt,
                "prompt": prompt_text,
                "image_paths": image_paths,
                "save_path": expected_image_path,
                "output_folder": out_dir,
                "type": "prompt_to_image"
            }
            
            if os.path.exists(expected_image_path) and os.path.getsize(expected_image_path) > 0:
                completed.append(task_item)
            else:
                pending.append(task_item)
                
    except Exception as e:
        print(f"❌ Lỗi quét prompt_image: {e}")
        
    return pending, completed

def get_1_image_prompt_video_status(json_path, img_dir, out_dir):
    pending = []
    completed = []
    
    if not os.path.exists(json_path) or not os.path.exists(img_dir):
        return [], []
        
    try:
        import json
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        for item in data:
            stt = str(item.get("STT"))
            timecode = item.get("timecode", "")
            prompt_text = item.get("prompt", "")
            characters_str = item.get("character", "")
            
            expected_video_path = os.path.join(out_dir, f"{stt}.mp4")
            
            image_paths = []
            skip_item = False
            if characters_str and characters_str != "0":
                chars = [c.strip() for c in characters_str.split(',')]
                for c in chars:
                    if not c: continue
                    img_p = os.path.join(img_dir, f"{c}.jpg")
                    if not os.path.exists(img_p):
                        img_p = os.path.join(img_dir, f"{c}.png")
                    if not os.path.exists(img_p):
                        skip_item = True
                        break
                    image_paths.append(img_p)
                    
            if skip_item:
                continue
                
            duration = 5
            if timecode:
                try:
                    parts = timecode.split('-->')
                    if len(parts) == 2:
                        def to_seconds(tc):
                            tc = tc.strip()
                            h, m, s = tc.split(':')
                            s, ms = s.split(',')
                            return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000
                        duration = to_seconds(parts[1]) - to_seconds(parts[0])
                except: pass
                
            task_item = {
                "STT": stt,
                "visual_details": prompt_text,
                "image_paths": image_paths,
                "duration": duration,
                "Timecode": timecode,
                "video_path": expected_video_path
            }
            
            if os.path.exists(expected_video_path) and os.path.getsize(expected_video_path) > 0:
                completed.append(task_item)
            else:
                pending.append(task_item)
                
    except Exception as e:
        print(f"❌ Lỗi quét 1_image_prompt_video: {e}")
        
    return pending, completed

def get_stretch_video_status(json_path, video_in_dir, out_dir):
    pending = []
    completed = []
    
    if not os.path.exists(json_path) or not os.path.exists(video_in_dir):
        return [], []
        
    try:
        import json
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        for item in data:
            stt = str(item.get("STT"))
            timecode = item.get("timecode", "")
            
            duration = 5.0
            
            if timecode:
                try:
                    parts = timecode.split("-->")
                    if len(parts) == 2:
                        def to_seconds(tc):
                            tc = tc.strip()
                            h, m, s = tc.split(':')
                            s, ms = s.split(',')
                            return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000
                            
                        duration = to_seconds(parts[1]) - to_seconds(parts[0])
                except:
                    pass
                    
            input_video_path = os.path.join(video_in_dir, f"{stt}.mp4")
            output_video_path = os.path.join(out_dir, f"{stt}.mp4")

            task_item = {
                "STT": stt,
                "video_in": input_video_path,
                "video_out": output_video_path,
                "duration": duration,
                "Timecode": timecode
            }
            
            if os.path.exists(output_video_path) and os.path.getsize(output_video_path) > 0:
                completed.append(task_item)
            else:
                pending.append(task_item)
                
    except Exception as e:
        print(f"❌ Lỗi quét stretch_video: {e}")
        
    return pending, completed

def validate_stretch_videos(json_path, video_in_dir):
    """
    Hàm kiểm tra cứng trước khi chạy Batch.
    Kiểm tra xem tất cả các mục trong file JSON có file video tương ứng trong thư mục Input hay không.
    Trả về (True, "") nếu mọi thứ đều khớp.
    Trả về (False, "Lý do lỗi") nếu có bất kỳ file nào bị thiếu.
    """
    if not os.path.exists(json_path):
        return False, f"Không tìm thấy file JSON: {json_path}"
    if not os.path.exists(video_in_dir):
        return False, f"Không tìm thấy thư mục video gốc: {video_in_dir}"
        
    try:
        import json
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        missing_files = []
        for item in data:
            stt = str(item.get("STT"))
                    
            input_video_path = os.path.join(video_in_dir, f"{stt}.mp4")
            if not os.path.exists(input_video_path):
                missing_files.append(f"STT: {stt} -> {stt}.mp4")
                
        if missing_files:
            err_msg = f"Thiếu {len(missing_files)} file video so với JSON!\nCác file bị thiếu:\n" + "\n".join(missing_files[:5])
            if len(missing_files) > 5:
                err_msg += f"\n... và {len(missing_files) - 5} file khác."
            return False, err_msg
    except Exception as e:
        return False, f"Lỗi đọc JSON: {e}"


def get_image_to_video_status(json_path, img_dir, out_dir):
    """
    Đọc file kịch bản JSON và đối chiếu với thư mục chứa ảnh tĩnh img_dir.
    Tìm kiếm [STT].jpg hoặc [STT].png tương ứng trong img_dir.
    Tính thời lượng video dựa theo timecode.
    """
    pending = []
    completed = []
    
    if not os.path.exists(json_path) or not os.path.exists(img_dir):
        return [], []
        
    try:
        import json
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        for item in data:
            stt = str(item.get("STT", "")).strip()
            if not stt:
                continue
                
            timecode = item.get("timecode", "").strip()
            
            duration = 5.0
            
            if timecode:
                try:
                    parts = timecode.split("-->")
                    if len(parts) == 2:
                        def to_seconds(tc):
                            tc = tc.strip()
                            h, m, s = tc.split(':')
                            s, ms = s.split(',')
                            return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000
                            
                        duration = to_seconds(parts[1]) - to_seconds(parts[0])
                except:
                    pass
                    
            input_image_path = os.path.join(img_dir, f"{stt}.jpg")
            if not os.path.exists(input_image_path):
                input_image_path = os.path.join(img_dir, f"{stt}.png")
                
            if not os.path.exists(input_image_path):
                # Không tìm thấy ảnh tĩnh cảnh cho phân đoạn này -> Bỏ qua
                continue
                
            output_video_path = os.path.join(out_dir, f"{stt}.mp4")

            task_item = {
                "STT": stt,
                "image_in": input_image_path,
                "video_out": output_video_path,
                "duration": duration,
                "Timecode": timecode
            }
            
            if os.path.exists(output_video_path) and os.path.getsize(output_video_path) > 0:
                completed.append(task_item)
            else:
                pending.append(task_item)
                
    except Exception as e:
        print(f"❌ Lỗi quét image_to_video: {e}")
        
    return pending, completed


def validate_image_to_video(json_path, img_dir):
    """
    Hàm kiểm tra cứng trước khi chạy Batch cho chế độ Image ➡ Video.
    Kiểm tra xem tất cả các mục trong file JSON có file ảnh tĩnh [STT].jpg/.png tương ứng hay không.
    """
    if not os.path.exists(json_path):
        return False, f"Không tìm thấy file JSON: {json_path}"
    if not os.path.exists(img_dir):
        return False, f"Không tìm thấy thư mục ảnh cảnh: {img_dir}"
        
    try:
        import json
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        missing_files = []
        for item in data:
            stt = str(item.get("STT", "")).strip()
            if not stt:
                continue
                
            input_image_path = os.path.join(img_dir, f"{stt}.jpg")
            if not os.path.exists(input_image_path):
                input_image_path = os.path.join(img_dir, f"{stt}.png")
                
            if not os.path.exists(input_image_path):
                missing_files.append(f"STT: {stt} -> {stt}.jpg/.png")
                
        if missing_files:
            err_msg = f"Thiếu {len(missing_files)} file ảnh tĩnh so với kịch bản JSON!\nCác file bị thiếu:\n" + "\n".join(missing_files[:5])
            if len(missing_files) > 5:
                err_msg += f"\n... và {len(missing_files) - 5} file khác."
            return False, err_msg
            
        return True, ""
    except Exception as e:
        return False, f"Lỗi đọc JSON: {e}"

