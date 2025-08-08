import os
import re
import csv
from PyPDF2 import PdfReader

# TOTALLIST 초기화
total_list = []

# 현재 폴더의 모든 PDF 파일 검색
for filename in os.listdir('.'):
    if filename.lower().endswith('.pdf'):
        print(f"Processing file: {filename}")
        try:
            reader = PdfReader(filename)
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    # 먼저 10으로 분할
                    parts = text.split('10')
                    for part in parts:
                        if part.strip():  # 빈 문자열 제외
                            full_str = '10' + part.strip()
                            if 'DN' in full_str:
                                # 정규식으로 끝나는 자리 찾기 (최대 DN 다음까지 잘라주기 위해)
                                match = re.match(r'(10\S*?DN\d+)', full_str)
                                if match:
                                    total_list.append(match.group(1))
                                else:
                                    total_list.append(full_str)
        except Exception as e:
            print(f"Error reading {filename}: {e}")

# 중복 제거 및 정렬
total_list = sorted(set(total_list))

# 결과 출력
print("\n정렬된 결과:")
for item in total_list:
    print(item)

# 기존 LINELIST.CSV 삭제 (PermissionError 방지)
if os.path.exists('LINELIST.CSV'):
    os.remove('LINELIST.CSV')

# CSV 파일로 저장 (한 열씩 정확히 저장)
with open('LINELIST.CSV', 'w', newline='', encoding='utf-8-sig') as f:
    writer = csv.writer(f)
    for item in total_list:
        writer.writerow([item])

print("\nLINELIST.CSV 파일 저장 완료")
