import fitz  # PyMuPDF
import csv
import os
import re
from collections import defaultdict
from tkinter import Tk, filedialog
from datetime import datetime

root = Tk()
root.withdraw()
current_dir = os.path.dirname(os.path.abspath(__file__))
pdf_paths = filedialog.askopenfilenames(
    title="PDF 파일들을 선택하세요",
    filetypes=[("PDF files", "*.pdf")],
    initialdir=current_dir
)
if not pdf_paths:
    print("PDF 파일이 선택되지 않았습니다.")
    exit()

def highlight(page, rect, color, opacity=0.4):
    if rect.get_area() == 0: return
    annot = page.add_rect_annot(rect)
    annot.set_colors(stroke=color, fill=color)
    annot.set_opacity(opacity)
    annot.update()

def natural_key(text):
    return [int(s) if s.isdigit() else s.lower() for s in re.split(r'(\d+)', text)]

def normalize_quote_before_slash(text):
    text = str(text)
    if "/" not in text:
        return text.replace('"', '')
    left, right = text.split("/", 1)
    left = left.replace('"', '')
    right = right.replace('"', '')
    return f"{left}/{right}"

def extract_vertical_words(page, min_len=4, gap_tol=2.2):
    try:
        chars = page.get_text("chars")
    except Exception:
        return []
    columns = defaultdict(list)
    for x0, y0, x1, y1, ch, *_ in chars:
        if not ch.strip(): continue
        col_key = round(x0, 1)
        columns[col_key].append((y0, x0, x1, y1, ch))
    results = []
    for col_items in columns.values():
        col_items.sort(key=lambda it: it[0])
        word = []
        rects = []
        prev_y, prev_h = None, None
        for y0, x0, x1, y1, ch in col_items:
            h = y1 - y0
            if prev_y is not None and (y0 - prev_y) > (prev_h or h) * gap_tol:
                if len(word) >= min_len:
                    results.append((word, rects))
                word = []
                rects = []
            word.append(ch)
            rects.append(fitz.Rect(x0, y0, x1, y1))
            prev_y, prev_h = y0, h
        if len(word) >= min_len:
            results.append((word, rects))
    words = []
    for group, rects in results:
        text = ''.join(group)
        words.append((text, rects))
    return words

special_pattern = re.compile(r'^(AJ|BJ|AT)[0-9]{3,4}', re.IGNORECASE)

for input_pdf_path in pdf_paths:
    input_pdf_name = os.path.basename(input_pdf_path)
    base_name = os.path.splitext(input_pdf_name)[0]
    folder = os.path.dirname(input_pdf_path)
    today_str = datetime.now().strftime("%Y%m%d")

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
        words_h = page.get_text("words")
        words_v = page.get_text("words", sort=False)
        words_set = {tuple(w[:5]) for w in words_h}
        words = words_h + [w for w in words_v if tuple(w[:5]) not in words_set]
        rect_map = {}

        # ---------- 세로 단어(글자별) 추가 ----------
        vert_words = extract_vertical_words(page)
        for vtxt, vrects in vert_words:
            t_clean = vtxt.strip().replace(" ", "")
            if len(t_clean) < 4: continue
            rect_map[vtxt] = vrects
            # 가로 단어와 x0/y0가 거의 같으면 중복 추가 방지
            if any(abs(vrects[0].x0 - w[0]) < 0.1 and abs(vrects[0].y0 - w[1]) < 0.1 for w in words_h):
                continue
            words.append([vrects[0].x0, vrects[0].y0, vrects[-1].x1, vrects[-1].y1, vtxt])

        i = 0
        while i < len(words):
            x0, y0, x1, y1, text = words[i][:5]
            clean_text = text.strip().replace(" ", "")
            if len(clean_text) < 4:
                i += 1
                continue
            prefix4 = clean_text[:4].upper()
            rect = fitz.Rect(x0, y0, x1, y1)
            is_found = False

            # ---------- LINE NO ----------
            if re.match(r'^\d{3}', text.strip()) and '"' in text:
                merged_text = text.strip()
                j = i + 1
                while j < len(words):
                    part = words[j][4].strip()
                    merged_text += ' ' + part
                    if re.search(r'[A-Za-z]', part):
                        x1, y1 = words[j][2], words[j][3]
                        break
                    x1, y1 = words[j][2], words[j][3]
                    j += 1
                full_line = merged_text.strip().replace('" /', '"/').replace(' ', '')
                if text in rect_map:
                    for r in rect_map[text]:
                        highlight(page, r, color=(0, 1, 0), opacity=0.2)
                        highlight(doc2[page_num-1], r, color=(0, 0, 1), opacity=0.5)
                else:
                    highlight(page, rect, color=(0, 1, 0), opacity=0.2)
                line_list.append([full_line, page_num])
                line_no_rects[full_line].append((page_num - 1, rect))
                is_found = True
                print(f"[{base_name}] LINE NO: {full_line}")
                i = j - 1

            # ---------- VALVE NO ----------
            elif (len(prefix4) > 0 and prefix4[0] == 'V' and re.match(r'^V\d{3,4}', clean_text)) or \
                 (re.match(r'^\d{3}', clean_text) and '-V' in clean_text):
                full_valve = clean_text
                if text in rect_map:
                    for r in rect_map[text]:
                        highlight(page, r, color=(1, 0, 1), opacity=0.2)
                        highlight(doc2[page_num-1], r, color=(1, 0, 0), opacity=0.5)
                else:
                    highlight(page, rect, color=(1, 0, 1), opacity=0.2)
                valve_list.append([full_valve, page_num])
                valve_no_rects[full_valve].append((page_num - 1, rect))
                is_found = True
                print(f"[{base_name}] VALVE NO: {full_valve}")

            # ---------- SPECIAL NO ----------
            elif special_pattern.match(clean_text):
                special_list.append([clean_text, page_num])
                special_no_rects[clean_text].append((page_num - 1, rect))
                is_found = True
                print(f"[{base_name}] SPECIAL NO: {clean_text}")

            i += 1

    # ---------- 중복 체크 및 CSV 저장 ----------
def process_list(lst):
    counts = defaultdict(int)
    for row in lst:
        counts[row[0]] += 1
    return [[row[0], "중복" if counts[row[0]] > 1 else "", row[1]] for row in lst], counts

# ⬇️ 함수 바깥에서 호출되도록 반드시 들여쓰기 없이 배치
line_list_dup, line_counts = process_list(line_list)
valve_list_dup, valve_counts = process_list(valve_list)
special_list_dup, special_counts = process_list(special_list)


# ---------- 정렬 및 CSV 저장 ----------
with open(line_csv, "w", newline='', encoding='utf-8-sig') as f:
    writer = csv.writer(f)
    writer.writerow(["LINE NO", "중복", "page_num"])
    for row in sorted(line_list_dup, key=lambda x: natural_key(x[0])):
        row_out = row.copy()
        row_out[0] = normalize_quote_before_slash(row_out[0])
        writer.writerow(row_out)

with open(valve_csv, "w", newline='', encoding='utf-8-sig') as f:
    writer = csv.writer(f)
    writer.writerow(["VALVE NO", "중복", "page_num"])
    for row in sorted(valve_list_dup, key=lambda x: natural_key(x[0])):
        row_out = row.copy()
        row_out[0] = normalize_quote_before_slash(row_out[0])
        writer.writerow(row_out)

with open(special_csv, "w", newline='', encoding='utf-8-sig') as f:
    writer = csv.writer(f)
    writer.writerow(["SPECIAL NO", "중복", "page_num"])
    for row in sorted(special_list_dup, key=lambda x: natural_key(x[0])):
        row_out = row.copy()
        row_out[0] = normalize_quote_before_slash(row_out[0])
        writer.writerow(row_out)

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
                    writer.writerow(
                        [normalize_quote_before_slash(x) for x in dup_lines[i]] +
                        [normalize_quote_before_slash(x) for x in dup_valves[i]] +
                        [normalize_quote_before_slash(x) for x in dup_specials[i]]
                    )
    for lineno, rects in line_no_rects.items():
        if len(rects) > 1:
            for idx, (pno, rect) in enumerate(rects):
                color = (0, 0, 1) if idx == 0 else (1, 0, 0)
                highlight(doc2[pno], rect, color=color, opacity=0.5)

    for valveno, rects in valve_no_rects.items():
        if len(rects) > 1:
            for idx, (pno, rect) in enumerate(rects):
                color = (0, 0, 1) if idx == 0 else (1, 0, 0)
                highlight(doc2[pno], rect, color=color, opacity=0.5)

    doc2.save(dup_pdf)
    doc2.close()
    doc.save(output_pdf)
    doc.close()
    print(f"✅ 처리 완료: {output_pdf}")

# ---------- 통합 CSV 저장 ----------
if any([line_list, valve_list, special_list]):
    first_pdf = os.path.splitext(os.path.basename(pdf_paths[0]))[0]
    all_csv = os.path.join(os.path.dirname(pdf_paths[0]),
                           f"ALL_{first_pdf}_{datetime.now().strftime('%Y%m%d')}.CSV")
    with open(all_csv, "w", newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(["LINE NO", "중복"])
        for row in sorted(line_list, key=lambda x: natural_key(x[0])):
            row_out = row.copy()
            row_out[0] = normalize_quote_before_slash(row_out[0])
            writer.writerow(row_out)
        writer.writerow([])
        writer.writerow(["VALVE NO", "중복"])
        for row in sorted(valve_list, key=lambda x: natural_key(x[0])):
            row_out = row.copy()
            row_out[0] = normalize_quote_before_slash(row_out[0])
            writer.writerow(row_out)
        writer.writerow([])
        writer.writerow(["SPECIAL NO", "중복"])
        for row in sorted(special_list, key=lambda x: natural_key(x[0])):
            row_out = row.copy()
            row_out[0] = normalize_quote_before_slash(row_out[0])
            writer.writerow(row_out)
    print(f"✅ 통합 CSV 생성됨 → {all_csv}")
