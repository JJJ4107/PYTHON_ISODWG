import os
import zipfile
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, messagebox
import traceback

def select_folder():
    root = tk.Tk()
    root.withdraw()
    folder = filedialog.askdirectory(title="백업할 폴더를 선택하세요")
    return folder

def find_py_files(folder):
    py_files = []
    print(f"검색 시작: {folder}")
    
    for dirpath, dirnames, filenames in os.walk(folder):
        for filename in filenames:
            if filename.lower().endswith('.py'):
                full_path = os.path.join(dirpath, filename)
                arcname = os.path.relpath(full_path, folder)
                py_files.append((full_path, arcname))
                print(f"  발견: {arcname}")
    
    print(f"총 {len(py_files)}개 파일 발견")
    return py_files

def backup_py_files_to_zip(folder, py_files):
    try:
        # 현재 시간
        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 백업 디렉토리 경로 생성
        parent_dir = os.path.dirname(folder)
        print(f"선택한 폴더: {folder}")
        print(f"상위 폴더: {parent_dir}")
        
        # 백업 폴더 경로
        backup_dir = os.path.join(parent_dir, "SP3DPYTHONBACKUP")
        print(f"백업 폴더 경로: {backup_dir}")
        
        # 백업 폴더 생성 시도
        try:
            os.makedirs(backup_dir, exist_ok=True)
            print(f"✅ 백업 폴더 생성/확인 완료")
        except Exception as e:
            print(f"❌ 백업 폴더 생성 실패: {e}")
            # 대체 경로 시도 - 선택한 폴더 내부에 생성
            backup_dir = os.path.join(folder, "SP3DPYTHONBACKUP")
            print(f"대체 경로 시도: {backup_dir}")
            os.makedirs(backup_dir, exist_ok=True)
        
        # ZIP 파일명과 경로
        zip_filename = f"SP3DPYTHONBACKUP_{now}.zip"
        zip_path = os.path.join(backup_dir, zip_filename)
        print(f"ZIP 파일 경로: {zip_path}")
        
        # ZIP 파일 생성
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for full_path, arcname in py_files:
                try:
                    zipf.write(full_path, arcname)
                    print(f"  압축: {arcname}")
                except Exception as e:
                    print(f"  ❌ 압축 실패 {arcname}: {e}")
        
        print(f"✅ ZIP 파일 생성 완료: {zip_path}")
        
        # 파일이 실제로 생성되었는지 확인
        if os.path.exists(zip_path):
            file_size = os.path.getsize(zip_path)
            print(f"✅ 파일 확인됨 (크기: {file_size:,} bytes)")
        else:
            print(f"❌ 파일이 생성되지 않았습니다!")
        
        return zip_path
        
    except Exception as e:
        error_msg = f"백업 중 오류 발생:\n{str(e)}\n\n{traceback.format_exc()}"
        print(error_msg)
        messagebox.showerror("백업 오류", error_msg)
        return None

def main():
    print("=== SP3D Python 백업 도구 시작 ===")
    
    # 폴더 선택
    folder = select_folder()
    if not folder:
        print("❌ 폴더가 선택되지 않았습니다.")
        return
    
    # 권한 확인
    try:
        test_file = os.path.join(os.path.dirname(folder), "test_write_permission.tmp")
        with open(test_file, 'w') as f:
            f.write("test")
        os.remove(test_file)
        print("✅ 쓰기 권한 확인됨")
    except Exception as e:
        print(f"⚠️ 쓰기 권한 문제 가능성: {e}")
    
    # Python 파일 찾기
    py_files = find_py_files(folder)
    if not py_files:
        messagebox.showinfo("백업", "해당 폴더에 .py 파일이 없습니다.")
        return
    
    # 백업 실행
    zip_path = backup_py_files_to_zip(folder, py_files)
    
    if zip_path and os.path.exists(zip_path):
        # 백업 성공
        msg = f"{len(py_files)}개 .py 파일이\n{zip_path}\n에 백업되었습니다."
        messagebox.showinfo("백업 완료", msg)
        print(f"✅ 백업 완료!")
        
        # 백업 폴더 열기 제안
        if messagebox.askyesno("폴더 열기", "백업 폴더를 열어보시겠습니까?"):
            backup_folder = os.path.dirname(zip_path)
            if os.name == 'nt':  # Windows
                os.startfile(backup_folder)
            else:  # macOS/Linux
                os.system(f'open "{backup_folder}"')
    else:
        print("❌ 백업 실패")

if __name__ == "__main__":
    # 콘솔 창이 바로 닫히지 않도록
    try:
        main()
    except Exception as e:
        print(f"프로그램 오류: {e}")
        traceback.print_exc()
    finally:
        input("\n종료하려면 Enter를 누르세요...")  # 디버그용