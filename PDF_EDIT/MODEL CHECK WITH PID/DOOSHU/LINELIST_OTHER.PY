import fitz  # PyMuPDF
from tkinter import Tk, filedialog
from datetime import datetime
import re
import os
import csv

root = Tk()
root.withdraw()
current_dir = os.path.dirname(os.path.abspath(__file__))  # 현재 파이썬 스크립트 경로
pdf_paths = filedialog.askopenfilenames(
    title="PDF 파일들을 선택하세요",
    filetypes=[("PDF files", "*.pdf")],
    initialdir=current_dir
)
if not pdf_paths:
    print("PDF 파일이 선택되지 않았습니다.")
    exit()

def highlight(page, rect, color, opacity=0.3):
    if rect.get_area() == 0: return
    annot = page.add_rect_annot(rect)
    annot.set_colors(stroke=color, fill=color)
    annot.set_opacity(opacity)
    annot.update()

def merge_to_N(words, start):
    text_acc = ""
    rects = []
    end = start
    found = False
    for j in range(start, len(words)):
        t = words[j][4]
        if text_acc: text_acc += " "
        text_acc += t
        rects.append(fitz.Rect(*words[j][:4]))
        end = j
        if "N" in t or "N" in text_acc:
            found = True
            break
    if found:
        return text_acc.strip(), rects, end
    else:
        return None, [], start

def is_valvno_start(word):
    word = word.upper()
    return (
        word.startswith('(-V') or word.startswith('(V-') or
        word.startswith('-V-') or word.startswith('-V') or word.startswith('V-')
    )

def is_valvno_any(word):
    wordu = word.upper()
    return (
        re.match(r'^(\(?-?V-?)\d{3,5}', wordu) or
        (wordu.startswith('3/4') and 'V-' in wordu)
    )

def find_nearby_pv(words, idx, max_dist=30):
    x0, y0, x1, y1, _ = words[idx][:5]
    center = ((x0+x1)/2, (y0+y1)/2)
    candidates = []
    for j, w in enumerate(words):
        if j == idx: continue
        tx0, ty0, tx1, ty1, ttxt = w[:5]
        ttxt_strip = ttxt.strip()
        if "-" not in ttxt_strip or len(ttxt_strip) > 8: continue
        tcenter = ((tx0+tx1)/2, (ty0+ty1)/2)
        dx, dy = tcenter[0] - center[0], tcenter[1] - center[1]
        if abs(dx) < max_dist and abs(dy) < max_dist:
            dist = (dx*dx + dy*dy)**0.5
            candidates.append((dist, j, ttxt_strip, fitz.Rect(tx0, ty0, tx1, ty1)))
    if candidates:
        candidates.sort()
        return candidates[0][2], candidates[0][3]
    return None, None

def natural_key(text):
    return [int(s) if s.isdigit() else s.lower() for s in re.split(r'(\d+)', text)]

for input_pdf_path in pdf_paths:
    input_pdf_name = os.path.basename(input_pdf_path)
    base_name = os.path.splitext(input_pdf_name)[0]
    folder = os.path.dirname(input_pdf_path)
    today_str = datetime.now().strftime("%Y%m%d")
    output_pdf = os.path.join(folder, f"OUT_{base_name}_{today_str}.PDF")
    dup_pdf = os.path.join(folder, f"DUP_{base_name}_{today_str}.PDF")
    line_csv = os.path.join(folder, f"LINE_{base_name}_{today_str}.CSV")
    valv_csv = os.path.join(folder, f"VALV_{base_name}_{today_str}.CSV")

    doc = fitz.open(input_pdf_path)
    already_line = set()
    already_valv = set()
    all_line_list = []
    all_valv_list = []

    line_rects = {}
    valv_rects = {}

    for page_num, page in enumerate(doc, 1):
        words = page.get_text("words")
        i = 0
        while i < len(words):
            x0, y0, x1, y1, text = words[i][:5]
            word1 = text.strip()

            # LINE 처리
            if re.match(r'^\d{3}-?[A-Z]\d*$', word1) or re.match(r'^\d{3}-[A-Z]', word1):
                merged, rects, end_idx = merge_to_N(words, i)
                key = (merged,)
                if merged and key not in already_line:
                    for r in rects:
                        highlight(page, r, color=(0, 1, 0), opacity=0.3)
                    already_line.add(key)
                    all_line_list.append([merged, page_num])
                    line_rects.setdefault(merged, []).append((page_num-1, rects))
                i = end_idx + 1
                continue
            elif re.match(r'^\d{3}-?[A-Z]\d*.*N', word1):
                rect = fitz.Rect(x0, y0, x1, y1)
                key = (word1,)
                if key not in already_line:
                    highlight(page, rect, color=(0, 1, 0), opacity=0.3)
                    already_line.add(key)
                    all_line_list.append([word1, page_num])
                    line_rects.setdefault(word1, []).append((page_num-1, [rect]))

            # VALVE 처리
            if is_valvno_any(word1):
                valv_final = word1
                pv_val, pv_rect = None, None
                if is_valvno_start(word1):
                    pv_val, pv_rect = find_nearby_pv(words, i)
                    if pv_val:
                        valv_final = pv_val + word1
                key = (valv_final,)
                if key not in already_valv:
                    if pv_rect:
                        highlight(page, pv_rect, color=(0.5, 0, 1), opacity=0.15)
                    highlight(page, fitz.Rect(x0, y0, x1, y1), color=(0.5, 0, 1), opacity=0.3)
                    already_valv.add(key)
                    all_valv_list.append([valv_final, page_num])
                    valv_rects.setdefault(valv_final, []).append((page_num-1, [fitz.Rect(x0, y0, x1, y1)]))
            i += 1

    # CSV 저장 + 중복 체크
    line_set = set(x[0] for x in all_line_list)
    valv_set = set(x[0] for x in all_valv_list)
    line_out = []
    valv_out = []

    for v in all_valv_list:
        valv_out.append([v[0], "중복" if v[0] in line_set else "", v[1]])

    for l in all_line_list:
        line_out.append([l[0], "중복" if l[0] in valv_set else "", l[1]])

    line_out = sorted(line_out, key=lambda x: natural_key(x[0]))
    valv_out = sorted(valv_out, key=lambda x: natural_key(x[0]))

    if line_out:
        with open(line_csv, "w", newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(["LINE", "중복", "PID PAGE"])
            writer.writerows(line_out)
    if valv_out:
        with open(valv_csv, "w", newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(["VALVNO", "중복", "PID PAGE"])
            writer.writerows(valv_out)

    # DUP PDF 저장
    docDUP = fitz.open(input_pdf_path)
    dupNO = list(line_set & valv_set)
    for no in dupNO:
        rect_list = line_rects.get(no, [])
        for idx, (pg, rects) in enumerate(rect_list):
            for r in rects:
                c = (0,0,1) if idx==0 else (1,0,0)
                highlight(docDUP[pg], r, color=c, opacity=0.5)
        rect_list = valv_rects.get(no, [])
        for idx, (pg, rects) in enumerate(rect_list):
            for r in rects:
                c = (0,0,1) if idx==0 else (1,0,0)
                highlight(docDUP[pg], r, color=c, opacity=0.5)
    docDUP.save(dup_pdf)
    docDUP.close()

    try:
        if not doc.is_closed and not doc.is_encrypted:
            doc.save(output_pdf)
        else:
            print("❌ 문서가 닫혔거나 암호화되어 저장할 수 없습니다.")
    except Exception as e:
        print(f"❌ PDF 저장 오류: {e}")
    finally:
        if not doc.is_closed:
            doc.close()

    print(f"✅ OUT/DUP PDF 및 정렬된 CSV 저장 완료 → {output_pdf}, {dup_pdf}")
