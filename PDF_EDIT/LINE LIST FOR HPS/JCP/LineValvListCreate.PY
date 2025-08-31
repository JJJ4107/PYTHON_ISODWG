import fitz  # PyMuPDF
import re
import csv
import math
from collections import defaultdict
import os
from tkinter import Tk, filedialog
from datetime import datetime

# -------------- 날짜 문자열 --------------
today_str = datetime.now().strftime("%Y%m%d")

# -------------- 파일 다중 선택 --------------
root = Tk()
root.withdraw()
pdf_paths = filedialog.askopenfilenames(
    title="PDF 파일들을 선택하세요",
    filetypes=[("PDF files", "*.pdf")]
)
if not pdf_paths:
    print("PDF 파일이 선택되지 않았습니다.")
    exit()

# -------------- 패턴 정의 --------------
P1_PATTERN = re.compile(r'^(00|11|21|22)[A-Za-z0-9]{0,7}$', re.IGNORECASE)
P2_PATTERN = re.compile(r'^(BR|AA)[A-Za-z0-9]{0,8}$', re.IGNORECASE)
P3_DN_PATTERN = re.compile(r'^DN.{0,11}$', re.IGNORECASE)
P3_H_PATTERN = re.compile(r'^H.{0,11}$', re.IGNORECASE)

# -------------- 헬퍼 함수 --------------
def highlight(page, rect, color, opacity=0.4):
    h = page.add_highlight_annot(rect)
    h.set_colors(stroke=color)
    h.set_opacity(opacity)
    h.update()

def center(rect):
    return ((rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2)

def distance(r1, r2):
    c1 = center(r1)
    c2 = center(r2)
    return math.hypot(c1[0] - c2[0], c1[1] - c2[1])

def normalize_p3(*words):
    return '-'.join(w.replace(' ', '-') for w in words if w).replace('--', '-')

# -------------- 각 PDF 파일 처리 --------------
for input_pdf_path in pdf_paths:
    input_pdf_name = os.path.basename(input_pdf_path)
    base_name = os.path.splitext(input_pdf_name)[0]
    folder = os.path.dirname(input_pdf_path)

    # 🔹 날짜 포함 파일 이름
    line_csv = os.path.join(folder, f"LINE_{base_name}_{today_str}.CSV")
    valve_csv = os.path.join(folder, f"VALVE_{base_name}_{today_str}.CSV")
    output_pdf = os.path.join(folder, f"OUT_{base_name}_{today_str}.PDF")
    dup_pdf = os.path.join(folder, f"DUP_{base_name}_{today_str}.PDF")

    doc = fitz.open(input_pdf_path)
    line_list = []
    valve_list = []
    valve_no_rects = defaultdict(list)

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
                    found_p2 = next_w[4].strip()
                    found_p2_rect = next_rect
            if not found_p2:
                continue
            highlight(page, found_p2_rect, color=(1, 0.5, 0), opacity=0.2)

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
                    highlight(page, found_p3_rect, color=(0, 0, 1), opacity=0.2)
                    line_no = f"{p1}-{found_p2.replace(' ', '-')}-{found_p3}"
                    line_list.append([line_no])
                    print(f"[{base_name}] LINE NO: {line_no}")
            elif found_p2.upper().startswith("AA"):
                valve_no = f"{p1}-{found_p2.replace(' ', '-')}"
                valve_list.append([valve_no])
                valve_no_rects[valve_no].append((page_num - 1, found_p2_rect))
                print(f"[{base_name}] VALVE NO: {valve_no}")

    # 중복 처리 및 정렬
    line_no_counts = defaultdict(int)
    for row in line_list:
        line_no_counts[row[0]] += 1
    line_list_with_dup = [row + ["중복" if line_no_counts[row[0]] > 1 else ""] for row in line_list]
    line_list_with_dup.sort(key=lambda x: x[0])

    valve_no_counts = defaultdict(int)
    for row in valve_list:
        valve_no_counts[row[0]] += 1
    valve_list_with_dup = [row + ["중복" if valve_no_counts[row[0]] > 1 else ""] for row in valve_list]
    valve_list_with_dup.sort(key=lambda x: x[0])

    # CSV 저장 (수정된 버전)
    with open(line_csv, "w", newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(["LINE NO", "중복"])
        writer.writerows(line_list_with_dup)

    with open(valve_csv, "w", newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(["VALVE NO", "중복"])
        writer.writerows(valve_list_with_dup)

    doc.save(output_pdf)
    print(f"✅ 저장 완료: {line_csv}, {valve_csv}, {output_pdf}")

    # DUP PDF 저장
    doc2 = fitz.open(input_pdf_path)
    dup_valve_nos = {row[0] for row in valve_list if valve_no_counts[row[0]] > 1}
    for valve_no in dup_valve_nos:
        rects = valve_no_rects[valve_no]
        for idx, (page_idx, rect) in enumerate(rects):
            page = doc2[page_idx]
            color = (0, 0, 1) if idx == 0 else (1, 0, 0)
            highlight(page, rect, color=color, opacity=0.4)
    doc2.save(dup_pdf)
    doc2.close()
    print(f"🎨 중복 VALVE NO는 {dup_pdf}에 파랑/빨강 하이라이트로 저장 완료!\n")
