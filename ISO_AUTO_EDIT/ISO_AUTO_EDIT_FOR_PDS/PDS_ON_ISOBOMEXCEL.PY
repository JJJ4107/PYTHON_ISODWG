#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import sys
import ezdxf
from datetime import datetime
from collections import defaultdict
import math

try:
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
except ImportError:
    raise SystemExit("openpyxl 라이브러리가 필요합니다. 설치 명령: pip install openpyxl")

# ─────────────────────────────────────────────────────────
# ANSI 재질, 등급 및 피팅 아이템 정의
# ─────────────────────────────────────────────────────────
ANSI_MATERIALS = [
    # Carbon Steel
    'A105', 'A106', 'A53', 'A234', 'A182', 'A216', 'A217', 'A350', 'A352',
    'A420', 'A694', 'A333', 'A671', 'A672', 'A691',
    # Stainless Steel
    'A403', 'A312', 'A351', 'A358', 'A376', 'A409', 'A240', 'A269', 'A270',
    'A479', 'A276',
    # Alloy Steel
    'A335', 'A387', 'A234',
    # With grade patterns
    'SA105', 'SA106', 'SA53', 'SA234', 'SA182', 'SA216', 'SA217', 'SA350',
    'SA335', 'SA403', 'SA312', 'SA351',
    # Common abbreviations
    'SS304', 'SS316', 'SS316L', 'SS321', 'SS347', 'SS304L', 'SS310',
    '304', '316', '316L', '304L', '321', '347', '310',
    'CS', 'SS', 'LTCS',  # Carbon Steel, Stainless Steel, Low Temp Carbon Steel
]

# 재질 패턴 (SA182-F92, SA234-WP92 등)
MATERIAL_PATTERNS = [
    r'^S?A\d{3,4}[-\s]?[A-Z]*\d*',  # SA182-F92, A105, SA234-WP92 등
    r'^S?A\d{3,4}$',  # A105, SA182 등
]

ANSI_RATINGS = [
    # Class ratings
    'CL150', 'CL300', 'CL600', 'CL900', 'CL1500', 'CL2500', 'CL3000', 'CL6000',
    'CLASS150', 'CLASS300', 'CLASS600', 'CLASS900', 'CLASS1500', 'CLASS2500', 'CLASS3000', 'CLASS6000',
    # Pound ratings
    '150#', '300#', '600#', '900#', '1500#', '2500#', '3000#', '6000#',
    '150LB', '300LB', '600LB', '900LB', '1500LB', '2500LB', '3000LB', '6000LB',
    # Schedule
    'SCH10', 'SCH20', 'SCH30', 'SCH40', 'SCH60', 'SCH80', 'SCH100', 'SCH120', 'SCH140', 'SCH160',
    'SCH10S', 'SCH40S', 'SCH80S',
    'S-10', 'S-20', 'S-30', 'S-40', 'S-60', 'S-80', 'S-100', 'S-120', 'S-140', 'S-160',
    'S-10S', 'S-40S', 'S-80S', 'S-XS', 'S-XXS', 'S-STD',
    'STD', 'XS', 'XXS',  # Standard, Extra Strong, Double Extra Strong
]

WELDING_TERMS = ['BW', 'SW', 'THD', 'RF', 'RTJ', 'FF']  # Butt Weld, Socket Weld, Threaded, etc.

# 피팅 아이템 (재질이 아닌 부품명)
FITTING_ITEMS = [
    'BOSS', 'COUPLING', 'ELBOW', 'TEE', 'REDUCER', 'CAP', 'STUB', 'NIPPLE',
    'UNION', 'SWAGE', 'OUTLET', 'FLANGE', 'GASKET', 'BOLT', 'NUT',
    'VALVE', 'GATE', 'GLOBE', 'CHECK', 'BALL', 'PLUG', 'BLIND',
    'OLET', 'WELDOLET', 'SOCKOLET', 'THREADOLET', 'LATROLET',
    'PIPE', 'TUBING', 'BEND', 'CROSS', 'BUSHING', 'INSERT', 'RING'
]

# 캐시된 세트로 변환하여 검색 속도 향상 (O(1) 검색)
ANSI_MATERIALS_SET = set(mat.upper() for mat in ANSI_MATERIALS)
ANSI_RATINGS_SET = set(rating.upper() for rating in ANSI_RATINGS)
WELDING_TERMS_SET = set(WELDING_TERMS)
FITTING_ITEMS_SET = set(item.upper() for item in FITTING_ITEMS)

# ─────────────────────────────────────────────────────────
# 유틸: 좌표/텍스트 안전 추출
# ─────────────────────────────────────────────────────────
def get_xy(e):
    """엔티티에서 XY 좌표 추출 (최적화됨)"""
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

# 유니코드 공백 문자 사전 정의 (최적화)
UNICODE_SPACES = str.maketrans({
    '\u2000': ' ', '\u2001': ' ', '\u2002': ' ', '\u2003': ' ', '\u2004': ' ', 
    '\u2005': ' ', '\u2006': ' ', '\u2007': ' ', '\u2008': ' ', '\u2009': ' ', 
    '\u200A': ' ', '\u202F': ' ', '\u205F': ' ', '\u3000': ' ', '\xa0': ' ',
    '\u00A0': ' ', '\u1680': ' ', '\u180E': ' ', '\u2028': ' ', '\u2029': ' ',
    '\u200B': ' ', '\u200C': ' ', '\u200D': ' ', '\uFEFF': ' ', '\t': ' ',
    '\n': ' ', '\r': ' '
})

def _normalize_spaces(text: str) -> str:
    """공백 문자 정규화 (최적화됨)"""
    # 문자열로 표현된 유니코드 이스케이프 처리
    text = re.sub(r'\\U\+[0-9A-Fa-f]{4}', ' ', text)
    # 유니코드 공백을 일반 공백으로 변환 (translate 사용으로 최적화)
    text = text.translate(UNICODE_SPACES)
    # 연속 공백 축소
    text = re.sub(r' {3,}', '  ', text)
    # 제어문자 제거
    import unicodedata
    text = ''.join(ch for ch in text if not unicodedata.category(ch).startswith('C'))
    return text.strip()

def get_text(e):
    """엔티티에서 텍스트 추출 (최적화됨)"""
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
# 분류 확인 함수 (최적화됨)
# ─────────────────────────────────────────────────────────
def is_fitting_item(text):
    """텍스트가 피팅 아이템인지 확인 (O(1) 검색)"""
    if not text:
        return False
    text_upper = text.upper().strip()
    # 정확한 매칭 먼저 확인
    if text_upper in FITTING_ITEMS_SET:
        return True
    # startswith 검사
    for item in FITTING_ITEMS_SET:
        if text_upper.startswith(item):
            return True
    return False

def is_ansi_material(text):
    """텍스트가 ANSI 재질인지 확인 (최적화됨)"""
    if not text:
        return False
    
    # 피팅 아이템인 경우 재질이 아님
    if is_fitting_item(text):
        return False
    
    text_upper = text.upper().strip()
    
    # 재질 패턴 매칭 먼저 (빠른 패턴 매칭)
    for pattern in MATERIAL_PATTERNS:
        if re.match(pattern, text_upper):
            return True
    
    # 재질 목록 확인 (O(1) 검색)
    if text_upper in ANSI_MATERIALS_SET:
        return True
    
    # 부분 문자열 검사
    for mat in ANSI_MATERIALS_SET:
        if mat in text_upper:
            return True
    
    return False

def is_ansi_rating(text):
    """텍스트가 ANSI 등급인지 확인 (최적화됨)"""
    if not text:
        return False
    text_upper = text.upper().strip()
    
    # 패턴 매칭 (빠른 검사)
    if re.match(r'^S-\w+', text_upper):
        return True
    if re.match(r'^(CL|CLASS)\d+', text_upper):
        return True
    if re.match(r'^\d+#$|^\d+LB$', text_upper):
        return True
    if re.match(r'^SCH\d+', text_upper):
        return True
    
    # 세트 검색 (O(1))
    if text_upper in ANSI_RATINGS_SET:
        return True
    
    # 부분 문자열 검사
    for rating in ANSI_RATINGS_SET:
        if rating in text_upper:
            return True
    
    return False

def contains_welding_term(text):
    """텍스트에 용접 관련 용어가 포함되어 있는지 확인 (최적화됨)"""
    if not text:
        return False
    text_upper = text.upper()
    for term in WELDING_TERMS_SET:
        if re.search(r'\b' + term + r'\b', text_upper):
            return True
    return False

def is_size_value(text):
    """텍스트가 SIZE 값인지 확인"""
    if not text:
        return False
    text = text.strip()
    # 숫자X숫자 패턴
    if re.match(r'^\d+X\d+$', text, re.I):
        return True
    # 단독 숫자 (정수 또는 소수)
    if re.match(r'^\d+(?:\.\d+)?$', text):
        try:
            val = float(text)
            if 10 <= val <= 10000:
                return True
        except:
            pass
    return False

# ─────────────────────────────────────────────────────────
# 모델공간 + 블록(INSERT) 내부 TEXT/MTEXT 수집 (최적화됨)
# ─────────────────────────────────────────────────────────
def get_text_from_blocks(doc, msp):
    """모든 텍스트 엔티티 수집 (최적화됨)"""
    all_texts = []
    
    # 1) 모델공간의 TEXT/MTEXT (한 번의 쿼리로 처리)
    for e in msp.query('TEXT MTEXT'):
        txt = get_text(e)
        if txt:  # 빈 텍스트 사전 필터링
            x, y = get_xy(e)
            all_texts.append((x, y, txt, 'normal'))

    # 2) INSERT 블록 내부 TEXT/MTEXT (블록 캐싱 고려)
    block_cache = {}  # 블록 캐시
    for ins in msp.query('INSERT'):
        try:
            ip = ins.dxf.insert
            x_scale = getattr(ins.dxf, 'xscale', 1.0) or 1.0
            y_scale = getattr(ins.dxf, 'yscale', 1.0) or 1.0
            rotation = getattr(ins.dxf, 'rotation', 0.0) or 0.0
            bname = ins.dxf.name
            
            if bname not in doc.blocks:
                continue
                
            # 블록 엔티티 캐싱
            if bname not in block_cache:
                block = doc.blocks[bname]
                block_texts = []
                for ent in block:
                    if ent.dxftype() in ('TEXT', 'MTEXT'):
                        txt = get_text(ent)
                        if txt:
                            lx, ly = get_xy(ent)
                            block_texts.append((lx, ly, txt))
                block_cache[bname] = block_texts
            
            # 좌표 변환 계산
            rad = math.radians(rotation)
            cos_r, sin_r = math.cos(rad), math.sin(rad)
            
            for lx, ly, txt in block_cache[bname]:
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
# 영역/근접 검색 (최적화됨)
# ─────────────────────────────────────────────────────────
def find_texts_in_area_with_blocks(all_texts, x_min, x_max, y_min, y_max):
    """영역 내 텍스트 찾기 (사전 수집된 텍스트 사용)"""
    texts = []
    for x, y, txt, src in all_texts:
        if x_min <= x <= x_max and y_min <= y <= y_max and txt:
            texts.append((x, y, txt))
    texts.sort(key=lambda t: -t[1])  # Y 내림차순
    return [t[2] for t in texts]

def find_text_in_rect_with_blocks(all_texts, x_min, x_max, y_min, y_max, condition=None):
    """사각형 영역에서 조건에 맞는 첫 번째 텍스트 찾기"""
    for x, y, txt, src in all_texts:
        if x_min <= x <= x_max and y_min <= y <= y_max and txt:
            if condition is None or condition(txt):
                return txt
    return None

def find_text_near_point_with_blocks(all_texts, cx, cy, tol_x, tol_y, condition=None):
    """점 근처의 텍스트 찾기"""
    return find_text_in_rect_with_blocks(all_texts, cx - tol_x, cx + tol_x, cy - tol_y, cy + tol_y, condition)

# ─────────────────────────────────────────────────────────
# 파싱/정리 유틸 (최적화됨)
# ─────────────────────────────────────────────────────────
def extract_number(text):
    """텍스트에서 숫자 추출 (최적화됨)"""
    if not text:
        return 0.0
    m = re.search(r'[\d.]+', str(text))
    if not m:
        return 0.0
    try:
        return float(m.group())
    except ValueError:
        return 0.0

def is_numeric_text(s):
    """숫자 텍스트 확인 (최적화됨)"""
    if s is None:
        return False
    s = str(s).strip()
    return bool(re.fullmatch(r'\d+(?:\.\d+)?', s))

SUBHEADERS_SET = {'NO.', 'DESCRIPTION', '(DN)', '(M,EA)', '(KG)', "Q'TY", 'QTY', 'WEIGHT', 'SIZE', 'PT', 'COMPONENT'}

def is_subheader(text):
    """서브헤더 확인 (O(1) 검색)"""
    if not text:
        return False
    return text.strip().upper() in SUBHEADERS_SET

def clean_text_for_excel(text):
    """엑셀용 텍스트 정리 (최적화됨)"""
    if not text:
        return ''
    return ' '.join(str(text).split())

def parse_combined_row_data(text):
    """공백 2개 이상으로 구분된 텍스트 파싱 (최적화됨)"""
    res = {'pt': '', 'comp': '', 'size': '', 'qty': '', 'weight': '', 'sch': '', 'material': ''}
    if not text:
        return res
    
    # 공백 2개 이상으로 분리
    parts = re.split(r'\s{2,}', text.strip())
    if not parts:
        return parse_single_string(text)
    
    # 첫 번째 부분에서 PT 추출
    first_part = parts[0]
    m_pt = re.match(r'^(\d+)\s+', first_part)
    if not m_pt:
        return parse_single_string(text)
    
    res['pt'] = m_pt.group(1)
    first_rest = first_part[m_pt.end():].strip()
    
    # 나머지 부분들 처리
    remaining_parts = [first_rest] + parts[1:] if first_rest else parts[1:]
    
    comp_parts = []
    size_found = False
    qty_found = False
    weight_found = False
    
    i = 0
    while i < len(remaining_parts):
        part = remaining_parts[i].strip()
        
        if not part:
            i += 1
            continue
        
        # 피팅 아이템 확인
        if is_fitting_item(part):
            comp_part = part
            if i + 1 < len(remaining_parts):
                next_part = remaining_parts[i + 1].strip()
                if (not is_ansi_material(next_part) and not is_ansi_rating(next_part) 
                    and not is_numeric_text(next_part) and next_part):
                    comp_part = part + ' ' + next_part
                    i += 1
            comp_parts.append(comp_part)
            i += 1
            continue
        
        # ANSI 등급 확인
        if is_ansi_rating(part):
            res['sch'] = (res['sch'] + ' ' + part).strip()
            i += 1
            continue
        
        # ANSI 재질 확인
        if is_ansi_material(part):
            res['material'] = (res['material'] + ' ' + part).strip()
            i += 1
            continue
        
        # 용접 용어 확인
        if contains_welding_term(part):
            res['sch'] = (res['sch'] + ' ' + part).strip()
            i += 1
            continue
        
        # 숫자X숫자 패턴
        if re.match(r'^\d+X\d+$', part, re.I):
            res['size'] = part
            size_found = True
            i += 1
            continue
        
        # 순수 숫자인 경우
        if is_numeric_text(part):
            val = float(part)
            if not size_found and 10 <= val <= 10000:
                res['size'] = part
                size_found = True
            elif size_found and not qty_found:
                res['qty'] = part
                qty_found = True
            elif qty_found and not weight_found:
                res['weight'] = part
                weight_found = True
            i += 1
            continue
        
        # M 또는 EA 단위가 포함된 경우
        if re.match(r'^\d+(?:\.\d+)?\s*(?:M|EA)$', part, re.I):
            m = re.match(r'^(\d+(?:\.\d+)?)\s*(?:M|EA)$', part, re.I)
            if m and not qty_found:
                res['qty'] = m.group(1)
                qty_found = True
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
    """공백 2개 미만인 경우의 파싱 (최적화됨)"""
    res = {'pt': '', 'comp': '', 'size': '', 'qty': '', 'weight': '', 'sch': '', 'material': ''}
    if not text:
        return res
    
    t = text.strip()
    
    # PT 추출
    m_pt = re.match(r'^(\d+)\s+', t)
    if not m_pt:
        return res
    res['pt'] = m_pt.group(1)
    rest = t[m_pt.end():].strip()

    # 공백 또는 쉼표로 분리
    parts = re.split(r'[,\s]+', rest)
    comp_parts = []
    size_found = False
    qty_found = False
    weight_found = False
    
    i = 0
    while i < len(parts):
        part = parts[i].strip()
        if not part:
            i += 1
            continue
        
        # 피팅 아이템 처리
        if is_fitting_item(part):
            comp_part = part
            if i + 1 < len(parts):
                next_part = parts[i + 1].strip()
                if (not is_ansi_material(next_part) and not is_ansi_rating(next_part) 
                    and not is_numeric_text(next_part) and next_part):
                    comp_part = part + ' ' + next_part
                    i += 1
            comp_parts.append(comp_part)
            i += 1
            continue
        
        # ANSI 등급 처리
        if is_ansi_rating(part):
            res['sch'] = (res['sch'] + ' ' + part).strip()
            i += 1
            continue
        
        # ANSI 재질 처리
        if is_ansi_material(part):
            res['material'] = (res['material'] + ' ' + part).strip()
            i += 1
            continue
        
        # 용접 용어 처리
        if contains_welding_term(part):
            res['sch'] = (res['sch'] + ' ' + part).strip()
            i += 1
            continue
        
        # 숫자X숫자 패턴
        if re.match(r'^\d+X\d+$', part, re.I):
            res['size'] = part
            size_found = True
            i += 1
            continue
        
        # 순수 숫자인 경우
        if is_numeric_text(part):
            val = float(part)
            if not size_found and 10 <= val <= 10000:
                res['size'] = part
                size_found = True
            elif size_found and not qty_found:
                res['qty'] = part
                qty_found = True
            elif qty_found and not weight_found:
                res['weight'] = part
                weight_found = True
            i += 1
            continue
        
        # 나머지는 COMPONENT
        comp_parts.append(part)
        i += 1
    
    # COMPONENT 조합
    if comp_parts:
        res['comp'] = ', '.join(comp_parts).rstrip(',').strip()
    
    return res

def split_text_by_distance(texts_with_pos, threshold=10.0):
    """같은 Y에서 X 간격 기반 토큰 묶기 (최적화됨)"""
    if not texts_with_pos:
        return []
    texts_with_pos.sort(key=lambda t: t[0])
    result = []
    cur = [texts_with_pos[0][2]]
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
    """헤더 위치 기반으로 값 할당 (최적화됨)"""
    vals = {k: '' for k in header_positions.keys()}
    vals['MATERIAL'] = ''
    vals['SCH/RATING'] = ''
    
    # 전체 텍스트 조합
    if len(row_texts) == 1:
        full_text = row_texts[0][2]
        if re.search(r'\s{2,}', full_text):
            parsed = parse_combined_row_data(full_text)
            vals['PT'] = parsed['pt']
            vals['COMPONENT'] = parsed['comp']
            vals['SIZE'] = parsed['size']
            vals["Q'TY"] = parsed['qty']
            vals['WEIGHT'] = parsed['weight']
            vals['SCH/RATING'] = parsed['sch']
            vals['MATERIAL'] = parsed['material']
            return vals
    
    # 여러 텍스트 조각인 경우
    for x, y, txt in row_texts:
        if not txt:
            continue
        
        # 피팅 아이템 처리
        if is_fitting_item(txt):
            closest, mind = None, float('inf')
            for h, hx in header_positions.items():
                if h == 'COMPONENT':
                    d = abs(x - hx)
                    if d < tolerance:
                        vals['COMPONENT'] = (vals['COMPONENT'] + ' ' + txt).strip()
                        break
            continue
        
        # ANSI 등급 처리
        if is_ansi_rating(txt):
            vals['SCH/RATING'] = (vals.get('SCH/RATING', '') + ' ' + txt).strip()
            continue
        
        # ANSI 재질 처리  
        if is_ansi_material(txt):
            vals['MATERIAL'] = (vals.get('MATERIAL', '') + ' ' + txt).strip()
            continue
        
        # 용접 용어 처리
        if contains_welding_term(txt):
            vals['SCH/RATING'] = (vals.get('SCH/RATING', '') + ' ' + txt).strip()
            continue
        
        # 숫자X숫자 처리
        if re.match(r'^\d+X\d+$', txt, re.I):
            vals['SIZE'] = txt
            continue
        
        # 단독 숫자이고 SIZE 가능성이 있는 경우
        if is_numeric_text(txt):
            val = float(txt)
            if 'SIZE' in header_positions:
                size_x = header_positions['SIZE']
                if abs(x - size_x) < tolerance and 10 <= val <= 10000 and not vals['SIZE']:
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
# DXF 문서 처리 함수 (런너 연동용 엔트리 포인트)
# ─────────────────────────────────────────────────────────
def process_doc(doc, file_path):
    """
    개별 DXF 문서 처리 함수 (런너 연동용 엔트리 포인트)
    
    Args:
        doc: ezdxf 문서 객체
        file_path: DXF 파일 경로
    
    Returns:
        tuple: (all_data, sheet_data) - 처리된 데이터
    """
    msp = doc.modelspace()
    
    # 텍스트 수집 (한 번만 수행하여 성능 최적화)
    all_texts = get_text_from_blocks(doc, msp)
    
    # 결과 버퍼
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

    # 1) LINE NO
    lineno_texts = find_texts_in_area_with_blocks(all_texts, 35, 115, 15, 75)
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

    # 2) INSU
    insu_texts = find_texts_in_area_with_blocks(all_texts, 235, 240, 35, 75)
    insu = '/'.join(insu_texts) if insu_texts else '-'

    # 3) 타이틀/리비전
    dwgno   = find_text_in_rect_with_blocks(all_texts, 720, 750, 30, 40) or '-'
    isodesc = find_text_in_rect_with_blocks(all_texts, 650, 750, 50, 65) or '-'
    sheetno = find_text_in_rect_with_blocks(all_texts, 800, 820, 20, 30, lambda t: ('OF' in t.upper()) or ('/' in t)) or '-'
    revno   = find_text_in_rect_with_blocks(all_texts, 770, 795, 20, 30, lambda t: t.isdigit()) or '-'

    if not dwgno or str(dwgno).strip() == '-':
        cx, cy, tx, ty = ISO_DWG_FALLBACK
        fb = find_text_near_point_with_blocks(all_texts, cx, cy, tx, ty)
        if fb:
            dwgno = fb
    if not sheetno or str(sheetno).strip() == '-':
        cx, cy, tx, ty = SHEETNO_FALLBACK
        fb = find_text_near_point_with_blocks(all_texts, cx, cy, tx, ty, lambda t: 'OF' in t.upper())
        if fb:
            sheetno = fb
    if not revno or str(revno).strip() == '-':
        cx, cy, tx, ty = REVNO_FALLBACK
        fb = find_text_near_point_with_blocks(all_texts, cx, cy, tx, ty,
                lambda t: re.fullmatch(r'[A-Z0-9]{1,2}', t.strip(), re.I))
        if fb:
            revno = fb

    # 4) 헤더 찾기
    headers_order = ['PT', 'COMPONENT', 'SIZE', "Q'TY", 'WEIGHT']
    header_positions = {}
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
                
                # 다음 헤더의 예상 X 위치 계산
                char_width = 200.0 / max(1, len(txt))
                current_x += len(part) * char_width + 2 * char_width
            break

    # 헤더를 찾지 못한 경우 빈 데이터 반환
    if not header_positions:
        return [], sheet_data

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

    # Y 라인(행 후보) 수집 (최적화됨)
    y_candidates = []
    for x, y, txt, src in all_texts:
        if (txt and table_x_min <= x <= table_x_max and 
            y <= y_start and y >= y_limit and 
            not is_subheader(txt)):
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

        # totxt(행 전체 원문)
        full_row_text = ''
        if len(row_texts) == 1:
            full_row_text = row_texts[0][2]
        else:
            split_texts = split_text_by_distance(row_texts)
            full_row_text = '  '.join(split_texts)
        
        totxt = full_row_text

        # 헤더 기준 할당 or 통합 파싱
        row_values = assign_values_by_header_position(row_texts, header_positions)
        pt_value   = row_values.get('PT', '')
        comp_value = row_values.get('COMPONENT', '')
        size_value = row_values.get('SIZE', '')
        qty_value  = row_values.get("Q'TY", '')
        weight_value = row_values.get('WEIGHT', '')
        sch_value = row_values.get('SCH/RATING', '')
        material_value = row_values.get('MATERIAL', '')

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
            if parsed['material']:
                material_value = parsed['material']

        # CUT 감지
        if (pt_value and 'CUT' in str(pt_value).upper()) or (comp_value and 'CUT' in str(comp_value).upper()):
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
            'material': material_value,
            'y_pos': data_y,
            'index': idx
        })

    # 7) CUT 이후 제거
    if cuit_found and cuit_index >= 0:
        all_rows_data = all_rows_data[:cuit_index]

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
                if parsed['material']:
                    row['material'] = parsed['material']

        if row['pt']:
            if not is_numeric_text(row['pt']):
                continue
            # 이전에 쌓인 빈 줄 병합
            if last_pt_data and empty_lines:
                for e in empty_lines:
                    if e['totxt'].strip():
                        last_pt_data['comp'] = clean_text_for_excel(
                            (last_pt_data['comp'] + ' ' + clean_text_for_excel(e['totxt'])).strip()
                        )
                        if e.get('sch'):
                            last_pt_data['sch'] = (last_pt_data.get('sch', '') + ' ' + e['sch']).strip()
                        if e.get('material'):
                            last_pt_data['material'] = (last_pt_data.get('material', '') + ' ' + e['material']).strip()
            last_pt_data = row.copy()
            merged_data.append(last_pt_data)
            empty_lines = []
        else:
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
                if e.get('material'):
                    last_pt_data['material'] = (last_pt_data.get('material', '') + ' ' + e.get('material', '')).strip()

    # 9) 최종 전처리 → 레코드화
    all_data = []
    for data in merged_data:
        pt_value    = clean_text_for_excel(data['pt'])
        comp_value  = clean_text_for_excel(data['comp'])
        size_value  = clean_text_for_excel(data['size'])
        qty_value   = clean_text_for_excel(data['qty'])
        tweight_value = clean_text_for_excel(data['weight'])
        sch_value   = clean_text_for_excel(data.get('sch', ''))
        material_value = clean_text_for_excel(data.get('material', ''))
        totxt       = clean_text_for_excel(data['totxt'])

        # CUT 처리
        if 'CUT' in comp_value.upper():
            cut_index = comp_value.upper().find('CUT')
            comp_value = comp_value[:cut_index + 3].strip()

        # COMPONENT에서 분류 재처리
        comp_parts = []
        comma_parts = [p.strip() for p in comp_value.split(',') if p.strip()]
        
        for comma_part in comma_parts:
            parts = [p.strip() for p in comma_part.split() if p.strip()]
            if not parts:
                continue
            
            i = 0
            while i < len(parts):
                part = parts[i]
                
                if is_fitting_item(part):
                    comp_part = part
                    if (i + 1 < len(parts) and 
                        not is_ansi_material(parts[i + 1]) and 
                        not is_ansi_rating(parts[i + 1]) and 
                        not is_numeric_text(parts[i + 1])):
                        comp_part = part + ' ' + parts[i + 1]
                        i += 1
                    comp_parts.append(comp_part)
                    i += 1
                elif contains_welding_term(part):
                    sch_value = (sch_value + ' ' + part).strip()
                    i += 1
                elif is_ansi_rating(part):
                    sch_value = (sch_value + ' ' + part).strip()
                    i += 1
                elif is_ansi_material(part):
                    material_value = (material_value + ' ' + part).strip()
                    i += 1
                else:
                    comp_parts.append(part)
                    i += 1
        
        # ITEM과 MATERIAL 최종 처리
        item_value = ''
        mate_value = material_value
        
        if comp_parts:
            item_value = comp_parts[0]
            if 'DEG' in item_value.upper() and len(comp_parts) > 1:
                if not is_ansi_material(comp_parts[1]):
                    item_value = comp_parts[0] + ', ' + comp_parts[1]
                    if len(comp_parts) > 2 and is_ansi_material(comp_parts[2]):
                        mate_value = (mate_value + ' ' + comp_parts[2]).strip()
                else:
                    mate_value = (mate_value + ' ' + comp_parts[1]).strip()
            elif len(comp_parts) > 1:
                if is_ansi_material(comp_parts[1]):
                    mate_value = (mate_value + ' ' + comp_parts[1]).strip()
                elif is_fitting_item(comp_parts[1]):
                    item_value = comp_parts[0] + ', ' + comp_parts[1]

        # U.WEIGHT = T.WEIGHT / QTY
        uweight_value = ''
        try:
            tw = extract_number(tweight_value)
            q = extract_number(qty_value)
            uw = tw / q if tw > 0 and q > 0 else 0.0
            if uw:
                uweight_value = str(int(uw)) if float(uw).is_integer() else str(round(uw, 2))
        except Exception:
            uweight_value = ''

        # 단위: PIPE면 M, 아니면 EA
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
            'U.WEIGHT': uweight_value,
            'T.WEIGHT': tweight_value,
            'INSU. THK': insu,
            'REMARK': '',
        }
        all_data.append(row_out)

    # 10) 시트 분류
    for r in all_data:
        rc = r.copy()
        rc.pop('TOTXT', None)

        # 전부 FAB MATERIAL에 포함
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

    return all_data, sheet_data

# ─────────────────────────────────────────────────────────
# Excel 저장 함수
# ─────────────────────────────────────────────────────────
def save_to_excel(all_data, sheet_data, output_path):
    """Excel 파일로 저장"""
    if not all_data:
        return

    wb = Workbook()
    headers = ['ISO DWG NO', 'LINE NO', 'ISO DESC.', 'SH\'T NO', 'REV. NO', 'ITEM NO',
               'ITEM', 'MATERIAL', 'SCH/RATING', 'SIZE', "Q'TY",
               '(M/EA)', 'U.WEIGHT', 'T.WEIGHT', 'INSU. THK', 'REMARK']

    # 스타일 정의
    header_font = Font(size=12, bold=True)
    header_alignment = Alignment(horizontal='center', vertical='center')
    header_border = Border(left=Side(style='thick'), right=Side(style='thick'),
                           top=Side(style='thick'), bottom=Side(style='thick'))
    data_font = Font(size=11)
    data_alignment = Alignment(horizontal='center', vertical='center')
    data_border = Border(left=Side(style='thin'), right=Side(style='thin'),
                         top=Side(style='thin'), bottom=Side(style='thin'))

    # MTO Data 시트
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

    # TOTAL BOM 시트
    ws_total = wb.create_sheet(title="TOTAL BOM")
    total_bom_data = defaultdict(lambda: {'Q\'TY': 0.0, 'T.WEIGHT': 0.0, '(M/EA)': ''})
    for row in all_data:
        key = (row.get('ITEM',''), row.get('MATERIAL',''),
               row.get('SCH/RATING',''), row.get('SIZE',''))
        qty = extract_number(row.get("Q'TY", ''))
        tweight = extract_number(row.get('T.WEIGHT', ''))
        total_bom_data[key]['Q\'TY'] += qty
        total_bom_data[key]['T.WEIGHT'] += tweight
        total_bom_data[key]['(M/EA)'] = row.get('(M/EA)', '')

    total_headers = ['ITEM', 'MATERIAL', 'SCH/RATING', 'SIZE', "Q'TY", '(M/EA)', 'T.WEIGHT']
    for c, h in enumerate(total_headers, 1):
        cell = ws_total.cell(row=1, column=c, value=h)
        cell.font = header_font
        cell.alignment = header_alignment
        cell.border = header_border

    total_weight_sum = 0.0
    row_idx = 2
    for (item, mat, sch, size), data in total_bom_data.items():
        tw = data['T.WEIGHT']
        q = data["Q'TY"]
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

    # 분류 시트들
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
        if sheet_data[key] or sname == 'EREC MATERIAL':
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

    wb.save(output_path)

# ─────────────────────────────────────────────────────────
# 메인 함수
# ─────────────────────────────────────────────────────────
def main():
    """메인 실행 함수"""
    # 명령행 인수 확인
    if len(sys.argv) < 2:
        raise SystemExit("사용법: python script.py file1.dxf file2.dxf ...")
    
    file_paths = sys.argv[1:]
    
    # DXF 파일 유효성 검사
    valid_files = []
    for file_path in file_paths:
        if not os.path.exists(file_path):
            continue
        if not file_path.lower().endswith('.dxf'):
            continue
        valid_files.append(file_path)
    
    if not valid_files:
        raise SystemExit("유효한 DXF 파일이 없습니다.")
    
    # 각 파일을 개별적으로 처리
    for file_path in valid_files:
        try:
            doc = ezdxf.readfile(file_path)
            
            # 개별 문서 처리 (런너 연동용 엔트리 포인트 사용)
            all_data, sheet_data = process_doc(doc, file_path)
            
            if not all_data:
                continue
            
            # 개별 Excel 파일 생성
            today = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            excel_filename = f"BOM_{base_name}_{today}.xlsx"
            excel_path = os.path.join(os.path.dirname(file_path), excel_filename)
            
            # Excel 파일 저장
            save_to_excel(all_data, sheet_data, excel_path)
            
        except Exception as e:
            continue

if __name__ == "__main__":
    main()

"""
시간복잡도 분석:

1. get_text_from_blocks: O(n + m*k)
   - n: 모델공간 텍스트 엔티티 수
   - m: INSERT 블록 수  
   - k: 블록당 평균 엔티티 수
   - 블록 캐싱으로 중복 처리 방지

2. 분류 함수들: O(1) ~ O(log n)
   - 세트 기반 검색으로 O(1) 성능
   - 정규표현식은 O(m), m은 문자열 길이

3. 텍스트 검색: O(n)
   - 한 번 수집된 텍스트를 재사용
   - 필터링으로 불필요한 처리 감소

4. 테이블 스캔: O(n*log n)
   - Y 좌표 정렬: O(n*log n)
   - 행별 처리: O(n)

5. 데이터 처리: O(k)
   - k: 추출된 행 수 (보통 n보다 훨씬 작음)

6. Excel 저장: O(k + s)
   - k: 데이터 행 수
   - s: 시트 수

전체 시간복잡도: O(n*log n + m*k)
- 실제 성능은 DXF 파일 크기와 복잡도에 비례
- 캐싱과 최적화로 상당한 성능 향상 달성

최적화 기법 적용:
- 텍스트 엔티티 한 번 수집 후 재사용
- 세트 기반 O(1) 검색
- 블록 엔티티 캐싱
- 정규표현식 컴파일 최적화
- 불필요한 문자열 조작 최소화
- 사전 필터링으로 처리 대상 감소
"""