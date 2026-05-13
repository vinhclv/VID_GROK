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

def get_prompt_image_status(prompt_json_path, output_root_dir):
    """
    Đọc file input .json (chứa Prompt).
    Kiểm tra xem file ảnh tương ứng (STT.jpg) đã tồn tại trong thư mục output chưa.
    
    Ví dụ: 
    - Input: data/movie.json
    - Output folder: output_root_dir/movie/
    - Item STT=1 -> Check file: output_root_dir/movie/1.jpg
    """
    pending = []
    completed = []
    
    if not os.path.exists(prompt_json_path):
        return [], []

    try:
        # 1. Đọc nội dung JSON Input
        with open(prompt_json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)


        # 3. Duyệt qua từng item
        for item in data:
            # Lấy STT và Prompt (ép kiểu str để an toàn)
            idx = str(item.get("STT", "")).strip()
            prompt_text = item.get("Prompt", "").strip() # Hoặc key là "text" tùy file json của bạn

            if not idx: continue # Bỏ qua nếu data lỗi không có STT

            # Đường dẫn file ảnh mong đợi
            # (Bạn có thể đổi thành .png nếu tool sinh ra png)
            image_filename = f"{idx}.jpg"
            image_path = os.path.join(output_root_dir, image_filename)

            # Tạo object task
            task_item = {
                "id": idx,
                "prompt": prompt_text,
                "save_path": image_path, # Đường dẫn lưu ảnh để Worker dùng
                "output_folder": output_root_dir,
                "type": "prompt_to_image"
            }

            # 4. Kiểm tra file ảnh có tồn tại và có dung lượng > 0
            if os.path.exists(image_path) and os.path.getsize(image_path) > 0:
                completed.append(task_item)
            else:
                pending.append(task_item)

    except Exception as e:
        print(f"❌ Lỗi đọc JSON Prompt Image: {e}")
        
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
            
            start_time_str = "00-00-00-000"
            if timecode:
                try:
                    start_part = timecode.split("-->")[0].strip()
                    start_time_str = start_part.replace(":", "-").replace(",", "-")
                except:
                    pass
                    
            expected_video_path = os.path.join(out_dir, f"{start_time_str}.mp4")
            
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
