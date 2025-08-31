import os
import tkinter as tk
from tkinter import filedialog, messagebox

def select_folder_and_save_bat_list():
    # tkinter 창 숨기기
    root = tk.Tk()
    root.withdraw()

    # 폴더 선택
    folder_path = filedialog.askdirectory(title="폴더를 선택하세요")

    if not folder_path:
        messagebox.showwarning("경고", "폴더가 선택되지 않았습니다.")
        return

    # 조건에 맞는 파일만 필터
    matching_files = [f for f in os.listdir(folder_path)
                      if f.lower().endswith("_pdms_pshes34.bat")]

    # 현재 py 파일이 있는 폴더 경로
    current_dir = os.path.dirname(os.path.abspath(__file__))
    output_file = os.path.join(current_dir, "BAT.TXT")

    # 결과 저장
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(f"선택된 폴더: {folder_path}\n")
        f.write("조건에 맞는 BAT 파일 목록:\n")
        if matching_files:
            for file in matching_files:
                f.write(file + "\n")
        else:
            f.write("조건에 맞는 파일이 없습니다.\n")

    messagebox.showinfo("완료", f"BAT.TXT 파일이 저장되었습니다:\n{output_file}")
    print(f"✔ BAT.TXT 저장 완료: {output_file}")

# 실행
if __name__ == "__main__":
    select_folder_and_save_bat_list()
