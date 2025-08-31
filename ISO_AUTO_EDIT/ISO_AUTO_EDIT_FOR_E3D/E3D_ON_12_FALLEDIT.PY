import ezdxf
import os
import math
import sys
from ezdxf.math import Vec2

def extract_points(entity):
    if entity.dxftype() == 'LWPOLYLINE':
        return [Vec2(x, y) for x, y, *_ in entity.get_points()]
    elif entity.dxftype() == 'POLYLINE':
        try:
            return [Vec2(v.dxf.location.x, v.dxf.location.y) for v in entity]
        except:
            return []
    return []

def distance(p1, p2):
    return math.hypot(p2.x - p1.x, p2.y - p1.y)

def get_angle(p1, p2):
    return math.degrees(math.atan2(p2.y - p1.y, p2.x - p1.x))

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
        if line.dxf.layer.upper() != 'ARROW':
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
        if line.dxf.layer.upper() == 'PIPE':
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
    
    # 간섭이 없으면 그대로 유지
    if min_interference == 0:
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
            
            # 간섭이 0이면 즉시 중단
            if interference == 0:
                break
    
    # 최적 위치로 이동
    if best_offset != 0:
        offset_vec = get_offset_by_angle(pipe_angle, best_offset)
        text.dxf.insert = (original_pos.x + offset_vec.x, 
                          original_pos.y + offset_vec.y, 0)
    else:
        # 원래 위치로 복원
        text.dxf.insert = (original_pos.x, original_pos.y, 0)

def process_file(filepath):
    doc = ezdxf.readfile(filepath)
    msp = doc.modelspace()
    
    # 삭제할 엔티티 리스트
    entities_to_delete = []
    
    # 모든 텍스트 수집 (간섭 체크용)
    all_texts = list(msp.query('TEXT'))
    
    # PIPE 엔티티 수집
    pipe_entities = []
    for entity in msp.query('LWPOLYLINE POLYLINE LINE'):
        if entity.dxf.layer.upper() == 'PIPE':
            pipe_entities.append(entity)

    # 1. FALL 레이어의 4점 폴리라인 찾기
    fall_polylines = []
    for pl in msp.query('LWPOLYLINE POLYLINE'):
        if pl.dxf.layer.upper() == 'FALL':
            pts = extract_points(pl)
            if len(pts) == 4:
                fall_polylines.append(pl)

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
                pl.dxf.layer = "G1"
                pl.dxf.color = 4  # CYAN
                g1_list.append(pl)
            
            # 3점 폴리라인 → 점간 거리에 따라 분류
            elif len(pts) == 3:
                if check_all_segments_under_21(pts):
                    # 모든 점간 거리 2.1 이하 → AD1
                    pl.dxf.layer = "AD1"
                    pl.dxf.color = 3  # GREEN
                    ad1_list.append(pl)
                    
                    # ARROW 레이어 line 찾기 (0.2mm 내, 1mm 이하)
                    arrow_lines = find_arrow_lines_near_points(msp, pts)
                    for arrow in arrow_lines:
                        arrow.dxf.color = 3  # GREEN
                    
                    ad1_groups.append({
                        'polyline': pl,
                        'arrows': arrow_lines
                    })
                else:
                    # 점간 거리 2.1 초과 → G1
                    pl.dxf.layer = "G1"
                    pl.dxf.color = 4  # CYAN
                    g1_list.append(pl)
        
        # 삭제 제외할 G1과 AD1 찾기
        exclude_from_deletion = set()
        
        for g1 in g1_list:
            g1_pts = extract_points(g1)
            if len(g1_pts) == 2 and g1_crosses_both_fall_segments(g1_pts, fall_pts):
                exclude_from_deletion.add(g1)
                
                # 이 G1과 접촉하는 AD1도 제외
                for ad1_group in ad1_groups:
                    ad1_pts = extract_points(ad1_group['polyline'])
                    if polylines_intersect(g1_pts, ad1_pts):
                        exclude_from_deletion.add(ad1_group['polyline'])
        
        # 3. G1과 AD1에서 FALL TEXT 찾기
        fall_text = None
        fall_o_text = None
        found_entities = []  # FALL TEXT를 찾은 모든 엔티티들
        found_ad1_groups = []  # FALL TEXT를 찾은 AD1 그룹들
        
        # G1 리스트에서 찾기
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
            
            # 먼 점 근처에서 FALL TEXT 찾기
            for t in msp.query('TEXT'):
                if 'FALL' in t.dxf.text.upper() and abs(t.dxf.rotation) < 1e-2:
                    insert = t.dxf.insert
                    t_pos = Vec2(insert[0], insert[1])
                    
                    if distance(t_pos, far_point) <= 20:
                        if not fall_text:  # 첫 번째 발견한 것만 처리용으로 저장
                            fall_text = t
                        found_entities.append(g1)
                        break
        
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
            
            # 먼 점 근처에서 FALL TEXT 찾기
            for t in msp.query('TEXT'):
                if 'FALL' in t.dxf.text.upper() and abs(t.dxf.rotation) < 1e-2:
                    insert = t.dxf.insert
                    t_pos = Vec2(insert[0], insert[1])
                    
                    if distance(t_pos, far_point) <= 20:
                        if not fall_text:  # 첫 번째 발견한 것만 처리용으로 저장
                            fall_text = t
                        found_entities.append(ad1_group['polyline'])
                        found_ad1_groups.append(ad1_group)
                        break
        
        # O 텍스트 찾기
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
                        if dist < min_dist and dist <= 20:
                            min_dist = dist
                            fall_o_text = o
                    except:
                        continue
        
        if not fall_text:
            continue
        
        fall_insert = fall_text.dxf.insert
        fall_pos = Vec2(fall_insert[0], fall_insert[1])
        
        # 4. FALL 레이어에 가장 가까운 PIPE 레이어 찾기
        found_pipe = None
        pipe_p1, pipe_p2 = None, None
        min_pipe_dist = float('inf')
        pipe_angle = 0  # PIPE 각도 저장
        
        for pl in msp.query('LWPOLYLINE POLYLINE'):
            if pl.dxf.layer.upper() != "PIPE":
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
            pipe_p1, pipe_p2 = fall_pts[0], fall_pts[1]
        
        # PIPE 각도 계산
        pipe_angle = get_angle(pipe_p1, pipe_p2)
        
        # 5. FALL TEXT 처리
        if not fall_text.dxf.text.endswith("°"):
            fall_text.dxf.text = fall_text.dxf.text + "°"
        
        if fall_o_text:
            try:
                msp.delete_entity(fall_o_text)
            except Exception as e:
                pass
        
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
        
        fall_text.dxf.color = 1
        fall_text.dxf.layer = "RED"
        
        # 간섭 체크 및 최적 위치 찾기
        find_optimal_text_position(fall_text, pipe_angle, msp, pipe_entities, all_texts)
        
        # 6. FALL TEXT를 찾는데 성공한 모든 G1과 AD1 삭제 (제외 대상 제외)
        for entity in found_entities:
            if entity not in exclude_from_deletion:
                entities_to_delete.append(entity)
                
                # G1인 경우, 시작점 0.5mm 내의 AD1 찾기
                if entity.dxf.layer == "G1":
                    g1_pts = extract_points(entity)
                    if g1_pts:
                        # G1 시작점에서 0.5mm 내의 AD1 찾기
                        near_ad1_groups = find_ad1_near_g1_start(g1_pts, ad1_groups, max_dist=0.5)
                        for ad1_group in near_ad1_groups:
                            if ad1_group['polyline'] not in exclude_from_deletion:
                                # AD1 삭제 예정에 추가
                                if ad1_group['polyline'] not in entities_to_delete:
                                    entities_to_delete.append(ad1_group['polyline'])
                                
                                # AD1의 ARROW line들도 삭제 예정에 추가
                                for arrow in ad1_group['arrows']:
                                    if arrow not in entities_to_delete:
                                        entities_to_delete.append(arrow)
        
        # AD1가 직접 FALL TEXT를 찾은 경우의 ARROW line들도 삭제
        for ad1_group in found_ad1_groups:
            if ad1_group['polyline'] not in exclude_from_deletion:
                for arrow in ad1_group['arrows']:
                    if arrow not in entities_to_delete:
                        entities_to_delete.append(arrow)
    
    # 삭제 실행
    for entity in entities_to_delete:
        try:
            msp.delete_entity(entity)
        except Exception as e:
            pass

    save_path = os.path.splitext(filepath)[0] + "_FALL.dxf"
    doc.saveas(save_path)

def main():
    if len(sys.argv) < 2:
        sys.exit(1)
    
    # 첫 번째 argument는 스크립트 이름이므로 제외
    dxf_files = sys.argv[1:]
    
    for dxf_file in dxf_files:
        if dxf_file.lower().endswith('.dxf'):
            try:
                process_file(dxf_file)
            except Exception as e:
                pass

if __name__ == "__main__":
    main()