import os
import re
import csv
import fitz  # PyMuPDF

# PDF 내에서 추출할 패턴 정의
DN_PATTERN = re.compile(r'^(10|11).*DN.*', re.IGNORECASE)
SIZE_PATTERN = re.compile(r'DN\s*(\d+)', re.IGNORECASE)
SPEC_PATTERN = re.compile(r'[A-Za-z]+')  # 문자만 추출 (SPEC용)

# 결과 저장용 dict (LINE 기준으로 중복 제거)
result_dict = dict()

# 현재 폴더의 PDF 파일 목록 가져오기
pdf_files = [f for f in os.listdir('.') if f.lower().endswith('.pdf')]

for pdf_file in pdf_files:
    print(f"Processing file: {pdf_file}")
    doc = fitz.open(pdf_file)
    
    for page in doc:
        text = page.get_text()
        lines = text.split('\n')
        
        for line in lines:
            line = line.strip()

            if not line:
                continue  # 빈 줄 skip

            if 'AA' in line:
                continue  # AA 포함되면 skip
            
            if DN_PATTERN.match(line):
                dn_match = SIZE_PATTERN.search(line)
                if dn_match:
                    size_value = int(dn_match.group(1))
                    clean_line = line
                    result_dict[clean_line] = size_value

    doc.close()

# 결과 분리 및 정렬
upper_list = []
lower_list = []

for item in result_dict.items():
    if item[1] >= 51:
        upper_list.append(item)
    else:
        lower_list.append(item)

# 각각 알파벳 기준으로 추가 정렬
upper_list = sorted(upper_list, key=lambda x: (x[1], x[0]))  # SIZE, LIST 기준 정렬
lower_list = sorted(lower_list, key=lambda x: (x[1], x[0]))

# 최종 리스트: upper 먼저, 빈줄, lower 순서
final_list = upper_list + [('', '')] + lower_list

# 화면 출력
print("\n추출된 LIST (분리 정렬 완료):")
for item in final_list:
    if item[0] == '':
        print('')  # 빈칸 출력
    else:
        print(item[0])

# CSV 파일 저장 (LIST, SIZE, SPEC 컬럼으로 확장)
with open('LINELIST.CSV', 'w', newline='', encoding='utf-8-sig') as csvfile:
    writer = csv.writer(csvfile)
    writer.writerow(['LIST', 'SIZE', 'SPEC'])  # 헤더 작성

    for item in final_list:
        list_value = item[0]
        size_value = item[1]

        if list_value == '':
            writer.writerow([])  # 빈 줄 추가
            continue

        # '-' 로 분리
        parts = list_value.split('-')
        list1 = parts[0] if len(parts) > 0 else ''
        list2 = parts[1] if len(parts) > 1 else ''
        list3 = parts[2] if len(parts) > 2 else ''
        list4 = parts[3] if len(parts) > 3 else ''

        # LIST1에서 문자만 추출하여 SPEC 지정
        spec_match = re.findall(r'[A-Za-z]+', list1)
        spec = ''.join(spec_match)

        writer.writerow([list_value, size_value, spec])

print("\nLINELIST.CSV 파일 생성 완료.")
