#!/usr/bin/env python3
"""
VSCode에서 현재 디렉토리의 모든 Python 파일을 Git에 업로드하는 스크립트
기본 사용자: JJJ4107
기본 이메일: jj@aceplant.co.kr
기본 저장소: https://github.com/JJJ4107/PYTHON_ISODWG.git
"""

import os
import subprocess
import sys
from pathlib import Path
from datetime import datetime

class GitPythonUploader:
    def __init__(self, user_name="JJJ4107", user_email="jj@aceplant.co.kr", github_repo_url="https://github.com/JJJ4107/PYTHON_ISODWG.git"):
        self.user_name = user_name
        self.user_email = user_email
        self.github_repo_url = github_repo_url
        self.current_dir = Path.cwd()
        
    def run_command(self, command):
        """Git 명령어 실행"""
        try:
            result = subprocess.run(command, shell=True, capture_output=True, text=True)
            if result.returncode == 0:
                return True, result.stdout
            else:
                return False, result.stderr
        except Exception as e:
            return False, str(e)
    
    def check_git_installed(self):
        """Git 설치 확인"""
        success, _ = self.run_command("git --version")
        if not success:
            print("❌ Git이 설치되어 있지 않습니다. Git을 먼저 설치해주세요.")
            return False
        print("✅ Git이 설치되어 있습니다.")
        return True
    
    def init_git_repo(self):
        """Git 저장소 초기화"""
        if os.path.exists(os.path.join(self.current_dir, '.git')):
            print("✅ Git 저장소가 이미 초기화되어 있습니다.")
            return True
        
        success, output = self.run_command("git init")
        if success:
            print("✅ Git 저장소를 초기화했습니다.")
            return True
        else:
            print(f"❌ Git 저장소 초기화 실패: {output}")
            return False
    
    def configure_git_user(self):
        """Git 사용자 설정"""
        # 로컬 저장소에만 사용자 정보 설정
        commands = [
            f'git config user.name "{self.user_name}"',
            f'git config user.email "{self.user_email}"'
        ]
        
        for cmd in commands:
            success, output = self.run_command(cmd)
            if not success:
                print(f"❌ Git 사용자 설정 실패: {output}")
                return False
        
        print(f"✅ Git 사용자 설정 완료: {self.user_name} <{self.user_email}>")
        return True
    
    def find_python_files(self):
        """현재 디렉토리의 모든 Python 파일 찾기"""
        python_files = []
        
        # .git 폴더와 __pycache__ 폴더는 제외
        exclude_dirs = {'.git', '__pycache__', 'venv', '.venv', 'env', '.env'}
        
        for root, dirs, files in os.walk(self.current_dir):
            # 제외할 디렉토리 건너뛰기
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            
            for file in files:
                # 대소문자 구분 없이 .py 또는 .PY 확장자 확인
                if file.lower().endswith('.py'):
                    relative_path = os.path.relpath(os.path.join(root, file), self.current_dir)
                    python_files.append(relative_path)
        
        return python_files
    
    def add_files_to_git(self, files):
        """파일들을 Git에 추가"""
        if not files:
            print("❌ 추가할 Python 파일이 없습니다.")
            
            # 디버깅: 현재 디렉토리의 파일 목록 출력
            print("\n📁 현재 디렉토리의 파일 목록:")
            try:
                all_files = []
                for file in os.listdir(self.current_dir):
                    if os.path.isfile(os.path.join(self.current_dir, file)):
                        all_files.append(file)
                
                if all_files:
                    for file in all_files[:10]:  # 처음 10개만 표시
                        print(f"   - {file}")
                    if len(all_files) > 10:
                        print(f"   ... 그 외 {len(all_files) - 10}개 파일")
                else:
                    print("   파일이 없습니다.")
                    
                # Python처럼 보이는 파일 확인
                py_like_files = [f for f in all_files if 'py' in f.lower()]
                if py_like_files:
                    print(f"\n💡 Python과 유사한 파일명: {py_like_files[:5]}")
                    
            except Exception as e:
                print(f"   디렉토리 읽기 오류: {e}")
            
            return False
        
        print(f"\n📁 {len(files)}개의 Python 파일을 찾았습니다:")
        for file in files:
            print(f"   - {file}")
        
        # 파일들을 하나씩 추가
        for file in files:
            success, output = self.run_command(f'git add "{file}"')
            if not success:
                print(f"❌ 파일 추가 실패 ({file}): {output}")
                return False
        
        print(f"✅ {len(files)}개의 Python 파일을 Git에 추가했습니다.")
        return True
    
    def create_gitignore(self):
        """Python 프로젝트용 .gitignore 파일 생성"""
        gitignore_content = """# Byte-compiled / optimized / DLL files
__pycache__/
*.py[cod]
*$py.class

# C extensions
*.so

# Distribution / packaging
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# PyInstaller
*.manifest
*.spec

# Installer logs
pip-log.txt
pip-delete-this-directory.txt

# Unit test / coverage reports
htmlcov/
.tox/
.coverage
.coverage.*
.cache
nosetests.xml
coverage.xml
*.cover
.hypothesis/
.pytest_cache/

# Translations
*.mo
*.pot

# Django stuff:
*.log
local_settings.py
db.sqlite3

# Flask stuff:
instance/
.webassets-cache

# Scrapy stuff:
.scrapy

# Sphinx documentation
docs/_build/

# PyBuilder
target/

# Jupyter Notebook
.ipynb_checkpoints

# pyenv
.python-version

# celery beat schedule file
celerybeat-schedule

# SageMath parsed files
*.sage.py

# Environments
.env
.venv
env/
venv/
ENV/
env.bak/
venv.bak/

# Spyder project settings
.spyderproject
.spyproject

# Rope project settings
.ropeproject

# mkdocs documentation
/site

# mypy
.mypy_cache/
.dmypy.json
dmypy.json

# IDE
.idea/
.vscode/
*.swp
*.swo
*~

# OS
.DS_Store
Thumbs.db
"""
        
        gitignore_path = os.path.join(self.current_dir, '.gitignore')
        if not os.path.exists(gitignore_path):
            with open(gitignore_path, 'w', encoding='utf-8') as f:
                f.write(gitignore_content)
            print("✅ .gitignore 파일을 생성했습니다.")
            self.run_command("git add .gitignore")
    
    def commit_changes(self):
        """변경사항 커밋"""
        # 스테이징된 파일이 있는지 확인
        success, output = self.run_command("git status --porcelain")
        if not output.strip():
            print("ℹ️  커밋할 변경사항이 없습니다.")
            return True
        
        # 커밋 메시지 생성
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        commit_message = f"Add Python files - {timestamp}"
        
        success, output = self.run_command(f'git commit -m "{commit_message}"')
        if success:
            print(f"✅ 커밋 완료: {commit_message}")
            return True
        else:
            print(f"❌ 커밋 실패: {output}")
            return False
    
    def setup_github_remote(self):
        """GitHub 원격 저장소 설정"""
        print("\n🔧 GitHub 원격 저장소 설정")
        print("GitHub 저장소 URL 형식:")
        print("  - HTTPS: https://github.com/사용자명/저장소명.git")
        print("  - SSH: git@github.com:사용자명/저장소명.git")
        
        # 기본 URL이 있으면 표시
        if self.github_repo_url:
            print(f"\n기본 저장소: {self.github_repo_url}")
            use_default = input("기본 저장소를 사용하시겠습니까? (y/n): ").lower()
            if use_default == 'y':
                github_url = self.github_repo_url
            else:
                github_url = input("GitHub 저장소 URL을 입력하세요: ").strip()
        else:
            github_url = input("\nGitHub 저장소 URL을 입력하세요 (엔터를 누르면 건너뛰기): ").strip()
        
        if github_url:
            # 기존 origin이 있는지 확인
            success, output = self.run_command("git remote get-url origin")
            if success:
                print(f"기존 원격 저장소: {output.strip()}")
                response = input("기존 설정을 덮어쓰시겠습니까? (y/n): ").lower()
                if response == 'y':
                    self.run_command("git remote remove origin")
                else:
                    return False
            
            # 새 원격 저장소 추가
            success, output = self.run_command(f"git remote add origin {github_url}")
            if success:
                print("✅ GitHub 원격 저장소가 설정되었습니다.")
                return True
            else:
                print(f"❌ 원격 저장소 설정 실패: {output}")
                return False
        
        return False
    
    def push_to_remote(self):
        """원격 저장소에 푸시 (선택적)"""
        # 원격 저장소가 설정되어 있는지 확인
        success, output = self.run_command("git remote -v")
        if not output.strip():
            print("\nℹ️  원격 저장소가 설정되어 있지 않습니다.")
            
            # 자동으로 GitHub 저장소 설정
            if self.github_repo_url:
                print(f"🔧 GitHub 저장소를 자동으로 설정합니다: {self.github_repo_url}")
                success, output = self.run_command(f"git remote add origin {self.github_repo_url}")
                if success:
                    print("✅ GitHub 원격 저장소가 설정되었습니다.")
                else:
                    print(f"❌ 원격 저장소 설정 실패: {output}")
                    return False
            else:
                # GitHub 설정 제안
                response = input("GitHub 저장소를 설정하시겠습니까? (y/n): ").lower()
                if response == 'y':
                    if not self.setup_github_remote():
                        return False
                else:
                    return True
        
        # 현재 브랜치 확인
        success, branch = self.run_command("git branch --show-current")
        if not success or not branch.strip():
            # 브랜치가 없으면 main으로 생성
            self.run_command("git checkout -b main")
            branch = "main"
        else:
            branch = branch.strip()
        
        print(f"\n📤 원격 저장소에 푸시 준비 (브랜치: {branch})")
        
        # 원격 저장소 정보 표시
        print("현재 설정된 원격 저장소:")
        self.run_command("git remote -v")
        
        response = input("\n푸시하시겠습니까? (y/n): ").lower()
        
        if response == 'y':
            # 첫 푸시인지 확인
            success, _ = self.run_command(f"git ls-remote origin {branch}")
            
            if not success:
                # 첫 푸시인 경우
                print("🚀 첫 번째 푸시를 진행합니다...")
                push_cmd = f"git push -u origin {branch}"
            else:
                # 기존 브랜치가 있는 경우
                push_cmd = f"git push origin {branch}"
            
            success, output = self.run_command(push_cmd)
            if success:
                print("✅ GitHub에 푸시 완료!")
                print(f"🌐 브라우저에서 확인: {self.get_github_url()}")
                return True
            else:
                if "authentication" in output.lower() or "permission" in output.lower():
                    print("\n❌ 인증 실패! GitHub 인증 설정이 필요합니다.")
                    print("\n📝 GitHub 인증 방법:")
                    print("1. Personal Access Token 사용 (권장):")
                    print("   - GitHub Settings > Developer settings > Personal access tokens")
                    print("   - 'Generate new token' 클릭")
                    print("   - 'repo' 권한 체크")
                    print("   - 생성된 토큰을 비밀번호 대신 사용")
                    print("\n2. SSH 키 설정:")
                    print("   - ssh-keygen -t ed25519 -C \"your_email@example.com\"")
                    print("   - GitHub Settings > SSH and GPG keys에 공개키 추가")
                elif "rejected" in output.lower():
                    print("\n❌ 푸시가 거부되었습니다. 원격 저장소에 변경사항이 있을 수 있습니다.")
                    print("다음 명령어로 원격 변경사항을 가져온 후 다시 시도하세요:")
                    print(f"git pull origin {branch}")
                else:
                    print(f"❌ 푸시 실패: {output}")
                return False
        else:
            print("ℹ️  푸시를 건너뛰었습니다.")
            return True
    
    def get_github_url(self):
        """GitHub 저장소 웹 URL 추출"""
        # 먼저 인스턴스 변수에서 확인
        if self.github_repo_url:
            url = self.github_repo_url
            # .git 제거
            if url.endswith(".git"):
                return url[:-4]
            return url
        
        # 원격 저장소에서 확인
        success, output = self.run_command("git remote get-url origin")
        if success and output:
            url = output.strip()
            # SSH URL을 HTTPS URL로 변환
            if url.startswith("git@github.com:"):
                url = url.replace("git@github.com:", "https://github.com/")
            # .git 제거
            if url.endswith(".git"):
                url = url[:-4]
            return url
        return ""
    
    def run(self):
        """전체 프로세스 실행"""
        print("🚀 Python 파일 Git 업로드 스크립트 시작")
        print(f"📂 작업 디렉토리: {self.current_dir}\n")
        
        # 1. Git 설치 확인
        if not self.check_git_installed():
            return
        
        # 2. Git 저장소 초기화
        if not self.init_git_repo():
            return
        
        # 3. Git 사용자 설정
        if not self.configure_git_user():
            return
        
        # 4. .gitignore 파일 생성
        self.create_gitignore()
        
        # 5. Python 파일 찾기
        python_files = self.find_python_files()
        
        # 6. 파일들을 Git에 추가
        if not self.add_files_to_git(python_files):
            return
        
        # 7. 커밋
        if not self.commit_changes():
            return
        
        # 8. 푸시 (선택적)
        self.push_to_remote()
        
        print("\n✨ 작업이 완료되었습니다!")

def main():
    """메인 함수"""
    uploader = GitPythonUploader()
    
    # 사용자 정보 확인
    print("현재 설정된 사용자 정보:")
    print(f"이름: {uploader.user_name}")
    print(f"이메일: {uploader.user_email}")
    print(f"GitHub 저장소: {uploader.github_repo_url}")
    print("\n다른 사용자 정보를 사용하시려면 'n'을 입력하세요.")
    response = input("현재 정보를 사용하시겠습니까? (y/n): ").lower()
    
    if response == 'n':
        name = input("Git 사용자 이름을 입력하세요: ")
        email = input("Git 이메일을 입력하세요: ")
        repo_url = input("GitHub 저장소 URL을 입력하세요 (선택사항, 엔터로 건너뛰기): ").strip()
        uploader = GitPythonUploader(name, email, repo_url if repo_url else None)
    
    print()
    uploader.run()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ 사용자가 작업을 중단했습니다.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 오류가 발생했습니다: {e}")
        sys.exit(1)