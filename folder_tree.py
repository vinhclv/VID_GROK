import os
from pathlib import Path

def generate_tree(dir_path: Path, prefix: str = ""):
    """
    Hàm đệ quy để vẽ cây thư mục.
    """
    try:
        # Lấy danh sách file/folder, bỏ qua file ẩn (.) và (__)
        # Sắp xếp: Folder lên trước, File xuống sau
        contents = [
            x for x in dir_path.iterdir() 
            if not x.name.startswith('.') and not x.name.startswith('__')
        ]
        contents.sort(key=lambda x: (not x.is_dir(), x.name.lower()))
    except PermissionError:
        print(f"{prefix}└── [Access Denied!]")
        return
    except FileNotFoundError:
        print(f"{prefix}└── [Path Not Found!]")
        return

    # Số lượng item trong thư mục
    count = len(contents)
    
    for index, item in enumerate(contents):
        # Kiểm tra xem đây có phải là item cuối cùng trong danh sách không
        is_last = (index == count - 1)
        
        # Chọn ký tự nối phù hợp
        connector = "└── " if is_last else "├── "
        
        # In ra tên item
        print(f"{prefix}{connector}{item.name}")
        
        # Nếu là folder, gọi đệ quy
        if item.is_dir():
            # Tính toán prefix cho cấp con
            # Nếu item hiện tại là cuối cùng, cấp con không cần gạch dọc (│)
            # Nếu item hiện tại chưa hết, cấp con cần gạch dọc để nối xuống dưới
            extension = "    " if is_last else "│   "
            generate_tree(item, prefix + extension)

def main():
    print("--- CÔNG CỤ VẼ CÂY THƯ MỤC ---")
    
    # Đường dẫn mặc định của bạn (Sử dụng r"" để tránh lỗi ký tự đặc biệt trong Windows)
    default_path = r"\\Synology-new\data share\V\V_Carl Jung\03\root"
    
    # Hỏi người dùng
    print(f"Nhấn Enter để dùng path mặc định: {default_path}")
    raw_input = input("Hoặc dán đường dẫn khác vào đây: ").strip()
    
    # Logic: Nếu không nhập gì thì dùng mặc định
    if raw_input == "":
        input_path = default_path
    else:
        # Xử lý nếu người dùng lỡ copy cả dấu ngoặc kép
        input_path = raw_input.strip('"').strip("'")
        
    path_obj = Path(input_path)

    print("\n" + "="*40)
    if not path_obj.exists():
        print(f"❌ LỖI: Đường dẫn không tồn tại!\n{input_path}")
        input("Nhấn Enter để thoát...")
        return

    print(f"📁 ROOT: {path_obj.name}")
    print(f"📍 Full Path: {input_path}")
    print("-" * 40)
    
    generate_tree(path_obj)
    
    print("="*40)
    print("\n✅ Hoàn thành!")
    input("Nhấn Enter để thoát...")

if __name__ == "__main__":
    main()