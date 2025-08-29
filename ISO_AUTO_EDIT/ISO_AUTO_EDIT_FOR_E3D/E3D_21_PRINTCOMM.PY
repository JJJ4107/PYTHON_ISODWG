import os
import re
import tkinter as tk
from tkinter import filedialog, messagebox
import sys

def remove_print_statements(code):
    """코드에서 print 문을 제거 - 정규표현식 사용"""
    # 단일 라인 print 문 제거
    code = re.sub(r'^\s*print\s*\([^)]*\)\s*$', '', code, flags=re.MULTILINE)
    
    # 여러 줄에 걸친 print 문 제거 (기본적인 경우)
    # print( 로 시작하는 부분 찾기
    lines = code.split('\n')
    result_lines = []
    skip_lines = 0
    
    for i, line in enumerate(lines):
        if skip_lines > 0:
            skip_lines -= 1
            continue
            
        # print 문의 시작을 감지
        if re.match(r'^\s*print\s*\(', line):
            # 괄호의 균형을 확인하여 print 문의 끝을 찾기
            open_count = line.count('(')
            close_count = line.count(')')
            j = i
            
            # 괄호가 균형을 이룰 때까지 계속 확인
            while j < len(lines) and open_count > close_count:
                j += 1
                if j < len(lines):
                    open_count += lines[j].count('(')
                    close_count += lines[j].count(')')
            
            # print 문이 끝나는 라인까지 스킵
            skip_lines = j - i
        else:
            result_lines.append(line)
    
    return '\n'.join(result_lines)

def modify_for_command_line(code, filename):
    """tkinter 기반 파일 선택을 command line 인자로 변경"""
    
    # tkinter import 문 제거
    code = re.sub(r'^\s*import\s+tkinter.*$', '', code, flags=re.MULTILINE)
    code = re.sub(r'^\s*from\s+tkinter\s+import.*$', '', code, flags=re.MULTILINE)
    code = re.sub(r'^\s*import\s+tkinter$', '', code, flags=re.MULTILINE)
    
    # Tk() 관련 코드 제거
    code = re.sub(r'^\s*\w+\s*=\s*tk\.Tk\(\).*$', '', code, flags=re.MULTILINE)
    code = re.sub(r'^\s*\w+\s*=\s*Tk\(\).*$', '', code, flags=re.MULTILINE)
    code = re.sub(r'^\s*root\s*=\s*tk\.Tk\(\).*$', '', code, flags=re.MULTILINE)
    code = re.sub(r'^\s*root\s*=\s*Tk\(\).*$', '', code, flags=re.MULTILINE)
    
    # withdraw, mainloop 등 tkinter 메서드 호출 제거
    code = re.sub(r'^\s*\w+\.withdraw\(\).*$', '', code, flags=re.MULTILINE)
    code = re.sub(r'^\s*\w+\.mainloop\(\).*$', '', code, flags=re.MULTILINE)
    code = re.sub(r'^\s*\w+\.deiconify\(\).*$', '', code, flags=re.MULTILINE)
    code = re.sub(r'^\s*\w+\.destroy\(\).*$', '', code, flags=re.MULTILINE)
    code = re.sub(r'^\s*root\..*$', '', code, flags=re.MULTILINE)
    
    # filedialog를 사용한 파일 선택 부분을 찾아서 command line 인자로 교체
    # 다양한 패턴들
    patterns = [
        r'(\w+)\s*=\s*filedialog\.askopenfilename\([^)]*\)',
        r'(\w+)\s*=\s*tkinter\.filedialog\.askopenfilename\([^)]*\)',
        r'(\w+)\s*=\s*tk\.filedialog\.askopenfilename\([^)]*\)',
        r'(\w+)\s*=\s*fd\.askopenfilename\([^)]*\)',  # fd로 import한 경우
    ]
    
    # sys import 추가 여부 확인
    has_sys_import = bool(re.search(r'^\s*import\s+sys\s*$', code, flags=re.MULTILINE))
    
    # 교체 함수
    def replace_with_sys_argv(match):
        var_name = match.group(1)
        return f"""{var_name} = sys.argv[1] if len(sys.argv) > 1 else None
if not {var_name}:
    print("Usage: python {filename} <DXF_FILE>")
    sys.exit(1)"""
    
    # 파일 선택 코드를 command line 인자로 교체
    replaced = False
    for pattern in patterns:
        if re.search(pattern, code):
            code = re.sub(pattern, replace_with_sys_argv, code)
            replaced = True
    
    # sys import가 없으면 추가
    if replaced and not has_sys_import:
        # 첫 번째 import 문을 찾아서 그 다음에 추가
        lines = code.split('\n')
        import_added = False
        for i, line in enumerate(lines):
            if line.strip().startswith('import ') or line.strip().startswith('from '):
                lines.insert(i + 1, 'import sys')
                import_added = True
                break
        
        if not import_added:
            # import 문이 없으면 맨 앞에 추가
            lines.insert(0, 'import sys')
        
        code = '\n'.join(lines)
    
    # 빈 줄이 너무 많이 생기는 것을 방지
    code = re.sub(r'\n\s*\n\s*\n+', '\n\n', code)
    
    return code

def find_py_files(directory, include_subdirs=True):
    """디렉토리에서 모든 Python 파일 찾기 (대소문자 구분 없음)"""
    py_files = []
    
    if include_subdirs:
        # 하위 디렉토리 포함하여 검색
        for root, dirs, files in os.walk(directory):
            for filename in files:
                # 대소문자 구분 없이 .py 확장자 확인
                if filename.lower().endswith('.py') and not filename.lower().endswith('.backup'):
                    py_files.append(os.path.join(root, filename))
    else:
        # 현재 디렉토리만 검색
        try:
            files = os.listdir(directory)
            for filename in files:
                if filename.lower().endswith('.py') and not filename.lower().endswith('.backup'):
                    py_files.append(os.path.join(directory, filename))
        except Exception as e:
            print(f"Error reading directory: {e}")
    
    return py_files

def process_py_file(filepath):
    """단일 .py 파일을 처리"""
    try:
        # 원본 파일 백업
        backup_path = filepath + '.backup'
        
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 백업 파일 생성
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        # 1. print 문 제거
        content = remove_print_statements(content)
        
        # 2. tkinter를 command line 인자로 변경
        filename = os.path.basename(filepath)
        content = modify_for_command_line(content, filename)
        
        # 3. 같은 이름으로 저장
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return True, f"Successfully processed: {filepath}"
    except Exception as e:
        return False, f"Error processing {filepath}: {str(e)}"

def main():
    # tkinter로 디렉토리 선택
    root = tk.Tk()
    root.withdraw()  # 메인 윈도우 숨기기
    
    directory = filedialog.askdirectory(title="Select Directory with Python Files")
    
    if not directory:
        print("No directory selected.")
        root.destroy()
        return
    
    # 하위 디렉토리 포함 여부 물어보기
    include_subdirs = messagebox.askyesno(
        "Include Subdirectories?",
        "Do you want to include Python files in subdirectories?"
    )
    
    root.destroy()  # tkinter 종료
    
    print(f"\nSearching for Python files in: {directory}")
    if include_subdirs:
        print("Including subdirectories...")
    
    # 디렉토리의 모든 파일 목록 출력 (디버깅용)
    print("\nAll files in selected directory:")
    try:
        all_files = os.listdir(directory)
        for f in all_files[:10]:  # 처음 10개만 출력
            print(f"  - {f}")
        if len(all_files) > 10:
            print(f"  ... and {len(all_files) - 10} more files")
    except Exception as e:
        print(f"Error listing directory: {e}")
    
    # Python 파일 찾기
    py_files = find_py_files(directory, include_subdirs)
    
    if not py_files:
        print(f"\nNo Python files (.py or .PY) found in {directory}")
        print("\nPlease check:")
        print("1. File extensions (.py, .PY, .Py)")
        print("2. File permissions")
        print("3. If files are in subdirectories, restart and select 'Yes' for including subdirectories")
        return
    
    print(f"\nFound {len(py_files)} Python files:")
    for pf in py_files[:5]:  # 처음 5개만 출력
        print(f"  - {os.path.basename(pf)}")
    if len(py_files) > 5:
        print(f"  ... and {len(py_files) - 5} more files")
    
    # 계속 진행할지 확인
    response = input("\nDo you want to process these files? (y/n): ")
    if response.lower() != 'y':
        print("Operation cancelled.")
        return
    
    print("\nProcessing files...")
    print("-" * 70)
    
    success_count = 0
    error_count = 0
    
    for py_file in py_files:
        success, message = process_py_file(py_file)
        print(message)
        
        if success:
            success_count += 1
        else:
            error_count += 1
    
    print("-" * 70)
    print(f"\nProcessing complete!")
    print(f"Success: {success_count} files")
    print(f"Errors: {error_count} files")
    print(f"\nNote: Original files have been backed up with .backup extension")

if __name__ == "__main__":
    main()