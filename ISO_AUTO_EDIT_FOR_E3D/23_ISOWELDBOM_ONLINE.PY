import os
import re
import sys
import ezdxf
from datetime import datetime

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

def clean_str(s):
    return ''.join(s.split())

# 동일 재질 매핑 테이블 (ASME B31.1/B31.3 기준)
MATERIAL_EQUIVALENCE = {
    # 탄소강 (Carbon Steel) - Grade B
    'A106-B': 'CS',
    'A106B': 'CS',
    'SA106-B': 'CS',
    'SA106B': 'CS',
    'A53-B': 'CS',
    'A53B': 'CS',
    'SA53-B': 'CS',
    'SA53B': 'CS',
    'A234-WPB': 'CS',
    'A234WPB': 'CS',
    'SA234-WPB': 'CS',
    'SA234WPB': 'CS',
    'A105': 'CS',
    'SA105': 'CS',
    
    # 탄소강 (Carbon Steel) - Grade C
    'A106-C': 'CS',
    'A106C': 'CS',
    'SA106-C': 'CS',
    'SA106C': 'CS',
    'A234-WPC': 'CS',
    'A234WPC': 'CS',
    'SA234-WPC': 'CS',
    'SA234WPC': 'CS',
    
    # 탄소강 (Carbon Steel) - Grade A
    'A106-A': 'CS',
    'A106A': 'CS',
    'SA106-A': 'CS',
    'SA106A': 'CS',
    'A53-A': 'CS',
    'A53A': 'CS',
    'SA53-A': 'CS',
    'SA53A': 'CS',
    'A234-WPA': 'CS',
    'A234WPA': 'CS',
    'SA234-WPA': 'CS',
    'SA234WPA': 'CS',
    
    # 저합금강 P1 (0.5Mo)
    'A335-P1': 'P1',
    'A335P1': 'P1',
    'SA335-P1': 'P1',
    'SA335P1': 'P1',
    'A234-WP1': 'P1',
    'A234WP1': 'P1',
    'SA234-WP1': 'P1',
    'SA234WP1': 'P1',
    'A182-F1': 'P1',
    'A182F1': 'P1',
    'SA182-F1': 'P1',
    'SA182F1': 'P1',
    
    # 저합금강 P5 (5Cr-0.5Mo)
    'A335-P5': 'P5',
    'A335P5': 'P5',
    'SA335-P5': 'P5',
    'SA335P5': 'P5',
    'A234-WP5': 'P5',
    'A234WP5': 'P5',
    'SA234-WP5': 'P5',
    'SA234WP5': 'P5',
    'A182-F5': 'P5',
    'A182F5': 'P5',
    'SA182-F5': 'P5',
    'SA182F5': 'P5',
    
    # 저합금강 P11 (1.25Cr-0.5Mo)
    'A335-P11': 'P11',
    'A335P11': 'P11',
    'SA335-P11': 'P11',
    'SA335P11': 'P11',
    'A234-WP11': 'P11',
    'A234WP11': 'P11',
    'SA234-WP11': 'P11',
    'SA234WP11': 'P11',
    'A182-F11': 'P11',
    'A182F11': 'P11',
    'SA182-F11': 'P11',
    'SA182F11': 'P11',
    
    # 저합금강 P22 (2.25Cr-1Mo)
    'A335-P22': 'P22',
    'A335P22': 'P22',
    'SA335-P22': 'P22',
    'SA335P22': 'P22',
    'A234-WP22': 'P22',
    'A234WP22': 'P22',
    'SA234-WP22': 'P22',
    'SA234WP22': 'P22',
    'A182-F22': 'P22',
    'A182F22': 'P22',
    'SA182-F22': 'P22',
    'SA182F22': 'P22',
    
    # 고합금강 P91 (9Cr-1Mo-V)
    'A335-P91': 'P91',
    'A335P91': 'P91',
    'SA335-P91': 'P91',
    'SA335P91': 'P91',
    'A234-WP91': 'P91',
    'A234WP91': 'P91',
    'SA234-WP91': 'P91',
    'SA234WP91': 'P91',
    'A182-F91': 'P91',
    'A182F91': 'P91',
    'SA182-F91': 'P91',
    'SA182F91': 'P91',
    
    # 고합금강 P92 (9Cr-0.5Mo-1.8W-V-Nb)
    'A335-P92': 'P92',
    'A335P92': 'P92',
    'SA335-P92': 'P92',
    'SA335P92': 'P92',
    'A234-WP92': 'P92',
    'A234WP92': 'P92',
    'SA234-WP92': 'P92',
    'SA234WP92': 'P92',
    'A182-F92': 'P92',
    'A182F92': 'P92',
    'SA182-F92': 'P92',
    'SA182F92': 'P92',
    
    # 스테인리스 304
    'A312-TP304': 'SS304',
    'A312TP304': 'SS304',
    'SA312-TP304': 'SS304',
    'SA312TP304': 'SS304',
    'A403-WP304': 'SS304',
    'A403WP304': 'SS304',
    'SA403-WP304': 'SS304',
    'SA403WP304': 'SS304',
    'A182-F304': 'SS304',
    'A182F304': 'SS304',
    'SA182-F304': 'SS304',
    'SA182F304': 'SS304',
    
    # 스테인리스 304L
    'A312-TP304L': 'SS304L',
    'A312TP304L': 'SS304L',
    'SA312-TP304L': 'SS304L',
    'SA312TP304L': 'SS304L',
    'A403-WP304L': 'SS304L',
    'A403WP304L': 'SS304L',
    'SA403-WP304L': 'SS304L',
    'SA403WP304L': 'SS304L',
    'A182-F304L': 'SS304L',
    'A182F304L': 'SS304L',
    'SA182-F304L': 'SS304L',
    'SA182F304L': 'SS304L',
    
    # 스테인리스 316
    'A312-TP316': 'SS316',
    'A312TP316': 'SS316',
    'SA312-TP316': 'SS316',
    'SA312TP316': 'SS316',
    'A403-WP316': 'SS316',
    'A403WP316': 'SS316',
    'SA403-WP316': 'SS316',
    'SA403WP316': 'SS316',
    'A182-F316': 'SS316',
    'A182F316': 'SS316',
    'SA182-F316': 'SS316',
    'SA182F316': 'SS316',
    
    # 스테인리스 316L
    'A312-TP316L': 'SS316L',
    'A312TP316L': 'SS316L',
    'SA312-TP316L': 'SS316L',
    'SA312TP316L': 'SS316L',
    'A403-WP316L': 'SS316L',
    'A403WP316L': 'SS316L',
    'SA403-WP316L': 'SS316L',
    'SA403WP316L': 'SS316L',
    'A182-F316L': 'SS316L',
    'A182F316L': 'SS316L',
    'SA182-F316L': 'SS316L',
    'SA182F316L': 'SS316L',
    
    # 스테인리스 321
    'A312-TP321': 'SS321',
    'A312TP321': 'SS321',
    'SA312-TP321': 'SS321',
    'SA312TP321': 'SS321',
    'A403-WP321': 'SS321',
    'A403WP321': 'SS321',
    'SA403-WP321': 'SS321',
    'SA403WP321': 'SS321',
    'A182-F321': 'SS321',
    'A182F321': 'SS321',
    'SA182-F321': 'SS321',
    'SA182F321': 'SS321',
    
    # 스테인리스 347
    'A312-TP347': 'SS347',
    'A312TP347': 'SS347',
    'SA312-TP347': 'SS347',
    'SA312TP347': 'SS347',
    'A403-WP347': 'SS347',
    'A403WP347': 'SS347',
    'SA403-WP347': 'SS347',
    'SA403WP347': 'SS347',
    'A182-F347': 'SS347',
    'A182F347': 'SS347',
    'SA182-F347': 'SS347',
    'SA182F347': 'SS347',
}

def get_mat_group(mat_value):
    """MAT 값에서 그룹명 추출 (ASME B31.1/B31.3 동일 재질 규정 적용)"""
    if not mat_value:
        return 'UNKNOWN'
    
    # 공백 제거 및 대문자 변환
    clean_mat = mat_value.strip().upper()
    
    # 동일 재질 매핑 테이블에서 찾기
    for mat_pattern, group in MATERIAL_EQUIVALENCE.items():
        if mat_pattern in clean_mat:
            return group
    
    # 매핑 테이블에 없으면 P 패턴으로 시도
    import re
    match = re.search(r'-P(\d+)', clean_mat)
    if match:
        return f"P{match.group(1)}"
    
    # 그 외의 경우 원래 재질명을 정리하여 사용
    # 특수문자 제거 (시트명에 사용 불가)
    clean_mat = re.sub(r'[^\w\s-]', '', mat_value)
    return clean_mat[:20]  # Excel 시트명 길이 제한

# DN to 인치 변환 테이블
DN_TO_INCH = {
    '15': '0.5',
    '20': '0.75',
    '25': '1',
    '32': '1.25',
    '40': '1.5',
    '50': '2',
    '65': '2.5',
    '80': '3',
    '100': '4',
    '125': '5',
    '150': '6',
    '200': '8',
    '250': '10',
    '300': '12',
    '350': '14',
    '400': '16',
    '450': '18',
    '500': '20',
    '600': '24',
    '700': '28',
    '750': '30',
    '800': '32',
    '900': '36',
    '1000': '40',
    '1200': '48'
}

def should_append_text(existing_text, new_text):
    """두 번째 줄 텍스트를 추가할지 결정하는 함수"""
    if not new_text or not existing_text:
        return True
    
    # 완전히 같으면 추가하지 않음
    if new_text == existing_text:
        return False
    
    # new_text가 existing_text에 완전히 포함되면 추가하지 않음
    if new_text in existing_text:
        return False
    
    # new_text의 모든 단어가 existing_text에 있으면 추가하지 않음
    new_words = new_text.split()
    existing_words = existing_text.split()
    
    # 모든 새 단어가 기존 텍스트에 있는지 확인
    all_words_exist = all(word in existing_words for word in new_words)
    
    return not all_words_exist

def update_size_mapping(size, new_mat, new_thk, size_mat_thk_mapping):
    """SIZE 매핑 업데이트 함수 - 포함 관계 확인하여 더 긴 텍스트 선택"""
    if size in size_mat_thk_mapping:
        existing_mat = size_mat_thk_mapping[size]['MAT']
        existing_thk = size_mat_thk_mapping[size]['THK']
        update_mat = False
        update_thk = False
        
        # MAT 포함 관계 확인
        if new_mat and existing_mat:
            if new_mat in existing_mat or existing_mat in new_mat:
                if len(new_mat) > len(existing_mat):
                    update_mat = True
        
        # THK 포함 관계 확인
        if new_thk and existing_thk:
            if new_thk in existing_thk or existing_thk in new_thk:
                if len(new_thk) > len(existing_thk):
                    update_thk = True
        
        # 업데이트 필요한 경우만 수정
        if update_mat or update_thk:
            final_mat = new_mat if update_mat else existing_mat
            final_thk = new_thk if update_thk else existing_thk
            size_mat_thk_mapping[size] = {'MAT': final_mat, 'THK': final_thk}
    else:
        size_mat_thk_mapping[size] = {'MAT': new_mat if new_mat else '', 'THK': new_thk if new_thk else ''}

def process_weld_type_data(fld_value, dn_value, type_value):
    """WELD 데이터에서 /FLD, DN, TYPE 값을 정리하는 함수
    특히 "FW 350 350" 같은 패턴을 처리
    """
    # TYPE에 DN 값(숫자)이 들어간 경우 처리
    if type_value and type_value.replace('.', '').replace('-', '').isdigit():
        # TYPE에 숫자가 있으면 DN이 잘못 들어간 것
        if not dn_value or dn_value == type_value:
            dn_value = type_value
            type_value = 'BW'  # 기본값으로 BW 설정
    
    # /FLD 값에 여러 값이 합쳐진 경우 처리 (예: "FW 350 350")
    if fld_value:
        parts = fld_value.split()
        if len(parts) >= 2:
            # 첫 번째 부분이 FW/SW인지 확인
            if parts[0].upper() in ['FW', 'SW', 'F', 'S']:
                fld_value = parts[0].upper()
                # 두 번째 부분이 숫자면 DN으로
                if len(parts) >= 2 and parts[1].replace('.', '').replace('-', '').isdigit():
                    if not dn_value:
                        dn_value = parts[1]
                    # 세 번째 부분 처리
                    if len(parts) >= 3:
                        # 세 번째도 숫자면 무시하고 BW로 설정
                        if parts[2].replace('.', '').replace('-', '').isdigit():
                            type_value = 'BW'
                        else:
                            type_value = parts[2].upper()
                    else:
                        # 세 번째 부분이 없으면 BW로 설정
                        type_value = 'BW'
    
    # DN 값에 여러 값이 합쳐진 경우 처리
    if dn_value and ' ' in dn_value:
        parts = dn_value.split()
        if len(parts) >= 2:
            # 첫 번째가 FW/SW면 /FLD로
            if parts[0].upper() in ['FW', 'SW', 'F', 'S'] and not fld_value:
                fld_value = parts[0].upper()
                if len(parts) >= 2:
                    dn_value = parts[1]
                if len(parts) >= 3 and not type_value:
                    type_value = parts[2].upper() if not parts[2].isdigit() else 'BW'
            # 첫 번째가 숫자면 DN으로
            elif parts[0].replace('.', '').replace('-', '').isdigit():
                dn_value = parts[0]
                if len(parts) >= 2 and not type_value:
                    type_value = parts[1].upper() if not parts[1].isdigit() else 'BW'
    
    # TYPE 값에 여러 값이 합쳐진 경우 처리
    if type_value and ' ' in type_value:
        parts = type_value.split()
        # 마지막 부분을 TYPE으로
        for part in reversed(parts):
            if part.upper() in ['BW', 'SW', 'FW', 'TH']:
                type_value = part.upper()
                break
        else:
            # 적절한 TYPE이 없으면 BW로 설정
            type_value = 'BW'
    
    # TYPE이 여전히 숫자면 BW로 변경
    if type_value and type_value.replace('.', '').replace('-', '').isdigit():
        type_value = 'BW'
    
    # TYPE이 비어있으면 BW로 설정
    if not type_value:
        type_value = 'BW'
    
    return fld_value, dn_value, type_value

# Command line 인자 확인
if len(sys.argv) < 2:
    print("사용법: python PLOTNEWLINE.PY file1.dxf file2.dxf ...")
    exit()

# DXF 파일 경로들
file_paths = sys.argv[1:]

# Excel 파일명 생성 (날짜시간 포함)
now = datetime.now()
datetime_str = now.strftime("%Y%m%d_%H%M%S")
excel_filename = f"TOTALWELD_{datetime_str}.xlsx"
excel_path = os.path.join(os.path.dirname(file_paths[0]), excel_filename)

# 전체 데이터를 저장할 리스트
all_weld_data = []

# 각 DXF 파일 처리
for file_path in file_paths:
    # 파일별로 SIZE 매핑 초기화 (각 도면마다 새로운 매핑)
    size_mat_thk_mapping = {}
    
    try:
        doc = ezdxf.readfile(file_path)
        msp = doc.modelspace()
    except Exception as e:
        continue
    
    # 1. LINENO 찾기
    lineno = None
    for e in msp.query('TEXT MTEXT'):
        txt = get_text(e).strip()
        x, y = get_xy(e)
        if 0 <= x <= 150 and 0 <= y <= 85 and '-' in txt and len(txt) >= 10:
            lineno = clean_str(txt)
            break
    
    if not lineno:
        lineno = '-'
    
    # 2. ISODWGNO 찾기
    isodwgno = None
    fab_mat_e = None
    fab_x, fab_y = None, None
    
    for e in msp.query('TEXT MTEXT'):
        txt = get_text(e)
        if "FABRICATION MATERIALS" in txt.upper():
            fab_mat_e = e
            fab_x, fab_y = get_xy(e)
            break
    
    if fab_mat_e:
        for e in msp.query('TEXT MTEXT'):
            txt = get_text(e).strip()
            x, y = get_xy(e)
            if fab_x is not None and fab_y is not None:
                if (x > fab_x) and (0 <= y <= 20) and ('-' in txt):
                    isodwgno = txt
                    break
    
    if not isodwgno:
        isodwgno = '-'
    
    # 3. PT 테이블에서 SIZE-MAT-THK 매핑 구축
    # PT 헤더 찾기
    pt_headers = []
    for e in msp.query('TEXT MTEXT'):
        txt = get_text(e).strip().upper()
        x, y = get_xy(e)
        if txt == 'PT' or (txt.startswith('PT') and len(txt) <= 5):
            pt_headers.append((x, y, txt))
    
    # 각 PT 테이블 처리
    for pt_idx, (pt_x, pt_y, pt_txt) in enumerate(pt_headers):
        # 현재 PT 헤더 주변의 다른 헤더들 찾기
        header_positions = {'PT': pt_x}
        
        # PT와 같은 Y 좌표 근처에서 다른 헤더 찾기
        for e in msp.query('TEXT MTEXT'):
            txt = get_text(e).strip().upper()
            x, y = get_xy(e)
            
            if abs(y - pt_y) <= 8:
                if 'SIZE' in txt:
                    header_positions['SIZE'] = x
                elif 'MATERIAL' in txt:
                    header_positions['MATERIAL'] = x
                elif 'DESC' in txt:
                    header_positions['DESCRIPTION'] = x
        
        # 필요한 헤더가 없으면 스킵
        if 'SIZE' not in header_positions:
            continue
        
        # 모든 텍스트를 Y좌표로 정렬
        all_texts = []
        for e in msp.query('TEXT MTEXT'):
            txt = get_text(e).strip()
            x, y = get_xy(e)
            if txt:
                all_texts.append((x, y, txt))
        
        all_texts.sort(key=lambda t: -t[1])  # Y좌표 내림차순 정렬
        
        # PT 데이터 읽기
        for x, y, txt in all_texts:
            # PT 헤더 아래에서만 검색
            if y >= pt_y:
                continue
            
            # PT 열에서 숫자 찾기
            if abs(x - pt_x) <= 4 and txt.isdigit():
                # 현재 행의 SIZE, MATERIAL, DESCRIPTION 읽기
                size_value = None
                mat_value = None
                desc_value = None
                
                # 첫 번째 줄 데이터 읽기
                for hdr, hdr_x in header_positions.items():
                    if hdr == 'SIZE':
                        for x2, y2, txt2 in all_texts:
                            if abs(x2 - hdr_x) <= 4 and abs(y2 - y) <= 4 and txt2:
                                size_value = txt2
                                break
                    elif hdr == 'MATERIAL':
                        for x2, y2, txt2 in all_texts:
                            if abs(x2 - hdr_x) <= 4 and abs(y2 - y) <= 4 and txt2:
                                mat_value = txt2
                                break
                    elif hdr == 'DESCRIPTION':
                        for x2, y2, txt2 in all_texts:
                            if abs(x2 - hdr_x) <= 4 and abs(y2 - y) <= 4 and txt2:
                                desc_value = txt2
                                break
                
                # 두 번째 줄 확인 - 모든 필드에 대해 2줄 데이터 처리
                for check_y in range(int(y-10), int(y-3)):
                    # PT 열에 숫자가 없는 경우만 (다음 PT 항목이 아닌 경우)
                    pt_exists = False
                    for x3, y3, txt3 in all_texts:
                        if abs(x3 - pt_x) <= 4 and abs(y3 - check_y) <= 2 and txt3.isdigit():
                            pt_exists = True
                            break
                    
                    if not pt_exists:
                        # SIZE 2줄 처리
                        if size_value and 'SIZE' in header_positions:
                            size_x = header_positions['SIZE']
                            for x2, y2, txt2 in all_texts:
                                if abs(x2 - size_x) <= 4 and abs(y2 - check_y) <= 2 and txt2:
                                    if should_append_text(size_value, txt2):
                                        size_value = size_value + ' ' + txt2
                                    break
                        
                        # MATERIAL 2줄 처리
                        if mat_value and 'MATERIAL' in header_positions:
                            mat_x = header_positions['MATERIAL']
                            for x2, y2, txt2 in all_texts:
                                if abs(x2 - mat_x) <= 4 and abs(y2 - check_y) <= 2 and txt2:
                                    if should_append_text(mat_value, txt2):
                                        mat_value = mat_value + ' ' + txt2
                                    break
                        
                        # DESCRIPTION 2줄 처리
                        if desc_value and 'DESCRIPTION' in header_positions:
                            desc_x = header_positions['DESCRIPTION']
                            for x2, y2, txt2 in all_texts:
                                if abs(x2 - desc_x) <= 4 and abs(y2 - check_y) <= 2 and txt2:
                                    if should_append_text(desc_value, txt2):
                                        desc_value = desc_value + ' ' + txt2
                                    break
                        break
                
                # SIZE가 있으면 매핑 구축
                if size_value and size_value.strip():
                    # SIZE에 x가 있는 경우 처리
                    if 'x' in size_value.lower():
                        # x로 분리
                        parts = re.split(r'[xX]', size_value)
                        if len(parts) == 2:
                            size1 = parts[0].strip()
                            size2 = parts[1].strip()
                            
                            # 빈 값 체크
                            if not size1 or not size2:
                                continue
                            
                            # DESCRIPTION에서도 x로 분리
                            if desc_value and 'x' in desc_value.lower():
                                desc_parts = re.split(r'[xX]', desc_value)
                                if len(desc_parts) == 2:
                                    thk1 = desc_parts[0].strip()
                                    thk2 = desc_parts[1].strip()
                                    
                                    # 각 SIZE별로 매핑 저장 (포함 관계 확인)
                                    update_size_mapping(size1, mat_value, thk1, size_mat_thk_mapping)
                                    update_size_mapping(size2, mat_value, thk2, size_mat_thk_mapping)
                                else:
                                    # x가 없으면 전체 DESCRIPTION을 THK로 사용 (포함 관계 확인)
                                    update_size_mapping(size1, mat_value, desc_value, size_mat_thk_mapping)
                                    update_size_mapping(size2, mat_value, desc_value, size_mat_thk_mapping)
                            else:
                                # DESCRIPTION에 x가 없으면 전체를 THK로 (포함 관계 확인)
                                update_size_mapping(size1, mat_value, desc_value, size_mat_thk_mapping)
                                update_size_mapping(size2, mat_value, desc_value, size_mat_thk_mapping)
                    else:
                        # x가 없는 경우 (포함 관계 확인)
                        update_size_mapping(size_value, mat_value, desc_value, size_mat_thk_mapping)
    
    # 4. NO/FLD/DN/TYPE 테이블 찾기
    weld_headers = ['NO', '/FLD', 'DN', 'TYPE']
    
    # NO 헤더 찾기 (다양한 형태 인식)
    no_headers = []
    for e in msp.query('TEXT MTEXT'):
        txt = get_text(e).strip().upper()
        x, y = get_xy(e)
        # NO, WELD NO, JT NO, JOINT NO 등 다양한 형태 인식
        if (txt == 'NO' or 
            (txt.startswith('NO') and len(txt) <= 5) or
            txt == 'WELD NO' or txt == 'WELDNO' or
            txt == 'JT NO' or txt == 'JTNO' or
            txt == 'JOINT NO' or txt == 'JOINTNO' or
            (txt.endswith('NO') and len(txt) <= 10)):
            
            # NO 오른쪽에서 /FLD, DN, TYPE 헤더 모두 확인
            found_headers = {'NO': True, '/FLD': False, 'DN': False, 'TYPE': False}
            
            for e2 in msp.query('TEXT MTEXT'):
                txt2 = get_text(e2).strip().upper()
                x2, y2 = get_xy(e2)
                # NO와 같은 높이(±20mm)이고 NO 오른쪽에 있는 헤더 확인
                if abs(y2 - y) <= 20 and x2 > x:
                    # /FLD 관련
                    if not found_headers['/FLD'] and ('FLD' in txt2 or txt2 in ['S', 'F', 'S/F']):
                        found_headers['/FLD'] = True
                    # DN 관련
                    elif not found_headers['DN'] and ('DN' in txt2 or 'SIZE' in txt2):
                        found_headers['DN'] = True
                    # TYPE 관련
                    elif not found_headers['TYPE'] and ('TYPE' in txt2 or 'WLD' in txt2 or 'WELD' in txt2):
                        found_headers['TYPE'] = True
            
            # 4개 헤더가 모두 있는 경우만 유효한 테이블로 인식
            if all(found_headers.values()):
                no_headers.append((x, y, txt))
    
    # 각 NO 테이블 처리
    for no_idx, (no_x, no_y, no_txt) in enumerate(no_headers):
        # 현재 NO 헤더 주변의 다른 헤더들 찾기
        weld_header_positions = {'NO': no_x}
        
        # NO와 같은 Y 좌표 근처에서 다른 헤더 찾기 (NO 오른쪽에서만 검색)
        # 먼저 NO와 비슷한 Y 좌표의 모든 텍스트를 수집
        header_candidates = []
        for e in msp.query('TEXT MTEXT'):
            txt = get_text(e).strip()
            txt_upper = txt.upper()
            x, y = get_xy(e)
            
            # NO와 같은 높이(±20mm)이고 NO보다 오른쪽(+X)에 있는 텍스트
            if abs(y - no_y) <= 20 and x > no_x:
                header_candidates.append((x, y, txt, txt_upper))
        
        # X 좌표로 정렬
        header_candidates.sort(key=lambda t: t[0])
        
        # 헤더를 순서대로 찾기 (X 좌표 순서대로)
        for x, y, txt, txt_upper in header_candidates:
            # /FLD 또는 FLD 찾기 (S, F, S/F도 포함)
            if '/FLD' not in weld_header_positions:
                if '/FLD' in txt_upper or txt_upper == 'FLD' or txt_upper in ['S/F', 'SHOP', 'FIELD']:
                    # 단독 S, F는 다른 헤더가 있을 때만 /FLD로 인식
                    if txt_upper in ['S', 'F']:
                        # 주변에 다른 WELD 헤더가 있는지 확인
                        if any(h in weld_header_positions for h in ['NO', 'DN', 'TYPE']):
                            weld_header_positions['/FLD'] = x
                    else:
                        weld_header_positions['/FLD'] = x
                    continue
            
            # DN 찾기 (숫자가 주로 오는 열)
            if 'DN' not in weld_header_positions:
                if txt_upper == 'DN' or txt_upper == 'SIZE' or txt_upper == 'BORE':
                    weld_header_positions['DN'] = x
                    continue
            
            # TYPE 찾기 (BW, SW 등이 오는 열) - 엄격한 매칭
            if 'TYPE' not in weld_header_positions:
                # DN과 동일한 X 위치가 아닌 경우에만 TYPE으로 인식
                if 'DN' in weld_header_positions and abs(x - weld_header_positions['DN']) < 5:
                    # DN과 너무 가까우면 TYPE이 아닐 가능성이 높음
                    continue
                    
                if txt_upper == 'TYPE' or txt_upper == 'WLD TYPE' or txt_upper == 'WELD TYPE':
                    weld_header_positions['TYPE'] = x
                    continue
                elif txt_upper in ['WLD', 'WELD', 'CONNECTION', 'JOINT TYPE', 'WELD JOINT']:
                    weld_header_positions['TYPE'] = x
                    continue
        
        # 4개 헤더를 모두 찾지 못한 경우 이 테이블 건너뛰기
        required_headers = ['NO', '/FLD', 'DN', 'TYPE']
        missing_headers = [h for h in required_headers if h not in weld_header_positions]
        
        if missing_headers:
            continue
        
        # 헤더를 못 찾은 경우 디버깅 정보 출력 및 추가 시도
        if len(weld_header_positions) < 4:
            nearby_texts = []
            for e in msp.query('TEXT MTEXT'):
                txt = get_text(e).strip()
                x, y = get_xy(e)
                # NO 헤더와 같은 높이(±25mm)이고 NO보다 오른쪽에 있는 텍스트만
                if abs(y - no_y) <= 25 and x > no_x and txt:
                    nearby_texts.append((x, y, txt))
            
            # X 좌표로 정렬하여 출력
            nearby_texts.sort(key=lambda t: t[0])
            
            # /FLD 헤더가 없는 경우 S, F 패턴으로 위치 추정
            if '/FLD' not in weld_header_positions:
                fld_x_candidates = {}
                sample_count = 0
                
                for x, y, txt in all_texts:
                    if y < no_y and abs(x - no_x) <= 8 and txt.isdigit() and sample_count < 5:
                        sample_count += 1
                        for x2, y2, txt2 in all_texts:
                            if abs(y2 - y) <= 4 and x2 > no_x + 5 and txt2.upper() in ['S', 'F', 'S/F', 'SW', 'FW']:
                                x_rounded = round(x2 / 5) * 5
                                fld_x_candidates[x_rounded] = fld_x_candidates.get(x_rounded, 0) + 1
                
                if fld_x_candidates:
                    best_x = max(fld_x_candidates.items(), key=lambda item: item[1])[0]
                    weld_header_positions['/FLD'] = best_x
            
            # TYPE 헤더가 없는 경우 BW, SW 패턴으로 위치 추정
            if 'TYPE' not in weld_header_positions:
                type_x_candidates = {}
                sample_count = 0
                
                for x, y, txt in all_texts:
                    if y < no_y and abs(x - no_x) <= 8 and txt.isdigit() and sample_count < 5:
                        sample_count += 1
                        for x2, y2, txt2 in all_texts:
                            if abs(y2 - y) <= 4 and x2 > no_x + 10 and txt2.upper() in ['BW', 'SW', 'FW', 'TH']:
                                # DN 위치와 다른 X 위치인 경우에만 TYPE 후보로 고려
                                if 'DN' in weld_header_positions and abs(x2 - weld_header_positions['DN']) < 10:
                                    continue
                                x_rounded = round(x2 / 5) * 5
                                type_x_candidates[x_rounded] = type_x_candidates.get(x_rounded, 0) + 1
                
                if type_x_candidates:
                    # DN 위치와 가장 멀리 떨어진 후보를 선택
                    if 'DN' in weld_header_positions:
                        dn_x = weld_header_positions['DN']
                        best_x = max(type_x_candidates.items(), 
                                   key=lambda item: (item[1], abs(item[0] - dn_x)))[0]
                    else:
                        best_x = max(type_x_candidates.items(), key=lambda item: item[1])[0]
                    weld_header_positions['TYPE'] = best_x
            
            # DN 헤더가 없는 경우 NO 오른쪽의 숫자 패턴으로 DN 위치 추정
            if 'DN' not in weld_header_positions:
                # NO 아래의 첫 몇 개 행에서 숫자 패턴 분석
                dn_x_candidates = {}
                sample_count = 0
                
                for x, y, txt in all_texts:
                    # NO 헤더 아래이고 NO 열에서 숫자인 경우
                    if y < no_y and abs(x - no_x) <= 8 and txt.isdigit() and sample_count < 5:
                        sample_count += 1
                        # 이 NO와 같은 Y에서 오른쪽의 숫자 찾기
                        for x2, y2, txt2 in all_texts:
                            if abs(y2 - y) <= 4 and x2 > no_x + 10 and txt2.replace('.', '').replace('-', '').isdigit():
                                x_rounded = round(x2 / 5) * 5  # 5mm 단위로 그룹화
                                dn_x_candidates[x_rounded] = dn_x_candidates.get(x_rounded, 0) + 1
                
                if dn_x_candidates:
                    # 가장 많이 나타나는 X 위치를 DN으로 추정
                    best_x = max(dn_x_candidates.items(), key=lambda item: item[1])[0]
                    weld_header_positions['DN'] = best_x
            # DN과 TYPE 헤더 위치 검증 - 데이터 패턴으로 확인
            if 'DN' in weld_header_positions and 'TYPE' in weld_header_positions:
                dn_x = weld_header_positions['DN']
                type_x = weld_header_positions['TYPE']
                
                # DN과 TYPE의 X 위치가 동일하거나 너무 가까운 경우
                if abs(dn_x - type_x) < 10:
                    # TYPE 위치를 다시 찾기 - DN보다 오른쪽에서 BW/SW 패턴 찾기
                    type_x_candidates = {}
                    sample_count = 0
                    
                    for x, y, txt in all_texts:
                        if y < no_y and abs(x - no_x) <= 8 and txt.isdigit() and sample_count < 5:
                            sample_count += 1
                            for x2, y2, txt2 in all_texts:
                                if (abs(y2 - y) <= 4 and x2 > dn_x + 10 and 
                                    txt2.upper() in ['BW', 'SW', 'FW', 'TH', 'BUTT', 'SOCKET']):
                                    x_rounded = round(x2 / 5) * 5
                                    type_x_candidates[x_rounded] = type_x_candidates.get(x_rounded, 0) + 1
                    
                    if type_x_candidates:
                        best_x = max(type_x_candidates.items(), key=lambda item: item[1])[0]
                        weld_header_positions['TYPE'] = best_x
                        type_x = best_x
                
                # 각 위치의 데이터 샘플 수집
                dn_samples = []
                type_samples = []
                sample_count = 0
                
                for x, y, txt in all_texts:
                    if y < no_y and abs(x - no_x) <= 8 and txt.isdigit() and sample_count < 3:
                        sample_count += 1
                        # DN 위치의 데이터
                        for x2, y2, txt2 in all_texts:
                            if abs(y2 - y) <= 4 and abs(x2 - dn_x) <= 8 and txt2:
                                dn_samples.append(txt2.upper())
                                break
                        # TYPE 위치의 데이터
                        for x2, y2, txt2 in all_texts:
                            if abs(y2 - y) <= 4 and abs(x2 - type_x) <= 8 and txt2:
                                type_samples.append(txt2.upper())
                                break
                
                # DN 위치에 타입 값(BW, SW 등)이 있고, TYPE 위치에 숫자가 있으면 바꾸기
                dn_has_types = any(s in ['BW', 'SW', 'FW', 'TH'] for s in dn_samples if s)
                type_has_numbers = any(s.replace('.', '').replace('-', '').isdigit() for s in type_samples if s)
                
                if dn_has_types and type_has_numbers:
                    weld_header_positions['DN'], weld_header_positions['TYPE'] = weld_header_positions['TYPE'], weld_header_positions['DN']
            
            # /FLD와 TYPE 위치 검증 - /FLD에 타입 값이 있는지 확인
            if '/FLD' in weld_header_positions and 'TYPE' in weld_header_positions:
                fld_x = weld_header_positions['/FLD']
                type_x = weld_header_positions['TYPE']
                
                # 각 위치의 데이터 샘플 수집
                fld_samples = []
                type_samples = []
                sample_count = 0
                
                for x, y, txt in all_texts:
                    if y < no_y and abs(x - no_x) <= 8 and txt.isdigit() and sample_count < 3:
                        sample_count += 1
                        # /FLD 위치의 데이터
                        for x2, y2, txt2 in all_texts:
                            if abs(y2 - y) <= 4 and abs(x2 - fld_x) <= 8 and txt2:
                                fld_samples.append(txt2.upper())
                                break
                        # TYPE 위치의 데이터
                        for x2, y2, txt2 in all_texts:
                            if abs(y2 - y) <= 4 and abs(x2 - type_x) <= 8 and txt2:
                                type_samples.append(txt2.upper())
                                break
                
                # /FLD 위치에 타입 값(BW, SW 등)이 있고, TYPE 위치에 S/F가 있으면 바꾸기
                fld_has_types = any(s in ['BW', 'SW', 'FW', 'TH'] for s in fld_samples if s)
                type_has_sf = any(s in ['S', 'F', 'SW', 'FW', 'SHOP', 'FIELD'] for s in type_samples if s)
                
                if fld_has_types and type_has_sf:
                    weld_header_positions['/FLD'], weld_header_positions['TYPE'] = weld_header_positions['TYPE'], weld_header_positions['/FLD']
        
        # 최종적으로 4개 헤더를 모두 찾지 못한 경우 이 테이블 건너뛰기
        required_headers = ['NO', '/FLD', 'DN', 'TYPE']
        missing_headers = [h for h in required_headers if h not in weld_header_positions]
        
        if missing_headers:
            continue
        
        # 모든 텍스트를 Y좌표로 정렬
        all_texts = []
        for e in msp.query('TEXT MTEXT'):
            txt = get_text(e).strip()
            x, y = get_xy(e)
            if txt:
                all_texts.append((x, y, txt))
        
        all_texts.sort(key=lambda t: -t[1])  # Y좌표 내림차순 정렬
        
        # NO 아래의 데이터 읽기
        weld_rows = []
        processed_nos = {}  # 처리된 NO 추적
        
        for x, y, txt in all_texts:
            # NO 헤더 아래에서만 검색
            if y >= no_y:
                continue
            
            # NO 열에서 숫자 찾기 (X 허용 범위 확대: ±8)
            if abs(x - no_x) <= 8 and txt.isdigit():  # X 범위를 ±5에서 ±8로 확대
                # 이미 처리된 NO는 스킵
                if txt in processed_nos:
                    continue
                
                # 현재 행의 데이터 읽기
                row_data = {'NO': txt}
                
                # 첫 번째 줄 데이터 수집 - NO의 Y 좌표와 각 헤더의 X 좌표 교차점에서 데이터 찾기
                for hdr, hdr_x in weld_header_positions.items():
                    if hdr != 'NO':
                        found = False
                        # 해당 헤더의 X 위치와 NO의 Y 위치가 교차하는 지점의 텍스트 찾기
                        for x2, y2, txt2 in all_texts:
                            # NO와 같은 Y 좌표(±4mm)이고 헤더의 X 좌표(±8mm)에 있는 텍스트
                            if abs(y2 - y) <= 4 and abs(x2 - hdr_x) <= 8 and txt2:
                                row_data[hdr] = txt2
                                found = True
                                break
                        if not found:
                            # 범위를 넓혀서 다시 시도
                            for x2, y2, txt2 in all_texts:
                                if abs(y2 - y) <= 8 and abs(x2 - hdr_x) <= 15 and txt2:
                                    row_data[hdr] = txt2
                                    break
                
                # WELD TYPE 데이터 정리 - "FW 350 350" → "FW", "350", "BW" 처리
                fld_value = row_data.get('/FLD', '')
                dn_value = row_data.get('DN', '')
                type_value = row_data.get('TYPE', '')
                
                # process_weld_type_data 함수를 사용하여 데이터 정리
                fld_value, dn_value, type_value = process_weld_type_data(fld_value, dn_value, type_value)
                
                # 정리된 값을 다시 저장
                row_data['/FLD'] = fld_value
                row_data['DN'] = dn_value
                row_data['TYPE'] = type_value
                
                processed_nos[txt] = True
                
                # DN 값으로 MAT와 THK 찾기
                weld_dia = ''
                
                # DN을 인치로 변환
                if dn_value:
                    weld_dia = DN_TO_INCH.get(dn_value, '')
                    if not weld_dia:
                        # 테이블에 없으면 직접 계산 시도
                        try:
                            dn_num = float(dn_value)
                            weld_dia = f"{dn_num / 25.4:.2f}"  # mm to inch
                        except:
                            weld_dia = ''
                
                if dn_value and dn_value in size_mat_thk_mapping:
                    row_data['MAT'] = size_mat_thk_mapping[dn_value]['MAT']
                    row_data['THK'] = size_mat_thk_mapping[dn_value]['THK']
                else:
                    row_data['MAT'] = ''
                    row_data['THK'] = ''
                
                # Excel 데이터 생성 (DXF 헤더 → Excel 헤더 매핑)
                excel_row = {
                    'ISO DWG NO': isodwgno if isodwgno else '-',
                    'LINE NO': lineno if lineno else '-',
                    'WELD NO': row_data.get('NO', '') if row_data.get('NO', '') else '-',
                    'SHOP/FLD': row_data.get('/FLD', '') if row_data.get('/FLD', '') else '-',
                    'WELD BORE': row_data.get('DN', '') if row_data.get('DN', '') else '-',
                    'WELD TYPE': row_data.get('TYPE', '') if row_data.get('TYPE', '') else '-',
                    'WELD MATERIAL': row_data.get('MAT', '-'),
                    'WELD THK': row_data.get('THK', '-'),
                    'WELDING DIA': weld_dia if weld_dia else '-'
                }
                
                all_weld_data.append(excel_row)

# 5. Excel 파일 저장
if all_weld_data:
    # Excel 워크북 생성
    wb = Workbook()
    
    # 기본 시트 제거
    if 'Sheet' in wb.sheetnames:
        wb.remove(wb['Sheet'])
    
    # 헤더 정의 (WELDING DIA를 맨 뒤로 이동)
    headers = ['ISO DWG NO', 'LINE NO', 'WELD NO', 'SHOP/FLD', 
               'WELD BORE', 'WELD TYPE', 'WELD MATERIAL', 'WELD THK', 'WELDING DIA']
    
    # 헤더 스타일 (크기 12, 굵게, 중앙 정렬, 굵은 테두리)
    header_font = Font(size=12, bold=True)
    header_alignment = Alignment(horizontal='center', vertical='center')
    thick_border = Border(
        left=Side(style='thick'),
        right=Side(style='thick'),
        top=Side(style='thick'),
        bottom=Side(style='thick')
    )
    
    # 데이터 스타일 (크기 11, 중앙 정렬, 얇은 테두리)
    data_font = Font(size=11)
    data_alignment = Alignment(horizontal='center', vertical='center')
    thin_border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )
    
    # 1. 전체 데이터 시트
    ws_all = wb.create_sheet("ALL_WELD")
    
    # 헤더 작성
    for col, header in enumerate(headers, 1):
        cell = ws_all.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.alignment = header_alignment
        cell.border = thick_border
    
    # 데이터 작성
    for row_idx, data in enumerate(all_weld_data, 2):
        for col_idx, header in enumerate(headers, 1):
            value = data.get(header, '')
            # 빈 값이면 '-'로 표시
            if value == '' or value is None:
                value = '-'
            cell = ws_all.cell(row=row_idx, column=col_idx, value=value)
            cell.font = data_font
            cell.alignment = data_alignment
            cell.border = thin_border
    
    # 2. SHOP/FLD별 시트 (FW, SW) - 기존 상세 데이터
    fw_data = [d for d in all_weld_data if d.get('SHOP/FLD', '').upper() in ['F', 'FW', 'FIELD']]
    sw_data = [d for d in all_weld_data if d.get('SHOP/FLD', '').upper() in ['S', 'SW', 'SHOP']]
    
    # FW 시트 (기존 상세 데이터)
    if fw_data:
        ws_fw = wb.create_sheet("FW")
        # 헤더
        for col, header in enumerate(headers, 1):
            cell = ws_fw.cell(row=1, column=col, value=header)
            cell.font = header_font
            cell.alignment = header_alignment
            cell.border = thick_border
        # 데이터
        for row_idx, data in enumerate(fw_data, 2):
            for col_idx, header in enumerate(headers, 1):
                value = data.get(header, '')
                # 빈 값이면 '-'로 표시
                if value == '' or value is None:
                    value = '-'
                cell = ws_fw.cell(row=row_idx, column=col_idx, value=value)
                cell.font = data_font
                cell.alignment = data_alignment
                cell.border = thin_border
    
    # SW 시트 (기존 상세 데이터)
    if sw_data:
        ws_sw = wb.create_sheet("SW")
        # 헤더
        for col, header in enumerate(headers, 1):
            cell = ws_sw.cell(row=1, column=col, value=header)
            cell.font = header_font
            cell.alignment = header_alignment
            cell.border = thick_border
        # 데이터
        for row_idx, data in enumerate(sw_data, 2):
            for col_idx, header in enumerate(headers, 1):
                value = data.get(header, '')
                # 빈 값이면 '-'로 표시
                if value == '' or value is None:
                    value = '-'
                cell = ws_sw.cell(row=row_idx, column=col_idx, value=value)
                cell.font = data_font
                cell.alignment = data_alignment
                cell.border = thin_border
    
    # 2-1. SW TOTAL 시트 (그룹화된 데이터)
    if sw_data:
        ws_sw_total = wb.create_sheet("SW TOTAL")
        
        # SW 데이터 그룹화
        sw_groups = {}
        for data in sw_data:
            # 그룹 키 생성 (SHOP/FLD, WELD BORE, WELD TYPE, WELD MATERIAL, WELD THK)
            group_key = (
                data.get('SHOP/FLD', ''),
                data.get('WELD BORE', ''),
                data.get('WELD TYPE', ''),
                data.get('WELD MATERIAL', ''),
                data.get('WELD THK', '')
            )
            
            if group_key not in sw_groups:
                sw_groups[group_key] = {
                    'count': 0,
                    'welding_dia_sum': 0.0,
                    'items': []
                }
            
            sw_groups[group_key]['count'] += 1
            sw_groups[group_key]['items'].append(data)
            
            # WELDING DIA 합산 (인치 값을 float로 변환)
            welding_dia = data.get('WELDING DIA', '')
            if welding_dia and welding_dia != '-':
                try:
                    # " 기호 제거하고 float로 변환
                    dia_value = float(welding_dia.replace('"', '').strip())
                    sw_groups[group_key]['welding_dia_sum'] += dia_value
                except:
                    pass
        
        # SW TOTAL 헤더
        sw_total_headers = ['SHOP/FLD', 'WELD BORE', 'WELD TYPE', 'WELD MATERIAL', 
                           'WELD THK', 'WELDING DIA', 'WELD POINT']
        
        # 헤더 작성
        for col, header in enumerate(sw_total_headers, 1):
            cell = ws_sw_total.cell(row=1, column=col, value=header)
            cell.font = header_font
            cell.alignment = header_alignment
            cell.border = thick_border
        
        # 그룹화된 데이터 작성
        row_idx = 2
        total_welding_dia = 0.0
        total_weld_point = 0
        
        for group_key, group_info in sorted(sw_groups.items()):
            # 각 컬럼 데이터
            shop_fld, weld_bore, weld_type, weld_material, weld_thk = group_key
            
            # WELDING DIA 포맷팅
            welding_dia_str = f"{group_info['welding_dia_sum']:.2f}" if group_info['welding_dia_sum'] > 0 else "-"
            
            # 데이터 행 작성
            row_data = [
                shop_fld if shop_fld else '-',
                weld_bore if weld_bore else '-',
                weld_type if weld_type else '-',
                weld_material if weld_material else '-',
                weld_thk if weld_thk else '-',
                welding_dia_str,
                group_info['count']  # WELD POINT
            ]
            
            for col_idx, value in enumerate(row_data, 1):
                cell = ws_sw_total.cell(row=row_idx, column=col_idx, value=value)
                cell.font = data_font
                cell.alignment = data_alignment
                cell.border = thin_border
            
            # 합계 누적
            total_welding_dia += group_info['welding_dia_sum']
            total_weld_point += group_info['count']
            
            row_idx += 1
        
        # 합계 행 추가
        cell = ws_sw_total.cell(row=row_idx, column=1, value="TOTAL")
        cell.font = Font(size=12, bold=True)
        cell.alignment = header_alignment
        cell.border = thick_border
        
        # 빈 셀들
        for col in range(2, 6):
            cell = ws_sw_total.cell(row=row_idx, column=col, value="-")
            cell.border = thick_border
        
        # WELDING DIA 합계
        cell = ws_sw_total.cell(row=row_idx, column=6, value=f"{total_welding_dia:.2f}")
        cell.font = Font(size=12, bold=True)
        cell.alignment = header_alignment
        cell.border = thick_border
        
        # WELD POINT 합계
        cell = ws_sw_total.cell(row=row_idx, column=7, value=total_weld_point)
        cell.font = Font(size=12, bold=True)
        cell.alignment = header_alignment
        cell.border = thick_border
    
    # 2-2. FW TOTAL 시트 (그룹화된 데이터)
    if fw_data:
        ws_fw_total = wb.create_sheet("FW TOTAL")
        
        # FW 데이터 그룹화
        fw_groups = {}
        for data in fw_data:
            # 그룹 키 생성 (SHOP/FLD, WELD BORE, WELD TYPE, WELD MATERIAL, WELD THK)
            group_key = (
                data.get('SHOP/FLD', ''),
                data.get('WELD BORE', ''),
                data.get('WELD TYPE', ''),
                data.get('WELD MATERIAL', ''),
                data.get('WELD THK', '')
            )
            
            if group_key not in fw_groups:
                fw_groups[group_key] = {
                    'count': 0,
                    'welding_dia_sum': 0.0,
                    'items': []
                }
            
            fw_groups[group_key]['count'] += 1
            fw_groups[group_key]['items'].append(data)
            
            # WELDING DIA 합산 (인치 값을 float로 변환)
            welding_dia = data.get('WELDING DIA', '')
            if welding_dia and welding_dia != '-':
                try:
                    # " 기호 제거하고 float로 변환
                    dia_value = float(welding_dia.replace('"', '').strip())
                    fw_groups[group_key]['welding_dia_sum'] += dia_value
                except:
                    pass
        
        # FW TOTAL 헤더
        fw_total_headers = ['SHOP/FLD', 'WELD BORE', 'WELD TYPE', 'WELD MATERIAL', 
                           'WELD THK', 'WELDING DIA', 'WELD POINT']
        
        # 헤더 작성
        for col, header in enumerate(fw_total_headers, 1):
            cell = ws_fw_total.cell(row=1, column=col, value=header)
            cell.font = header_font
            cell.alignment = header_alignment
            cell.border = thick_border
        
        # 그룹화된 데이터 작성
        row_idx = 2
        total_welding_dia = 0.0
        total_weld_point = 0
        
        for group_key, group_info in sorted(fw_groups.items()):
            # 각 컬럼 데이터
            shop_fld, weld_bore, weld_type, weld_material, weld_thk = group_key
            
            # WELDING DIA 포맷팅
            welding_dia_str = f"{group_info['welding_dia_sum']:.2f}" if group_info['welding_dia_sum'] > 0 else "-"
            
            # 데이터 행 작성
            row_data = [
                shop_fld if shop_fld else '-',
                weld_bore if weld_bore else '-',
                weld_type if weld_type else '-',
                weld_material if weld_material else '-',
                weld_thk if weld_thk else '-',
                welding_dia_str,
                group_info['count']  # WELD POINT
            ]
            
            for col_idx, value in enumerate(row_data, 1):
                cell = ws_fw_total.cell(row=row_idx, column=col_idx, value=value)
                cell.font = data_font
                cell.alignment = data_alignment
                cell.border = thin_border
            
            # 합계 누적
            total_welding_dia += group_info['welding_dia_sum']
            total_weld_point += group_info['count']
            
            row_idx += 1
        
        # 합계 행 추가
        cell = ws_fw_total.cell(row=row_idx, column=1, value="TOTAL")
        cell.font = Font(size=12, bold=True)
        cell.alignment = header_alignment
        cell.border = thick_border
        
        # 빈 셀들
        for col in range(2, 6):
            cell = ws_fw_total.cell(row=row_idx, column=col, value="-")
            cell.border = thick_border
        
        # WELDING DIA 합계
        cell = ws_fw_total.cell(row=row_idx, column=6, value=f"{total_welding_dia:.2f}")
        cell.font = Font(size=12, bold=True)
        cell.alignment = header_alignment
        cell.border = thick_border
        
        # WELD POINT 합계
        cell = ws_fw_total.cell(row=row_idx, column=7, value=total_weld_point)
        cell.font = Font(size=12, bold=True)
        cell.alignment = header_alignment
        cell.border = thick_border
    
    # 3. MAT 그룹별 시트
    mat_groups = {}
    for data in all_weld_data:
        mat_value = data.get('WELD MATERIAL', '')
        if mat_value and mat_value != '-':
            group_name = get_mat_group(mat_value)
            if group_name not in mat_groups:
                mat_groups[group_name] = []
            mat_groups[group_name].append(data)
    
    # 각 MAT 그룹별로 시트 생성
    for group_name, group_data in sorted(mat_groups.items()):
        # 시트명 길이 제한 (31자)
        sheet_name = f"MAT_{group_name}"[:31]
        ws_mat = wb.create_sheet(sheet_name)
        
        # 헤더
        for col, header in enumerate(headers, 1):
            cell = ws_mat.cell(row=1, column=col, value=header)
            cell.font = header_font
            cell.alignment = header_alignment
            cell.border = thick_border
        
        # 데이터 (SW/FW 순서로 정렬, 그 다음 MAT별로 정렬)
        def sort_key(row):
            # SHOP/FLD 값을 숫자로 변환 (SW=0, FW=1, 기타=2)
            shop_fld = row.get('SHOP/FLD', '').upper()
            if shop_fld in ['S', 'SW', 'SHOP']:
                priority = 0
            elif shop_fld in ['F', 'FW', 'FIELD']:
                priority = 1
            else:
                priority = 2
            # (우선순위, MAT값)으로 정렬
            return (priority, row.get('WELD MATERIAL', ''))
        
        sorted_data = sorted(group_data, key=sort_key)
        
        # SW/FW 구분선 찾기
        sw_count = 0
        fw_start_row = 2  # 헤더 다음 행
        
        for row_idx, data in enumerate(sorted_data, 2):
            shop_fld = data.get('SHOP/FLD', '').upper()
            if shop_fld in ['S', 'SW', 'SHOP']:
                sw_count += 1
            elif sw_count > 0 and shop_fld in ['F', 'FW', 'FIELD']:
                fw_start_row = row_idx
                break
            
            for col_idx, header in enumerate(headers, 1):
                value = data.get(header, '')
                # 빈 값이면 '-'로 표시
                if value == '' or value is None:
                    value = '-'
                cell = ws_mat.cell(row=row_idx, column=col_idx, value=value)
                cell.font = data_font
                cell.alignment = data_alignment
                cell.border = thin_border
        
        # SW와 FW 사이에 빈 줄 추가 (선택사항)
        if sw_count > 0 and fw_start_row > sw_count + 2:
            # 빈 줄에 구분 표시
            cell = ws_mat.cell(row=fw_start_row-1, column=1, value="--- Field Weld ---")
            cell.font = Font(size=11, italic=True)
            cell.alignment = Alignment(horizontal='center')
            # 빈 줄에도 테두리 적용
            for col in range(1, len(headers) + 1):
                cell = ws_mat.cell(row=fw_start_row-1, column=col)
                if col == 1:
                    cell.border = thin_border
                else:
                    cell.border = thin_border
                    cell.value = "-"
    
    # 모든 시트의 컬럼 너비 자동 조정
    for sheet in wb.worksheets:
        for column in sheet.columns:
            max_length = 0
            column_letter = get_column_letter(column[0].column)
            
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            
            adjusted_width = (max_length + 2) * 1.2
            sheet.column_dimensions[column_letter].width = adjusted_width
    
    # 파일 저장
    wb.save(excel_path)
else:
    print("*** 추출된 WELD 데이터가 없습니다 ***")