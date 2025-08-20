import ezdxf
import tkinter as tk
from tkinter import filedialog
import os
from ezdxf.colors import DXF_DEFAULT_COLORS, RED, YELLOW, CYAN, WHITE

def process_dxf_files():
    """DXF 파일을 선택하고 처리하는 메인 함수"""
    # Tkinter 루트 윈도우 생성 (파일 대화상자용)
    root = tk.Tk()
    root.withdraw()  # 메인 윈도우 숨기기
    
    # 파일 선택 대화상자 열기
    file_paths = filedialog.askopenfilenames(
        title="DXF 파일을 선택하세요",
        filetypes=[("DXF files", "*.dxf"), ("All files", "*.*")]
    )
    
    if not file_paths:
        print("파일이 선택되지 않았습니다.")
        return
    
    # 선택된 각 파일 처리
    for file_path in file_paths:
        try:
            process_single_dxf(file_path)
            print(f"성공적으로 처리됨: {file_path}")
        except Exception as e:
            print(f"오류 발생 ({file_path}): {str(e)}")

def process_single_dxf(file_path):
    """단일 DXF 파일을 처리하는 함수"""
    # DXF 파일 읽기
    doc = ezdxf.readfile(file_path)
    msp = doc.modelspace()
    
    # 1단계: 색상 변경 작업 수행
    for entity in msp:
        # WDC 레이어의 원을 흰색으로
        if entity.dxftype() == 'CIRCLE' and entity.dxf.layer.upper() == 'WDC':
            entity.dxf.color = WHITE
        
        # ITNO 레이어의 TEXT를 YELLOW로
        elif entity.dxftype() in ['TEXT', 'MTEXT'] and entity.dxf.layer.upper() == 'ITNO':
            entity.dxf.color = YELLOW
        
        # ITNO 레이어의 LINE을 흰색으로
        elif entity.dxftype() == 'LINE' and entity.dxf.layer.upper() == 'ITNO':
            entity.dxf.color = WHITE
        
        # WELDS 레이어의 MAGENTA 색상 원을 흰색으로
        elif entity.dxftype() == 'CIRCLE' and entity.dxf.layer.upper() == 'WELDS' and entity.dxf.color == 6:  # MAGENTA = 6
            entity.dxf.color = WHITE
        
        # ITEMPOS 레이어의 YELLOW 선을 흰색으로
        elif entity.dxftype() == 'LINE' and entity.dxf.layer.upper() == 'ITEMPOS' and entity.dxf.color == YELLOW:
            entity.dxf.color = WHITE
        
        # CYAN 색상의 LINE을 흰색으로
        elif entity.dxftype() == 'LINE' and entity.dxf.color == CYAN:
            entity.dxf.color = WHITE
        
        # CYAN 색상의 TEXT를 YELLOW로
        elif entity.dxftype() in ['TEXT', 'MTEXT'] and entity.dxf.color == CYAN:
            entity.dxf.color = YELLOW
        
        # YELLOW 색상의 원을 흰색으로
        elif entity.dxftype() == 'CIRCLE' and entity.dxf.color == YELLOW:
            entity.dxf.color = WHITE
        
        # WDT 레이어의 TEXT 중 값이 "0"인 것을 빨간색으로
        elif entity.dxftype() in ['TEXT', 'MTEXT'] and entity.dxf.layer.upper() == 'WDT':
            text_value = ""
            if entity.dxftype() == 'TEXT':
                text_value = entity.dxf.text
            elif entity.dxftype() == 'MTEXT':
                text_value = entity.text
            
            if text_value.strip() == "0":
                entity.dxf.color = RED
        
        # RED 색상의 TEXT를 YELLOW로
        elif entity.dxftype() in ['TEXT', 'MTEXT'] and entity.dxf.color == RED:
            # WDT 레이어의 "0" 텍스트는 방금 빨간색으로 변경했으므로 제외
            if not (entity.dxf.layer.upper() == 'WDT' and get_text_value(entity).strip() == "0"):
                entity.dxf.color = YELLOW
    
    # 2단계: 모든 객체를 ACE_SP3D 레이어로 변경
    # ACE_SP3D 레이어가 없으면 생성
    if 'ACE_SP3D' not in doc.layers:
        doc.layers.add('ACE_SP3D')
    
    # 모든 엔티티의 레이어를 ACE_SP3D로 변경
    for entity in msp:
        entity.dxf.layer = 'ACE_SP3D'
    
    # 3단계: 새 파일명 생성 및 저장
    dir_name = os.path.dirname(file_path)
    base_name = os.path.basename(file_path)
    name_without_ext = os.path.splitext(base_name)[0]
    
    # "PL" 이전의 이름 추출
    if 'PL' in name_without_ext.upper():
        # 대소문자 구분 없이 PL 위치 찾기
        pl_index = name_without_ext.upper().find('PL')
        new_name = name_without_ext[:pl_index] + '_SP3D.DXF'
    else:
        # PL이 없으면 전체 이름 사용
        new_name = name_without_ext + '_SP3D.DXF'
    
    new_file_path = os.path.join(dir_name, new_name)
    
    # 파일 저장
    doc.saveas(new_file_path)
    print(f"저장 완료: {new_file_path}")

def get_text_value(entity):
    """TEXT 또는 MTEXT 엔티티에서 텍스트 값을 추출하는 헬퍼 함수"""
    if entity.dxftype() == 'TEXT':
        return entity.dxf.text
    elif entity.dxftype() == 'MTEXT':
        return entity.text
    return ""

if __name__ == "__main__":
    print("DXF 파일 색상 및 레이어 변환 프로그램")
    print("=====================================")
    print("처리 내용:")
    print("1. WDC 레이어의 원 → 흰색")
    print("2. ITNO 레이어의 TEXT → 노란색")
    print("3. ITNO 레이어의 LINE → 흰색")
    print("4. WELDS 레이어의 MAGENTA 원 → 흰색")
    print("5. ITEMPOS 레이어의 YELLOW 선 → 흰색")
    print("6. CYAN 색상의 LINE → 흰색")
    print("7. CYAN 색상의 TEXT → 노란색")
    print("8. YELLOW 색상의 원 → 흰색")
    print("9. WDT 레이어의 '0' 텍스트 → 빨간색")
    print("10. RED 색상의 TEXT → 노란색")
    print("11. 모든 객체 → ACE_SP3D 레이어로 이동")
    print("=====================================\n")
    
    try:
        process_dxf_files()
    except Exception as e:
        print(f"프로그램 실행 중 오류 발생: {str(e)}")
    
    input("\n프로그램을 종료하려면 Enter 키를 누르세요...")