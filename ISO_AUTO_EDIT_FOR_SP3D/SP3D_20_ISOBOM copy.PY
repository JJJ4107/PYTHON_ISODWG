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
    
    # 1. 일반 TEXT/MTEXT 수집
    for e in msp.query('TEXT MTEXT'):
        txt = get_text(e).strip()
        x, y = get_xy(e)
        if txt:
            all_texts.append((x, y, txt, 'normal'))
    
    # 2. 블록(INSERT) 내부의 텍스트 수집
    for insert in msp.query('INSERT'):
        # 블록의 위치와 스케일
        insert_point = insert.dxf.insert
        x_scale = insert.dxf.xscale if hasattr(insert.dxf, 'xscale') else 1
        y_scale = insert.dxf.yscale if hasattr(insert.dxf, 'yscale') else 1
        rotation = insert.dxf.rotation if hasattr(insert.dxf, 'rotation') else 0
        
        # 블록 정의 가져오기
        block_name = insert.dxf.name
        if block_name in doc.blocks:
            block = doc.blocks[block_name]
            
            # 블록 내부의 TEXT/MTEXT 처리
            for entity in block:
                if entity.dxftype() in ['TEXT', 'MTEXT']:
                    txt = get_text(entity).strip()
                    if txt:
                        # 블록 내부 좌표를 절대 좌표로 변환
                        local_x, local_y = get_xy(entity)
                        
                        # 스케일과 회전 적용 (간단한 변환)
                        import math
                        if rotation != 0:
                            # 회전 변환
                            rad = math.radians(rotation)
                            cos_r = math.cos(rad)
                            sin_r = math.sin(rad)
                            abs_x = insert_point[0] + (local_x * cos_r - local_y * sin_r) * x_scale
                            abs_y = insert_point[1] + (local_x * sin_r + local_y * cos_r) * y_scale
                        else:
                            # 스케일만 적용
                            abs_x = insert_point[0] + local_x * x_scale
                            abs_y = insert_point[1] + local_y * y_scale
                        
                        all_texts.append((abs_x, abs_y, txt, 'block'))
    
    return all_texts

def find_texts_in_area_with_blocks(doc, msp, x_min, x_max, y_min, y_max):
    """블록을 포함하여 특정 영역 내의 모든 텍스트 찾기"""
    texts = []
    all_texts = get_text_from_blocks(doc, msp)
    
    for x, y, txt, source in all_texts:
        if x_min <= x <= x_max and y_min <= y <= y_max:
            texts.append((x, y, txt))
    
    # Y좌표 기준 내림차순 정렬
    texts.sort(key=lambda t: -t[1])
    
    # 텍스트만 추출
    return [t[2] for t in texts]

def find_text_in_rect_with_blocks(doc, msp, x_min, x_max, y_min, y_max, condition=None):
    """블록을 포함하여 사각형 영역에서 조건에 맞는 텍스트 찾기"""
    all_texts = get_text_from_blocks(doc, msp)
    
    for x, y, txt, source in all_texts:
        if x_min <= x <= x_max and y_min <= y <= y_max:
            if condition:
                if condition(txt):
                    return txt
            elif txt:
                return txt
    return None

def extract_number(text):
    """텍스트에서 숫자만 추출"""
    if not text:
        return 0
    
    # 숫자와 소수점만 추출
    numbers = re.findall(r'[\d.]+', str(text))
    if numbers:
        try:
            return float(numbers[0])
        except ValueError:
            return 0
    return 0

def split_text_by_distance(texts_with_pos, threshold=10):
    """텍스트 간 거리가 threshold 이상이면 분리"""
    if not texts_with_pos:
        return []
    
    # X좌표 기준으로 정렬
    texts_with_pos.sort(key=lambda t: t[0])
    
    result = []
    current_group = [texts_with_pos[0][2]]
    last_x = texts_with_pos[0][0]
    
    for i in range(1, len(texts_with_pos)):
        x, y, txt = texts_with_pos[i]
        
        # 이전 텍스트와의 거리가 threshold 이상이면 새 그룹
        if x - last_x >= threshold:
            result.append(' '.join(current_group))
            current_group = [txt]
        else:
            current_group.append(txt)
        
        last_x = x
    
    # 마지막 그룹 추가
    if current_group:
        result.append(' '.join(current_group))
    
    return result

# 파일 선택 (tkinter 사용)
root = tk.Tk()
root.withdraw()
file_paths = filedialog.askopenfilenames(
    title="DXF 도면 선택", filetypes=[("DXF files", "*.dxf")]
)
root.destroy()
if not file_paths:
    print("DXF 파일이 선택되지 않았습니다.")
    exit()

# Excel 파일명 생성
today = datetime.now().strftime("%Y%m%d_%H%M%S")
excel_filename = f"TOTALBOM_{today}.xlsx"
excel_path = os.path.join(os.path.dirname(file_paths[0]), excel_filename)

# 전체 데이터를 저장할 리스트
all_data = []

# 시트별 데이터를 저장할 딕셔너리
sheet_data = {
    'FABMAT': [],
    'ERECMAT': [],
    'PIPE': [],
    'VALV': [],
    'BOLT-NUT': [],
    'FITTINGS': []
}

# 각 DXF 파일 처리
for file_path in file_paths:
    print(f"\n처리 중: {os.path.basename(file_path)}")
    
    try:
        doc = ezdxf.readfile(file_path)
        msp = doc.modelspace()
    except Exception as e:
        print(f"파일 읽기 오류: {e}")
        continue
    
    # 1. LINE NO 찾기 (X 35~115, Y 15~75 mm) - 블록 포함
    lineno_texts = find_texts_in_area_with_blocks(doc, msp, 35, 115, 15, 75)
    
    # LINE NO 처리: 첫번째 값과 동일한 부분 제거
    if lineno_texts:
        processed_linenos = []
        first_lineno = lineno_texts[0] if lineno_texts else ''
        
        for i, text in enumerate(lineno_texts):
            if i == 0:
                processed_linenos.append(text)
            else:
                # 첫번째 LINE NO와 공통 부분 찾기
                common_prefix = ''
                for j in range(min(len(first_lineno), len(text))):
                    if first_lineno[j] == text[j]:
                        common_prefix += first_lineno[j]
                    else:
                        break
                
                # 공통 부분 제거 (하이픈'-' 포함 시 하이픈까지 제거)
                if common_prefix and '-' in common_prefix:
                    # 마지막 하이픈까지 제거
                    last_dash = common_prefix.rfind('-')
                    if last_dash >= 0:
                        common_prefix = common_prefix[:last_dash+1]
                
                # 공통 부분 제거한 텍스트
                remaining_text = text[len(common_prefix):] if len(common_prefix) < len(text) else text
                processed_linenos.append(remaining_text)
        
        lineno = '/'.join(processed_linenos)
    else:
        lineno = '-'
    
    print(f"  - LINENO: {lineno}")
    
    # 2. INSU 찾기 (X 270~310, Y 15~75 mm) - 블록 포함
    insu_texts = find_texts_in_area_with_blocks(doc, msp, 270, 310, 15, 75)
    insu = '/'.join(insu_texts) if insu_texts else '-'
    print(f"  - INSU: {insu}")
    
    # 3. 특정 위치에서 값 찾기 - 블록 포함
    dwgno = find_text_in_rect_with_blocks(doc, msp, 720, 750, 30, 40) or '-'
    isodesc = find_text_in_rect_with_blocks(doc, msp, 650, 750, 40, 50) or '-'
    sheetno = find_text_in_rect_with_blocks(doc, msp, 800, 850, 30, 40, lambda t: 'OF' in t.upper()) or '-'
    revno = find_text_in_rect_with_blocks(doc, msp, 800, 850, 5, 20, lambda t: t.isdigit()) or '-'
    
    print(f"  - DWGNO: {dwgno}")
    print(f"  - ISODESC: {isodesc}")
    print(f"  - SHEETNO: {sheetno}")
    print(f"  - REVNO: {revno}")
    
    # 4. 헤더 찾기: 'PT', 'COMPONENT', 'SIZE', "Q'TY", 'WEIGHT' - 블록 포함
    headers = ['PT', 'COMPONENT', 'SIZE', "Q'TY", 'WEIGHT']
    header_positions = {}
    
    # 모든 텍스트 가져오기 (블록 포함)
    all_texts = get_text_from_blocks(doc, msp)
    
    # COMPONENT 헤더 찾기
    comp_header = None
    comp_x, comp_y = None, None
    
    for x, y, txt, source in all_texts:
        if 'COMPONENT' in txt.upper():
            comp_header = True
            comp_x, comp_y = x, y
            header_positions['COMPONENT'] = comp_x
            print(f"  - COMPONENT 헤더 발견 at ({comp_x:.1f}, {comp_y:.1f}) from {source}")
            break
    
    if not comp_header:
        print("  - COMPONENT 헤더를 찾을 수 없습니다.")
        continue
    
    # 다른 헤더들 찾기 (COMPONENT와 같은 Y 좌표 근처)
    for x, y, txt, source in all_texts:
        txt_upper = txt.upper()
        
        if abs(y - comp_y) <= 5:  # COMPONENT와 비슷한 Y 좌표
            if txt_upper == 'PT' or (txt_upper.startswith('PT') and len(txt_upper) <= 5):
                header_positions['PT'] = x
            elif 'SIZE' in txt_upper:
                header_positions['SIZE'] = x
            elif "Q'TY" in txt_upper or 'QTY' in txt_upper:
                header_positions["Q'TY"] = x
            elif 'WEIGHT' in txt_upper and 'T.WEIGHT' not in txt_upper:
                header_positions['WEIGHT'] = x
    
    print(f"  - 찾은 헤더들: {list(header_positions.keys())}")
    
    # 5. COMPONENT 기준으로 데이터 읽기 - Y좌표 +250mm까지만
    all_rows_data = []  # 모든 행 데이터 저장
    
    # 테이블 영역의 모든 Y 위치 찾기 (모든 열 고려)
    comp_data_y_positions = []
    
    # Y 좌표 제한 설정 (COMPONENT Y - 250mm)
    y_limit = comp_y - 250
    
    print(f"\n  - 테이블 영역 스캔: X {comp_x-20:.1f} ~ {comp_x+180:.1f}")
    print(f"  - Y 좌표 범위: {comp_y:.1f} ~ {y_limit:.1f} (250mm)")
    
    for x, y, txt, source in all_texts:
        # 테이블 영역 내의 모든 텍스트 (헤더 아래, X 범위 내, Y 제한 내)
        if comp_x - 20 <= x <= comp_x + 180 and y < comp_y - 5 and y >= y_limit and txt:
            comp_data_y_positions.append(y)
    
    # 중복 제거 및 정렬
    comp_data_y_positions = sorted(list(set(comp_data_y_positions)), reverse=True)
    
    print(f"  - 발견된 데이터 행 수: {len(comp_data_y_positions)}")
    
    # 모든 행 데이터 읽기
    erection_weight_found = False
    fabrication_found = False
    
    for data_y in comp_data_y_positions:
        # COMPONENT 값의 -X 20 ~ +X 180 범위에서 모든 텍스트 읽기
        row_texts = []
        
        for x, y, txt, source in all_texts:
            # 같은 Y 좌표이고, 지정된 X 범위 내
            if abs(y - data_y) <= 2 and comp_x - 20 <= x <= comp_x + 180 and txt:
                row_texts.append((x, y, txt))
        
        if not row_texts:
            continue
        
        # X좌표 기준으로 정렬
        row_texts.sort(key=lambda t: t[0])
        
        # 전체 텍스트를 하나로 합치기 (TOTXT)
        totxt = ' '.join([t[2] for t in row_texts])
        
        # ERECTION WEIGHT 체크 - 찾으면 즉시 중단
        if 'ERECTION WEIGHT' in totxt.upper():
            print(f"\n!!! ERECTION WEIGHT 발견 in TOTXT: {totxt}")
            erection_weight_found = True
            break  # 즉시 중단
        
        # FABRICATION 체크
        if 'FABRICATION' in totxt.upper():
            fabrication_found = True
        
        # 텍스트 간 거리가 10 이상이면 분리
        separated_values = split_text_by_distance(row_texts, 10)
        
        # PT, COMP, SIZE, QTY, WEIGHT로 분리
        pt_value = ''
        comp_value = ''
        size_value = ''
        qty_value = ''
        weight_value = ''
        
        # 헤더 위치에 따라 값 할당
        if len(separated_values) > 0:
            # 첫 번째 값이 숫자면 PT, 아니면 COMP
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
                # PT가 없는 경우
                comp_value = ' '.join(separated_values[:2]) if len(separated_values) > 1 else separated_values[0]
                if len(separated_values) > 2:
                    size_value = separated_values[2]
                if len(separated_values) > 3:
                    qty_value = separated_values[3]
                if len(separated_values) > 4:
                    weight_value = separated_values[4]
        
        # 행 데이터 저장
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
    
    # ERECTION WEIGHT가 없고 FABRICATION이 있는 경우 처리
    if not erection_weight_found and fabrication_found:
        print(f"\n  - ERECTION WEIGHT 없음, FABRICATION까지만 처리")
        # FABRICATION이 포함된 마지막 행 찾기
        last_fab_index = -1
        for i, row in enumerate(all_rows_data):
            if 'FABRICATION' in row['totxt'].upper():
                last_fab_index = i
        
        if last_fab_index >= 0:
            # FABRICATION 이후 데이터 제거
            all_rows_data = all_rows_data[:last_fab_index + 1]
            print(f"  - FABRICATION 이후 데이터 제거, 남은 행: {len(all_rows_data)}")
    
    # 6. PT 없는 라인을 이전 PT 라인의 COMP에 병합
    merged_data = []
    last_pt_data = None
    empty_lines = []  # PT가 없는 라인들 임시 저장
    
    for row in all_rows_data:
        # FABRICATION/ERECTION이 포함된 행은 처리하지 않음
        totxt_upper = row['totxt'].upper()
        if 'FABRICATION' in totxt_upper or 'ERECTION' in totxt_upper:
            print(f"    FABRICATION/ERECTION 행 건너뛰기: {row['totxt'][:50]}...")
            continue
            
        if row['pt']:  # PT가 있는 경우
            # 이전에 저장된 empty_lines가 있다면 last_pt_data의 comp에 병합
            if last_pt_data and empty_lines:
                for empty_row in empty_lines:
                    # FABRICATION/ERECTION이 포함된 라인은 병합하지 않음
                    if empty_row['totxt'].strip():
                        totxt_upper = empty_row['totxt'].upper()
                        if 'FABRICATION' not in totxt_upper and 'ERECTION' not in totxt_upper:
                            last_pt_data['comp'] += ' ' + empty_row['totxt'].strip()
                            print(f"    공백 라인 병합: {empty_row['totxt'].strip()}")
                        else:
                            print(f"    FABRICATION/ERECTION 라인 병합 제외: {empty_row['totxt'].strip()}")
            
            # 현재 행을 새로운 PT 데이터로 설정
            last_pt_data = row.copy()
            merged_data.append(last_pt_data)
            empty_lines = []  # 빈 라인 리스트 초기화
        else:  # PT가 없는 경우
            empty_lines.append(row)
    
    # 마지막 empty_lines 처리
    if last_pt_data and empty_lines:
        for empty_row in empty_lines:
            # FABRICATION/ERECTION이 포함된 라인은 병합하지 않음
            if empty_row['totxt'].strip():
                totxt_upper = empty_row['totxt'].upper()
                if 'FABRICATION' not in totxt_upper and 'ERECTION' not in totxt_upper:
                    last_pt_data['comp'] += ' ' + empty_row['totxt'].strip()
                    print(f"    공백 라인 병합: {empty_row['totxt'].strip()}")
                else:
                    print(f"    FABRICATION/ERECTION 라인 병합 제외: {empty_row['totxt'].strip()}")
    
    # 7. 병합된 데이터로 최종 처리
    all_totxt = []
    
    for data in merged_data:
        pt_value = data['pt']
        comp_value = data['comp']
        size_value = data['size']
        qty_value = data['qty']
        weight_value = data['weight']
        totxt = data['totxt']
        
        # FABRICATION 또는 ERECTION이 포함된 라인은 제외
        totxt_upper = totxt.upper()
        comp_upper = comp_value.upper()
        
        # TOTXT나 COMP에 FABRICATION/ERECTION이 포함되면 제외
        if ('FABRICATION' in totxt_upper or 'ERECTION' in totxt_upper or
            'FABRICATION' in comp_upper or 'ERECTION' in comp_upper):
            print(f"\n  - FABRICATION/ERECTION 라인 제외: {totxt[:50]}...")
            continue
        
        # COMP 값을 ','로 분리
        item_value = ''
        endtype_value = ''
        mate_value = ''
        sch_value = ''
        
        comp_upper = comp_value.upper()
        totxt_upper = totxt.upper()
        
        # SPIRAL이 TOTXT에 포함된 경우
        if 'SPIRAL' in totxt_upper:
            print(f"    SPIRAL 처리 (TOTXT에 포함): {comp_value}")
            comp_parts = comp_value.split(',')
            if len(comp_parts) >= 3:
                # 1번째 + 2번째 + 3번째 = ITEM
                item_value = comp_parts[0].strip()
                if len(comp_parts) > 1:
                    item_value += ', ' + comp_parts[1].strip()
                if len(comp_parts) > 2:
                    item_value += ', ' + comp_parts[2].strip()
            if len(comp_parts) > 3:
                # 4번째 = MATERIAL
                mate_value = comp_parts[3].strip()
            if len(comp_parts) > 4:
                # 5번째 = SCH/RATING
                sch_value = comp_parts[4].strip()
            print(f"      -> ITEM: {item_value}, MATE: {mate_value}, SCH: {sch_value}")
        
        # BOLT 또는 NUT이 포함된 경우
        elif 'BOLT' in comp_upper or 'NUT' in comp_upper:
            print(f"    BOLT/NUT 처리: {comp_value}")
            comp_parts = comp_value.split(',')
            if len(comp_parts) > 0:
                item_value = comp_parts[0].strip()
            if len(comp_parts) > 1:
                # 2번째에서 '-' 찾기
                second_part = comp_parts[1].strip()
                if '-' in second_part:
                    dash_pos = second_part.find('-')
                    mate_value = second_part[:dash_pos].strip()
                    sch_value = second_part[dash_pos+1:].strip()
                else:
                    mate_value = second_part
                    if len(comp_parts) > 2:
                        sch_value = comp_parts[2].strip()
            print(f"      -> ITEM: {item_value}, MATE: {mate_value}, SCH: {sch_value}")
        
        # 일반적인 경우
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
        
        # WEIGHT × QTY = TWEIGHT 계산 (QTY에서 문자 제거)
        tweight_value = ''
        try:
            weight_float = extract_number(weight_value)
            qty_float = extract_number(qty_value)
            
            if weight_float > 0 and qty_float > 0:
                tweight = weight_float * qty_float
                
                if tweight.is_integer():
                    tweight_value = str(int(tweight))
                else:
                    tweight_value = str(round(tweight, 1))
        except Exception:
            tweight_value = ''
        
        # UNI 값 결정
        uni_value = 'M' if 'PIPE' in item_value.upper() else 'EA'
        
        # 데이터 저장
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
    
    # 8. TOTXT에 따라 시트 분류
    # 원본 all_rows_data에서 FABRICATION 위치 찾기 (제외되기 전 데이터)
    fabmat_last_index = -1
    
    for i, row in enumerate(all_rows_data):
        if 'FABRICATION' in row['totxt'].upper():
            fabmat_last_index = i
            print(f"  - FABRICATION 발견 at original index {i}: {row['totxt'][:50]}...")
    
    # all_totxt의 각 데이터가 원본에서 어디에 위치했는지 찾기
    for totxt_data in all_totxt:
        # TOTXT 제거 (엑셀에는 불필요)
        data_copy = totxt_data.copy()
        if 'TOTXT' in data_copy:
            del data_copy['TOTXT']
        
        # 원본 위치 찾기 (PT와 SIZE로 매칭)
        orig_index = -1
        for i, row in enumerate(all_rows_data):
            if (row['pt'] == totxt_data['ITEM NO'] and 
                row['size'] == totxt_data['SIZE'] and
                row['pt'] != ''):
                orig_index = i
                break
        
        # FABMAT/ERECMAT 분류
        is_fabmat = False
        is_erecmat = False
        
        if fabmat_last_index >= 0 and orig_index >= 0:
            if orig_index <= fabmat_last_index:
                # FABRICATION 위치까지 → FABMAT
                is_fabmat = True
            else:
                # FABRICATION 이후 → ERECMAT
                is_erecmat = True
        else:
            # FABRICATION이 없거나 위치를 못 찾으면 FABMAT
            is_fabmat = True
        
        if is_fabmat:
            sheet_data['FABMAT'].append(data_copy)
        if is_erecmat:
            sheet_data['ERECMAT'].append(data_copy)
        
        # ITEM 내용에 따라 추가 분류
        item_upper = data_copy.get('ITEM', '').upper()
        
        # PIPE
        if 'PIPE' in item_upper:
            sheet_data['PIPE'].append(data_copy)
        
        # VALV
        valv_keywords = ['VALV', 'V/V', 'NRV', 'MOV', 'PCV']
        if any(keyword in item_upper for keyword in valv_keywords):
            sheet_data['VALV'].append(data_copy)
        
        # BOLT/NUT
        bolt_keywords = ['BOLT', 'NUT', 'GASKET', 'GRAPHITE', 'WOUND', 'RING']
        if any(keyword in item_upper for keyword in bolt_keywords):
            sheet_data['BOLT-NUT'].append(data_copy)
        
        # FITTINGS (나머지)
        is_fitting = True
        if 'PIPE' in item_upper:
            is_fitting = False
        elif any(keyword in item_upper for keyword in valv_keywords):
            is_fitting = False
        elif any(keyword in item_upper for keyword in bolt_keywords):
            is_fitting = False
        
        if is_fitting and item_upper:  # ITEM이 비어있지 않은 경우만
            sheet_data['FITTINGS'].append(data_copy)
        
        # 전체 데이터에 추가
        all_data.append(data_copy)

# 9. Excel 파일 저장
if all_data:
    wb = Workbook()
    
    # 헤더 정의
    headers = ['ISO DWG NO', 'LINE NO', 'ISO DESC.', 'SH\'T NO', 'REV. NO', 'ITEM NO', 
               'ITEM', 'END TYPE', 'MATERIAL', 'SCH/RATING', 'SIZE', "Q'TY", 
               '(M/EA)', 'U.WEIGHT', 'T.WEIGHT', 'INSU. THK', 'REMARK']
    
    # 헤더 스타일 (크기 12, 굵게, 중앙 정렬, 굵은 테두리)
    header_font = Font(size=12, bold=True)
    header_alignment = Alignment(horizontal='center', vertical='center')
    header_border = Border(
        left=Side(style='thick'),
        right=Side(style='thick'),
        top=Side(style='thick'),
        bottom=Side(style='thick')
    )
    
    # 데이터 스타일 (크기 11, 중앙 정렬, 일반 테두리)
    data_font = Font(size=11)
    data_alignment = Alignment(horizontal='center', vertical='center')
    data_border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )
    
    # 첫 번째 시트: 전체 데이터 (MTO Data)
    ws = wb.active
    ws.title = "MTO Data"
    
    # 헤더 작성
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.alignment = header_alignment
        cell.border = header_border
    
    # 데이터 작성
    for row_idx, data in enumerate(all_data, 2):
        for col_idx, header in enumerate(headers, 1):
            value = data.get(header, '')
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.font = data_font
            cell.alignment = data_alignment
            cell.border = data_border
    
    # 컬럼 너비 자동 조정
    for column in ws.columns:
        max_length = 0
        column_letter = get_column_letter(column[0].column)
        
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        
        adjusted_width = (max_length + 2) * 1.2
        ws.column_dimensions[column_letter].width = adjusted_width
    
    # TOTAL BOM 시트 생성
    ws_total = wb.create_sheet(title="TOTAL BOM")
    
    # TOTAL BOM 데이터 그룹화
    total_bom_data = defaultdict(lambda: {'Q\'TY': 0, 'U.WEIGHT': '', '(M/EA)': ''})
    
    for row in all_data:
        # 그룹화 키: ITEM + END TYPE + MATERIAL + SCH/RATING + SIZE
        key = (
            row.get('ITEM', ''),
            row.get('END TYPE', ''),
            row.get('MATERIAL', ''),
            row.get('SCH/RATING', ''),
            row.get('SIZE', '')
        )
        
        # 수량 합산
        qty = extract_number(row.get('Q\'TY', ''))
        total_bom_data[key]['Q\'TY'] += qty
        total_bom_data[key]['U.WEIGHT'] = row.get('U.WEIGHT', '')
        total_bom_data[key]['(M/EA)'] = row.get('(M/EA)', '')
    
    # TOTAL BOM 헤더
    total_headers = ['ITEM', 'END TYPE', 'MATERIAL', 'SCH/RATING', 'SIZE', 
                     "Q'TY", '(M/EA)', 'T.WEIGHT']
    
    # 헤더 작성
    for col, header in enumerate(total_headers, 1):
        cell = ws_total.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.alignment = header_alignment
        cell.border = header_border
    
    # 데이터 작성 및 T.WEIGHT 합계 계산
    total_weight_sum = 0
    row_idx = 2
    
    for (item, endtype, material, sch, size), data in total_bom_data.items():
        # T.WEIGHT 계산
        weight = extract_number(data['U.WEIGHT'])
        qty = data['Q\'TY']
        tweight = weight * qty if weight > 0 and qty > 0 else 0
        
        if tweight > 0:
            total_weight_sum += tweight
            if tweight.is_integer():
                tweight_str = str(int(tweight))
            else:
                tweight_str = str(round(tweight, 1))
        else:
            tweight_str = ''
        
        # 수량 문자열
        if data['Q\'TY'] > 0:
            if float(data['Q\'TY']).is_integer():
                qty_str = str(int(data['Q\'TY']))
            else:
                qty_str = str(round(data['Q\'TY'], 1))
        else:
            qty_str = ''
        
        # 행 데이터
        row_data = [item, endtype, material, sch, size, qty_str, data['(M/EA)'], tweight_str]
        
        for col_idx, value in enumerate(row_data, 1):
            cell = ws_total.cell(row=row_idx, column=col_idx, value=value)
            cell.font = data_font
            cell.alignment = data_alignment
            cell.border = data_border
        
        row_idx += 1
    
    # T.WEIGHT 합계 행 추가
    sum_row = row_idx
    
    # "TOTAL" 텍스트
    cell = ws_total.cell(row=sum_row, column=1, value='TOTAL')
    cell.font = Font(size=12, bold=True)
    cell.alignment = header_alignment
    cell.border = header_border
    
    # 빈 셀들
    for col in range(2, 8):
        cell = ws_total.cell(row=sum_row, column=col, value='')
        cell.border = header_border
    
    # T.WEIGHT 합계
    if total_weight_sum > 0:
        if total_weight_sum.is_integer():
            sum_str = str(int(total_weight_sum))
        else:
            sum_str = str(round(total_weight_sum, 1))
    else:
        sum_str = '0'
    
    cell = ws_total.cell(row=sum_row, column=8, value=sum_str)
    cell.font = Font(size=12, bold=True)
    cell.alignment = header_alignment
    cell.border = header_border
    
    # 컬럼 너비 자동 조정
    for column in ws_total.columns:
        max_length = 0
        column_letter = get_column_letter(column[0].column)
        
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        
        adjusted_width = (max_length + 2) * 1.2
        ws_total.column_dimensions[column_letter].width = adjusted_width
    
    # 나머지 시트들 생성
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
        
        # EREC MATERIAL은 데이터가 없어도 항상 생성
        if sheet_data[data_key] or sheet_name == 'EREC MATERIAL':
            ws_sheet = wb.create_sheet(title=sheet_name)
            
            # 헤더 작성
            for col, header in enumerate(headers, 1):
                cell = ws_sheet.cell(row=1, column=col, value=header)
                cell.font = header_font
                cell.alignment = header_alignment
                cell.border = header_border
            
            # 데이터 작성 (데이터가 있는 경우만)
            if sheet_data[data_key]:
                for row_idx, data in enumerate(sheet_data[data_key], 2):
                    for col_idx, header in enumerate(headers, 1):
                        value = data.get(header, '')
                        cell = ws_sheet.cell(row=row_idx, column=col_idx, value=value)
                        cell.font = data_font
                        cell.alignment = data_alignment
                        cell.border = data_border
            
            # 컬럼 너비 자동 조정
            for column in ws_sheet.columns:
                max_length = 0
                column_letter = get_column_letter(column[0].column)
                
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                
                adjusted_width = (max_length + 2) * 1.2
                ws_sheet.column_dimensions[column_letter].width = adjusted_width
    
    # 파일 저장
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
    print(f"1. LINENO 처리: 첫번째 값과 동일한 부분 제거 후 '/'로 구분")
    print(f"2. TOTXT 읽기: COMPONENT Y좌표에서 +250mm까지만 읽기")
    print(f"3. ERECTION WEIGHT가 없으면 FABRICATION까지만 처리")
    print(f"4. FABRICATION/ERECTION이 포함된 라인은 데이터에서 제외")
    print(f"5. PT 없는 라인: 전체 TOTXT를 이전 PT 라인의 COMP에 병합")
    print(f"6. FABMAT/ERECMAT 구분: FABRICATION 텍스트 위치 기준")
    print(f"   - FABRICATION 위치까지: FABMAT")
    print(f"   - FABRICATION 이후: ERECMAT")
    print(f"7. 시트 분류:")
    print(f"   - PIPE: ITEM에 'PIPE' 포함")
    print(f"   - VALV: VALV, V/V, NRV, MOV, PCV 포함")
    print(f"   - BOLT-NUT: BOLT, NUT, GASKET, GRAPHITE, WOUND, RING 포함")
    print(f"   - FITTINGS: 나머지 모든 객체")
else:
    print("\n추출된 데이터가 없습니다.")