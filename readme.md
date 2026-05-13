

## 🛠 1. Các Chế Độ Vận Hành (Mode Map)



| Chế độ                | Mã (Key)         | Đầu vào (Input)                    | Đầu ra (Output)                           |
| **Image ➡ Prompt**   | `image_prompt`   | Folder chứa ảnh                    |Folder chưa  File `[STT].json`             |
| **SRT ➡ Prompt**     | `srt_prompt`     |File kịch bản `[Tên dự án].srt`     |Folder chứa  File `[Tên dự án].json`       |
| **Prompt ➡ Image**   | `prompt_image`   | File kịch bản `[Tên dự án].json`   | Folder chứa ảnh                           |
| **2_Image ➡ Prompt** | `2_image_prompt` | Folder chứa ảnh                    | Folder chứa cặp file `[STT - STT].json`   |
| **SRT ➡ Image**      | `srt_image`      | File kịch bản `[Tên dự án].srt`    | Folder chứa ảnh
| **SRT ➡ Multilanguage** | `srt_multilang` | File kịch bản `[Tên dự án].srt`    | Folder chứa file `[Tên dự án].json`       |
| **SRT ➡ Shuffle**    | `srt_shuffle`    | File kịch bản `[Tên dự án].srt`    | Folder chứa file `[Tên dự án].json`       |
| **Shuffle ➡ Image**  | `shuffle_image`  | Folder chứa ảnh                    | Folder chứa ảnh                           |
| **2_Image + Prompt ➡ Video**| `2_image_prompt_video`| Folder Prompt + Folder Ảnh | Folder chứa Video

[SETUP]
1 Import Profile -> setup lần đầu ( đăng nhập vào gemini test)
2 Cấu hình GEM ( Thêm Gem theo dự án)

[RUN]
1 Chọn Type trong 6 Options
2 Chọn Input Path và OutPut Path và GEM + Prompt (option)
3 Thêm task vào hàng đợi
4 Quay lại bước 4 nếu cần chạy nhiều task
5 Chọn Batch ( Số lần gửi request đến web sau đó tắt profile để tạo bối cảnh mới) + Threads ( Số luồng chạy)
6 Chạy List

[!IMPORTANT]
Lưu ý:  
1 Nếu muốn dừng dự án thì phải chờ chạy xong nốt Batch đang thực thi
=> có thể chọn dừng và tắt các trình duyệt orbita, tự khắc sẽ dừng toàn bộ tool
2 Nếu chất lượng thành phẩm không theo mong muốn thì dừng tool và cập nhật lại các profile + Gmail mới
3 Nếu trình duyệt orbita bị lag thì dừng tool lại, xoá các task orbita chạy ngầm trong Task Manager là chạy ngon luôn