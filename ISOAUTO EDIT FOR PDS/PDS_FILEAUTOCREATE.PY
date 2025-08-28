import os
import shutil
import sys

def rename_pds_files():
    """현재 디렉토리에서 PDS로 시작하는 .py 파일들을 PDS_ON으로 이름 변경"""
    
    # 이 프로그램 파일이 있는 디렉토리 가져오기
    current_dir = os.path.dirname(os.path.abspath(__file__))
    print(f"\n프로그램 파일 위치: {current_dir}")
    print("-" * 50)
    
    # 처리된 파일 수 카운터
    copied_count = 0
    skipped_count = 0
    error_count = 0
    
    # 현재 디렉토리의 모든 파일 확인
    try:
        files = [f for f in os.listdir(current_dir) if os.path.isfile(os.path.join(current_dir, f))]
    except Exception as e:
        print(f"❌ 디렉토리 읽기 오류: {str(e)}")
        return
    
    # 디버깅: 모든 파일 목록 출력
    print(f"📁 폴더 내 전체 파일 수: {len(files)}")
    print("\n📄 모든 파일 목록:")
    for i, filename in enumerate(files, 1):
        print(f"  {i:2d}. {filename}")
    
    print("\n" + "-" * 30)
    
    # PDS로 시작하는 .py 파일들 찾기
    pds_files = []
    py_files = []
    
    for filename in files:
        # 모든 .py 파일 수집 (대소문자 구분 없이)
        if filename.lower().endswith('.py'):
            py_files.append(filename)
            
            # PDS로 시작하고 PDS_ON으로 시작하지 않는 파일
            if (filename.startswith('PDS') and 
                not filename.startswith('PDS_ON')):
                pds_files.append(filename)
    
    print(f"🐍 Python 파일 수: {len(py_files)}")
    if py_files:
        for py_file in py_files:
            status = "✅ 대상" if py_file in pds_files else "⏭️ 제외"
            print(f"     {status}: {py_file}")
    
    print(f"\n🎯 처리 대상 PDS 파일 수: {len(pds_files)}")
    if pds_files:
        for pds_file in pds_files:
            print(f"     ▶️  {pds_file}")
    
    if not pds_files:
        print("🔍 PDS로 시작하는 .py 파일이 없습니다.")
        return
    
    print(f"📁 발견된 PDS 파일 수: {len(pds_files)}")
    print("-" * 30)
    
    # 각 파일 처리
    for filename in pds_files:
        old_path = os.path.join(current_dir, filename)
        
        try:
            # 새 파일명 생성: PDS를 PDS_ON으로 변경하고 뒤의 문자는 그대로 유지
            # PDS 뒤의 모든 문자를 추출
            remaining_part = filename[3:]  # PDS(3글자) 뒤의 모든 문자
            new_filename = f"PDS_ON{remaining_part}"
            
            new_path = os.path.join(current_dir, new_filename)
            
            # 대상 파일이 이미 존재하는지 확인
            if os.path.exists(new_path):
                print(f"⚠️  이미 존재함: {new_filename}")
                skipped_count += 1
            else:
                # 파일 복사
                import shutil
                shutil.copy2(old_path, new_path)
                print(f"✅ 복사 생성: {filename} → {new_filename}")
                copied_count += 1
                
        except Exception as e:
            print(f"❌ 오류 발생 ({filename}): {str(e)}")
            error_count += 1
    
    # 처리 결과 출력
    print("\n" + "="*50)
    print(f"🎯 처리 완료!")
    print(f"✅ 복사 생성된 파일 수: {copied_count}")
    print(f"⏭️  건너뛴 파일 수: {skipped_count}")
    print(f"❌ 오류 발생 파일 수: {error_count}")
    print("="*50)

def main():
    """프로그램 실행"""
    print("\n" + "="*50)
    print("PDS 파일 이름 변경 프로그램")
    print("="*50)
    print("\n이 프로그램은 현재 디렉토리에서:")
    print("1. 'PDS'로 시작하는 .py 파일을 찾습니다")
    print("2. 원본은 그대로 두고 'PDS_ON'으로 시작하는 복사본을 생성합니다")
    print("3. 이미 'PDS_ON'으로 시작하는 파일은 건너뜁니다")
    print("-" * 50)
    
    # 사용자 확인
    try:
        confirm = input("\n계속 진행하시겠습니까? (y/N): ").strip().lower()
        if confirm in ['y', 'yes']:
            rename_pds_files()
        else:
            print("작업이 취소되었습니다.")
    except KeyboardInterrupt:
        print("\n\n작업이 중단되었습니다.")
    
    input("\n종료하려면 Enter 키를 누르세요...")

if __name__ == "__main__":
    main()