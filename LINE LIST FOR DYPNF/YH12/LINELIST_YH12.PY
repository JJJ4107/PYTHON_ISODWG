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

# ---------- 하이라이트 함수 ----------
def highlight(page, rect, color, opacity=0.4):
    annot = page.add_rect_annot(rect)
    annot.set_colors(stroke=color, fill=color)
    annot.set_opacity(opacity)
    annot.update()

# ---------- 자연 정렬 ----------
def natural_key(text):
    return [int(s) if s.isdigit() else s.lower() for s in re.split(r'(\d+)', text)]

# ---------- SPECIAL 패턴 ----------
special_pattern = re.compile(r'^(AJ|BJ|AT)[0-9]{3,4}', re.IGNORECASE)

# ---------- 전체 통합 리스트 ----------
all_LINE, all_VALVE, all_SPECIAL = [], [], []

# ---------- PDF 처리 ----------
for input_pdf_path in pdf_paths:
    input_pdf_name = os.path.basename(input_pdf_path)
    base_name = os.path.splitext(input_pdf_name)[0]
    folder = os.path.dirname(input_pdf_path)
    today_str = datetime.now().strftime("%Y%m%d")

    # 결과 파일 경로 설정
    line_csv = os.path.join(folder, f"LINE_{base_name}_{today_str}.CSV")
    valve_csv = os.path.join(folder, f"VALVE_{base_name}_{today_str}.CSV")
    special_csv = os.path.join(folder, f"SPECIAL_{base_name}_{today_str}.CSV")
    dup_csv_path = os.path.join(folder, f"DUP_{base_name}_{today_str}.CSV")
    output_pdf = os.path.join(folder, f"OUT_{base_name}_{today_str}.PDF")
    dup_pdf = os.path.join(folder, f"DUP_{base_name}_{today_str}.PDF")

    doc = fitz.open(input_pdf_path)
    doc2 = fitz.open(input_pdf_path)

    line_list, valve_list, special_list = [], [], []
    line_no_rects = defaultdict(list)
    valve_no_rects = defaultdict(list)
    special_no_rects = defaultdict(list)

    for page_num, page in enumerate(doc, 1):
        words = page.get_text("words")
        for w in words:
            x0, y0, x1, y1, text = w[:5]
            clean_text = text.strip().replace(" ", "")
            if len(clean_text) < 4:
                continue
            prefix4 = clean_text[:4].upper()

            rect = fitz.Rect(x0, y0, x1, y1)
            is_found = False

            # ---------- LINE NO ----------
            if len(prefix4) >= 4 and prefix4[3] == 'A' and len(clean_text) >= 9:
                full_line = f"1-62100-{clean_text}"
                line_list.append([full_line])
                line_no_rects[full_line].append((page_num - 1, rect))
                all_LINE.append([full_line])
                is_found = True
                print(f"[{base_name}] LINE NO: {full_line}")

            # ---------- VALVE NO ----------
            elif prefix4[0] == 'V':
                full_valve = f"1-62100-{clean_text}"
                valve_list.append([full_valve])
                valve_no_rects[full_valve].append((page_num - 1, rect))
                all_VALVE.append([full_valve])
                is_found = True
                print(f"[{base_name}] VALVE NO: {full_valve}")

            # ---------- SPECIAL NO ----------
            elif special_pattern.match(clean_text):
                special_list.append([clean_text])
                special_no_rects[clean_text].append((page_num - 1, rect))
                all_SPECIAL.append([clean_text])
                is_found = True
                print(f"[{base_name}] SPECIAL NO: {clean_text}")

            # ---------- 하이라이트 ----------
            if is_found:
                highlight(page, rect, color=(0, 1, 0), opacity=0.2)

    # ---------- 중복 체크 및 CSV 저장 ----------
    def process_list(lst):
        counts = defaultdict(int)
        for row in lst:
            counts[row[0]] += 1
        return [row + ["중복" if counts[row[0]] > 1 else ""] for row in lst], counts

    line_list_dup, line_counts = process_list(line_list)
    valve_list_dup, valve_counts = process_list(valve_list)
    special_list_dup, special_counts = process_list(special_list)

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

    # ---------- 중복 전용 CSV ----------
    def extract_dups(lst):
        return [r for r in lst if r[1] == "중복"]

    dup_lines = extract_dups(line_list_dup)
    dup_valves = extract_dups(valve_list_dup)
    dup_specials = extract_dups(special_list_dup)

    max_len = max(len(dup_lines), len(dup_valves), len(dup_specials))
    dup_lines += [["", ""]] * (max_len - len(dup_lines))
    dup_valves += [["", ""]] * (max_len - len(dup_valves))
    dup_specials += [["", ""]] * (max_len - len(dup_specials))

    with open(dup_csv_path, "w", newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(["LINE NO", "중복", "VALVE NO", "중복", "SPECIAL NO", "중복"])
        for i in range(max_len):
            writer.writerow(dup_lines[i] + dup_valves[i] + dup_specials[i])

    # ---------- 중복 하이라이트 색상 표시 ----------
    def highlight_duplicates(counts_dict, rects_dict):
        for key, rects in rects_dict.items():
            if counts_dict[key] > 1:
                for idx, (pg, rect) in enumerate(rects):
                    color = (0, 0, 1) if idx == 0 else (1, 0, 0)
                    highlight(doc2[pg], rect, color=color, opacity=0.4)

    highlight_duplicates(line_counts, line_no_rects)
    highlight_duplicates(valve_counts, valve_no_rects)
    highlight_duplicates(special_counts, special_no_rects)

    doc2.save(dup_pdf); doc2.close()
    print(f"🎨 중복 하이라이트 저장 완료 → {dup_pdf}")
    doc.save(output_pdf); doc.close()
    print(f"📄 기본 하이라이트 저장 완료 → {output_pdf}\n")

# ---------- 통합 CSV 저장 ----------
if any([all_LINE, all_VALVE, all_SPECIAL]):
    first_pdf = os.path.splitext(os.path.basename(pdf_paths[0]))[0]
    all_csv = os.path.join(os.path.dirname(pdf_paths[0]),
                           f"ALL_{first_pdf}_{datetime.now().strftime('%Y%m%d')}.CSV")
    with open(all_csv, "w", newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(["LINE NO", "중복"])
        writer.writerows(all_LINE)
        writer.writerow([])
        writer.writerow(["VALVE NO", "중복"])
        writer.writerows(all_VALVE)
        writer.writerow([])
        writer.writerow(["SPECIAL NO", "중복"])
        writer.writerows(all_SPECIAL)
    print(f"✅ 통합 CSV 생성됨 → {all_csv}")
