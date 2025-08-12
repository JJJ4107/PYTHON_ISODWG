#!/usr/bin/env python3
"""
Git 저장소 현황 확인 스크립트
사용자: 장혁준
이메일: jj@aceplant.co.kr
"""

import subprocess
import os
from datetime import datetime
from pathlib import Path

class GitStatusChecker:
    def __init__(self):
        self.current_dir = Path.cwd()
        # Windows 환경에서 Git 출력 인코딩 설정
        os.environ['LANG'] = 'en_US.UTF-8'
        os.environ['LC_ALL'] = 'en_US.UTF-8'
        
    def run_command(self, command):
        """Git 명령어 실행"""
        try:
            # Windows 환경에서 UTF-8 인코딩 사용
            result = subprocess.run(
                command, 
                shell=True, 
                capture_output=True, 
                text=True,
                encoding='utf-8',
                errors='replace'  # 디코딩 에러 시 대체 문자 사용
            )
            
            # stdout이 None인 경우 빈 문자열 반환
            stdout = result.stdout if result.stdout is not None else ""
            return result.returncode == 0, stdout
        except Exception as e:
            return False, str(e)
    
    def check_git_repo(self):
        """Git 저장소인지 확인"""
        if not os.path.exists(os.path.join(self.current_dir, '.git')):
            print("❌ 현재 디렉토리는 Git 저장소가 아닙니다.")
            return False
        return True
    
    def show_user_info(self):
        """현재 Git 사용자 정보 표시"""
        print("\n👤 Git 사용자 정보:")
        print("=" * 50)
        
        success, name = self.run_command("git config user.name")
        if success:
            print(f"이름: {name.strip()}")
        
        success, email = self.run_command("git config user.email")
        if success:
            print(f"이메일: {email.strip()}")
    
    def show_repository_info(self):
        """저장소 기본 정보 표시"""
        print("\n📁 저장소 정보:")
        print("=" * 50)
        print(f"위치: {self.current_dir}")
        
        # 현재 브랜치
        success, branch = self.run_command("git branch --show-current")
        if success:
            print(f"현재 브랜치: {branch.strip()}")
        
        # 모든 브랜치 목록
        success, branches = self.run_command("git branch -a")
        if success:
            print("\n브랜치 목록:")
            for line in branches.strip().split('\n'):
                print(f"  {line}")
    
    def show_remote_info(self):
        """원격 저장소 정보 표시"""
        print("\n🌐 원격 저장소 정보:")
        print("=" * 50)
        
        success, remotes = self.run_command("git remote -v")
        if success and remotes.strip():
            print(remotes.strip())
        else:
            print("설정된 원격 저장소가 없습니다.")
    
    def show_status(self):
        """현재 작업 상태 표시"""
        print("\n📊 현재 작업 상태:")
        print("=" * 50)
        
        success, status = self.run_command("git status")
        if success:
            print(status.strip())
    
    def show_commit_history(self, limit=10):
        """커밋 히스토리 표시"""
        print(f"\n📜 최근 커밋 히스토리 (최근 {limit}개):")
        print("=" * 50)
        
        # 더 자세한 로그 형식
        log_format = "--pretty=format:'%C(yellow)%h%C(reset) - %C(green)(%cr)%C(reset) %C(bold blue)<%an>%C(reset) %s'"
        success, log = self.run_command(f"git log {log_format} -{limit}")
        
        if success and log.strip():
            print(log.strip())
        else:
            print("커밋 히스토리가 없습니다.")
    
    def show_file_statistics(self):
        """파일 통계 표시"""
        print("\n📈 파일 통계:")
        print("=" * 50)
        
        # 전체 파일 수
        success, files = self.run_command("git ls-files")
        if success:
            file_list = files.strip().split('\n') if files.strip() else []
            total_files = len(file_list)
            print(f"Git에 추적되는 전체 파일 수: {total_files}")
            
            # 파일 타입별 통계
            file_types = {}
            for file in file_list:
                ext = os.path.splitext(file)[1].lower()
                if ext:
                    file_types[ext] = file_types.get(ext, 0) + 1
            
            if file_types:
                print("\n파일 타입별 통계:")
                for ext, count in sorted(file_types.items(), key=lambda x: x[1], reverse=True)[:10]:
                    print(f"  {ext}: {count}개")
            
            # Python 파일 통계
            py_files = [f for f in file_list if f.lower().endswith('.py')]
            if py_files:
                print(f"\nPython 파일: {len(py_files)}개")
                print("최근 추가된 Python 파일 (최대 5개):")
                for file in py_files[-5:]:
                    print(f"  - {file}")
    
    def show_uncommitted_changes(self):
        """커밋되지 않은 변경사항 표시"""
        print("\n⚠️  커밋되지 않은 변경사항:")
        print("=" * 50)
        
        # 스테이징된 파일
        success, staged = self.run_command("git diff --cached --name-status")
        if success and staged.strip():
            print("\n스테이징된 파일:")
            for line in staged.strip().split('\n'):
                parts = line.split('\t', 1)
                if len(parts) == 2:
                    status, filename = parts
                    status_text = {'A': '추가', 'M': '수정', 'D': '삭제'}.get(status, status)
                    print(f"  [{status_text}] {filename}")
                else:
                    print(f"  {line}")
        
        # 수정된 파일
        success, modified = self.run_command("git diff --name-status")
        if success and modified.strip():
            print("\n수정된 파일 (스테이징 안됨):")
            for line in modified.strip().split('\n'):
                parts = line.split('\t', 1)
                if len(parts) == 2:
                    status, filename = parts
                    status_text = {'M': '수정', 'D': '삭제'}.get(status, status)
                    print(f"  [{status_text}] {filename}")
                else:
                    print(f"  {line}")
        
        # 추적되지 않는 파일
        success, untracked = self.run_command("git ls-files --others --exclude-standard")
        if success and untracked.strip():
            untracked_files = untracked.strip().split('\n')
            print(f"\n추적되지 않는 파일 ({len(untracked_files)}개):")
            for file in untracked_files[:10]:
                print(f"  - {file}")
            if len(untracked_files) > 10:
                print(f"  ... 그 외 {len(untracked_files) - 10}개")
    
    def show_last_push_info(self):
        """마지막 푸시 정보 표시"""
        print("\n📤 마지막 푸시 정보:")
        print("=" * 50)
        
        # 현재 브랜치의 업스트림 확인
        success, upstream = self.run_command("git rev-parse --abbrev-ref --symbolic-full-name @{u}")
        if success and upstream.strip():
            # 로컬과 원격의 차이 확인
            success, ahead = self.run_command("git rev-list --count @{u}..HEAD")
            success2, behind = self.run_command("git rev-list --count HEAD..@{u}")
            
            if success and success2:
                ahead_count = int(ahead.strip()) if ahead.strip() else 0
                behind_count = int(behind.strip()) if behind.strip() else 0
                
                print(f"업스트림 브랜치: {upstream.strip()}")
                
                if ahead_count == 0 and behind_count == 0:
                    print("✅ 로컬과 원격이 동기화되어 있습니다.")
                else:
                    if ahead_count > 0:
                        print(f"⬆️  푸시되지 않은 커밋: {ahead_count}개")
                    if behind_count > 0:
                        print(f"⬇️  풀 받아야 할 커밋: {behind_count}개")
        else:
            print("업스트림 브랜치가 설정되지 않았습니다.")
    
    def run(self):
        """전체 상태 확인 실행"""
        print("🔍 Git 저장소 현황 확인")
        print("=" * 70)
        print(f"확인 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        if not self.check_git_repo():
            return
        
        self.show_user_info()
        self.show_repository_info()
        self.show_remote_info()
        self.show_status()
        self.show_file_statistics()
        self.show_uncommitted_changes()
        self.show_last_push_info()
        self.show_commit_history()
        
        print("\n" + "=" * 70)
        print("✨ Git 현황 확인 완료!")

def main():
    checker = GitStatusChecker()
    checker.run()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ 사용자가 작업을 중단했습니다.")
    except Exception as e:
        print(f"\n❌ 오류가 발생했습니다: {e}")