#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import ezdxf
import tkinter as tk
from tkinter import filedialog
from datetime import datetime
from collections import defaultdict
import math

try:
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
except ImportError:
    print("openpyxl 라이브러리가 필요합니다.")
    print("설치 명령: pip install openpyxl")
    raise SystemExit(1)

# ─────────────────────────────────────────────────────────
# 유틸: 좌표/텍스트 안전 추출
# ─────────────────────────────────────────────────────────
def get_xy(e):
    try:
        if hasattr(e, 'dxf') and hasattr(e.dxf, 'insert'):
            ins = e.dxf.insert
            if hasattr(ins, 'x') and hasattr(ins, 'y'):
                return float(ins.x), float(ins.y)
            elif isinstance(ins, (tuple, list)) and len(ins) >= 2:
                return float(ins[0]), float(ins[1])
        elif hasattr(e, 'insert'):
            ins = e.insert
            if isinstance(ins, (tuple, list)) and len(ins) >= 2:
                return float(ins[0]), float(ins[1])
    except Exception:
        pass
    return 0.0, 0.0

def _normalize_spaces(text: str) -> str:
    # 문자열로 표현된 유니코드 이스케이프 처리 (\U+XXXX → ' ')
    text = re.sub(r'\\U\+[0-9A-Fa-f]{4}', ' ', text)
    # 다양한 유니코드 공백을 일반 공백으로
    unicode_spaces = [
        '\u2000', '\u2001', '\u2002', '\u2003', '\u2004', '\u2005',
        '\u2006', '\u2007', '\u2008', '\u2009', '\u200A', '\u202F',
        '\u205F', '\u3000', '\xa0', '\u00A0', '\u1680', '\u180E',
        '\u2028', '\u2029', '\u200B', '\u200C', '\u200D', '\uFEFF',
    ]
    for sp in unicode_spaces:
        text = text.replace(sp, ' ')
    # 탭/줄바꿈 제거
    text = text.replace('\t', ' ').replace('\n', ' ').replace('\r', ' ')
    # 연속공백 축소 (2개 이상의 공백은 유지)
    text = re.sub(r' {3,}', '  ', text)  # 3개 이상의 공백을 2개로
    # 제어문자 제거
    import unicodedata
    text = ''.join(ch for ch in text if not unicodedata.category(ch).startswith('C'))
    return text.strip()

def get_text(e):
    try:
        text = ''
        if hasattr(e, 'dxf') and hasattr(e.dxf, 'text'):
            text = e.dxf.text
        elif hasattr(e, 'text'):
            text = e.text
        if text:
            return _normalize_spaces(str(text))
    except Exception:
        pass
    return ''

# ─────────────────────────────────────────────────────────
# 모델공간 + 블록(INSERT) 내부 TEXT/MTEXT 수집 (절대좌표화)
# ─────────────────────────────────────────────────────────
def get_text_from_blocks(doc, msp):
    all_texts = []
    # 1) 모델공간의 TEXT/MTEXT
    for e in msp.query('TEXT MTEXT'):
        txt = get_text(e)
        if not txt:
            continue
        x, y = get_xy(e)
        all_texts.append((x, y, txt, 'normal'))

    # 2) INSERT 블록 내부 TEXT/MTEXT
    for ins in msp.query('INSERT'):
        try:
            ip = ins.dxf.insert
            x_scale = getattr(ins.dxf, 'xscale', 1.0) or 1.0
            y_scale = getattr(ins.dxf, 'yscale', 1.0) or 1.0
            rotation = getattr(ins.dxf, 'rotation', 0.0) or 0.0
            bname = ins.dxf.name
            if bname not in doc.blocks:
                continue
            block = doc.blocks[bname]
            rad = math.radians(rotation)
            cos_r, sin_r = math.cos(rad), math.sin(rad)
            for ent in block:
                if ent.dxftype() not in ('TEXT', 'MTEXT'):
                    continue
                txt = get_text(ent)
                if not txt:
                    continue
                lx, ly = get_xy(ent)
                if rotation != 0.0:
                    ax = ip[0] + (lx * cos_r - ly * sin_r) * x_scale
                    ay = ip[1] + (lx * sin_r + ly * cos_r) * y_scale
                else:
                    ax = ip[0] + lx * x_scale
                    ay = ip[1] + ly * y_scale
                all_texts.append((ax, ay, txt, 'block'))
        except Exception:
            continue
    return all_texts

# ─────────────────────────────────────────────────────────
# 영역/근접 검색
# ─────────────────────────────────────────────────────────
def find_texts_in_area_with_blocks(doc, msp, x_min, x_max, y_min, y_max):
    texts = []
    for x, y, txt, src in get_text_from_blocks(doc, msp):
        if x_min <= x <= x_max and y_min <= y <= y_max and txt:
            texts.append((x, y, txt))
    texts.sort(key=lambda t: -t[1])  # Y 내림차순
    return [t[2] for t in texts]

def find_text_in_rect_with_blocks(doc, msp, x_min, x_max, y_min, y_max, condition=None):
    for x, y, txt, src in get_text_from_blocks(doc, msp):
        if x_min <= x <= x_max and y_min <= y <= y_max and txt:
            if condition is None or condition(txt):
                return txt
    return None

def find_text_near_point_with_blocks(doc, msp, cx, cy, tol_x, tol_y, condition=None):
    return find_text_in_rect_with_blocks(doc, msp, cx - tol_x, cx + tol_x, cy - tol_y, cy + tol_y, condition)

# ─────────────────────────────────────────────────────────
# 파싱/정리 유틸
# ─────────────────────────────────────────────────────────
def extract_number(text):
    if not text:
        return 0.0
    m = re.findall(r'[\d.]+', str(text))
    if not m:
        return 0.0
    try:
        return float(m[0])
    except ValueError:
        return 0.0

def is_numeric_text(s):
    if s is None:
        return False
    s = str(s).strip()
    return bool(re.fullmatch(r'\d+(?:\.\d+)?', s))

def is_subheader(text):
    if not text:
        return False
    u = text.strip().upper()
    return u in {'NO.', 'DESCRIPTION', '(DN)', '(M,EA)', '(KG)', "Q'TY", 'QTY', 'WEIGHT', 'SIZE', 'PT', 'COMPONENT'}

def clean_text_for_excel(text):
    if not text:
        return ''
    # 연속 공백은 하나로 변경
    return ' '.join(str(text).split())

def parse_combined_row_data(text):
    """ '1 FLANGE, A105, 300  12  4.5' 같은 텍스트를 파싱 (공백 2개 이상으로 구분) """
    res = {'pt': '', 'comp': '', 'size': '', 'qty': '', 'weight': '', 'sch': ''}
    if not text:
        return res
    
    # 공백 2개 이상으로 분리
    parts = re.split(r'\s{2,}', text.strip())
    if not parts:
        return res
    
    # 첫 번째 부분에서 PT 추출
    first_part = parts[0]
    m_pt = re.match(r'^(\d+)\s+', first_part)
    if not m_pt:
        # PT가 없으면 전체를 하나의 문자열로 파싱 시도
        return parse_single_string(text)
    
    res['pt'] = m_pt.group(1)
    # PT 뒤의 나머지 첫 부분
    first_rest = first_part[m_pt.end():].strip()
    
    # 나머지 부분들 처리
    remaining_parts = [first_rest] + parts[1:] if first_rest else parts[1:]
    
    # 각 부분 분석
    comp_parts = []
    i = 0
    while i < len(remaining_parts):
        part = remaining_parts[i].strip()
        
        # AWT가 포함된 경우 SCH/RATING으로
        if 'AWT' in part.upper():
            res['sch'] = part
            i += 1
            continue
            
        # 숫자X숫자 패턴 확인 (SIZE)
        if re.match(r'^\d+X\d+', part, re.I):
            res['size'] = part
            i += 1
            continue
            
        # 순수 숫자인 경우
        if is_numeric_text(part):
            # 아직 SIZE가 없으면 SIZE로
            if not res['size']:
                res['size'] = part
            # SIZE가 있고 QTY가 없으면 QTY로
            elif not res['qty']:
                res['qty'] = part
            # QTY도 있으면 WEIGHT로
            elif not res['weight']:
                res['weight'] = part
            i += 1
            continue
            
        # M 또는 EA 단위가 포함된 경우
        if re.match(r'^\d+(?:\.\d+)?\s*(?:M|EA)$', part, re.I):
            # 숫자와 단위 분리
            m = re.match(r'^(\d+(?:\.\d+)?)\s*(?:M|EA)$', part, re.I)
            if m and not res['qty']:
                res['qty'] = m.group(1)
            i += 1
            continue
            
        # 그 외는 COMPONENT로
        comp_parts.append(part)
        i += 1
    
    # COMPONENT 조합
    if comp_parts:
        res['comp'] = ', '.join(comp_parts).rstrip(',').strip()
    
    return res

def parse_single_string(text):
    """ 공백 2개 미만인 경우의 파싱 (기존 로직 유지) """
    res = {'pt': '', 'comp': '', 'size': '', 'qty': '', 'weight': '', 'sch': ''}
    if not text:
        return res
    
    t = text.strip()
    
    # PT 추출
    m_pt = re.match(r'^(\d+)\s+', t)
    if not m_pt:
        return res
    res['pt'] = m_pt.group(1)
    rest = t[m_pt.end():].strip()

    # AWT 처리
    if 'AWT' in rest.upper():
        # AWT 앞까지를 처리하고 AWT 포함 부분을 SCH로
        awt_idx = rest.upper().find('AWT')
        before_awt = rest[:awt_idx].strip()
        awt_part = rest[awt_idx:]
        
        # AWT 부분에서 다음 쉼표까지 추출
        m = re.match(r'^([^,]+)', awt_part)
        if m:
            res['sch'] = m.group(1).strip()
            rest = before_awt + rest[awt_idx + len(m.group(1)):]
        else:
            res['sch'] = awt_part.strip()
            rest = before_awt

    # 숫자X숫자 패턴 추출 (SIZE)
    size_pattern = re.search(r'\b(\d+X\d+)\b', rest, re.I)
    if size_pattern:
        res['size'] = size_pattern.group(1)
        # SIZE 제거
        rest = rest[:size_pattern.start()] + rest[size_pattern.end():]
        rest = rest.strip().rstrip(',').strip()

    # 뒤에서 SIZE QTY UNIT WEIGHT 패턴 찾기
    m = re.search(r'(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)\s+(M|EA)\s+(\d+(?:\.\d+)?)\s*$', rest, re.I)
    if m:
        if not res['size']:  # SIZE가 아직 없으면
            res['size'] = m.group(1)
        res['qty'] = m.group(2)
        res['weight'] = m.group(4)
        res['comp'] = rest[:m.start()].strip().rstrip(',').strip()
        return res

    # 대안: SIZE, QTY만이라도
    m2 = re.search(r'(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)\s*$', rest)
    if m2:
        if not res['size']:  # SIZE가 아직 없으면
            res['size'] = m2.group(1)
        res['qty'] = m2.group(2)
        res['comp'] = rest[:m2.start()].strip().rstrip(',').strip()
        return res

    # 마지막 대안: 숫자 시작 전까지를 COMP으로
    parts = rest.split()
    comp_parts = []
    for i, p in enumerate(parts):
        if is_numeric_text(p):
            # 숫자부터 뒤는 나눠담기
            nums = parts[i:]
            if len(nums) >= 1 and not res['size']: 
                res['size'] = nums[0]
            if len(nums) >= 2: 
                res['qty'] = nums[1]
            if len(nums) >= 4: 
                res['weight'] = nums[3]
            break
        comp_parts.append(p)
    if comp_parts:
        res['comp'] = ' '.join(comp_parts).rstrip(',').strip()
    
    return res

def split_text_by_distance(texts_with_pos, threshold=10.0):
    """같은 Y에서 X 간격 기반 토큰 묶기"""
    if not texts_with_pos:
        return []
    texts_with_pos.sort(key=lambda t: t[0])
    result = []
    cur = [texts_with_pos[0][2]]  # 원본 텍스트 유지 (공백 보존)
    last_x = texts_with_pos[0][0]
    for x, _, txt in texts_with_pos[1:]:
        if x - last_x >= threshold:
            result.append(' '.join(cur))
            cur = [txt]
        else:
            cur.append(txt)
        last_x = x
    if cur:
        result.append(' '.join(cur))
    return result

def assign_values_by_header_position(row_texts, header_positions, tolerance=30.0):
    """헤더 위치 기반으로 값 할당 (공백 2개 이상 구분 추가)"""
    vals = {k: '' for k in header_positions.keys()}
    
    # 전체 텍스트 조합 (원본 공백 유지)
    if len(row_texts) == 1:
        # 단일 텍스트인 경우 공백 2개 이상으로 분리 시도
        full_text = row_texts[0][2]
        if re.search(r'\s{2,}', full_text):
            # 공백 2개 이상이 있으면 parse_combined_row_data 사용
            parsed = parse_combined_row_data(full_text)
            vals['PT'] = parsed['pt']
            vals['COMPONENT'] = parsed['comp']
            vals['SIZE'] = parsed['size']
            vals["Q'TY"] = parsed['qty']
            vals['WEIGHT'] = parsed['weight']
            if parsed['sch']:
                vals['SCH/RATING'] = parsed['sch']
            return vals
    
    # 여러 텍스트 조각인 경우 기존 로직 사용
    for x, y, txt in row_texts:
        if not txt:
            continue
        
        # AWT 처리
        if 'AWT' in txt.upper():
            vals['SCH/RATING'] = (vals.get('SCH/RATING', '') + ' ' + txt).strip()
            continue
            
        # 숫자X숫자 처리
        if re.match(r'^\d+X\d+', txt, re.I):
            vals['SIZE'] = txt
            continue
        
        # 헤더 위치 기반 할당
        closest, mind = None, float('inf')
        for h, hx in header_positions.items():
            d = abs(x - hx)
            if d < mind and d < tolerance:
                mind = d
                closest = h
        if closest:
            vals[closest] = (vals[closest] + ' ' + txt).strip()
    
    return vals

# ─────────────────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────────────────
def main():
    # 파일 선택
    root = tk.Tk()
    root.withdraw()
    file_paths = filedialog.askopenfilenames(
        title="DXF 도면 선택", filetypes=[("DXF files", "*.dxf")]
    )
    root.destroy()
    if not file_paths:
        print("DXF 파일이 선택되지 않았습니다.")
        return

    # Excel 파일명
    today = datetime.now().strftime("%Y%m%d_%H%M%S")
    excel_filename = f"TOTALBOM_{today}.xlsx"
    excel_path = os.path.join(os.path.dirname(file_paths[0]), excel_filename)

    # 결과 버퍼
    all_data = []
    sheet_data = {
        'FABMAT': [],
        'ERECMAT': [],
        'PIPE': [],
        'VALV': [],
        'BOLT-NUT': [],
        'FITTINGS': []
    }

    ISO_DWG_FALLBACK = (708.0, 42.5, 10.0, 10.0)
    SHEETNO_FALLBACK = (810.0, 25.0, 10.0, 5.0)
    REVNO_FALLBACK   = (782.5, 25.0, 12.5, 5.0)

    for file_path in file_paths:
        print(f"\n처리 중: {os.path.basename(file_path)}")
        print("=" * 80)
        try:
            doc = ezdxf.readfile(file_path)
            msp = doc.modelspace()
        except Exception as e:
            print(f"파일 읽기 오류: {e}")
            continue

        # 1) LINE NO
        lineno_texts = find_texts_in_area_with_blocks(doc, msp, 35, 115, 15, 75)
        if lineno_texts:
            processed = []
            first = lineno_texts[0]
            for i, t in enumerate(lineno_texts):
                if i == 0:
                    processed.append(t)
                else:
                    # 공통 prefix 잘라내기
                    common = []
                    for a, b in zip(first, t):
                        if a == b:
                            common.append(a)
                        else:
                            break
                    cp = ''.join(common)
                    if cp and '-' in cp:
                        cp = cp[:cp.rfind('-') + 1]
                    rest = t[len(cp):] if len(cp) < len(t) else t
                    processed.append(rest)
            lineno = '/'.join(processed)
        else:
            lineno = '-'
        print(f"  - LINENO: {lineno}")

        # 2) INSU
        insu_texts = find_texts_in_area_with_blocks(doc, msp, 270, 310, 15, 75)
        insu = '/'.join(insu_texts) if insu_texts else '-'
        print(f"  - INSU: {insu}")

        # 3) 타이틀/리비전 (수정된 검색 위치)
        dwgno   = find_text_in_rect_with_blocks(doc, msp, 720, 750, 30, 40) or '-'
        isodesc = find_text_in_rect_with_blocks(doc, msp, 650, 750, 50, 65) or '-'
        sheetno = find_text_in_rect_with_blocks(doc, msp, 800, 820, 20, 30, lambda t: ('OF' in t.upper()) or ('/' in t)) or '-'
        revno   = find_text_in_rect_with_blocks(doc, msp, 770, 795, 20, 30, lambda t: t.isdigit()) or '-'

        if not dwgno or str(dwgno).strip() == '-':
            cx, cy, tx, ty = ISO_DWG_FALLBACK
            fb = find_text_near_point_with_blocks(doc, msp, cx, cy, tx, ty)
            if fb:
                dwgno = fb
                print(f"  - ISO DWG NO 보정됨: {dwgno}")
        if not sheetno or str(sheetno).strip() == '-':
            cx, cy, tx, ty = SHEETNO_FALLBACK
            fb = find_text_near_point_with_blocks(doc, msp, cx, cy, tx, ty, lambda t: 'OF' in t.upper())
            if fb:
                sheetno = fb
                print(f"  - SH'T NO 보정됨: {sheetno}")
        if not revno or str(revno).strip() == '-':
            cx, cy, tx, ty = REVNO_FALLBACK
            fb = find_text_near_point_with_blocks(doc, msp, cx, cy, tx, ty,
                    lambda t: re.fullmatch(r'[A-Z0-9]{1,2}', t.strip(), re.I))
            if fb:
                revno = fb
                print(f"  - REV NO 보정됨: {revno}")

        print(f"  - DWGNO: {dwgno}")
        print(f"  - ISODESC: {isodesc}")
        print(f"  - SHEETNO: {sheetno}")
        print(f"  - REVNO: {revno}")

        # 4) 헤더 찾기 - 통합 헤더만 검색
        headers_order = ['PT', 'COMPONENT', 'SIZE', "Q'TY", 'WEIGHT']
        header_positions = {}
        all_texts = get_text_from_blocks(doc, msp)
        base_y = None

        # 통합 헤더 문자열 탐지
        for x, y, txt, src in all_texts:
            tu = txt.upper()
            if 'PT' in tu and 'COMPONENT' in tu:
                # 헤더 찾음
                header_x, header_y = x, y
                base_y = header_y
                
                # 두 개 이상의 공백으로 구분하여 헤더 분리
                header_parts = re.split(r'\s{2,}', txt.strip())
                current_x = x
                
                for part in header_parts:
                    part_upper = part.upper()
                    if 'PT' in part_upper and re.search(r'\bPT\b', part_upper):
                        header_positions['PT'] = current_x
                    elif 'COMPONENT' in part_upper:
                        header_positions['COMPONENT'] = current_x
                    elif 'SIZE' in part_upper:
                        header_positions['SIZE'] = current_x
                    elif "Q'TY" in part_upper or 'QTY' in part_upper:
                        header_positions["Q'TY"] = current_x
                    elif 'WEIGHT' in part_upper and 'T.WEIGHT' not in part_upper:
                        header_positions['WEIGHT'] = current_x
                    
                    # 다음 헤더의 예상 X 위치 계산 (문자 폭 추정)
                    char_width = 200.0 / max(1, len(txt))
                    current_x += len(part) * char_width + 2 * char_width  # 공백 고려
                break

        # 헤더를 찾지 못한 경우 스킵
        if not header_positions:
            print("  - 헤더를 찾을 수 없습니다. 이 파일을 스킵합니다.")
            continue

        found_headers = [h for h in headers_order if h in header_positions]
        print(f"  - 찾은 헤더들: {found_headers}")
        print("  - 헤더 X 좌표: " + ", ".join(f"{h}={header_positions[h]:.1f}" for h in found_headers))

        # 5) PT 아래 첫 숫자 Y
        first_pt_number_y = None
        if 'PT' in header_positions and base_y is not None:
            pt_x_pos = header_positions['PT']
            for x, y, txt, src in all_texts:
                if abs(x - pt_x_pos) <= 10 and y < (base_y - 5):
                    if not is_subheader(txt) and is_numeric_text(txt):
                        first_pt_number_y = y
                        break

        # 6) 테이블 스캔
        all_rows_data = []
        cuit_found = False
        cuit_index = -1

        # 테이블 X 범위
        hx = list(header_positions.values())
        table_x_min = (min(hx) - 20.0) if hx else 600.0
        table_x_max = (max(hx) + 50.0) if hx else 850.0

        y_limit = (base_y if base_y else 550.0) - 250.0
        y_start = first_pt_number_y if first_pt_number_y else ((base_y if base_y else 550.0) - 10.0)

        # Y 라인(행 후보) 수집
        y_candidates = []
        for x, y, txt, src in all_texts:
            if not txt:
                continue
            if table_x_min <= x <= table_x_max and (y <= y_start) and (y >= y_limit):
                if not is_subheader(txt):
                    y_candidates.append(y)
        # 병합(근접한 Y는 같은 행으로)
        y_positions = sorted(set(y_candidates), reverse=True)
        merged_y = []
        for y in y_positions:
            if not merged_y or abs(merged_y[-1] - y) > 2.0:
                merged_y.append(y)

        for idx, data_y in enumerate(merged_y):
            row_texts = []
            for x, y, txt, src in all_texts:
                if table_x_min <= x <= table_x_max and abs(y - data_y) <= 2.0 and txt:
                    row_texts.append((x, y, txt))
            if not row_texts:
                continue
            row_texts.sort(key=lambda t: t[0])

            # totxt(행 전체 원문) - 원본 공백 유지
            full_row_text = ''
            if len(row_texts) == 1:
                full_row_text = row_texts[0][2]
            else:
                # 여러 텍스트를 거리 기반으로 결합
                split_texts = split_text_by_distance(row_texts)
                full_row_text = '  '.join(split_texts)  # 2개 공백으로 구분
            
            totxt = full_row_text

            # 헤더 기준 할당 or 통합 파싱
            pt_value = comp_value = size_value = qty_value = weight_value = sch_value = ''
            
            # assign_values_by_header_position이 이미 내부적으로 공백 2개 처리를 함
            row_values = assign_values_by_header_position(row_texts, header_positions)
            pt_value   = row_values.get('PT', '')
            comp_value = row_values.get('COMPONENT', '')
            size_value = row_values.get('SIZE', '')
            qty_value  = row_values.get("Q'TY", '')
            weight_value = row_values.get('WEIGHT', '')
            sch_value = row_values.get('SCH/RATING', '')

            # PT에 덩어리 텍스트가 전부 들어왔을 때 재파싱
            if pt_value and len(pt_value) > 20 and not comp_value and not size_value:
                parsed = parse_combined_row_data(pt_value)
                pt_value = parsed['pt']
                comp_value = parsed['comp']
                size_value = parsed['size']
                qty_value = parsed['qty']
                weight_value = parsed['weight']
                if parsed['sch']:
                    sch_value = parsed['sch']

            # CUT 또는 SCH/RATING에 CUT 포함 감지
            if (pt_value and 'CUT' in str(pt_value).upper()) or (comp_value and 'CUT' in str(comp_value).upper()):
                print(f"\n!!! CUT 발견 at index {idx}: PT='{pt_value}', COMP='{comp_value}'")
                cuit_found = True
                cuit_index = idx
                break

            all_rows_data.append({
                'totxt': totxt,
                'pt': pt_value,
                'comp': comp_value,
                'size': size_value,
                'qty': qty_value,
                'weight': weight_value,
                'sch': sch_value,
                'y_pos': data_y,
                'index': idx
            })

        # 7) CUT 이후 제거
        if cuit_found and cuit_index >= 0:
            print(f"\n  - CUT 발견 → 이후 데이터 제거")
            all_rows_data = all_rows_data[:cuit_index]
            print(f"  - 남은 행: {len(all_rows_data)}")

        # 8) PT 없는 행 병합 + 비숫자 PT 스킵
        merged_data = []
        last_pt_data = None
        empty_lines = []

        for row in all_rows_data:
            # PT가 길게 뭉친 경우 우선 파싱 시도
            if row['pt'] and len(row['pt']) > 20 and not row['comp']:
                parsed = parse_combined_row_data(row['pt'])
                if parsed['pt'] and is_numeric_text(parsed['pt']):
                    row['pt'] = parsed['pt']
                    row['comp'] = parsed['comp']
                    row['size'] = parsed['size']
                    row['qty'] = parsed['qty']
                    row['weight'] = parsed['weight']
                    if parsed['sch']:
                        row['sch'] = parsed['sch']

            if row['pt']:
                if not is_numeric_text(row['pt']):
                    # 숫자가 아니면 스킵 (서브헤더/오염 라인)
                    continue
                # 이전에 쌓인 빈 줄 병합
                if last_pt_data and empty_lines:
                    for e in empty_lines:
                        if e['totxt'].strip():
                            last_pt_data['comp'] = clean_text_for_excel(
                                (last_pt_data['comp'] + ' ' + clean_text_for_excel(e['totxt'])).strip()
                            )
                            # SCH 값도 병합
                            if e.get('sch'):
                                last_pt_data['sch'] = (last_pt_data.get('sch', '') + ' ' + e['sch']).strip()
                last_pt_data = row.copy()
                merged_data.append(last_pt_data)
                empty_lines = []
            else:
                # PT 비어있으면 이후 병합候補
                empty_lines.append(row)

        # 마지막 남은 empty_lines 병합
        if last_pt_data and empty_lines:
            for e in empty_lines:
                if e['totxt'].strip():
                    last_pt_data['comp'] = clean_text_for_excel(
                        (last_pt_data['comp'] + ' ' + clean_text_for_excel(e['totxt'])).strip()
                    )
                    if e.get('sch'):
                        last_pt_data['sch'] = (last_pt_data.get('sch', '') + ' ' + e.get('sch', '')).strip()

        print(f"  - PT 검증 후 남은 데이터: {len(merged_data)}개")

        # 9) 최종 전처리 → 레코드화
        all_totxt = []
        for data in merged_data:
            pt_value    = clean_text_for_excel(data['pt'])
            comp_value  = clean_text_for_excel(data['comp'])
            size_value  = clean_text_for_excel(data['size'])
            qty_value   = clean_text_for_excel(data['qty'])
            weight_value= clean_text_for_excel(data['weight'])
            sch_value   = clean_text_for_excel(data.get('sch', ''))
            totxt       = clean_text_for_excel(data['totxt'])

            # CUT 처리: COMPONENT에 CUT가 포함되어 있으면 CUT 포함 이후 삭제
            if 'CUT' in comp_value.upper():
                cut_index = comp_value.upper().find('CUT')
                comp_value = comp_value[:cut_index + 3].strip()  # CUT까지만 포함

            # COMPONENT를 쉼표 기준으로 분리 (개선된 버전)
            parts = [p.strip() for p in re.split(r',\s*', comp_value) if p.strip()]
            
            # DEG 처리: DEG가 포함되면 다음 쉼표 구분자까지 포함해서 ITEM으로
            item_value = ''
            mate_value = ''
            
            # AWT가 이미 sch_value에 있으면 parts에서 제거
            if sch_value and 'AWT' in sch_value.upper():
                parts = [p for p in parts if 'AWT' not in p.upper()]
            
            if parts:
                item_value = parts[0]
                # DEG 처리
                if 'DEG' in item_value.upper():
                    if len(parts) > 1:
                        # 다음 부분이 'A' 또는 'SA'로 시작하는지 확인
                        next_part = parts[1].strip().upper()
                        if not (next_part.startswith('A') or next_part.startswith('SA')):
                            # 'A' 또는 'SA'로 시작하지 않으면 ITEM에 포함
                            item_value = parts[0] + ', ' + parts[1]
                            # 나머지 부분들 재배열
                            if len(parts) > 2:
                                mate_value = parts[2]
                            # SCH는 이미 별도로 처리됨
                        else:
                            # 'A' 또는 'SA'로 시작하면 포함하지 않음
                            if len(parts) > 1:
                                mate_value = parts[1]
                else:
                    # DEG가 없으면 기존 로직대로
                    if len(parts) > 1:
                        mate_value = parts[1]

            # T.WEIGHT = U.WEIGHT * QTY
            tweight_value = ''
            try:
                w = extract_number(weight_value)
                q = extract_number(qty_value)
                tw = w * q if w > 0 and q > 0 else 0.0
                if tw:
                    tweight_value = str(int(tw)) if float(tw).is_integer() else str(round(tw, 1))
            except Exception:
                tweight_value = ''

            # 단위: PIPE면 M, 아니면 EA (단순 규칙)
            uni_value = 'M' if 'PIPE' in item_value.upper() else 'EA'

            row_out = {
                'TOTXT': totxt,
                'ISO DWG NO': dwgno,
                'LINE NO': lineno,
                'ISO DESC.': isodesc,
                'SH\'T NO': sheetno,
                'REV. NO': revno,
                'ITEM NO': pt_value,
                'ITEM': item_value,
                'MATERIAL': mate_value,
                'SCH/RATING': sch_value,
                'SIZE': size_value,
                "Q'TY": qty_value,
                '(M/EA)': uni_value,
                'U.WEIGHT': weight_value,
                'T.WEIGHT': tweight_value,
                'INSU. THK': insu,
                'REMARK': '',
            }
            all_totxt.append(row_out)

        # 10) 시트 분류
        print(f"\n  - 시트 분류 시작: 총 {len(all_totxt)}개 데이터")
        for r in all_totxt:
            rc = r.copy()
            rc.pop('TOTXT', None)

            # 전부 FAB MATERIAL에 포함 (CUIT 이후 제거로 가정)
            sheet_data['FABMAT'].append(rc)

            item_u = (rc.get('ITEM') or '').upper()
            if 'PIPE' in item_u:
                sheet_data['PIPE'].append(rc)

            if any(k in item_u for k in ['VALV', 'V/V', 'NRV', 'MOV', 'PCV']):
                sheet_data['VALV'].append(rc)

            if any(k in item_u for k in ['BOLT', 'NUT', 'GASKET', 'GRAPHITE', 'WOUND', 'RING']):
                sheet_data['BOLT-NUT'].append(rc)

            is_fitting = not ('PIPE' in item_u or any(k in item_u for k in ['VALV', 'V/V', 'NRV', 'MOV', 'PCV']) or any(k in item_u for k in ['BOLT','NUT','GASKET','GRAPHITE','WOUND','RING']))
            if is_fitting and item_u:
                sheet_data['FITTINGS'].append(rc)

            all_data.append(rc)

    # 11) Excel 저장
    if not all_data:
        print("\n추출된 데이터가 없습니다.")
        return

    wb = Workbook()
    # END TYPE 제거된 헤더
    headers = ['ISO DWG NO', 'LINE NO', 'ISO DESC.', 'SH\'T NO', 'REV. NO', 'ITEM NO',
               'ITEM', 'MATERIAL', 'SCH/RATING', 'SIZE', "Q'TY",
               '(M/EA)', 'U.WEIGHT', 'T.WEIGHT', 'INSU. THK', 'REMARK']

    header_font = Font(size=12, bold=True)
    header_alignment = Alignment(horizontal='center', vertical='center')
    header_border = Border(left=Side(style='thick'), right=Side(style='thick'),
                           top=Side(style='thick'), bottom=Side(style='thick'))
    data_font = Font(size=11)
    data_alignment = Alignment(horizontal='center', vertical='center')
    data_border = Border(left=Side(style='thin'), right=Side(style='thin'),
                         top=Side(style='thin'), bottom=Side(style='thin'))

    # MTO Data
    ws = wb.active
    ws.title = "MTO Data"
    for c, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=c, value=h)
        cell.font = header_font
        cell.alignment = header_alignment
        cell.border = header_border
    for r_idx, d in enumerate(all_data, 2):
        for c_idx, h in enumerate(headers, 1):
            v = clean_text_for_excel(d.get(h, ''))
            cell = ws.cell(row=r_idx, column=c_idx, value=v)
            cell.font = data_font
            cell.alignment = data_alignment
            cell.border = data_border
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            try:
                max_len = max(max_len, len(str(cell.value or '')))
            except Exception:
                pass
        ws.column_dimensions[col_letter].width = (max_len + 2) * 1.2

    # TOTAL BOM
    ws_total = wb.create_sheet(title="TOTAL BOM")
    total_bom_data = defaultdict(lambda: {'Q\'TY': 0.0, 'U.WEIGHT': '', '(M/EA)': ''})
    for row in all_data:
        key = (row.get('ITEM',''), row.get('MATERIAL',''),
               row.get('SCH/RATING',''), row.get('SIZE',''))
        qty = extract_number(row.get("Q'TY", ''))
        total_bom_data[key]['Q\'TY'] += qty
        total_bom_data[key]['U.WEIGHT'] = row.get('U.WEIGHT', '')
        total_bom_data[key]['(M/EA)'] = row.get('(M/EA)', '')

    # TOTAL BOM 헤더도 END TYPE 제거
    total_headers = ['ITEM', 'MATERIAL', 'SCH/RATING', 'SIZE', "Q'TY", '(M/EA)', 'T.WEIGHT']
    for c, h in enumerate(total_headers, 1):
        cell = ws_total.cell(row=1, column=c, value=h)
        cell.font = header_font
        cell.alignment = header_alignment
        cell.border = header_border

    total_weight_sum = 0.0
    row_idx = 2
    for (item, mat, sch, size), data in total_bom_data.items():
        w = extract_number(data['U.WEIGHT'])
        q = data["Q'\\TY".replace('\\','')] if "Q'\\TY".replace('\\','') in data else data["Q\'TY"]
        tw = w * q if w > 0 and q > 0 else 0.0
        if tw:
            total_weight_sum += tw
        tweight_str = str(int(tw)) if tw and float(tw).is_integer() else (str(round(tw, 1)) if tw else '')
        qty_str = str(int(q)) if q and float(q).is_integer() else (str(round(q, 1)) if q else '')
        out = [item, mat, sch, size, qty_str, data['(M/EA)'], tweight_str]
        for c_idx, v in enumerate(out, 1):
            cell = ws_total.cell(row=row_idx, column=c_idx, value=clean_text_for_excel(v))
            cell.font = data_font
            cell.alignment = data_alignment
            cell.border = data_border
        row_idx += 1

    sum_row = row_idx
    cell = ws_total.cell(row=sum_row, column=1, value='TOTAL')
    cell.font = Font(size=12, bold=True)
    cell.alignment = header_alignment
    cell.border = header_border
    for col in range(2, 7):
        cell = ws_total.cell(row=sum_row, column=col, value='')
        cell.border = header_border
    sum_str = str(int(total_weight_sum)) if total_weight_sum and float(total_weight_sum).is_integer() else (str(round(total_weight_sum, 1)) if total_weight_sum else '0')
    cell = ws_total.cell(row=sum_row, column=7, value=sum_str)
    cell.font = Font(size=12, bold=True)
    cell.alignment = header_alignment
    cell.border = header_border

    for col in ws_total.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            try:
                max_len = max(max_len, len(str(cell.value or '')))
            except Exception:
                pass
        ws_total.column_dimensions[col_letter].width = (max_len + 2) * 1.2

    # 분류 시트
    sheet_order = ['FAB MATERIAL', 'EREC MATERIAL', 'PIPE', 'FITTINGS', 'VALV', 'BOLT-NUT']
    sheet_mapping = {
        'FAB MATERIAL': 'FABMAT',
        'EREC MATERIAL': 'ERECMAT',
        'PIPE': 'PIPE',
        'FITTINGS': 'FITTINGS',
        'VALV': 'VALV',
        'BOLT-NUT': 'BOLT-NUT',
    }
    for sname in sheet_order:
        key = sheet_mapping[sname]
        if sheet_data[key] or sname == 'EREC MATERIAL':  # EREC 시트는 비어도 생성
            ws_s = wb.create_sheet(title=sname)
            for c, h in enumerate(headers, 1):
                cell = ws_s.cell(row=1, column=c, value=h)
                cell.font = header_font
                cell.alignment = header_alignment
                cell.border = header_border
            if sheet_data[key]:
                for r_i, d in enumerate(sheet_data[key], 2):
                    for c_i, h in enumerate(headers, 1):
                        v = clean_text_for_excel(d.get(h, ''))
                        cell = ws_s.cell(row=r_i, column=c_i, value=v)
                        cell.font = data_font
                        cell.alignment = data_alignment
                        cell.border = data_border
            for col in ws_s.columns:
                max_len = 0
                col_letter = get_column_letter(col[0].column)
                for cell in col:
                    try:
                        max_len = max(max_len, len(str(cell.value or '')))
                    except Exception:
                        pass
                ws_s.column_dimensions[col_letter].width = (max_len + 2) * 1.2

    wb.save(excel_path)
    print(f"\n=== Excel 파일 저장 완료 ===")
    print(f"파일명: {excel_filename}")
    print(f"경로: {excel_path}")
    print(f"총 {len(all_data)}개의 데이터 저장됨")

if __name__ == "__main__":
    main()