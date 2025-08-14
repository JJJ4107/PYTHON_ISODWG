import os
import re
import ezdxf
import tkinter as tk
from tkinter import filedialog
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

# Rating to Schedule 변환 테이블
RATING_TO_SCH = {
    '#150': {'CS': 'STD', 'SS': '10S'},
    '#300': {'CS': 'STD', 'SS': '10S'},
    '#600': {'CS': 'XS', 'SS': '40S'},
    '#900': {'CS': 'XXS', 'SS': '80S'},
    '#1500': {'CS': 'XXS', 'SS': '80S'},
    '#2500': {'CS': 'XXS', 'SS': '80S'},
    '#3000': {'CS': '160', 'SS': '80S'},
    '#6000': {'CS': 'XXS', 'SS': '80S'},
}

def get_thickness_from_thk(thk_value):
    """THK 값에서 두께(mm) 추출"""
    if not thk_value or thk_value == '-':
        return 6  # 기본값
    
    # AWT.48 형태에서 숫자 추출
    match = re.search(r'AWT\.(\d+)', thk_value)
    if match:
        return int(match.group(1))
    
    # SCH 형태에서 추정 (대략적인 값)
    sch_thickness = {
        'STD': 6, 'XS': 10, 'XXS': 15,
        'SCH10': 3, 'SCH20': 4, 'SCH30': 5,
        'SCH40': 6, 'SCH60': 8, 'SCH80': 15,  # SCH80을 10에서 15로 수정
        'SCH100': 18, 'SCH120': 22, 'SCH140': 25,
        'SCH160': 28, '10S': 3, '40S': 6, '80S': 10
    }
    
    thk_upper = thk_value.upper()
    for sch, thick in sch_thickness.items():
        if sch in thk_upper:
            return thick
    
    # #3000, #6000 등의 경우 기본값
    if '#' in thk_value:
        return 15  # 기본 두께
    
    # 숫자만 있는 경우 (예: "10", "15.5" 등)
    try:
        return int(float(thk_value))
    except:
        pass
    
    return 6  # 기본값

def get_groove_type(thickness, weld_type):
    """두께와 용접 타입에 따른 그루브 타입 결정"""
    if weld_type.upper() in ['SW', 'FW']:
        return 'N/A'
    
    if thickness <= 3:
        return 'Square'
    elif thickness <= 6:
        return 'V-Groove'
    elif thickness <= 19:
        return 'Single V'
    elif thickness <= 38:
        return 'Double V'
    else:
        return 'Double U'

def calculate_deposition(dia_inch, thickness, groove_type):
    """용착량 계산 (kg/joint) - 간단한 추정"""
    try:
        dia = float(dia_inch.replace('"', ''))
        if groove_type == 'N/A':
            return 0
        
        # 인치를 mm로 변환
        dia_mm = dia * 25.4
        
        # 그루브 단면적 계산 (mm²) - 더 현실적인 추정
        if groove_type == 'Square':
            # Square groove: 단면적 = 두께 × 루트갭(3mm 가정)
            area = thickness * 3
        elif groove_type == 'V-Groove' or groove_type == 'Single V':
            # Single V (60도 가정): 단면적 = 0.5 × 두께²
            area = 0.5 * thickness * thickness
        elif groove_type == 'Double V':
            # Double V: 단면적 = 0.7 × 두께²
            area = 0.7 * thickness * thickness
        else:  # Double U
            # Double U: 단면적 = 0.6 × 두께²
            area = 0.6 * thickness * thickness
        
        # 용접부 길이 (원주) = π × 직경
        weld_length = 3.14159 * dia_mm
        
        # 체적 (mm³) = 단면적 × 길이
        volume_mm3 = area * weld_length
        
        # 체적을 cm³로 변환
        volume_cm3 = volume_mm3 / 1000
        
        # 무게 (kg) = 체적(cm³) × 밀도(7.85 g/cm³) ÷ 1000
        weight = volume_cm3 * 7.85 / 1000
        
        print(f"      - 용착량 계산:")
        print(f"        직경: {dia}\" = {dia_mm:.1f}mm")
        print(f"        두께: {thickness}mm")
        print(f"        그루브: {groove_type}")
        print(f"        단면적: {area:.1f}mm²")
        print(f"        원주: {weld_length:.1f}mm")
        print(f"        체적: {volume_cm3:.1f}cm³")
        print(f"        무게: {weight:.2f}kg")
        
        return round(weight, 2)
    except Exception as e:
        print(f"      - 용착량 계산 오류: {e}")
        return 0

def calculate_electrode(deposition):
    """용접봉 수량 계산 (kg) - 효율 60% 가정"""
    if deposition == 0:
        return 0
    return round(deposition / 0.6, 2)

def get_welding_material(mat_group, weld_type):
    """재질에 따른 용접재료 선택"""
    welding_materials = {
        'CS': 'E7018',
        'P1': 'E7018-A1',
        'P5': 'E8018-B2',
        'P11': 'E8018-B2',
        'P22': 'E9018-B3',
        'P91': 'E9015-B91',
        'P92': 'E9015-B92',
        'SS304': 'E308-16',
        'SS304L': 'E308L-16',
        'SS316': 'E316-16',
        'SS316L': 'E316L-16',
        'SS321': 'E347-16',
        'SS347': 'E347-16'
    }
    
    if weld_type.upper() in ['SW', 'FW']:
        return 'N/A'
    
    return welding_materials.get(mat_group, 'E7018')

def get_preheat_temp(mat_group, thickness):
    """재질과 두께에 따른 예열 온도 (°C)"""
    # ASME B31.1/B31.3 기준
    preheat_table = {
        'CS': {10: 0, 19: 10, 38: 95, 999: 150},
        'P1': {10: 0, 19: 10, 38: 120, 999: 175},
        'P5': {999: 200},
        'P11': {999: 200},
        'P22': {999: 250},
        'P91': {999: 200},
        'P92': {999: 200},
        'SS304': {999: 0},
        'SS304L': {999: 0},
        'SS316': {999: 0},
        'SS316L': {999: 0},
        'SS321': {999: 0},
        'SS347': {999: 0}
    }
    
    temps = preheat_table.get(mat_group, {999: 0})
    for thick_limit, temp in sorted(temps.items()):
        if thickness <= thick_limit:
            return temp
    return 0

def get_pwht_requirement(mat_group, thickness):
    """재질과 두께에 따른 PWHT 요구사항"""
    # ASME B31.1/B31.3 기준
    pwht_table = {
        'CS': 19,  # 19mm 초과 시 PWHT 필요
        'P1': 19,
        'P5': 0,   # 모든 두께에서 PWHT 필요
        'P11': 0,
        'P22': 0,
        'P91': 0,
        'P92': 0,
        'SS304': 999,  # PWHT 불필요
        'SS304L': 999,
        'SS316': 999,
        'SS316L': 999,
        'SS321': 999,
        'SS347': 999
    }
    
    limit = pwht_table.get(mat_group, 19)
    if thickness > limit:
        if mat_group.startswith('SS'):
            return 'N/A'
        elif mat_group in ['P91', 'P92']:
            return f'760°C x {max(1, thickness//25)}hr'
        elif mat_group in ['P5', 'P11', 'P22']:
            return f'705°C x {max(1, thickness//25)}hr'
        else:
            return f'620°C x {max(1, thickness//25)}hr'
    else:
        return 'N/R'  # Not Required

def get_nde_requirement(mat_group, weld_type, thickness, service='Normal'):
    """재질, 용접 타입, 두께에 따른 NDE 요구사항 결정 (ASME B31.1/B31.3 기준)"""
    # SW/FW는 일반적으로 Visual Inspection만
    if weld_type.upper() in ['SW', 'FW']:
        return 'VT 100%'
    
    # BW (Butt Weld)의 경우
    nde_requirements = {
        # 일반 탄소강
        'CS': {
            'Normal': {19: 'VT 100%', 38: 'RT 10%', 999: 'RT 100%'},
            'Severe': {10: 'RT 10%', 19: 'RT 100%', 999: 'RT 100%'}
        },
        # 저합금강
        'P1': {
            'Normal': {19: 'VT 100%', 38: 'RT 10%', 999: 'RT 100%'},
            'Severe': {0: 'RT 100%', 999: 'RT 100%'}
        },
        'P5': {
            'Normal': {0: 'RT 100%', 999: 'RT 100%'},
            'Severe': {0: 'RT 100%', 999: 'RT 100%'}
        },
        'P11': {
            'Normal': {0: 'RT 100%', 999: 'RT 100%'},
            'Severe': {0: 'RT 100%', 999: 'RT 100%'}
        },
        'P22': {
            'Normal': {0: 'RT 100%', 999: 'RT 100%'},
            'Severe': {0: 'RT 100%', 999: 'RT 100%'}
        },
        'P91': {
            'Normal': {0: 'RT 100% + PT', 999: 'RT 100% + PT'},
            'Severe': {0: 'RT 100% + UT', 999: 'RT 100% + UT'}
        },
        'P92': {
            'Normal': {0: 'RT 100% + PT', 999: 'RT 100% + PT'},
            'Severe': {0: 'RT 100% + UT', 999: 'RT 100% + UT'}
        }
    }
    
    # 스테인리스강은 기본적으로 RT 또는 PT
    if mat_group.startswith('SS'):
        if thickness <= 10:
            return 'PT 100%'
        else:
            return 'RT 100%'
    
    # 해당 재질의 NDE 요구사항 찾기
    mat_requirements = nde_requirements.get(mat_group, nde_requirements['CS'])
    service_requirements = mat_requirements.get(service, mat_requirements['Normal'])
    
    for thick_limit, nde in sorted(service_requirements.items()):
        if thickness <= thick_limit:
            return nde
    
    return 'VT 100%'  # 기본값

def calculate_welding_data(weld_bore, weld_material, weld_thk, weld_type, welding_dia):
    """용접 관련 데이터 계산"""
    # 재질 그룹 결정
    mat_group = get_mat_group(weld_material)
    
    # 두께 추출
    thickness = get_thickness_from_thk(weld_thk)
    pipe_thk_info = f"{thickness}mm"  # 기본값
    
    # #3000, #6000 등의 경우 Schedule 변환
    if '#' in weld_thk:
        rating = weld_thk.split()[0] if ' ' in weld_thk else weld_thk
        material_type = 'SS' if 'SS' in mat_group else 'CS'
        if rating in RATING_TO_SCH:
            sch = RATING_TO_SCH[rating].get(material_type, 'STD')
            # Schedule에서 두께 재계산
            sch_thickness = {
                'STD': 6, 'XS': 10, 'XXS': 15,
                '10S': 3, '40S': 6, '80S': 10,
                '160': 28  # 160을 20에서 28로 수정
            }
            thickness = sch_thickness.get(sch, thickness)
            pipe_thk_info = f"{thickness}mm (SCH {sch})"
    
    # 그루브 타입 결정
    groove_type = get_groove_type(thickness, weld_type)
    
    # 용착량 계산
    deposition = calculate_deposition(welding_dia, thickness, groove_type)
    
    # 용접봉 수량 계산
    electrode = calculate_electrode(deposition)
    
    # 용접재료 선택
    welding_mat = get_welding_material(mat_group, weld_type)
    
    # 예열 온도
    preheat = get_preheat_temp(mat_group, thickness)
    
    # PWHT 요구사항
    pwht = get_pwht_requirement(mat_group, thickness)
    
    # NDE 검사 요구사항
    nde = get_nde_requirement(mat_group, weld_type, thickness)
    
    return {
        'PIPE THK': pipe_thk_info,
        'GROOVE TYPE': groove_type,
        '용착량': f'{deposition}kg' if deposition > 0 else 'N/A',
        '용접봉수량': f'{electrode}kg' if electrode > 0 else 'N/A',
        '용접재료': welding_mat,
        'PREHEAT': f'{preheat}°C' if preheat > 0 else 'N/R',
        'PWHT': pwht,
        'NDE 검사': nde
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
                    print(f"    > SIZE '{size}' MAT 업데이트: '{existing_mat}' → '{new_mat}' (더 긴 텍스트)")
            else:
                print(f"    > SIZE '{size}' MAT 경고: 다른 값 발견 (기존: '{existing_mat}', 새값: '{new_mat}')")
        elif new_mat and not existing_mat:
            # 기존 MAT가 비어있으면 새 값으로 업데이트
            update_mat = True
        
        # THK 포함 관계 확인
        if new_thk and existing_thk:
            if new_thk in existing_thk or existing_thk in new_thk:
                if len(new_thk) > len(existing_thk):
                    update_thk = True
                    print(f"    > SIZE '{size}' THK 업데이트: '{existing_thk}' → '{new_thk}' (더 긴 텍스트)")
            else:
                print(f"    > SIZE '{size}' THK 경고: 다른 값 발견 (기존: '{existing_thk}', 새값: '{new_thk}')")
        elif new_thk and not existing_thk:
            # 기존 THK가 비어있으면 새 값으로 업데이트
            update_thk = True
        
        # 업데이트 필요한 경우만 수정
        if update_mat or update_thk:
            final_mat = new_mat if update_mat else existing_mat
            final_thk = new_thk if update_thk else existing_thk
            size_mat_thk_mapping[size] = {'MAT': final_mat, 'THK': final_thk}
    else:
        size_mat_thk_mapping[size] = {'MAT': new_mat if new_mat else '', 'THK': new_thk if new_thk else ''}
        print(f"    > SIZE '{size}' 매핑: MAT='{new_mat}', THK='{new_thk}'")

def process_weld_type_data(fld_value, dn_value, type_value):
    """WELD 데이터에서 /FLD, DN, TYPE 값을 정리하는 함수
    특히 "FW 350 350" 같은 패턴을 처리
    """
    # 원본 값 출력 (디버깅용)
    print(f"      원본 - /FLD: '{fld_value}', DN: '{dn_value}', TYPE: '{type_value}'")
    
    # TYPE에 DN 값(숫자)이 들어간 경우 처리
    if type_value and type_value.replace('.', '').replace('-', '').isdigit():
        # TYPE에 숫자가 있으면 DN이 잘못 들어간 것
        if not dn_value or dn_value == type_value:
            dn_value = type_value
            type_value = 'BW'  # 기본값으로 BW 설정
            print(f"      수정1 - TYPE에 DN 발견, BW로 변경")
    
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
                print(f"      수정2 - /FLD 분리: '{parts}' → FLD='{fld_value}', DN='{dn_value}', TYPE='{type_value}'")
    
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
    
    print(f"      최종 - /FLD: '{fld_value}', DN: '{dn_value}', TYPE: '{type_value}'")
    
    return fld_value, dn_value, type_value

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

# Excel 파일명 생성 (날짜시간 포함)
now = datetime.now()
datetime_str = now.strftime("%Y%m%d_%H%M%S")
excel_filename = f"TOTALWELD_{datetime_str}.xlsx"
excel_path = os.path.join(os.path.dirname(file_paths[0]), excel_filename)

# 전체 데이터를 저장할 리스트
all_weld_data = []

# 각 DXF 파일 처리
for file_path in file_paths:
    print(f"\n처리 중: {os.path.basename(file_path)}")
    
    # 파일별로 SIZE 매핑 초기화 (각 도면마다 새로운 매핑)
    size_mat_thk_mapping = {}
    
    try:
        doc = ezdxf.readfile(file_path)
        msp = doc.modelspace()
    except Exception as e:
        print(f"  - 파일 읽기 오류: {e}")
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
        print(f"  - LINE NO를 찾을 수 없습니다 (기본값 '-' 사용)")
    else:
        print(f"  - LINE NO: {lineno}")
    
    # 2. ISODWGNO 찾기
    isodwgno = None
    description = None  # DESCRIPTION 추가
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
                    # DESCRIPTION 찾기: ISODWGNO 위치에서 X-50~+50, Y+10~+45 범위
                    # X: x-50 ~ x+50 범위
                    # Y: y+10 ~ y+45 범위
                    for e2 in msp.query('TEXT MTEXT'):
                        txt2 = get_text(e2).strip()
                        x2, y2 = get_xy(e2)
                        # X: ISODWGNO x좌표에서 -50 ~ +50 범위 (총 100 범위)
                        # Y: ISODWGNO y좌표에서 +10 ~ +45 범위 (총 35 범위)
                        if (x - 50 <= x2 <= x + 50) and (y + 10 <= y2 <= y + 45) and txt2:
                            description = txt2
                            print(f"  - DESCRIPTION 발견 at ({x2:.1f}, {y2:.1f}): '{description}'")
                            break
                    break
    
    if not isodwgno:
        isodwgno = '-'
        print(f"  - ISO DWG NO를 찾을 수 없습니다 (기본값 '-' 사용)")
    else:
        print(f"  - ISO DWG NO: {isodwgno}")
    
    if not description:
        description = '-'
        print(f"  - DESCRIPTION을 찾을 수 없습니다 (기본값 '-' 사용)")
    else:
        print(f"  - DESCRIPTION: {description}")
    
    # 3. PT 테이블에서 SIZE-MAT-THK 매핑 구축
    print(f"\n  === SIZE-MAT-THK 매핑 구축 중 ===")
    
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
                                        print(f"    > PT {txt}: SIZE 2줄 결합 → '{size_value}'")
                                    else:
                                        print(f"    > PT {txt}: SIZE 2줄째 '{txt2}' 중복 (스킵)")
                                    break
                        
                        # MATERIAL 2줄 처리
                        if mat_value and 'MATERIAL' in header_positions:
                            mat_x = header_positions['MATERIAL']
                            for x2, y2, txt2 in all_texts:
                                if abs(x2 - mat_x) <= 4 and abs(y2 - check_y) <= 2 and txt2:
                                    if should_append_text(mat_value, txt2):
                                        mat_value = mat_value + ' ' + txt2
                                        print(f"    > PT {txt}: MATERIAL 2줄 결합 → '{mat_value}'")
                                    else:
                                        print(f"    > PT {txt}: MATERIAL 2줄째 '{txt2}' 중복 (스킵)")
                                    break
                        
                        # DESCRIPTION 2줄 처리
                        if desc_value and 'DESCRIPTION' in header_positions:
                            desc_x = header_positions['DESCRIPTION']
                            for x2, y2, txt2 in all_texts:
                                if abs(x2 - desc_x) <= 4 and abs(y2 - check_y) <= 2 and txt2:
                                    if should_append_text(desc_value, txt2):
                                        desc_value = desc_value + ' ' + txt2
                                        print(f"    > PT {txt}: DESCRIPTION 2줄 결합 → '{desc_value}'")
                                    else:
                                        print(f"    > PT {txt}: DESCRIPTION 2줄째 '{txt2}' 중복 (스킵)")
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
                            if desc_value:
                                # desc_value에서 x를 찾아 분리 (대소문자 구분 없이)
                                desc_has_x = False
                                desc_parts = []
                                
                                # x가 있는지 확인 (독립된 x 또는 끝에 있는 x)
                                if ' x ' in desc_value.lower() or desc_value.lower().endswith(' x'):
                                    desc_has_x = True
                                    # x로 분리 (끝에 있는 x도 처리)
                                    desc_parts = re.split(r'\s+[xX]\s*', desc_value)
                                elif 'x' in desc_value.lower():
                                    # x가 붙어있는 경우도 처리
                                    desc_has_x = True
                                    desc_parts = re.split(r'[xX]', desc_value)
                                
                                if desc_has_x and len(desc_parts) >= 2:
                                    thk1 = desc_parts[0].strip()
                                    thk2 = desc_parts[1].strip() if desc_parts[1].strip() else desc_parts[0].strip()
                                    
                                    # 각 SIZE별로 매핑 저장
                                    update_size_mapping(size1, mat_value, thk1, size_mat_thk_mapping)
                                    update_size_mapping(size2, mat_value, thk2, size_mat_thk_mapping)
                                else:
                                    # x가 없거나 분리가 안되면 전체 DESCRIPTION을 양쪽에 사용
                                    update_size_mapping(size1, mat_value, desc_value, size_mat_thk_mapping)
                                    update_size_mapping(size2, mat_value, desc_value, size_mat_thk_mapping)
                            else:
                                # DESCRIPTION이 없으면 빈 값으로
                                update_size_mapping(size1, mat_value, '', size_mat_thk_mapping)
                                update_size_mapping(size2, mat_value, '', size_mat_thk_mapping)
                    else:
                        # x가 없는 경우 (포함 관계 확인)
                        update_size_mapping(size_value, mat_value, desc_value, size_mat_thk_mapping)
    
    print(f"  - 이 파일의 SIZE 매핑: {len(size_mat_thk_mapping)}개")
    
    # 이 파일의 SIZE 매핑 정보 출력
    if size_mat_thk_mapping:
        print(f"\n  === 이 파일의 SIZE-MAT-THK 매핑 ===")
        for size, info in sorted(size_mat_thk_mapping.items()):
            print(f"    SIZE: {size} → MAT: {info['MAT']}, THK: {info['THK']}")
    
    # 4. NO/FLD/DN/TYPE 테이블 찾기
    print(f"\n  === WELD 테이블 검색 중 ===")
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
                print(f"  - NO 헤더 발견 (4개 헤더 모두 확인): ({x:.1f}, {y:.1f}) - '{txt}'")
            else:
                missing = [k for k, v in found_headers.items() if not v]
                print(f"  - NO 헤더 발견했으나 일부 헤더 누락 ({x:.1f}, {y:.1f}) - 누락: {missing}")
    
    print(f"  - 총 {len(no_headers)}개의 WELD 테이블 발견")
    
    # 각 NO 테이블 처리
    for no_idx, (no_x, no_y, no_txt) in enumerate(no_headers):
        print(f"\n  === WELD 테이블 {no_idx+1}/{len(no_headers)} 처리 중 ===")
        print(f"  - NO 헤더 위치: ({no_x:.1f}, {no_y:.1f})")
        print(f"  - NO 헤더 오른쪽(+X 방향)에서 다른 헤더 검색...")
        
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
        
        # 헤더 찾기
        print(f"  - NO 오른쪽에서 찾은 후보 헤더들:")
        for x, y, txt, txt_upper in header_candidates[:10]:  # 처음 10개만 출력
            print(f"    > X={x:.1f}, Y={y:.1f}: '{txt}'")
        
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
                            print(f"  - /FLD 헤더로 인식: X={x:.1f}, Text='{txt}'")
                    else:
                        weld_header_positions['/FLD'] = x
                        print(f"  - /FLD 헤더로 인식: X={x:.1f}, Text='{txt}'")
                    continue
            
            # DN 찾기 (숫자가 주로 오는 열)
            if 'DN' not in weld_header_positions:
                if txt_upper == 'DN' or txt_upper == 'SIZE' or txt_upper == 'BORE':
                    weld_header_positions['DN'] = x
                    print(f"  - DN 헤더로 인식: X={x:.1f}, Text='{txt}'")
                    continue
            
            # TYPE 찾기 (BW, SW 등이 오는 열) - 엄격한 매칭
            if 'TYPE' not in weld_header_positions:
                # DN과 동일한 X 위치가 아닌 경우에만 TYPE으로 인식
                if 'DN' in weld_header_positions and abs(x - weld_header_positions['DN']) < 5:
                    # DN과 너무 가까우면 TYPE이 아닐 가능성이 높음
                    continue
                    
                if txt_upper == 'TYPE' or txt_upper == 'WLD TYPE' or txt_upper == 'WELD TYPE':
                    weld_header_positions['TYPE'] = x
                    print(f"  - TYPE 헤더로 인식: X={x:.1f}, Text='{txt}'")
                    continue
                elif txt_upper in ['WLD', 'WELD', 'CONNECTION', 'JOINT TYPE', 'WELD JOINT']:
                    weld_header_positions['TYPE'] = x
                    print(f"  - TYPE 헤더로 인식: X={x:.1f}, Text='{txt}'")
                    continue
        
        print(f"  - 찾은 헤더들: {list(weld_header_positions.keys())}")
        
        # 헤더 위치 정보 출력
        for hdr, hdr_x in weld_header_positions.items():
            print(f"    > {hdr} 헤더 X 위치: {hdr_x:.1f}")
        
        # 4개 헤더를 모두 찾지 못한 경우 이 테이블 건너뛰기
        required_headers = ['NO', '/FLD', 'DN', 'TYPE']
        missing_headers = [h for h in required_headers if h not in weld_header_positions]
        
        if missing_headers:
            print(f"  - 경고: 필수 헤더 누락 {missing_headers}. 이 테이블은 건너뜁니다.")
            continue
        
        # 헤더를 못 찾은 경우 디버깅 정보 출력 및 추가 시도
        if len(weld_header_positions) < 4:
            print(f"  - 경고: 일부 헤더를 찾지 못함. NO 헤더 오른쪽 텍스트 확인:")
            nearby_texts = []
            for e in msp.query('TEXT MTEXT'):
                txt = get_text(e).strip()
                x, y = get_xy(e)
                # NO 헤더와 같은 높이(±25mm)이고 NO보다 오른쪽에 있는 텍스트만
                if abs(y - no_y) <= 25 and x > no_x and txt:
                    nearby_texts.append((x, y, txt))
            
            # X 좌표로 정렬하여 출력
            nearby_texts.sort(key=lambda t: t[0])
            print(f"  - NO 헤더 오른쪽에 있는 텍스트들:")
            for x, y, txt in nearby_texts[:20]:  # 처음 20개만 출력
                print(f"    > ({x:.1f}, {y:.1f}): '{txt}'")
            
            # /FLD 헤더가 없는 경우 S, F 패턴으로 위치 추정
            if '/FLD' not in weld_header_positions:
                print(f"  - /FLD 헤더를 찾지 못함. S/F 패턴으로 위치 추정 중...")
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
                    print(f"  - /FLD 헤더 위치 추정: X={best_x:.1f}")
            
            # TYPE 헤더가 없는 경우 BW, SW 패턴으로 위치 추정
            if 'TYPE' not in weld_header_positions:
                print(f"  - TYPE 헤더를 찾지 못함. BW/SW 패턴으로 위치 추정 중...")
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
                    print(f"  - TYPE 헤더 위치 추정: X={best_x:.1f}")
            
            # DN 헤더가 없는 경우 NO 오른쪽의 숫자 패턴으로 DN 위치 추정
            if 'DN' not in weld_header_positions:
                print(f"  - DN 헤더를 찾지 못함. NO 데이터 행에서 DN 위치 추정 중...")
                
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
                print(f"  - DN과 TYPE 헤더 위치 검증 중...")
                dn_x = weld_header_positions['DN']
                type_x = weld_header_positions['TYPE']
                
                # DN과 TYPE의 X 위치가 동일하거나 너무 가까운 경우
                if abs(dn_x - type_x) < 10:
                    print(f"  - 경고: DN(X={dn_x:.1f})과 TYPE(X={type_x:.1f}) 위치가 너무 가깝습니다!")
                    print(f"  - TYPE 위치를 다시 찾습니다...")
                    
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
                        print(f"  - TYPE 헤더 위치 재설정: X={best_x:.1f}")
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
                
                print(f"    > DN 위치(X={dn_x:.1f}) 샘플: {dn_samples[:3]}")
                print(f"    > TYPE 위치(X={type_x:.1f}) 샘플: {type_samples[:3]}")
                
                # DN 위치에 타입 값(BW, SW 등)이 있고, TYPE 위치에 숫자가 있으면 바꾸기
                dn_has_types = any(s in ['BW', 'SW', 'FW', 'TH'] for s in dn_samples if s)
                type_has_numbers = any(s.replace('.', '').replace('-', '').isdigit() for s in type_samples if s)
                
                if dn_has_types and type_has_numbers:
                    print(f"  - 경고: DN과 TYPE 위치가 바뀐 것으로 판단됨. 위치 교체!")
                    weld_header_positions['DN'], weld_header_positions['TYPE'] = weld_header_positions['TYPE'], weld_header_positions['DN']
                    print(f"    > 수정된 DN 위치: X={weld_header_positions['DN']:.1f}")
                    print(f"    > 수정된 TYPE 위치: X={weld_header_positions['TYPE']:.1f}")
            
            # /FLD와 TYPE 위치 검증 - /FLD에 타입 값이 있는지 확인
            if '/FLD' in weld_header_positions and 'TYPE' in weld_header_positions:
                print(f"  - /FLD와 TYPE 헤더 위치 검증 중...")
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
                
                print(f"    > /FLD 위치(X={fld_x:.1f}) 샘플: {fld_samples[:3]}")
                print(f"    > TYPE 위치(X={type_x:.1f}) 샘플: {type_samples[:3]}")
                
                # /FLD 위치에 타입 값(BW, SW 등)이 있고, TYPE 위치에 S/F가 있으면 바꾸기
                fld_has_types = any(s in ['BW', 'SW', 'FW', 'TH'] for s in fld_samples if s)
                type_has_sf = any(s in ['S', 'F', 'SW', 'FW', 'SHOP', 'FIELD'] for s in type_samples if s)
                
                if fld_has_types and type_has_sf:
                    print(f"  - 경고: /FLD와 TYPE 위치가 바뀐 것으로 판단됨. 위치 교체!")
                    weld_header_positions['/FLD'], weld_header_positions['TYPE'] = weld_header_positions['TYPE'], weld_header_positions['/FLD']
                    print(f"    > 수정된 /FLD 위치: X={weld_header_positions['/FLD']:.1f}")
                    print(f"    > 수정된 TYPE 위치: X={weld_header_positions['TYPE']:.1f}")
        
        # 최종적으로 4개 헤더를 모두 찾지 못한 경우 이 테이블 건너뛰기
        required_headers = ['NO', '/FLD', 'DN', 'TYPE']
        missing_headers = [h for h in required_headers if h not in weld_header_positions]
        
        if missing_headers:
            print(f"  - 최종 경고: 필수 헤더 누락 {missing_headers}. 이 테이블은 건너뜁니다.")
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
                
                print(f"  - NO {txt} 발견 at ({x:.1f}, {y:.1f})")
                
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
                                print(f"    > {hdr} (X={hdr_x:.1f}): '{txt2}'")
                                found = True
                                break
                        if not found:
                            print(f"    > {hdr} (헤더 X={hdr_x:.1f}): 데이터 없음 (Y={y:.1f}±4mm, X={hdr_x:.1f}±8mm 범위)")
                            # 범위를 넓혀서 다시 시도
                            for x2, y2, txt2 in all_texts:
                                if abs(y2 - y) <= 8 and abs(x2 - hdr_x) <= 15 and txt2:
                                    row_data[hdr] = txt2
                                    print(f"    > {hdr}: '{txt2}' 찾음 (확장 범위: {x2:.1f}, {y2:.1f})")
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
                    print(f"    > DN '{dn_value}' → WELDING DIA: '{weld_dia}\"'")
                
                if dn_value and dn_value in size_mat_thk_mapping:
                    row_data['MAT'] = size_mat_thk_mapping[dn_value]['MAT']
                    row_data['THK'] = size_mat_thk_mapping[dn_value]['THK']
                    print(f"    > DN '{dn_value}' → MAT: '{row_data['MAT']}', THK: '{row_data['THK']}'")
                else:
                    row_data['MAT'] = ''
                    row_data['THK'] = ''
                    if dn_value:
                        print(f"    > DN '{dn_value}'에 대한 매핑 없음")
                
                # 용접 관련 데이터 계산
                welding_data = calculate_welding_data(
                    row_data.get('DN', ''),
                    row_data.get('MAT', ''),
                    row_data.get('THK', ''),
                    row_data.get('TYPE', ''),
                    weld_dia
                )
                
                # Excel 데이터 생성 전 디버깅
                print(f"  - Excel 행 생성:")
                print(f"    > ISO DWG NO: {isodwgno}")
                print(f"    > LINE NO: {lineno}")
                print(f"    > DESCRIPTION: {description}")
                print(f"    > WELD NO: {row_data.get('NO', '')}")
                print(f"    > SHOP/FLD: {row_data.get('/FLD', '')}")
                print(f"    > WELD BORE: {row_data.get('DN', '')}")
                print(f"    > WELD TYPE: {row_data.get('TYPE', '')}")
                print(f"    > WELD MATERIAL: {row_data.get('MAT', '')}")
                print(f"    > WELD THK: {row_data.get('THK', '')}")
                print(f"    > WELDING DIA: {weld_dia}")
                print(f"    > PIPE THK: {welding_data['PIPE THK']}")
                print(f"    > GROOVE TYPE: {welding_data['GROOVE TYPE']}")
                print(f"    > 용착량: {welding_data['용착량']}")
                print(f"    > 용접봉수량: {welding_data['용접봉수량']}")
                print(f"    > 용접재료: {welding_data['용접재료']}")
                print(f"    > PREHEAT: {welding_data['PREHEAT']}")
                print(f"    > PWHT: {welding_data['PWHT']}")
                print(f"    > NDE 검사: {welding_data['NDE 검사']}")
                
                # Excel 데이터 생성 (DXF 헤더 → Excel 헤더 매핑)
                excel_row = {
                    'ISO DWG NO': isodwgno if isodwgno else '-',
                    'LINE NO': lineno if lineno else '-',
                    'DESCRIPTION': description if description else '-',  # LINE NO 뒤로 이동
                    'WELD NO': row_data.get('NO', '') if row_data.get('NO', '') else '-',
                    'SHOP/FLD': row_data.get('/FLD', '') if row_data.get('/FLD', '') else '-',
                    'WELD BORE': row_data.get('DN', '') if row_data.get('DN', '') else '-',
                    'WELD TYPE': row_data.get('TYPE', '') if row_data.get('TYPE', '') else '-',
                    'WELD MATERIAL': row_data.get('MAT', '-'),
                    'WELD THK': row_data.get('THK', '-'),
                    'WELDING DIA': weld_dia if weld_dia else '-',
                    'PIPE THK': welding_data['PIPE THK'],
                    'GROOVE TYPE': welding_data['GROOVE TYPE'],
                    '용착량': welding_data['용착량'],
                    '용접봉수량': welding_data['용접봉수량'],
                    '용접재료': welding_data['용접재료'],
                    'PREHEAT': welding_data['PREHEAT'],
                    'PWHT': welding_data['PWHT'],
                    'NDE 검사': welding_data['NDE 검사']
                }
                
                all_weld_data.append(excel_row)
        
        print(f"  - 테이블 {no_idx+1}에서 추출된 WELD 데이터: {len(processed_nos)}행")
    
    # 파일별 처리 완료 메시지
    file_weld_count = len([d for d in all_weld_data if d['ISO DWG NO'] == isodwgno and d['LINE NO'] == lineno])
    print(f"\n  === 파일 처리 완료: {os.path.basename(file_path)} ===")
    print(f"  - 이 파일에서 추출된 WELD 데이터: {file_weld_count}행")
    print(f"  - ISO DWG NO: {isodwgno}")
    print(f"  - LINE NO: {lineno}")
    print(f"  - DESCRIPTION: {description}")
    print(f"  - 이 파일의 SIZE 매핑 수: {len(size_mat_thk_mapping)}개")
    print(f"  - 전체 누적 WELD 데이터: {len(all_weld_data)}행")

# 5. Excel 파일 저장
print(f"\n=== 전체 처리 결과 ===")
print(f"처리된 파일 수: {len(file_paths)}")
print(f"추출된 총 WELD 데이터 행 수: {len(all_weld_data)}")

if all_weld_data:
    # Excel 워크북 생성
    wb = Workbook()
    
    # 기본 시트 제거
    if 'Sheet' in wb.sheetnames:
        wb.remove(wb['Sheet'])
    
    # 헤더 정의 (DESCRIPTION을 LINE NO 뒤로 이동, 용접 관련 정보 추가)
    headers = ['ISO DWG NO', 'LINE NO', 'DESCRIPTION', 'WELD NO', 'SHOP/FLD', 
               'WELD BORE', 'WELD TYPE', 'WELD MATERIAL', 'WELD THK', 'WELDING DIA',
               'PIPE THK', 'GROOVE TYPE', '용착량', '용접봉수량', '용접재료', 'PREHEAT', 'PWHT', 'NDE 검사']
    
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
        print(f"  - FW 시트 생성: {len(fw_data)}개 데이터")
    
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
        print(f"  - SW 시트 생성: {len(sw_data)}개 데이터")
    
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
                    'deposition_per_joint': 0.0,
                    'electrode_per_joint': 0.0,
                    'welding_material': '',
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
            
            # 용착량, 용접봉수량, 용접재료 저장 (첫 번째 아이템 기준)
            if sw_groups[group_key]['count'] == 1:
                deposition = data.get('용착량', '0kg')
                electrode = data.get('용접봉수량', '0kg')
                try:
                    sw_groups[group_key]['deposition_per_joint'] = float(deposition.replace('kg', '').replace('N/A', '0'))
                    sw_groups[group_key]['electrode_per_joint'] = float(electrode.replace('kg', '').replace('N/A', '0'))
                except:
                    pass
                sw_groups[group_key]['welding_material'] = data.get('용접재료', '-')
        
        # SW TOTAL 헤더
        sw_total_headers = ['SHOP/FLD', 'WELD BORE', 'WELD TYPE', 'WELD MATERIAL', 
                           'WELD THK', 'WELDING DIA', 'WELD POINT', '용착량 TOTAL', 
                           '용접봉수량 TOTAL', '용접재료']
        
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
        total_deposition = 0.0
        total_electrode = 0.0
        
        for group_key, group_info in sorted(sw_groups.items()):
            # 각 컬럼 데이터
            shop_fld, weld_bore, weld_type, weld_material, weld_thk = group_key
            
            # WELDING DIA 포맷팅
            welding_dia_str = f"{group_info['welding_dia_sum']:.2f}" if group_info['welding_dia_sum'] > 0 else "-"
            
            # 용착량/용접봉수량 총합 계산
            deposition_total = group_info['deposition_per_joint'] * group_info['count']
            electrode_total = group_info['electrode_per_joint'] * group_info['count']
            
            # 데이터 행 작성
            row_data = [
                shop_fld if shop_fld else '-',
                weld_bore if weld_bore else '-',
                weld_type if weld_type else '-',
                weld_material if weld_material else '-',
                weld_thk if weld_thk else '-',
                welding_dia_str,
                group_info['count'],  # WELD POINT
                f"{deposition_total:.2f}kg" if deposition_total > 0 else "-",
                f"{electrode_total:.2f}kg" if electrode_total > 0 else "-",
                group_info['welding_material']
            ]
            
            for col_idx, value in enumerate(row_data, 1):
                cell = ws_sw_total.cell(row=row_idx, column=col_idx, value=value)
                cell.font = data_font
                cell.alignment = data_alignment
                cell.border = thin_border
            
            # 합계 누적
            total_welding_dia += group_info['welding_dia_sum']
            total_weld_point += group_info['count']
            total_deposition += deposition_total
            total_electrode += electrode_total
            
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
        
        # 용착량 TOTAL 합계
        cell = ws_sw_total.cell(row=row_idx, column=8, value=f"{total_deposition:.2f}kg")
        cell.font = Font(size=12, bold=True)
        cell.alignment = header_alignment
        cell.border = thick_border
        
        # 용접봉수량 TOTAL 합계
        cell = ws_sw_total.cell(row=row_idx, column=9, value=f"{total_electrode:.2f}kg")
        cell.font = Font(size=12, bold=True)
        cell.alignment = header_alignment
        cell.border = thick_border
        
        # 용접재료 (TOTAL 행에는 '-' 표시)
        cell = ws_sw_total.cell(row=row_idx, column=10, value="-")
        cell.font = Font(size=12, bold=True)
        cell.alignment = header_alignment
        cell.border = thick_border
        
        print(f"  - SW TOTAL 시트 생성: {len(sw_groups)}개 그룹, 총 {total_weld_point}개 포인트")
        print(f"    > 총 용착량: {total_deposition:.2f}kg")
        print(f"    > 총 용접봉수량: {total_electrode:.2f}kg")
    
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
                    'deposition_per_joint': 0.0,
                    'electrode_per_joint': 0.0,
                    'welding_material': '',
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
            
            # 용착량, 용접봉수량, 용접재료 저장 (첫 번째 아이템 기준)
            if fw_groups[group_key]['count'] == 1:
                deposition = data.get('용착량', '0kg')
                electrode = data.get('용접봉수량', '0kg')
                try:
                    fw_groups[group_key]['deposition_per_joint'] = float(deposition.replace('kg', '').replace('N/A', '0'))
                    fw_groups[group_key]['electrode_per_joint'] = float(electrode.replace('kg', '').replace('N/A', '0'))
                except:
                    pass
                fw_groups[group_key]['welding_material'] = data.get('용접재료', '-')
        
        # FW TOTAL 헤더
        fw_total_headers = ['SHOP/FLD', 'WELD BORE', 'WELD TYPE', 'WELD MATERIAL', 
                           'WELD THK', 'WELDING DIA', 'WELD POINT', '용착량 TOTAL', 
                           '용접봉수량 TOTAL', '용접재료']
        
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
        total_deposition = 0.0
        total_electrode = 0.0
        
        for group_key, group_info in sorted(fw_groups.items()):
            # 각 컬럼 데이터
            shop_fld, weld_bore, weld_type, weld_material, weld_thk = group_key
            
            # WELDING DIA 포맷팅
            welding_dia_str = f"{group_info['welding_dia_sum']:.2f}" if group_info['welding_dia_sum'] > 0 else "-"
            
            # 용착량/용접봉수량 총합 계산
            deposition_total = group_info['deposition_per_joint'] * group_info['count']
            electrode_total = group_info['electrode_per_joint'] * group_info['count']
            
            # 데이터 행 작성
            row_data = [
                shop_fld if shop_fld else '-',
                weld_bore if weld_bore else '-',
                weld_type if weld_type else '-',
                weld_material if weld_material else '-',
                weld_thk if weld_thk else '-',
                welding_dia_str,
                group_info['count'],  # WELD POINT
                f"{deposition_total:.2f}kg" if deposition_total > 0 else "-",
                f"{electrode_total:.2f}kg" if electrode_total > 0 else "-",
                group_info['welding_material']
            ]
            
            for col_idx, value in enumerate(row_data, 1):
                cell = ws_fw_total.cell(row=row_idx, column=col_idx, value=value)
                cell.font = data_font
                cell.alignment = data_alignment
                cell.border = thin_border
            
            # 합계 누적
            total_welding_dia += group_info['welding_dia_sum']
            total_weld_point += group_info['count']
            total_deposition += deposition_total
            total_electrode += electrode_total
            
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
        
        # 용착량 TOTAL 합계
        cell = ws_fw_total.cell(row=row_idx, column=8, value=f"{total_deposition:.2f}kg")
        cell.font = Font(size=12, bold=True)
        cell.alignment = header_alignment
        cell.border = thick_border
        
        # 용접봉수량 TOTAL 합계
        cell = ws_fw_total.cell(row=row_idx, column=9, value=f"{total_electrode:.2f}kg")
        cell.font = Font(size=12, bold=True)
        cell.alignment = header_alignment
        cell.border = thick_border
        
        # 용접재료 (TOTAL 행에는 '-' 표시)
        cell = ws_fw_total.cell(row=row_idx, column=10, value="-")
        cell.font = Font(size=12, bold=True)
        cell.alignment = header_alignment
        cell.border = thick_border
        
        print(f"  - FW TOTAL 시트 생성: {len(fw_groups)}개 그룹, 총 {total_weld_point}개 포인트")
        print(f"    > 총 용착량: {total_deposition:.2f}kg")
        print(f"    > 총 용접봉수량: {total_electrode:.2f}kg")
    
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
        
        print(f"  - MAT_{group_name} 시트 생성: {len(group_data)}개 (SW: {sw_count}개 먼저 출력)")
    
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
    
    print(f"\n=== Excel 파일 저장 완료 ===")
    print(f"파일명: {excel_filename}")
    print(f"경로: {excel_path}")
    print(f"총 {len(all_weld_data)}개의 WELD 데이터 저장됨")
    print(f"\n시트 구성:")
    print(f"  - ALL_WELD: 전체 데이터")
    print(f"  - FW: Field Weld 상세 ({len(fw_data)}개)")
    print(f"  - SW: Shop Weld 상세 ({len(sw_data)}개)")
    print(f"  - FW TOTAL: Field Weld 그룹화 요약 (용착량/용접봉수량 총합 포함)")
    print(f"  - SW TOTAL: Shop Weld 그룹화 요약 (용착량/용접봉수량 총합 포함)")
    print(f"  - MAT별 시트: {len(mat_groups)}개 그룹")
    
    # 처음 몇 개 데이터 샘플 출력 (전체 열 확인)
    print(f"\n=== WELD 데이터 샘플 (처음 3개) ===")
    for i, row in enumerate(all_weld_data[:3]):
        print(f"\n  행 {i+1}:")
        print(f"    ISO DWG NO: '{row.get('ISO DWG NO', '')}'")
        print(f"    LINE NO: '{row.get('LINE NO', '')}'")
        print(f"    DESCRIPTION: '{row.get('DESCRIPTION', '')}'")
        print(f"    WELD NO: '{row.get('WELD NO', '')}'")
        print(f"    SHOP/FLD: '{row.get('SHOP/FLD', '')}'")
        print(f"    WELD BORE: '{row.get('WELD BORE', '')}'")
        print(f"    WELD TYPE: '{row.get('WELD TYPE', '')}'")
        print(f"    WELD MATERIAL: '{row.get('WELD MATERIAL', '')}'")
        print(f"    WELD THK: '{row.get('WELD THK', '')}'")
        print(f"    WELDING DIA: '{row.get('WELDING DIA', '')}'")
        print(f"    PIPE THK: '{row.get('PIPE THK', '')}'")
        print(f"    GROOVE TYPE: '{row.get('GROOVE TYPE', '')}'")
        print(f"    용착량: '{row.get('용착량', '')}'")
        print(f"    용접봉수량: '{row.get('용접봉수량', '')}'")
        print(f"    용접재료: '{row.get('용접재료', '')}'")
        print(f"    PREHEAT: '{row.get('PREHEAT', '')}'")
        print(f"    PWHT: '{row.get('PWHT', '')}'")
        print(f"    NDE 검사: '{row.get('NDE 검사', '')}'")
    
    # MAT 그룹 정보 출력
    print(f"\n=== MAT 그룹 정보 ===")
    for group_name, group_data in sorted(mat_groups.items()):
        mat_examples = list(set([d.get('WELD MATERIAL', '') for d in group_data[:3]]))
        print(f"  - {group_name}: {len(group_data)}개 (예: {', '.join(mat_examples[:2])})")
else:
    print("\n*** 추출된 WELD 데이터가 없습니다 ***")