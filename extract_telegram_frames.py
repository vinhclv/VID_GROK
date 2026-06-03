import os
import subprocess

FFMPEG_EXE = r"d:\final_I2V\GROK\ffmpeg\ffmpeg.exe"
INPUT_VIDEO = r"C:\Users\CLV_SEO\AppData\Roaming\Telegram Desktop\0602.mp4"
OUTPUT_DIR = r"C:\Users\CLV_SEO\.gemini\antigravity-ide\brain\cd141b7e-90ca-40ec-ac99-efe07ef4bd80"

def extract_frames():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        
    cmd = [
        FFMPEG_EXE,
        "-y",
        "-i", INPUT_VIDEO,
        "-vf", "fps=1",
        os.path.join(OUTPUT_DIR, "tg_frame_%03d.jpg")
    ]
    
    print("Running:", " ".join(cmd))
    try:
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        print("Frames extracted successfully!")
        print("Files:", [f for f in os.listdir(OUTPUT_DIR) if f.startswith("tg_frame")])
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    extract_frames()
