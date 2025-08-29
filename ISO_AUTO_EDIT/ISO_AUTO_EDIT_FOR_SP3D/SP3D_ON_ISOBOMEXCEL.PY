import os
import re
import ezdxf
import sys
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
    exit()

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

def get_text(e):
    try:
        text = ''
        if hasattr(e, 'dxf') and hasattr(e.dxf, 'text'):
            text = e.dxf.text
        elif hasattr(e, 'text'):
            text = e.text
        
        # 특수 유니코드 공백 문자들을 일반 공백으로 치환
        if text:
            # 문자열로 표현된 유니코드 이스케이프 시퀀스 처리
            # 예: "\\U+2004" 문자열을 공백으로 변환
            text = re.sub(r'\\U\+[0-9A-Fa-f]{4}', ' ', text)
            
            # 다양한 유니코드 공백 문자들
            unicode_spaces = [
                '\u2000',  # En Quad
                '\u2001',  # Em Quad
                '\u2002',  # En Space
                '\u2003',  # Em Space
                '\u2004',  # Three-Per-Em Space
                '\u2005',  # Four-Per-Em Space
                '\u2006',  # Six-Per-Em Space
                '\u2007',  # Figure Space
                '\u2008',  # Punctuation Space
                '\u2009',  # Thin Space
                '\u200A',  # Hair Space
                '\u202F',  # Narrow No-Break Space
                '\u205F',  # Medium Mathematical Space
                '\u3000',  # Ideographic Space
                '\xa0',    # Non-breaking space
            ]
            for space in unicode_spaces:
                text = text.replace(space, ' ')
            
            # 연속된 공백을 하나로 축소
            text = ' '.join(text.split())
            
        return text
    except Exception:
        pass
    return ''

def get_text_from_blocks(doc, msp):
    """블록 내부의 텍스트를 포함하여 모든 텍스트 수집"""
    all_texts = []
    # 1) 모델공간 TEXT/MTEXT
    for e in msp.query('TEXT MTEXT'):
        txt = get_text(e)  # 이미 처리된 텍스트
        x, y = get_xy(e)
        if txt:
            all_texts.append((x, y, txt, 'normal'))
    # 2) INSERT 블록 내부 TEXT/MTEXT
    for insert in msp.query('INSERT'):
        insert_point = insert.dxf.insert
        x_scale = insert.dxf.xscale if hasattr(insert.dxf, 'xscale') else 1
        y_scale = insert.dxf.yscale if hasattr(insert.dxf, 'yscale') else 1
        rotation = insert.dxf.rotation if hasattr(insert.dxf, 'rotation') else 0
        block_name = insert.dxf.name
        if block_name in doc.blocks:
            block = doc.blocks[block_name]
            for entity in block:
                if entity.dxftype() in ['TEXT', 'MTEXT']:
                    txt = get_text(entity)  # 이미 처리된 텍스트
                    if not txt:
                        continue
                    local_x, local_y = get_xy(entity)
                    if rotation != 0:
                        rad = math.radians(rotation)
                        cos_r = math.cos(rad)
                        sin_r = math.sin(rad)
                        abs_x = insert_point[0] + (local_x * cos_r - local_y * sin_r) * x_scale
                        abs_y = insert_point[1] + (local_x * sin_r + local_y * cos_r) * y_scale
                    else:
                        abs_x = insert_point[0] + local_x * x_scale
                        abs_y = insert_point[1] + local_y * y_scale
                    all_texts.append((abs_x, abs_y, txt, 'block'))
    return all_texts

def find_texts_in_area_with_blocks(doc, msp, x_min, x_max, y_min, y_max):
    """블록 포함 특정 영역 내 텍스트 목록 (텍스트만 리스트)"""
    texts = []
    all_texts = get_text_from_blocks(doc, msp)
    for x, y, txt, source in all_texts:
        if x_min <= x <= x_max and y_min <= y <= y_max:
            texts.append((x, y, txt))
    texts.sort(key=lambda t: -t[1])  # Y 내림차순
    return [t[2] for t in texts]

def find_text_in_rect_with_blocks(doc, msp, x_min, x_max, y_min, y_max, condition=None):
    """블록 포함 사각형 영역 첫 번째 텍스트"""
    all_texts = get_text_from_blocks(doc, msp)
    for x, y, txt, source in all_texts:
        if x_min <= x <= x_max and y_min <= y <= y_max:
            if condition:
                if condition(txt):
                    return txt
            elif txt:
                return txt
    return None

def find_text_near_point_with_blocks(doc, msp, cx, cy, tol_x, tol_y, condition=None):
    """중심점 (cx,cy) 기준 ±tol_x, ±tol_y 박스에서 텍스트 검색"""
    return find_text_in_rect_with_blocks(doc, msp, cx - tol_x, cx + tol_x, cy - tol_y, cy + tol_y, condition)

def extract_number(text):
    """텍스트에서 숫자만 추출 -> float"""
    if not text:
        return 0
    numbers = re.findall(r'[\d.]+', str(text))
    if numbers:
        try:
            return float(numbers[0])
        except ValueError:
            return 0
    return 0

def is_numeric_text(s: str) -> bool:
    """순수 숫자(정수/소수)만 인정"""
    if s is None:
        return False
    s = str(s).strip()
    return bool(re.fullmatch(r'\d+(\.\d+)?', s))

def clean_text_for_excel(text):
    """Excel 저장 전 텍스트 정리"""
    if not text:
        return ''
    
    # 문자열로 변환
    text = str(text)
    
    # 문자열로 표현된 유니코드 이스케이프 시퀀스 처리
    # 예: "\\U+2004" 문자열을 공백으로 변환
    import re
    text = re.sub(r'\\U\+[0-9A-Fa-f]{4}', ' ', text)
    
    # 특수 유니코드 공백 문자들을 일반 공백으로 치환
    unicode_spaces = [
        '\u2000', '\u2001', '\u2002', '\u2003', '\u2004', '\u2005',
        '\u2006', '\u2007', '\u2008', '\u2009', '\u200A', '\u202F',
        '\u205F', '\u3000', '\xa0',
        '\u00A0',  # Non-breaking space
        '\u1680',  # Ogham Space Mark
        '\u180E',  # Mongolian Vowel Separator
        '\u2028',  # Line Separator
        '\u2029',  # Paragraph Separator
        '\u200B',  # Zero Width Space
        '\u200C',  # Zero Width Non-Joiner
        '\u200D',  # Zero Width Joiner
        '\uFEFF',  # Zero Width No-Break Space
    ]
    
    cleaned = text
    for space in unicode_spaces:
        if space in cleaned:
            cleaned = cleaned.replace(space, ' ')
    
    # 탭과 줄바꿈을 공백으로
    cleaned = cleaned.replace('\t', ' ').replace('\n', ' ').replace('\r', ' ')
    
    # 연속된 공백을 하나로 축소
    cleaned = ' '.join(cleaned.split())
    
    # 모든 제어 문자 제거
    import unicodedata
    cleaned = ''.join(char for char in cleaned if not unicodedata.category(char).startswith('C'))
    
    return cleaned.strip()

def split_text_by_distance(texts_with_pos, threshold=10):
    """X 거리 기준 분리"""
    if not texts_with_pos:
        return []
    texts_with_pos.sort(key=lambda t: t[0])
    result = []
    current_group = [clean_text_for_excel(texts_with_pos[0][2])]
    last_x = texts_with_pos[0][0]
    for i in range(1, len(texts_with_pos)):
        x, y, txt = texts_with_pos[i]
        cleaned_txt = clean_text_for_excel(txt)
        if x - last_x >= threshold:
            result.append(' '.join(current_group))
            current_group = [cleaned_txt]
        else:
            current_group.append(cleaned_txt)
        last_x = x
    if current_group:
        result.append(' '.join(current_group))
    return result

def assign_values_by_header_position(row_texts, header_positions, tolerance=20):
    """헤더 위치를 기반으로 각 텍스트를 적절한 컬럼에 할당"""
    values = {header: '' for header in header_positions.keys()}
    
    # 각 텍스트를 가장 가까운 헤더에 할당
    for x, y, txt in row_texts:
        cleaned_txt = clean_text_for_excel(txt)
        if not cleaned_txt:
            continue
            
        closest_header = None
        min_distance = float('inf')
        
        for header, header_x in header_positions.items():
            distance = abs(x - header_x)
            if distance < min_distance and distance < tolerance:
                min_distance = distance
                closest_header = header
        
        if closest_header:
            if values[closest_header]:  # 이미 값이 있으면 추가
                values[closest_header] += ' ' + cleaned_txt
            else:
                values[closest_header] = cleaned_txt
    
    return values

# Command line arguments 처리
if len(sys.argv) < 2:
    print("사용법: python PLTONEWLINE.py file1.dxf file2.dxf ...")
    sys.exit(1)

file_paths = sys.argv[1:]

# 헤더 미검출 시 고정 좌표
FALLBACK_Y_HEADER = 546.0
FALLBACK_Y_LIMIT  = 250.0
FALLBACK_X_TOL    = 4.0
FALLBACK_COLS = {
    'PT': 618.0,
    'COMPONENT': 630.0,
    'SIZE': 738.0,
    "Q'TY": 766.0,
    'WEIGHT': 793.2,
}

# 제목/리비전 보정 좌표 (±10mm)
ISO_DWG_FALLBACK = (708.0, 42.5, 10.0, 10.0)  # cx, cy, tx, ty
SHEETNO_FALLBACK = (799.0, 42.5, 10.0, 10.0)
REVNO_FALLBACK   = (803.0, 20.0, 10.0, 10.0)

for file_path in file_paths:
    # 수집 버퍼 - 각 파일마다 초기화
    all_data = []
    sheet_data = {
        'FABMAT': [],
        'ERECMAT': [],
        'PIPE': [],
        'VALV': [],
        'BOLT-NUT': [],
        'FITTINGS': []
    }
    
    try:
        doc = ezdxf.readfile(file_path)
        msp = doc.modelspace()
    except Exception as e:
        continue

    # 1) LINE NO
    lineno_texts = find_texts_in_area_with_blocks(doc, msp, 35, 115, 15, 75)
    if lineno_texts:
        processed_linenos = []
        first_lineno = lineno_texts[0] if lineno_texts else ''
        for i, text in enumerate(lineno_texts):
            if i == 0:
                processed_linenos.append(text)
            else:
                common_prefix = ''
                for j in range(min(len(first_lineno), len(text))):
                    if first_lineno[j] == text[j]:
                        common_prefix += first_lineno[j]
                    else:
                        break
                if common_prefix and '-' in common_prefix:
                    last_dash = common_prefix.rfind('-')
                    if last_dash >= 0:
                        common_prefix = common_prefix[:last_dash+1]
                remaining_text = text[len(common_prefix):] if len(common_prefix) < len(text) else text
                processed_linenos.append(remaining_text)
        lineno = '/'.join(processed_linenos)
    else:
        lineno = '-'

    # 2) INSU
    insu_texts = find_texts_in_area_with_blocks(doc, msp, 270, 310, 15, 75)
    insu = '/'.join(insu_texts) if insu_texts else '-'

    # 3) 제목/설명/시트/리비전 1차 추출
    dwgno = find_text_in_rect_with_blocks(doc, msp, 720, 750, 30, 40) or '-'
    isodesc = find_text_in_rect_with_blocks(doc, msp, 650, 750, 40, 50) or '-'
    sheetno = find_text_in_rect_with_blocks(doc, msp, 790, 820, 30, 50, lambda t: ('OF' in t.upper()) or ('/' in t)) or '-'
    revno = find_text_in_rect_with_blocks(doc, msp, 800, 850, 5, 20, lambda t: t.isdigit()) or '-'

    # 3-보정) ISO DWG NO / SH'T NO / REV NO 보정 (값 없거나 '-'일 때만)
    if not dwgno or str(dwgno).strip() == '-':
        cx, cy, tx, ty = ISO_DWG_FALLBACK
        fallback_dwg = find_text_near_point_with_blocks(doc, msp, cx, cy, tx, ty)
        if fallback_dwg:
            dwgno = fallback_dwg
    if not sheetno or str(sheetno).strip() == '-':
        cx, cy, tx, ty = SHEETNO_FALLBACK
        fallback_sheet = find_text_near_point_with_blocks(doc, msp, cx, cy, tx, ty, lambda t: 'OF' in t.upper())
        if fallback_sheet:
            sheetno = fallback_sheet
    if not revno or str(revno).strip() == '-':
        cx, cy, tx, ty = REVNO_FALLBACK
        fallback_rev = find_text_near_point_with_blocks(
        doc, msp, cx, cy, tx, ty,
        lambda t: re.fullmatch(r'[A-Z0-9]{1,2}', t.strip(), re.I)
)
        if fallback_rev:
            revno = fallback_rev

    # 4) 헤더 찾기 - 순서대로 PT, COMPONENT, SIZE, Q'TY, WEIGHT
    headers_order = ['PT', 'COMPONENT', 'SIZE', "Q'TY", 'WEIGHT']
    header_positions = {}
    all_texts = get_text_from_blocks(doc, msp)

    # 1단계: PT 헤더 찾기
    pt_header = None
    pt_x, pt_y = None, None
    for x, y, txt, source in all_texts:
        txt_upper = txt.upper()
        if txt_upper == 'PT' or (txt_upper.startswith('PT') and len(txt_upper) <= 5):
            pt_header = True
            pt_x, pt_y = x, y
            header_positions['PT'] = pt_x
            break

    # 2단계: COMPONENT 헤더 찾기
    comp_header = None
    comp_x, comp_y = None, None
    base_y = None
    
    if pt_header:
        # PT가 있으면 PT와 같은 Y선상에서 COMPONENT 찾기
        base_y = pt_y
        for x, y, txt, source in all_texts:
            if 'COMPONENT' in txt.upper() and abs(y - pt_y) <= 5:
                comp_header = True
                comp_x, comp_y = x, y
                header_positions['COMPONENT'] = comp_x
                break
    else:
        # PT가 없으면 COMPONENT 독립적으로 찾기
        for x, y, txt, source in all_texts:
            if 'COMPONENT' in txt.upper():
                comp_header = True
                comp_x, comp_y = x, y
                header_positions['COMPONENT'] = comp_x
                base_y = comp_y
                break

    # 헤더 미검출 시 고정 좌표 사용
    use_fallback = False
    if not comp_header and not pt_header:
        use_fallback = True
        header_positions = {k: v for k, v in FALLBACK_COLS.items()}
        comp_x = FALLBACK_COLS['COMPONENT']
        comp_y = FALLBACK_Y_HEADER
        base_y = comp_y

    # 3단계: 나머지 헤더들 찾기 (SIZE, Q'TY, WEIGHT)
    if not use_fallback and base_y:
        for x, y, txt, source in all_texts:
            txt_upper = txt.upper()
            if abs(y - base_y) <= 5:
                if 'SIZE' in txt_upper and 'SIZE' not in header_positions:
                    header_positions['SIZE'] = x
                elif ("Q'TY" in txt_upper or 'QTY' in txt_upper) and "Q'TY" not in header_positions:
                    header_positions["Q'TY"] = x
                elif 'WEIGHT' in txt_upper and 'T.WEIGHT' not in txt_upper and 'WEIGHT' not in header_positions:
                    header_positions['WEIGHT'] = x

    # 5) 테이블 행 스캔
    all_rows_data = []
    
    # 변수 초기화 (정상/대체 경로 모두에서 사용)
    erection_materials_found = False
    erection_materials_index = -1
    fabrication_weight_found = False
    fabrication_weight_index = -1
    erection_weight_found = False

    if not use_fallback:
        y_limit = comp_y - 250
        comp_data_y_positions = []
        for x, y, txt, source in all_texts:
            if comp_x - 20 <= x <= comp_x + 180 and y < comp_y - 5 and y >= y_limit and txt:
                comp_data_y_positions.append(y)
        comp_data_y_positions = sorted(list(set(comp_data_y_positions)), reverse=True)

        # ERECTION MATERIALS/WEIGHT 찾기
        erection_materials_found = False
        erection_materials_index = -1
        erection_weight_found = False
        last_pt_y = None  # 마지막 PT가 있는 Y 좌표 저장
        
        for idx, data_y in enumerate(comp_data_y_positions):
            row_texts = []
            for x, y, txt, source in all_texts:
                if abs(y - data_y) <= 2 and comp_x - 20 <= x <= comp_x + 180 and txt:
                    row_texts.append((x, y, txt))
            if not row_texts:
                continue
            row_texts.sort(key=lambda t: t[0])
            # 각 텍스트를 정리한 후 합치기
            cleaned_texts = []
            for x, y, txt in row_texts:
                cleaned = clean_text_for_excel(txt)
                if cleaned:
                    cleaned_texts.append(cleaned)
            totxt = ' '.join(cleaned_texts)

            # ERECTION MATERIALS 체크
            if 'ERECTION MATERIAL' in totxt.upper():
                erection_materials_found = True
                erection_materials_index = idx
                
            # ERECTION WEIGHT 체크
            if 'ERECTION WEIGHT' in totxt.upper():
                erection_weight_found = True
                break

            # 헤더 위치 기반 값 할당
            if header_positions:
                row_values = assign_values_by_header_position(row_texts, header_positions)
                pt_value = row_values.get('PT', '')
                comp_value = row_values.get('COMPONENT', '')
                size_value = row_values.get('SIZE', '')
                qty_value = row_values.get("Q'TY", '')
                weight_value = row_values.get('WEIGHT', '')
            else:
                # 기존 방식 (거리 기반)
                separated_values = split_text_by_distance(row_texts, 10)
                pt_value = ''
                comp_value = ''
                size_value = ''
                qty_value = ''
                weight_value = ''

                if len(separated_values) > 0:
                    if separated_values[0].isdigit():
                        pt_value = separated_values[0]
                        if len(separated_values) > 1:
                            comp_value = separated_values[1]
                        if len(separated_values) > 2:
                            size_value = separated_values[2]
                        if len(separated_values) > 3:
                            qty_value = separated_values[3]
                        if len(separated_values) > 4:
                            weight_value = separated_values[4]
                    else:
                        comp_value = ' '.join(separated_values[:2]) if len(separated_values) > 1 else separated_values[0]
                        if len(separated_values) > 2:
                            size_value = separated_values[2]
                        if len(separated_values) > 3:
                            qty_value = separated_values[3]
                        if len(separated_values) > 4:
                            weight_value = separated_values[4]

            # PT가 있고 숫자인 경우 마지막 PT Y 좌표 업데이트
            if pt_value and is_numeric_text(pt_value):
                last_pt_y = data_y

            row_data = {
                'totxt': totxt,
                'pt': pt_value,
                'comp': comp_value,
                'size': size_value,
                'qty': qty_value,
                'weight': weight_value,
                'y_pos': data_y,
                'index': idx  # 인덱스 추가
            }
            all_rows_data.append(row_data)

        # 특수 텍스트(ERECTION WEIGHT, FABRICATION WEIGHT, ERECTION MATERIALS) 추가 검색
        # X 범위: PT X값 ~ WEIGHT X값 (또는 가장 왼쪽/오른쪽 헤더)
        # Y 범위: 마지막 PT Y값 - 20mm까지
        if not erection_weight_found and last_pt_y and header_positions:
            # X 범위 결정
            header_x_values = list(header_positions.values())
            search_x_min = min(header_x_values) - 10  # 가장 왼쪽 헤더
            search_x_max = max(header_x_values) + 10  # 가장 오른쪽 헤더
            
            # PT와 WEIGHT가 있으면 그것을 사용
            if 'PT' in header_positions and 'WEIGHT' in header_positions:
                search_x_min = header_positions['PT'] - 10
                search_x_max = header_positions['WEIGHT'] + 10
            
            search_y_min = last_pt_y - 20
            search_y_max = last_pt_y
            
            for x, y, txt, source in all_texts:
                if search_x_min <= x <= search_x_max and search_y_min <= y <= search_y_max:
                    txt_upper = txt.upper()
                    
                    if 'ERECTION WEIGHT' in txt_upper and not erection_weight_found:
                        erection_weight_found = True
                    elif 'FABRICATION WEIGHT' in txt_upper and not fabrication_weight_found:
                        fabrication_weight_found = True
                        # Y 좌표를 기준으로 인덱스 찾기
                        for i, row in enumerate(all_rows_data):
                            if row['y_pos'] < y:  # FABRICATION WEIGHT보다 아래에 있는 첫 번째 행
                                fabrication_weight_index = i
                                break
                        if fabrication_weight_index == -1:
                            fabrication_weight_index = len(all_rows_data)
                    elif 'ERECTION MATERIAL' in txt_upper and not erection_materials_found:
                        erection_materials_found = True
                        # Y 좌표를 기준으로 인덱스 찾기
                        for i, row in enumerate(all_rows_data):
                            if row['y_pos'] < y:  # ERECTION MATERIALS보다 아래에 있는 첫 번째 행
                                erection_materials_index = i
                                break
                        if erection_materials_index == -1:
                            erection_materials_index = len(all_rows_data)

        # 전체 텍스트에서 FABRICATION WEIGHT, ERECTION MATERIALS 찾기
        # 테이블 영역 내외 모두 검색
        fabrication_weight_y = None
        erection_materials_y = None
        
        for x, y, txt, source in all_texts:
            txt_upper = txt.upper()
            # 테이블 X 범위 근처에서만 검색 (±50mm 여유)
            if comp_x - 70 <= x <= comp_x + 230:
                if 'FABRICATION WEIGHT' in txt_upper and not fabrication_weight_y:
                    fabrication_weight_y = y
                elif 'ERECTION MATERIAL' in txt_upper and not erection_materials_y:
                    erection_materials_y = y
        
        # Y 좌표 기준으로 인덱스 결정
        if fabrication_weight_y:
            found_index = -1
            for i, row in enumerate(all_rows_data):
                row_y = row['y_pos']
                if row_y < fabrication_weight_y:  # FABRICATION WEIGHT보다 아래
                    found_index = i
                    break
            
            if found_index >= 0:
                fabrication_weight_found = True
                fabrication_weight_index = found_index - 1  # 바로 다음 행부터 EREC이므로 -1
        
        if erection_materials_y:
            found_index = -1
            for i, row in enumerate(all_rows_data):
                row_y = row['y_pos']
                if row_y < erection_materials_y:  # ERECTION MATERIALS보다 아래
                    found_index = i
                    break
            
            if found_index >= 0:
                erection_materials_found = True
                erection_materials_index = found_index - 1  # 바로 다음 행부터 EREC이므로 -1

        fabrication_found = any('FABRICATION' in r['totxt'].upper() for r in all_rows_data)

    else:
        # 대체 경로
        col_windows = {name: (xc - FALLBACK_X_TOL, xc + FALLBACK_X_TOL) for name, xc in header_positions.items()}
        y_start = FALLBACK_Y_HEADER
        y_limit = FALLBACK_Y_LIMIT

        y_candidates = []
        for x, y, txt, source in all_texts:
            if txt and (y < y_start - 5) and (y >= y_limit):
                for (xmin, xmax) in col_windows.values():
                    if xmin <= x <= xmax:
                        y_candidates.append(y)
                        break
        y_candidates = sorted(set(y_candidates), reverse=True)
        merged_y_positions = []
        for y in y_candidates:
            if not merged_y_positions:
                merged_y_positions.append(y)
            else:
                if abs(merged_y_positions[-1] - y) <= 2.0:
                    continue
                merged_y_positions.append(y)

        last_pt_y = None  # 마지막 PT가 있는 Y 좌표 저장
        
        for idx, data_y in enumerate(merged_y_positions):
            per_col_tokens = {k: [] for k in col_windows.keys()}
            row_tokens_for_totxt = []
            for x, y, txt, source in all_texts:
                if not txt:
                    continue
                if abs(y - data_y) <= 2.0:
                    matched_any = False
                    for col_name, (xmin, xmax) in col_windows.items():
                        if xmin <= x <= xmax:
                            per_col_tokens[col_name].append((x, y, txt))
                            matched_any = True
                    if matched_any:
                        row_tokens_for_totxt.append((x, y, txt))
            if not any(per_col_tokens[col] for col in per_col_tokens):
                continue
            for col in per_col_tokens:
                per_col_tokens[col].sort(key=lambda t: t[0])

            pt_value = ' '.join([clean_text_for_excel(t[2]) for t in per_col_tokens['PT']]).strip()
            comp_value = ' '.join([clean_text_for_excel(t[2]) for t in per_col_tokens['COMPONENT']]).strip()
            size_value = ' '.join([clean_text_for_excel(t[2]) for t in per_col_tokens['SIZE']]).strip()
            qty_value = ' '.join([clean_text_for_excel(t[2]) for t in per_col_tokens["Q'TY"]]).strip()
            weight_value = ' '.join([clean_text_for_excel(t[2]) for t in per_col_tokens['WEIGHT']]).strip()

            # PT가 있고 숫자인 경우 마지막 PT Y 좌표 업데이트
            if pt_value and is_numeric_text(pt_value):
                last_pt_y = data_y

            row_tokens_for_totxt.sort(key=lambda t: t[0])
            # 각 텍스트를 정리한 후 합치기
            cleaned_texts = []
            for x, y, txt in row_tokens_for_totxt:
                cleaned = clean_text_for_excel(txt)
                if cleaned:
                    cleaned_texts.append(cleaned)
            totxt = ' '.join(cleaned_texts)

            # ERECTION MATERIALS 체크
            if 'ERECTION MATERIAL' in totxt.upper():
                erection_materials_found = True
                erection_materials_index = idx
            
            # FABRICATION WEIGHT 체크
            if 'FABRICATION WEIGHT' in totxt.upper():
                fabrication_weight_found = True
                fabrication_weight_index = idx

            row_data = {
                'totxt': totxt,
                'pt': pt_value,
                'comp': comp_value,
                'size': size_value,
                'qty': qty_value,
                'weight': weight_value,
                'y_pos': data_y,
                'index': idx  # 인덱스 추가
            }
            all_rows_data.append(row_data)

        # 특수 텍스트(ERECTION WEIGHT, FABRICATION WEIGHT, ERECTION MATERIALS) 추가 검색
        # X 범위: PT X값 ~ WEIGHT X값
        # Y 범위: 마지막 PT Y값 - 20mm까지
        if last_pt_y and 'PT' in header_positions and 'WEIGHT' in header_positions:
            search_x_min = header_positions['PT'] - FALLBACK_X_TOL
            search_x_max = header_positions['WEIGHT'] + FALLBACK_X_TOL
            search_y_min = last_pt_y - 20
            search_y_max = last_pt_y
            
            for x, y, txt, source in all_texts:
                if search_x_min <= x <= search_x_max and search_y_min <= y <= search_y_max:
                    txt_upper = txt.upper()
                    if 'ERECTION WEIGHT' in txt_upper and not erection_weight_found:
                        erection_weight_found = True
                    elif 'FABRICATION WEIGHT' in txt_upper and not fabrication_weight_found:
                        fabrication_weight_found = True
                        # 현재 행 위치를 인덱스로 추정 (마지막 데이터 행 + 1)
                        fabrication_weight_index = len(all_rows_data)
                    elif 'ERECTION MATERIAL' in txt_upper and not erection_materials_found:
                        erection_materials_found = True
                        erection_materials_index = len(all_rows_data)

        # 전체 텍스트에서 FABRICATION WEIGHT, ERECTION MATERIALS 찾기 (대체 경로)
        # 테이블 영역 내외 모두 검색
        fabrication_weight_y = None
        erection_materials_y = None
        
        # 테이블 X 범위 결정
        x_min = min(header_positions.values()) - 50
        x_max = max(header_positions.values()) + 50
        
        for x, y, txt, source in all_texts:
            txt_upper = txt.upper()
            # 테이블 X 범위 근처에서만 검색
            if x_min <= x <= x_max:
                if 'FABRICATION WEIGHT' in txt_upper and not fabrication_weight_y:
                    fabrication_weight_y = y
                elif 'ERECTION MATERIAL' in txt_upper and not erection_materials_y:
                    erection_materials_y = y
        
        # Y 좌표 기준으로 인덱스 결정
        if fabrication_weight_y:
            found_index = -1
            for i, row in enumerate(all_rows_data):
                if row['y_pos'] < fabrication_weight_y:  # FABRICATION WEIGHT보다 아래
                    found_index = i
                    break
            
            if found_index >= 0:
                fabrication_weight_found = True
                fabrication_weight_index = found_index - 1  # 바로 다음 행부터 EREC이므로 -1
        
        if erection_materials_y:
            found_index = -1
            for i, row in enumerate(all_rows_data):
                if row['y_pos'] < erection_materials_y:  # ERECTION MATERIALS보다 아래
                    found_index = i
                    break
            
            if found_index >= 0:
                erection_materials_found = True
                erection_materials_index = found_index - 1  # 바로 다음 행부터 EREC이므로 -1

        erection_weight_found = erection_weight_found or any('ERECTION WEIGHT' in r['totxt'].upper() for r in all_rows_data)
        if erection_weight_found:
            # ERECTION WEIGHT가 있는 행 찾기
            cut_idx = -1
            for i, r in enumerate(all_rows_data):
                if 'ERECTION WEIGHT' in r['totxt'].upper():
                    cut_idx = i
                    break
            if cut_idx >= 0:
                all_rows_data = all_rows_data[:cut_idx]
        
        fabrication_found = any('FABRICATION' in r['totxt'].upper() for r in all_rows_data)

    # 6) FABRICATION 컷
    if not erection_weight_found and fabrication_found:
        last_fab_index = -1
        for i, row in enumerate(all_rows_data):
            if 'FABRICATION' in row['totxt'].upper():
                last_fab_index = i
        if last_fab_index >= 0:
            all_rows_data = all_rows_data[:last_fab_index + 1]

    # 7) PT 없는 행 병합 + (추가) PT 비숫자 SKIP
    merged_data = []
    last_pt_data = None
    empty_lines = []

    for row in all_rows_data:
        totxt_upper = row['totxt'].upper()
            
        if 'FABRICATION' in totxt_upper or 'ERECTION' in totxt_upper:
            continue

        if row['pt']:  # PT 문자열 존재
            # === 추가: PT가 숫자가 아니면 SKIP ===
            if not is_numeric_text(row['pt']):
                continue

            # 이전 PT에 모여있던 빈 행 병합
            if last_pt_data and empty_lines:
                for empty_row in empty_lines:
                    if empty_row['totxt'].strip():
                        cleaned_empty_text = clean_text_for_excel(empty_row['totxt'])
                        tupper = cleaned_empty_text.upper()
                        if 'FABRICATION' not in tupper and 'ERECTION' not in tupper:
                            # comp 값도 다시 정리
                            last_pt_data['comp'] = clean_text_for_excel(last_pt_data['comp'] + ' ' + cleaned_empty_text)

            last_pt_data = row.copy()
            merged_data.append(last_pt_data)
            empty_lines = []

        else:
            # PT가 완전히 비어있을 때만 이전 PT에 붙이기 후보로 보관
            empty_lines.append(row)

    # 마지막 empty_lines 처리
    if last_pt_data and empty_lines:
        for empty_row in empty_lines:
            if empty_row['totxt'].strip():
                cleaned_empty_text = clean_text_for_excel(empty_row['totxt'])
                tupper = cleaned_empty_text.upper()
                if 'FABRICATION' not in tupper and 'ERECTION' not in tupper:
                    # comp 값도 다시 정리
                    last_pt_data['comp'] = clean_text_for_excel(last_pt_data['comp'] + ' ' + cleaned_empty_text)

    # 8) 최종 전처리 → 레코드화
    all_totxt = []
    for data in merged_data:
        # 각 값을 clean_text_for_excel로 정리
        pt_value = clean_text_for_excel(data['pt'])
        comp_value = clean_text_for_excel(data['comp'])
        size_value = clean_text_for_excel(data['size'])
        qty_value = clean_text_for_excel(data['qty'])
        weight_value = clean_text_for_excel(data['weight'])
        totxt = clean_text_for_excel(data['totxt'])

        totxt_upper = totxt.upper()
        comp_upper = comp_value.upper()
        
        if ('FABRICATION' in totxt_upper or 'ERECTION' in totxt_upper or
            'FABRICATION' in comp_upper or 'ERECTION' in comp_upper):
            continue

        item_value = ''
        endtype_value = ''
        mate_value = ''
        sch_value = ''

        if 'SPIRAL' in totxt_upper:
            comp_parts = comp_value.split(',')
            if len(comp_parts) >= 3:
                item_value = clean_text_for_excel(comp_parts[0])
                if len(comp_parts) > 1:
                    item_value += ', ' + clean_text_for_excel(comp_parts[1])
                if len(comp_parts) > 2:
                    item_value += ', ' + clean_text_for_excel(comp_parts[2])
            if len(comp_parts) > 3:
                mate_value = clean_text_for_excel(comp_parts[3])
            if len(comp_parts) > 4:
                sch_value = clean_text_for_excel(comp_parts[4])
        elif 'BOLT' in comp_upper or 'NUT' in comp_upper:
            comp_parts = comp_value.split(',')
            if len(comp_parts) > 0:
                item_value = clean_text_for_excel(comp_parts[0])
            if len(comp_parts) > 1:
                second_part = clean_text_for_excel(comp_parts[1])
                if '-' in second_part:
                    dash_pos = second_part.find('-')
                    mate_value = clean_text_for_excel(second_part[:dash_pos])
                    sch_value = clean_text_for_excel(second_part[dash_pos+1:])
                else:
                    mate_value = second_part
                    if len(comp_parts) > 2:
                        sch_value = clean_text_for_excel(comp_parts[2])
        else:
            comp_parts = comp_value.split(',')
            if len(comp_parts) > 0:
                item_value = clean_text_for_excel(comp_parts[0])
            if len(comp_parts) > 1:
                endtype_value = clean_text_for_excel(comp_parts[1])
            if len(comp_parts) > 2:
                mate_value = clean_text_for_excel(comp_parts[2])
            if len(comp_parts) > 3:
                sch_value = clean_text_for_excel(comp_parts[3])

        # T.WEIGHT = U.WEIGHT * QTY
        tweight_value = ''
        try:
            weight_float = extract_number(weight_value)
            qty_float = extract_number(qty_value)
            if weight_float > 0 and qty_float > 0:
                tweight = weight_float * qty_float
                tweight_value = str(int(tweight)) if tweight.is_integer() else str(round(tweight, 1))
        except Exception:
            tweight_value = ''

        # 단위
        uni_value = 'M' if 'PIPE' in item_value.upper() else 'EA'

        data_row = {
            'TOTXT': totxt,
            'ISO DWG NO': dwgno,
            'LINE NO': lineno,
            'ISO DESC.': isodesc,
            'SH\'T NO': sheetno,
            'REV. NO': revno,
            'ITEM NO': pt_value,
            'ITEM': item_value,
            'END TYPE': endtype_value,
            'MATERIAL': mate_value,
            'SCH/RATING': sch_value,
            'SIZE': size_value,
            "Q'TY": qty_value,
            '(M/EA)': uni_value,
            'U.WEIGHT': weight_value,
            'T.WEIGHT': tweight_value,
            'INSU. THK': insu,
            'REMARK': '',
            'original_index': data.get('index', -1)  # 원본 인덱스 저장
        }
        all_totxt.append(data_row)

    # 9) 시트 분류 - ERECTION MATERIALS 기준으로 개선
    for totxt_data in all_totxt:
        data_copy = totxt_data.copy()
        if 'TOTXT' in data_copy:
            del data_copy['TOTXT']
        if 'original_index' in data_copy:
            orig_idx = data_copy['original_index']
            del data_copy['original_index']
        else:
            orig_idx = -1

        # ERECTION MATERIALS가 있으면 그 이후는 모두 ERECMAT
        # ERECTION MATERIALS가 없고 FABRICATION WEIGHT가 있으면 그 이후는 모두 ERECMAT
        is_fabmat = True
        is_erecmat = False
        
        if erection_materials_found and erection_materials_index >= 0 and orig_idx >= 0:
            if orig_idx > erection_materials_index:
                is_fabmat = False
                is_erecmat = True
        elif not erection_materials_found and fabrication_weight_found and fabrication_weight_index >= 0 and orig_idx >= 0:
            # ERECTION MATERIALS를 찾지 못했지만 FABRICATION WEIGHT를 찾은 경우
            if orig_idx > fabrication_weight_index:
                is_fabmat = False
                is_erecmat = True
        
        if is_fabmat:
            sheet_data['FABMAT'].append(data_copy)
        if is_erecmat:
            sheet_data['ERECMAT'].append(data_copy)

        item_upper = data_copy.get('ITEM', '').upper()
        if 'PIPE' in item_upper:
            sheet_data['PIPE'].append(data_copy)

        valv_keywords = ['VALV', 'V/V', 'NRV', 'MOV', 'PCV']
        if any(keyword in item_upper for keyword in valv_keywords):
            sheet_data['VALV'].append(data_copy)

        bolt_keywords = ['BOLT', 'NUT', 'GASKET', 'GRAPHITE', 'WOUND', 'RING']
        if any(keyword in item_upper for keyword in bolt_keywords):
            sheet_data['BOLT-NUT'].append(data_copy)

        is_fitting = True
        if 'PIPE' in item_upper:
            is_fitting = False
        elif any(keyword in item_upper for keyword in valv_keywords):
            is_fitting = False
        elif any(keyword in item_upper for keyword in bolt_keywords):
            is_fitting = False

        if is_fitting and item_upper:
            sheet_data['FITTINGS'].append(data_copy)

        all_data.append(data_copy)

    # 10) Excel 저장
    if all_data:
        # Excel 파일명
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        today = datetime.now().strftime("%Y%m%d_%H%M%S")
        excel_filename = f"{base_name}_BOM_{today}.xlsx"
        excel_path = os.path.join(os.path.dirname(file_path), excel_filename)
        
        wb = Workbook()
        headers = ['ISO DWG NO', 'LINE NO', 'ISO DESC.', 'SH\'T NO', 'REV. NO', 'ITEM NO', 
                   'ITEM', 'END TYPE', 'MATERIAL', 'SCH/RATING', 'SIZE', "Q'TY", 
                   '(M/EA)', 'U.WEIGHT', 'T.WEIGHT', 'INSU. THK', 'REMARK']
        
        header_font = Font(size=12, bold=True)
        header_alignment = Alignment(horizontal='center', vertical='center')
        header_border = Border(left=Side(style='thick'), right=Side(style='thick'),
                               top=Side(style='thick'), bottom=Side(style='thick'))
        data_font = Font(size=11)
        data_alignment = Alignment(horizontal='center', vertical='center')
        data_border = Border(left=Side(style='thin'), right=Side(style='thin'),
                             top=Side(style='thin'), bottom=Side(style='thin'))
        
        ws = wb.active
        ws.title = "MTO Data"
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=header)
            cell.font = header_font
            cell.alignment = header_alignment
            cell.border = header_border
        for row_idx, data in enumerate(all_data, 2):
            for col_idx, header in enumerate(headers, 1):
                value = data.get(header, '')
                # Excel 저장 전 텍스트 정리
                value = clean_text_for_excel(value)
                cell = ws.cell(row=row_idx, column=col_idx, value=value)
                cell.font = data_font
                cell.alignment = data_alignment
                cell.border = data_border
        for column in ws.columns:
            max_length = 0
            column_letter = get_column_letter(column[0].column)
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            ws.column_dimensions[column_letter].width = (max_length + 2) * 1.2
        
        # TOTAL BOM
        ws_total = wb.create_sheet(title="TOTAL BOM")
        total_bom_data = defaultdict(lambda: {'Q\'TY': 0, 'U.WEIGHT': '', '(M/EA)': ''})
        for row in all_data:
            key = (row.get('ITEM', ''), row.get('END TYPE', ''), row.get('MATERIAL', ''),
                   row.get('SCH/RATING', ''), row.get('SIZE', ''))
            qty = extract_number(row.get('Q\'TY', ''))
            total_bom_data[key]['Q\'TY'] += qty
            total_bom_data[key]['U.WEIGHT'] = row.get('U.WEIGHT', '')
            total_bom_data[key]['(M/EA)'] = row.get('(M/EA)', '')

        total_headers = ['ITEM', 'END TYPE', 'MATERIAL', 'SCH/RATING', 'SIZE', "Q'TY", '(M/EA)', 'T.WEIGHT']
        for col, header in enumerate(total_headers, 1):
            cell = ws_total.cell(row=1, column=col, value=header)
            cell.font = header_font
            cell.alignment = header_alignment
            cell.border = header_border
        
        total_weight_sum = 0
        row_idx = 2
        for (item, endtype, material, sch, size), data in total_bom_data.items():
            weight = extract_number(data['U.WEIGHT'])
            qty = data['Q\'TY']
            tweight = weight * qty if weight > 0 and qty > 0 else 0
            tweight_str = str(int(tweight)) if tweight and float(tweight).is_integer() else (str(round(tweight, 1)) if tweight else '')
            if tweight:
                total_weight_sum += tweight
            qty_str = str(int(qty)) if qty and float(qty).is_integer() else (str(round(qty, 1)) if qty else '')
            row_data = [item, endtype, material, sch, size, qty_str, data['(M/EA)'], tweight_str]
            for col_idx, value in enumerate(row_data, 1):
                # Excel 저장 전 텍스트 정리
                value = clean_text_for_excel(value)
                cell = ws_total.cell(row=row_idx, column=col_idx, value=value)
                cell.font = data_font
                cell.alignment = data_alignment
                cell.border = data_border
            row_idx += 1
        
        sum_row = row_idx
        cell = ws_total.cell(row=sum_row, column=1, value='TOTAL')
        cell.font = Font(size=12, bold=True)
        cell.alignment = header_alignment
        cell.border = header_border
        for col in range(2, 8):
            cell = ws_total.cell(row=sum_row, column=col, value='')
            cell.border = header_border
        sum_str = str(int(total_weight_sum)) if total_weight_sum and float(total_weight_sum).is_integer() else (str(round(total_weight_sum, 1)) if total_weight_sum else '0')
        cell = ws_total.cell(row=sum_row, column=8, value=sum_str)
        cell.font = Font(size=12, bold=True)
        cell.alignment = header_alignment
        cell.border = header_border
        for column in ws_total.columns:
            max_length = 0
            column_letter = get_column_letter(column[0].column)
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            ws_total.column_dimensions[column_letter].width = (max_length + 2) * 1.2
        
        # 분류 시트
        sheet_order = ['FAB MATERIAL', 'EREC MATERIAL', 'PIPE', 'FITTINGS', 'VALV', 'BOLT-NUT']
        sheet_mapping = {
            'FAB MATERIAL': 'FABMAT',
            'EREC MATERIAL': 'ERECMAT',
            'PIPE': 'PIPE',
            'FITTINGS': 'FITTINGS',
            'VALV': 'VALV',
            'BOLT-NUT': 'BOLT-NUT'
        }
        for sheet_name in sheet_order:
            data_key = sheet_mapping[sheet_name]
            if sheet_data[data_key] or sheet_name == 'EREC MATERIAL':
                ws_sheet = wb.create_sheet(title=sheet_name)
                for col, header in enumerate(headers, 1):
                    cell = ws_sheet.cell(row=1, column=col, value=header)
                    cell.font = header_font
                    cell.alignment = header_alignment
                    cell.border = header_border
                if sheet_data[data_key]:
                    for row_idx, data in enumerate(sheet_data[data_key], 2):
                        for col_idx, header in enumerate(headers, 1):
                            value = data.get(header, '')
                            # Excel 저장 전 텍스트 정리
                            value = clean_text_for_excel(value)
                            cell = ws_sheet.cell(row=row_idx, column=col_idx, value=value)
                            cell.font = data_font
                            cell.alignment = data_alignment
                            cell.border = data_border
                for column in ws_sheet.columns:
                    max_length = 0
                    column_letter = get_column_letter(column[0].column)
                    for cell in column:
                        try:
                            if len(str(cell.value)) > max_length:
                                max_length = len(str(cell.value))
                        except:
                            pass
                    ws_sheet.column_dimensions[column_letter].width = (max_length + 2) * 1.2
        
        wb.save(excel_path)