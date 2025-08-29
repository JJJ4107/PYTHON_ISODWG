import os
import subprocess
import glob
from pathlib import Path
import sys

class GitPythonManager:
    def __init__(self, username="장혁준", email="jj@aceplant.co.kr"):
        self.username = username
        self.email = email
        self.current_dir = os.getcwd()
        
    def setup_git_user(self):
        """Git 사용자 정보 설정"""
        try:
            # Git 사용자 이름 설정
            result = subprocess.run(['git', 'config', '--global', 'user.name', self.username], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                print(f"✓ Git 사용자 이름 설정 완료: {self.username}")
            else:
                print(f"⚠️  Git 사용자 이름 설정 중 경고: {result.stderr}")
            
            # Git 사용자 이메일 설정
            result = subprocess.run(['git', 'config', '--global', 'user.email', self.email], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                print(f"✓ Git 사용자 이메일 설정 완료: {self.email}")
            else:
                print(f"⚠️  Git 사용자 이메일 설정 중 경고: {result.stderr}")
            
            # 설정 확인
            name_result = subprocess.run(['git', 'config', '--global', 'user.name'], 
                                       capture_output=True, text=True)
            email_result = subprocess.run(['git', 'config', '--global', 'user.email'], 
                                        capture_output=True, text=True)
            
            print(f"\n현재 Git 설정:")
            
            # stdout이 None이 아닌지 확인
            if name_result.stdout:
                print(f"  - 사용자: {name_result.stdout.strip()}")
            else:
                print(f"  - 사용자: 설정되지 않음")
                
            if email_result.stdout:
                print(f"  - 이메일: {email_result.stdout.strip()}")
            else:
                print(f"  - 이메일: 설정되지 않음")
            
        except FileNotFoundError:
            print("❌ Git이 설치되어 있지 않습니다.")
            print("   Git을 먼저 설치해주세요: https://git-scm.com/downloads")
            return False
        except Exception as e:
            print(f"❌ Git 설정 오류: {e}")
            return False
        return True
    
    def list_python_files(self):
        """현재 디렉토리와 하위 디렉토리의 모든 Python 파일 목록 작성"""
        print(f"\n📁 현재 위치: {self.current_dir}")
        print("Python 파일 목록:")
        print("-" * 50)
        
        python_files = []
        
        try:
            # glob을 사용하여 재귀적으로 Python 파일 찾기
            for file_path in glob.glob('**/*.py', recursive=True):
                try:
                    file_size = os.path.getsize(file_path)
                    python_files.append(file_path)
                    print(f"  📄 {file_path} ({file_size:,} bytes)")
                except OSError:
                    print(f"  ⚠️  {file_path} (크기를 읽을 수 없음)")
                    python_files.append(file_path)
            
            if not python_files:
                print("  ⚠️  Python 파일을 찾을 수 없습니다.")
            else:
                print(f"\n총 {len(python_files)}개의 Python 파일을 찾았습니다.")
                
        except Exception as e:
            print(f"❌ 파일 검색 중 오류 발생: {e}")
            
        return python_files
    
    def check_git_status(self):
        """현재 디렉토리의 Git 상태 확인"""
        try:
            result = subprocess.run(['git', 'status'], 
                                  capture_output=True, text=True)
            return result.returncode == 0
        except FileNotFoundError:
            print("❌ Git이 설치되어 있지 않습니다.")
            return False
        except Exception:
            return False
    
    def git_clone(self, repo_url, directory=None):
        """Git 저장소 클론"""
        try:
            print(f"📥 저장소 클론 중: {repo_url}")
            
            if directory:
                result = subprocess.run(['git', 'clone', repo_url, directory], 
                                      capture_output=True, text=True)
                if result.returncode == 0:
                    print(f"✓ 저장소를 {directory}에 클론했습니다.")
                else:
                    print(f"❌ 클론 실패: {result.stderr}")
                    return False
            else:
                result = subprocess.run(['git', 'clone', repo_url], 
                                      capture_output=True, text=True)
                if result.returncode == 0:
                    print(f"✓ 저장소를 클론했습니다.")
                else:
                    print(f"❌ 클론 실패: {result.stderr}")
                    return False
            return True
            
        except FileNotFoundError:
            print("❌ Git이 설치되어 있지 않습니다.")
            return False
        except Exception as e:
            print(f"❌ 클론 중 오류 발생: {e}")
            return False
    
    def git_pull(self):
        """현재 디렉토리에서 Git pull 실행"""
        if not self.check_git_status():
            print("❌ 현재 디렉토리는 Git 저장소가 아닙니다.")
            return False
        
        try:
            # 현재 브랜치 확인
            branch_result = subprocess.run(['git', 'branch', '--show-current'], 
                                         capture_output=True, text=True)
            if branch_result.returncode == 0 and branch_result.stdout:
                current_branch = branch_result.stdout.strip()
                print(f"🌿 현재 브랜치: {current_branch}")
            else:
                print("🌿 현재 브랜치를 확인할 수 없습니다.")
            
            # Git pull 실행
            print("📥 Git pull 실행 중...")
            pull_result = subprocess.run(['git', 'pull'], 
                                       capture_output=True, text=True)
            
            if pull_result.returncode == 0:
                if pull_result.stdout and "Already up to date" in pull_result.stdout:
                    print("✓ 이미 최신 상태입니다.")
                else:
                    print("✓ 업데이트를 완료했습니다.")
                    if pull_result.stdout:
                        print(pull_result.stdout)
            else:
                print(f"❌ Pull 실패: {pull_result.stderr}")
                return False
                
            return True
            
        except FileNotFoundError:
            print("❌ Git이 설치되어 있지 않습니다.")
            return False
        except Exception as e:
            print(f"❌ Pull 중 오류 발생: {e}")
            return False
    
    def git_fetch(self):
        """원격 저장소의 변경사항 가져오기 (병합하지 않음)"""
        if not self.check_git_status():
            print("❌ 현재 디렉토리는 Git 저장소가 아닙니다.")
            return False
        
        try:
            print("📡 Git fetch 실행 중...")
            result = subprocess.run(['git', 'fetch'], capture_output=True, text=True)
            
            if result.returncode == 0:
                print("✓ 원격 저장소의 변경사항을 가져왔습니다.")
                
                # 로컬과 원격의 차이 확인
                status_result = subprocess.run(['git', 'status', '-uno'], 
                                             capture_output=True, text=True)
                if status_result.stdout:
                    if "Your branch is behind" in status_result.stdout:
                        print("ℹ️  로컬 브랜치가 원격 브랜치보다 뒤처져 있습니다.")
                        print("   'git pull'을 실행하여 변경사항을 병합할 수 있습니다.")
                    elif "Your branch is ahead" in status_result.stdout:
                        print("ℹ️  로컬 브랜치가 원격 브랜치보다 앞서 있습니다.")
                    else:
                        print("✓ 로컬과 원격이 동기화되어 있습니다.")
            else:
                print(f"❌ Fetch 실패: {result.stderr}")
                return False
                
            return True
            
        except FileNotFoundError:
            print("❌ Git이 설치되어 있지 않습니다.")
            return False
        except Exception as e:
            print(f"❌ Fetch 중 오류 발생: {e}")
            return False


def main():
    """메인 실행 함수"""
    manager = GitPythonManager()
    
    print("=== Git 및 Python 파일 관리 도구 ===\n")
    
    # 1. Git 사용자 설정
    print("1️⃣ Git 사용자 설정")
    manager.setup_git_user()
    
    # 2. Python 파일 목록 작성
    print("\n2️⃣ Python 파일 목록 작성")
    python_files = manager.list_python_files()
    
    # 3. Git 작업 선택
    print("\n3️⃣ Git 작업")
    
    if manager.check_git_status():
        print("✓ 현재 디렉토리는 Git 저장소입니다.")
        print("\n작업을 선택하세요:")
        print("1. Git Pull (변경사항 다운로드 및 병합)")
        print("2. Git Fetch (변경사항 확인만)")
        print("3. 새 저장소 클론")
        print("4. 종료")
        
        try:
            choice = input("\n선택 (1-4): ").strip()
            
            if choice == '1':
                manager.git_pull()
            elif choice == '2':
                manager.git_fetch()
            elif choice == '3':
                repo_url = input("저장소 URL을 입력하세요: ").strip()
                if repo_url:
                    manager.git_clone(repo_url)
                else:
                    print("⚠️  URL이 입력되지 않았습니다.")
            elif choice == '4':
                print("프로그램을 종료합니다.")
            else:
                print("잘못된 선택입니다.")
        except KeyboardInterrupt:
            print("\n\n프로그램을 중단합니다.")
    else:
        print("⚠️  현재 디렉토리는 Git 저장소가 아닙니다.")
        print("\n작업을 선택하세요:")
        print("1. 새 저장소 클론")
        print("2. 현재 디렉토리를 Git 저장소로 초기화")
        print("3. 종료")
        
        try:
            choice = input("\n선택 (1-3): ").strip()
            
            if choice == '1':
                repo_url = input("저장소 URL을 입력하세요: ").strip()
                if repo_url:
                    directory = input("클론할 디렉토리 이름 (비워두면 기본값): ").strip()
                    manager.git_clone(repo_url, directory if directory else None)
                else:
                    print("⚠️  URL이 입력되지 않았습니다.")
            elif choice == '2':
                try:
                    result = subprocess.run(['git', 'init'], capture_output=True, text=True)
                    if result.returncode == 0:
                        print("✓ Git 저장소를 초기화했습니다.")
                    else:
                        print(f"❌ Git 초기화 실패: {result.stderr}")
                except FileNotFoundError:
                    print("❌ Git이 설치되어 있지 않습니다.")
                except Exception as e:
                    print(f"❌ 초기화 중 오류 발생: {e}")
            elif choice == '3':
                print("프로그램을 종료합니다.")
            else:
                print("잘못된 선택입니다.")
        except KeyboardInterrupt:
            print("\n\n프로그램을 중단합니다.")


if __name__ == "__main__":
    # Git이 설치되어 있는지 확인
    try:
        result = subprocess.run(['git', '--version'], capture_output=True, text=True)
        if result.returncode != 0:
            print("❌ Git이 제대로 작동하지 않습니다.")
            print("   Git을 다시 설치해주세요: https://git-scm.com/downloads")
            sys.exit(1)
        else:
            print(f"✓ Git 버전: {result.stdout.strip()}")
    except FileNotFoundError:
        print("❌ Git이 설치되어 있지 않습니다.")
        print("   Git을 먼저 설치해주세요: https://git-scm.com/downloads")
        print("\n   Windows: https://git-scm.com/download/win")
        print("   설치 후 VSCode를 재시작해주세요.")
        sys.exit(1)
    
    main()