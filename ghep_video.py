import os
import sys
import re
import subprocess

def main():
    print("=" * 60)
    print("       HỆ THỐNG GHÉP VIDEO TỰ ĐỘNG (FFMPEG + PYTHON)")
    print("=" * 60)
    print()

    try:
        folder_path = input("👉 Nhập hoặc kéo-thả đường dẫn folder chứa video vào đây: ").strip()
    except EOFError:
        return

    folder_path = folder_path.strip('"').strip("'")

    if not folder_path or not os.path.exists(folder_path):
        print("\n❌ Thư mục không tồn tại! Vui lòng kiểm tra lại đường dẫn.")
        input("\nBấm Enter để thoát...")
        return

    print(f"\n🔍 Đang quét video trong: {folder_path} ...")
    
    # Lấy tất cả file .mp4 (trừ final.mp4)
    files = [f for f in os.listdir(folder_path) if f.lower().endswith('.mp4') and f != 'final.mp4']
    
    if not files:
        print("❌ Không tìm thấy file .mp4 nào trong thư mục!")
        input("\nBấm Enter để thoát...")
        return

    # Sắp xếp chuẩn theo số (1.mp4, 2.mp4... 10.mp4... 26.mp4)
    def extract_num(filename):
        m = re.search(r'(\d+)', filename)
        return int(m.group(1)) if m else 999999

    files.sort(key=extract_num)

    print(f"✅ Tìm thấy {len(files)} file video:")
    print(" ➔ " + ", ".join(files[:15]) + (f" ... và {len(files)-15} file nữa" if len(files) > 15 else ""))

    # Tạo file list.txt tạm trong folder
    list_txt = os.path.join(folder_path, "list_tmp.txt")
    output_mp4 = os.path.join(folder_path, "final.mp4")

    with open(list_txt, "w", encoding="utf-8") as f:
        for fname in files:
            clean_name = fname.replace("'", "'\\''")
            f.write(f"file '{clean_name}'\n")

    print("\n⏳ Đang tiến hành ghép video bằng FFmpeg Concat...")

    # Chạy FFmpeg concat (siêu tốc `-c copy`)
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", list_txt,
        "-c", "copy",
        output_mp4
    ]

    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            print("⚠️ Ghép `-c copy` thất bại (do lệch codec/khung hình), thử mã hóa lại...")
            cmd_reencode = [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", list_txt,
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                output_mp4
            ]
            subprocess.run(cmd_reencode, check=True)
        
        print("\n" + "=" * 60)
        print(f" ✅ HOÀN THÀNH! File video đầu ra: {output_mp4}")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ Lỗi khi chạy FFmpeg: {e}")
    finally:
        if os.path.exists(list_txt):
            try: os.remove(list_txt)
            except: pass

    input("\nBấm Enter để hoàn tất...")

if __name__ == "__main__":
    main()
