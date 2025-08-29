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

# 프로그램 설명
print("=== DXF BOM 추출 프로그램 v2.1 ===")
print("- BLOCK과 일반 텍스트를 모두 읽어 정확한 ISODWGNO 추출")
print("- Y값 그룹화로 같은 줄의 모든 텍스트 조합")
print("- 확장된 X 범위 검색 (700-950)")
print("- X: 770-780, Y: 5-20 범위의 추가 텍스트를 ISODWGNO에 연결")
print("")

# ANSI 규격 파이프 두께 (mm) - Rating별
ANSI_THICKNESS = {
    '#150': {'default': 3.2},
    '#300': {'default': 6.4},
    '#600': {'default': 9.5},
    '#900': {'default': 12.7},
    '#1500': {'default': 19.0},
    '#2500': {'default': 25.4},
    '#3000': {'default': 25.4},
    '#6000': {'default': 38.1}
}

# ANSI 피팅 종류 (계산 대상)
ANSI_FITTINGS = [
    'ELBO', 'ELBOW', 'FLANGE', 'FLNG', 'OLET', 'WELDOLET', 'SOCKOLET', 'THREADOLET',
    'REDU', 'REDUCER', 'TEE', 'CAP', 'COUPLING', 'UNION', 'NIPPLE', 'STUB'
]

def get_xy(e): 
    """엔티티의 X, Y 좌표 반환"""
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
    """엔티티에서 텍스트 추출"""
    try:
        if hasattr(e, 'dxf') and hasattr(e.dxf, 'text'):
            return e.dxf.text
        elif hasattr(e, 'text'):
            return e.text
    except Exception:
        pass
    return ''

def get_all_texts_including_blocks(msp, doc):
    """블록 내부의 텍스트를 포함한 모든 텍스트 요소 반환 (개선된 버전)"""
    all_texts = []
    
    # 1. 모델 스페이스의 직접적인 텍스트 (TEXT, MTEXT)
    for e in msp.query('TEXT MTEXT'):
        txt = get_text(e).strip()
        x, y = get_xy(e)
        if txt:
            all_texts.append((x, y, txt, e, 'NORMAL'))  # 타입 추가
    
    # 2. INSERT(블록 참조)를 통한 텍스트
    for insert in msp.query('INSERT'):
        try:
            block_name = insert.dxf.name
            block = doc.blocks.get(block_name)
            if block:
                # 블록의 삽입점과 스케일, 회전 정보
                insert_x, insert_y = get_xy(insert)
                
                # 스케일 팩터 가져오기
                x_scale = getattr(insert.dxf, 'xscale', 1.0)
                y_scale = getattr(insert.dxf, 'yscale', 1.0)
                rotation = getattr(insert.dxf, 'rotation', 0.0)
                
                # 블록 내부의 텍스트 요소들
                for e in block.query('TEXT MTEXT'):
                    txt = get_text(e).strip()
                    if txt:
                        # 블록 내부 좌표를 실제 좌표로 변환
                        block_x, block_y = get_xy(e)
                        
                        # 스케일 적용
                        scaled_x = block_x * x_scale
                        scaled_y = block_y * y_scale
                        
                        # 회전 적용 (라디안으로 변환)
                        if rotation != 0:
                            import math
                            rad = math.radians(rotation)
                            cos_r = math.cos(rad)
                            sin_r = math.sin(rad)
                            
                            # 회전 변환
                            rotated_x = scaled_x * cos_r - scaled_y * sin_r
                            rotated_y = scaled_x * sin_r + scaled_y * cos_r
                            
                            actual_x = insert_x + rotated_x
                            actual_y = insert_y + rotated_y
                        else:
                            actual_x = insert_x + scaled_x
                            actual_y = insert_y + scaled_y
                        
                        all_texts.append((actual_x, actual_y, txt, e, 'BLOCK'))  # 타입 추가
                
                # 블록 내부의 속성(ATTRIB) 텍스트도 확인
                if hasattr(insert, 'attribs'):
                    for attrib in insert.attribs:
                        txt = attrib.dxf.text.strip() if hasattr(attrib.dxf, 'text') else ''
                        if txt:
                            x, y = get_xy(attrib)
                            all_texts.append((x, y, txt, attrib, 'ATTRIB'))
        except Exception as e:
            print(f"  블록 처리 오류: {e}")
            continue
    
    # 3. ATTDEF (속성 정의) 확인
    for e in msp.query('ATTDEF'):
        txt = e.dxf.default_value.strip() if hasattr(e.dxf, 'default_value') else ''
        if txt:
            x, y = get_xy(e)
            all_texts.append((x, y, txt, e, 'ATTDEF'))
    
    return all_texts

def clean_str(s):
    return ''.join(s.split())

def extract_size(size_str):
    """SIZE 문자열에서 직경 추출 (mm 단위로 반환)"""
    if not size_str:
        return 0
    
    # 분수 처리 (예: 1/2, 3/4) - 인치로 가정
    if '/' in size_str:
        parts = size_str.split('/')
        if len(parts) == 2:
            try:
                inch_value = float(parts[0]) / float(parts[1])
                return inch_value * 25.4  # 인치를 mm로 변환
            except:
                pass
    
    # 일반 숫자 추출
    match = re.search(r'(\d+(?:\.\d+)?)', size_str)
    if match:
        value = float(match.group(1))
        # 50 이하는 인치로 가정, 50 초과는 mm로 가정
        if value <= 50:
            return value * 25.4  # 인치를 mm로 변환
        else:
            return value  # 이미 mm 단위
    
    return 0

def extract_thickness(description):
    """DESCRIPTION에서 두께 추출"""
    # AWT.48 형태에서 두께 추출
    awt_match = re.search(r'AWT\.(\d+(?:\.\d+)?)', description)
    if awt_match:
        return float(awt_match.group(1))
    
    # WT48 형태에서 두께 추출
    wt_match = re.search(r'WT(\d+(?:\.\d+)?)', description)
    if wt_match:
        return float(wt_match.group(1))
    
    # #3000, #6000 등의 Rating에서 두께 추출
    rating_match = re.search(r'#(\d+)', description)
    if rating_match:
        rating = f"#{rating_match.group(1)}"
        if rating in ANSI_THICKNESS:
            return ANSI_THICKNESS[rating]['default']
    
    # SCH40, SCH80 등에서 표준 두께 사용
    if 'SCH40' in description.upper():
        return 6.0  # 표준 두께
    elif 'SCH80' in description.upper():
        return 9.0  # 표준 두께
    elif 'SCH160' in description.upper():
        return 15.0  # 표준 두께
    
    # BW (Butt Weld) 표준 두께
    if 'BW' in description.upper():
        return 7.0  # BW 표준 두께
    
    return 5.0  # 기본 두께 5mm

def calculate_paint_area(item, size, description, qty, mmea):
    """내면적과 외면적 계산"""
    try:
        # 수량을 float로 변환
        quantity = float(qty) if qty else 0
        if quantity == 0:
            return 0, 0
        
        # SIZE에서 직경 추출 (mm 단위로 반환됨)
        outer_diameter = extract_size(size)
        if outer_diameter == 0:
            return 0, 0
        
        # 두께 추출
        thickness = extract_thickness(description)
        inner_diameter = outer_diameter - (2 * thickness)
        
        # 내경이 0 이하인 경우 처리
        if inner_diameter <= 0:
            inner_diameter = 0
        
        item_upper = item.upper()
        desc_upper = description.upper()
        
        # PIPE인 경우
        if 'PIPE' in item_upper:
            # 길이는 수량 (mm 단위)
            length = quantity  # PIPE는 항상 MM 단위
            
            # 내면적 = π × 내경 × 길이 (m²로 변환)
            inner_area = math.pi * inner_diameter * length / 1000000
            # 외면적 = π × 외경 × 길이 (m²로 변환)
            outer_area = math.pi * outer_diameter * length / 1000000
            
            return round(inner_area, 2), round(outer_area, 2)
        
        # ANSI FITTING인지 확인
        is_ansi_fitting = False
        for fitting in ANSI_FITTINGS:
            if fitting in item_upper or fitting in desc_upper:
                is_ansi_fitting = True
                break
        
        # ANSI FITTING이 아니면 계산하지 않음
        if not is_ansi_fitting:
            return 0, 0
        
        # ELBO/ELBOW 특별 처리
        if 'ELBO' in item_upper or 'ELBOW' in item_upper or 'ELBO' in desc_upper or 'ELBOW' in desc_upper:
            # 각도 확인 (기본값 90도)
            angle = 90
            if '45' in desc_upper:
                angle = 45
            elif '30' in desc_upper:
                angle = 30
            elif '60' in desc_upper:
                angle = 60
            
            # 곡률반경 R = 1.5 × 직경
            bend_radius = outer_diameter * 1.5
            
            # 토러스(도넛) 표면적 계산
            # 외면적 = (angle/360) × 2π² × R × r
            # R: 곡률반경, r: 파이프 반경
            angle_ratio = angle / 360
            outer_surface = angle_ratio * 2 * math.pi * math.pi * bend_radius * (outer_diameter / 2)
            inner_surface = angle_ratio * 2 * math.pi * math.pi * bend_radius * (inner_diameter / 2)
            
            # m²로 변환 후 수량 곱하기
            outer_area = outer_surface * quantity / 1000000
            inner_area = inner_surface * quantity / 1000000
            
            return round(inner_area, 2), round(outer_area, 2)
        
        # FLANGE 처리
        elif 'FLANGE' in item_upper or 'FLNG' in item_upper or 'FLANGE' in desc_upper or 'FLNG' in desc_upper:
            # 플랜지는 원판 형태 (두께 20mm 가정)
            flange_thickness = 20
            # 외경은 파이프 외경의 2배 정도
            flange_outer_dia = outer_diameter * 2
            
            # 원판 양면 + 원주면
            outer_area = (2 * math.pi * (flange_outer_dia/2)**2 + math.pi * flange_outer_dia * flange_thickness) * quantity / 1000000
            # 내면적은 구멍 부분
            inner_area = math.pi * inner_diameter * flange_thickness * quantity / 1000000
            
            return round(inner_area, 2), round(outer_area, 2)
        
        # TEE 처리
        elif 'TEE' in item_upper or 'TEE' in desc_upper:
            # TEE는 파이프 3개 연결 (본관 2D + 분기관 1D)
            pipe_length = outer_diameter * 3
            
            outer_area = math.pi * outer_diameter * pipe_length * quantity / 1000000
            inner_area = math.pi * inner_diameter * pipe_length * quantity / 1000000
            
            return round(inner_area, 2), round(outer_area, 2)
        
        # REDUCER 처리
        elif 'REDU' in item_upper or 'REDUCER' in item_upper or 'REDU' in desc_upper or 'REDUCER' in desc_upper:
            # 리듀서는 원뿔대 형태 (길이는 큰 직경의 2배)
            reducer_length = outer_diameter * 2
            
            # 간단히 평균 직경으로 계산
            outer_area = math.pi * outer_diameter * reducer_length * quantity / 1000000
            inner_area = math.pi * inner_diameter * reducer_length * quantity / 1000000
            
            return round(inner_area, 2), round(outer_area, 2)
        
        # CAP 처리
        elif 'CAP' in item_upper or 'CAP' in desc_upper:
            # 캡은 반구 + 원판
            outer_area = (2 * math.pi * (outer_diameter/2)**2) * quantity / 1000000
            # 내면적은 반구만
            inner_area = (2 * math.pi * (inner_diameter/2)**2) * quantity / 1000000
            
            return round(inner_area, 2), round(outer_area, 2)
        
        # OLET 류 처리
        elif 'OLET' in item_upper or 'OLET' in desc_upper:
            # OLET은 작은 원통형 (높이는 직경과 동일)
            olet_height = outer_diameter
            
            outer_area = (math.pi * outer_diameter * olet_height + math.pi * (outer_diameter/2)**2) * quantity / 1000000
            inner_area = math.pi * inner_diameter * olet_height * quantity / 1000000
            
            return round(inner_area, 2), round(outer_area, 2)
        
        # 기타 ANSI FITTING (COUPLING, UNION, NIPPLE 등)
        else:
            # 기본적으로 짧은 파이프로 계산 (길이 = 직경)
            fitting_length = outer_diameter
            
            outer_area = math.pi * outer_diameter * fitting_length * quantity / 1000000
            inner_area = math.pi * inner_diameter * fitting_length * quantity / 1000000
            
            return round(inner_area, 2), round(outer_area, 2)
        
    except Exception as e:
        print(f"면적 계산 오류: {e}")
        return 0, 0

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

# 시트별 데이터를 저장할 딕셔너리 추가 (BOLT/NUT을 BOLT-NUT으로 변경)
sheet_data = {
    'FAB MAT': [],
    'ELEC MAT': [],
    'PIPE': [],
    'BOLT-NUT': [],  # '/' 제거
    'INST': [],
    'FITTING': []
}

# 각 DXF 파일 처리
for file_path in file_paths:
    print(f"\n처리 중: {os.path.basename(file_path)}")
    file_data = []  # 현재 파일의 데이터를 임시 저장
    
    try:
        doc = ezdxf.readfile(file_path)
        msp = doc.modelspace()
    except Exception as e:
        continue
    
    # 1. LINENO 찾기 (블록 포함)
    lineno = None
    all_texts = get_all_texts_including_blocks(msp, doc)
    
    for x, y, txt, e, txt_type in all_texts:
        if 0 <= x <= 150 and 0 <= y <= 85 and '-' in txt and len(txt) >= 10:
            lineno = clean_str(txt)
            break
    
    if not lineno:
        lineno = '-'
    
    # 2. FABRICATION MATERIALS 섹션에서 ISODWGNO 찾기
    isodwgno = None
    iso_description = '-'  # ISO DESCRIPTION 초기값
    fab_mat_e = None
    fab_x, fab_y = None, None
    iso_x, iso_y = None, None  # ISO DWG NO의 위치 저장
    
    for x, y, txt, e, txt_type in all_texts:
        if "FABRICATION MATERIALS" in txt.upper():
            fab_mat_e = e
            fab_x, fab_y = x, y
            break
    
    if fab_mat_e:
        for x, y, txt, e, txt_type in all_texts:
            if fab_x is not None and fab_y is not None:
                if (x > fab_x) and (0 <= y <= 20) and ('-' in txt):
                    isodwgno = txt
                    iso_x, iso_y = x, y  # ISO DWG NO의 위치 저장
                    break
    
    # ISODWGNO가 'unset' 또는 '-'인 경우 대체 위치에서 찾기
    if not isodwgno or isodwgno == '-' or isodwgno.lower() == 'unset':
        # X: 700-900, Y: 5-25 범위의 모든 텍스트 수집 (범위 확대)
        iso_texts = []
        print(f"  - ISODWGNO 대체 위치 검색 중...")
        
        for x, y, txt, e, txt_type in all_texts:
            if 700 <= x <= 900 and 5 <= y <= 25 and txt:  # X 범위를 900까지 확대
                iso_texts.append((x, y, txt, txt_type))
                print(f"    발견: '{txt}' at ({x:.1f}, {y:.1f}) - 타입: {txt_type}")
        
        if iso_texts:
            # Y값으로 그룹화 (같은 줄의 텍스트들끼리 그룹화)
            y_groups = defaultdict(list)
            for x, y, txt, txt_type in iso_texts:
                # Y값을 2단위로 그룹화 (더 정밀하게)
                y_group = round(y / 2) * 2
                y_groups[y_group].append((x, y, txt, txt_type))
            
            # 가장 텍스트가 많은 Y 그룹 찾기
            max_group_y = max(y_groups.keys(), key=lambda k: len(y_groups[k]))
            selected_texts = y_groups[max_group_y]
            
            # X 좌표로 정렬
            selected_texts.sort(key=lambda t: t[0])
            
            print(f"  - 선택된 Y 그룹 ({max_group_y}): {len(selected_texts)}개 텍스트")
            
            # 모든 텍스트를 공백 없이 연결
            isodwgno = ''
            for i, (x, y, txt, txt_type) in enumerate(selected_texts):
                isodwgno += txt
                print(f"    조합 중 [{i+1}]: '{txt}' → 누적: '{isodwgno}'")
            
            # 위치는 첫 번째 텍스트의 위치 사용
            if selected_texts:
                iso_x, iso_y = selected_texts[0][0], selected_texts[0][1]
            
            print(f"  - ISODWGNO 대체 위치에서 발견: '{isodwgno}' (총 {len(selected_texts)}개 텍스트 조합)")
    
    # ISODWGNO가 여전히 없다면 더 넓은 범위에서 재검색
    if not isodwgno or isodwgno == '-' or isodwgno.lower() == 'unset':
        # X: 690-950, Y: 0-30 범위로 확대하여 검색 (X 범위 더 확대)
        iso_texts_wide = []
        print(f"  - ISODWGNO 확장 범위 검색 중...")
        
        for x, y, txt, e, txt_type in all_texts:
            if 690 <= x <= 950 and 0 <= y <= 30 and txt:  # X 범위를 950까지 확대
                # 모든 텍스트를 일단 수집 (필터링 제거)
                iso_texts_wide.append((x, y, txt, txt_type))
                print(f"    확장 검색 발견: '{txt}' at ({x:.1f}, {y:.1f}) - 타입: {txt_type}")
        
        if iso_texts_wide:
            # Y값으로 그룹화 (비슷한 Y값끼리)
            y_groups = defaultdict(list)
            for x, y, txt, txt_type in iso_texts_wide:
                y_group = round(y / 2) * 2  # 2단위로 그룹화 (더 정밀하게)
                y_groups[y_group].append((x, y, txt, txt_type))
            
            # 각 Y 그룹별로 출력
            print(f"  - Y 그룹별 텍스트 개수:")
            for y_val, texts in sorted(y_groups.items()):
                print(f"    Y={y_val}: {len(texts)}개")
            
            # '-'를 포함하거나 'JCP'로 시작하는 텍스트가 있는 Y 그룹 우선 선택
            best_group = None
            for y_val, texts in y_groups.items():
                for x, y, txt, txt_type in texts:
                    if 'JCP' in txt or '-' in txt:
                        best_group = texts
                        print(f"  - 'JCP' 또는 '-' 포함 텍스트가 있는 Y={y_val} 그룹 선택")
                        break
                if best_group:
                    break
            
            # 없으면 가장 많은 텍스트가 있는 그룹 선택
            if not best_group:
                best_group = max(y_groups.values(), key=len)
            
            # X로 정렬
            best_group.sort(key=lambda t: t[0])
            
            # 텍스트 조합 (모든 텍스트를 공백 없이 연결)
            isodwgno = ''
            for i, (x, y, txt, txt_type) in enumerate(best_group):
                isodwgno += txt
                print(f"    확장 조합 중 [{i+1}]: '{txt}' → 누적: '{isodwgno}'")
            
            if best_group:
                iso_x, iso_y = best_group[0][0], best_group[0][1]
                print(f"  - ISODWGNO 확장 검색에서 발견: '{isodwgno}'")
    
    # 2-1단계: X: 770-780, Y: 5-20 범위의 추가 텍스트 읽기
    if isodwgno and isodwgno != '-':
        additional_texts = []
        print(f"\n  - ISODWGNO 추가 텍스트 검색 중 (X: 770-780, Y: 5-20)...")
        
        for x, y, txt, e, txt_type in all_texts:
            if 770 <= x <= 780 and 5 <= y <= 20 and txt:
                additional_texts.append((x, y, txt, txt_type))
                print(f"    추가 텍스트 발견: '{txt}' at ({x:.1f}, {y:.1f}) - 타입: {txt_type}")
        
        if additional_texts:
            # Y값으로 정렬 (위에서 아래로)
            additional_texts.sort(key=lambda t: t[1])
            
            # 추가 텍스트를 ISODWGNO에 연결
            for x, y, txt, txt_type in additional_texts:
                isodwgno += txt
                print(f"    ISODWGNO에 추가: '{txt}' → 결과: '{isodwgno}'")
            
            print(f"  - 추가 텍스트 {len(additional_texts)}개 연결 완료")
    
    if not isodwgno:
        isodwgno = '-'
    else:
        # 최종 ISODWGNO 정리 (불필요한 공백 제거)
        isodwgno = isodwgno.strip()
        print(f"  - 최종 ISODWGNO: '{isodwgno}'")
    
    # 2.1. ISO DESCRIPTION 찾기
    if iso_x is not None and iso_y is not None:
        # 지정된 범위에서 텍스트 찾기
        for x, y, txt, e, txt_type in all_texts:
            # X 좌표: iso_x-50부터 iso_x+50까지, Y 좌표: iso_y+10부터 iso_y+45까지
            if (iso_x - 50 <= x <= iso_x + 50) and (iso_y + 10 <= y <= iso_y + 45) and txt:
                iso_description = txt
                print(f"  - ISO DESCRIPTION 발견: {iso_description} at ({x:.1f}, {y:.1f}) - 타입: {txt_type}")
                break  # 첫 번째 텍스트만 사용
    
    # ISO DESCRIPTION이 'unset' 또는 '-'인 경우 대체 위치에서 찾기
    if iso_description == '-' or iso_description.lower() == 'unset':
        desc_texts = []
        print(f"  - ISO DESCRIPTION 대체 위치 검색 중...")
        
        for x, y, txt, e, txt_type in all_texts:
            if 700 <= x <= 950 and 20 <= y <= 40 and txt:  # X 범위 확대, Y 범위도 조정
                desc_texts.append((x, y, txt, txt_type))
                print(f"    ISO DESC 발견: '{txt}' at ({x:.1f}, {y:.1f}) - 타입: {txt_type}")
        
        if desc_texts:
            # Y값으로 그룹화
            y_groups = defaultdict(list)
            for x, y, txt, txt_type in desc_texts:
                y_group = round(y / 2) * 2  # 2단위로 그룹화
                y_groups[y_group].append((x, y, txt))
            
            # 가장 많은 텍스트가 있는 Y 그룹 선택
            if y_groups:
                best_y = max(y_groups.keys(), key=lambda k: len(y_groups[k]))
                best_group = y_groups[best_y]
                
                # X로 정렬
                best_group.sort(key=lambda t: t[0])
                
                # 모든 텍스트를 공백으로 연결
                iso_description = ' '.join(t[2] for t in best_group)
                print(f"  - ISO DESCRIPTION 대체 위치에서 발견: '{iso_description}' (Y={best_y} 그룹)")
    
    # 2.5. INSU 값 찾기 (X: 185-200, Y: 60-70 영역)
    insu_value = '-'
    
    # 해당 영역의 모든 텍스트 확인
    area_texts = []
    for x, y, txt, e, txt_type in all_texts:
        if 185 <= x <= 200 and 60 <= y <= 70:
            area_texts.append((x, y, txt))
    
    # 숫자 텍스트 찾기
    for x, y, txt in area_texts:
        # 숫자인지 확인 (소수점 포함)
        try:
            float(txt)  # 숫자 변환 시도
            insu_value = txt
            break
        except ValueError:
            # 숫자가 아니면 계속 검색
            continue
    
    # INSU 값이 'unset' 또는 '-'인 경우 대체 위치에서 찾기
    if insu_value == '-' or insu_value.lower() == 'unset':
        for x, y, txt, e, txt_type in all_texts:
            if 260 <= x <= 280 and 30 <= y <= 75:
                try:
                    float(txt)  # 숫자인지 확인
                    insu_value = txt
                    print(f"  - INSU 대체 위치에서 발견: {insu_value} at ({x:.1f}, {y:.1f})")
                    break
                except ValueError:
                    continue
    
    # 3. PT 헤더 찾기 (블록 포함)
    headers = ['PT', 'ITEM', 'MATERIAL', 'SIZE', 'DESCRIPTION', 'QTY', 'UNIT', 'TOTAL', 'REMARK']
    
    # 모든 PT 헤더 찾기
    pt_headers = []
    for x, y, txt, e, txt_type in all_texts:
        txt_upper = txt.upper()
        # PT가 포함되고, 다른 긴 텍스트가 아닌 경우
        if txt_upper == 'PT' or (txt_upper.startswith('PT') and len(txt_upper) <= 5):
            pt_headers.append((x, y, txt_upper))
    
    if not pt_headers:
        continue
    
    # 각 PT 헤더에 대해 처리
    file_processed_pts = {}  # 파일 전체에서 처리된 PT 추적 - 각 파일마다 초기화
    
    for pt_idx, (pt_x, pt_y, pt_txt) in enumerate(pt_headers):
        
        # 현재 PT 헤더 주변의 다른 헤더들 찾기
        header_positions = {'PT': pt_x}
        
        # PT와 같은 Y 좌표 근처(±5)에서 다른 헤더 찾기
        for x, y, txt, e, txt_type in all_texts:
            txt_upper = txt.upper()
            
            # PT와 비슷한 Y 좌표에 있는 헤더들 찾기
            if abs(y - pt_y) <= 5:
                for header in headers:
                    if header != 'PT':
                        # 헤더 텍스트 정확히 매칭 또는 포함 확인
                        if (header == txt_upper) or (header in txt_upper and len(txt_upper) <= len(header) + 10):
                            header_positions[header] = x
                            break
        
        # DESCRIPTION 헤더 특별 처리 (다양한 변형 확인)
        if 'DESCRIPTION' not in header_positions:
            for x, y, txt, e, txt_type in all_texts:
                txt_upper = txt.upper()
                if abs(y - pt_y) <= 5:
                    if 'DESC' in txt_upper or 'DESCRIPT' in txt_upper:
                        header_positions['DESCRIPTION'] = x
                        break
        
        # 4. PT 아래의 데이터 추출
        data_rows = []
        
        # Y좌표로 정렬 (블록 텍스트 포함)
        all_texts_sorted = sorted(all_texts, key=lambda t: -t[1])  # Y좌표 내림차순 정렬
        
        # PT 숫자 찾기
        current_row = None
        last_pt_y = None
        pt_count = 0
        processed_pts = {}  # PT 번호별로 처리 여부 추적 {pt_number: row_data}
        
        for x, y, txt, e, txt_type in all_texts_sorted:
            # PT 헤더 아래에서만 검색
            if y >= pt_y:
                continue
            
            # PT 열 위치 확인
            is_pt_column = abs(x - pt_x) <= 2
            
            # PT 열에서 숫자 찾기
            if is_pt_column and txt.isdigit():
                # 파일 전체에서 이미 처리된 PT인지 확인 (PT 번호만으로 체크)
                if txt in file_processed_pts:
                    print(f"    → PT {txt} 중복 발견, 건너뛰기")
                    continue
                
                print(f"  - PT {txt} 발견 at Y={y:.1f}")
                
                # 현재 테이블에서 중복 PT 처리
                if txt in processed_pts:
                    print(f"    → PT {txt} 중복 발견, 건너뛰기")
                    # 중복 PT가 발견되면 완전히 건너뛰기
                    continue
                
                # 이전 행 저장 (중복 체크)
                if current_row and current_row.get('ITEM NO') not in processed_pts:
                    processed_pts[current_row.get('ITEM NO')] = current_row
                    data_rows.append(current_row)
                
                pt_count += 1
                
                # 새로운 행 시작
                current_row = {'ITEM NO': txt, '_y_pos': y, '_pt_header_index': pt_idx}  # PT 헤더 인덱스 추가
                last_pt_y = y
                
                # 첫 번째 줄 데이터 수집
                for hdr, hdr_x in header_positions.items():
                    if hdr != 'PT':
                        for x2, y2, txt2, e2, txt_type2 in all_texts_sorted:
                            if abs(x2 - hdr_x) <= 2 and abs(y2 - y) <= 2:
                                if txt2:  # 빈 텍스트가 아닌 경우만
                                    current_row[hdr] = txt2
                                break
                
                # 다음 줄 데이터 확인 (PT 열이 비어있는 경우에만)
                # 현재 PT 아래 2-6mm 범위에서 확인
                for next_y in range(int(y-6), int(y-2)):
                    next_y_float = float(next_y)
                    
                    # 먼저 이 Y 위치의 PT 열 확인
                    has_pt_at_next = False
                    for x2, y2, txt2, e2, txt_type2 in all_texts_sorted:
                        if abs(x2 - pt_x) <= 2 and abs(y2 - next_y_float) <= 1:
                            if txt2 and txt2.strip():  # 공백이 아닌 텍스트가 있으면
                                if txt2.isdigit():  # PT 번호가 있으면
                                    has_pt_at_next = True
                                    break
                    
                    # PT 열에 숫자가 있으면 다음 PT이므로 중단
                    if has_pt_at_next:
                        break
                    
                    # PT 열이 비어있으면 다른 열의 데이터 확인
                    next_line_data = {}
                    has_data_at_next = False
                    
                    for hdr, hdr_x in header_positions.items():
                        if hdr != 'PT':
                            for x2, y2, txt2, e2, txt_type2 in all_texts_sorted:
                                if abs(x2 - hdr_x) <= 2 and abs(y2 - next_y_float) <= 1 and txt2:
                                    next_line_data[hdr] = txt2
                                    has_data_at_next = True
                                    break
                    
                    # 데이터가 있으면 현재 행에 병합
                    if has_data_at_next:
                        for hdr, txt2 in next_line_data.items():
                            if current_row.get(hdr):
                                # 숫자 필드는 대체, 텍스트 필드는 공백 포함 연결
                                if hdr in ['UNIT', 'TOTAL', 'QTY']:
                                    current_row[hdr] = txt2  # 숫자는 대체
                                else:
                                    # 텍스트는 공백으로 연결
                                    current_row[hdr] = current_row[hdr] + ' ' + txt2
                            else:
                                current_row[hdr] = txt2
                        break  # 한 줄만 병합
            
            # PT 열이 비어있는 경우 - 추가 데이터 수집
            elif is_pt_column and current_row and abs(y - current_row['_y_pos']) < 10:
                # 현재 행의 PT 위치에서 10mm 이내인 경우만 처리
                # 다른 열에 데이터가 있는지 확인
                for hdr, hdr_x in header_positions.items():
                    if hdr != 'PT':
                        for x2, y2, txt2, e2, txt_type2 in all_texts_sorted:
                            if abs(x2 - hdr_x) <= 2 and abs(y2 - y) <= 2 and txt2:
                                if current_row.get(hdr):
                                    # 숫자 필드는 대체, 텍스트 필드는 공백 포함 연결
                                    if hdr in ['UNIT', 'TOTAL', 'QTY']:
                                        current_row[hdr] = txt2
                                    else:
                                        current_row[hdr] = current_row[hdr] + ' ' + txt2
                                else:
                                    current_row[hdr] = txt2
                                break
            
            # 다른 PT 헤더 영역 도달 시 중단
            if y < pt_y - 100:  # PT 헤더에서 100mm 이상 떨어지면 중단
                break
            for other_idx, (other_pt_x, other_pt_y, _) in enumerate(pt_headers):
                if other_idx != pt_idx and other_pt_y < pt_y and abs(y - other_pt_y) <= 5:
                    break
        
        # 마지막 행 추가 (중복 체크)
        if current_row and current_row.get('ITEM NO') not in processed_pts:
            processed_pts[current_row.get('ITEM NO')] = current_row
            data_rows.append(current_row)
        
        # data_rows를 processed_pts 기준으로 재구성 (중복 제거)
        unique_data_rows = []
        seen_pts = set()
        for row in data_rows:
            pt_no = row.get('ITEM NO')
            if pt_no and pt_no not in seen_pts:
                seen_pts.add(pt_no)
                unique_data_rows.append(row)
        data_rows = unique_data_rows
        
        print(f"  - 테이블 {pt_idx+1}: 처리된 PT 개수 = {len(processed_pts)}, 고유 데이터 행 수 = {len(data_rows)}")
        
        # 5. UNIT 결정 및 Excel 데이터 생성
        table_data_count = 0
        
        for row in data_rows:
            # 같은 파일 내에서 이미 처리된 PT는 건너뛰기
            if row.get('ITEM NO') in file_processed_pts:
                print(f"    > PT {row.get('ITEM NO')}는 이미 처리됨 (건너뛰기)")
                continue
            
            # PT 헤더 인덱스 보존
            pt_header_index = row.get('_pt_header_index', -1)
            
            # _y_pos 제거 (내부 사용 필드)
            if '_y_pos' in row:
                del row['_y_pos']
                
            item = row.get('ITEM', '')
            mmea = 'MM' if 'PIPE' in item.upper() else 'EA'
            
            # UNIT와 TOTAL 값 반올림 처리
            unit_value = row.get('UNIT', '')
            total_value = row.get('TOTAL', '')
            
            # UNIT 반올림
            try:
                unit_float = float(unit_value)
                # 정수인지 확인
                if unit_float.is_integer():
                    unit_value = str(int(unit_float))
                else:
                    unit_value = str(round(unit_float, 1))
            except (ValueError, TypeError):
                unit_value = unit_value  # 숫자가 아니면 그대로 사용
            
            # TOTAL 반올림
            try:
                total_float = float(total_value)
                # 정수인지 확인
                if total_float.is_integer():
                    total_value = str(int(total_float))
                else:
                    total_value = str(round(total_float, 1))
            except (ValueError, TypeError):
                total_value = total_value  # 숫자가 아니면 그대로 사용
            
            # PAINT 면적 계산
            inner_area, outer_area = calculate_paint_area(
                item, 
                row.get('SIZE', ''), 
                row.get('DESCRIPTION', ''), 
                row.get('QTY', ''),
                mmea
            )
            
            csv_row = {
                'ISO DWG NO': isodwgno,
                'LINE NO': lineno,
                'ISO DESCRIPTION': iso_description,  # LINE NO 뒤로 이동
                'ITEM NO': row.get('ITEM NO', ''),  # PT를 ITEM NO로
                'ITEM': item,
                'SIZE': row.get('SIZE', ''),
                'MATERIAL': row.get('MATERIAL', ''),
                'DESCRIPTION': row.get('DESCRIPTION', ''),
                'Q\'TY': row.get('QTY', ''),
                '(mm/ea)': mmea,
                'U.WT': unit_value,  # 반올림된 UNIT 값
                'T.WT': total_value,  # 반올림된 TOTAL 값
                'INSU. T\'HK': insu_value,  # INSU 값 추가
                'PAINT 내면적(m²)': str(inner_area) if inner_area > 0 else '-',
                'PAINT 외면적(m²)': str(outer_area) if outer_area > 0 else '-',
                'REMARK': row.get('REMARK', ''),
                '_pt_header_index': pt_header_index  # PT 헤더 인덱스 추가
            }
            
            # 모든 'unset' 값을 '-'로 변경
            for key, value in csv_row.items():
                if isinstance(value, str) and value.lower() == 'unset':
                    csv_row[key] = '-'
            
            file_data.append(csv_row)  # 파일별 임시 리스트에 저장
            table_data_count += 1
            
            # 파일 전체 PT 추적에 추가 (PT 번호만으로 추적)
            file_processed_pts[row.get('ITEM NO')] = True
            
            # 디버깅: 생성된 행 확인
            desc_preview = csv_row['DESCRIPTION'][:30] + '...' if len(csv_row['DESCRIPTION']) > 30 else csv_row['DESCRIPTION']
            print(f"    > Excel 행 생성: PT={csv_row['ITEM NO']}, DESC={desc_preview}, T.WT={csv_row['T.WT']}")
        
        print(f"  - 테이블 {pt_idx+1}에서 추출된 행 수: {table_data_count}")
    
    # 현재 파일의 데이터를 PT 번호로 정렬
    if file_data:
        # PT를 숫자로 변환하여 정렬 (빈 값은 맨 뒤로)
        def sort_key(row):
            try:
                return int(row['ITEM NO'])
            except (ValueError, KeyError):
                return 9999  # ITEM NO가 없거나 숫자가 아닌 경우 맨 뒤로
        
        # 중복 제거
        unique_file_data = {}
        duplicate_count = 0
        for row in file_data:
            item_no = row.get('ITEM NO')
            if item_no:
                if item_no not in unique_file_data:
                    unique_file_data[item_no] = row
                else:
                    duplicate_count += 1
                    print(f"  - 중복 PT {item_no} 제거됨")
        
        if duplicate_count > 0:
            print(f"  - 총 {duplicate_count}개의 중복 데이터 제거됨")
        
        file_data_sorted = sorted(unique_file_data.values(), key=sort_key)
        
        # 정렬된 데이터를 전체 리스트에 추가
        all_data.extend(file_data_sorted)
        
        # 시트별로 데이터 분류
        for row in file_data_sorted:
            pt_header_idx = row.get('_pt_header_index', -1)
            item_upper = row.get('ITEM', '').upper()
            
            # _pt_header_index 제거 (시트별 데이터에는 필요 없음)
            row_copy = row.copy()
            if '_pt_header_index' in row_copy:
                del row_copy['_pt_header_index']
            
            # PT 헤더 인덱스에 따라 분류
            if pt_header_idx == 0:  # 첫 번째 PT 헤더
                sheet_data['FAB MAT'].append(row_copy)
            elif pt_header_idx == 1:  # 두 번째 PT 헤더
                sheet_data['ELEC MAT'].append(row_copy)
            
            # ITEM 내용에 따라 분류
            if 'PIPE' in item_upper and 'SUPPORT' not in item_upper:
                sheet_data['PIPE'].append(row_copy)
            elif 'BOLT' in item_upper or 'NUT' in item_upper or 'GASKET' in item_upper or 'GASK' in item_upper:
                sheet_data['BOLT-NUT'].append(row_copy)  # '/' 제거
            elif 'VALV' in item_upper or 'INST' in item_upper or 'V/V' in item_upper or 'MOV' in item_upper or 'PCV' in item_upper or 'NRV' in item_upper:
                sheet_data['INST'].append(row_copy)
            else:
                sheet_data['FITTING'].append(row_copy)
        
        print(f"\n  === 파일 처리 완료: {os.path.basename(file_path)} ===")
        print(f"  - 이 파일에서 추출된 데이터: {len(file_data_sorted)}행 (중복 제거 후)")
        print(f"  - 현재까지 총 데이터: {len(all_data)}행")
    else:
        print(f"\n  === 파일 처리 완료: {os.path.basename(file_path)} ===")
        print(f"  - 이 파일에서 추출된 데이터: 0행")

# 6. Excel 파일 저장
if all_data:
    # Excel 워크북 생성
    wb = Workbook()
    
    # 헤더 정의 (PAINT 면적 추가)
    headers = ['ISO DWG NO', 'LINE NO', 'ISO DESCRIPTION', 'ITEM NO', 'ITEM', 'SIZE', 'MATERIAL', 
               'DESCRIPTION', 'Q\'TY', '(mm/ea)', 'U.WT', 'T.WT', 'INSU. T\'HK', 
               'PAINT 내면적(m²)', 'PAINT 외면적(m²)', 'REMARK']
    
    # INST, BOLT-NUT 시트용 헤더 (PAINT 면적 제외)
    headers_without_paint = ['ISO DWG NO', 'LINE NO', 'ISO DESCRIPTION', 'ITEM NO', 'ITEM', 'SIZE', 'MATERIAL', 
                           'DESCRIPTION', 'Q\'TY', '(mm/ea)', 'U.WT', 'T.WT', 'INSU. T\'HK', 'REMARK']
    
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
    
    # 첫 번째 시트: 전체 데이터 (MTO Data) - PAINT 면적 포함
    ws = wb.active
    ws.title = "MTO Data"
    
    # 헤더 작성
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.alignment = header_alignment
        cell.border = header_border
    
    # 데이터 작성 (_pt_header_index 제외)
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
    
    # 추가 시트 생성 및 데이터 입력
    sheet_names = ['FAB MAT', 'ELEC MAT', 'PIPE', 'BOLT-NUT', 'FITTING', 'INST']  # '/' 제거
    
    # TOTAL BOM 시트 생성을 위한 데이터 그룹화
    total_bom_data = defaultdict(lambda: {
        'Q\'TY': 0,
        '(mm/ea)': '',
        'U.WT': '',
        'count': 0,
        'inner_area': 0,
        'outer_area': 0
    })
    
    # 전체 데이터를 그룹화하여 합산
    for row in all_data:
        # 그룹화 키: ITEM + SIZE + MATERIAL + DESCRIPTION
        key = (
            row.get('ITEM', ''),
            row.get('SIZE', ''),
            row.get('MATERIAL', ''),
            row.get('DESCRIPTION', '')
        )
        
        # 수량 합산
        try:
            qty = float(row.get('Q\'TY', 0) or 0)
        except (ValueError, TypeError):
            qty = 0
        
        # 면적 합산
        try:
            inner = float(row.get('PAINT 내면적(m²)', 0) if row.get('PAINT 내면적(m²)') != '-' else 0)
            outer = float(row.get('PAINT 외면적(m²)', 0) if row.get('PAINT 외면적(m²)') != '-' else 0)
        except (ValueError, TypeError):
            inner = 0
            outer = 0
        
        total_bom_data[key]['Q\'TY'] += qty
        total_bom_data[key]['(mm/ea)'] = row.get('(mm/ea)', '')
        total_bom_data[key]['U.WT'] = row.get('U.WT', '')
        total_bom_data[key]['inner_area'] += inner
        total_bom_data[key]['outer_area'] += outer
        total_bom_data[key]['count'] += 1
    
    # TOTAL BOM 시트 데이터 생성
    total_bom_rows = []
    for (item, size, material, description), data in total_bom_data.items():
        # T.WT 계산 (Q'TY × U.WT)
        try:
            unit_weight = float(data['U.WT'] or 0)
            total_qty = data['Q\'TY']
            total_weight = unit_weight * total_qty
            
            # (mm/ea) 값이 MM인 경우 1000으로 나누기
            if data['(mm/ea)'] == 'MM':
                total_weight = total_weight / 1000
            
            # 반올림 처리
            if total_weight.is_integer():
                total_weight_str = str(int(total_weight))
            else:
                total_weight_str = str(round(total_weight, 1))
        except (ValueError, TypeError):
            total_weight_str = ''
        
        # 수량 반올림 처리
        if isinstance(data['Q\'TY'], (int, float)):
            if float(data['Q\'TY']).is_integer():
                qty_str = str(int(data['Q\'TY']))
            else:
                qty_str = str(round(data['Q\'TY'], 1))
        else:
            qty_str = str(data['Q\'TY'])
        
        # 면적 문자열 처리
        inner_area_str = str(round(data['inner_area'], 2)) if data['inner_area'] > 0 else '-'
        outer_area_str = str(round(data['outer_area'], 2)) if data['outer_area'] > 0 else '-'
        
        total_bom_rows.append({
            'ITEM': item,
            'SIZE': size,
            'MATERIAL': material,
            'DESCRIPTION': description,
            'Q\'TY': qty_str,
            '(mm/ea)': data['(mm/ea)'],
            'U.WT': data['U.WT'],
            'T.WT': total_weight_str,
            'PAINT 내면적(m²)': inner_area_str,
            'PAINT 외면적(m²)': outer_area_str
        })
    
    # TOTAL BOM 시트 생성 (PAINT 면적 포함)
    ws_total_bom = wb.create_sheet(title="TOTAL BOM", index=1)  # MTO Data 다음에 위치
    
    # TOTAL BOM 헤더 정의 (PAINT 면적 포함)
    total_bom_headers = ['ITEM', 'SIZE', 'MATERIAL', 'DESCRIPTION', 'Q\'TY', '(mm/ea)', 'U.WT', 'T.WT', 
                        'PAINT 내면적(m²)', 'PAINT 외면적(m²)']
    
    # 헤더 작성
    for col, header in enumerate(total_bom_headers, 1):
        cell = ws_total_bom.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.alignment = header_alignment
        cell.border = header_border
    
    # 데이터 작성 (ITEM으로 정렬)
    total_bom_rows_sorted = sorted(total_bom_rows, key=lambda x: x['ITEM'])
    
    # T.WT, 면적 합계 계산을 위한 변수 초기화
    total_weight_sum = 0
    total_inner_area_sum = 0
    total_outer_area_sum = 0
    
    for row_idx, data in enumerate(total_bom_rows_sorted, 2):
        for col_idx, header in enumerate(total_bom_headers, 1):
            value = data.get(header, '')
            cell = ws_total_bom.cell(row=row_idx, column=col_idx, value=value)
            cell.font = data_font
            cell.alignment = data_alignment
            cell.border = data_border
            
            # 합계 계산
            if header == 'T.WT' and value and value != '-':
                try:
                    total_weight_sum += float(value)
                except (ValueError, TypeError):
                    pass
            elif header == 'PAINT 내면적(m²)' and value and value != '-':
                try:
                    total_inner_area_sum += float(value)
                except (ValueError, TypeError):
                    pass
            elif header == 'PAINT 외면적(m²)' and value and value != '-':
                try:
                    total_outer_area_sum += float(value)
                except (ValueError, TypeError):
                    pass
    
    # 합계 행 추가
    sum_row = len(total_bom_rows_sorted) + 2
    
    # "TOTAL" 텍스트를 DESCRIPTION 열에 표시
    desc_col = total_bom_headers.index('DESCRIPTION') + 1
    cell = ws_total_bom.cell(row=sum_row, column=desc_col, value='TOTAL')
    cell.font = Font(size=12, bold=True)
    cell.alignment = header_alignment
    cell.border = header_border
    
    # T.WT 합계 표시
    twt_col = total_bom_headers.index('T.WT') + 1
    if total_weight_sum > 0:
        if total_weight_sum.is_integer():
            sum_value = str(int(total_weight_sum))
        else:
            sum_value = str(round(total_weight_sum, 1))
    else:
        sum_value = '0'
    
    cell = ws_total_bom.cell(row=sum_row, column=twt_col, value=sum_value)
    cell.font = Font(size=12, bold=True)
    cell.alignment = header_alignment
    cell.border = header_border
    
    # PAINT 내면적 합계 표시
    inner_col = total_bom_headers.index('PAINT 내면적(m²)') + 1
    if total_inner_area_sum > 0:
        inner_sum_value = str(round(total_inner_area_sum, 2))
    else:
        inner_sum_value = '0'
    
    cell = ws_total_bom.cell(row=sum_row, column=inner_col, value=inner_sum_value)
    cell.font = Font(size=12, bold=True)
    cell.alignment = header_alignment
    cell.border = header_border
    
    # PAINT 외면적 합계 표시
    outer_col = total_bom_headers.index('PAINT 외면적(m²)') + 1
    if total_outer_area_sum > 0:
        outer_sum_value = str(round(total_outer_area_sum, 2))
    else:
        outer_sum_value = '0'
    
    cell = ws_total_bom.cell(row=sum_row, column=outer_col, value=outer_sum_value)
    cell.font = Font(size=12, bold=True)
    cell.alignment = header_alignment
    cell.border = header_border
    
    # 나머지 빈 셀에도 테두리 적용
    for col_idx in range(1, len(total_bom_headers) + 1):
        if col_idx not in [desc_col, twt_col, inner_col, outer_col]:
            cell = ws_total_bom.cell(row=sum_row, column=col_idx, value='')
            cell.border = header_border
    
    # 컬럼 너비 자동 조정
    for column in ws_total_bom.columns:
        max_length = 0
        column_letter = get_column_letter(column[0].column)
        
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        
        adjusted_width = (max_length + 2) * 1.2
        ws_total_bom.column_dimensions[column_letter].width = adjusted_width
    
    # 나머지 시트들 생성
    for sheet_name in sheet_names:
        if sheet_data[sheet_name]:  # 데이터가 있는 경우만 시트 생성
            ws = wb.create_sheet(title=sheet_name)
            
            # INST, BOLT-NUT은 PAINT 면적 제외
            if sheet_name in ['INST', 'BOLT-NUT']:  # '/' 제거
                use_headers = headers_without_paint
            else:
                use_headers = headers
            
            # 헤더 작성
            for col, header in enumerate(use_headers, 1):
                cell = ws.cell(row=1, column=col, value=header)
                cell.font = header_font
                cell.alignment = header_alignment
                cell.border = header_border
            
            # 데이터 작성
            for row_idx, data in enumerate(sheet_data[sheet_name], 2):
                for col_idx, header in enumerate(use_headers, 1):
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
    
    # 파일 저장
    wb.save(excel_path)
    
    print(f"\n=== Excel 파일 저장 완료 ===")
    print(f"파일명: {excel_filename}")
    print(f"경로: {excel_path}")
    print(f"총 {len(all_data)}개의 데이터 저장됨")
    print(f"\n=== 개선된 기능 ===")
    print(f"- BLOCK 텍스트와 일반 텍스트 모두 정확히 읽기")
    print(f"- BLOCK의 스케일과 회전 변환 적용")
    print(f"- 텍스트 타입별 디버깅 정보 추가 (NORMAL/BLOCK/ATTRIB/ATTDEF)")
    print(f"- Y값 그룹화를 통한 같은 줄 텍스트 정확한 조합")
    print(f"- 모든 텍스트를 공백 없이 연결하여 완전한 ISODWGNO 생성")
    print(f"- X: 770-780, Y: 5-20 범위의 추가 텍스트를 ISODWGNO에 연결")
    print(f"\n=== ISODWGNO 검색 프로세스 ===")
    print(f"1단계: FABRICATION MATERIALS 섹션에서 검색")
    print(f"2단계: X: 700-900, Y: 5-25 범위에서 검색 및 조합")
    print(f"2-1단계: X: 770-780, Y: 5-20 범위의 추가 텍스트 연결")
    print(f"3단계: X: 690-950, Y: 0-30 확장 범위 검색 (필요시)")
    print(f"\n=== 기타 값 검색 우선순위 ===")
    print(f"- INSU: X:185-200 Y:60-70 → X:260-280 Y:30-75")
    print(f"- ISO DESCRIPTION: ISO DWG NO 근처 → X:700-950 Y:20-40")
    print(f"- BLOCK 내부의 TEXT도 검색 가능 (스케일/회전 보정)")
    print(f"- Y값을 2단위로 그룹화하여 같은 줄 텍스트 정확히 포착")
else:
    print("\n추출된 데이터가 없습니다.")