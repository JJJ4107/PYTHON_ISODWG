import os
import re
import ezdxf
import math
import sys

def get_xy(e):
    """엔티티의 X, Y 좌표를 반환"""
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
    """엔티티의 텍스트 내용을 반환"""
    try:
        if hasattr(e, 'dxf') and hasattr(e.dxf, 'text'):
            return e.dxf.text.strip()
        elif hasattr(e, 'text'):
            return e.text.strip()
    except Exception:
        pass
    return ''

def set_color(e, color):
    """엔티티의 색상을 변경"""
    try:
        if hasattr(e, 'dxf'):
            e.dxf.color = color
            return True
    except Exception:
        pass
    return False

def find_special_below(msp, base_x, base_y, x_tol=4, y_tol=20, patt=None):
    """기준 좌표 아래에서 특정 패턴의 텍스트를 찾음"""
    candidates = []
    for e in msp.query('TEXT MTEXT'):
        txt = get_text(e)
        x, y = get_xy(e)
        if abs(x-base_x) <= x_tol and (y < base_y) and (0 < base_y - y <= y_tol):
            if patt is None or re.search(patt, txt, re.I):
                candidates.append((base_y - y, e))
    if not candidates:
        return []
    return [e for _, e in sorted(candidates, key=lambda t: t[0])]

def get_text_width(e):
    """텍스트의 너비를 추정 (텍스트 높이 * 문자 수 * 0.7)"""
    try:
        if hasattr(e, 'dxf'):
            text = get_text(e)
            height = getattr(e.dxf, 'height', 2.5)  # 기본 높이 2.5
            # 간단한 너비 추정: 높이 * 문자수 * 0.7 (평균 문자 폭 비율)
            return height * len(text) * 0.7
    except:
        pass
    return 10  # 기본값

def get_tbox(entities):
    """TBOX (Text Box) 계산 - 가장 긴 텍스트 기준, X/2 이동, Y는 텍스트 높이/2 이동"""
    if not entities:
        return None
    
    # 가장 긴 텍스트 찾기
    max_text_width = 0
    text_height = 2.5  # 기본값
    
    for e in entities:
        width = get_text_width(e)
        if width > max_text_width:
            max_text_width = width
            if hasattr(e, 'dxf') and hasattr(e.dxf, 'height'):
                text_height = e.dxf.height
    
    # APOS 그룹의 Y 범위 계산
    y_coords = []
    x_coords = []
    for e in entities:
        x, y = get_xy(e)
        x_coords.append(x)
        y_coords.append(y)
    
    # 기본 중심점
    center_x = sum(x_coords) / len(x_coords)
    center_y = sum(y_coords) / len(y_coords)
    
    # X축으로 max_text_width/2 만큼 이동
    # Y축으로 text_height/2 만큼 이동
    shifted_center_x = center_x + max_text_width / 2
    shifted_center_y = center_y + text_height / 2
    
    # TBOX 생성 (이동된 중심점 기준)
    min_x = shifted_center_x - max_text_width / 2
    max_x = shifted_center_x + max_text_width / 2
    min_y = min(y_coords) - 2
    max_y = max(y_coords) + 2
    
    return (min_x, min_y, max_x, max_y)

def get_min_distance_polyline_to_box(polyline_points, tbox):
    """폴리라인의 점들과 TBOX의 가장 가까운 거리 계산 (디버깅용 상세 버전)"""
    min_distance = float('inf')
    
    # TBOX의 4개 코너
    box_corners = [
        (tbox[0], tbox[1]),  # 좌하단
        (tbox[2], tbox[1]),  # 우하단
        (tbox[2], tbox[3]),  # 우상단
        (tbox[0], tbox[3])   # 좌상단
    ]
    
    # 폴리라인의 각 점과 TBOX 코너 간 최소 거리
    for px, py in polyline_points:
        for bx, by in box_corners:
            dist = math.sqrt((px - bx)**2 + (py - by)**2)
            min_distance = min(min_distance, dist)
    
    # TBOX 가장자리와의 거리도 확인
    box_edges = [
        (tbox[0], tbox[1], tbox[2], tbox[1]),  # 하단
        (tbox[2], tbox[1], tbox[2], tbox[3]),  # 우측
        (tbox[2], tbox[3], tbox[0], tbox[3]),  # 상단
        (tbox[0], tbox[3], tbox[0], tbox[1])   # 좌측
    ]
    
    for px, py in polyline_points:
        for x1, y1, x2, y2 in box_edges:
            dist = distance_point_to_line(px, py, x1, y1, x2, y2)
            min_distance = min(min_distance, dist)
    
    return min_distance

def point_in_box(px, py, box):
    """점이 박스 안에 있는지 확인"""
    min_x, min_y, max_x, max_y = box
    return min_x <= px <= max_x and min_y <= py <= max_y

def line_intersects_box(x1, y1, x2, y2, box):
    """선분이 박스와 교차하는지 확인"""
    min_x, min_y, max_x, max_y = box
    
    # 선분의 양 끝점이 박스 안에 있으면 교차
    if point_in_box(x1, y1, box) or point_in_box(x2, y2, box):
        return True
    
    # 선분이 박스의 변과 교차하는지 확인
    # 박스의 4개 변
    box_lines = [
        (min_x, min_y, max_x, min_y),  # 하단
        (max_x, min_y, max_x, max_y),  # 우측
        (max_x, max_y, min_x, max_y),  # 상단
        (min_x, max_y, min_x, min_y)   # 좌측
    ]
    
    for bx1, by1, bx2, by2 in box_lines:
        if lines_intersect(x1, y1, x2, y2, bx1, by1, bx2, by2):
            return True
    
    return False

def lines_intersect(x1, y1, x2, y2, x3, y3, x4, y4):
    """두 선분이 교차하는지 확인"""
    def ccw(A, B, C):
        return (C[1]-A[1]) * (B[0]-A[0]) > (B[1]-A[1]) * (C[0]-A[0])
    
    A = (x1, y1)
    B = (x2, y2)
    C = (x3, y3)
    D = (x4, y4)
    
    return ccw(A, C, D) != ccw(B, C, D) and ccw(A, B, C) != ccw(A, B, D)

def polyline_near_tbox(polyline_points, tbox, tolerance=5):
    """폴리라인의 점이 TBOX와 관련있는지 확인 (점이 안에 있거나, 교차하거나, 어느 한점과도 5mm 이내)"""
    min_x, min_y, max_x, max_y = tbox
    
    # TBOX의 4개 코너
    box_corners = [
        (min_x, min_y),  # 좌하단
        (max_x, min_y),  # 우하단
        (max_x, max_y),  # 우상단
        (min_x, max_y)   # 좌상단
    ]
    
    # 1. 점이 TBOX 안에 있는지 확인
    for px, py in polyline_points:
        if point_in_box(px, py, tbox):
            return True
    
    # 2. 선분이 TBOX와 교차하는지 확인
    for i in range(len(polyline_points) - 1):
        x1, y1 = polyline_points[i]
        x2, y2 = polyline_points[i + 1]
        if line_intersects_box(x1, y1, x2, y2, tbox):
            return True
    
    # 3. 폴리라인의 어느 점이든 TBOX의 어느 한점과도 5mm 이내에 있는지 확인
    for px, py in polyline_points:
        for bx, by in box_corners:
            dist = math.sqrt((px - bx)**2 + (py - by)**2)
            if dist <= tolerance:
                return True
    
    # 4. TBOX 가장자리와의 거리도 확인
    box_edges = [
        (min_x, min_y, max_x, min_y),  # 하단
        (max_x, min_y, max_x, max_y),  # 우측
        (max_x, max_y, min_x, max_y),  # 상단
        (min_x, max_y, min_x, min_y)   # 좌측
    ]
    
    for px, py in polyline_points:
        for x1, y1, x2, y2 in box_edges:
            dist = distance_point_to_line(px, py, x1, y1, x2, y2)
            if dist <= tolerance:
                return True
    
    return False

def create_box_polyline(msp, box, color=3, layer="APOS_BOX"):
    """바운딩 박스를 폴리라인으로 생성"""
    if not box:
        return None
    
    min_x, min_y, max_x, max_y = box
    
    try:
        # 먼저 LWPOLYLINE 시도 (DXF R2000 이상)
        points = [
            (min_x, min_y),  # 좌하단
            (max_x, min_y),  # 우하단
            (max_x, max_y),  # 우상단
            (min_x, max_y),  # 좌상단
            (min_x, min_y)   # 좌하단 (닫힌 폴리라인)
        ]
        
        polyline = msp.add_lwpolyline(points, dxfattribs={
            'layer': layer,
            'color': color,
            'closed': True
        })
    except:
        # LWPOLYLINE이 지원되지 않으면 일반 POLYLINE 사용
        polyline = msp.add_polyline2d(
            points=[(min_x, min_y), (max_x, min_y), (max_x, max_y), (min_x, max_y)],
            dxfattribs={
                'layer': layer,
                'color': color,
                'closed': True
            }
        )
    
    return polyline

def distance_point_to_line(px, py, x1, y1, x2, y2):
    """점에서 선분까지의 최단 거리 계산"""
    line_length = math.sqrt((x2-x1)**2 + (y2-y1)**2)
    if line_length == 0:
        return math.sqrt((px-x1)**2 + (py-y1)**2)
    
    t = max(0, min(1, ((px-x1)*(x2-x1) + (py-y1)*(y2-y1)) / (line_length**2)))
    projection_x = x1 + t * (x2-x1)
    projection_y = y1 + t * (y2-y1)
    
    return math.sqrt((px-projection_x)**2 + (py-projection_y)**2)

def get_polyline_points(polyline):
    """폴리라인의 점들을 가져옴"""
    points = []
    if polyline.dxftype() == 'LWPOLYLINE':
        points = [(p[0], p[1]) for p in polyline.get_points()]
    elif polyline.dxftype() == 'POLYLINE':
        for vertex in polyline.vertices:
            points.append((vertex.dxf.location.x, vertex.dxf.location.y))
    return points

def get_polyline_length(points):
    """폴리라인의 전체 길이 계산"""
    if len(points) < 2:
        return 0
    
    total_length = 0
    for i in range(len(points) - 1):
        x1, y1 = points[i]
        x2, y2 = points[i + 1]
        total_length += math.sqrt((x2-x1)**2 + (y2-y1)**2)
    
    return total_length

def get_polyline_angles(points):
    """폴리라인의 모든 선분 각도 계산"""
    angles = []
    
    for i in range(len(points) - 1):
        x1, y1 = points[i]
        x2, y2 = points[i + 1]
        
        # 각도 계산 (도 단위)
        angle = math.degrees(math.atan2(y2 - y1, x2 - x1))
        # 0~360도로 정규화
        if angle < 0:
            angle += 360
        
        angles.append(angle)
    
    return angles

def is_angle_excluded(angle, tolerance=0.5):
    """45도 간격의 정각인지 확인 (오차 허용)"""
    # 45도 간격 각도들 (0, 45, 90, 135, 180, 225, 270, 315)
    for base_angle in range(0, 360, 45):
        if abs(angle - base_angle) <= tolerance:
            return True
    return False

def has_excluded_angle(points, tolerance=0.5):
    """폴리라인의 모든 선분 중 45도 간격 정각이 있는지 확인"""
    angles = get_polyline_angles(points)
    
    for angle in angles:
        if is_angle_excluded(angle, tolerance):
            return True, angles
    
    return False, angles

def get_apos_group_center(group):
    """APOS 그룹의 중심점 계산"""
    x_coords = []
    y_coords = []
    
    for e in group:
        x, y = get_xy(e)
        x_coords.append(x)
        y_coords.append(y)
    
    center_x = sum(x_coords) / len(x_coords)
    center_y = sum(y_coords) / len(y_coords)
    
    return center_x, center_y

def get_min_distance_to_group(polyline_points, group_center_x, group_center_y):
    """폴리라인과 APOS 그룹 중심 간의 최소 거리"""
    min_dist = float('inf')
    
    # 각 점에서의 거리 확인
    for px, py in polyline_points:
        dist = math.sqrt((px - group_center_x)**2 + (py - group_center_y)**2)
        min_dist = min(min_dist, dist)
    
    # 선분에서의 거리 확인 (2점 이상인 경우)
    if len(polyline_points) >= 2:
        for i in range(len(polyline_points) - 1):
            x1, y1 = polyline_points[i]
            x2, y2 = polyline_points[i + 1]
            dist = distance_point_to_line(group_center_x, group_center_y, x1, y1, x2, y2)
            min_dist = min(min_dist, dist)
    
    return min_dist

def find_arrow_lines(msp, polyline_points):
    """DEL1 폴리라인과 교차하는 LINE 찾기 (1개만) - PIPE 레이어 제외"""
    if not polyline_points or len(polyline_points) < 2:
        return []
    
    # DEL1 폴리라인의 선분들
    del1_segments = []
    for i in range(len(polyline_points) - 1):
        x1, y1 = polyline_points[i]
        x2, y2 = polyline_points[i + 1]
        del1_segments.append((x1, y1, x2, y2))
    
    # 모든 LINE 검토
    for line in msp.query('LINE'):
        # PIPE 레이어 제외
        if 'PIPE' in line.dxf.layer.upper():
            continue
            
        start = line.dxf.start
        end = line.dxf.end
        
        # DEL1의 어느 한 선분과 교차하는지 확인
        for seg_x1, seg_y1, seg_x2, seg_y2 in del1_segments:
            if lines_intersect(start.x, start.y, end.x, end.y, seg_x1, seg_y1, seg_x2, seg_y2):
                return [line]  # 첫 번째 교차하는 LINE만 반환
    
    return []

def find_del3_polylines(msp, del2_line):
    """DEL2의 양 끝점이 모두 만나는 3점 ARROW/GT_1/PL3 폴리라인 찾기 (길이 5mm 이하) - PIPE 레이어 제외"""
    if not del2_line:
        return []
    
    # DEL2 LINE의 양 끝점
    start = del2_line.dxf.start
    end = del2_line.dxf.end
    del2_points = [(start.x, start.y), (end.x, end.y)]
    
    # ARROW, GT_1, PL3 레이어의 3점 폴리라인 검토
    for polyline in msp.query('LWPOLYLINE POLYLINE'):
        layer_name = polyline.dxf.layer.upper()
        
        # PIPE 레이어 제외
        if 'PIPE' in layer_name:
            continue
        
        # ARROW, GT_1, PL3 레이어 확인
        if not ('ARROW' in layer_name or 'GT_1' in layer_name or 'PL3' in layer_name):
            continue
        
        polyline_points = get_polyline_points(polyline)
        
        # 3점 확인
        if len(polyline_points) != 3:
            continue
        
        # 전체 길이 계산 (5mm 이하)
        total_length = get_polyline_length(polyline_points)
        if total_length > 5:
            continue
        
        # DEL2의 양 끝점이 모두 DEL3의 점들과 만나는지 확인
        matched_del2_points = set()
        
        for dx, dy in del2_points:
            for px, py in polyline_points:
                dist = math.sqrt((px - dx)**2 + (py - dy)**2)
                if dist < 0.1:  # 거의 만나는 경우 (0.1mm 오차 허용)
                    matched_del2_points.add((dx, dy))
                    break
        
        # DEL2의 양 끝점이 모두 매칭되었는지 확인
        if len(matched_del2_points) == 2:
            return [polyline]  # 조건을 만족하는 첫 번째 폴리라인 반환
    
    return []

def find_apos_group_from_cont(msp, cont_x, cont_y):
    """CONT 아래에서 완전한 APOS 그룹(E/W, S/N, FL/EL)을 찾음"""
    apos_groups = []
    
    # AFDNO 찾기 (색상 조건 있음)
    afdno_es = find_special_below(msp, cont_x, cont_y, x_tol=4, y_tol=20, patt=r"(-|FMF)")
    for afdno_e in afdno_es:
        color = getattr(afdno_e.dxf, "color", 256)
        if color in (1, 2, 5):  # RED, YELLOW, BLUE
            afdno_x, afdno_y = get_xy(afdno_e)
            
            # E/W 찾기
            epos_es = find_special_below(msp, afdno_x, afdno_y, x_tol=4, y_tol=20, patt=r"\b(E|W)\b")
            if epos_es:
                epos_e = epos_es[0]
                epos_x, epos_y = get_xy(epos_e)
                
                # S/N 찾기
                npos_es = find_special_below(msp, epos_x, epos_y, x_tol=4, y_tol=20, patt=r"\b(S|N)\b")
                if npos_es:
                    npos_e = npos_es[0]
                    npos_x, npos_y = get_xy(npos_e)
                    
                    # FL/EL 찾기
                    flpos_es = find_special_below(msp, npos_x, npos_y, x_tol=4, y_tol=20, patt=r"(FL|EL)")
                    if flpos_es:
                        flpos_e = flpos_es[0]
                        # 3개 조건이 모두 있는 경우만 그룹으로 추가
                        apos_groups.append([epos_e, npos_e, flpos_e])
    
    return apos_groups

def find_independent_apos_groups(msp, cont_apos_entities):
    """CONT와 독립적인 완전한 APOS 그룹(E/W, S/N, FL/EL)을 찾음"""
    independent_groups = []
    
    # E/W 패턴을 가진 모든 엔티티 찾기
    for e in msp.query('TEXT MTEXT'):
        # 이미 CONT 그룹에 속한 경우 스킵
        if e in cont_apos_entities:
            continue
            
        txt = get_text(e).upper()
        if re.search(r"\b(E|W)\b", txt):
            e_x, e_y = get_xy(e)
            
            # S/N 찾기
            npos_es = find_special_below(msp, e_x, e_y, x_tol=4, y_tol=20, patt=r"\b(S|N)\b")
            if npos_es:
                npos_e = npos_es[0]
                # CONT 그룹에 속한 경우 스킵
                if npos_e in cont_apos_entities:
                    continue
                    
                npos_x, npos_y = get_xy(npos_e)
                
                # FL/EL 찾기
                flpos_es = find_special_below(msp, npos_x, npos_y, x_tol=4, y_tol=20, patt=r"(FL|EL)")
                if flpos_es:
                    flpos_e = flpos_es[0]
                    # CONT 그룹에 속한 경우 스킵
                    if flpos_e in cont_apos_entities:
                        continue
                    
                    # 3개 조건이 모두 있는 경우만 그룹으로 추가
                    independent_groups.append([e, npos_e, flpos_e])
    
    return independent_groups

# Command line에서 전달된 DXF 파일들 처리
if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(1)
    
    # 각 파일 처리
    for file_path in sys.argv[1:]:
        if not os.path.exists(file_path) or not file_path.lower().endswith('.dxf'):
            continue
            
        file_name = os.path.basename(file_path)
        file_dir = os.path.dirname(file_path)
        base_name = os.path.splitext(file_name)[0]
        output_path = os.path.join(file_dir, f"{base_name}_PDEL.dxf")
        
        try:
            # DXF 파일 읽기
            doc = ezdxf.readfile(file_path)
            msp = doc.modelspace()
            
            # CONT 찾기 및 APOS 그룹 찾기
            cont_apos_entities = []  # CONT 그룹에 속한 모든 엔티티
            cont_apos_groups = []    # CONT 그룹의 완전한 APOS 그룹들
            cont_count = 0
            
            for e in msp.query('TEXT MTEXT'):
                txt = get_text(e).upper()
                if (('CONT' in txt and '.' in txt) or
                    ('CONN' in txt and '.' in txt)):
                    cont_count += 1
                    cont_x, cont_y = get_xy(e)
                    
                    # CONT 아래의 완전한 APOS 그룹 찾기
                    apos_groups = find_apos_group_from_cont(msp, cont_x, cont_y)
                    for group in apos_groups:
                        cont_apos_groups.append(group)
                        cont_apos_entities.extend(group)
                        
                        # CONT 그룹의 APOS를 CYAN으로 변경
                        for apos_e in group:
                            set_color(apos_e, 4)  # CYAN = 4
            
            # 독립적인 완전한 APOS 그룹 찾기
            independent_groups = find_independent_apos_groups(msp, cont_apos_entities)
            
            # 독립적인 APOS 그룹을 RED로 변경하고 BOX 생성
            for i, group in enumerate(independent_groups):
                # APOS를 RED로 변경
                for apos_e in group:
                    set_color(apos_e, 1)  # RED = 1
            
            # DEL1과 DEL2, DEL3 처리 - RED APOS 그룹만 처리
            del1_entities = []
            del2_entities = []
            del3_entities = []
            entities_to_delete = []  # 삭제할 엔티티 목록
            
            # 독립적인 APOS 그룹(RED)에 대해서만 폴리라인과 화살표 찾기
            for i, group in enumerate(independent_groups):
                # APOS 그룹의 TBOX 계산 (삭제 조건 확인용)
                tbox = get_tbox(group)
                if not tbox:
                    continue
                
                # GT_1, PL2, ARROW 레이어의 폴리라인 찾기
                candidates = []  # 후보 폴리라인들
                for polyline in msp.query('LWPOLYLINE POLYLINE'):
                    layer_name = polyline.dxf.layer.upper()
                    
                    # PIPE 레이어 제외
                    if 'PIPE' in layer_name:
                        continue
                    
                    if 'GT_1' in layer_name or 'PL2' in layer_name or 'ARROW' in layer_name:
                        polyline_points = get_polyline_points(polyline)
                        
                        # 점 개수 확인 (2~3개)
                        if len(polyline_points) < 2 or len(polyline_points) > 3:
                            continue
                        
                        # 폴리라인 길이 확인 (최소 2.5mm)
                        polyline_length = get_polyline_length(polyline_points)
                        if polyline_length < 2.5:
                            continue
                        
                        # TBOX와의 관계 확인 (안에 있거나, 교차하거나, 5mm 이내)
                        is_near = polyline_near_tbox(polyline_points, tbox, tolerance=5)
                        
                        if is_near:
                            # 폴리라인 점들과 TBOX 간 최소 거리
                            min_distance = get_min_distance_polyline_to_box(polyline_points, tbox)
                            
                            angles = get_polyline_angles(polyline_points)
                            angles_str = ", ".join([f"{a:.1f}°" for a in angles])
                            candidates.append((min_distance, polyline, polyline_points, polyline_length, layer_name, angles_str))
                
                # APOS 1개당 가장 가까운 1개의 폴리라인만 선택
                if candidates:
                    candidates.sort(key=lambda x: x[0])  # 거리순 정렬
                    
                    closest = candidates[0]
                    min_distance, polyline, polyline_points, polyline_length, layer_name, angles_str = closest
                    
                    del1_entities.append(polyline)
                    
                    # DEL2: DEL1과 교차하는 LINE 찾기 (1개)
                    arrow_lines = find_arrow_lines(msp, polyline_points)
                    del2_line = None
                    if arrow_lines:
                        del2_line = arrow_lines[0]
                        del2_entities.append(del2_line)
                        
                        # DEL3: DEL2의 양 끝점이 모두 만나는 3점 ARROW/GT_1/PL3 폴리라인 찾기
                        del3_polylines = find_del3_polylines(msp, del2_line)
                        if del3_polylines:
                            del3_entities.extend(del3_polylines)
                    
                    # APOS가 RED이고 DEL1이 선택되었으면 삭제 대상에 추가
                    # (DEL1이 RED로 변경되기 전이지만, 선택되었다는 것은 RED가 될 예정)
                    if polyline in del1_entities:
                        # APOS 그룹 삭제 대상에 추가
                        entities_to_delete.extend(group)
                        # DEL1 삭제 대상에 추가
                        entities_to_delete.append(polyline)
                        # DEL2 삭제 대상에 추가
                        if del2_line:
                            entities_to_delete.append(del2_line)
                        # DEL3 삭제 대상에 추가
                        if del3_polylines:
                            entities_to_delete.extend(del3_polylines)
            
            # 엔티티 삭제
            for entity in entities_to_delete:
                try:
                    msp.delete_entity(entity)
                except Exception as e:
                    pass
            
            # 파일 저장
            doc.saveas(output_path)
            
        except Exception as e:
            pass