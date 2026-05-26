import os
import subprocess
import time

FFMPEG_DIR = os.path.join(os.getcwd(), 'ffmpeg')
FFMPEG_EXE = os.path.join(FFMPEG_DIR, 'ffmpeg.exe')
FFPROBE_EXE = os.path.join(FFMPEG_DIR, 'ffprobe.exe')

def get_video_duration(video_path):
    """Sử dụng ffprobe để lấy thời lượng chính xác của video."""
    try:
        cmd = [
            FFPROBE_EXE,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        duration = float(result.stdout.strip())
        return duration
    except Exception as e:
        print(f"❌ Lỗi đo thời lượng {video_path}: {e}")
        return None

def stretch_video_ffmpeg(input_path, output_path, target_duration):
    """Sử dụng ffmpeg để ép (co/kéo) thời lượng video và bỏ âm thanh."""
    actual_duration = get_video_duration(input_path)
    if not actual_duration:
        return False

    if actual_duration == 0:
        return False

    # Tính toán hệ số PTS (Presentation Time Stamp)
    # setpts = (target_duration / actual_duration) * PTS
    pts_factor = target_duration / actual_duration

    try:
        cmd = [
            FFMPEG_EXE,
            "-y", # Ghi đè file nếu đã tồn tại
            "-i", input_path,
            "-filter:v", f"setpts={pts_factor}*PTS",
            "-an", # Loại bỏ âm thanh
            output_path
        ]
        
        # Chạy ffmpeg ngầm không hiện cửa sổ
        subprocess.run(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, 
            check=True, 
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Lỗi xử lý ffmpeg: {e.stderr}")
        return False
    except Exception as e:
        print(f"❌ Lỗi không xác định khi chạy ffmpeg: {e}")
        return False

def handle_stretch_video(batch, out_path, log_callback):
    """
    Hàm xử lý lô video. (Khớp chữ ký is_healthy, failed_items)
    - batch: danh sách dict chứa {'video_in': path, 'duration': float, 'video_out': path, ...}
    - out_path: thư mục xuất video.
    """
    is_healthy = True
    failed_items = []
    
    if not os.path.exists(out_path):
        os.makedirs(out_path)

    for item in batch:
        input_vid = item.get('video_in')
        target_dur = item.get('duration')
        stt = item.get('STT')
        output_vid = item.get('video_out') # Đường dẫn output theo tên gốc

        log_callback(f"⏳ [Stretch] Đang xử lý STT {stt} ({target_dur}s)...")
        
        if not input_vid or not os.path.exists(input_vid):
            log_callback(f"⚠️ Không tìm thấy video gốc cho STT {stt}")
            failed_items.append(item)
            continue
            
        success = stretch_video_ffmpeg(input_vid, output_vid, target_dur)
        if success and os.path.exists(output_vid) and os.path.getsize(output_vid) > 0:
            log_callback(f"✅ Xong Stretch STT {stt}")
        else:
            log_callback(f"❌ Lỗi Stretch STT {stt}")
            failed_items.append(item)
            
    # Task ffmpeg xử lý local, không ảnh hưởng 'chết profile' như Chrome, nên is_healthy luôn True trừ khi lỗi hệ thống nặng.
    return is_healthy, failed_items

def merge_videos_ffmpeg(json_path, out_dir, log_callback=print):
    """
    Ghép tất cả các file video đã co kéo thành 1 file tổng.
    Tên file tổng = Tên file JSON.
    """
    import json
    
    if not os.path.exists(json_path):
        log_callback(f"⚠️ Không tìm thấy file JSON để ghép video: {json_path}")
        return False
        
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        # Thu thập danh sách các file cần ghép theo đúng thứ tự JSON
        video_files = []
        for item in data:
            timecode = item.get("timecode", "")
            start_time_str = "00-00-00-000"
            if timecode:
                try:
                    parts = timecode.split("-->")
                    if len(parts) == 2:
                        start_part = parts[0].strip()
                        start_time_str = start_part.replace(":", "-").replace(",", "-")
                except:
                    pass
            
            vid_path = os.path.join(out_dir, f"{start_time_str}.mp4")
            if os.path.exists(vid_path):
                # FFmpeg concat yêu cầu đường dẫn tuyệt đối phải được format an toàn, hoặc dùng đường dẫn tương đối
                # Tốt nhất nên chuyển đường dẫn thành dạng an toàn: thay \ thành /
                safe_vid_path = vid_path.replace('\\', '/')
                video_files.append(safe_vid_path)
        
        if not video_files:
            log_callback("⚠️ Không có file video nào để ghép.")
            return False
            
        # Tạo file concat list
        concat_txt_path = os.path.join(out_dir, "concat_list.txt")
        with open(concat_txt_path, 'w', encoding='utf-8') as f:
            for vf in video_files:
                # Cú pháp file của ffmpeg: file 'duong_dan'
                f.write(f"file '{vf}'\n")
                
        # Tên file tổng = Tên JSON
        json_basename = os.path.splitext(os.path.basename(json_path))[0]
        final_output_path = os.path.join(out_dir, f"{json_basename}.mp4")
        
        log_callback(f"🎬 Đang ghép nối {len(video_files)} video thành {json_basename}.mp4 ...")
        
        cmd = [
            FFMPEG_EXE,
            "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_txt_path,
            "-c", "copy",
            final_output_path
        ]
        
        subprocess.run(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, 
            check=True, 
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        
        log_callback(f"🎉 Đã ghép xong video tổng: {final_output_path}")
        
        # Dọn dẹp
        try:
            os.remove(concat_txt_path)
        except:
            pass
            
        return True
    except Exception as e:
        log_callback(f"❌ Lỗi khi ghép video: {e}")
        return False


def convert_image_to_video_ffmpeg(image_path, output_path, duration):
    """Sử dụng ffmpeg local để chuyển đổi ảnh tĩnh thành video mp4 tĩnh có thời lượng duration."""
    try:
        # Lệnh ffmpeg chuyển 1 ảnh thành video mp4 tĩnh:
        # -loop 1 -i {image_path} -t {duration} -pix_fmt yuv420p -c:v libx264 {output_path}
        cmd = [
            FFMPEG_EXE,
            "-y",                     # Ghi đè file nếu đã tồn tại
            "-loop", "1",
            "-i", image_path,
            "-t", str(duration),
            "-pix_fmt", "yuv420p",
            "-c:v", "libx264",
            # scale chẵn chiều rộng và cao để tương thích tốt với các phần mềm phát video
            "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
            output_path
        ]
        
        # Chạy ffmpeg ngầm không hiện cửa sổ
        subprocess.run(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, 
            check=True, 
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Lỗi xử lý ffmpeg convert_image: {e.stderr}")
        return False
    except Exception as e:
        print(f"❌ Lỗi không xác định khi chạy ffmpeg convert_image: {e}")
        return False


def handle_image_to_video(batch, out_path, log_callback):
    """
    Hàm xử lý lô ảnh tĩnh thành video tĩnh bằng FFmpeg. (Local 100%)
    - batch: danh sách dict chứa {'image_in': path, 'duration': float, 'video_out': path, ...}
    - out_path: thư mục xuất video.
    """
    is_healthy = True
    failed_items = []
    
    if not os.path.exists(out_path):
        os.makedirs(out_path)

    for item in batch:
        input_img = item.get('image_in')
        target_dur = item.get('duration')
        stt = item.get('STT')
        output_vid = item.get('video_out')

        log_callback(f"⏳ [Local FFmpeg] Đang tạo video phân cảnh: STT {stt} ({target_dur}s)...")
        
        if not input_img or not os.path.exists(input_img):
            log_callback(f"⚠️ Không tìm thấy ảnh gốc cho STT {stt}")
            failed_items.append(item)
            continue
            
        success = convert_image_to_video_ffmpeg(input_img, output_vid, target_dur)
        if success and os.path.exists(output_vid) and os.path.getsize(output_vid) > 0:
            log_callback(f"✅ Thành công tạo video phân cảnh STT {stt}")
        else:
            log_callback(f"❌ Lỗi tạo video phân cảnh STT {stt}")
            failed_items.append(item)
            
    return is_healthy, failed_items

