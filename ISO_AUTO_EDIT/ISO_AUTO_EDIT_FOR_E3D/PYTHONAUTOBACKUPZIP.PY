import os
import zipfile
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, messagebox

def select_folder():
    root = tk.Tk()
    root.withdraw()
    folder = filedialog.askdirectory(title="백업할 폴더를 선택하세요")
    return folder

def find_py_files(folder):
    py_files = []
    for dirpath, dirnames, filenames in os.walk(folder):
        for filename in filenames:
            if filename.lower().endswith('.py'):
                full_path = os.path.join(dirpath, filename)
                # zip에 저장될 상대경로 (선택폴더 기준)
                arcname = os.path.relpath(full_path, folder)
                py_files.append((full_path, arcname))
    return py_files

def backup_py_files_to_zip(folder, py_files):
    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = os.path.join(os.path.dirname(folder), "PYTHONBACKUP")
    os.makedirs(backup_dir, exist_ok=True)
    zip_filename = f"PYTHONBACKUP_{now}.zip"
    zip_path = os.path.join(backup_dir, zip_filename)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for full_path, arcname in py_files:
            zipf.write(full_path, arcname)
    return zip_path

def main():
    folder = select_folder()
    if not folder:
        print("❌ 폴더가 선택되지 않았습니다.")
        return

    py_files = find_py_files(folder)
    if not py_files:
        messagebox.showinfo("백업", "해당 폴더에 .py 파일이 없습니다.")
        return

    zip_path = backup_py_files_to_zip(folder, py_files)
    messagebox.showinfo("백업 완료", f"{len(py_files)}개 .py 파일이\n{zip_path}\n에 백업되었습니다.")
    print(f"✅ {len(py_files)}개 .py 파일을 압축 완료:\n{zip_path}")

if __name__ == "__main__":
    main()
