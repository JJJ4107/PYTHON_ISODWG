# -*- coding: utf-8 -*-
import ezdxf
import tkinter as tk
from tkinter import filedialog
import os
import math
from ezdxf.colors import RED, YELLOW, CYAN, WHITE, BLUE
from ezdxf import bbox

# --- T1 탐색 파라미터 ---
T1_X_MIN = 600.0
T1_X_MAX = 850.0
T1_Y_TOP = 550.0
T1_Y_BOTTOM = 250.0

# --- 폭 비율(Width Factor) 통일값 ---
TARGET_WIDTH_FACTOR = 0.87

# --- 유니코드 공백 (⅓ em) ---
THREE_PER_EM = "\u2004"  # 1/3 em
TWO_THIRDS_EM = THREE_PER_EM + THREE_PER_EM  # 2/3 em

def process_dxf_files():
    """DXF 파일을 선택하고 처리하는 메인 함수"""
    root = tk.Tk()
    root.withdraw()
    file_paths = filedialog.askopenfilenames(
        title="DXF 파일을 선택하세요",
        filetypes=[("DXF files", "*.dxf"), ("All files", "*.*")]
    )
    if not file_paths:
        print("파일이 선택되지 않았습니다.")
        return
    for file_path in file_paths:
        try:
            process_single_dxf(file_path)
            print(f"성공적으로 처리됨: {file_path}")
        except Exception as e:
            print(f"오류 발생 ({file_path}): {str(e)}")

def calculate_line_length(line_entity):
    start = line_entity.dxf.start
    end = line_entity.dxf.end
    return math.sqrt(
        (end[0] - start[0])**2 +
        (end[1] - start[1])**2 +
        (end[2] - start[2])**2
    )

def calculate_arc_length(arc_entity):
    """ARC 엔티티의 길이 계산"""
    radius = arc_entity.dxf.radius
    start_angle = math.radians(arc_entity.dxf.start_angle)
    end_angle = math.radians(arc_entity.dxf.end_angle)
    
    # 각도 차이 계산 (0~2π 범위)
    angle_diff = end_angle - start_angle
    if angle_diff < 0:
        angle_diff += 2 * math.pi
    
    return radius * angle_diff

def arc_to_points(arc_entity, num_segments=16):
    """ARC를 폴리라인 점들로 변환"""
    center = arc_entity.dxf.center
    radius = arc_entity.dxf.radius
    start_angle = math.radians(arc_entity.dxf.start_angle)
    end_angle = math.radians(arc_entity.dxf.end_angle)
    
    # 각도 차이 계산
    angle_diff = end_angle - start_angle
    if angle_diff < 0:
        angle_diff += 2 * math.pi
    
    # 세그먼트별 각도
    angle_step = angle_diff / num_segments
    
    points = []
    for i in range(num_segments + 1):
        angle = start_angle + i * angle_step
        x = center[0] + radius * math.cos(angle)
        y = center[1] + radius * math.sin(angle)
        points.append((x, y))
    
    return points

def process_single_dxf(file_path):
    doc = ezdxf.readfile(file_path)
    msp = doc.modelspace()

    # PIPE, TEE, ELBO 레이어의 LINE과 ARC를 변환할 리스트
    lines_to_convert = []
    arcs_to_convert = []

    # 색상 변경 작업 수행
    for entity in msp:
        layer_name = entity.dxf.layer.upper()
        
        # LINE 수집
        if entity.dxftype() == 'LINE' and ('PIPE' in layer_name or 'TEE' in layer_name or 'ELBO' in layer_name):
            lines_to_convert.append(entity)
            continue
            
        # ARC 수집 (ELBO만)
        if entity.dxftype() == 'ARC' and 'ELBO' in layer_name:
            arcs_to_convert.append(entity)
            continue

        if entity.dxftype() == 'CIRCLE' and layer_name == 'WDC':
            entity.dxf.color = WHITE
        elif entity.dxftype() in ['TEXT', 'MTEXT'] and layer_name == 'ITNO':
            entity.dxf.color = YELLOW
        elif entity.dxftype() == 'LINE' and layer_name == 'ITNO':
            entity.dxf.color = WHITE
        elif entity.dxftype() == 'CIRCLE' and layer_name == 'WELDS' and entity.dxf.color == 6:
            entity.dxf.color = WHITE
        elif entity.dxftype() == 'LINE' and layer_name == 'ITEMPOS' and entity.dxf.color == YELLOW:
            entity.dxf.color = WHITE
        elif entity.dxftype() == 'LINE' and entity.dxf.color == CYAN:
            entity.dxf.color = WHITE
        elif entity.dxftype() in ['TEXT', 'MTEXT'] and entity.dxf.color == CYAN:
            entity.dxf.color = YELLOW
        elif entity.dxftype() == 'CIRCLE' and entity.dxf.color == YELLOW:
            entity.dxf.color = WHITE
        elif entity.dxftype() in ['TEXT', 'MTEXT'] and layer_name == 'WDT':
            text_value = entity.dxf.text if entity.dxftype() == 'TEXT' else entity.text
            if text_value.strip() == "0":
                entity.dxf.color = RED
        elif entity.dxftype() in ['TEXT', 'MTEXT'] and entity.dxf.color == RED:
            if not (layer_name == 'WDT' and get_text_value(entity).strip() == "0"):
                entity.dxf.color = YELLOW
        elif entity.dxftype() == 'LINE' and layer_name == 'SUPP':
            if 6 <= calculate_line_length(entity) <= 9:
                entity.dxf.color = CYAN

    # PIPE, TEE, ELBO 레이어의 LINE → POLYLINE 변환
    for line in lines_to_convert:
        start, end = line.dxf.start, line.dxf.end
        points = [(start[0], start[1]), (end[0], end[1])]
        layer_name = line.dxf.layer.upper()
        if 'PIPE' in layer_name:
            if calculate_line_length(line) <= 2:
                pline = msp.add_lwpolyline(points)
                pline.dxf.const_width = 0.3
                pline.dxf.color = YELLOW
                pline.dxf.layer = line.dxf.layer
            else:
                pline = msp.add_lwpolyline(points)
                pline.dxf.const_width = 0.6
                pline.dxf.color = BLUE
                pline.dxf.layer = line.dxf.layer
        else:
            pline = msp.add_lwpolyline(points)
            pline.dxf.const_width = 0.6
            pline.dxf.color = BLUE
            pline.dxf.layer = line.dxf.layer
        msp.delete_entity(line)

    # ELBO 레이어의 ARC → POLYLINE 변환
    for arc in arcs_to_convert:
        # ARC를 점들로 변환 (16개 세그먼트 사용)
        points = arc_to_points(arc, num_segments=16)
        
        # POLYLINE 생성
        pline = msp.add_lwpolyline(points)
        pline.dxf.const_width = 0.6
        pline.dxf.color = BLUE
        pline.dxf.layer = arc.dxf.layer
        
        # 원래 ARC 삭제
        msp.delete_entity(arc)

    # --- T1 처리: x=600~850, y=550~250 ---
    apply_t1_formatting(
        doc, msp,
        x_min=T1_X_MIN, x_max=T1_X_MAX,
        y_top=T1_Y_TOP, y_bottom=T1_Y_BOTTOM,
        width_factor=TARGET_WIDTH_FACTOR
    )

    # ZOOM ALL 적용
    try:
        # 방법 1: 간단한 방법
        doc.set_modelspace_vport(center='*', height='*')
        print("ZOOM ALL 적용 완료 (방법 1)")
    except Exception:
        try:
            # 방법 2: bbox를 이용한 방법
            cache = bbox.Cache()
            extents = bbox.extents(msp, cache=cache)
            if extents.has_data:
                center = extents.center
                size = extents.size
                height = max(size.x, size.y) * 1.1  # 10% 여백 추가
                doc.set_modelspace_vport(center=center, height=height)
                print("ZOOM ALL 적용 완료 (방법 2)")
            else:
                print("ZOOM ALL 적용 실패: 도면에 객체가 없습니다")
        except Exception as e:
            print(f"ZOOM ALL 적용 중 오류 (무시하고 계속): {e}")

    # 저장
    dir_name = os.path.dirname(file_path)
    base_name = os.path.basename(file_path)
    name_without_ext = os.path.splitext(base_name)[0]
    if 'PL' in name_without_ext.upper():
        pl_index = name_without_ext.upper().find('PL')
        new_name = name_without_ext[:pl_index] + '_SP3D.DXF'
    else:
        new_name = name_without_ext + '_SP3D.DXF'
    new_file_path = os.path.join(dir_name, new_name)
    doc.saveas(new_file_path)
    print(f"저장 완료: {new_file_path}")

def get_text_value(entity):
    if entity.dxftype() == 'TEXT':
        return entity.dxf.text
    elif entity.dxftype() == 'MTEXT':
        return entity.text
    return ""

# -------------------- 추가 유틸 --------------------
def ensure_text_style(doc, style_name: str = "ARIAL", font_file: str = "arial.ttf", width_factor: float = 0.87):
    """ARIAL 스타일 생성/갱신 + 폭 비율 통일"""
    try:
        style = doc.styles.get(style_name)
    except ezdxf.DXFKeyError:
        style = doc.styles.new(style_name, dxfattribs={"font": font_file})
    try:
        style.dxf.width_factor = width_factor
    except Exception:
        pass

def get_text_reference_xy(e):
    """TEXT: align_point 우선, 없으면 insert / MTEXT: insert"""
    try:
        if e.dxftype() == "TEXT":
            if e.dxf.hasattr("align_point"):
                ap = e.dxf.align_point
                if ap is not None:
                    ax, ay = float(ap[0]), float(ap[1])
                    if ax != 0.0 or ay != 0.0:
                        return ax, ay
            ins = getattr(e.dxf, "insert", None)
            if ins is not None:
                return float(ins[0]), float(ins[1])
        elif e.dxftype() == "MTEXT":
            ins = getattr(e.dxf, "insert", None)
            if ins is not None:
                return float(ins[0]), float(ins[1])
    except Exception:
        return None
    return None

def is_in_band(xy, x_min, x_max, y_top, y_bottom):
    if xy is None:
        return False
    px, py = xy
    return (x_min <= px <= x_max) and (min(y_bottom, y_top) <= py <= max(y_bottom, y_top))

def replace_spaces_two_thirds_em(text: str) -> str:
    """' ' → 2/3 em 공백으로 치환 (TEXT/MTEXT 공통, 인라인 코드 사용 안 함)"""
    if not text:
        return text
    return text.replace(" ", TWO_THIRDS_EM)

def apply_t1_formatting(doc, msp, x_min, x_max, y_top, y_bottom, width_factor: float = 0.87):
    """T1 영역의 TEXT/MTEXT에 ARIAL + 폭비율 + 공백(높이*2/3) 적용"""
    ensure_text_style(doc, "ARIAL", "arial.ttf", width_factor=width_factor)
    t1_count = 0

    for e in list(msp):
        if e.dxftype() not in ("TEXT", "MTEXT"):
            continue
        xy = get_text_reference_xy(e)
        if not is_in_band(xy, x_min, x_max, y_top, y_bottom):
            continue

        # 스타일 통일
        try:
            e.dxf.style = "ARIAL"
        except Exception:
            pass

        # 폭 비율 적용
        if e.dxftype() == "TEXT":
            try:
                e.dxf.width = width_factor
            except Exception:
                pass
            # 공백 치환 (2/3 em)
            try:
                e.dxf.text = replace_spaces_two_thirds_em(e.dxf.text)
            except Exception:
                pass
        else:  # MTEXT
            # MTEXT는 스타일의 width_factor 적용을 신뢰 (인라인 \W 사용 안 함)
            try:
                e.text = replace_spaces_two_thirds_em(e.text)
            except Exception:
                pass

        t1_count += 1

    print(f"[T1] 스타일=ARIAL, 폭비율={width_factor}, 공백=높이*2/3(유니코드) 적용 대상: {t1_count}")
# -------------------- 추가 유틸 끝 --------------------

if __name__ == "__main__":
    print("DXF 파일 색상 및 객체 변환 프로그램")
    print("=====================================")
    print("처리 내용:")
    print("1~12. (기존 색상 변경 및 POLYLINE 변환 작업)")
    print("13. (추가) x=600~850, y=550~250 TEXT/MTEXT(T1)")
    print("    - 스타일 ARIAL 통일")
    print("    - 폭 비율 0.87 적용")
    print("    - 공백 = 글자 높이 × 2/3 (유니코드 1/3em × 2)로 치환, 인라인 코드 미사용")
    print("14. (추가) ELBO 레이어의 ARC도 POLYLINE으로 변환")
    print("    - 폭 0.6, 색상 BLUE")
    print("15. (추가) 저장 시 ZOOM ALL 자동 적용")
    print("=====================================\n")

    try:
        process_dxf_files()
    except Exception as e:
        print(f"프로그램 실행 중 오류 발생: {str(e)}")

    input("\n프로그램을 종료하려면 Enter 키를 누르세요...")