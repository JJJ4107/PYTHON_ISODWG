import csv
import fitz  # PyMuPDF
import os
import subprocess
import time

# === 설정 ===
csv_file = 'VALVELIST.CSV'
original_pdf_file = 'PID.PDF'
sumatra_path = r"C:\Program Files\SumatraPDF\SumatraPDF.exe"
log_file = 'search_log.txt'
temp_current_pdf = 'CURRENT_OUTPUT.PDF'

# 파일 확인
for file in [csv_file, original_pdf_file, sumatra_path]:
    if not os.path.exists(file):
        print(f"❌ 필수 파일이 존재하지 않습니다: {file}")
        exit()

# 로그 초기화
with open(log_file, 'w', encoding='utf-8') as log:
    log.write("검색결과 로그\n\n")

# CSV 파일 읽기
with open(csv_file, 'r', newline='', encoding='utf-8-sig') as file:
    reader = csv.reader(file)
    count = 1

    for row in reader:
        if not row or not row[0].strip():
            continue

        vname = row[0].strip()
        print(f"\n[{count}] VNAME 검색 시작: {vname}")

        src_doc = fitz.open(original_pdf_file)
        found = False

        for i, page in enumerate(src_doc):
            text_instances = page.search_for(vname)
            if text_instances:
                found = True
                first_rect = text_instances[0]

                # 원본 페이지를 통째로 복사
                new_doc = fitz.open()
                new_doc.insert_pdf(src_doc, from_page=i, to_page=i)
                copied_page = new_doc[0]

                # 하이라이트 추가
                copied_page.add_highlight_annot(first_rect)

                new_doc.save(temp_current_pdf, garbage=4, deflate=True)
                new_doc.close()
                break

        src_doc.close()

        with open(log_file, 'a', encoding='utf-8') as log:
            if found:
                log.write(f"[{count}] {vname} → FOUND\n")
            else:
                log.write(f"[{count}] {vname} → NOT FOUND\n")

        if found:
            try:
                subprocess.Popen([
                    sumatra_path, "-reuse-instance", "-zoom", "200", os.path.abspath(temp_current_pdf)
                ], shell=False)
                time.sleep(0.5)
            except Exception as e:
                print(f"❌ SumatraPDF 실행 실패: {e}")

        input("→ 엔터를 누르면 다음 검색으로 넘어갑니다...")
        count += 1

print("\n🎯 모든 검색이 완료되었습니다. 프로그램 정상 종료.")
