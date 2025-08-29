import ezdxf
import os
import math
from ezdxf.math import Vec2
from tkinter import Tk, filedialog

def select_dxf_files():
    root = Tk()
    root.withdraw()
    file_paths = filedialog.askopenfilenames(
        title="DXF 파일 선택",
        filetypes=[("DXF Files", "*.dxf")]
    )
    root.destroy()
    return file_paths

def extract_points(entity):
    if entity.dxftype() == 'LWPOLYLINE':
        return [Vec2(x, y) for x, y, *_ in entity.get_points()]
    elif entity.dxftype() == 'POLYLINE':
        try:
            return [Vec2(v.dxf.location.x, v.dxf.location.y) for v in entity]
        except:
            return []
    elif entity.dxftype() == 'LINE':
        try:
            # LINE 엔티티의 경우
            start_3d = entity.dxf.start
            end_3d = entity.dxf.end
            return [Vec2(start_3d.x, start_3d.y), Vec2(end_3d.x, end_3d.y)]
        except:
            try:
                # 대체 방법
                start = entity.get_dxf_attrib('start')
                end = entity.get_dxf_attrib('end')
                return [Vec2(start[0], start[1]), Vec2(end[0], end[1])]
            except:
                return []
    return []

def distance(p1, p2):
    return math.hypot(p2.x - p1.x, p2.y - p1.y)

def get_entity_layer(entity):
    """엔티티의 레이어 이름을 안전하게 가져오기"""
    try:
        return entity.dxf.layer
    except AttributeError:
        try:
            return entity.get_dxf_attrib('layer', default='UNKNOWN')
        except:
            return 'UNKNOWN'

def get_entity_handle(entity):
    """엔티티의 핸들을 안전하게 가져오기"""
    try:
        return entity.dxf.handle
    except AttributeError:
        try:
            return entity.get_dxf_attrib('handle', default='UNKNOWN')
        except:
            return 'UNKNOWN'

def get_entity_color(entity):
    """엔티티의 색상을 안전하게 가져오기"""
    try:
        return entity.dxf.color
    except AttributeError:
        try:
            return entity.get_dxf_attrib('color', default=7)
        except:
            return 7

def set_entity_layer(entity, layer_name):
    """엔티티의 레이어를 안전하게 설정하기"""
    try:
        entity.dxf.layer = layer_name
    except AttributeError:
        try:
            entity.set_dxf_attrib('layer', layer_name)
        except:
            pass

def set_entity_color(entity, color):
    """엔티티의 색상을 안전하게 설정하기"""
    try:
        entity.dxf.color = color
    except AttributeError:
        try:
            entity.set_dxf_attrib('color', color)
        except:
            pass

def get_angle(p1, p2):
    return math.degrees(math.atan2(p2.y - p1.y, p2.x - p1.x))

def normalize_angle(angle):
    """각도를 -180 ~ 180 범위로 정규화"""
    while angle > 180:
        angle -= 360
    while angle < -180:
        angle += 360
    return angle

def angles_are_similar(angle1, angle2, tolerance=15):
    """두 각도가 유사한지 확인 (tolerance: 허용 오차)"""
    # 각도를 -180 ~ 180 범위로 정규화
    a1 = normalize_angle(angle1)
    a2 = normalize_angle(angle2)
    
    # 직접 차이
    diff = abs(a1 - a2)
    
    # 180도 반대 방향도 동일한 것으로 간주
    diff_opposite = abs(diff - 180)
    
    # 360도 경계 처리
    if diff > 180:
        diff = 360 - diff
    
    return diff <= tolerance or diff_opposite <= tolerance

def get_offset_by_angle(angle_deg, distance_mm):
    angle_rad = math.radians(angle_deg)
    return Vec2(math.cos(angle_rad), math.sin(angle_rad)) * distance_mm

def get_perpendicular_offset(angle_deg, distance_mm):
    angle_rad = math.radians(angle_deg + 90)
    return Vec2(math.cos(angle_rad), math.sin(angle_rad)) * distance_mm

def rotate_point(point, center, angle_deg):
    angle_rad = math.radians(angle_deg)
    dx, dy = point - center
    cos_a, sin_a = math.cos(angle_rad), math.sin(angle_rad)
    return Vec2(center.x + dx * cos_a - dy * sin_a,
                center.y + dx * sin_a + dy * cos_a)

def rotate_text(text, center, angle_deg):
    insert = text.dxf.insert
    pt = Vec2(insert[0], insert[1])
    new_pt = rotate_point(pt, center, angle_deg)
    text.dxf.insert = (new_pt.x, new_pt.y, 0)
    text.dxf.rotation += angle_deg

def move_text(text, offset):
    insert = text.dxf.insert
    pt = Vec2(insert[0], insert[1])
    new_pt = pt + offset
    text.dxf.insert = (new_pt.x, new_pt.y, 0)

def segments_cross(a1, a2, b1, b2):
    def ccw(A, B, C):
        return (C.y - A.y) * (B.x - A.x) > (B.y - A.y) * (C.x - A.x)
    return (ccw(a1, b1, b2) != ccw(a2, b1, b2)) and (ccw(a1, a2, b1) != ccw(a1, a2, b2))

def polyline_intersects_with_fall(pl_points, fall_points):
    """폴리라인이 FALL 폴리라인의 어떤 선분과도 교차하는지 확인"""
    for i in range(len(fall_points)):
        j = (i + 1) % len(fall_points)
        fall_seg_start = fall_points[i]
        fall_seg_end = fall_points[j]
        
        for k in range(len(pl_points) - 1):
            pl_seg_start = pl_points[k]
            pl_seg_end = pl_points[k + 1]
            
            if segments_cross(fall_seg_start, fall_seg_end, pl_seg_start, pl_seg_end):
                return True
    return False

def g1_crosses_both_fall_segments(g1_pts, fall_pts):
    """G1이 FALL의 점1-2 선분과 점3-4 선분을 모두 통과하는지 확인"""
    if len(g1_pts) != 2 or len(fall_pts) != 4:
        return False
    
    # FALL의 점1-2 선분과 교차 확인
    crosses_12 = segments_cross(g1_pts[0], g1_pts[1], fall_pts[0], fall_pts[1])
    
    # FALL의 점3-4 선분과 교차 확인
    crosses_34 = segments_cross(g1_pts[0], g1_pts[1], fall_pts[2], fall_pts[3])
    
    return crosses_12 and crosses_34

def polylines_intersect(pl1_points, pl2_points):
    """두 폴리라인이 교차하는지 확인"""
    for i in range(len(pl1_points) - 1):
        for j in range(len(pl2_points) - 1):
            if segments_cross(pl1_points[i], pl1_points[i+1], 
                            pl2_points[j], pl2_points[j+1]):
                return True
    return False

def check_all_segments_under_21(pts):
    """모든 점간 거리가 2.1mm 이하인지 확인"""
    for i in range(len(pts) - 1):
        if distance(pts[i], pts[i+1]) > 2.1:
            return False
    return True

def find_arrow_lines_near_points(msp, points, max_dist=0.2, max_length=1.0):
    """AD1의 점에서 max_dist(0.2mm) 내의 max_length(1mm) 이하 ARROW 레이어 line 찾기"""
    arrow_lines = []
    for line in msp.query('LINE'):
        if get_entity_layer(line).upper() != 'ARROW':
            continue
        
        start = Vec2(line.dxf.start.x, line.dxf.start.y)
        end = Vec2(line.dxf.end.x, line.dxf.end.y)
        
        # 라인 길이 확인
        line_length = distance(start, end)
        if line_length > max_length:
            continue
        
        # 각 AD1 점에서 line까지의 최소 거리 확인
        for pt in points:
            dist_to_start = distance(pt, start)
            dist_to_end = distance(pt, end)
            min_dist_to_line = min(dist_to_start, dist_to_end)
            
            if min_dist_to_line <= max_dist:
                arrow_lines.append(line)
                break
    
    return arrow_lines

def find_ad1_near_g1_start(g1_pts, ad1_groups, max_dist=0.5):
    """G1의 시작점에서 AD1 폴리라인이 max_dist(0.5mm) 내에 있는 AD1 찾기"""
    if not g1_pts:
        return []
    
    g1_start = g1_pts[0]  # G1의 시작점
    found_ad1_groups = []
    
    for ad1_group in ad1_groups:
        ad1_pts = extract_points(ad1_group['polyline'])
        
        # AD1의 모든 점 중 하나라도 G1 시작점에서 0.5mm 내에 있는지 확인
        for i, pt in enumerate(ad1_pts):
            dist = distance(g1_start, pt)
            if dist <= max_dist:
                found_ad1_groups.append(ad1_group)
                print(f"    [G1-AD1 연결] G1 시작점과 AD1 {i+1}번점 거리: {dist:.3f}mm")
                break  # 하나라도 찾으면 추가하고 다음 AD1로
    
    return found_ad1_groups

def is_text_upside_down(text_rotation):
    """텍스트가 뒤집혀 있는지 확인 (90도 < 회전 < 270도)"""
    # 회전 각도를 0-360 범위로 정규화
    normalized_rotation = text_rotation % 360
    return 90 < normalized_rotation < 270

def get_text_bounds(text):
    """텍스트의 대략적인 경계 상자를 반환"""
    # ezdxf의 TEXT 엔티티 속성 접근 방식
    try:
        # 방법 1: dxf 속성 사용
        insert = text.dxf.insert
        text_str = text.dxf.text
        height = text.dxf.height
        rotation = text.dxf.rotation
    except AttributeError:
        try:
            # 방법 2: get_dxf_attrib 메서드 사용
            insert = text.get_dxf_attrib('insert', default=(0, 0, 0))
            text_str = text.get_dxf_attrib('text', default='')
            height = text.get_dxf_attrib('height', default=1.0)
            rotation = text.get_dxf_attrib('rotation', default=0.0)
        except:
            # 방법 3: 직접 속성 접근
            insert = getattr(text, 'insert', (0, 0, 0))
            text_str = getattr(text, 'text', '')
            height = getattr(text, 'height', 1.0)
            rotation = getattr(text, 'rotation', 0.0)
    
    pos = Vec2(insert[0], insert[1])
    
    # 텍스트 크기 추정 (폰트 크기와 텍스트 길이 기반)
    text_length = len(text_str) * height * 0.7
    text_height = height * 1.2
    
    # 회전 고려
    angle_rad = math.radians(rotation)
    cos_a, sin_a = math.cos(angle_rad), math.sin(angle_rad)
    
    # 네 모서리 점 계산
    corners = [
        pos,
        pos + Vec2(text_length * cos_a, text_length * sin_a),
        pos + Vec2(text_length * cos_a - text_height * sin_a, 
                   text_length * sin_a + text_height * cos_a),
        pos + Vec2(-text_height * sin_a, text_height * cos_a)
    ]
    
    return corners

def point_to_line_distance(point, line_start, line_end):
    """점에서 선분까지의 최단 거리 계산"""
    line_vec = line_end - line_start
    point_vec = point - line_start
    line_len = distance(line_start, line_end)
    
    if line_len < 0.001:  # 선분이 점인 경우
        return distance(point, line_start)
    
    t = max(0, min(1, (point_vec.x * line_vec.x + point_vec.y * line_vec.y) / (line_len * line_len)))
    projection = line_start + line_vec * t
    
    return distance(point, projection)

def text_intersects_polyline(text, polyline_points):
    """텍스트가 폴리라인과 교차하는지 확인"""
    text_corners = get_text_bounds(text)
    
    # 텍스트 경계의 각 선분과 폴리라인의 각 선분이 교차하는지 확인
    for i in range(len(text_corners)):
        j = (i + 1) % len(text_corners)
        for k in range(len(polyline_points) - 1):
            if segments_cross(text_corners[i], text_corners[j], 
                            polyline_points[k], polyline_points[k+1]):
                return True
    
    # 텍스트의 각 모서리가 폴리라인에 너무 가까운지 확인 (1mm 이내)
    for corner in text_corners:
        for k in range(len(polyline_points) - 1):
            if point_to_line_distance(corner, polyline_points[k], polyline_points[k+1]) < 1.0:
                return True
    
    return False

def texts_overlap(text1, text2):
    """두 텍스트가 겹치는지 확인"""
    if text1 == text2:
        return False
    
    corners1 = get_text_bounds(text1)
    corners2 = get_text_bounds(text2)
    
    # 두 텍스트 경계가 교차하는지 확인
    for i in range(len(corners1)):
        j = (i + 1) % len(corners1)
        for k in range(len(corners2)):
            l = (k + 1) % len(corners2)
            if segments_cross(corners1[i], corners1[j], corners2[k], corners2[l]):
                return True
    
    # 한 텍스트의 중심이 다른 텍스트 내부에 있는지 확인
    try:
        insert1 = text1.dxf.insert
        insert2 = text2.dxf.insert
        height1 = text1.dxf.height
        height2 = text2.dxf.height
    except AttributeError:
        try:
            insert1 = text1.get_dxf_attrib('insert', default=(0, 0, 0))
            insert2 = text2.get_dxf_attrib('insert', default=(0, 0, 0))
            height1 = text1.get_dxf_attrib('height', default=1.0)
            height2 = text2.get_dxf_attrib('height', default=1.0)
        except:
            insert1 = getattr(text1, 'insert', (0, 0, 0))
            insert2 = getattr(text2, 'insert', (0, 0, 0))
            height1 = getattr(text1, 'height', 1.0)
            height2 = getattr(text2, 'height', 1.0)
    
    center1 = Vec2(insert1[0], insert1[1])
    center2 = Vec2(insert2[0], insert2[1])
    
    # 중심 간 거리가 너무 가까운 경우
    if distance(center1, center2) < (height1 + height2) * 0.5:
        return True
    
    return False

def count_interferences(text, msp, pipe_entities, other_texts):
    """텍스트의 간섭 수를 계산 (PIPE 제외)"""
    interference_count = 0
    
    # 모든 폴리라인과의 간섭 확인 (PIPE 제외)
    for entity in msp.query('LWPOLYLINE POLYLINE'):
        if entity in pipe_entities:
            continue
        
        pts = extract_points(entity)
        if pts and text_intersects_polyline(text, pts):
            interference_count += 1
    
    # 라인과의 간섭 확인 (PIPE 제외)
    for line in msp.query('LINE'):
        if get_entity_layer(line).upper() == 'PIPE':
            continue
        
        line_pts = [
            Vec2(line.dxf.start.x, line.dxf.start.y),
            Vec2(line.dxf.end.x, line.dxf.end.y)
        ]
        if text_intersects_polyline(text, line_pts):
            interference_count += 1
    
    # 다른 텍스트와의 간섭 확인
    for other_text in other_texts:
        if texts_overlap(text, other_text):
            interference_count += 100  # 텍스트 간섭은 매우 높은 가중치
    
    return interference_count

def find_optimal_text_position(text, pipe_angle, msp, pipe_entities, other_texts, max_offset=10):
    """텍스트의 최적 위치 찾기 (1mm 단위로 이동하며 간섭 최소화)"""
    insert = text.dxf.insert
    original_pos = Vec2(insert[0], insert[1])
    min_interference = count_interferences(text, msp, pipe_entities, other_texts)
    best_offset = 0
    
    print(f"    [간섭 체크] 시작 위치 간섭 수: {min_interference}")
    
    # 간섭이 없으면 그대로 유지
    if min_interference == 0:
        print(f"    [간섭 체크] 간섭 없음, 위치 유지")
        return
    
    # -10mm ~ +10mm 범위에서 1mm씩 이동하며 테스트
    for offset_mm in range(-max_offset, max_offset + 1):
        if offset_mm == 0:
            continue
        
        # 임시로 텍스트 이동
        offset_vec = get_offset_by_angle(pipe_angle, offset_mm)
        text.dxf.insert = (original_pos.x + offset_vec.x, 
                          original_pos.y + offset_vec.y, 0)
        
        # 간섭 수 계산
        interference = count_interferences(text, msp, pipe_entities, other_texts)
        
        # 더 적은 간섭을 찾은 경우
        if interference < min_interference:
            min_interference = interference
            best_offset = offset_mm
            print(f"    [간섭 체크] {offset_mm}mm 위치: 간섭 {interference}개")
            
            # 간섭이 0이면 즉시 중단
            if interference == 0:
                print(f"    [간섭 체크] 간섭 없는 위치 발견!")
                break
    
    # 최적 위치로 이동
    if best_offset != 0:
        offset_vec = get_offset_by_angle(pipe_angle, best_offset)
        text.dxf.insert = (original_pos.x + offset_vec.x, 
                          original_pos.y + offset_vec.y, 0)
        print(f"    [간섭 체크] 최종 이동: {best_offset}mm (간섭 {min_interference}개)")
    else:
        # 원래 위치로 복원
        text.dxf.insert = (original_pos.x, original_pos.y, 0)
        print(f"    [간섭 체크] 원래 위치 유지 (간섭 {min_interference}개)")

def min_distance_to_polyline(point, polyline_points):
    """점에서 폴리라인까지의 최소 거리 계산"""
    min_dist = float('inf')
    for i in range(len(polyline_points) - 1):
        dist = point_to_line_distance(point, polyline_points[i], polyline_points[i+1])
        min_dist = min(min_dist, dist)
    return min_dist

def find_fall_text_with_box(msp, reference_point, max_distance=100):
    """reference_point 주위에서 FALL을 포함하는 텍스트를 찾고 BOX화하여 가장 가까운 것 선택"""
    candidates = []
    
    for t in msp.query('TEXT'):
        if 'FALL' in t.dxf.text.upper():  # 회전 각도 제한 없음
            insert = t.dxf.insert
            t_pos = Vec2(insert[0], insert[1])
            
            # reference_point에서 max_distance 내에 있는지 확인
            if distance(t_pos, reference_point) <= max_distance:
                # 텍스트 BOX 생성
                text_corners = get_text_bounds(t)
                
                # BOX의 모든 점 중 reference_point에 가장 가까운 점 찾기
                min_dist = float('inf')
                for corner in text_corners:
                    dist = distance(corner, reference_point)
                    min_dist = min(min_dist, dist)
                
                candidates.append({
                    'text': t,
                    'min_distance': min_dist,
                    'corners': text_corners
                })
    
    # 가장 가까운 CT 선택
    if candidates:
        candidates.sort(key=lambda x: x['min_distance'])
        selected = candidates[0]
        rotation_info = f"(회전: {selected['text'].dxf.rotation:.1f}°)" if abs(selected['text'].dxf.rotation) > 1e-2 else "(수평)"
        print(f"  [CT 선택] '{selected['text'].dxf.text}' {rotation_info} - 최소 거리: {selected['min_distance']:.3f}mm")
        return selected['text']
    
    return None

def find_connected_pipes(msp, start_pipe, tolerance=0.2):
    """시작 PIPE에서 연결된 모든 PIPE 찾기"""
    connected_pipes = [start_pipe]
    processed = set([start_pipe])
    to_process = [start_pipe]
    
    # 좌표 스케일 확인을 위한 첫 번째 파이프 확인
    first_pts = extract_points(start_pipe)
    if len(first_pts) >= 2:
        first_length = distance(first_pts[0], first_pts[-1])
        print(f"    [첫 번째 PIPE 길이] {first_length:.3f}")
        
        # 파이프 길이가 매우 크면 tolerance 조정
        if first_length > 1000:  # 1000 이상이면 단위가 다를 가능성
            adjusted_tolerance = tolerance * 1000  # 미터 단위로 가정
            print(f"    [tolerance 자동 조정] {tolerance} → {adjusted_tolerance}")
            tolerance = adjusted_tolerance
    
    while to_process:
        current_pipe = to_process.pop(0)
        
        # extract_points 함수 사용으로 통일
        current_pts = extract_points(current_pipe)
        
        if len(current_pts) < 2:
            continue
            
        # 현재 PIPE의 양 끝점
        end_points = [current_pts[0], current_pts[-1]]
        
        # 다른 PIPE들과 연결 확인
        for entity in msp.query('LWPOLYLINE POLYLINE LINE'):
            if entity in processed or get_entity_layer(entity).upper() != 'PIPE':
                continue
                
            # extract_points 함수 사용으로 통일
            other_pts = extract_points(entity)
                
            if len(other_pts) < 2:
                continue
                
            # 다른 PIPE의 양 끝점
            other_end_points = [other_pts[0], other_pts[-1]]
            
            # 끝점 간 연결 확인
            connected = False
            min_connection_dist = float('inf')
            
            for ep1 in end_points:
                for ep2 in other_end_points:
                    dist = distance(ep1, ep2)
                    min_connection_dist = min(min_connection_dist, dist)
                    if dist <= tolerance:
                        connected = True
                        print(f"      [연결 감지] 거리 {dist:.6f}")
                        break
                if connected:
                    break
            
            if connected:
                connected_pipes.append(entity)
                processed.add(entity)
                to_process.append(entity)
                print(f"    [PIPE 연결] {get_entity_handle(entity)} 발견 (타입: {entity.dxftype()})")
            elif min_connection_dist < tolerance * 10:  # 근처에 있지만 연결되지 않은 경우
                print(f"    [근접 PIPE] {get_entity_handle(entity)} - 최소 거리: {min_connection_dist:.6f}")
    
    return connected_pipes

def create_tpipe_segments(connected_pipes):
    """연결된 PIPE들로부터 모든 선분 추출"""
    segments = []
    
    print(f"    [TPIPE 선분 생성] {len(connected_pipes)}개의 PIPE에서 선분 추출")
    
    for i, pipe in enumerate(connected_pipes):
        pts = extract_points(pipe)
        
        if len(pts) >= 2:
            # LINE인 경우 하나의 선분
            if pipe.dxftype() == 'LINE':
                segments.append([pts[0], pts[1]])
                if i < 5:  # 처음 5개만 출력
                    print(f"      {pipe.dxftype()}[{i}]: ({pts[0].x:.3f}, {pts[0].y:.3f}) → ({pts[1].x:.3f}, {pts[1].y:.3f})")
            else:
                # POLYLINE인 경우 여러 선분
                for j in range(len(pts) - 1):
                    segments.append([pts[j], pts[j+1]])
                    if i < 3 and j < 2:  # 처음 3개 폴리라인의 처음 2개 선분만 출력
                        print(f"      {pipe.dxftype()}[{i}]-seg[{j}]: ({pts[j].x:.3f}, {pts[j].y:.3f}) → ({pts[j+1].x:.3f}, {pts[j+1].y:.3f})")
        else:
            print(f"      [경고] {pipe.dxftype()}[{i}]: 점이 {len(pts)}개뿐임")
    
    print(f"    [TPIPE 선분 생성 완료] 총 {len(segments)}개 선분")
    
    # 좌표 범위 확인
    if segments:
        all_x = [pt.x for seg in segments for pt in seg]
        all_y = [pt.y for seg in segments for pt in seg]
        print(f"    [좌표 범위] X: {min(all_x):.3f} ~ {max(all_x):.3f}, Y: {min(all_y):.3f} ~ {max(all_y):.3f}")
        
        # 좌표 스케일 확인
        x_range = max(all_x) - min(all_x)
        y_range = max(all_y) - min(all_y)
        print(f"    [좌표 스케일] X 범위: {x_range:.3f}, Y 범위: {y_range:.3f}")
        
        # 매우 큰 좌표값이 있는지 확인
        if x_range > 10000 or y_range > 10000:
            print(f"    [경고] 좌표 범위가 매우 큽니다. 단위가 mm가 아닐 수 있습니다.")
    
    return segments

def find_fall_text_near_tpipe(msp, tpipe_segments, processed_texts, tpipe_layer_name, max_distance=20):
    """TPIPE 선분에서 max_distance 내의 모든 FALL 텍스트 찾기 (기울기 확인 포함)"""
    fall_texts = []
    
    # 디버깅: 전체 TEXT 개수 확인
    all_texts = list(msp.query('TEXT'))
    fall_containing_texts = [t for t in all_texts if 'FALL' in t.dxf.text.upper() and t not in processed_texts]
    print(f"  [디버깅] 전체 TEXT 개수: {len(all_texts)}, 미처리 FALL 포함 TEXT 개수: {len(fall_containing_texts)}")
    
    changed_count = 0
    
    for t in msp.query('TEXT'):
        if 'FALL' in t.dxf.text.upper() and t not in processed_texts:
            insert = t.dxf.insert
            t_pos = Vec2(insert[0], insert[1])
            
            # 텍스트 BOX의 각 모서리 점
            text_corners = get_text_bounds(t)
            
            # 텍스트의 회전 각도
            text_rotation = t.dxf.rotation
            
            # TPIPE의 각 선분에 대해 최소 거리 계산
            min_dist_to_tpipe = float('inf')
            closest_segment = None
            closest_info = None
            
            # 1. 선분까지의 거리 확인
            for seg_idx, segment in enumerate(tpipe_segments):
                # 선분의 각도 계산
                segment_angle = get_angle(segment[0], segment[1])
                
                # 텍스트와 선분의 각도가 유사한지 확인 (15도 이내)
                if not angles_are_similar(text_rotation, segment_angle, tolerance=15):
                    continue  # 각도가 맞지 않으면 스킵
                
                # 텍스트 BOX의 각 점에서 선분까지의 거리
                for corner in text_corners:
                    dist = point_to_line_distance(corner, segment[0], segment[1])
                    if dist < min_dist_to_tpipe:
                        min_dist_to_tpipe = dist
                        closest_segment = segment
                        closest_info = f"선분[{seg_idx}]의 corner (각도: {segment_angle:.1f}°)"
                
                # 텍스트 중심점에서도 거리 측정
                dist_center = point_to_line_distance(t_pos, segment[0], segment[1])
                if dist_center < min_dist_to_tpipe:
                    min_dist_to_tpipe = dist_center
                    closest_segment = segment
                    closest_info = f"선분[{seg_idx}]의 center (각도: {segment_angle:.1f}°)"
            
            if min_dist_to_tpipe <= max_distance and closest_segment:
                fall_texts.append(t)
                processed_texts.add(t)  # 처리된 텍스트로 표시
                
                # 디버깅 정보 출력
                rotation_info = f"(회전: {t.dxf.rotation:.1f}°)" if abs(t.dxf.rotation) > 1e-2 else "(수평)"
                layer_info = f"[레이어: {t.dxf.layer}]"
                color_info = f"[색상: {t.dxf.color}]"
                
                print(f"  [FT 발견] '{t.dxf.text}' {layer_info} {color_info} {rotation_info} - TPIPE 거리: {min_dist_to_tpipe:.3f} ({closest_info})")
                
                # TPIPE 레이어로 변경
                if t.dxf.layer != tpipe_layer_name:
                    old_layer = t.dxf.layer
                    old_color = t.dxf.color
                    t.dxf.layer = tpipe_layer_name
                    t.dxf.color = 4  # CYAN
                    changed_count += 1
                    print(f"    → {tpipe_layer_name}로 변경: 레이어 {old_layer}→{tpipe_layer_name}, 색상 {old_color}→4")
    
    print(f"  [FT 검색 결과] TPIPE {max_distance}mm 내에서 총 {len(fall_texts)}개의 FALL TEXT 발견 ({changed_count}개를 {tpipe_layer_name}로 변경)")
    
    return fall_texts

def find_fall_polyline_near_text(msp, text, processed_polylines):
    """텍스트와 가장 가까운 4점 FALL 레이어 폴리라인 찾기 (거리 제한 없음)"""
    insert = text.dxf.insert
    t_pos = Vec2(insert[0], insert[1])
    
    candidates = []
    
    for pl in msp.query('LWPOLYLINE POLYLINE'):
        if get_entity_layer(pl).upper() == 'FALL' and pl not in processed_polylines:
            pts = extract_points(pl)
            if len(pts) == 4:
                # 폴리라인의 각 점에서 텍스트까지의 최소 거리
                min_dist = float('inf')
                for pt in pts:
                    dist = distance(pt, t_pos)
                    if dist < min_dist:
                        min_dist = dist
                
                # 폴리라인의 중심에서 텍스트까지의 거리도 확인
                pl_center = Vec2(
                    sum(p.x for p in pts) / 4,
                    sum(p.y for p in pts) / 4
                )
                center_dist = distance(pl_center, t_pos)
                min_dist = min(min_dist, center_dist)
                
                candidates.append({
                    'polyline': pl,
                    'distance': min_dist
                })
                print(f"      [FL 후보] {get_entity_handle(pl)} - 거리: {min_dist:.3f}")
    
    # 가장 가까운 FL 반환
    if candidates:
        candidates.sort(key=lambda x: x['distance'])
        selected = candidates[0]
        print(f"    [FL 선택] {get_entity_handle(selected['polyline'])} - 거리: {selected['distance']:.3f}")
        return selected['polyline']
    else:
        print(f"    [FL 찾기 실패] 미사용 FALL 폴리라인 없음")
    
    return None

def find_fall_polyline_near_text_with_limit(msp, text, max_distance=20):
    """텍스트 근처의 4점 FALL 레이어 폴리라인 찾기 (거리 제한 있음, 초기 FALL 처리용)"""
    insert = text.dxf.insert
    t_pos = Vec2(insert[0], insert[1])
    
    candidates = []
    
    # 스케일 자동 조정을 위한 첫 번째 FALL 폴리라인 확인
    first_fall_pl = None
    for pl in msp.query('LWPOLYLINE POLYLINE'):
        if get_entity_layer(pl).upper() == 'FALL':
            pts = extract_points(pl)
            if len(pts) == 4:
                first_fall_pl = pl
                first_pts = pts
                break
    
    # 거리 스케일 조정
    adjusted_max_distance = max_distance
    if first_fall_pl:
        # 첫 번째 FALL 폴리라인의 크기 확인
        min_x = min(p.x for p in first_pts)
        max_x = max(p.x for p in first_pts)
        min_y = min(p.y for p in first_pts)
        max_y = max(p.y for p in first_pts)
        pl_size = max(max_x - min_x, max_y - min_y)
        
        if pl_size > 100:  # 폴리라인이 크면 스케일 조정
            scale_factor = pl_size / 10
            adjusted_max_distance = max_distance * scale_factor
            print(f"    [FL 거리 조정] {max_distance} → {adjusted_max_distance:.3f} (폴리라인 크기: {pl_size:.3f})")
    
    for pl in msp.query('LWPOLYLINE POLYLINE'):
        if get_entity_layer(pl).upper() == 'FALL':
            pts = extract_points(pl)
            if len(pts) == 4:
                # 폴리라인의 각 점에서 텍스트까지의 최소 거리
                min_dist = float('inf')
                for pt in pts:
                    dist = distance(pt, t_pos)
                    if dist < min_dist:
                        min_dist = dist
                
                # 폴리라인의 중심에서 텍스트까지의 거리도 확인
                pl_center = Vec2(
                    sum(p.x for p in pts) / 4,
                    sum(p.y for p in pts) / 4
                )
                center_dist = distance(pl_center, t_pos)
                min_dist = min(min_dist, center_dist)
                
                if min_dist <= adjusted_max_distance:
                    candidates.append({
                        'polyline': pl,
                        'distance': min_dist
                    })
                    print(f"      [FL 후보] {get_entity_handle(pl)} - 거리: {min_dist:.3f}")
    
    # 가장 가까운 FL 반환
    if candidates:
        candidates.sort(key=lambda x: x['distance'])
        selected = candidates[0]
        print(f"    [FL 선택] {get_entity_handle(selected['polyline'])} - 거리: {selected['distance']:.3f}")
        return selected['polyline']
    else:
        print(f"    [FL 찾기 실패] 조정된 거리 {adjusted_max_distance:.3f} 내에 FALL 폴리라인 없음")
    
    return None

def process_file(filepath):
    doc = ezdxf.readfile(filepath)
    msp = doc.modelspace()
    
    # DXF 파일의 단위 확인
    try:
        units = doc.header.get('$INSUNITS', 0)
        unit_names = {0: "없음", 1: "인치", 2: "피트", 3: "마일", 4: "밀리미터", 
                     5: "센티미터", 6: "미터", 7: "킬로미터", 8: "마이크로인치",
                     9: "밀", 10: "야드", 11: "옹스트롬", 12: "나노미터",
                     13: "마이크론", 14: "데시미터", 15: "데카미터", 16: "헥토미터",
                     17: "기가미터", 18: "천문단위", 19: "광년", 20: "파섹"}
        unit_name = unit_names.get(units, f"알 수 없음({units})")
        print(f"\n[DXF 파일 정보]")
        print(f"  파일명: {os.path.basename(filepath)}")
        print(f"  단위: {unit_name} (코드: {units})")
        
        # 단위가 mm가 아닌 경우 경고
        if units != 4 and units != 0:  # 4 = 밀리미터, 0 = 단위 없음
            print(f"  [경고] 파일 단위가 밀리미터가 아닙니다. 거리 계산이 부정확할 수 있습니다.")
    except:
        print(f"\n[DXF 파일 정보] 단위 정보를 읽을 수 없습니다.")
    
    # 삭제할 엔티티 리스트
    entities_to_delete = []
    
    # 모든 텍스트 수집 (간섭 체크용)
    all_texts = list(msp.query('TEXT'))
    
    # PIPE 엔티티 수집
    pipe_entities = []
    for entity in msp.query('LWPOLYLINE POLYLINE LINE'):
        if get_entity_layer(entity).upper() == 'PIPE':
            pipe_entities.append(entity)

    # FF 그룹 저장 (FT + FL)
    ff_groups = []

    # 1. FALL 레이어의 4점 폴리라인 찾기
    fall_polylines = []
    for pl in msp.query('LWPOLYLINE POLYLINE'):
        if get_entity_layer(pl).upper() == 'FALL':
            pts = extract_points(pl)
            if len(pts) == 4:
                fall_polylines.append(pl)
                print(f"[FALL 레이어] 4점 폴리라인 발견: {get_entity_handle(pl)}")

    # 각 FALL 폴리라인 처리
    for fall_pl in fall_polylines:
        fall_pts = extract_points(fall_pl)
        
        # FALL 폴리라인의 점 1번과 2번의 중심점 계산
        fall_p1_p2_center = Vec2(
            (fall_pts[0].x + fall_pts[1].x) / 2,
            (fall_pts[0].y + fall_pts[1].y) / 2
        )
        
        # FALL 중심 계산
        fall_center = Vec2(
            sum(p.x for p in fall_pts) / 4,
            sum(p.y for p in fall_pts) / 4
        )
        
        # 2. FALL 선분에 접하는 2점, 3점 폴리라인 찾기 및 분류
        g1_list = []  # 2점 폴리라인 + 점간거리 2.1 초과 3점 폴리라인
        ad1_list = []  # 점간거리 2.1 이하 3점 폴리라인
        ad1_groups = []  # AD1과 연관된 ARROW line들의 그룹
        
        for pl in msp.query('LWPOLYLINE POLYLINE'):
            if pl is fall_pl:  # FALL 자신은 제외
                continue
                
            pts = extract_points(pl)
            
            if not polyline_intersects_with_fall(pts, fall_pts):
                continue
            
            # 2점 폴리라인 → G1
            if len(pts) == 2:
                set_entity_layer(pl, "G1")
                set_entity_color(pl, 4)  # CYAN
                g1_list.append(pl)
                print(f"  [G1] 2점 폴리라인 발견: {get_entity_handle(pl)}")
            
            # 3점 폴리라인 → 점간 거리에 따라 분류
            elif len(pts) == 3:
                if check_all_segments_under_21(pts):
                    # 모든 점간 거리 2.1 이하 → AD1
                    set_entity_layer(pl, "AD1")
                    set_entity_color(pl, 3)  # GREEN
                    ad1_list.append(pl)
                    
                    # ARROW 레이어 line 찾기 (0.2mm 내, 1mm 이하)
                    arrow_lines = find_arrow_lines_near_points(msp, pts)
                    for arrow in arrow_lines:
                        set_entity_color(arrow, 3)  # GREEN
                    
                    ad1_groups.append({
                        'polyline': pl,
                        'arrows': arrow_lines
                    })
                    
                    print(f"  [AD1] 3점 폴리라인 발견 (점간거리≤2.1): {get_entity_handle(pl)}")
                    if arrow_lines:
                        print(f"    - 연관된 ARROW line {len(arrow_lines)}개 발견")
                else:
                    # 점간 거리 2.1 초과 → G1
                    set_entity_layer(pl, "G1")
                    set_entity_color(pl, 4)  # CYAN
                    g1_list.append(pl)
                    print(f"  [G1] 3점 폴리라인 발견 (점간거리>2.1): {get_entity_handle(pl)}")
        
        # 삭제 제외할 G1과 AD1 찾기
        exclude_from_deletion = set()
        
        for g1 in g1_list:
            g1_pts = extract_points(g1)
            if len(g1_pts) == 2 and g1_crosses_both_fall_segments(g1_pts, fall_pts):
                exclude_from_deletion.add(g1)
                print(f"  [삭제 제외] G1 {get_entity_handle(g1)} - FALL의 양쪽 선분 통과")
                
                # 이 G1과 접촉하는 AD1도 제외
                for ad1_group in ad1_groups:
                    ad1_pts = extract_points(ad1_group['polyline'])
                    if polylines_intersect(g1_pts, ad1_pts):
                        exclude_from_deletion.add(ad1_group['polyline'])
                        print(f"    [삭제 제외] AD1 {get_entity_handle(ad1_group['polyline'])} - 제외된 G1과 접촉")
        
        # 3. G1과 AD1에서 FALL TEXT 찾기 (개선된 방식)
        fall_text = None
        fall_o_text = None
        found_entities = []  # FALL TEXT를 찾은 모든 엔티티들
        found_ad1_groups = []  # FALL TEXT를 찾은 AD1 그룹들
        
        # G1 리스트에서 찾기 (BOX화 방식)
        for g1 in g1_list:
            g1_pts = extract_points(g1)
            
            # G1의 FALL로부터 가장 먼 점 찾기
            max_dist = 0
            far_point = None
            for pt in g1_pts:
                d = distance(pt, fall_center)
                if d > max_dist:
                    max_dist = d
                    far_point = pt
            
            if not far_point:
                continue
            
            # 먼 점 근처에서 FALL TEXT 찾기 (BOX화 방식, 100mm 범위)
            ct = find_fall_text_with_box(msp, far_point, max_distance=100)
            if ct:
                if not fall_text:  # 첫 번째 발견한 것만 처리용으로 저장
                    fall_text = ct
                found_entities.append(g1)
                print(f"  [FALL TEXT] G1에서 발견: '{ct.dxf.text}' at G1: {get_entity_handle(g1)}")
        
        # AD1에서도 찾기
        for ad1_group in ad1_groups:
            ad1_pts = extract_points(ad1_group['polyline'])
            
            # AD1의 FALL로부터 가장 먼 점 찾기
            max_dist = 0
            far_point = None
            for pt in ad1_pts:
                d = distance(pt, fall_center)
                if d > max_dist:
                    max_dist = d
                    far_point = pt
            
            if not far_point:
                continue
            
            # 먼 점 근처에서 FALL TEXT 찾기 (50mm로 확대, 회전 제한 없음)
            for t in msp.query('TEXT'):
                if 'FALL' in t.dxf.text.upper():  # 회전 각도 제한 제거
                    insert = t.dxf.insert
                    t_pos = Vec2(insert[0], insert[1])
                    
                    if distance(t_pos, far_point) <= 50:  # 20mm → 50mm
                        if not fall_text:  # 첫 번째 발견한 것만 처리용으로 저장
                            fall_text = t
                        found_entities.append(ad1_group['polyline'])
                        found_ad1_groups.append(ad1_group)
                        print(f"  [FALL TEXT] AD1에서 발견: '{t.dxf.text}' at AD1: {get_entity_handle(ad1_group['polyline'])}")
                        break
        
        # O 텍스트 찾기 (거리 제한 없이 가장 가까운 것)
        if fall_text:
            insert = fall_text.dxf.insert
            t_pos = Vec2(insert[0], insert[1])
            min_dist = float('inf')
            for o in msp.query('TEXT'):
                if o.dxf.text.strip().upper() == 'O':
                    try:
                        o_insert = o.dxf.insert
                        o_pos = Vec2(o_insert[0], o_insert[1])
                        dist = distance(o_pos, t_pos)
                        if dist < min_dist:  # 거리 제한 제거
                            min_dist = dist
                            fall_o_text = o
                    except:
                        continue
        
        if not fall_text:
            print(f"  [주의] FALL TEXT를 찾을 수 없습니다.")
            continue
        
        fall_insert = fall_text.dxf.insert
        fall_pos = Vec2(fall_insert[0], fall_insert[1])
        
        # 4. FALL 레이어에 가장 가까운 PIPE 레이어 찾기
        found_pipe = None
        pipe_p1, pipe_p2 = None, None
        min_pipe_dist = float('inf')
        pipe_angle = 0  # PIPE 각도 저장
        
        for pl in msp.query('LWPOLYLINE POLYLINE'):
            if get_entity_layer(pl).upper() != "PIPE":
                continue
            pts = extract_points(pl)
            
            if len(pts) == 2:
                for pt in pts:
                    d = distance(pt, fall_center)
                    if d < min_pipe_dist:
                        min_pipe_dist = d
                        found_pipe = pl
                        if distance(pts[0], fall_pos) <= distance(pts[1], fall_pos):
                            pipe_p1, pipe_p2 = pts[0], pts[1]
                        else:
                            pipe_p1, pipe_p2 = pts[1], pts[0]
        
        if not found_pipe:
            print(f"  [PIPE] 레이어를 찾을 수 없어 FALL 폴리라인을 사용합니다.")
            pipe_p1, pipe_p2 = fall_pts[0], fall_pts[1]
        else:
            print(f"  [PIPE] 레이어 발견: {get_entity_handle(found_pipe)}")
        
        # PIPE 각도 계산
        pipe_angle = get_angle(pipe_p1, pipe_p2)
        
        # 5. FALL TEXT 처리
        if not fall_text.dxf.text.endswith("°"):
            fall_text.dxf.text = fall_text.dxf.text + "°"
        
        if fall_o_text:
            try:
                msp.delete_entity(fall_o_text)
                print(f"  [삭제] O 텍스트")
            except Exception as e:
                print(f"  O 삭제 오류: {e}")
        
        # 회전 각도 계산
        angle = get_angle(pipe_p1, pipe_p2)
        rotate_angle = 180 - abs(angle) if angle < -120 else angle
        
        # FALL 텍스트 회전 및 이동
        rotate_text(fall_text, fall_pos, rotate_angle)
        current_insert = fall_text.dxf.insert
        current_pos = Vec2(current_insert[0], current_insert[1])
        move_text(fall_text, fall_p1_p2_center - current_pos)
        
        if angle < -120:
            move_text(fall_text, get_offset_by_angle(angle, 12))
            move_text(fall_text, get_perpendicular_offset(angle, 5.5))
        else:
            move_text(fall_text, get_offset_by_angle(angle, -5))
            move_text(fall_text, get_perpendicular_offset(angle, -5.5))
        
        # 텍스트가 뒤집혀 있는지 확인하고 180도 회전
        current_rotation = fall_text.dxf.rotation % 360
        if is_text_upside_down(current_rotation):
            rotate_text(fall_text, fall_p1_p2_center, 180)
            print(f"  [180도 회전] FALL TEXT가 뒤집혀 있어 180도 회전")
        
        fall_text.dxf.color = 1
        fall_text.dxf.layer = "RED"
        
        # 간섭 체크 및 최적 위치 찾기
        print(f"  [간섭 최적화] FALL TEXT 위치 최적화 시작...")
        find_optimal_text_position(fall_text, pipe_angle, msp, pipe_entities, all_texts)
        
        # 6. FALL TEXT를 찾는데 성공한 모든 G1과 AD1 삭제 (제외 대상 제외)
        for entity in found_entities:
            if entity not in exclude_from_deletion:
                entities_to_delete.append(entity)
                layer = get_entity_layer(entity)
                print(f"  [삭제 예정] {layer}: {get_entity_handle(entity)} (FALL TEXT 찾음)")
                
                # G1인 경우, 시작점 0.5mm 내의 AD1 찾기
                if layer == "G1":
                    g1_pts = extract_points(entity)
                    if g1_pts:
                        # G1 시작점에서 0.5mm 내의 AD1 찾기
                        near_ad1_groups = find_ad1_near_g1_start(g1_pts, ad1_groups, max_dist=0.5)
                        for ad1_group in near_ad1_groups:
                            if ad1_group['polyline'] not in exclude_from_deletion:
                                # AD1 삭제 예정에 추가
                                if ad1_group['polyline'] not in entities_to_delete:
                                    entities_to_delete.append(ad1_group['polyline'])
                                    print(f"    [G1 연관 삭제 예정] AD1: {get_entity_handle(ad1_group['polyline'])} (G1 시작점 0.5mm 내)")
                                
                                # AD1의 ARROW line들도 삭제 예정에 추가
                                for arrow in ad1_group['arrows']:
                                    if arrow not in entities_to_delete:
                                        entities_to_delete.append(arrow)
                                        print(f"    [G1 연관 삭제 예정] ARROW line: {get_entity_handle(arrow)}")
        
        # AD1가 직접 FALL TEXT를 찾은 경우의 ARROW line들도 삭제
        for ad1_group in found_ad1_groups:
            if ad1_group['polyline'] not in exclude_from_deletion:
                for arrow in ad1_group['arrows']:
                    if arrow not in entities_to_delete:
                        entities_to_delete.append(arrow)
                        print(f"  [삭제 예정] ARROW line: {get_entity_handle(arrow)} (AD1이 FALL TEXT 찾음)")
    
    # 7. TPIPE 기반 FF 찾기 및 중복 제거
    print("\n[TPIPE 기반 FF 검색 시작]")
    
    # TPIPE 처리 전 FALL TEXT 통계
    initial_fall_texts = [t for t in msp.query('TEXT') if 'FALL' in t.dxf.text.upper()]
    initial_red_count = sum(1 for t in initial_fall_texts if t.dxf.layer == "RED" and t.dxf.color == 1)
    print(f"[초기 상태] 전체 FALL TEXT: {len(initial_fall_texts)}개 (RED: {initial_red_count}개)")
    
    # 전체 FALL TEXT 색상 변경 통계
    total_fall_texts_changed = 0
    
    # 이미 처리된 텍스트와 폴리라인 추적
    processed_texts = set()
    processed_polylines = set()
    
    # 모든 PIPE 엔티티에 대해 TPIPE 생성
    processed_pipes = set()
    tpipe_count = 0  # TPIPE 번호 카운터
    
    for pipe in pipe_entities:
        if pipe in processed_pipes:
            continue
            
        # 연결된 모든 PIPE 찾기
        connected_pipes = find_connected_pipes(msp, pipe)
        for cp in connected_pipes:
            processed_pipes.add(cp)
        
        tpipe_count += 1
        tpipe_layer_name = f"TPIPE{tpipe_count}"
        
        print(f"\n[TPIPE{tpipe_count}] 총 {len(connected_pipes)}개의 연결된 PIPE 발견")
        
        # 연결된 PIPE들의 레이어를 TPIPE#로 변경
        for cp in connected_pipes:
            set_entity_layer(cp, tpipe_layer_name)
            print(f"  [레이어 변경] {get_entity_handle(cp)} → {tpipe_layer_name}")
        
        # TPIPE 선분 생성
        tpipe_segments = create_tpipe_segments(connected_pipes)
        
        # TPIPE에서 20mm 내의 FALL 텍스트 찾기
        print(f"\n  [TPIPE{tpipe_count} FALL TEXT 검색 시작]")
        
        # 거리 기준 20mm로 설정
        ft_list = find_fall_text_near_tpipe(msp, tpipe_segments, processed_texts, tpipe_layer_name, max_distance=20)
        
        total_fall_texts_changed += len(ft_list)
        
        # 이 TPIPE의 FF 후보들 저장
        tpipe_ff_candidates = []
        
        # 각 FT에 대해 FL 찾기 (거리 제한 없음)
        for ft in ft_list:
            fl = find_fall_polyline_near_text(msp, ft, processed_polylines)
            if fl:
                processed_polylines.add(fl)  # 처리된 폴리라인으로 표시
                
                # FL도 TPIPE 레이어로 변경
                old_fl_layer = fl.dxf.layer
                old_fl_color = fl.dxf.color
                fl.dxf.layer = tpipe_layer_name
                fl.dxf.color = 4  # CYAN
                print(f"    [FL 레이어 변경] {old_fl_layer}→{tpipe_layer_name}, 색상 {old_fl_color}→4")
                
                # TPIPE에서 FT까지의 최소 거리 계산
                ft_pos = Vec2(ft.dxf.insert[0], ft.dxf.insert[1])
                min_dist_to_tpipe = float('inf')
                
                for segment in tpipe_segments:
                    dist = point_to_line_distance(ft_pos, segment[0], segment[1])
                    min_dist_to_tpipe = min(min_dist_to_tpipe, dist)
                
                ff_groups.append({
                    'ft': ft,
                    'fl': fl,
                    'ft_text': ft.dxf.text,
                    'tpipe_num': tpipe_count,
                    'tpipe_layer': tpipe_layer_name,
                    'distance': min_dist_to_tpipe
                })
                print(f"  [FF 생성] FT: '{ft.dxf.text}' + FL: {get_entity_handle(fl)} ({tpipe_layer_name}, 거리: {min_dist_to_tpipe:.3f}mm)")
            else:
                print(f"  [경고] FT '{ft.dxf.text}'에 대한 미사용 FL을 찾을 수 없음")
    
    # 삭제 실행
    for entity in entities_to_delete:
        try:
            msp.delete_entity(entity)
            layer = get_entity_layer(entity)
            handle = get_entity_handle(entity)
            print(f"[삭제 완료] {layer}: {handle}")
        except Exception as e:
            print(f"삭제 오류: {e}")

    # 동일한 레이어의 중복 FT 제거 (FF와 별개로 모든 FT 검사)
    print("\n[동일 레이어 중복 FT 제거]")
    
    # 모든 FALL TEXT를 레이어별로 그룹화
    all_fall_texts = [t for t in msp.query('TEXT') if 'FALL' in t.dxf.text.upper()]
    ft_by_layer = {}
    
    for ft in all_fall_texts:
        layer = ft.dxf.layer
        if layer not in ft_by_layer:
            ft_by_layer[layer] = []
        ft_by_layer[layer].append(ft)
    
    # 각 레이어에서 중복 FT 제거
    for layer, layer_fts in ft_by_layer.items():
        if len(layer_fts) > 1:
            print(f"\n  [{layer}] {len(layer_fts)}개의 FALL TEXT 발견")
            
            # 각 FT의 위치와 텍스트 정보 수집
            ft_info_list = []
            for ft in layer_fts:
                ft_pos = Vec2(ft.dxf.insert[0], ft.dxf.insert[1])
                
                # TPIPE 레이어인 경우 해당 TPIPE와의 거리 계산
                min_dist = float('inf')
                if layer.startswith('TPIPE'):
                    # 해당 TPIPE의 엔티티들 찾기
                    for entity in msp.query('LWPOLYLINE POLYLINE LINE'):
                        if get_entity_layer(entity) == layer:
                            pts = extract_points(entity)
                            for i in range(len(pts) - 1):
                                dist = point_to_line_distance(ft_pos, pts[i], pts[i+1])
                                min_dist = min(min_dist, dist)
                
                ft_info_list.append({
                    'ft': ft,
                    'text': ft.dxf.text,
                    'distance': min_dist if min_dist != float('inf') else 0
                })
            
            # 거리 순으로 정렬 (가장 가까운 것 우선)
            ft_info_list.sort(key=lambda x: x['distance'])
            
            # 첫 번째만 유지하고 나머지 삭제
            print(f"    [유지] FT: '{ft_info_list[0]['text']}' (거리: {ft_info_list[0]['distance']:.3f}mm)")
            
            for i in range(1, len(ft_info_list)):
                ft_info = ft_info_list[i]
                try:
                    msp.delete_entity(ft_info['ft'])
                    print(f"    [삭제] FT: '{ft_info['text']}' (거리: {ft_info['distance']:.3f}mm)")
                except Exception as e:
                    print(f"    [삭제 오류] {e}")

    # 동일한 레이어의 중복 FF 제거 (FL도 함께 제거)
    print("\n[동일 레이어 중복 FF 제거]")
    
    # 레이어별로 FF 그룹화
    ff_by_layer = {}
    for ff in ff_groups:
        layer = ff['tpipe_layer']
        if layer not in ff_by_layer:
            ff_by_layer[layer] = []
        ff_by_layer[layer].append(ff)
    
    # 각 레이어에서 중복 제거
    for layer, layer_ffs in ff_by_layer.items():
        if len(layer_ffs) > 1:
            print(f"\n  [{layer}] {len(layer_ffs)}개의 FF 발견")
            
            # 거리 순으로 정렬 (가장 가까운 것 우선)
            layer_ffs.sort(key=lambda x: x['distance'])
            
            # 첫 번째만 유지하고 나머지의 FL만 삭제 (FT는 이미 위에서 처리됨)
            print(f"    [유지] FF: FT '{layer_ffs[0]['ft_text']}' + FL (거리: {layer_ffs[0]['distance']:.3f}mm)")
            
            for i in range(1, len(layer_ffs)):
                ff = layer_ffs[i]
                try:
                    # FL 삭제
                    msp.delete_entity(ff['fl'])
                    print(f"    [삭제] FL: {get_entity_handle(ff['fl'])}")
                except Exception as e:
                    print(f"    [FL 삭제 오류] {e}")

    # TPIPE 처리 요약
    print(f"\n[TPIPE 처리 요약]")
    print(f"  총 TPIPE 그룹 수: {tpipe_count}개")
    print(f"  TPIPE를 통해 변경된 FALL TEXT: {total_fall_texts_changed}개")
    
    # 마지막에 전체 FALL TEXT 통계 출력
    print("\n[전체 FALL TEXT 최종 통계]")
    final_fall_texts = [t for t in msp.query('TEXT') if 'FALL' in t.dxf.text.upper()]
    red_count = sum(1 for t in final_fall_texts if t.dxf.layer == "RED" and t.dxf.color == 1)
    tpipe_count_texts = sum(1 for t in final_fall_texts if t.dxf.layer.startswith("TPIPE"))
    other_count = len(final_fall_texts) - red_count - tpipe_count_texts
    
    print(f"  총 FALL TEXT 개수: {len(final_fall_texts)}개")
    print(f"  - RED 레이어 (색상 1): {red_count}개")
    print(f"  - TPIPE 레이어: {tpipe_count_texts}개")
    print(f"  - 기타: {other_count}개")
    
    if other_count > 0:
        print(f"\n  [RED/TPIPE가 아닌 FALL TEXT 목록]")
        for t in final_fall_texts:
            if t.dxf.layer != "RED" and not t.dxf.layer.startswith("TPIPE"):
                print(f"    '{t.dxf.text}' [레이어: {t.dxf.layer}] [색상: {t.dxf.color}]")
    
    # FALL 폴리라인 통계
    print("\n[FALL 폴리라인 최종 통계]")
    final_fall_polylines = [pl for pl in msp.query('LWPOLYLINE POLYLINE') 
                           if get_entity_layer(pl).upper() == 'FALL' or get_entity_layer(pl).startswith('TPIPE')]
    fall_layer_count = sum(1 for pl in final_fall_polylines if get_entity_layer(pl).upper() == 'FALL')
    tpipe_layer_count = sum(1 for pl in final_fall_polylines if get_entity_layer(pl).startswith('TPIPE'))
    
    print(f"  총 FALL 관련 폴리라인: {len(final_fall_polylines)}개")
    print(f"  - FALL 레이어: {fall_layer_count}개")
    print(f"  - TPIPE 레이어: {tpipe_layer_count}개")
    
    save_path = os.path.splitext(filepath)[0] + "_FALL.dxf"
    doc.saveas(save_path)
    print(f"\n✅ 처리 완료: {os.path.basename(save_path)}")

if __name__ == "__main__":
    files = select_dxf_files()
    if not files:
        print("❌ 선택된 파일이 없습니다.")
    else:
        for file in files:
            try:
                process_file(file)
            except Exception as e:
                print(f"파일 처리 중 오류 발생 ({os.path.basename(file)}): {e}")
        print("🎉 모든 파일 처리 완료.")