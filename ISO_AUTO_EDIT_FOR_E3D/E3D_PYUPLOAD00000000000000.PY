#!/usr/bin/env python3
"""
VSCode에서 현재 디렉토리의 모든 Python 파일을 Git에 업로드하는 스크립트
사용자: 장혁준
이메일: jj@aceplant.co.kr
"""

import os
import subprocess
import sys
from pathlib import Path
from datetime import datetime

class GitPythonUploader:
    def __init__(self, user_name="JJJ4107", user_email="jj@aceplant.co.kr"):
        self.user_name = user_name
        self.user_email = user_email
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
    
    def push_to_remote(self):
        """원격 저장소에 푸시 (선택적)"""
        # 원격 저장소가 설정되어 있는지 확인
        success, output = self.run_command("git remote -v")
        if not output.strip():
            print("\nℹ️  원격 저장소가 설정되어 있지 않습니다.")
            print("원격 저장소를 추가하려면 다음 명령어를 사용하세요:")
            print("git remote add origin <repository-url>")
            return False
        
        # 현재 브랜치 확인
        success, branch = self.run_command("git branch --show-current")
        if not success:
            branch = "main"  # 기본값
        else:
            branch = branch.strip()
        
        print(f"\n원격 저장소에 푸시하시겠습니까? (현재 브랜치: {branch})")
        response = input("푸시하려면 'y'를 입력하세요: ").lower()
        
        if response == 'y':
            success, output = self.run_command(f"git push -u origin {branch}")
            if success:
                print("✅ 원격 저장소에 푸시 완료!")
                return True
            else:
                print(f"❌ 푸시 실패: {output}")
                return False
        else:
            print("ℹ️  푸시를 건너뛰었습니다.")
            return True
    
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
    print("\n다른 사용자 정보를 사용하시려면 'n'을 입력하세요.")
    response = input("현재 정보를 사용하시겠습니까? (y/n): ").lower()
    
    if response == 'n':
        name = input("Git 사용자 이름을 입력하세요: ")
        email = input("Git 이메일을 입력하세요: ")
        uploader = GitPythonUploader(name, email)
    
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