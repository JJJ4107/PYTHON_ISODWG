import csv
import fitz  # PyMuPDF
import os
import subprocess
import shutil

# === 설정 ===
csv_file = 'VALVELIST.CSV'
original_pdf_file = 'PID.PDF'
temp_copied_pdf = 'TEMP_WORKING.PDF'
sumatra_path = r"C:\Users\acepl\AppData\Local\SumatraPDF\SumatraPDF.exe"
log_file = 'search_log.txt'
temp_current_pdf = 'CURRENT_OUTPUT.PDF'

# === Crop 영역 설정 ===
crop_width = 450
crop_height = 400

# === 파일 존재 확인 ===
for file in [csv_file, original_pdf_file, sumatra_path]:
    if not os.path.exists(file):
        print(f"필수 파일이 존재하지 않습니다: {file}")
        exit()

# 원본 PDF 복사 (원본 보호)
shutil.copyfile(original_pdf_file, temp_copied_pdf)

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
        print(f"\n[{count}] VNAME 검색: {vname}")

        try:
            src_doc = fitz.open(temp_copied_pdf)
        except Exception as e:
            print(f"PDF 열기 실패: {e}")
            continue

        found = False

        for i, page in enumerate(src_doc):
            text_instances = page.search_for(vname)
            if text_instances:
                found = True
                first_rect = text_instances[0]
                center_x = (first_rect.x0 + first_rect.x1) / 2
                center_y = (first_rect.y0 + first_rect.y1) / 2

                crop_rect = fitz.Rect(
                    center_x - crop_width / 2,
                    center_y - crop_height / 2,
                    center_x + crop_width / 2,
                    center_y + crop_height / 2
                )

                # 페이지 추출 및 크롭
                page_pdf = fitz.open()
                page_pdf.insert_pdf(src_doc, from_page=i, to_page=i)

                new_doc = fitz.open()
                new_page = new_doc.new_page(width=crop_width, height=crop_height)
                new_page.show_pdf_page(new_page.rect, page_pdf, 0, clip=crop_rect)

                # 하이라이트 위치 보정
                offset_x, offset_y = crop_rect.x0, crop_rect.y0

                adjusted_rect = fitz.Rect(
                    (first_rect.x0 - offset_x),
                    (first_rect.y0 - offset_y),
                    (first_rect.x1 - offset_x),
                    (first_rect.y1 - offset_y)
                )

                highlight = new_page.add_highlight_annot(adjusted_rect)
                highlight.update()

                new_doc.save(temp_current_pdf)
                new_doc.close()
                page_pdf.close()
                break

        src_doc.close()

        with open(log_file, 'a', encoding='utf-8') as log:
            if found:
                log.write(f"[{count}] {vname} → FOUND\n")
            else:
                log.write(f"[{count}] {vname} → NOT FOUND\n")

        # SumatraPDF로 보여주기 (2배 확대 적용)
        if found:
            subprocess.Popen([
                sumatra_path, "-reuse-instance", "-zoom", "200", os.path.abspath(temp_current_pdf)
            ], shell=False)

        input("→ 엔터를 누르면 다음 검색으로 넘어갑니다...")
        count += 1

# 임시파일 정리
for temp_file in [temp_copied_pdf, temp_current_pdf]:
    try:
        os.remove(temp_file)
    except:
        pass

print("\n🎯 모든 검색이 완료되었습니다. 프로그램 종료.")
