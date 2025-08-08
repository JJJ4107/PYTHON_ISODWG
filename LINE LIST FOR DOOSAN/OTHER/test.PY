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

def highlight(page, rect, color=(0, 1, 0), opacity=0.3):
    if rect.get_area() == 0: return
    annot = page.add_rect_annot(rect)
    annot.set_colors(stroke=color, fill=color)
    annot.set_opacity(opacity)
    annot.update()

def merge_to_N(words, start):
    """start 인덱스부터 단어를 붙여가다 N이 나오면 그 위치까지 병합해서 반환"""
    text_acc = ""
    x0, y0, _, _ = words[start][:4]
    end = start
    found = False
    for j in range(start, len(words)):
        t = words[j][4]
        text_acc += t
        end = j
        if "N" in text_acc:
            idx = text_acc.index("N")
            text_acc = text_acc[:idx+1]
            found = True
            break
    _, _, x1, y1 = words[end][:4]
    rect = fitz.Rect(x0, y0, x1, y1)
    return text_acc.strip(), rect, end if found else (None, None, start)

for input_pdf_path in pdf_paths:
    input_pdf_name = os.path.basename(input_pdf_path)
    base_name = os.path.splitext(input_pdf_name)[0]
    folder = os.path.dirname(input_pdf_path)
    today_str = datetime.now().strftime("%Y%m%d")
    output_pdf = os.path.join(folder, f"OUT_{base_name}_{today_str}.PDF")
    line_csv = os.path.join(folder, f"LINE_{base_name}_{today_str}.CSV")

    doc = fitz.open(input_pdf_path)
    already = set()
    all_line_list = []

    for page in doc:
        words = page.get_text("words")
        n = len(words)
        i = 0
        while i < n:
            x0, y0, x1, y1, text = words[i][:5]
            word1 = text.strip()
            # 1. 123-로 시작(공백 포함)
            if re.match(r'^\d{3}-', word1):
                merged, rect, end_idx = merge_to_N(words, i)
                if merged and merged not in already:
                    highlight(page, rect, color=(0, 1, 0), opacity=0.3)
                    already.add(merged)
                    all_line_list.append([merged])
                    print(f"LINE: {merged}")
                i = end_idx + 1
                continue
            # 2. 123(한 단어) + '-'(다음 단어) 조합
            elif re.fullmatch(r'\d{3}', word1):
                if i+1 < n and words[i+1][4].strip() == '-':
                    merged, rect, end_idx = merge_to_N(words, i)
                    if merged and merged not in already:
                        highlight(page, rect, color=(0, 1, 0), opacity=0.3)
                        already.add(merged)
                        all_line_list.append([merged])
                        print(f"LINE: {merged}")
                    i = end_idx + 1
                    continue
            i += 1

        # 세로(문자열 단위)에서도 동일하게 조합
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
                i = 0
                while i < len(chars_only)-3:
                    # 3숫자+-
                    if (re.fullmatch(r'\d', chars_only[i]) and
                        re.fullmatch(r'\d', chars_only[i+1]) and
                        re.fullmatch(r'\d', chars_only[i+2]) and
                        chars_only[i+3] == '-'):
                        # N까지 병합
                        merged = ''
                        slice_end = i
                        for j in range(i, len(chars_only)):
                            merged += chars_only[j]
                            if chars_only[j] == 'N':
                                slice_end = j
                                break
                        else:
                            i += 1
                            continue
                        x0s = [boxes[j][1] for j in range(i, slice_end+1)]
                        y0s = [boxes[j][0] for j in range(i, slice_end+1)]
                        x1s = [boxes[j][2] for j in range(i, slice_end+1)]
                        y1s = [boxes[j][3] for j in range(i, slice_end+1)]
                        rect = fitz.Rect(min(x0s), min(y0s), max(x1s), max(y1s))
                        if merged and merged not in already:
                            highlight(page, rect, color=(0, 1, 0), opacity=0.3)
                            already.add(merged)
                            all_line_list.append([merged])
                            print(f"세로 LINE: {merged}")
                        i = slice_end + 1
                        continue
                    i += 1
        except Exception:
            pass

    doc.save(output_pdf)
    doc.close()
    print(f"✅ 3자리+-, N까지 LINE NO 하이라이트 → {output_pdf}")

    # ---------- CSV 저장 ----------
    if all_line_list:
        with open(line_csv, "w", newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(["LINE"])
            writer.writerows(all_line_list)
        print(f"✅ 모든 LINE을 {line_csv}에 저장 완료")
    else:
        print(f"❗ 하이라이트된 LINE 없음")
