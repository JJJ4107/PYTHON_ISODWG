import os
import sys
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox
import glob
import time
import json
import shutil
import tempfile
import threading

# DXF 파일 처리를 위한 ezdxf 라이브러리
try:
    import ezdxf
    EZDXF_AVAILABLE = True
except ImportError:
    EZDXF_AVAILABLE = False
    print("ezdxf 라이브러리가 필요합니다. 설치하세요: pip install ezdxf")

class DXFAutoProcessor:
    def __init__(self):
        # 실행할 Python 스크립트 순서
        self.scripts = [
            "PLTONEWLINE_1.PY",
            "DIMEDIT_2.PY",
            "WELDEDIT_3.PY",
            "WELDTABLE_4.PY",
            "SUPPTAG_5.PY",
            "SPOOLNEDIT_6.PY",
            "ELBOEDIT_7.PY",
            "FALLEDIT_8.PY",
            "ITEMNOEDIT_9.PY",
            "OLETDIMDEL_10.PY",
            "POSDELETE_11.PY",
            "ISODWGNOSET_12.PY",
            "ISODWGNOFIX_13.PY"
        ]
        
        self.current_dir = os.path.dirname(os.path.abspath(__file__))
        self.config_file = os.path.join(self.current_dir, "dxf_automation_config.json")
        self.last_dxf_dir = self.load_last_directory()
        self.temp_dir = None
        self.temp_files = set()  # 임시 파일 추적
        
        # 자동화 코드 템플릿
        self.wrapper_code = '''
import os
import sys
import types
import io

# ===== 자동화 래퍼 시작 =====
# UTF-8 인코딩 설정
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# 자동 모드 확인
if os.environ.get('AUTO_MODE') == 'TRUE':
    selected_file = os.environ.get('SELECTED_DXF_FILE')
    
    if selected_file and os.path.exists(selected_file):
        print(f"[자동화] 파일 처리: {os.path.basename(selected_file)}")
        
        # 전역 변수로 설정
        import builtins
        setattr(builtins, 'SELECTED_FILE', selected_file)
        setattr(builtins, 'AUTO_MODE', True)
        
        # print 함수 오버라이드
        original_print = print
        
        def safe_print(*args, **kwargs):
            try:
                original_print(*args, **kwargs)
            except UnicodeEncodeError:
                safe_args = []
                for arg in args:
                    if isinstance(arg, str):
                        safe_arg = arg.encode('cp949', errors='replace').decode('cp949')
                        safe_args.append(safe_arg)
                    else:
                        safe_args.append(arg)
                original_print(*safe_args, **kwargs)
        
        builtins.print = safe_print
        
        # Mock pyautogui 모듈
        mock_pyautogui = types.ModuleType('pyautogui')
        mock_pyautogui.click = lambda *args, **kwargs: None
        mock_pyautogui.moveTo = lambda *args, **kwargs: None
        mock_pyautogui.press = lambda *args, **kwargs: None
        mock_pyautogui.keyDown = lambda *args, **kwargs: None
        mock_pyautogui.keyUp = lambda *args, **kwargs: None
        mock_pyautogui.hotkey = lambda *args, **kwargs: None
        mock_pyautogui.typewrite = lambda *args, **kwargs: None
        mock_pyautogui.screenshot = lambda *args, **kwargs: None
        mock_pyautogui.locateOnScreen = lambda *args, **kwargs: None
        mock_pyautogui.locateCenterOnScreen = lambda *args, **kwargs: None
        mock_pyautogui.position = lambda: (0, 0)
        mock_pyautogui.size = lambda: (1920, 1080)
        mock_pyautogui.FAILSAFE = False
        mock_pyautogui.PAUSE = 0.1
        
        # Mock pymsgbox 모듈
        mock_pymsgbox = types.ModuleType('pymsgbox')
        mock_pymsgbox.alert = lambda *args, **kwargs: print(f"[자동화] Alert: {args}")
        mock_pymsgbox.confirm = lambda *args, **kwargs: 'OK'
        mock_pymsgbox.prompt = lambda *args, **kwargs: ''
        mock_pymsgbox.password = lambda *args, **kwargs: ''
        
        # Mock pygetwindow 모듈
        mock_pygetwindow = types.ModuleType('pygetwindow')
        
        # 모듈 등록
        sys.modules['pyautogui'] = mock_pyautogui
        sys.modules['pymsgbox'] = mock_pymsgbox
        sys.modules['pygetwindow'] = mock_pygetwindow
        
        # tkinter 모듈 완전 대체
        class MockTk:
            def __init__(self, *args, **kwargs):
                self.mock = True
            def withdraw(self):
                pass
            def destroy(self):
                pass
            def mainloop(self):
                pass
            def quit(self):
                pass
            def deiconify(self):
                pass
            def title(self, *args):
                pass
            def geometry(self, *args):
                pass
            def protocol(self, *args):
                pass
            def bind(self, *args):
                pass
            def update(self):
                pass
            def update_idletasks(self):
                pass
            def configure(self, *args, **kwargs):
                pass
            def winfo_exists(self):
                return True
            def __getattr__(self, name):
                return lambda *args, **kwargs: None
        
        class MockToplevel(MockTk):
            pass
        
        class MockFiledialog:
            @staticmethod
            def askopenfilename(*args, **kwargs):
                print(f"[자동화] 파일 선택 대화상자 호출 차단 → {os.path.basename(selected_file)} 반환")
                return selected_file
            
            @staticmethod
            def askopenfilenames(*args, **kwargs):
                print(f"[자동화] 파일 선택 대화상자 호출 차단 → [{os.path.basename(selected_file)}] 반환")
                return (selected_file,)
            
            @staticmethod
            def asksaveasfilename(*args, **kwargs):
                base, ext = os.path.splitext(selected_file)
                save_file = base + "_result" + ext
                print(f"[자동화] 저장 대화상자 호출 차단 → {os.path.basename(save_file)} 반환")
                return save_file
            
            @staticmethod
            def askdirectory(*args, **kwargs):
                return os.path.dirname(selected_file)
        
        # tkinter 모듈 대체
        mock_tk = types.ModuleType('tkinter')
        mock_tk.Tk = MockTk
        mock_tk.Toplevel = MockToplevel
        mock_tk.Frame = MockTk
        mock_tk.Label = MockTk
        mock_tk.Button = MockTk
        mock_tk.Entry = MockTk
        mock_tk.Text = MockTk
        mock_tk.Canvas = MockTk
        mock_tk.Listbox = MockTk
        mock_tk.Menu = MockTk
        mock_tk.StringVar = lambda: types.SimpleNamespace(get=lambda: "", set=lambda x: None)
        mock_tk.IntVar = lambda: types.SimpleNamespace(get=lambda: 0, set=lambda x: None)
        mock_tk.BooleanVar = lambda: types.SimpleNamespace(get=lambda: False, set=lambda x: None)
        mock_tk.messagebox = types.SimpleNamespace(
            showinfo=lambda *args, **kwargs: print(f"[자동화] 메시지: {args}"),
            showerror=lambda *args, **kwargs: print(f"[자동화] 오류: {args}"),
            showwarning=lambda *args, **kwargs: print(f"[자동화] 경고: {args}"),
            askyesno=lambda *args, **kwargs: True,
            askokcancel=lambda *args, **kwargs: True
        )
        
        mock_filedialog = types.ModuleType('tkinter.filedialog')
        for attr in dir(MockFiledialog):
            if not attr.startswith('_'):
                setattr(mock_filedialog, attr, getattr(MockFiledialog, attr))
        
        # 시스템 모듈 대체
        sys.modules['tkinter'] = mock_tk
        sys.modules['tkinter.filedialog'] = mock_filedialog
        sys.modules['Tkinter'] = mock_tk
        
        # 다른 가능한 import 방식도 차단
        original_import = builtins.__import__
        
        def custom_import(name, *args, **kwargs):
            if name in ['tkinter', 'Tkinter', 'pyautogui', 'pymsgbox', 'pygetwindow']:
                if name == 'tkinter' or name == 'Tkinter':
                    return mock_tk
                elif name == 'pyautogui':
                    return mock_pyautogui
                elif name == 'pymsgbox':
                    return mock_pymsgbox
                elif name == 'pygetwindow':
                    return mock_pygetwindow
            elif name.startswith('tkinter.'):
                if name == 'tkinter.filedialog':
                    return mock_filedialog
                else:
                    return types.SimpleNamespace()
            return original_import(name, *args, **kwargs)
        
        builtins.__import__ = custom_import
        
        print("[자동화] GUI 모듈 대체 완료")

# ===== 자동화 래퍼 끝 =====

'''
    
    def load_last_directory(self):
        """마지막으로 사용한 디렉토리 로드"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    return config.get('last_dxf_dir', self.current_dir)
        except:
            pass
        return self.current_dir
    
    def save_last_directory(self, directory):
        """마지막 사용 디렉토리 저장"""
        try:
            config = {'last_dxf_dir': directory}
            with open(self.config_file, 'w') as f:
                json.dump(config, f)
        except:
            pass
    
    def select_dxf_files(self):
        """DXF 파일 선택 대화상자"""
        root = tk.Tk()
        root.withdraw()
        
        initial_dir = self.last_dxf_dir if os.path.exists(self.last_dxf_dir) else self.current_dir
        
        files = filedialog.askopenfilenames(
            title="처리할 DXF 파일을 선택하세요 (여러 개 선택 가능)",
            filetypes=[("DXF files", "*.dxf"), ("All files", "*.*")],
            initialdir=initial_dir
        )
        
        root.destroy()
        
        if files:
            self.last_dxf_dir = os.path.dirname(files[0])
            self.save_last_directory(self.last_dxf_dir)
        
        return list(files)
    
    def get_clean_filename(self, original_file):
        """파일명에서 _ 뒤의 내용을 제거하고 ACEPLANT를 추가한 이름 반환"""
        dir_name = os.path.dirname(original_file)
        base_name = os.path.splitext(os.path.basename(original_file))[0]
        
        # _ 문자가 있으면 그 앞까지만 사용
        if '_' in base_name:
            base_name = base_name.split('_')[0]
        
        # 빈 문자열이 되면 원본 이름 사용
        if not base_name:
            base_name = os.path.splitext(os.path.basename(original_file))[0]
        
        # ACEPLANT 추가
        clean_name = base_name + 'ACEPLANT.dxf'
        return os.path.join(dir_name, clean_name)
    
    def create_wrapped_script(self, original_script_path):
        """원본 스크립트를 래핑한 임시 스크립트 생성"""
        try:
            with open(original_script_path, 'r', encoding='utf-8') as f:
                original_content = f.read()
        except UnicodeDecodeError:
            try:
                with open(original_script_path, 'r', encoding='cp949') as f:
                    original_content = f.read()
            except:
                with open(original_script_path, 'r', encoding='latin-1') as f:
                    original_content = f.read()
        
        wrapped_content = self.wrapper_code + original_content
        
        temp_script = os.path.join(self.temp_dir, f"wrapped_{os.path.basename(original_script_path)}")
        with open(temp_script, 'w', encoding='utf-8') as f:
            f.write(wrapped_content)
        
        return temp_script
    
    def find_newly_created_dxf(self, work_dir, before_time, exclude_files=None):
        """새로 생성된 DXF 파일 찾기"""
        dxf_files = glob.glob(os.path.join(work_dir, "*.dxf"))
        
        if exclude_files is None:
            exclude_files = []
        
        new_files = []
        for f in dxf_files:
            skip = False
            for exclude in exclude_files:
                try:
                    if os.path.samefile(f, exclude):
                        skip = True
                        break
                except:
                    if os.path.abspath(f) == os.path.abspath(exclude):
                        skip = True
                        break
            
            if skip:
                continue
                
            if os.path.getmtime(f) > before_time:
                new_files.append(f)
        
        if new_files:
            return max(new_files, key=os.path.getmtime)
        
        return None
    
    def wait_for_file_ready(self, file_path, timeout=30):
        """파일이 완전히 생성되고 쓰기가 완료될 때까지 대기"""
        if not os.path.exists(file_path):
            return False
        
        start_time = time.time()
        last_size = -1
        stable_count = 0
        
        while time.time() - start_time < timeout:
            try:
                current_size = os.path.getsize(file_path)
                
                if current_size == last_size and current_size > 0:
                    stable_count += 1
                    if stable_count >= 3:
                        try:
                            with open(file_path, 'rb') as f:
                                f.read(1)
                            return True
                        except:
                            pass
                else:
                    stable_count = 0
                
                last_size = current_size
                time.sleep(0.5)
                
            except Exception:
                time.sleep(0.5)
        
        return False
    
    def process_single_file(self, original_file):
        """하나의 DXF 파일을 모든 스크립트로 처리"""
        current_file = original_file
        work_dir = os.path.dirname(original_file)
        processed_files = [original_file]  # 처리 과정에서 생성된 파일들
        
        print(f"\n파일 처리 시작: {os.path.basename(original_file)}")
        print("=" * 60)
        
        for script_idx, script in enumerate(self.scripts):
            print(f"  [{script_idx+1}/{len(self.scripts)}] {script} 실행 중...", end="")
            
            original_script_path = os.path.join(self.current_dir, script)
            
            if not os.path.exists(original_script_path):
                print(" ⚠ 스크립트 없음")
                continue
            
            wrapped_script = self.create_wrapped_script(original_script_path)
            before_time = time.time()
            
            try:
                env = os.environ.copy()
                env['SELECTED_DXF_FILE'] = current_file
                env['AUTO_MODE'] = 'TRUE'
                env['PYTHONIOENCODING'] = 'utf-8'
                
                if sys.platform == 'win32':
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    startupinfo.wShowWindow = subprocess.SW_HIDE
                else:
                    startupinfo = None
                
                process = subprocess.Popen(
                    [sys.executable, wrapped_script],
                    env=env,
                    cwd=work_dir,
                    startupinfo=startupinfo,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    encoding='utf-8',
                    errors='replace'
                )
                
                stdout, stderr = process.communicate(timeout=120)
                
                if process.returncode == 0:
                    print(" ✓")
                    
                    time.sleep(2)
                    
                    new_file = self.find_newly_created_dxf(work_dir, before_time, processed_files)
                    
                    if new_file and self.wait_for_file_ready(new_file):
                        processed_files.append(new_file)
                        self.temp_files.add(new_file)
                        current_file = new_file
                    elif os.path.exists(current_file) and os.path.getmtime(current_file) > before_time:
                        pass  # 현재 파일이 수정됨
                else:
                    print(" ⚠ 오류")
                    if stderr:
                        print(f"      오류: {stderr.strip()[:100]}")
                
            except subprocess.TimeoutExpired:
                print(" ⏱ 시간 초과")
                process.kill()
            except Exception as e:
                print(f" ✗ 오류: {str(e)}")
            finally:
                try:
                    os.remove(wrapped_script)
                except:
                    pass
            
            time.sleep(1)
        
        return current_file, processed_files
    
    def rename_all_layers_to_aceplant(self, dxf_file):
        """DXF 파일의 모든 레이어 이름을 ACEPLANT로 변경"""
        if not EZDXF_AVAILABLE:
            print(f"  ✗ ezdxf 라이브러리가 없어 레이어 변경을 건너뜁니다.")
            return False
            
        try:
            print(f"\n레이어 이름 변경 중: {os.path.basename(dxf_file)}")
            
            # DXF 파일 읽기
            doc = ezdxf.readfile(dxf_file)
            
            # 모든 엔티티의 레이어를 ACEPLANT로 변경
            for entity in doc.modelspace():
                entity.dxf.layer = "ACEPLANT"
            
            # 페이퍼스페이스의 엔티티도 처리
            for layout in doc.layouts:
                if layout.name != 'Model':
                    for entity in layout:
                        try:
                            entity.dxf.layer = "ACEPLANT"
                        except:
                            pass
            
            # 블록 내부의 엔티티도 처리
            for block in doc.blocks:
                for entity in block:
                    try:
                        entity.dxf.layer = "ACEPLANT"
                    except:
                        pass
            
            # 기존 레이어들 삭제 (ACEPLANT와 0 레이어 제외)
            layers_to_delete = []
            for layer in doc.layers:
                if layer.dxf.name not in ['ACEPLANT', '0']:
                    layers_to_delete.append(layer.dxf.name)
            
            # ACEPLANT 레이어가 없으면 생성
            if 'ACEPLANT' not in [layer.dxf.name for layer in doc.layers]:
                doc.layers.new(name='ACEPLANT')
            
            # 불필요한 레이어 삭제
            for layer_name in layers_to_delete:
                try:
                    doc.layers.remove(layer_name)
                except:
                    pass
            
            # 임시 파일로 저장
            temp_file = dxf_file + '.tmp'
            doc.saveas(temp_file)
            
            # 원본 파일 교체
            os.remove(dxf_file)
            os.rename(temp_file, dxf_file)
            
            print(f"  ✓ 모든 레이어가 ACEPLANT로 변경됨")
            return True
            
        except Exception as e:
            print(f"  ✗ 레이어 변경 실패: {str(e)}")
            return False
    
    def cleanup_temp_files(self, original_files, final_files, keep_files):
        """임시 파일 정리"""
        print("\n임시 파일 정리 중...")
        
        # 보존해야 할 파일들
        keep_set = set()
        for f in original_files + final_files + keep_files:
            if f and os.path.exists(f):
                keep_set.add(os.path.abspath(f))
        
        # 임시 파일 삭제
        deleted_count = 0
        for temp_file in list(self.temp_files):
            try:
                abs_temp = os.path.abspath(temp_file)
                if abs_temp not in keep_set and os.path.exists(temp_file):
                    os.remove(temp_file)
                    deleted_count += 1
                    print(f"  ✓ 삭제: {os.path.basename(temp_file)}")
            except Exception as e:
                print(f"  ✗ 삭제 실패: {os.path.basename(temp_file)} - {str(e)}")
        
        print(f"  총 {deleted_count}개 임시 파일 삭제됨")
    
    def process_files(self):
        """선택된 DXF 파일들을 처리"""
        files = self.select_dxf_files()
        
        if not files:
            messagebox.showinfo("알림", "선택된 파일이 없습니다.")
            return
        
        print(f"\n{'='*60}")
        print(f"DXF 자동 처리 시작")
        print(f"선택된 파일: {len(files)}개")
        for f in files:
            print(f"  - {os.path.basename(f)}")
        print(f"{'='*60}")
        
        self.temp_dir = tempfile.mkdtemp()
        final_results = {}
        
        try:
            # 각 파일을 개별적으로 처리
            for file_idx, original_file in enumerate(files, 1):
                print(f"\n\n[파일 {file_idx}/{len(files)}] 처리 중...")
                
                # 모든 스크립트로 파일 처리
                final_file, temp_files = self.process_single_file(original_file)
                
                # 레이어 이름 변경 (ezdxf가 있을 때만)
                if final_file and os.path.exists(final_file):
                    if EZDXF_AVAILABLE:
                        self.rename_all_layers_to_aceplant(final_file)
                    else:
                        print("  ⚠ ezdxf가 없어 레이어 변경을 건너뜁니다.")
                
                # 최종 파일명 생성 및 저장 (예: drawing_Final_v2.dxf → drawingACEPLANT.dxf)
                clean_name = self.get_clean_filename(original_file)
                final_path = os.path.join(os.path.dirname(original_file), clean_name)
                
                try:
                    # 최종 파일이 원본과 다른 경우
                    if os.path.abspath(final_file) != os.path.abspath(final_path):
                        # 기존 파일이 있으면 백업
                        if os.path.exists(final_path) and os.path.abspath(final_path) != os.path.abspath(original_file):
                            backup_path = final_path + '.bak'
                            shutil.move(final_path, backup_path)
                            self.temp_files.add(backup_path)
                        
                        # 최종 파일 복사
                        shutil.copy2(final_file, final_path)
                        print(f"  ✓ 최종 파일 저장: {clean_name}")
                    
                    final_results[original_file] = final_path
                    
                except Exception as e:
                    print(f"  ✗ 최종 파일 저장 실패: {str(e)}")
                    final_results[original_file] = final_file
            
            # 임시 파일 정리
            keep_files = list(final_results.values())
            self.cleanup_temp_files(files, keep_files, [])
            
            # 결과 출력
            print(f"\n\n{'='*60}")
            print("🎉 모든 처리가 완료되었습니다!")
            print(f"\n처리 결과:")
            print(f"  원본 파일: {len(files)}개")
            print(f"  처리 완료: {len(final_results)}개")
            print(f"\n최종 파일 목록:")
            for original, final in final_results.items():
                if os.path.exists(final):
                    print(f"  ✓ {os.path.basename(original)} → {os.path.basename(final)}")
                else:
                    print(f"  ✗ {os.path.basename(original)} (처리 실패)")
            print(f"{'='*60}")
            
        except Exception as e:
            print(f"\n\n심각한 오류 발생: {str(e)}")
            import traceback
            traceback.print_exc()
            
        finally:
            # 임시 디렉토리 정리
            if self.temp_dir and os.path.exists(self.temp_dir):
                try:
                    shutil.rmtree(self.temp_dir)
                except:
                    print(f"\n임시 디렉토리 삭제 실패: {self.temp_dir}")

def main():
    print("DXF 자동 처리 프로그램 v2.1")
    print("="*60)
    print("이 프로그램의 기능:")
    print("  1. 선택된 DXF 파일들을 지정된 Python 스크립트로 순차 처리")
    print("  2. 처리 중 생성된 임시 파일들 자동 삭제")
    print("  3. 최종 파일의 모든 레이어를 ACEPLANT로 변경")
    print("  4. 파일명에서 _ 뒤의 내용을 제거하고 'ACEPLANT.dxf'로 저장")
    print("     예: drawing_Final_v2.dxf → drawingACEPLANT.dxf")
    print("\n참고: 레이어 변경 기능은 ezdxf 라이브러리가 필요합니다.")
    print("     설치 명령어: pip install ezdxf")
    print("="*60)
    
    # ezdxf 라이브러리 확인
    if not EZDXF_AVAILABLE:
        print("\n⚠ ezdxf 라이브러리가 설치되어 있지 않습니다!")
        print("설치 명령어: pip install ezdxf")
        input("\nEnter 키를 눌러 종료...")
        return
    
    try:
        # 버전 확인 - 여러 방법 시도
        version = None
        if hasattr(ezdxf, '__version__'):
            version = ezdxf.__version__
        elif hasattr(ezdxf, 'version'):
            if isinstance(ezdxf.version, str):
                version = ezdxf.version
            elif hasattr(ezdxf.version, '__version__'):
                version = ezdxf.version.__version__
        
        if version:
            print(f"ezdxf 버전: {version}")
        else:
            print("ezdxf가 설치되어 있습니다.")
    except Exception as e:
        print(f"ezdxf 버전 확인 중 오류: {e}")
        print("ezdxf가 설치되어 있습니다.")
    
    processor = DXFAutoProcessor()
    
    # 스크립트 파일 확인
    missing = []
    print(f"\n현재 디렉토리: {processor.current_dir}")
    print("\n스크립트 파일 확인 중...")
    
    for script in processor.scripts:
        script_path = os.path.join(processor.current_dir, script)
        if os.path.exists(script_path):
            print(f"  ✓ {script}")
        else:
            print(f"  ✗ {script} (누락)")
            missing.append(script)
    
    if missing:
        print(f"\n⚠ 총 {len(missing)}개의 스크립트가 누락되었습니다.")
        print("  누락된 스크립트로 인해 일부 처리가 건너뛰어질 수 있습니다.")
        if input("\n계속하시겠습니까? (y/n): ").lower() != 'y':
            return
    else:
        print(f"\n✓ 모든 스크립트 파일이 준비되었습니다.")
    
    try:
        processor.process_files()
    except KeyboardInterrupt:
        print("\n\n사용자에 의해 중단되었습니다.")
    except Exception as e:
        print(f"\n\n오류 발생: {str(e)}")
        import traceback
        traceback.print_exc()
    
    print("\n종료하려면 Enter 키를 누르세요...")
    input()

if __name__ == "__main__":
    main()