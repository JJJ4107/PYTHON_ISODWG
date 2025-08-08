import os
import re
import csv
import fitz  # PyMuPDF

def extract_valves_from_pdf(file_path):
    doc = fitz.open(file_path)
    valves = []

    for page in doc:
        text = page.get_text()
        lines = text.split('\n')

        for line in lines:
            line = line.strip()

            # 1단계: '10' 또는 '11' 로 시작하는지 확인
            if not (line.startswith('10') or line.startswith('11')):
                continue

            # 2단계: 'AA' 가 포함되어야 함
            if 'AA' not in line:
                continue

            # 3단계: 'DN' 이 포함되어 있으면 skip
            if 'DN' in line:
                continue

            # 4단계: 라인을 공백 기준으로 나눠서 각각을 VALVE로 간주
            parts = line.split()

            for part in parts:
                part = part.strip()
                if part:  # 빈 문자열 제외
                    valves.append(part)

    return valves

def main():
    all_valves = []

    for filename in os.listdir('.'):
        if filename.lower().endswith('.pdf'):
            print(f"처리중: {filename}")
            valves = extract_valves_from_pdf(filename)
            all_valves.extend(valves)

    # 중복 제거 및 정렬
    unique_valves = sorted(set(all_valves))

    # 결과 출력
    print("추출된 VALVE 목록:")
    for valve in unique_valves:
        print(valve)

    # CSV 저장
    with open('VALVELIST.CSV', 'w', newline='', encoding='utf-8-sig') as csvfile:
        writer = csv.writer(csvfile)
        for valve in unique_valves:
            writer.writerow([valve])

    print("VALVELIST.CSV 파일이 생성되었습니다.")

if __name__ == "__main__":
    main()
