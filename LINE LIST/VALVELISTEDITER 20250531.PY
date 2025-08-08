import csv
import fitz
import os
import subprocess
import time
import shutil

# 파일 경로 설정
csv_file = 'VALVELIST.CSV'
original_pdf_file = 'PID.PDF'
output_folder = 'PDF_OUTPUT'
temp_copied_pdf = 'TEMP_WORKING.PDF'
sumatra_path = r"C:\Users\acepl\AppData\Local\SumatraPDF\SumatraPDF.exe"

# 출력 폴더 준비
if not os.path.exists(output_folder):
    os.makedirs(output_folder)

# 파일 확인
if not os.path.exists(csv_file) or not os.path.exists(original_pdf_file):
    print("CSV 또는 PDF 파일이 존재하지 않습니다.")
    exit()

if not os.path.exists(sumatra_path):
    print("SumatraPDF 실행 파일이 존재하지 않습니다.")
    exit()

# 매 검색마다 TEMP 복사본 사용 (원본 보호)
shutil.copyfile(original_pdf_file, temp_copied_pdf)

# Crop 영역 설정
crop_width = 1000
crop_height = 800

with open(csv_file, 'r', newline='', encoding='utf-8-sig') as file:
    reader = csv.reader(file)
    count = 1

    for row in reader:
        if not row:
            continue

        vname = row[0].strip()
        if not vname:
            continue

        print(f"\n[{count}] VNAME 검색: {vname}")

        src_doc = fitz.open(temp_copied_pdf)
        found = False

        for i in range(src_doc.page_count):
            page = src_doc.load_page(i)
            text_instances = page.search_for(vname)
            if text_instances:
                found = True

                first_rect = text_instances[0]

                center_x = (first_rect.x0 + first_rect.x1) / 2
                center_y = (first_rect.y0 + first_rect.y1) / 2

                crop_rect = fitz.Rect(
                    center_x - crop_width/2,
                    center_y - crop_height/2,
                    center_x + crop_width/2,
                    center_y + crop_height/2
                )

                # 원본 페이지에서 해당 페이지만 추출
                page_pdf = fitz.open()
                page_pdf.insert_pdf(src_doc, from_page=i, to_page=i)
                src_doc.close()

                # 새 crop PDF 생성
                new_doc = fitz.open()
                new_page = new_doc.new_page(width=crop_width, height=crop_height)
                new_page.show_pdf_page(new_page.rect, page_pdf, 0, clip=crop_rect)

                # 좌표 보정: offset + scale 적용 (완전 정밀 보정)
                scale_x = crop_width / crop_rect.width
                scale_y = crop_height / crop_rect.height
                offset_x = crop_rect.x0
                offset_y = crop_rect.y0

                adjusted_rect = fitz.Rect(
                    (first_rect.x0 - offset_x) * scale_x,
                    (first_rect.y0 - offset_y) * scale_y,
                    (first_rect.x1 - offset_x) * scale_x,
                    (first_rect.y1 - offset_y) * scale_y
                )

                highlight = new_page.add_highlight_annot(adjusted_rect)
                highlight.update()

                # 새 PDF 저장
                output_pdf = os.path.join(output_folder, f"VNAME_{count}.pdf")
                new_doc.save(output_pdf)
                new_doc.close()
                page_pdf.close()

                break

        else:
            src_doc.close()

        if not found:
            print("  - 검색결과 없음.")
            input("엔터를 누르면 다음으로 넘어갑니다...")
            count += 1
            continue

        # SumatraPDF에 해당 crop된 새 PDF를 오픈
        subprocess.Popen([
            sumatra_path,
            "-reuse-instance",
            os.path.abspath(output_pdf)
        ], shell=False)

        time.sleep(1)
        input("엔터를 누르면 다음 검색으로 넘어갑니다...")
        count += 1

print("\n🎯 모든 검색 및 하이라이트 완료되었습니다.")
