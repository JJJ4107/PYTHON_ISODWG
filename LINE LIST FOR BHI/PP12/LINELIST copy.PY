import fitz  # PyMuPDF
import csv
import os
import re
from collections import defaultdict
from tkinter import Tk, filedialog
from datetime import datetime

# ---------- 파일 다중 선택 ----------
root = Tk()
root.withdraw()
pdf_paths = filedialog.askopenfilenames(
    title="PDF 파일들을 선택하세요",
    filetypes=[("PDF files", "*.pdf")]
)
if not pdf_paths:
    print("PDF 파일이 선택되지 않았습니다.")
    exit()

# ---------- 사각형 박스 하이라이트 ----------
def highlight(page, rect, color, opacity=0.4):
    annot = page.add_rect_annot(rect)
    annot.set_colors(stroke=color, fill=color)
    annot.set_opacity(opacity)
    annot.update()

# ---------- 자연 정렬을 위한 키 생성 함수 ----------
def natural_key(text):
    return [int(s) if s.isdigit() else s.lower() for s in re.split(r'(\d+)', text)]

# ---------- 패턴 정의 ----------
valve_pattern = re.compile(r'AA[0-9]{3,4}', re.IGNORECASE)
special_pattern = re.compile(r'(AJ|BJ|AT)[0-9]{3,4}', re.IGNORECASE)

# ---------- PDF 처리 ----------
for input_pdf_path in pdf_paths:
    input_pdf_name = os.path.basename(input_pdf_path)
    base_name = os.path.splitext(input_pdf_name)[0]
    folder = os.path.dirname(input_pdf_path)

    today_str = datetime.now().strftime("%Y%m%d")

    line_csv = os.path.join(folder, f"LINE_{base_name}_{today_str}.CSV")
    valve_csv = os.path.join(folder, f"VALVE_{base_name}_{today_str}.CSV")
    special_csv = os.path.join(folder, f"SPECIAL_{base_name}_{today_str}.CSV")
    output_pdf = os.path.join(folder, f"OUT_{base_name}_{today_str}.PDF")
    dup_pdf = os.path.join(folder, f"DUP_{base_name}_{today_str}.PDF")
    dup_csv_path = os.path.join(folder, f"DUP_{base_name}_{today_str}.CSV")

    doc = fitz.open(input_pdf_path)    # OUT 용
    doc2 = fitz.open(input_pdf_path)   # DUP 용

    line_list, valve_list, special_list = [], [], []
    line_no_rects = defaultdict(list)
    valve_no_rects = defaultdict(list)
    special_no_rects = defaultdict(list)

    for page_num, page in enumerate(doc, 1):
        words = page.get_text("words")
        for word in words:
            x0, y0, x1, y1, text = word[:5]
            if not text.strip():
                continue

            p1 = text.strip().split()[0].upper()
            rect = fitz.Rect(x0, y0, x1, y1)
            is_p1 = False

            # ----- P1으로 인정되는 경우만 is_p1 = True -----
            if "BR" in p1 and "DN" in p1:
                dn_index = p1.find("DN")
                if dn_index != -1:
                    after_dn = p1[dn_index:].split()[0]
                    line_no = p1[:dn_index] + after_dn
                    line_list.append([line_no])
                    line_no_rects[line_no].append((page_num - 1, rect))
                    is_p1 = True
                    print(f"[{base_name}] LINE NO: {line_no}")
            elif valve_pattern.search(p1):
                valve_list.append([p1])
                valve_no_rects[p1].append((page_num - 1, rect))
                is_p1 = True
                print(f"[{base_name}] VALVE NO: {p1}")
            elif special_pattern.search(p1):
                special_list.append([p1])
                special_no_rects[p1].append((page_num - 1, rect))
                is_p1 = True
                print(f"[{base_name}] SPECIAL NO: {p1}")

            # OUT PDF는 위 조건에 해당(P1)하는 경우에만 하이라이트!
            if is_p1:
                highlight(page, rect, color=(0, 1, 0), opacity=0.2)

    # 중복 체크
    line_counts = defaultdict(int)
    for row in line_list:
        line_counts[row[0]] += 1
    line_list_dup = [row + ["중복" if line_counts[row[0]] > 1 else ""] for row in line_list]

    valve_counts = defaultdict(int)
    for row in valve_list:
        valve_counts[row[0]] += 1
    valve_list_dup = [row + ["중복" if valve_counts[row[0]] > 1 else ""] for row in valve_list]

    special_counts = defaultdict(int)
    for row in special_list:
        special_counts[row[0]] += 1
    special_list_dup = [row + ["중복" if special_counts[row[0]] > 1 else ""] for row in special_list]

    # CSV 저장
    with open(line_csv, "w", newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(["LINE NO", "중복"])
        writer.writerows(sorted(line_list_dup, key=lambda x: natural_key(x[0])))

    with open(valve_csv, "w", newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(["VALVE NO", "중복"])
        writer.writerows(sorted(valve_list_dup, key=lambda x: natural_key(x[0])))

    with open(special_csv, "w", newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(["SPECIAL NO", "중복"])
        writer.writerows(sorted(special_list_dup, key=lambda x: natural_key(x[0])))

    # 중복 항목만 병합하여 DUP CSV 저장
    dup_lines = [row for row in line_list_dup if row[1] == "중복"]
    dup_valves = [row for row in valve_list_dup if row[1] == "중복"]
    dup_specials = [row for row in special_list_dup if row[1] == "중복"]
    max_len = max(len(dup_lines), len(dup_valves), len(dup_specials))
    dup_lines += [["", ""]] * (max_len - len(dup_lines))
    dup_valves += [["", ""]] * (max_len - len(dup_valves))
    dup_specials += [["", ""]] * (max_len - len(dup_specials))

    with open(dup_csv_path, "w", newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(["LINE NO", "중복", "VALVE NO", "중복", "SPECIAL NO", "중복"])
        for i in range(max_len):
            writer.writerow(dup_lines[i] + dup_valves[i] + dup_specials[i])

    print(f"📁 중복 항목 저장 완료: {dup_csv_path}")

    # 중복 하이라이트 PDF (DUP)
    for key, rects in valve_no_rects.items():
        if valve_counts[key] > 1:
            for idx, (pg, rect) in enumerate(rects):
                page = doc2[pg]
                color = (0, 0, 1) if idx == 0 else (1, 0, 0)
                highlight(page, rect, color=color, opacity=0.4)

    for key, rects in line_no_rects.items():
        if line_counts[key] > 1:
            for idx, (pg, rect) in enumerate(rects):
                page = doc2[pg]
                color = (0, 0, 1) if idx == 0 else (1, 0, 0)
                highlight(page, rect, color=color, opacity=0.4)

    for key, rects in special_no_rects.items():
        if special_counts[key] > 1:
            for idx, (pg, rect) in enumerate(rects):
                page = doc2[pg]
                color = (0, 0, 1) if idx == 0 else (1, 0, 0)
                highlight(page, rect, color=color, opacity=0.4)

    doc2.save(dup_pdf)
    doc2.close()
    print(f"🎨 중복 하이라이트 저장 완료 → {dup_pdf}")

    # OUT PDF (P1만 하이라이트) 저장
    doc.save(output_pdf)
    doc.close()
    print(f"📄 기본 P1 하이라이트 저장 완료 → {output_pdf}\n")
