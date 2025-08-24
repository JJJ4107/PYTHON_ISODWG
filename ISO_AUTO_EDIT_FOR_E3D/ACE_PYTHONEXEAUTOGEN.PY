import os
import sys
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path

def check_pyinstaller():
    """PyInstaller 설치 확인 및 자세한 정보 제공"""
    try:
        # PyInstaller 버전 확인
        result = subprocess.run([sys.executable, "-m", "PyInstaller", "--version"], 
                              check=True, capture_output=True, text=True)
        print(f"PyInstaller가 설치되어 있습니다: {result.stdout.strip()}")
        return True
    except subprocess.CalledProcessError:
        print("PyInstaller 실행 오류")
    except FileNotFoundError:
        print("Python 실행 파일을 찾을 수 없습니다")
    except:
        print("PyInstaller를 찾을 수 없습니다")
    
    # GUI 메시지 박스로 설치 확인
    result = messagebox.askyesno(
        "PyInstaller 설치", 
        "PyInstaller가 설치되어 있지 않습니다.\n\n"
        "설치하시겠습니까?\n\n"
        "※ 설치 후에도 문제가 발생하면:\n"
        "1. 명령 프롬프트를 관리자 권한으로 실행\n"
        "2. pip install --upgrade pyinstaller 실행"
    )
    
    if result:
        try:
            # 설치 진행 창
            install_window = tk.Tk()
            install_window.title("PyInstaller 설치 중...")
            install_window.geometry("400x200")
            
            frame = tk.Frame(install_window, padx=20, pady=20)
            frame.pack(fill=tk.BOTH, expand=True)
            
            label = tk.Label(frame, text="PyInstaller를 설치하는 중입니다...\n잠시만 기다려주세요.", 
                           font=("Arial", 11))
            label.pack(pady=20)
            
            progress_text = tk.Text(frame, height=5, width=45)
            progress_text.pack()
            
            install_window.update()
            
            # pip 업그레이드
            progress_text.insert(tk.END, "pip 업그레이드 중...\n")
            install_window.update()
            subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"], 
                         check=True)
            
            # PyInstaller 설치
            progress_text.insert(tk.END, "PyInstaller 설치 중...\n")
            install_window.update()
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--upgrade", "pyinstaller"],
                capture_output=True, text=True
            )
            
            if result.returncode == 0:
                progress_text.insert(tk.END, "✓ 설치 완료!\n")
                install_window.update()
                
                # 설치 확인
                verify = subprocess.run([sys.executable, "-m", "PyInstaller", "--version"],
                                      capture_output=True, text=True)
                if verify.returncode == 0:
                    progress_text.insert(tk.END, f"설치된 버전: {verify.stdout.strip()}")
                    install_window.update()
                    
                    # 2초 후 자동 닫기
                    install_window.after(2000, install_window.destroy)
                    install_window.mainloop()
                    return True
            else:
                progress_text.insert(tk.END, f"✗ 설치 실패:\n{result.stderr}")
                install_window.update()
                
                # 닫기 버튼 추가
                close_btn = tk.Button(frame, text="닫기", command=install_window.destroy)
                close_btn.pack(pady=10)
                
                install_window.mainloop()
                return False
                
        except Exception as e:
            messagebox.showerror("설치 실패", 
                               f"PyInstaller 설치에 실패했습니다.\n\n"
                               f"오류: {str(e)}\n\n"
                               f"명령 프롬프트에서 다음 명령을 직접 실행해보세요:\n"
                               f"pip install pyinstaller")
            return False
    return False

def find_python_files(directory):
    """디렉토리에서 모든 Python 파일 찾기"""
    py_files = []
    # 디버그 정보
    print(f"검색 디렉토리: {directory}")
    
    for root, dirs, files in os.walk(directory):
        # 현재 디렉토리의 파일 출력 (디버그)
        if files:
            print(f"폴더 {root}의 파일들: {files[:5]}...")  # 처음 5개만 표시
        
        for file in files:
            # 대소문자 구분 없이 확장자 확인
            if file.lower().endswith('.py'):
                full_path = os.path.join(root, file)
                py_files.append(full_path)
                print(f"Python 파일 발견: {file}")
    
    print(f"총 {len(py_files)}개의 Python 파일을 찾았습니다.")
    return py_files

def convert_to_exe(py_file, onefile=True, noconsole=False, icon=None, progress_callback=None):
    """Python 파일을 EXE로 변환"""
    cmd = [sys.executable, "-m", "PyInstaller"]
    
    # 클린 빌드를 위해 --clean 추가
    cmd.append("--clean")
    
    if onefile:
        cmd.append("--onefile")
    if noconsole:
        cmd.append("--noconsole")
    if icon and os.path.exists(icon):
        cmd.extend(["--icon", icon])
        
    # 출력 디렉토리 설정 (원본 파일과 같은 위치에 dist 폴더 생성)
    output_dir = os.path.dirname(py_file)
    dist_dir = os.path.join(output_dir, "dist")
    build_dir = os.path.join(output_dir, "build")
    
    cmd.extend(["--distpath", dist_dir])
    cmd.extend(["--workpath", build_dir])
    cmd.extend(["--specpath", build_dir])
    
    # 추가 옵션들
    cmd.extend(["--noconfirm"])  # 덮어쓰기 확인 없이 진행
    
    cmd.append(py_file)
    
    if progress_callback:
        progress_callback(f"변환 중: {os.path.basename(py_file)}")
        progress_callback(f"명령어: {' '.join(cmd)}")
    
    try:
        # 실시간 출력을 위해 수정
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            universal_newlines=True,
            bufsize=1
        )
        
        output = []
        for line in process.stdout:
            output.append(line.strip())
            if progress_callback and line.strip():
                progress_callback(f"  > {line.strip()}")
        
        process.wait()
        
        if process.returncode == 0:
            # EXE 파일이 실제로 생성되었는지 확인
            exe_name = os.path.splitext(os.path.basename(py_file))[0] + ".exe"
            exe_path = os.path.join(dist_dir, exe_name)
            
            if os.path.exists(exe_path):
                # dist 폴더에서 원본 위치로 복사
                final_exe_path = os.path.join(output_dir, exe_name)
                try:
                    shutil.copy2(exe_path, final_exe_path)
                    if progress_callback:
                        progress_callback(f"  ✓ EXE 생성 완료: {final_exe_path}")
                except Exception as e:
                    if progress_callback:
                        progress_callback(f"  ! EXE는 {exe_path}에 생성됨")
                
                # 빌드 파일 정리
                cleanup_build_files(output_dir)
                return True, None
            else:
                return False, "EXE 파일이 생성되지 않았습니다."
        else:
            error_msg = "\n".join(output[-20:])  # 마지막 20줄만
            return False, error_msg
            
    except Exception as e:
        return False, f"실행 오류: {str(e)}"

def cleanup_build_files(output_dir):
    """빌드 과정에서 생성된 임시 파일들 정리"""
    build_dir = os.path.join(output_dir, "build")
    dist_dir = os.path.join(output_dir, "dist")
    
    # build 폴더 삭제
    if os.path.exists(build_dir):
        try:
            shutil.rmtree(build_dir)
            print(f"빌드 폴더 삭제됨: {build_dir}")
        except Exception as e:
            print(f"빌드 폴더 삭제 실패: {e}")
    
    # .spec 파일 삭제
    for spec_file in os.listdir(output_dir):
        if spec_file.endswith('.spec'):
            try:
                os.remove(os.path.join(output_dir, spec_file))
                print(f"spec 파일 삭제됨: {spec_file}")
            except Exception as e:
                print(f"spec 파일 삭제 실패: {e}")

def select_directory():
    """디렉토리 선택 다이얼로그"""
    root = tk.Tk()
    root.withdraw()  # 메인 윈도우 숨기기
    
    directory = filedialog.askdirectory(
        title="Python 파일이 있는 디렉토리를 선택하세요"
    )
    
    root.destroy()
    
    # 선택한 디렉토리 경로를 정규화
    if directory:
        directory = os.path.normpath(directory)
    
    return directory

def show_progress_window(py_files, onefile=True, noconsole=False, icon=None):
    """변환 진행 상황을 보여주는 윈도우"""
    progress_window = tk.Tk()
    progress_window.title("Python to EXE 변환 중...")
    progress_window.geometry("800x600")
    
    # 프레임 생성
    frame = tk.Frame(progress_window, padx=20, pady=20)
    frame.pack(fill=tk.BOTH, expand=True)
    
    # 레이블
    label = tk.Label(frame, text=f"총 {len(py_files)}개 파일 변환 중...", font=("Arial", 12))
    label.pack(pady=(0, 10))
    
    # 진행 상황 텍스트
    text_widget = tk.Text(frame, height=20, width=90, font=("Consolas", 9))
    text_widget.pack(fill=tk.BOTH, expand=True)
    
    # 스크롤바
    scrollbar = tk.Scrollbar(text_widget)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    text_widget.config(yscrollcommand=scrollbar.set)
    scrollbar.config(command=text_widget.yview)
    
    # 진행률 레이블
    progress_label = tk.Label(frame, text="0 / 0", font=("Arial", 10))
    progress_label.pack(pady=(10, 0))
    
    # 변환 시작
    success_count = 0
    failed_files = []
    
    def update_progress(message):
        text_widget.insert(tk.END, message + "\n")
        text_widget.see(tk.END)
        progress_window.update()
    
    # 환경 정보 출력
    update_progress("=== 환경 정보 ===")
    update_progress(f"Python 버전: {sys.version.split()[0]}")
    update_progress(f"PyInstaller 버전 확인 중...")
    
    try:
        result = subprocess.run([sys.executable, "-m", "PyInstaller", "--version"], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            update_progress(f"PyInstaller 버전: {result.stdout.strip()}")
        else:
            update_progress("PyInstaller 버전을 확인할 수 없습니다.")
    except:
        update_progress("PyInstaller 버전 확인 실패")
    
    update_progress(f"작업 디렉토리: {os.path.dirname(py_files[0]) if py_files else 'Unknown'}")
    update_progress("=" * 50 + "\n")
    
    for i, py_file in enumerate(py_files, 1):
        file_name = os.path.basename(py_file)
        update_progress(f"\n[{i}/{len(py_files)}] {file_name}")
        update_progress("-" * 40)
        
        success, error = convert_to_exe(py_file, onefile, noconsole, icon, update_progress)
        
        if success:
            update_progress(f"✓ 성공: {file_name}")
            success_count += 1
        else:
            update_progress(f"✗ 실패: {file_name}")
            if error:
                update_progress(f"오류 내용:\n{error}")
            failed_files.append(file_name)
        
        progress_label.config(text=f"{i} / {len(py_files)}")
        progress_window.update()
    
    # 결과 출력
    update_progress("\n" + "="*50)
    update_progress(f"변환 완료!")
    update_progress(f"성공: {success_count}개")
    update_progress(f"실패: {len(failed_files)}개")
    
    if failed_files:
        update_progress("\n실패한 파일:")
        for file in failed_files:
            update_progress(f"  - {file}")
        
        update_progress("\n=== 문제 해결 방법 ===")
        update_progress("1. 바이러스 백신이 PyInstaller를 차단하고 있을 수 있습니다.")
        update_progress("   → Windows Defender나 백신 프로그램에서 제외 폴더로 설정해보세요.")
        update_progress("\n2. Python 스크립트에 import 오류가 있을 수 있습니다.")
        update_progress("   → 스크립트를 직접 실행해서 오류가 없는지 확인하세요.")
        update_progress("\n3. 필요한 패키지가 설치되지 않았을 수 있습니다.")
        update_progress("   → pip install [패키지명]으로 필요한 패키지를 설치하세요.")
        update_progress("\n4. 경로에 한글이나 특수문자가 있으면 문제가 될 수 있습니다.")
        update_progress("   → 영문 경로로 이동 후 다시 시도해보세요.")
    
    # 버튼 프레임
    button_frame = tk.Frame(frame)
    button_frame.pack(pady=(10, 0))
    
    # dist 폴더 열기 버튼
    def open_dist_folder():
        if py_files:
            dist_dir = os.path.join(os.path.dirname(py_files[0]), "dist")
            if os.path.exists(dist_dir):
                if sys.platform.startswith('win'):
                    os.startfile(dist_dir)
                else:
                    subprocess.Popen(['open' if sys.platform == 'darwin' else 'xdg-open', dist_dir])
            else:
                # 원본 폴더 열기
                folder = os.path.dirname(py_files[0])
                if sys.platform.startswith('win'):
                    os.startfile(folder)
                else:
                    subprocess.Popen(['open' if sys.platform == 'darwin' else 'xdg-open', folder])
    
    if success_count > 0:
        open_button = tk.Button(button_frame, text="출력 폴더 열기", 
                              command=open_dist_folder, padx=15, pady=5)
        open_button.pack(side=tk.LEFT, padx=5)
    
    # 닫기 버튼
    close_button = tk.Button(button_frame, text="닫기", command=progress_window.destroy, 
                           padx=20, pady=5, font=("Arial", 10))
    close_button.pack(side=tk.LEFT, padx=5)
    
    progress_window.mainloop()

def show_options_dialog(py_files, directory):
    """변환 옵션을 선택하는 다이얼로그"""
    # 경로에 한글이나 특수문자가 있는지 확인
    if any(ord(char) > 127 for char in directory):
        warning_msg = (
            "주의: 선택한 경로에 한글이나 특수문자가 포함되어 있습니다.\n\n"
            f"경로: {directory}\n\n"
            "PyInstaller는 한글 경로에서 문제가 발생할 수 있습니다.\n"
            "가능하면 영문 경로를 사용하는 것을 권장합니다.\n\n"
            "계속 진행하시겠습니까?"
        )
        if not messagebox.askyesno("경로 확인", warning_msg):
            return
    
    options_window = tk.Tk()
    options_window.title("변환 옵션 선택")
    options_window.geometry("500x450")
    
    # 변수들
    onefile_var = tk.BooleanVar(value=True)
    noconsole_var = tk.BooleanVar(value=False)
    icon_path_var = tk.StringVar()
    
    # 프레임
    frame = tk.Frame(options_window, padx=20, pady=20)
    frame.pack(fill=tk.BOTH, expand=True)
    
    # 정보 레이블
    info_label = tk.Label(frame, text=f"선택된 디렉토리: {directory}\n찾은 Python 파일: {len(py_files)}개", 
                         font=("Arial", 10), justify=tk.LEFT)
    info_label.pack(anchor=tk.W, pady=(0, 20))
    
    # 파일 목록
    list_frame = tk.Frame(frame)
    list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 20))
    
    list_label = tk.Label(list_frame, text="변환할 파일 목록:", font=("Arial", 10, "bold"))
    list_label.pack(anchor=tk.W)
    
    # 리스트박스와 스크롤바
    listbox_frame = tk.Frame(list_frame)
    listbox_frame.pack(fill=tk.BOTH, expand=True)
    
    scrollbar = tk.Scrollbar(listbox_frame)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    
    listbox = tk.Listbox(listbox_frame, yscrollcommand=scrollbar.set, height=8)
    for py_file in py_files:
        listbox.insert(tk.END, os.path.relpath(py_file, directory))
    listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar.config(command=listbox.yview)
    
    # 옵션들
    options_label = tk.Label(frame, text="변환 옵션:", font=("Arial", 10, "bold"))
    options_label.pack(anchor=tk.W, pady=(10, 5))
    
    onefile_check = tk.Checkbutton(frame, text="단일 EXE 파일로 생성 (--onefile)", 
                                  variable=onefile_var)
    onefile_check.pack(anchor=tk.W, pady=2)
    
    noconsole_check = tk.Checkbutton(frame, text="콘솔 창 숨기기 (--noconsole) [GUI 앱용]", 
                                    variable=noconsole_var)
    noconsole_check.pack(anchor=tk.W, pady=2)
    
    # 아이콘 선택
    icon_frame = tk.Frame(frame)
    icon_frame.pack(anchor=tk.W, pady=(10, 0))
    
    icon_label = tk.Label(icon_frame, text="아이콘 파일 (선택사항):")
    icon_label.pack(side=tk.LEFT)
    
    icon_entry = tk.Entry(icon_frame, textvariable=icon_path_var, width=30)
    icon_entry.pack(side=tk.LEFT, padx=5)
    
    def select_icon():
        icon_file = filedialog.askopenfilename(
            title="아이콘 파일 선택",
            filetypes=[("아이콘 파일", "*.ico"), ("모든 파일", "*.*")]
        )
        if icon_file:
            icon_path_var.set(icon_file)
    
    icon_button = tk.Button(icon_frame, text="찾아보기", command=select_icon)
    icon_button.pack(side=tk.LEFT)
    
    # 주의사항
    note_label = tk.Label(frame, 
                         text="※ 변환된 EXE 파일은 각 Python 파일과 같은 위치에 생성됩니다.",
                         font=("Arial", 9), fg="blue")
    note_label.pack(anchor=tk.W, pady=(10, 0))
    
    # 버튼들
    button_frame = tk.Frame(frame)
    button_frame.pack(side=tk.BOTTOM, pady=(20, 0))
    
    def start_conversion():
        options_window.destroy()
        icon_path = icon_path_var.get() if icon_path_var.get() else None
        show_progress_window(py_files, onefile_var.get(), noconsole_var.get(), icon_path)
    
    start_button = tk.Button(button_frame, text="변환 시작", command=start_conversion, 
                           padx=20, pady=5, bg="#4CAF50", fg="white", font=("Arial", 10, "bold"))
    start_button.pack(side=tk.LEFT, padx=5)
    
    cancel_button = tk.Button(button_frame, text="취소", command=options_window.destroy, 
                            padx=20, pady=5, font=("Arial", 10))
    cancel_button.pack(side=tk.LEFT, padx=5)
    
    options_window.mainloop()

def show_debug_info(directory, py_files):
    """디버그 정보를 보여주는 창"""
    debug_window = tk.Tk()
    debug_window.title("디버그 정보")
    debug_window.geometry("600x400")
    
    frame = tk.Frame(debug_window, padx=10, pady=10)
    frame.pack(fill=tk.BOTH, expand=True)
    
    # 텍스트 위젯
    text_widget = tk.Text(frame, wrap=tk.WORD)
    text_widget.pack(fill=tk.BOTH, expand=True)
    
    # 스크롤바
    scrollbar = tk.Scrollbar(text_widget)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    text_widget.config(yscrollcommand=scrollbar.set)
    scrollbar.config(command=text_widget.yview)
    
    # 디버그 정보 추가
    text_widget.insert(tk.END, f"선택한 디렉토리: {directory}\n")
    text_widget.insert(tk.END, "-" * 60 + "\n\n")
    
    # 디렉토리 내용
    try:
        items = os.listdir(directory)
        text_widget.insert(tk.END, f"디렉토리 내 총 항목 수: {len(items)}개\n\n")
        
        # 모든 파일 표시
        text_widget.insert(tk.END, "모든 파일 목록:\n")
        for item in sorted(items):
            if os.path.isfile(os.path.join(directory, item)):
                text_widget.insert(tk.END, f"  - {item}\n")
        
        text_widget.insert(tk.END, "\n" + "-" * 60 + "\n\n")
        
        # Python 파일만 표시
        py_in_dir = [f for f in items if f.lower().endswith('.py')]
        text_widget.insert(tk.END, f"Python 파일 (.py/.PY): {len(py_in_dir)}개\n")
        for f in py_in_dir:
            text_widget.insert(tk.END, f"  - {f}\n")
            
    except Exception as e:
        text_widget.insert(tk.END, f"디렉토리 읽기 오류: {e}\n")
    
    # 닫기 버튼
    close_button = tk.Button(frame, text="닫기", command=debug_window.destroy)
    close_button.pack(pady=(10, 0))
    
    debug_window.mainloop()

def main():
    # PyInstaller 확인
    if not check_pyinstaller():
        return
    
    # 디렉토리 선택
    directory = select_directory()
    if not directory:
        messagebox.showinfo("취소", "디렉토리 선택이 취소되었습니다.")
        return
    
    # 선택한 디렉토리 정보 출력
    print(f"\n선택한 디렉토리: {directory}")
    
    # 디렉토리 내용 확인 (디버그)
    try:
        items = os.listdir(directory)
        print(f"디렉토리 내 항목 수: {len(items)}개")
        print(f"처음 10개 항목: {items[:10]}")
        
        # .py 또는 .PY 파일 직접 확인
        py_files_direct = [f for f in items if f.lower().endswith('.py')]
        print(f"직접 확인한 Python 파일: {py_files_direct}")
    except Exception as e:
        print(f"디렉토리 읽기 오류: {e}")
    
    # Python 파일 찾기
    py_files = find_python_files(directory)
    
    if not py_files:
        # 더 자세한 정보를 포함한 메시지
        result = messagebox.askyesno(
            "파일 없음", 
            f"선택한 디렉토리에서 Python 파일을 찾을 수 없습니다.\n\n"
            f"디렉토리: {directory}\n\n"
            f"디버그 정보를 확인하시겠습니까?"
        )
        
        if result:
            show_debug_info(directory, py_files)
        
        # 콘솔 창 유지
        input("\n엔터 키를 눌러 종료하세요...")
        return
    
    # 옵션 선택 및 변환 시작
    show_options_dialog(py_files, directory)

if __name__ == "__main__":
    # 콘솔 창 유지 (디버그용)
    if sys.platform.startswith('win'):
        # Windows에서 콘솔 창이 바로 닫히지 않도록 설정
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-10), 7)
    
    print("Python to EXE 변환기 시작...")
    print(f"Python 버전: {sys.version}")
    print(f"현재 작업 디렉토리: {os.getcwd()}")
    print("-" * 50)
    
    main()