import fitz  # PyMuPDF
import re
import math
import os
from collections import defaultdict
from tkinter import Tk, filedialog
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import Font, Border, Side, PatternFill
from openpyxl.utils import get_column_letter

# ============================================
# 통합 LINE/VALVE 추출 시스템
# 5가지 PDF 형식을 모두 처리 가능
# Excel + PDF 저장 방식
# ============================================

# -------------- 날짜 문자열 --------------
today_str = datetime.now().strftime("%Y%m%d")

# -------------- 파일 다중 선택 --------------
root = Tk()
root.withdraw()
current_dir = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else os.getcwd()
pdf_paths = filedialog.askopenfilenames(
    title="PDF 파일들을 선택하세요",
    filetypes=[("PDF files", "*.pdf")],
    initialdir=current_dir
)
if not pdf_paths:
    print("PDF 파일이 선택되지 않았습니다.")
    exit()

# -------------- 패턴 정의 (TYPE 1,2: LineValvListCreate, BLUE_LINELIST) --------------
P1_PATTERN = re.compile(r'^(00|11|21|22)[A-Za-z0-9]{0,7}$', re.IGNORECASE)
P2_PATTERN = re.compile(r'^(BR|AA)[A-Za-z0-9]{0,8}$', re.IGNORECASE)
P3_DN_PATTERN = re.compile(r'^DN.{0,11}$', re.IGNORECASE)
P3_H_PATTERN = re.compile(r'^H.{0,11}$', re.IGNORECASE)

# -------------- 패턴 정의 (TYPE 3: LINELIST_OTHER) --------------
VALVNO_PATTERN = re.compile(r'^(\(?-?V-?)\d{3,5}', re.IGNORECASE)
LINE_PATTERN1 = re.compile(r'^\d{3}-?[A-Z]\d*$')
LINE_PATTERN2 = re.compile(r'^\d{3}-[A-Z]')
LINE_PATTERN3 = re.compile(r'^\d{3}-?[A-Z]\d*.*N')

# -------------- 패턴 정의 (TYPE 4,5: SPECIAL) --------------
SPECIAL_PATTERN = re.compile(r'^(AJ|BJ|AT)[0-9]{3,4}', re.IGNORECASE)

# -------------- Excel 스타일 정의 --------------
BOLD = Font(bold=True)
THIN_BORDER = Border(
    left=Side(style="thin"), right=Side(style="thin"),
    top=Side(style="thin"), bottom=Side(style="thin"),
)
# 반투명 느낌의 연한 색상
FILL_BLUE_SOFT = PatternFill(fill_type="solid", start_color="FF9999FF", end_color="FF9999FF")
FILL_RED_SOFT = PatternFill(fill_type="solid", start_color="FFFF9999", end_color="FFFF9999")

# -------------- 전체 통합 리스트 (여러 PDF 처리용) --------------
all_LINE = []
all_VALVE = []
all_SPECIAL = []
all_line_seen = defaultdict(int)
all_valve_seen = defaultdict(int)
all_special_seen = defaultdict(int)

# -------------- 헬퍼 함수 --------------
def highlight(page, rect, color, opacity=0.4):
    """하이라이트 추가"""
    if rect.get_area() == 0: 
        return
    try:
        annot = page.add_rect_annot(rect)
        annot.set_colors(stroke=color, fill=color)
        annot.set_opacity(opacity)
        annot.update()
    except:
        pass

def center(rect):
    """사각형의 중심점 계산"""
    return ((rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2)

def distance(r1, r2):
    """두 사각형 간 거리 계산"""
    c1 = center(r1)
    c2 = center(r2)
    return math.hypot(c1[0] - c2[0], c1[1] - c2[1])

def normalize_p3(*words):
    """P3 값 정규화"""
    return '-'.join(w.replace(' ', '-') for w in words if w).replace('--', '-')

def natural_key(text):
    """자연 정렬을 위한 키 생성"""
    return [int(s) if s.isdigit() else s.lower() for s in re.split(r'(\d+)', text)]

def normalize_quote_before_slash(text):
    """슬래시 전 따옴표 정규화"""
    text = str(text)
    if "/" not in text:
        return text.replace('"', '')
    left, right = text.split("/", 1)
    left = left.replace('"', '')
    right = right.replace('"', '')
    return f"{left}/{right}"

def apply_full_border(ws):
    """워크시트 전체에 테두리 적용"""
    max_row = ws.max_row
    max_col = ws.max_column
    for r in range(1, max_row + 1):
        for c in range(1, max_col + 1):
            ws.cell(row=r, column=c).border = THIN_BORDER

def autofit_columns(ws, min_width=8, pad=2, scale=1.2):
    """열 너비 자동 조정"""
    max_len_by_col = defaultdict(int)
    for r in ws.iter_rows(values_only=True):
        for idx, val in enumerate(r, start=1):
            txt = "" if val is None else str(val)
            if len(txt) > max_len_by_col[idx]:
                max_len_by_col[idx] = len(txt)
    for col_idx, max_len in max_len_by_col.items():
        width = max(min_width, int(max_len * scale) + pad)
        ws.column_dimensions[get_column_letter(col_idx)].width = width

# -------------- TYPE 3 전용 함수 --------------
def merge_to_N(words, start):
    """N까지 단어 병합"""
    text_acc = ""
    rects = []
    end = start
    found = False
    for j in range(start, len(words)):
        t = words[j][4]
        if text_acc: 
            text_acc += " "
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
    """VALVE NO 시작 패턴 확인"""
    word = word.upper()
    return (
        word.startswith('(-V') or word.startswith('(V-') or
        word.startswith('-V-') or word.startswith('-V') or word.startswith('V-')
    )

def is_valvno_any(word):
    """VALVE NO 패턴 확인"""
    wordu = word.upper()
    return (
        re.match(r'^(\(?-?V-?)\d{3,5}', wordu) or
        (wordu.startswith('3/4') and 'V-' in wordu)
    )

def find_nearby_pv(words, idx, max_dist=30):
    """근처 PV 값 찾기"""
    x0, y0, x1, y1, _ = words[idx][:5]
    center = ((x0+x1)/2, (y0+y1)/2)
    candidates = []
    for j, w in enumerate(words):
        if j == idx: 
            continue
        tx0, ty0, tx1, ty1, ttxt = w[:5]
        ttxt_strip = ttxt.strip()
        if "-" not in ttxt_strip or len(ttxt_strip) > 8: 
            continue
        tcenter = ((tx0+tx1)/2, (ty0+ty1)/2)
        dx, dy = tcenter[0] - center[0], tcenter[1] - center[1]
        if abs(dx) < max_dist and abs(dy) < max_dist:
            dist = (dx*dx + dy*dy)**0.5
            candidates.append((dist, j, ttxt_strip, fitz.Rect(tx0, ty0, tx1, ty1)))
    if candidates:
        candidates.sort()
        return candidates[0][2], candidates[0][3]
    return None, None

# -------------- TYPE 4 전용 함수 --------------
def extract_vertical_words(page, min_len=4, gap_tol=2.2):
    """세로 텍스트 추출"""
    try:
        chars = page.get_text("chars")
    except Exception:
        return []
    columns = defaultdict(list)
    for char_info in chars:
        if len(char_info) < 5:
            continue
        x0, y0, x1, y1, ch = char_info[:5]
        if not ch.strip(): 
            continue
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

# -------------- 메인 처리 함수 --------------
def process_type1_2(page, words, line_list, valve_list, line_seen, valve_seen, line_no_rects, valve_no_rects, base_name, page_num):
    """TYPE 1,2: P1-P2-P3 패턴 처리"""
    n = len(words)
    processed = set()
    
    for i, w in enumerate(words):
        if i in processed:
            continue
            
        text = w[4].strip().replace(" ", "")
        if not P1_PATTERN.match(text):
            continue
        
        p1 = text
        p1_rect = fitz.Rect(w[:4])
        highlight(page, p1_rect, color=(0, 1, 0), opacity=0.2)
        
        # P2 찾기
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
        processed.add(i)
        
        # BR인 경우 P3 찾기
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
                
                line_seen[line_no] += 1
                occ = line_seen[line_no]
                line_list.append([line_no, occ])
                line_no_rects[line_no].append((page_num - 1, found_p3_rect))
                
                all_line_seen[line_no] += 1
                all_occ = all_line_seen[line_no]
                all_LINE.append([line_no, all_occ])
                
                print(f"[{base_name}] LINE NO: {line_no}")
        
        # AA인 경우 VALVE
        elif found_p2.upper().startswith("AA"):
            valve_no = f"{p1}-{found_p2.replace(' ', '-')}"
            
            valve_seen[valve_no] += 1
            occ = valve_seen[valve_no]
            valve_list.append([valve_no, occ])
            valve_no_rects[valve_no].append((page_num - 1, found_p2_rect))
            
            all_valve_seen[valve_no] += 1
            all_occ = all_valve_seen[valve_no]
            all_VALVE.append([valve_no, all_occ])
            
            print(f"[{base_name}] VALVE NO: {valve_no}")

def process_type3(page, words, line_list, valve_list, line_seen, valve_seen, line_no_rects, valve_no_rects, base_name, page_num):
    """TYPE 3: OTHER 패턴 처리"""
    i = 0
    while i < len(words):
        x0, y0, x1, y1, text = words[i][:5]
        word1 = text.strip()
        
        # LINE 처리
        if re.match(r'^\d{3}-?[A-Z]\d*$', word1) or re.match(r'^\d{3}-[A-Z]', word1):
            merged, rects, end_idx = merge_to_N(words, i)
            if merged:
                for r in rects:
                    highlight(page, r, color=(0, 1, 0), opacity=0.3)
                
                line_seen[merged] += 1
                occ = line_seen[merged]
                line_list.append([merged, occ])
                line_no_rects[merged].append((page_num-1, rects))
                
                all_line_seen[merged] += 1
                all_occ = all_line_seen[merged]
                all_LINE.append([merged, all_occ])
                
                print(f"[{base_name}] LINE NO: {merged}")
            i = end_idx + 1
            continue
            
        elif re.match(r'^\d{3}-?[A-Z]\d*.*N', word1):
            rect = fitz.Rect(x0, y0, x1, y1)
            highlight(page, rect, color=(0, 1, 0), opacity=0.3)
            
            line_seen[word1] += 1
            occ = line_seen[word1]
            line_list.append([word1, occ])
            line_no_rects[word1].append((page_num-1, [rect]))
            
            all_line_seen[word1] += 1
            all_occ = all_line_seen[word1]
            all_LINE.append([word1, all_occ])
            
            print(f"[{base_name}] LINE NO: {word1}")
        
        # VALVE 처리
        if is_valvno_any(word1):
            valv_final = word1
            pv_val, pv_rect = None, None
            if is_valvno_start(word1):
                pv_val, pv_rect = find_nearby_pv(words, i)
                if pv_val:
                    valv_final = pv_val + word1
            
            if pv_rect:
                highlight(page, pv_rect, color=(0.5, 0, 1), opacity=0.15)
            highlight(page, fitz.Rect(x0, y0, x1, y1), color=(0.5, 0, 1), opacity=0.3)
            
            valve_seen[valv_final] += 1
            occ = valve_seen[valv_final]
            valve_list.append([valv_final, occ])
            valve_no_rects[valv_final].append((page_num-1, [fitz.Rect(x0, y0, x1, y1)]))
            
            all_valve_seen[valv_final] += 1
            all_occ = all_valve_seen[valv_final]
            all_VALVE.append([valv_final, all_occ])
            
            print(f"[{base_name}] VALVNO: {valv_final}")
        i += 1

def process_type4(page, words, line_list, valve_list, special_list, line_seen, valve_seen, special_seen, 
                  line_no_rects, valve_no_rects, special_no_rects, base_name, page_num):
    """TYPE 4: TBN 패턴 처리 (세로 텍스트 포함)"""
    # 세로 단어 추출
    vert_words = extract_vertical_words(page)
    rect_map = {}
    
    for vtxt, vrects in vert_words:
        t_clean = vtxt.strip().replace(" ", "")
        if len(t_clean) < 4: 
            continue
        rect_map[vtxt] = vrects
        # 가로 단어와 중복 방지
        words_h = page.get_text("words")
        if not any(abs(vrects[0].x0 - w[0]) < 0.1 and abs(vrects[0].y0 - w[1]) < 0.1 for w in words_h):
            words.append([vrects[0].x0, vrects[0].y0, vrects[-1].x1, vrects[-1].y1, vtxt])
    
    i = 0
    while i < len(words):
        x0, y0, x1, y1, text = words[i][:5]
        clean_text = text.strip().replace(" ", "")
        if len(clean_text) < 4:
            i += 1
            continue
        
        prefix4 = clean_text[:4].upper() if len(clean_text) >= 4 else ""
        rect = fitz.Rect(x0, y0, x1, y1)
        
        # LINE NO (따옴표 포함)
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
            else:
                highlight(page, rect, color=(0, 1, 0), opacity=0.2)
            
            line_seen[full_line] += 1
            occ = line_seen[full_line]
            line_list.append([full_line, occ])
            line_no_rects[full_line].append((page_num - 1, rect))
            
            all_line_seen[full_line] += 1
            all_occ = all_line_seen[full_line]
            all_LINE.append([full_line, all_occ])
            
            print(f"[{base_name}] LINE NO: {full_line}")
            i = j - 1
        
        # VALVE NO
        elif (len(prefix4) > 0 and prefix4[0] == 'V' and re.match(r'^V\d{3,4}', clean_text)) or \
             (re.match(r'^\d{3}', clean_text) and '-V' in clean_text):
            full_valve = clean_text
            if text in rect_map:
                for r in rect_map[text]:
                    highlight(page, r, color=(1, 0, 1), opacity=0.2)
            else:
                highlight(page, rect, color=(1, 0, 1), opacity=0.2)
            
            valve_seen[full_valve] += 1
            occ = valve_seen[full_valve]
            valve_list.append([full_valve, occ])
            valve_no_rects[full_valve].append((page_num - 1, rect))
            
            all_valve_seen[full_valve] += 1
            all_occ = all_valve_seen[full_valve]
            all_VALVE.append([full_valve, all_occ])
            
            print(f"[{base_name}] VALVE NO: {full_valve}")
        
        # SPECIAL NO
        elif SPECIAL_PATTERN.match(clean_text):
            special_seen[clean_text] += 1
            occ = special_seen[clean_text]
            special_list.append([clean_text, occ])
            special_no_rects[clean_text].append((page_num - 1, rect))
            
            all_special_seen[clean_text] += 1
            all_occ = all_special_seen[clean_text]
            all_SPECIAL.append([clean_text, all_occ])
            
            print(f"[{base_name}] SPECIAL NO: {clean_text}")
        
        i += 1

def process_type5(page, words, line_list, valve_list, special_list, line_seen, valve_seen, special_seen,
                  line_no_rects, valve_no_rects, special_no_rects, base_name, page_num):
    """TYPE 5: YH12 패턴 처리"""
    for w in words:
        x0, y0, x1, y1, text = w[:5]
        clean_text = text.strip().replace(" ", "")
        if len(clean_text) < 4:
            continue
        
        prefix4 = clean_text[:4].upper()
        rect = fitz.Rect(x0, y0, x1, y1)
        
        # LINE NO (특수 패턴)
        if len(prefix4) >= 4 and prefix4[3] == 'A' and len(clean_text) >= 9:
            full_line = f"1-62100-{clean_text}"
            highlight(page, rect, color=(0, 1, 0), opacity=0.2)
            
            line_seen[full_line] += 1
            occ = line_seen[full_line]
            line_list.append([full_line, occ])
            line_no_rects[full_line].append((page_num - 1, rect))
            
            all_line_seen[full_line] += 1
            all_occ = all_line_seen[full_line]
            all_LINE.append([full_line, all_occ])
            
            print(f"[{base_name}] LINE NO: {full_line}")
        
        # VALVE NO
        elif prefix4[0] == 'V':
            full_valve = f"1-62100-{clean_text}"
            highlight(page, rect, color=(1, 0, 1), opacity=0.2)
            
            valve_seen[full_valve] += 1
            occ = valve_seen[full_valve]
            valve_list.append([full_valve, occ])
            valve_no_rects[full_valve].append((page_num - 1, rect))
            
            all_valve_seen[full_valve] += 1
            all_occ = all_valve_seen[full_valve]
            all_VALVE.append([full_valve, all_occ])
            
            print(f"[{base_name}] VALVE NO: {full_valve}")
        
        # SPECIAL NO
        elif SPECIAL_PATTERN.match(clean_text):
            highlight(page, rect, color=(1, 0.5, 0), opacity=0.2)
            
            special_seen[clean_text] += 1
            occ = special_seen[clean_text]
            special_list.append([clean_text, occ])
            special_no_rects[clean_text].append((page_num - 1, rect))
            
            all_special_seen[clean_text] += 1
            all_occ = all_special_seen[clean_text]
            all_SPECIAL.append([clean_text, all_occ])
            
            print(f"[{base_name}] SPECIAL NO: {clean_text}")

def process_type6_simple(page, words, line_list, valve_list, special_list, line_seen, valve_seen, special_seen,
                         line_no_rects, valve_no_rects, special_no_rects, base_name, page_num):
    """TYPE 6: 유첨 코드의 단순 패턴 처리"""
    valve_pattern = re.compile(r'AA[0-9]{3,4}', re.IGNORECASE)
    
    for w in words:
        x0, y0, x1, y1, text = w[:5]
        if not text or not str(text).strip():
            continue
        p1 = str(text).strip().split()[0].upper()
        rect = fitz.Rect(x0, y0, x1, y1)
        
        # BR+DN 패턴
        if "BR" in p1 and "DN" in p1:
            dn_index = p1.find("DN")
            if dn_index != -1:
                after_dn = p1[dn_index:].split()[0]
                line_no = p1[:dn_index] + after_dn
                
                line_seen[line_no] += 1
                occ = line_seen[line_no]
                line_list.append([line_no, occ])
                line_no_rects[line_no].append((page_num - 1, rect))
                
                all_line_seen[line_no] += 1
                all_occ = all_line_seen[line_no]
                all_LINE.append([line_no, all_occ])
                
                highlight(page, rect, color=(0, 1, 0), opacity=0.2)
                print(f"[{base_name}] LINE NO: {line_no}")
        
        # AA 패턴
        elif valve_pattern.search(p1):
            valve_seen[p1] += 1
            occ = valve_seen[p1]
            valve_list.append([p1, occ])
            valve_no_rects[p1].append((page_num - 1, rect))
            
            all_valve_seen[p1] += 1
            all_occ = all_valve_seen[p1]
            all_VALVE.append([p1, all_occ])
            
            highlight(page, rect, color=(0, 1, 0), opacity=0.2)
            print(f"[{base_name}] VALVE NO: {p1}")
        
        # SPECIAL 패턴
        elif SPECIAL_PATTERN.search(p1):
            special_seen[p1] += 1
            occ = special_seen[p1]
            special_list.append([p1, occ])
            special_no_rects[p1].append((page_num - 1, rect))
            
            all_special_seen[p1] += 1
            all_occ = all_special_seen[p1]
            all_SPECIAL.append([p1, all_occ])
            
            highlight(page, rect, color=(0, 1, 0), opacity=0.2)
            print(f"[{base_name}] SPECIAL NO: {p1}")

# -------------- 각 PDF 파일 처리 --------------
for pdf_idx, input_pdf_path in enumerate(pdf_paths):
    input_pdf_name = os.path.basename(input_pdf_path)
    base_name = os.path.splitext(input_pdf_name)[0]
    folder = os.path.dirname(input_pdf_path)
    
    # 파일 이름 설정 (Excel과 PDF만)
    output_pdf = os.path.join(folder, f"OUT_{base_name}_{today_str}.PDF")
    output_xlsx = os.path.join(folder, f"{base_name}_LIST_{today_str}.XLSX")
    
    doc = fitz.open(input_pdf_path)
    
    # [value, occurrence]
    line_list = []
    valve_list = []
    special_list = []
    
    line_seen = defaultdict(int)
    valve_seen = defaultdict(int)
    special_seen = defaultdict(int)
    
    line_no_rects = defaultdict(list)
    valve_no_rects = defaultdict(list)
    special_no_rects = defaultdict(list)
    
    print(f"\n{'='*50}")
    print(f"처리 중 ({pdf_idx+1}/{len(pdf_paths)}): {base_name}")
    print(f"{'='*50}")
    
    for page_num, page in enumerate(doc, 1):
        print(f"페이지 {page_num} 처리 중...")
        
        # 기본 단어 추출
        words = page.get_text("words")
        
        # 모든 TYPE 처리 (순차적으로 시도)
        # TYPE 1,2: P1-P2-P3 패턴
        process_type1_2(page, words, line_list, valve_list, line_seen, valve_seen, 
                       line_no_rects, valve_no_rects, base_name, page_num)
        
        # TYPE 3: OTHER 패턴
        process_type3(page, words, line_list, valve_list, line_seen, valve_seen, 
                     line_no_rects, valve_no_rects, base_name, page_num)
        
        # TYPE 4: TBN 패턴 (세로 텍스트)
        process_type4(page, words, line_list, valve_list, special_list, line_seen, valve_seen, special_seen,
                     line_no_rects, valve_no_rects, special_no_rects, base_name, page_num)
        
        # TYPE 5: YH12 패턴
        process_type5(page, words, line_list, valve_list, special_list, line_seen, valve_seen, special_seen,
                     line_no_rects, valve_no_rects, special_no_rects, base_name, page_num)
        
        # TYPE 6: 유첨 코드 패턴
        process_type6_simple(page, words, line_list, valve_list, special_list, line_seen, valve_seen, special_seen,
                            line_no_rects, valve_no_rects, special_no_rects, base_name, page_num)
    
    # 중복 집계
    line_counts = defaultdict(int)
    for val, _ in line_list:
        line_counts[val] += 1
    valve_counts = defaultdict(int)
    for val, _ in valve_list:
        valve_counts[val] += 1
    special_counts = defaultdict(int)
    for val, _ in special_list:
        special_counts[val] += 1
    
    # PDF 중복 하이라이트
    for key, rects in valve_no_rects.items():
        if valve_counts[key] > 1:
            for idx, (pg, rect) in enumerate(rects):
                color = (0, 0, 1) if idx == 0 else (1, 0, 0)
                if isinstance(rect, list):
                    for r in rect:
                        highlight(doc[pg], r, color=color, opacity=0.4)
                else:
                    highlight(doc[pg], rect, color=color, opacity=0.4)
    
    for key, rects in line_no_rects.items():
        if line_counts[key] > 1:
            for idx, (pg, rect) in enumerate(rects):
                color = (0, 0, 1) if idx == 0 else (1, 0, 0)
                if isinstance(rect, list):
                    for r in rect:
                        highlight(doc[pg], r, color=color, opacity=0.4)
                else:
                    highlight(doc[pg], rect, color=color, opacity=0.4)
    
    for key, rects in special_no_rects.items():
        if special_counts[key] > 1:
            for idx, (pg, rect) in enumerate(rects):
                color = (0, 0, 1) if idx == 0 else (1, 0, 0)
                highlight(doc[pg], rect, color=color, opacity=0.4)
    
    # ---------- XLSX 작성 ----------
    wb = Workbook()
    ws = wb.active
    ws.title = "ALL NO"
    
    headers = ["LINE NO", "중복", "VALVE NO", "중복", "SPECIAL NO", "중복"]
    ws.append(headers)
    for c in ws[1]:
        c.font = BOLD
    
    # 정렬 및 중복 표시
    line_sorted = sorted(line_list, key=lambda x: natural_key(x[0]))
    valve_sorted = sorted(valve_list, key=lambda x: natural_key(x[0]))
    special_sorted = sorted(special_list, key=lambda x: natural_key(x[0]))
    
    line_sorted = [[normalize_quote_before_slash(v), ("중복" if line_counts[v] > 1 else ""), occ] 
                   for v, occ in line_sorted]
    valve_sorted = [[normalize_quote_before_slash(v), ("중복" if valve_counts[v] > 1 else ""), occ] 
                    for v, occ in valve_sorted]
    special_sorted = [[normalize_quote_before_slash(v), ("중복" if special_counts[v] > 1 else ""), occ] 
                      for v, occ in special_sorted]
    
    # 리스트 길이 맞추기
    max_len = max(len(line_sorted), len(valve_sorted), len(special_sorted))
    while len(line_sorted) < max_len:
        line_sorted.append(["", "", 0])
    while len(valve_sorted) < max_len:
        valve_sorted.append(["", "", 0])
    while len(special_sorted) < max_len:
        special_sorted.append(["", "", 0])
    
    # 데이터 쓰기 및 색상 적용
    for i in range(max_len):
        row_idx = ws.max_row + 1
        L_val, L_dup, L_occ = line_sorted[i]
        V_val, V_dup, V_occ = valve_sorted[i]
        S_val, S_dup, S_occ = special_sorted[i]
        
        ws.append([L_val, L_dup, V_val, V_dup, S_val, S_dup])
        
        # 색상 지정: 반투명 느낌의 연한 색
        if L_val and line_counts[L_val.replace('"', '')] > 1:
            fill = FILL_BLUE_SOFT if L_occ == 1 else FILL_RED_SOFT
            ws.cell(row=row_idx, column=1).fill = fill
            ws.cell(row=row_idx, column=2).fill = fill
        if V_val and valve_counts[V_val.replace('"', '')] > 1:
            fill = FILL_BLUE_SOFT if V_occ == 1 else FILL_RED_SOFT
            ws.cell(row=row_idx, column=3).fill = fill
            ws.cell(row=row_idx, column=4).fill = fill
        if S_val and special_counts[S_val.replace('"', '')] > 1:
            fill = FILL_BLUE_SOFT if S_occ == 1 else FILL_RED_SOFT
            ws.cell(row=row_idx, column=5).fill = fill
            ws.cell(row=row_idx, column=6).fill = fill
    
    autofit_columns(ws)
    apply_full_border(ws)
    
    wb.save(output_xlsx)
    print(f"📊 XLSX(연한 중복 색/자동너비/테두리) 저장 완료 → {output_xlsx}")
    
    doc.save(output_pdf)
    doc.close()
    print(f"📄 하이라이트 PDF 저장 완료 → {output_pdf}")
    
    # 결과 요약
    print(f"\n{'='*50}")
    print(f"처리 완료: {base_name}")
    print(f"- LINE NO: {len(line_list)}개 (중복 {sum(1 for c in line_counts.values() if c > 1)}개)")
    print(f"- VALVE NO: {len(valve_list)}개 (중복 {sum(1 for c in valve_counts.values() if c > 1)}개)")
    print(f"- SPECIAL NO: {len(special_list)}개 (중복 {sum(1 for c in special_counts.values() if c > 1)}개)")
    print(f"{'='*50}\n")

# ---------- 통합 XLSX (여러 PDF 처리 시) ----------
if len(pdf_paths) > 1 and any([all_LINE, all_VALVE, all_SPECIAL]):
    first_pdf = os.path.splitext(os.path.basename(pdf_paths[0]))[0]
    all_xlsx = os.path.join(os.path.dirname(pdf_paths[0]),
                            f"ALL_{first_pdf}_LIST_{today_str}.XLSX")
    
    all_line_counts = defaultdict(int)
    for v, _occ in all_LINE:
        all_line_counts[v] += 1
    all_valve_counts = defaultdict(int)
    for v, _occ in all_VALVE:
        all_valve_counts[v] += 1
    all_special_counts = defaultdict(int)
    for v, _occ in all_SPECIAL:
        all_special_counts[v] += 1
    
    line_all_sorted = sorted(all_LINE, key=lambda x: natural_key(x[0]))
    valve_all_sorted = sorted(all_VALVE, key=lambda x: natural_key(x[0]))
    special_all_sorted = sorted(all_SPECIAL, key=lambda x: natural_key(x[0]))
    
    line_all_sorted = [[normalize_quote_before_slash(v), ("중복" if all_line_counts[v] > 1 else ""), occ] 
                       for v, occ in line_all_sorted]
    valve_all_sorted = [[normalize_quote_before_slash(v), ("중복" if all_valve_counts[v] > 1 else ""), occ] 
                        for v, occ in valve_all_sorted]
    special_all_sorted = [[normalize_quote_before_slash(v), ("중복" if all_special_counts[v] > 1 else ""), occ] 
                          for v, occ in special_all_sorted]
    
    max_len = max(len(line_all_sorted), len(valve_all_sorted), len(special_all_sorted))
    while len(line_all_sorted) < max_len:
        line_all_sorted.append(["", "", 0])
    while len(valve_all_sorted) < max_len:
        valve_all_sorted.append(["", "", 0])
    while len(special_all_sorted) < max_len:
        special_all_sorted.append(["", "", 0])
    
    wb_all = Workbook()
    ws_all = wb_all.active
    ws_all.title = "ALL NO"
    
    headers = ["LINE NO", "중복", "VALVE NO", "중복", "SPECIAL NO", "중복"]
    ws_all.append(headers)
    for c in ws_all[1]:
        c.font = BOLD
    
    for i in range(max_len):
        row_idx = ws_all.max_row + 1
        L_val, L_dup, L_occ = line_all_sorted[i]
        V_val, V_dup, V_occ = valve_all_sorted[i]
        S_val, S_dup, S_occ = special_all_sorted[i]
        
        ws_all.append([L_val, L_dup, V_val, V_dup, S_val, S_dup])
        
        if L_val and all_line_counts[L_val.replace('"', '')] > 1:
            fill = FILL_BLUE_SOFT if L_occ == 1 else FILL_RED_SOFT
            ws_all.cell(row=row_idx, column=1).fill = fill
            ws_all.cell(row=row_idx, column=2).fill = fill
        if V_val and all_valve_counts[V_val.replace('"', '')] > 1:
            fill = FILL_BLUE_SOFT if V_occ == 1 else FILL_RED_SOFT
            ws_all.cell(row=row_idx, column=3).fill = fill
            ws_all.cell(row=row_idx, column=4).fill = fill
        if S_val and all_special_counts[S_val.replace('"', '')] > 1:
            fill = FILL_BLUE_SOFT if S_occ == 1 else FILL_RED_SOFT
            ws_all.cell(row=row_idx, column=5).fill = fill
            ws_all.cell(row=row_idx, column=6).fill = fill
    
    autofit_columns(ws_all)
    apply_full_border(ws_all)
    
    wb_all.save(all_xlsx)
    print(f"✅ 통합 XLSX(연한 중복 색/자동너비/테두리) 생성됨 → {all_xlsx}")

print("\n" + "="*70)
print("모든 PDF 파일 처리 완료!")
print("📊 Excel 파일과 📄 PDF 파일이 저장되었습니다.")
print("="*70)