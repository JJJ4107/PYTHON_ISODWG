import fitz  # PyMuPDF
from tkinter import Tk, filedialog
from datetime import datetime
import re
import os
import csv

root = Tk()
root.withdraw()
pdf_paths = filedialog.askopenfilenames(
    title="PDF 파일들을 선택하세요",
    filetypes=[("PDF files", "*.pdf")]
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
    """자연스러운 문자열 정렬(숫자, 알파벳 혼합)"""
    import re
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
    doc2 = fitz.open(input_pdf_path)
    already_line = set()
    already_valv = set()
    all_line_list = []
    all_valv_list = []

    # 각 NO별 rect 저장 (중복용)
    line_rects = {}
    valv_rects = {}

    for page_num, page in enumerate(doc, 1):
        words = page.get_text("words")
        n = len(words)
        i = 0
        while i < n:
            x0, y0, x1, y1, text = words[i][:5]
            word1 = text.strip()
            # 1. LINENO
            if re.match(r'^\d{3}-?[A-Z]\d*$', word1) or re.match(r'^\d{3}-[A-Z]', word1):
                merged, rects, end_idx = merge_to_N(words, i)
                key = (merged,)
                if merged and key not in already_line:
                    for r in rects:
                        highlight(page, r, color=(0, 1, 0), opacity=0.3)
                    already_line.add(key)
                    all_line_list.append([merged])
                    line_rects.setdefault(merged, []).append((page_num-1, rects))
                i = end_idx + 1
                continue
            elif re.match(r'^\d{3}-?[A-Z]\d*.*N', word1):
                rect = fitz.Rect(x0, y0, x1, y1)
                key = (word1,)
                if key not in already_line:
                    highlight(page, rect, color=(0, 1, 0), opacity=0.3)
                    already_line.add(key)
                    all_line_list.append([word1])
                    line_rects.setdefault(word1, []).append((page_num-1, [rect]))
            # 2. VALVNO
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
                    all_valv_list.append([valv_final])
                    valv_rects.setdefault(valv_final, []).append((page_num-1, [fitz.Rect(x0, y0, x1, y1)]))
            i += 1

        # 세로(문자) 조립에서도 동일하게
        try:
            chars = page.get_text("chars")
            columns = {}
            for x0, y0, x1, y1, ch, *_ in chars:
                if not ch.strip(): continue
                k = round(x0, 1)
                columns.setdefault(k, []).append((y0, x0, x1, y1, ch))
            for col_items in columns.values():
                col_items.sort(key=lambda t: t[0])
                chars_only = [c[4] for c in col_items]
                boxes = col_items
                maxlen = len(chars_only)
                i = 0
                while i < maxlen:
                    if (i+3 < maxlen and
                        re.fullmatch(r'\d', chars_only[i]) and
                        re.fullmatch(r'\d', chars_only[i+1]) and
                        re.fullmatch(r'\d', chars_only[i+2]) and
                        (chars_only[i+3] == '-' or chars_only[i+3].isalpha())):
                        merged = ''.join(chars_only[i:i+4])
                        rects = []
                        slice_end = i+3
                        for j in range(i+4, maxlen):
                            merged += chars_only[j]
                            rects.append(fitz.Rect(boxes[j][1], boxes[j][0], boxes[j][2], boxes[j][3]))
                            if chars_only[j] == 'N':
                                slice_end = j
                                break
                        else:
                            i += 1
                            continue
                        for j in range(i, i+4):
                            rects.append(fitz.Rect(boxes[j][1], boxes[j][0], boxes[j][2], boxes[j][3]))
                        key = (merged,)
                        if key not in already_line:
                            for r in rects:
                                highlight(page, r, color=(0, 1, 0), opacity=0.3)
                            already_line.add(key)
                            all_line_list.append([merged])
                            line_rects.setdefault(merged, []).append((page_num-1, rects))
                        i = slice_end + 1
                        continue
                    i += 1

                # VALVNO(세로 문자)
                i = 0
                while i < maxlen:
                    for slen in range(4, 13):
                        if i+slen <= maxlen:
                            part = ''.join(chars_only[i:i+slen])
                            if is_valvno_any(part):
                                valv_final = part
                                pv_val, pv_rect = None, None
                                if is_valvno_start(part):
                                    center_y = (boxes[i][0] + boxes[i+slen-1][3]) / 2
                                    center_x = (boxes[i][1] + boxes[i+slen-1][2]) / 2
                                    min_dist, best_val, best_rect = 9999, None, None
                                    for k2, cc2 in columns.items():
                                        if cc2 == col_items: continue
                                        for seglen in range(2, 9):
                                            for idx in range(len(cc2) - seglen + 1):
                                                segtxt = ''.join(cc2[idx:idx+seglen][k][4] for k in range(seglen))
                                                if '-' in segtxt and len(segtxt) <= 8:
                                                    cy = (cc2[idx][0] + cc2[idx+seglen-1][3]) / 2
                                                    cx = (cc2[idx][1] + cc2[idx+seglen-1][2]) / 2
                                                    dist = abs(center_x - cx) + abs(center_y - cy)
                                                    if dist < min_dist:
                                                        min_dist, best_val, best_rect = dist, segtxt, fitz.Rect(
                                                            min([cc2[idx+k][1] for k in range(seglen)]),
                                                            min([cc2[idx+k][0] for k in range(seglen)]),
                                                            max([cc2[idx+k][2] for k in range(seglen)]),
                                                            max([cc2[idx+k][3] for k in range(seglen)])
                                                        )
                                    pv_val, pv_rect = best_val, best_rect
                                    if pv_val:
                                        valv_final = pv_val + part
                                key = (valv_final,)
                                if key not in already_valv:
                                    if pv_rect:
                                        highlight(page, pv_rect, color=(0.5, 0, 1), opacity=0.15)
                                    x0s = [boxes[j][1] for j in range(i, i+slen)]
                                    y0s = [boxes[j][0] for j in range(i, i+slen)]
                                    x1s = [boxes[j][2] for j in range(i, i+slen)]
                                    y1s = [boxes[j][3] for j in range(i, i+slen)]
                                    rect = fitz.Rect(min(x0s), min(y0s), max(x1s), max(y1s))
                                    highlight(page, rect, color=(0.5, 0, 1), opacity=0.3)
                                    already_valv.add(key)
                                    all_valv_list.append([valv_final])
                                    valv_rects.setdefault(valv_final, []).append((page_num-1, [rect]))
                    i += 1
        except Exception:
            pass

    # ---------- CSV 저장 + 중복 체크 ----------
    line_set = set(x[0] for x in all_line_list)
    valv_set = set(x[0] for x in all_valv_list)
    line_out = []
    valv_out = []
    for v in all_valv_list:
        valv_out.append([v[0], "중복" if v[0] in line_set else ""])
    for l in all_line_list:
        line_out.append([l[0], "중복" if l[0] in valv_set else ""])

    # 정렬
    line_out = sorted(line_out, key=lambda x: natural_key(x[0]))
    valv_out = sorted(valv_out, key=lambda x: natural_key(x[0]))

    if line_out:
        with open(line_csv, "w", newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(["LINE", "중복"])
            writer.writerows(line_out)
    if valv_out:
        with open(valv_csv, "w", newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(["VALVNO", "중복"])
            writer.writerows(valv_out)

    # ---------- DUP PDF: 중복 NO만 파랑/빨강 하이라이트 ----------
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

    doc.save(output_pdf)
    doc.close()
    print(f"✅ OUT/DUP PDF 및 정렬된 CSV 저장 완료 → {output_pdf}, {dup_pdf}")
