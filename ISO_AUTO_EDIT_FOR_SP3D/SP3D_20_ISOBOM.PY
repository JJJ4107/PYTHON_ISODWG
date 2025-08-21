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
        if hasattr(e, 'dxf') and hasattr(e.dxf, 'text'):
            return e.dxf.text
        elif hasattr(e, 'text'):
            return e.text
    except Exception:
        pass
    return ''

def get_text_from_blocks(doc, msp):
    """블록 내부의 텍스트를 포함하여 모든 텍스트 수집"""
    all_texts = []
    # 1) 모델공간 TEXT/MTEXT
    for e in msp.query('TEXT MTEXT'):
        txt = get_text(e).strip()
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
                    txt = get_text(entity).strip()
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

def split_text_by_distance(texts_with_pos, threshold=10):
    """X 거리 기준 분리"""
    if not texts_with_pos:
        return []
    texts_with_pos.sort(key=lambda t: t[0])
    result = []
    current_group = [texts_with_pos[0][2]]
    last_x = texts_with_pos[0][0]
    for i in range(1, len(texts_with_pos)):
        x, y, txt = texts_with_pos[i]
        if x - last_x >= threshold:
            result.append(' '.join(current_group))
            current_group = [txt]
        else:
            current_group.append(txt)
        last_x = x
    if current_group:
        result.append(' '.join(current_group))
    return result

# 파일 선택
root = tk.Tk()
root.withdraw()
file_paths = filedialog.askopenfilenames(
    title="DXF 도면 선택", filetypes=[("DXF files", "*.dxf")]
)
root.destroy()
if not file_paths:
    print("DXF 파일이 선택되지 않았습니다.")
    exit()

# Excel 파일명
today = datetime.now().strftime("%Y%m%d_%H%M%S")
excel_filename = f"TOTALBOM_{today}.xlsx"
excel_path = os.path.join(os.path.dirname(file_paths[0]), excel_filename)

# 수집 버퍼
all_data = []
sheet_data = {
    'FABMAT': [],
    'ERECMAT': [],
    'PIPE': [],
    'VALV': [],
    'BOLT-NUT': [],
    'FITTINGS': []
}

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
    print(f"\n처리 중: {os.path.basename(file_path)}")
    try:
        doc = ezdxf.readfile(file_path)
        msp = doc.modelspace()
    except Exception as e:
        print(f"파일 읽기 오류: {e}")
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
    print(f"  - LINENO: {lineno}")

    # 2) INSU
    insu_texts = find_texts_in_area_with_blocks(doc, msp, 270, 310, 15, 75)
    insu = '/'.join(insu_texts) if insu_texts else '-'
    print(f"  - INSU: {insu}")

    # 3) 제목/설명/시트/리비전 1차 추출
    dwgno = find_text_in_rect_with_blocks(doc, msp, 720, 750, 30, 40) or '-'
    isodesc = find_text_in_rect_with_blocks(doc, msp, 650, 750, 40, 50) or '-'
    sheetno = find_text_in_rect_with_blocks(doc, msp, 790, 810, 40, 50,  lambda t: ('OF' in t.upper()) or ('/' in t)) or '-'
    revno = find_text_in_rect_with_blocks(doc, msp, 800, 850, 5, 20, lambda t: t.isdigit()) or '-'

    # 3-보정) ISO DWG NO / SH'T NO / REV NO 보정 (값 없거나 '-'일 때만)
    if not dwgno or str(dwgno).strip() == '-':
        cx, cy, tx, ty = ISO_DWG_FALLBACK
        fallback_dwg = find_text_near_point_with_blocks(doc, msp, cx, cy, tx, ty)
        if fallback_dwg:
            dwgno = fallback_dwg
            print(f"  - ISO DWG NO 보정됨: {dwgno}")
    if not sheetno or str(sheetno).strip() == '-':
        cx, cy, tx, ty = SHEETNO_FALLBACK
        fallback_sheet = find_text_near_point_with_blocks(doc, msp, cx, cy, tx, ty, lambda t: 'OF' in t.upper())
        if fallback_sheet:
            sheetno = fallback_sheet
            print(f"  - SH'T NO 보정됨: {sheetno}")
    if not revno or str(revno).strip() == '-':
        cx, cy, tx, ty = REVNO_FALLBACK
        fallback_rev = find_text_near_point_with_blocks(
        doc, msp, cx, cy, tx, ty,
        lambda t: re.fullmatch(r'[A-Z0-9]{1,2}', t.strip(), re.I)
)
        if fallback_rev:
            revno = fallback_rev
            print(f"  - REV NO 보정됨: {revno}")

    print(f"  - DWGNO: {dwgno}")
    print(f"  - ISODESC: {isodesc}")
    print(f"  - SHEETNO: {sheetno}")
    print(f"  - REVNO: {revno}")

    # 4) 헤더 찾기
    headers = ['PT', 'COMPONENT', 'SIZE', "Q'TY", 'WEIGHT']
    header_positions = {}
    all_texts = get_text_from_blocks(doc, msp)

    # COMPONENT 헤더
    comp_header = None
    comp_x, comp_y = None, None
    for x, y, txt, source in all_texts:
        if 'COMPONENT' in txt.upper():
            comp_header = True
            comp_x, comp_y = x, y
            header_positions['COMPONENT'] = comp_x
            print(f"  - COMPONENT 헤더 발견 at ({comp_x:.1f}, {comp_y:.1f}) from {source}")
            break

    # 헤더 미검출 시 고정 좌표 사용
    use_fallback = False
    if not comp_header:
        print("  - COMPONENT 헤더 미검출 ▶ 고정 좌표(±2mm) 대체 스캔 사용")
        use_fallback = True
        header_positions = {k: v for k, v in FALLBACK_COLS.items()}
        comp_x = FALLBACK_COLS['COMPONENT']
        comp_y = FALLBACK_Y_HEADER

    # 다른 헤더는 정상 경로에서만 자동 탐색
    if not use_fallback:
        for x, y, txt, source in all_texts:
            txt_upper = txt.upper()
            if abs(y - comp_y) <= 5:
                if txt_upper == 'PT' or (txt_upper.startswith('PT') and len(txt_upper) <= 5):
                    header_positions['PT'] = x
                elif 'SIZE' in txt_upper:
                    header_positions['SIZE'] = x
                elif "Q'TY" in txt_upper or 'QTY' in txt_upper:
                    header_positions["Q'TY"] = x
                elif 'WEIGHT' in txt_upper and 'T.WEIGHT' not in txt_upper:
                    header_positions['WEIGHT'] = x
        print(f"  - 찾은 헤더들: {list(header_positions.keys())}")
    else:
        print(f"  - 고정 헤더 X: { {k: round(v,1) for k,v in header_positions.items()} }")
        print(f"  - Y 스캔: {comp_y:.1f} → {FALLBACK_Y_LIMIT:.1f}")

    # 5) 테이블 행 스캔
    all_rows_data = []

    if not use_fallback:
        y_limit = comp_y - 250
        print(f"\n  - 테이블 스캔: X {comp_x-20:.1f} ~ {comp_x+180:.1f}")
        print(f"  - Y 범위: {comp_y:.1f} ~ {y_limit:.1f} (250mm)")
        comp_data_y_positions = []
        for x, y, txt, source in all_texts:
            if comp_x - 20 <= x <= comp_x + 180 and y < comp_y - 5 and y >= y_limit and txt:
                comp_data_y_positions.append(y)
        comp_data_y_positions = sorted(list(set(comp_data_y_positions)), reverse=True)
        print(f"  - 발견된 행: {len(comp_data_y_positions)}")

        erection_weight_found = False
        for data_y in comp_data_y_positions:
            row_texts = []
            for x, y, txt, source in all_texts:
                if abs(y - data_y) <= 2 and comp_x - 20 <= x <= comp_x + 180 and txt:
                    row_texts.append((x, y, txt))
            if not row_texts:
                continue
            row_texts.sort(key=lambda t: t[0])
            totxt = ' '.join([t[2] for t in row_texts])

            if 'ERECTION WEIGHT' in totxt.upper():
                print(f"\n!!! ERECTION WEIGHT 발견: {totxt}")
                erection_weight_found = True
                break

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

            row_data = {
                'totxt': totxt,
                'pt': pt_value,
                'comp': comp_value,
                'size': size_value,
                'qty': qty_value,
                'weight': weight_value,
                'y_pos': data_y
            }
            all_rows_data.append(row_data)

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
        print(f"  - (대체) 발견된 행: {len(merged_y_positions)}")

        for data_y in merged_y_positions:
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

            pt_value = ' '.join([t[2] for t in per_col_tokens['PT']]).strip()
            comp_value = ' '.join([t[2] for t in per_col_tokens['COMPONENT']]).strip()
            size_value = ' '.join([t[2] for t in per_col_tokens['SIZE']]).strip()
            qty_value = ' '.join([t[2] for t in per_col_tokens["Q'TY"]]).strip()
            weight_value = ' '.join([t[2] for t in per_col_tokens['WEIGHT']]).strip()

            row_tokens_for_totxt.sort(key=lambda t: t[0])
            totxt = ' '.join([t[2] for t in row_tokens_for_totxt]).strip()

            row_data = {
                'totxt': totxt,
                'pt': pt_value,
                'comp': comp_value,
                'size': size_value,
                'qty': qty_value,
                'weight': weight_value,
                'y_pos': data_y
            }
            all_rows_data.append(row_data)

        erection_weight_found = any('ERECTION WEIGHT' in r['totxt'].upper() for r in all_rows_data)
        if erection_weight_found:
            print("\n!!! ERECTION WEIGHT 발견: 이후 행 무시")
            cut_idx = next(i for i, r in enumerate(all_rows_data) if 'ERECTION WEIGHT' in r['totxt'].upper())
            all_rows_data = all_rows_data[:cut_idx]
        fabrication_found = any('FABRICATION' in r['totxt'].upper() for r in all_rows_data)

    # 6) FABRICATION 컷
    if not erection_weight_found and fabrication_found:
        print(f"\n  - ERECTION WEIGHT 없음 → FABRICATION까지만 처리")
        last_fab_index = -1
        for i, row in enumerate(all_rows_data):
            if 'FABRICATION' in row['totxt'].upper():
                last_fab_index = i
        if last_fab_index >= 0:
            all_rows_data = all_rows_data[:last_fab_index + 1]
            print(f"  - FABRICATION 이후 제거, 남은 행: {len(all_rows_data)}")

    # 7) PT 없는 행 병합 + (추가) PT 비숫자 SKIP
    merged_data = []
    last_pt_data = None
    empty_lines = []

    for row in all_rows_data:
        totxt_upper = row['totxt'].upper()
        if 'FABRICATION' in totxt_upper or 'ERECTION' in totxt_upper:
            print(f"    FABRICATION/ERECTION 행 스킵: {row['totxt'][:50]}...")
            continue

        if row['pt']:  # PT 문자열 존재
            # === 추가: PT가 숫자가 아니면 SKIP ===
            if not is_numeric_text(row['pt']):
                print(f"    [SKIP] 비숫자 PT 행: PT='{row['pt']}' | {row['totxt'][:50]}...")
                continue

            # 이전 PT에 모여있던 빈 행 병합
            if last_pt_data and empty_lines:
                for empty_row in empty_lines:
                    if empty_row['totxt'].strip():
                        tupper = empty_row['totxt'].upper()
                        if 'FABRICATION' not in tupper and 'ERECTION' not in tupper:
                            last_pt_data['comp'] += ' ' + empty_row['totxt'].strip()
                            print(f"    공백 라인 병합: {empty_row['totxt'].strip()}")
                        else:
                            print(f"    공백 FAB/EREC 라인 병합 제외: {empty_row['totxt'].strip()}")

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
                tupper = empty_row['totxt'].upper()
                if 'FABRICATION' not in tupper and 'ERECTION' not in tupper:
                    last_pt_data['comp'] += ' ' + empty_row['totxt'].strip()
                    print(f"    공백 라인 병합: {empty_row['totxt'].strip()}")
                else:
                    print(f"    공백 FAB/EREC 라인 병합 제외: {empty_row['totxt'].strip()}")

    # 8) 최종 전처리 → 레코드화
    all_totxt = []
    for data in merged_data:
        pt_value = data['pt']
        comp_value = data['comp']
        size_value = data['size']
        qty_value = data['qty']
        weight_value = data['weight']
        totxt = data['totxt']

        totxt_upper = totxt.upper()
        comp_upper = comp_value.upper()
        if ('FABRICATION' in totxt_upper or 'ERECTION' in totxt_upper or
            'FABRICATION' in comp_upper or 'ERECTION' in comp_upper):
            print(f"\n  - FAB/EREC 라인 제외: {totxt[:50]}...")
            continue

        item_value = ''
        endtype_value = ''
        mate_value = ''
        sch_value = ''

        if 'SPIRAL' in totxt_upper:
            print(f"    SPIRAL 처리: {comp_value}")
            comp_parts = comp_value.split(',')
            if len(comp_parts) >= 3:
                item_value = comp_parts[0].strip()
                if len(comp_parts) > 1:
                    item_value += ', ' + comp_parts[1].strip()
                if len(comp_parts) > 2:
                    item_value += ', ' + comp_parts[2].strip()
            if len(comp_parts) > 3:
                mate_value = comp_parts[3].strip()
            if len(comp_parts) > 4:
                sch_value = comp_parts[4].strip()
        elif 'BOLT' in comp_upper or 'NUT' in comp_upper:
            print(f"    BOLT/NUT 처리: {comp_value}")
            comp_parts = comp_value.split(',')
            if len(comp_parts) > 0:
                item_value = comp_parts[0].strip()
            if len(comp_parts) > 1:
                second_part = comp_parts[1].strip()
                if '-' in second_part:
                    dash_pos = second_part.find('-')
                    mate_value = second_part[:dash_pos].strip()
                    sch_value = second_part[dash_pos+1:].strip()
                else:
                    mate_value = second_part
                    if len(comp_parts) > 2:
                        sch_value = comp_parts[2].strip()
        else:
            comp_parts = comp_value.split(',')
            if len(comp_parts) > 0:
                item_value = comp_parts[0].strip()
            if len(comp_parts) > 1:
                endtype_value = comp_parts[1].strip()
            if len(comp_parts) > 2:
                mate_value = comp_parts[2].strip()
            if len(comp_parts) > 3:
                sch_value = comp_parts[3].strip()

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
            'REMARK': ''
        }
        all_totxt.append(data_row)

    # 9) 시트 분류
    fabmat_last_index = -1
    for i, row in enumerate(all_rows_data):
        if 'FABRICATION' in row['totxt'].upper():
            fabmat_last_index = i
            print(f"  - FABRICATION 위치 index {i}: {row['totxt'][:50]}...")

    for totxt_data in all_totxt:
        data_copy = totxt_data.copy()
        if 'TOTXT' in data_copy:
            del data_copy['TOTXT']

        # 원본 위치(PT & SIZE)로 FAB/EREC 구분 시도
        orig_index = -1
        for i, row in enumerate(all_rows_data):
            if (row['pt'] == totxt_data['ITEM NO'] and 
                row['size'] == totxt_data['SIZE'] and
                row['pt'] != ''):
                orig_index = i
                break

        is_fabmat = False
        is_erecmat = False
        if fabmat_last_index >= 0 and orig_index >= 0:
            if orig_index <= fabmat_last_index:
                is_fabmat = True
            else:
                is_erecmat = True
        else:
            is_fabmat = True
        
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
    print(f"\n=== Excel 파일 저장 완료 ===")
    print(f"파일명: {excel_filename}")
    print(f"경로: {excel_path}")
    print(f"총 {len(all_data)}개의 데이터 저장됨")
    print(f"\n=== 시트별 데이터 ===")
    print(f"- MTO Data: 전체 데이터 ({len(all_data)}행)")
    print(f"- TOTAL BOM: 그룹화된 BOM (T.WEIGHT 합계: {sum_str})")
    print(f"- FAB MATERIAL: {len(sheet_data['FABMAT'])}행")
    print(f"- EREC MATERIAL: {len(sheet_data['ERECMAT'])}행")
    print(f"- PIPE: {len(sheet_data['PIPE'])}행")
    print(f"- FITTINGS: {len(sheet_data['FITTINGS'])}행")
    print(f"- VALV: {len(sheet_data['VALV'])}행")
    print(f"- BOLT-NUT: {len(sheet_data['BOLT-NUT'])}행")
    print(f"\n=== 주요 변경사항 ===")
    print(f"1) PT가 숫자가 아니면 해당 행 완전 SKIP")
    print(f"2) ISO DWG NO 없거나 '-' → X708,Y42.5(±10mm) 재탐색")
    print(f"3) SH'T NO 없거나 '-' → X799,Y42.5(±10mm) 재탐색")
    print(f"4) REV NO 없거나 '-' → X803,Y20(±10mm) 재탐색(숫자 우선)")
else:
    print("\n추출된 데이터가 없습니다.")
