import fitz  # PyMuPDF
import re
import csv
import math
import os
from collections import defaultdict
from tkinter import Tk, filedialog
from datetime import datetime

# 날짜 문자열
today_str = datetime.now().strftime("%Y%m%d")

# 파일 선택
root = Tk()
root.withdraw()
pdf_paths = filedialog.askopenfilenames(title="PDF 파일을 선택하세요", filetypes=[("PDF files", "*.pdf")])
if not pdf_paths:
    print("❌ PDF 파일이 선택되지 않았습니다.")
    exit()

model_csv_path = filedialog.askopenfilename(title="MODEL.CSV 파일을 선택하세요", filetypes=[("CSV files", "*.csv")])
if not model_csv_path:
    print("❌ MODEL.CSV 파일이 선택되지 않았습니다.")
    exit()

# MODEL 목록 로딩
with open(model_csv_path, newline='', encoding='utf-8-sig') as f:
    reader = csv.reader(f)
    model_set = set(row[0].strip().upper() for row in reader if row and row[0].strip())

# 정규식
P1_PATTERN = re.compile(r'^(00|11|21|22)[A-Za-z0-9]{0,7}$', re.IGNORECASE)
P2_PATTERN = re.compile(r'^(BR|AA)[A-Za-z0-9]{0,8}$', re.IGNORECASE)
P3_DN_PATTERN = re.compile(r'^DN.{0,11}$', re.IGNORECASE)
P3_H_PATTERN = re.compile(r'^H.{0,11}$', re.IGNORECASE)

# 거리 계산
def center(rect): return ((rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2)
def distance(r1, r2): return math.hypot(center(r1)[0] - center(r2)[0], center(r1)[1] - center(r2)[1])
def normalize_p3(*words): return '-'.join(w.replace(' ', '-') for w in words if w).replace('--', '-')
def highlight(page, rect, color, opacity=0.4):
    annot = page.add_rect_annot(rect)
    annot.set_colors(stroke=color)
    annot.set_opacity(opacity)
    annot.update()

# PDF 처리
for input_pdf_path in pdf_paths:
    base_name = os.path.splitext(os.path.basename(input_pdf_path))[0]
    folder = os.path.dirname(input_pdf_path)

    output_pdf = os.path.join(folder, f"CHK_{base_name}_{today_str}.PDF")
    unmodel_csv = os.path.join(folder, f"UNMODEL_{base_name}_{today_str}.CSV")
    unmodel_sorted_csv = os.path.join(folder, f"UNMODEL_SORTED_{base_name}_{today_str}.CSV")

    doc = fitz.open(input_pdf_path)
    unmatched_set = set()

    for page_num, page in enumerate(doc, 1):
        words = page.get_text("words")
        n = len(words)
        for i, w in enumerate(words):
            text = w[4].strip().replace(" ", "")
            if not P1_PATTERN.match(text):
                continue
            p1 = text
            p1_rect = fitz.Rect(w[:4])
            highlight(page, p1_rect, color=(0, 1, 0), opacity=0.2)

            # P2 탐색
            min_dist = float('inf')
            found_p2 = None
            found_p2_rect = None
            for j, next_w in enumerate(words):
                if i == j:
                    continue
                next_text = next_w[4].strip().replace(" ", "")
                if not P2_PATTERN.match(next_text):
                    continue
                next_rect = fitz.Rect(next_w[:4])
                dist = distance(p1_rect, next_rect)
                if dist < min_dist:
                    min_dist = dist
                    found_p2 = next_text
                    found_p2_rect = next_rect
            if not found_p2:
                continue
            highlight(page, found_p2_rect, color=(1, 0.5, 0), opacity=0.2)

            # P3 있는 경우 → LINE NO
            if found_p2.upper().startswith("BR"):
                min_dist3 = float('inf')
                found_p3 = None
                found_p3_rect = None
                for k, next_w3 in enumerate(words):
                    dn_raw = next_w3[4].strip()
                    if not P3_DN_PATTERN.match(dn_raw):
                        continue
                    dn_rect = fitz.Rect(next_w3[:4])
                    dist3 = distance(found_p2_rect, dn_rect)
                    if dist3 < min_dist3:
                        p3_full = dn_raw
                        p3_rects = [dn_rect]
                        if k + 1 < n:
                            next_h_word = words[k + 1][4].strip()
                            next_h_rect = fitz.Rect(words[k + 1][:4])
                            if P3_H_PATTERN.match(next_h_word) and distance(dn_rect, next_h_rect) < 20:
                                p3_full = f"{dn_raw} {next_h_word}"
                                p3_rects.append(next_h_rect)
                        found_p3 = normalize_p3(*p3_full.split())
                        found_p3_rect = p3_rects[0]
                        min_dist3 = dist3
                if found_p3:
                    full_line_no = f"{p1}-{found_p2.replace(' ', '-')}-{found_p3}"
                    highlight(page, found_p3_rect, color=(0, 0, 1), opacity=0.2)
                    if full_line_no not in model_set:
                        unmatched_set.add(full_line_no)
                        highlight(page, p1_rect, color=(1, 0, 0), opacity=0.4)
                        highlight(page, found_p2_rect, color=(1, 0, 0), opacity=0.4)
                        highlight(page, found_p3_rect, color=(1, 0, 0), opacity=0.4)
            elif found_p2.upper().startswith("AA"):
                full_valve_no = f"{p1}-{found_p2.replace(' ', '-')}"
                if full_valve_no not in model_set:
                    unmatched_set.add(full_valve_no)
                    highlight(page, p1_rect, color=(1, 0, 0), opacity=0.4)
                    highlight(page, found_p2_rect, color=(1, 0, 0), opacity=0.4)

    # 하이라이트 저장
    doc.save(output_pdf)
    doc.close()
    print(f"📄 CHK PDF 저장 완료: {output_pdf}")

    # UNMODEL CSV 저장
    if unmatched_set:
        with open(unmodel_csv, "w", newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(["UNMODELED P1"])
            for p in sorted(unmatched_set):
                writer.writerow([p])
        print(f"❌ UNMODELED 저장 완료: {unmodel_csv}")
    else:
        print("✅ 모든 P1이 MODEL.CSV와 일치합니다.")

    # 정렬 테이블 저장 (LINE / VALVE 세로 구분)
    line_nos = sorted([p for p in unmatched_set if "-BR" in p])
    valve_nos = sorted([p for p in unmatched_set if any(tag in p for tag in ["-AA", "-AJ", "-BJ", "-AT"])])

    max_len = max(len(line_nos), len(valve_nos))
    with open(unmodel_sorted_csv, "w", newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(["LINE NO", "VALVE NO"])
        for i in range(max_len):
            line_val = line_nos[i] if i < len(line_nos) else ""
            valve_val = valve_nos[i] if i < len(valve_nos) else ""
            writer.writerow([line_val, valve_val])
    print(f"🧾 정리된 UNMODEL 테이블 저장 완료: {unmodel_sorted_csv}")
