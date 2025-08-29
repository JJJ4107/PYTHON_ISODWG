import os
import shutil
import tkinter as tk
from tkinter import filedialog
import sys

def process_py_files():
    """디렉토리를 선택하고 .py 파일들을 처리하는 메인 함수"""
    
    # tkinter 루트 윈도우 생성 및 설정
    root = tk.Tk()
    root.withdraw()  # 메인 윈도우 숨기기
    root.wm_attributes('-topmost', 1)  # 창을 최상위로
    
    # 포커스 설정을 위한 더미 윈도우 생성
    root.update_idletasks()
    root.update()
    
    # 디렉토리 선택 대화상자 열기
    selected_dir = filedialog.askdirectory(
        title="처리할 디렉토리를 선택하세요",
        parent=root
    )
    
    # root 윈도우 종료
    root.destroy()
    
    if not selected_dir:
        print("디렉토리가 선택되지 않았습니다.")
        return
    
    print(f"\n선택된 디렉토리: {selected_dir}")
    print("-" * 50)
    
    # 처리된 파일 수 카운터
    renamed_count = 0
    copied_count = 0
    skipped_count = 0
    
    # 디렉토리의 모든 파일 확인
    files = [f for f in os.listdir(selected_dir) if os.path.isfile(os.path.join(selected_dir, f))]
    
    for filename in files:
        # .py 파일이고 앞 2자리가 숫자인지 확인
        if filename.lower().endswith('.py') and len(filename) >= 2:
            # 파일명 앞 2자리가 숫자인지 확인
            if filename[:2].isdigit():
                old_path = os.path.join(selected_dir, filename)
                
                try:
                    # 1. 원본 파일 이름 변경: E3D_ + 원래파일이름
                    # 이미 E3D_로 시작하는 경우는 건너뛰기
                    if not filename.startswith("E3D_"):
                        new_filename = f"E3D_{filename}"
                        new_path = os.path.join(selected_dir, new_filename)
                        
                        # 대상 파일이 이미 존재하는지 확인
                        if os.path.exists(new_path):
                            print(f"⚠️  이미 존재함: {new_filename}")
                            skipped_count += 1
                        else:
                            os.rename(old_path, new_path)
                            print(f"✅ 이름 변경: {filename} → {new_filename}")
                            renamed_count += 1
                            
                            # 이름 변경 후의 경로 업데이트
                            old_path = new_path
                            filename = new_filename
                    else:
                        # 이미 E3D_로 시작하는 파일
                        print(f"⏭️  건너뜀 (이미 E3D_ 접두사): {filename}")
                        skipped_count += 1
                    
                    # 2. 파일 복사: E3D_ON_ + 원래파일이름
                    # E3D_가 이미 붙어있는 경우 처리
                    if filename.startswith("E3D_"):
                        original_name = filename[4:]  # E3D_ 제거
                    else:
                        original_name = filename
                        
                    copy_filename = f"E3D_ON_{original_name}"
                    copy_path = os.path.join(selected_dir, copy_filename)
                    
                    # 복사본이 이미 존재하지 않는 경우에만 복사
                    if not os.path.exists(copy_path):
                        shutil.copy2(old_path, copy_path)
                        print(f"✅ 복사 생성: {copy_filename}")
                        copied_count += 1
                    else:
                        print(f"⚠️  복사본 이미 존재: {copy_filename}")
                        
                except Exception as e:
                    print(f"❌ 오류 발생 ({filename}): {str(e)}")
    
    # 처리 결과 출력
    print("\n" + "="*50)
    print(f"🎯 처리 완료!")
    print(f"✅ 이름 변경된 파일 수: {renamed_count}")
    print(f"✅ 복사 생성된 파일 수: {copied_count}")
    print(f"⏭️  건너뛴 파일 수: {skipped_count}")
    print("="*50)

def test_tkinter():
    """tkinter가 제대로 작동하는지 테스트"""
    try:
        root = tk.Tk()
        root.destroy()
        return True
    except Exception as e:
        print(f"tkinter 오류: {e}")
        return False

def main():
    """프로그램 실행"""
    print("\n" + "="*50)
    print("Python 파일 이름 변경 및 복사 프로그램")
    print("="*50)
    print("\n이 프로그램은 선택한 디렉토리에서:")
    print("1. 파일명 앞 2자리가 숫자인 .py 파일을 찾습니다")
    print("2. 해당 파일명을 'E3D_' + 원래이름으로 변경합니다")
    print("3. 각 파일을 'E3D_ON_' + 원래이름으로 복사합니다")
    print("-" * 50)
    
    # tkinter 테스트
    if not test_tkinter():
        print("\n⚠️  tkinter가 제대로 설치되지 않았거나 작동하지 않습니다.")
        print("대신 디렉토리 경로를 직접 입력해주세요.")
        selected_dir = input("디렉토리 경로: ").strip()
        
        if os.path.isdir(selected_dir):
            print(f"\n선택된 디렉토리: {selected_dir}")
            print("-" * 50)
            
            # 직접 처리 함수 호출
            process_py_files_manual(selected_dir)
        else:
            print("올바른 디렉토리 경로가 아닙니다.")
    else:
        input("\n계속하려면 Enter 키를 누르세요...")
        process_py_files()
    
    input("\n종료하려면 Enter 키를 누르세요...")

def process_py_files_manual(selected_dir):
    """수동으로 입력받은 디렉토리 처리"""
    # 처리된 파일 수 카운터
    renamed_count = 0
    copied_count = 0
    skipped_count = 0
    
    # 디렉토리의 모든 파일 확인
    files = [f for f in os.listdir(selected_dir) if os.path.isfile(os.path.join(selected_dir, f))]
    
    for filename in files:
        # .py 파일이고 앞 2자리가 숫자인지 확인
        if filename.lower().endswith('.py') and len(filename) >= 2:
            # 파일명 앞 2자리가 숫자인지 확인
            if filename[:2].isdigit():
                old_path = os.path.join(selected_dir, filename)
                
                try:
                    # 1. 원본 파일 이름 변경: E3D_ + 원래파일이름
                    if not filename.startswith("E3D_"):
                        new_filename = f"E3D_{filename}"
                        new_path = os.path.join(selected_dir, new_filename)
                        
                        if os.path.exists(new_path):
                            print(f"⚠️  이미 존재함: {new_filename}")
                            skipped_count += 1
                        else:
                            os.rename(old_path, new_path)
                            print(f"✅ 이름 변경: {filename} → {new_filename}")
                            renamed_count += 1
                            
                            old_path = new_path
                            filename = new_filename
                    else:
                        print(f"⏭️  건너뜀 (이미 E3D_ 접두사): {filename}")
                        skipped_count += 1
                    
                    # 2. 파일 복사: E3D_ON_ + 원래파일이름
                    if filename.startswith("E3D_"):
                        original_name = filename[4:]
                    else:
                        original_name = filename
                        
                    copy_filename = f"E3D_ON_{original_name}"
                    copy_path = os.path.join(selected_dir, copy_filename)
                    
                    if not os.path.exists(copy_path):
                        shutil.copy2(old_path, copy_path)
                        print(f"✅ 복사 생성: {copy_filename}")
                        copied_count += 1
                    else:
                        print(f"⚠️  복사본 이미 존재: {copy_filename}")
                        
                except Exception as e:
                    print(f"❌ 오류 발생 ({filename}): {str(e)}")
    
    # 처리 결과 출력
    print("\n" + "="*50)
    print(f"🎯 처리 완료!")
    print(f"✅ 이름 변경된 파일 수: {renamed_count}")
    print(f"✅ 복사 생성된 파일 수: {copied_count}")
    print(f"⏭️  건너뛴 파일 수: {skipped_count}")
    print("="*50)

if __name__ == "__main__":
    main()