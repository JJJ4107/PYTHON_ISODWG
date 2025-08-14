import os
import subprocess
import time
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import threading
import glob
import json
from datetime import datetime
import win32com.client
import win32gui
import win32con
import psutil

class AdvancedDXFProcessor:
    def __init__(self, root):
        self.root = root
        self.root.title("DXF 파일 처리 자동화 도구 (고급)")
        self.root.geometry("800x600")
        
        # 변수들
        self.base_dir = tk.StringVar()
        self.processing = False
        self.current_process = None
        self.config = self.load_config()
        
        # UI 설정
        self.setup_ui()
        
    def setup_ui(self):
        # 노트북 위젯 (탭)
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 메인 탭
        main_tab = ttk.Frame(notebook)
        notebook.add(main_tab, text="메인")
        self.setup_main_tab(main_tab)
        
        # 설정 탭
        config_tab = ttk.Frame(notebook)
        notebook.add(config_tab, text="설정")
        self.setup_config_tab(config_tab)
        
        # 로그 탭
        log_tab = ttk.Frame(notebook)
        notebook.add(log_tab, text="로그")
        self.setup_log_tab(log_tab)
        
    def setup_main_tab(self, parent):
        # 디렉토리 선택
        dir_frame = tk.Frame(parent, padx=10, pady=10)
        dir_frame.pack(fill=tk.X)
        
        tk.Label(dir_frame, text="작업 디렉토리:").pack(side=tk.LEFT)
        tk.Entry(dir_frame, textvariable=self.base_dir, width=60).pack(side=tk.LEFT, padx=5)
        tk.Button(dir_frame, text="찾아보기", command=self.select_directory).pack(side=tk.LEFT)
        
        # 구조 확인
        info_frame = tk.LabelFrame(parent, text="디렉토리 구조", padx=10, pady=10)
        info_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.info_text = tk.Text(info_frame, height=8, width=80)
        self.info_text.pack()
        
        # 처리 옵션
        option_frame = tk.LabelFrame(parent, text="처리 옵션", padx=10, pady=10)
        option_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.backup_var = tk.BooleanVar(value=True)
        tk.Checkbutton(option_frame, text="원본 파일 백업", variable=self.backup_var).pack(anchor=tk.W)
        
        self.verify_var = tk.BooleanVar(value=True)
        tk.Checkbutton(option_frame, text="처리 결과 검증", variable=self.verify_var).pack(anchor=tk.W)
        
        # 진행 상황
        progress_frame = tk.LabelFrame(parent, text="진행 상황", padx=10, pady=10)
        progress_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.status_label = tk.Label(progress_frame, text="대기 중...")
        self.status_label.pack()
        
        self.progress = ttk.Progressbar(progress_frame, mode='determinate')
        self.progress.pack(fill=tk.X, pady=5)
        
        self.detail_progress = ttk.Progressbar(progress_frame, mode='determinate')
        self.detail_progress.pack(fill=tk.X, pady=5)
        
        # 버튼
        button_frame = tk.Frame(parent, padx=10, pady=10)
        button_frame.pack(fill=tk.X)
        
        self.start_button = tk.Button(button_frame, text="처리 시작", 
                                     command=self.start_processing, 
                                     bg="green", fg="white", font=("Arial", 10, "bold"))
        self.start_button.pack(side=tk.LEFT, padx=5)
        
        self.pause_button = tk.Button(button_frame, text="일시정지", 
                                     command=self.pause_processing, state=tk.DISABLED)
        self.pause_button.pack(side=tk.LEFT, padx=5)
        
        self.stop_button = tk.Button(button_frame, text="중지", 
                                    command=self.stop_processing, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=5)
        
    def setup_config_tab(self, parent):
        # 처리 설정
        process_frame = tk.LabelFrame(parent, text="처리 설정", padx=10, pady=10)
        process_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # 대기 시간 설정
        tk.Label(process_frame, text="EXE 로딩 대기 시간 (초):").grid(row=0, column=0, sticky=tk.W)
        self.load_wait = tk.IntVar(value=self.config.get('load_wait', 3))
        tk.Spinbox(process_frame, from_=1, to=30, textvariable=self.load_wait, width=10).grid(row=0, column=1)
        
        tk.Label(process_frame, text="파일 처리 대기 시간 (초):").grid(row=1, column=0, sticky=tk.W)
        self.process_wait = tk.IntVar(value=self.config.get('process_wait', 5))
        tk.Spinbox(process_frame, from_=1, to=60, textvariable=self.process_wait, width=10).grid(row=1, column=1)
        
        tk.Label(process_frame, text="저장 대기 시간 (초):").grid(row=2, column=0, sticky=tk.W)
        self.save_wait = tk.IntVar(value=self.config.get('save_wait', 2))
        tk.Spinbox(process_frame, from_=1, to=30, textvariable=self.save_wait, width=10).grid(row=2, column=1)
        
        # 자동화 방법 선택
        method_frame = tk.LabelFrame(parent, text="자동화 방법", padx=10, pady=10)
        method_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.method_var = tk.StringVar(value=self.config.get('method', 'sendkeys'))
        tk.Radiobutton(method_frame, text="SendKeys 방식 (안정적)", 
                      variable=self.method_var, value="sendkeys").pack(anchor=tk.W)
        tk.Radiobutton(method_frame, text="PyAutoGUI 방식 (범용적)", 
                      variable=self.method_var, value="pyautogui").pack(anchor=tk.W)
        tk.Radiobutton(method_frame, text="커맨드라인 방식 (EXE가 지원하는 경우)", 
                      variable=self.method_var, value="cmdline").pack(anchor=tk.W)
        
        # 저장 버튼
        tk.Button(parent, text="설정 저장", command=self.save_config).pack(pady=10)
        
    def setup_log_tab(self, parent):
        # 로그 텍스트
        log_frame = tk.Frame(parent, padx=10, pady=10)
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        scrollbar = tk.Scrollbar(log_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.log_text = tk.Text(log_frame, yscrollcommand=scrollbar.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.log_text.yview)
        
        # 로그 버튼
        button_frame = tk.Frame(parent)
        button_frame.pack(fill=tk.X)
        
        tk.Button(button_frame, text="로그 지우기", command=self.clear_log).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="로그 저장", command=self.save_log).pack(side=tk.LEFT, padx=5)
        
    def load_config(self):
        """설정 파일 로드"""
        config_file = "dxf_processor_config.json"
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {}
        
    def save_config(self):
        """설정 저장"""
        config = {
            'load_wait': self.load_wait.get(),
            'process_wait': self.process_wait.get(),
            'save_wait': self.save_wait.get(),
            'method': self.method_var.get()
        }
        
        with open("dxf_processor_config.json", 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
            
        messagebox.showinfo("저장", "설정이 저장되었습니다.")
        
    def log(self, message, level="INFO"):
        """로그 메시지 추가"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] [{level}] {message}\n"
        
        self.log_text.insert(tk.END, log_entry)
        self.log_text.see(tk.END)
        self.root.update()
        
        # 파일에도 로그 저장
        with open("dxf_processor.log", 'a', encoding='utf-8') as f:
            f.write(log_entry)
            
    def clear_log(self):
        """로그 지우기"""
        self.log_text.delete(1.0, tk.END)
        
    def save_log(self):
        """로그 파일로 저장"""
        filename = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("텍스트 파일", "*.txt"), ("모든 파일", "*.*")]
        )
        if filename:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(self.log_text.get(1.0, tk.END))
                
    def select_directory(self):
        """디렉토리 선택"""
        directory = filedialog.askdirectory()
        if directory:
            self.base_dir.set(directory)
            self.check_directory_structure()
            
    def check_directory_structure(self):
        """디렉토리 구조 확인"""
        base = self.base_dir.get()
        if not base:
            return
            
        self.info_text.delete(1.0, tk.END)
        
        # 필요한 디렉토리들
        dirs_to_check = {
            "PYEXE": "EXE 파일",
            "DXFFILE": "원본 DXF 파일"
        }
        
        for dir_name, description in dirs_to_check.items():
            dir_path = os.path.join(base, dir_name)
            if os.path.exists(dir_path):
                files = os.listdir(dir_path)
                self.info_text.insert(tk.END, f"✓ {dir_name}: {len(files)}개 파일\n")
                
                if dir_name == "PYEXE":
                    # EXE 파일 체크
                    for i in range(18):
                        exe_prefix = f"{i:02d}_"
                        found = any(f.startswith(exe_prefix) and f.endswith('.exe') for f in files)
                        if not found:
                            self.info_text.insert(tk.END, f"  ⚠ {exe_prefix}*.exe 없음\n")
            else:
                self.info_text.insert(tk.END, f"✗ {dir_name} 디렉토리 없음\n")
                
    def backup_files(self):
        """원본 파일 백업"""
        if not self.backup_var.get():
            return
            
        backup_dir = os.path.join(self.base_dir.get(), "BACKUP", 
                                 datetime.now().strftime("%Y%m%d_%H%M%S"))
        
        dxffile_dir = os.path.join(self.base_dir.get(), "DXFFILE")
        if os.path.exists(dxffile_dir):
            shutil.copytree(dxffile_dir, os.path.join(backup_dir, "DXFFILE"))
            self.log(f"원본 파일 백업 완료: {backup_dir}")
            
    def find_window_by_title(self, title_part):
        """윈도우 제목으로 창 찾기"""
        def enum_windows_callback(hwnd, windows):
            if win32gui.IsWindowVisible(hwnd):
                window_title = win32gui.GetWindowText(hwnd)
                if title_part.lower() in window_title.lower():
                    windows.append((hwnd, window_title))
            return True
            
        windows = []
        win32gui.EnumWindows(enum_windows_callback, windows)
        return windows[0][0] if windows else None
        
    def send_keys_method(self, exe_path, dxf_file, output_file):
        """SendKeys 방식으로 파일 처리"""
        shell = win32com.client.Dispatch("WScript.Shell")
        
        # EXE 실행
        process = subprocess.Popen([exe_path])
        time.sleep(self.load_wait.get())
        
        # 파일 선택 다이얼로그 처리
        shell.SendKeys(dxf_file)
        time.sleep(0.5)
        shell.SendKeys("{ENTER}")
        
        # 처리 대기
        time.sleep(self.process_wait.get())
        
        # 저장 다이얼로그 처리
        shell.SendKeys(output_file)
        time.sleep(0.5)
        shell.SendKeys("{ENTER}")
        
        # 덮어쓰기 확인
        time.sleep(0.5)
        shell.SendKeys("y")
        
        time.sleep(self.save_wait.get())
        
        # 프로세스 종료
        try:
            process.terminate()
        except:
            pass
            
    def cmdline_method(self, exe_path, dxf_file, output_file):
        """커맨드라인 방식으로 파일 처리"""
        # EXE가 커맨드라인 인수를 지원하는 경우
        cmd = [exe_path, "-i", dxf_file, "-o", output_file]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, 
                                  timeout=self.process_wait.get() + 10)
            if result.returncode != 0:
                raise Exception(f"Return code: {result.returncode}")
        except subprocess.TimeoutExpired:
            self.log("처리 시간 초과", "WARNING")
        except Exception as e:
            raise e
            
    def process_single_file(self, exe_path, dxf_file, output_file):
        """단일 파일 처리"""
        method = self.method_var.get()
        
        try:
            if method == "sendkeys":
                self.send_keys_method(exe_path, dxf_file, output_file)
            elif method == "pyautogui":
                # PyAutoGUI 방식은 기본 버전과 동일
                import pyautogui
                subprocess.Popen([exe_path])
                time.sleep(self.load_wait.get())
                time.sleep(1)
                pyautogui.write(dxf_file)
                time.sleep(0.5)
                pyautogui.press('enter')
                time.sleep(self.process_wait.get())
                pyautogui.write(output_file)
                time.sleep(0.5)
                pyautogui.press('enter')
                time.sleep(0.5)
                pyautogui.press('y')
                time.sleep(self.save_wait.get())
            elif method == "cmdline":
                self.cmdline_method(exe_path, dxf_file, output_file)
                
            # 결과 검증
            if self.verify_var.get() and not os.path.exists(output_file):
                raise Exception("출력 파일이 생성되지 않았습니다.")
                
        except Exception as e:
            raise e
            
    def process_files_batch(self, exe_path, input_files, output_dir, phase_name):
        """파일 일괄 처리"""
        total = len(input_files)
        self.detail_progress['maximum'] = total
        
        for i, input_file in enumerate(input_files):
            if not self.processing:
                break
                
            filename = os.path.basename(input_file)
            output_file = os.path.join(output_dir, filename)
            
            self.status_label.config(text=f"{phase_name}: {filename} ({i+1}/{total})")
            self.detail_progress['value'] = i + 1
            
            try:
                self.process_single_file(exe_path, input_file, output_file)
                self.log(f"✓ {filename} 처리 완료")
            except Exception as e:
                self.log(f"✗ {filename} 처리 실패: {str(e)}", "ERROR")
                
    def start_processing(self):
        """처리 시작"""
        if not self.validate_directories():
            return
            
        self.processing = True
        self.start_button.config(state=tk.DISABLED)
        self.pause_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.NORMAL)
        
        thread = threading.Thread(target=self.process_all)
        thread.daemon = True
        thread.start()
        
    def pause_processing(self):
        """일시정지"""
        # 구현 예정
        pass
        
    def stop_processing(self):
        """중지"""
        self.processing = False
        self.log("처리를 중지합니다...", "WARNING")
        
    def validate_directories(self):
        """디렉토리 검증"""
        base = self.base_dir.get()
        if not base:
            messagebox.showerror("오류", "디렉토리를 선택해주세요.")
            return False
            
        required_dirs = ["PYEXE", "DXFFILE"]
        for dir_name in required_dirs:
            if not os.path.exists(os.path.join(base, dir_name)):
                messagebox.showerror("오류", f"{dir_name} 디렉토리가 없습니다.")
                return False
                
        return True
        
    def get_exe_path(self, number):
        """EXE 파일 경로 찾기"""
        pyexe_dir = os.path.join(self.base_dir.get(), "PYEXE")
        prefix = f"{number:02d}_"
        
        for file in os.listdir(pyexe_dir):
            if file.startswith(prefix) and file.endswith('.exe'):
                return os.path.join(pyexe_dir, file)
        return None
        
    def process_all(self):
        """전체 처리 프로세스"""
        try:
            self.log("="*50)
            self.log("처리 시작")
            
            # 백업
            self.backup_files()
            
            # 디렉토리 생성
            base = self.base_dir.get()
            for dir_name in ["OUTPUT1", "OUTPUT2", "OUTPUT_FINAL"]:
                dir_path = os.path.join(base, dir_name)
                os.makedirs(dir_path, exist_ok=True)
                
            self.progress['maximum'] = 3  # 3 phases
            
            # Phase 1: 00_ ~ 12_
            self.log("\n=== Phase 1: 00_ ~ 12_ 실행 ===")
            self.progress['value'] = 0
            
            dxf_files = glob.glob(os.path.join(base, "DXFFILE", "*.dxf"))
            
            for i in range(13):
                if not self.processing:
                    break
                    
                exe_path = self.get_exe_path(i)
                if exe_path:
                    self.log(f"\n{i:02d}_ 실행 중...")
                    self.process_files_batch(exe_path, dxf_files, 
                                           os.path.join(base, "OUTPUT1"), 
                                           f"Phase 1 ({i:02d}_)")
                else:
                    self.log(f"{i:02d}_ EXE 파일 없음", "WARNING")
                    
            self.progress['value'] = 1
            
            # Phase 2: 13_
            if self.processing:
                self.log("\n=== Phase 2: 13_ 실행 ===")
                
                exe_path = self.get_exe_path(13)
                if exe_path:
                    output1_files = glob.glob(os.path.join(base, "OUTPUT1", "*.dxf"))
                    self.process_files_batch(exe_path, output1_files,
                                           os.path.join(base, "OUTPUT2"),
                                           "Phase 2 (13_)")
                                           
            self.progress['value'] = 2
            
            # Phase 3: 14_ ~ 17_
            if self.processing:
                self.log("\n=== Phase 3: 14_ ~ 17_ 실행 ===")
                
                output2_files = glob.glob(os.path.join(base, "OUTPUT2", "*.dxf"))
                
                for i in range(14, 18):
                    if not self.processing:
                        break
                        
                    exe_path = self.get_exe_path(i)
                    if exe_path:
                        self.log(f"\n{i:02d}_ 실행 중...")
                        self.process_files_batch(exe_path, output2_files,
                                               os.path.join(base, "OUTPUT_FINAL"),
                                               f"Phase 3 ({i:02d}_)")
                    else:
                        self.log(f"{i:02d}_ EXE 파일 없음", "WARNING")
                        
            self.progress['value'] = 3
            
            if self.processing:
                self.log("\n처리 완료!")
                self.status_label.config(text="처리 완료!")
                messagebox.showinfo("완료", "모든 처리가 완료되었습니다.")
            else:
                self.log("\n처리 중단됨", "WARNING")
                self.status_label.config(text="처리 중단됨")
                
        except Exception as e:
            self.log(f"\n오류 발생: {str(e)}", "ERROR")
            messagebox.showerror("오류", f"처리 중 오류가 발생했습니다:\n{str(e)}")
            
        finally:
            self.processing = False
            self.start_button.config(state=tk.NORMAL)
            self.pause_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.DISABLED)
            self.progress['value'] = 0
            self.detail_progress['value'] = 0


def main():
    root = tk.Tk()
    app = AdvancedDXFProcessor(root)
    root.mainloop()


if __name__ == "__main__":
    main()