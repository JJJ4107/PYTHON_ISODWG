import fitz  # PyMuPDF
import re
import csv
import math
from collections import defaultdict

input_pdf = "RUM11.PDF"
line_csv = "LINE_RUM11.CSV"
valve_csv = "VALVE_RUM11.CSV"
output_pdf = "RUM11_OUT.PDF"

P1_PATTERN = re.compile(r'^(00|11|21|22)[A-Za-z0-9]{0,7}$', re.IGNORECASE)    # 9자리 이하
P2_PATTERN = re.compile(r'^(BR|AA)[A-Za-z0-9]{0,8}$', re.IGNORECASE)         # 10자리 이하
P3_DN_PATTERN = re.compile(r'^DN.{0,11}$', re.IGNORECASE)                    # 13자리 이하(DN으로 시작)
P3_H_PATTERN = re.compile(r'^H.{0,11}$', re.IGNORECASE)                      # H로 시작, 13자리 이하

def highlight(page, rect, color=(0,1,0), opacity=0.2):
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

doc = fitz.open(input_pdf)
line_list = []
valve_list = []

for page_num, page in enumerate(doc, 1):
    words = page.get_text("words")
    n = len(words)
    for i, w in enumerate(words):
        text = w[4].strip().replace(" ", "")
        if not P1_PATTERN.match(text):
            continue
        p1 = w[4].strip().replace(" ", "")
        p1_rect = fitz.Rect(w[:4])
        highlight(page, p1_rect, color=(0, 1, 0), opacity=0.2)  # 초록

        # P2 후보 중 가장 가까운 것 선택
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
        highlight(page, found_p2_rect, color=(1,0.5,0), opacity=0.2)  # 주황

        # BR이면 P3 후보(DN, 그리고 그 다음 인접 H 포함) 중 가장 가까운 것
        if found_p2.upper().startswith("BR"):
            min_dist3 = float('inf')
            found_p3 = None
            found_p3_rect = None
            for k, next_w3 in enumerate(words):
                dn_raw = next_w3[4].strip()
                dn_raw_nospace = dn_raw.replace(" ", "")
                if not P3_DN_PATTERN.match(dn_raw):
                    continue
                dn_rect = fitz.Rect(next_w3[:4])
                dist3 = distance(found_p2_rect, dn_rect)
                if dist3 < min_dist3:
                    # DN 찾은 뒤, 인접하게 붙은 단어가 H로 시작하면 합침
                    p3_full = dn_raw
                    p3_rects = [dn_rect]
                    # 다음 단어 체크(공백이 실제 단어 사이에 있을 수 있으니, x좌표 거리로 인접 판단)
                    if k+1 < n:
                        next_h_word = words[k+1][4].strip()
                        next_h_rect = fitz.Rect(words[k+1][:4])
                        # H로 시작 & x/y 좌표상 인접(20pt 이내)인 경우
                        if P3_H_PATTERN.match(next_h_word) and distance(dn_rect, next_h_rect) < 20:
                            p3_full = f"{dn_raw} {next_h_word}"
                            p3_rects.append(next_h_rect)
                    found_p3 = normalize_p3(*p3_full.split())
                    found_p3_rect = p3_rects[0]
                    min_dist3 = dist3
            if found_p3:
                highlight(page, found_p3_rect, color=(0,0,1), opacity=0.2)  # 파랑(첫 DN만 하이라이트)
                line_no = f"{p1}-{found_p2.replace(' ','-')}-{found_p3}"
                line_list.append([p1, found_p2.replace(' ','-'), found_p3, line_no])
                print(f"[LINE NO] {line_no}")
        # AA면 VALVE
        elif found_p2.upper().startswith("AA"):
            valve_no = f"{p1}-{found_p2.replace(' ','-')}"
            valve_list.append([p1, found_p2.replace(' ','-'), valve_no])
            print(f"[VALVE NO] {valve_no}")

# 중복 체크 (LINE NO)
line_no_counts = defaultdict(int)
for row in line_list:
    line_no_counts[row[3]] += 1
line_list_with_dup = []
for row in line_list:
    dup = "중복" if line_no_counts[row[3]] > 1 else ""
    line_list_with_dup.append(row + [dup])

# 중복 체크 (VALVE NO)
valve_no_counts = defaultdict(int)
for row in valve_list:
    valve_no_counts[row[2]] += 1
valve_list_with_dup = []
for row in valve_list:
    dup = "중복" if valve_no_counts[row[2]] > 1 else ""
    valve_list_with_dup.append(row + [dup])

# CSV 저장
with open(line_csv, "w", newline='', encoding='utf-8-sig') as f:
    writer = csv.writer(f)
    writer.writerow(["P1", "P2", "P3", "LINE NO", "중복"])
    writer.writerows(line_list_with_dup)

with open(valve_csv, "w", newline='', encoding='utf-8-sig') as f:
    writer = csv.writer(f)
    writer.writerow(["P1", "P2", "VALVE NO", "중복"])
    writer.writerows(valve_list_with_dup)

doc.save(output_pdf)
doc.close()
print(f"\n저장 완료: {line_csv}, {valve_csv}, {output_pdf}")
