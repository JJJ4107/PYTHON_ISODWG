import csv
import fitz  # PyMuPDF
import os
import subprocess
import shutil

# === 설정 ===
csv_file = 'LINELIST.CSV'
original_pdf_file = 'PID.PDF'
temp_copied_pdf = 'TEMP_WORKING.PDF'
sumatra_path = r"C:\Program Files\SumatraPDF\SumatraPDF.exe"
log_file = 'search_log.txt'
temp_current_pdf = 'CURRENT_OUTPUT.PDF'

# === 파일 존재 확인 ===
for file in [csv_file, original_pdf_file, sumatra_path]:
    if not os.path.exists(file):
        print(f"❌ 필수 파일이 존재하지 않습니다: {file}")
        exit()

# 원본 PDF 복사 (원본 보호)
shutil.copyfile(original_pdf_file, temp_copied_pdf)

# 로그 초기화
with open(log_file, 'w', encoding='utf-8') as log:
    log.write("🔎 검색결과 로그\n\n")

# CSV 파일 읽기
with open(csv_file, 'r', newline='', encoding='utf-8-sig') as file:
    reader = csv.reader(file)
    count = 1

    for row in reader:
        if not row or not row[0].strip():
            continue

        vname = row[0].strip()
        print(f"\n[{count}] VNAME 검색: {vname}")

        try:
            with fitz.open(temp_copied_pdf) as src_doc:
                found = False

                for i, page in enumerate(src_doc):
                    text_instances = page.search_for(vname)
                    if text_instances:
                        found = True

                        # 새 문서 생성 (해당 페이지 전체 복사)
                        new_doc = fitz.open()
                        new_doc.insert_pdf(src_doc, from_page=i, to_page=i)

                        # 하이라이트 추가
                        new_page = new_doc[0]
                        for rect in text_instances:
                            highlight = new_page.add_highlight_annot(rect)
                            highlight.update()

                        new_doc.save(temp_current_pdf)
                        new_doc.close()
                        break

            # 로그 기록
            with open(log_file, 'a', encoding='utf-8') as log:
                if found:
                    log.write(f"[{count}] {vname} → ✅ FOUND\n")
                else:
                    log.write(f"[{count}] {vname} → ❌ NOT FOUND\n")

            # SumatraPDF로 보여주기 (확대 없이 기본으로)
            if found:
                subprocess.Popen([
                    sumatra_path, "-reuse-instance", os.path.abspath(temp_current_pdf)
                ], shell=False)

            input("→ 엔터를 누르면 다음 검색으로 넘어갑니다...")

        except Exception as e:
            print(f"‼ 오류 발생: {e}")

        count += 1

# 임시파일 정리
for temp_file in [temp_copied_pdf, temp_current_pdf]:
    try:
        os.remove(temp_file)
    except:
        pass

print("\n🎯 모든 검색이 완료되었습니다. 프로그램 종료.")
