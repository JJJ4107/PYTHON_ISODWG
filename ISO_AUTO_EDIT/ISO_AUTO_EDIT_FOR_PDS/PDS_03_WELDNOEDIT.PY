import ezdxf
import os
import math
from ezdxf.math import Vec2
from tkinter import Tk, filedialog

def distance(p1, p2):
    return math.hypot(p2.x - p1.x, p2.y - p1.y)

def point_to_segment_distance(p: Vec2, a: Vec2, b: Vec2) -> float:
    ap = p - a
    ab = b - a
    ab_len_squared = ab.dot(ab)
    if ab_len_squared == 0:
        return distance(p, a)
    t = max(0, min(1, ap.dot(ab) / ab_len_squared))
    projection = a + ab * t
    return distance(p, projection)

def get_line_angle(p1: Vec2, p2: Vec2) -> float:
    """두 점 사이의 각도를 라디안으로 반환"""
    return math.atan2(p2.y - p1.y, p2.x - p1.x)

def is_horizontal_text(text) -> bool:
    """텍스트가 수평(기울기 0)인지 확인"""
    if hasattr(text.dxf, 'rotation'):
        return abs(text.dxf.rotation) < 0.1  # 약간의 오차 허용
    return True

def get_text_bounding_box(text):
    """TEXT 엔티티의 바운딩 박스를 계산하는 함수"""
    try:
        # 텍스트의 기본 속성
        insert = Vec2(text.dxf.insert.x, text.dxf.insert.y)
        height = text.dxf.height
        
        # 텍스트 내용 길이 (대략적인 너비 계산)
        text_content = text.dxf.text
        width = len(text_content) * height * 0.7  # 대략적인 문자 너비 비율
        
        # 텍스트 정렬 방식 확인 (기본값은 LEFT)
        halign = text.dxf.halign if hasattr(text.dxf, 'halign') else 0
        valign = text.dxf.valign if hasattr(text.dxf, 'valign') else 0
        
        # 수평 정렬에 따른 바운딩 박스 계산
        if halign == 0:  # LEFT
            min_x = insert.x
            max_x = insert.x + width
        elif halign == 1:  # CENTER
            min_x = insert.x - width/2
            max_x = insert.x + width/2
        elif halign == 2:  # RIGHT
            min_x = insert.x - width
            max_x = insert.x
        else:
            min_x = insert.x
            max_x = insert.x + width
        
        # 수직 정렬에 따른 바운딩 박스 계산
        if valign == 0:  # BASELINE
            min_y = insert.y
            max_y = insert.y + height
        elif valign == 1:  # BOTTOM
            min_y = insert.y
            max_y = insert.y + height
        elif valign == 2:  # MIDDLE
            min_y = insert.y - height/2
            max_y = insert.y + height/2
        elif valign == 3:  # TOP
            min_y = insert.y - height
            max_y = insert.y
        else:
            min_y = insert.y
            max_y = insert.y + height
        
        # 바운딩 박스 중심
        center = Vec2((min_x + max_x)/2, (min_y + max_y)/2)
        
        return {
            'center': center,
            'width': width,
            'height': height,
            'min_x': min_x,
            'max_x': max_x,
            'min_y': min_y,
            'max_y': max_y
        }
    except Exception as e:
        print(f"텍스트 바운딩 박스 계산 오류: {e}")
        return None

def check_text_endpoint_interference(text_entity, msp, exclude_entities, min_distance=5.0, check_center=None, check_radius=25.0):
    """TEXT 엔티티의 시작점/끝점이 다른 TEXT의 시작점/끝점에서 5mm 이내면 간섭으로 판정 - 모든 레이어 포함"""
    try:
        # 현재 텍스트의 바운딩 박스
        bbox1 = get_text_bounding_box(text_entity)
        if not bbox1:
            return False
        
        # 체크 중심이 주어진 경우, 텍스트가 범위 내에 있는지 확인
        if check_center and distance(bbox1['center'], check_center) > check_radius:
            return False
        
        for e in msp:
            if e in exclude_entities or not hasattr(e, "dxf") or e.dxf is None:
                continue
            
            # 모든 TEXT/MTEXT 체크 - 레이어 구분 없음
            if e.dxftype() in ("TEXT", "MTEXT"):
                if e.dxftype() == "TEXT":
                    bbox2 = get_text_bounding_box(e)
                else:  # MTEXT
                    # MTEXT의 경우 insert point만 체크
                    insert_pos = Vec2(e.dxf.insert.x, e.dxf.insert.y)
                    bbox2 = {
                        'center': insert_pos,
                        'width': 5.0,  # 대략적인 크기
                        'height': 3.0
                    }
                
                if not bbox2:
                    continue
                
                other_center = bbox2['center']
                if check_center and distance(other_center, check_center) > check_radius:
                    continue
                
                # 바운딩 박스 중심 간 거리 체크
                center_distance = distance(bbox1['center'], bbox2['center'])
                # 두 텍스트의 크기를 고려한 최소 거리
                min_center_distance = max(bbox1['height'], bbox2['height']) * 1.5
                
                if center_distance < min_center_distance:
                    return True
        
        return False
    except Exception as e:
        print(f"텍스트 끝점 간섭 체크 오류: {e}")
        return False

def check_pipe_layer_interference(wc_entities, msp, exclude_entities, check_radius=25.0):
    """PIPE 또는 ELBO를 포함하는 레이어와의 간섭을 체크 (25mm 범위 내만)"""
    try:
        # WC 원 찾기
        wc_center = None
        for wc_entity in wc_entities:
            if wc_entity.dxftype() == 'CIRCLE' and wc_entity.dxf.radius == 3.0:  # 6mm 지름
                wc_center = Vec2(wc_entity.dxf.center.x, wc_entity.dxf.center.y)
                break
        
        if not wc_center:
            return False
        
        for wc_entity in wc_entities:
            if wc_entity.dxftype() == 'CIRCLE':
                circle_center = Vec2(wc_entity.dxf.center.x, wc_entity.dxf.center.y)
                circle_radius = wc_entity.dxf.radius
                
                # 모든 엔티티 검사
                for e in msp:
                    if e in exclude_entities or not hasattr(e, "dxf") or e.dxf is None:
                        continue
                    
                    # 레이어 이름에 PIPE, ELBO, 또는 다른 중요 키워드가 포함되어 있는지 확인
                    if hasattr(e.dxf, 'layer'):
                        layer_name = e.dxf.layer.upper()
                        # 더 많은 레이어 타입 체크
                        if any(keyword in layer_name for keyword in ['PIPE', 'ELBO', 'FITTING', 'VALVE', 'FLANGE']):
                            if e.dxftype() in ("LINE", "POLYLINE", "LWPOLYLINE", "ARC", "CIRCLE"):
                                # 선분과의 거리 체크
                                if e.dxftype() == "LINE":
                                    start = Vec2(e.dxf.start.x, e.dxf.start.y)
                                    end = Vec2(e.dxf.end.x, e.dxf.end.y)
                                    
                                    # 25mm 범위 내인지 확인
                                    if (distance(wc_center, start) > check_radius and 
                                        distance(wc_center, end) > check_radius):
                                        continue
                                    
                                    dist = point_to_segment_distance(circle_center, start, end)
                                    if dist < circle_radius:
                                        return True
                                elif e.dxftype() == "ARC":
                                    arc_center = Vec2(e.dxf.center.x, e.dxf.center.y)
                                    if distance(wc_center, arc_center) <= check_radius:
                                        if distance(circle_center, arc_center) < (e.dxf.radius + circle_radius):
                                            return True
                                elif e.dxftype() == "CIRCLE":
                                    entity_center = Vec2(e.dxf.center.x, e.dxf.center.y)
                                    if distance(wc_center, entity_center) <= check_radius:
                                        if distance(circle_center, entity_center) < (e.dxf.radius + circle_radius):
                                            return True
                                else:
                                    # 폴리라인
                                    if e.dxftype() == "POLYLINE":
                                        pts = [Vec2(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]
                                    else:
                                        pts = [Vec2(x, y) for x, y, *_ in e.get_points()]
                                    
                                    # 25mm 범위 내에 점이 있는지 확인
                                    in_range = False
                                    for pt in pts:
                                        if distance(wc_center, pt) <= check_radius:
                                            in_range = True
                                            break
                                    
                                    if in_range:
                                        for i in range(len(pts) - 1):
                                            dist = point_to_segment_distance(circle_center, pts[i], pts[i+1])
                                            if dist < circle_radius:
                                                return True
        
        return False
    except Exception as e:
        print(f"PIPE/ELBO 레이어 간섭 체크 오류: {e}")
        return False

def check_30degree_polyline_interference(wc_entities, msp, exclude_entities, check_radius=25.0):
    """30도 단위 정각도를 가진 폴리라인/LW폴리라인과의 간섭을 체크 (25mm 범위 내만)"""
    try:
        # WC 원 찾기
        wc_center = None
        for wc_entity in wc_entities:
            if wc_entity.dxftype() == 'CIRCLE' and wc_entity.dxf.radius == 3.0:
                wc_center = Vec2(wc_entity.dxf.center.x, wc_entity.dxf.center.y)
                break
        
        if not wc_center:
            return False
        
        for wc_entity in wc_entities:
            if wc_entity.dxftype() == 'CIRCLE':
                circle_center = Vec2(wc_entity.dxf.center.x, wc_entity.dxf.center.y)
                circle_radius = wc_entity.dxf.radius
                
                # 모든 폴리라인 검사
                for e in msp.query("POLYLINE LWPOLYLINE"):
                    if e in exclude_entities or not hasattr(e, "dxf") or e.dxf is None:
                        continue
                    
                    # 폴리라인의 점들 가져오기
                    if e.dxftype() == "POLYLINE":
                        pts = [Vec2(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]
                    else:
                        pts = [Vec2(x, y) for x, y, *_ in e.get_points()]
                    
                    if len(pts) < 2:
                        continue
                    
                    # 25mm 범위 내에 있는지 확인
                    in_range = False
                    for pt in pts:
                        if distance(wc_center, pt) <= check_radius:
                            in_range = True
                            break
                    
                    if not in_range:
                        continue
                    
                    # 각 선분의 각도 체크
                    for i in range(len(pts) - 1):
                        p1, p2 = pts[i], pts[i+1]
                        
                        # 선분의 각도 계산 (라디안)
                        dx = p2.x - p1.x
                        dy = p2.y - p1.y
                        angle_rad = math.atan2(dy, dx)
                        
                        # 각도를 0~360도로 변환
                        angle_deg = math.degrees(angle_rad) % 360
                        
                        # 30도 단위로 반올림
                        nearest_30 = round(angle_deg / 30) * 30
                        
                        # 정확히 30도 단위인지 확인 (오차 1도 이내)
                        if abs(angle_deg - nearest_30) < 1.0:
                            # 원과 선분의 거리 체크
                            dist = point_to_segment_distance(circle_center, p1, p2)
                            if dist < circle_radius:
                                return True
        
        return False
    except Exception as e:
        print(f"30도 단위 폴리라인 간섭 체크 오류: {e}")
        return False

def check_circle_to_segments_distance(circle_center, circle_radius, segments, min_distance=1.0):
    """원과 선분들 사이의 최소 거리가 min_distance 이하인지 확인"""
    for start, end in segments:
        # 원의 중심에서 선분까지의 거리
        dist_to_segment = point_to_segment_distance(circle_center, start, end)
        
        # 원의 외곽에서 선분까지의 거리 = 중심에서 선분까지의 거리 - 반지름
        dist_from_circle_edge = dist_to_segment - circle_radius
        
        # 선분이 원 내부를 통과하는 경우도 간섭으로 처리
        if dist_to_segment < circle_radius:
            return True
        
        # 원의 외곽에서 선분까지의 거리가 min_distance 이하면 간섭
        if dist_from_circle_edge <= min_distance:
            return True
    
    return False

def get_iso_orthogonal_angle(wa_angle_deg):
    """ISO 도면에서 WA 각도에 대한 직교 각도를 반환"""
    # WA 각도를 0-360 범위로 정규화
    wa_angle_norm = wa_angle_deg % 360
    
    # 가장 가까운 30도 단위 각도로 반올림
    nearest_30 = round(wa_angle_norm / 30) * 30
    nearest_30 = nearest_30 % 360
    
    # 배관 ISO 도면의 직교 관계 매핑
    iso_orthogonal_map = {
        0: [90, 270],      # 0° (수평) → 90°, 270° (수직)
        30: [330],         # 30° → 330° (ISO 표준 직교)
        60: [150, 330],    # 60° → 150°, 330°
        90: [270],         # 90° → 270° (ISO 표준 직교)
        120: [30, 210],    # 120° → 30°, 210°
        150: [210],        # 150° → 210° (ISO 표준 직교)
        180: [90, 270],    # 180° (수평) → 90°, 270° (수직)
        210: [150],        # 210° → 150° (ISO 표준 직교)
        240: [150, 330],   # 240° → 150°, 330°
        270: [90],         # 270° → 90° (ISO 표준 직교)
        300: [30, 210],    # 300° → 30°, 210°
        330: [30],         # 330° → 30° (ISO 표준 직교)
    }
    
    if nearest_30 in iso_orthogonal_map:
        return iso_orthogonal_map[nearest_30]
    else:
        # 기본값: 90°, 270° (수직 방향)
        return [90, 270]

def calculate_wa_line_to_pipe_angle(wa_angle, pipe_lines):
    """WA 라인과 PIPE 라인 사이의 각도 차이를 계산하고 ISO 도면 직교성을 평가"""
    if not pipe_lines:
        return None
    
    orthogonality_score = float('inf')  # 0이 완벽한 직교
    best_pipe_angle = 0
    best_target_angle = 0
    
    # WA 라인의 각도 (도 단위)
    wa_angle_deg = math.degrees(wa_angle) % 360
    
    # WA 각도에 대한 ISO 직교 각도들 가져오기
    orthogonal_angles = get_iso_orthogonal_angle(wa_angle_deg)
    
    for pipe in pipe_lines:
        for segment in pipe['segments']:
            start, end = segment
            pipe_angle = math.atan2(end.y - start.y, end.x - start.x)
            pipe_angle_deg = math.degrees(pipe_angle) % 360
            
            # PIPE 각도와 각 직교 각도와의 차이 계산
            for ortho_angle in orthogonal_angles:
                diff = abs(pipe_angle_deg - ortho_angle)
                if diff > 180:
                    diff = 360 - diff
                
                if diff < orthogonality_score:
                    orthogonality_score = diff
                    best_pipe_angle = pipe_angle_deg
                    best_target_angle = ortho_angle
    
    return {
        'orthogonality_score': orthogonality_score,  # 0에 가까울수록 직교에 가까움
        'pipe_angle': best_pipe_angle,
        'target_angle': best_target_angle,  # 목표 직교 각도
        'wa_angle': wa_angle_deg,
        'orthogonal_angles': orthogonal_angles  # 가능한 직교 각도들
    }

def check_interference_at_position_detailed(test_center, msp, exclude_entities, weld_radius=3.0, check_radius=25.0):
    """특정 위치에서의 간섭을 체크하는 함수 (상세 정보 포함)"""
    interference_count = 0
    interference_details = []
    
    for e in msp:
        if e in exclude_entities or not hasattr(e, "dxf") or e.dxf is None:
            continue
        
        # 엔티티가 25mm 범위 밖이면 건너뛰기 (빠른 필터링)
        if hasattr(e, 'dxf'):
            entity_pos = None
            max_entity_radius = 0
            
            if e.dxftype() == "CIRCLE":
                entity_pos = Vec2(e.dxf.center.x, e.dxf.center.y)
                max_entity_radius = e.dxf.radius
            elif e.dxftype() in ("TEXT", "MTEXT"):
                entity_pos = Vec2(e.dxf.insert.x, e.dxf.insert.y)
            elif e.dxftype() == "LINE":
                # 선분의 중점
                start = Vec2(e.dxf.start.x, e.dxf.start.y)
                end = Vec2(e.dxf.end.x, e.dxf.end.y)
                entity_pos = Vec2((start.x + end.x) / 2, (start.y + end.y) / 2)
                max_entity_radius = distance(start, end) / 2
            elif e.dxftype() == "INSERT":  # 블록 참조
                entity_pos = Vec2(e.dxf.insert.x, e.dxf.insert.y)
            elif e.dxftype() == "DIMENSION":  # 치수선
                if hasattr(e.dxf, 'defpoint'):
                    entity_pos = Vec2(e.dxf.defpoint.x, e.dxf.defpoint.y)
            
            # 대략적인 거리로 범위 밖 엔티티 필터링
            if entity_pos and distance(test_center, entity_pos) > check_radius + max_entity_radius + weld_radius:
                continue
        
        layer_name = e.dxf.layer if hasattr(e.dxf, 'layer') else 'NO_LAYER'
        interference_found = False
        
        if e.dxftype() in ("TEXT", "MTEXT"):
            # 원과 텍스트 간의 거리 체크
            text_pos = Vec2(e.dxf.insert.x, e.dxf.insert.y)
            if distance(test_center, text_pos) < weld_radius:
                interference_count += 1
                interference_found = True
                
        elif e.dxftype() == "LINE":
            # LINE 엔티티와의 간섭 체크 - DIMLINES 레이어 포함
            start = Vec2(e.dxf.start.x, e.dxf.start.y)
            end = Vec2(e.dxf.end.x, e.dxf.end.y)
            
            # 25mm 범위 내인지 확인
            if (distance(test_center, start) <= check_radius or 
                distance(test_center, end) <= check_radius or
                point_to_segment_distance(test_center, start, end) <= check_radius):
                
                # 선분과의 거리가 weld_radius 이내면 간섭
                if point_to_segment_distance(test_center, start, end) < weld_radius:
                    interference_count += 1
                    interference_found = True
                
        elif e.dxftype() in ("POLYLINE", "LWPOLYLINE"):
            if e.dxftype() == "POLYLINE":
                pts = [Vec2(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]
            else:
                pts = [Vec2(x, y) for x, y, *_ in e.get_points()]
            
            # 폴리라인이 25mm 범위 내에 있는지 확인
            in_range = False
            for pt in pts:
                if distance(test_center, pt) <= check_radius:
                    in_range = True
                    break
            
            if in_range:
                for i in range(len(pts) - 1):
                    if point_to_segment_distance(test_center, pts[i], pts[i+1]) < weld_radius:
                        interference_count += 1
                        interference_found = True
                        break
                    
        elif e.dxftype() == "CIRCLE":
            circle_center = Vec2(e.dxf.center.x, e.dxf.center.y)
            if distance(circle_center, test_center) < (e.dxf.radius + weld_radius):
                interference_count += 1
                interference_found = True
                
        elif e.dxftype() == "ARC":
            # ARC 엔티티 체크
            arc_center = Vec2(e.dxf.center.x, e.dxf.center.y)
            if distance(arc_center, test_center) < (e.dxf.radius + weld_radius):
                interference_count += 1
                interference_found = True
                
        elif e.dxftype() == "INSERT":
            # 블록 참조 체크
            insert_pos = Vec2(e.dxf.insert.x, e.dxf.insert.y)
            if distance(test_center, insert_pos) < weld_radius:
                interference_count += 1
                interference_found = True
                
        elif e.dxftype() == "DIMENSION":
            # 치수선 체크
            try:
                # 치수선의 여러 점들 체크
                if hasattr(e.dxf, 'defpoint'):
                    defpoint = Vec2(e.dxf.defpoint.x, e.dxf.defpoint.y)
                    if distance(test_center, defpoint) < weld_radius:
                        interference_count += 1
                        interference_found = True
                if not interference_found and hasattr(e.dxf, 'defpoint2'):
                    defpoint2 = Vec2(e.dxf.defpoint2.x, e.dxf.defpoint2.y)
                    if distance(test_center, defpoint2) < weld_radius:
                        interference_count += 1
                        interference_found = True
                if not interference_found and hasattr(e.dxf, 'defpoint3'):
                    defpoint3 = Vec2(e.dxf.defpoint3.x, e.dxf.defpoint3.y)
                    if distance(test_center, defpoint3) < weld_radius:
                        interference_count += 1
                        interference_found = True
            except:
                pass
        
        if interference_found:
            interference_details.append(f"{e.dxftype()}/{layer_name}")
    
    return interference_count, interference_details

def check_interference_at_position(test_center, msp, exclude_entities, weld_radius=3.0, check_radius=25.0):
    """특정 위치에서의 간섭을 체크하는 함수 (기존 인터페이스 유지)"""
    count, _ = check_interference_at_position_detailed(test_center, msp, exclude_entities, weld_radius, check_radius)
    return count > 0

def find_pipe_lines_near_ws(ws_center, msp, search_radius=5.0):
    """WS 근처의 PIPE 선을 찾는 함수"""
    pipe_lines = []
    
    try:
        # LINE 검색
        for entity in msp.query('LINE'):
            try:
                if hasattr(entity.dxf, 'layer'):
                    layer_name = entity.dxf.layer.upper()
                    if 'PIPE' in layer_name:
                        start = Vec2(entity.dxf.start.x, entity.dxf.start.y)
                        end = Vec2(entity.dxf.end.x, entity.dxf.end.y)
                        
                        # WS 중심에서의 거리
                        dist_to_start = distance(ws_center, start)
                        dist_to_end = distance(ws_center, end)
                        min_dist = min(dist_to_start, dist_to_end)
                        
                        if min_dist <= search_radius:
                            pipe_lines.append({
                                'entity': entity,
                                'type': 'LINE',
                                'segments': [(start, end)],
                                'min_distance': min_dist
                            })
            except Exception:
                continue
        
        # POLYLINE/LWPOLYLINE 검색
        for poly in msp.query("POLYLINE LWPOLYLINE"):
            try:
                if hasattr(poly.dxf, 'layer'):
                    layer_name = poly.dxf.layer.upper()
                    if 'PIPE' in layer_name:
                        if poly.dxftype() == "POLYLINE":
                            points = [Vec2(v.dxf.location.x, v.dxf.location.y) for v in poly.vertices]
                        else:
                            points = [Vec2(x, y) for x, y, *_ in poly.get_points()]
                        
                        if len(points) >= 2:
                            # 모든 점들에 대해 최소 거리 계산
                            min_dist = float('inf')
                            for pt in points:
                                dist = distance(ws_center, pt)
                                min_dist = min(min_dist, dist)
                            
                            if min_dist <= search_radius:
                                segments = []
                                for i in range(len(points) - 1):
                                    segments.append((points[i], points[i+1]))
                                
                                pipe_lines.append({
                                    'entity': poly,
                                    'type': poly.dxftype(),
                                    'segments': segments,
                                    'min_distance': min_dist
                                })
            except Exception:
                continue
        
        # 거리가 가까운 순으로 정렬하여 상위 2개만 선택
        pipe_lines.sort(key=lambda x: x['min_distance'])
        pipe_lines = pipe_lines[:2]
        
        print(f"   WS 근처 PIPE 검색 완료: {len(pipe_lines)}개 발견")
        
    except Exception as e:
        print(f"PIPE 선 찾기 오류: {e}")
        pipe_lines = []
    
    return pipe_lines

def check_wc_interference_with_priority(wc_entities, ws_center, rotation_angle, msp, exclude_entities, pipe_lines=None):
    """우선순위 기반 WC 간섭 체크 - 각 간섭 유형별로 별도 체크"""
    try:
        # 임시로 회전시켜서 간섭 체크
        temp_positions = []
        
        # 모든 엔티티의 현재 위치 백업
        for entity in wc_entities:
            if entity.dxftype() == 'CIRCLE':
                temp_positions.append({
                    'entity': entity,
                    'type': 'CIRCLE',
                    'original': (entity.dxf.center.x, entity.dxf.center.y, 0)
                })
            elif entity.dxftype() == 'TEXT':
                temp_positions.append({
                    'entity': entity,
                    'type': 'TEXT',
                    'original': (entity.dxf.insert.x, entity.dxf.insert.y, 0)
                })
            elif entity.dxftype() == 'LINE':
                temp_positions.append({
                    'entity': entity,
                    'type': 'LINE',
                    'original_start': (entity.dxf.start.x, entity.dxf.start.y, 0),
                    'original_end': (entity.dxf.end.x, entity.dxf.end.y, 0)
                })
        
        # 임시로 회전
        for entity in wc_entities:
            rotate_entity_around_point(entity, ws_center, rotation_angle)
        
        # 회전 후 WT 텍스트를 WC 원 중심으로 재정렬
        wc_circle = None
        wt_texts = []
        
        for entity in wc_entities:
            if entity.dxftype() == 'CIRCLE' and entity.dxf.radius == 3.0:  # 6mm 지름
                wc_circle = entity
            elif entity.dxftype() == 'TEXT':
                # 텍스트가 수평인지 확인
                if is_horizontal_text(entity):
                    wt_texts.append(entity)
        
        if wc_circle and wt_texts:
            wc_center = Vec2(wc_circle.dxf.center.x, wc_circle.dxf.center.y)
            for txt in wt_texts:
                bbox = get_text_bounding_box(txt)
                if bbox:
                    offset = wc_center - bbox['center']
                    new_insert = Vec2(txt.dxf.insert.x + offset.x, 
                                    txt.dxf.insert.y + offset.y)
                    txt.dxf.insert = (new_insert.x, new_insert.y, 0)
        
        # 회전 후 WC 중심 위치
        wc_center_for_check = Vec2(wc_circle.dxf.center.x, wc_circle.dxf.center.y) if wc_circle else ws_center
        
        # WA 라인의 각도 계산 (WS에서 WC로의 방향)
        wa_angle = math.atan2(wc_center_for_check.y - ws_center.y, 
                             wc_center_for_check.x - ws_center.x)
        
        # PIPE와의 직교성 계산
        pipe_angle_info = calculate_wa_line_to_pipe_angle(wa_angle, pipe_lines)
        
        # 각 간섭 유형별로 체크
        has_text_interference = False
        has_pipe_layer_interference = False
        has_pc_circle_interference = False
        has_30degree_polyline_interference = False
        general_interference_score = 0
        
        # 1. TEXT 간섭 체크 (최우선) - 25mm 범위 내만
        for entity in wc_entities:
            if entity.dxftype() == 'TEXT':
                if check_text_endpoint_interference(entity, msp, exclude_entities + wc_entities, 5.0, wc_center_for_check, 25.0):
                    has_text_interference = True
                    break
        
        # 2. PIPE/ELBO 레이어 간섭 체크 (두번째 우선순위) - 25mm 범위 내만
        has_pipe_layer_interference = check_pipe_layer_interference(wc_entities, msp, exclude_entities + wc_entities, 25.0)
        
        # 3. PIPE와 WC 원 사이 1mm 체크 (세번째 우선순위)
        if pipe_lines:
            for entity in wc_entities:
                if entity.dxftype() == 'CIRCLE' and entity.dxf.radius == 3.0:  # WC 원 (6mm 지름)
                    center = Vec2(entity.dxf.center.x, entity.dxf.center.y)
                    for pipe in pipe_lines:
                        if check_circle_to_segments_distance(center, entity.dxf.radius, pipe['segments'], 1.0):
                            has_pc_circle_interference = True
                            break
                    if has_pc_circle_interference:
                        break
        
        # 4. 30도 단위 정각도 폴리라인 간섭 체크 (네번째 우선순위) - 25mm 범위 내만
        has_30degree_polyline_interference = check_30degree_polyline_interference(wc_entities, msp, exclude_entities + wc_entities, 25.0)
        
        # 5. 일반 간섭 점수 계산 (최하위 우선순위) - 25mm 범위 내만
        general_interference_details = []
        for entity in wc_entities:
            if entity.dxftype() == 'CIRCLE':
                center = Vec2(entity.dxf.center.x, entity.dxf.center.y)
                # WC 원의 경우 반지름을 약간 늘려서 체크 (여유 공간 확보)
                check_radius_adjusted = entity.dxf.radius + 1.0  # 1mm 여유
                interference_count, details = check_interference_at_position_detailed(center, msp, exclude_entities + wc_entities, check_radius_adjusted, 25.0)
                general_interference_score += interference_count
                if details:
                    general_interference_details.extend(details)
        
        # 원래 위치로 복구
        for backup in temp_positions:
            if backup['type'] == 'CIRCLE':
                backup['entity'].dxf.center = backup['original']
            elif backup['type'] == 'TEXT':
                backup['entity'].dxf.insert = backup['original']
            elif backup['type'] == 'LINE':
                backup['entity'].dxf.start = backup['original_start']
                backup['entity'].dxf.end = backup['original_end']
        
        return {
            'text_interference': has_text_interference,
            'pipe_layer_interference': has_pipe_layer_interference,
            'pc_circle_interference': has_pc_circle_interference,
            '30degree_polyline_interference': has_30degree_polyline_interference,
            'general_score': general_interference_score,
            'general_details': general_interference_details,
            'pipe_angle_info': pipe_angle_info
        }
        
    except Exception as e:
        print(f"우선순위 기반 간섭 체크 오류: {e}")
        return {
            'text_interference': True,
            'pipe_layer_interference': True,
            'pc_circle_interference': True,
            '30degree_polyline_interference': True,
            'general_score': 999,
            'general_details': [],
            'pipe_angle_info': None
        }

def rotate_entity_around_point(entity, center, angle):
    """엔티티를 특정 점을 중심으로 회전시키는 함수"""
    try:
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        
        if entity.dxftype() == 'CIRCLE':
            # 원의 중심점 회전
            old_center = Vec2(entity.dxf.center.x, entity.dxf.center.y)
            dx = old_center.x - center.x
            dy = old_center.y - center.y
            new_x = center.x + dx * cos_a - dy * sin_a
            new_y = center.y + dx * sin_a + dy * cos_a
            entity.dxf.center = (new_x, new_y, 0)
            
        elif entity.dxftype() == 'TEXT':
            # 텍스트 삽입점 회전
            old_pos = Vec2(entity.dxf.insert.x, entity.dxf.insert.y)
            dx = old_pos.x - center.x
            dy = old_pos.y - center.y
            new_x = center.x + dx * cos_a - dy * sin_a
            new_y = center.y + dx * sin_a + dy * cos_a
            entity.dxf.insert = (new_x, new_y, 0)
            
        elif entity.dxftype() == 'LINE':
            # 선의 시작점과 끝점 회전
            start = Vec2(entity.dxf.start.x, entity.dxf.start.y)
            end = Vec2(entity.dxf.end.x, entity.dxf.end.y)
            
            # 시작점 회전
            dx = start.x - center.x
            dy = start.y - center.y
            new_start_x = center.x + dx * cos_a - dy * sin_a
            new_start_y = center.y + dx * sin_a + dy * cos_a
            
            # 끝점 회전
            dx = end.x - center.x
            dy = end.y - center.y
            new_end_x = center.x + dx * cos_a - dy * sin_a
            new_end_y = center.y + dx * sin_a + dy * cos_a
            
            entity.dxf.start = (new_start_x, new_start_y, 0)
            entity.dxf.end = (new_end_x, new_end_y, 0)
            
    except Exception as e:
        print(f"엔티티 회전 오류: {e}")

def add_wt_text_to_wc_centered(msp, wc_center, text_value, height, color, layer, doc=None):
    """'00' 텍스트를 (0,0)에 생성하여 중심을 계산한 후 WC 중심으로 이동"""
    try:
        # TXT 스타일이 없으면 생성
        if doc and "TXT" not in doc.styles:
            try:
                doc.styles.new("TXT")
            except:
                pass
        
        # 1. (0,0)에 '00' 텍스트 생성
        text = msp.add_text(
            text_value,
            dxfattribs={
                'height': height,
                'color': color,
                'layer': layer,
                'insert': (0, 0, 0),
                'halign': 0,  # LEFT
                'valign': 0,  # BASELINE
                'style': 'TXT' if doc else 'Standard',
                'width': 0.85  # 폭비율 0.85
            }
        )
        
        # 2. 바운딩 박스를 계산하여 텍스트의 실제 중심 구하기
        bbox = get_text_bounding_box(text)
        
        if bbox:
            # 3. 텍스트 중심과 WC 중심의 차이 계산
            text_center = bbox['center']
            offset_x = wc_center[0] - text_center.x
            offset_y = wc_center[1] - text_center.y
            
            # 4. 텍스트를 WC 중심으로 이동
            current_insert = Vec2(text.dxf.insert.x, text.dxf.insert.y)
            new_insert = current_insert + Vec2(offset_x, offset_y)
            text.dxf.insert = (new_insert.x, new_insert.y, 0)
            
            return text
        else:
            # 바운딩 박스 계산 실패 시 기본 중앙 정렬
            text.dxf.halign = 4  # CENTER
            text.dxf.valign = 2  # MIDDLE
            text.dxf.insert = (wc_center[0], wc_center[1], 0)
            return text
            
    except Exception as e:
        print(f"WT 텍스트 생성 오류: {e}")
        # fallback: 기본 방식
        try:
            return msp.add_text(
                text_value,
                dxfattribs={
                    'height': height,
                    'color': color,
                    'layer': layer,
                    'insert': (wc_center[0], wc_center[1], 0),
                    'halign': 4,  # CENTER
                    'valign': 2,  # MIDDLE
                    'style': 'TXT' if doc else 'Standard',
                    'width': 0.85
                }
            )
        except:
            return None

def add_wt_text_to_wc(msp, center, text_value, height, color, layer, doc=None):
    """WC 중심에 WT 텍스트를 생성하는 함수 (첨부 코드의 add_text_to_node와 완전 동일)"""
    try:
        if doc and "ARIAL" not in doc.styles:
            try:
                doc.styles.new("ARIAL", dxfattribs={"font": "arial.ttf"})
            except:
                pass
        txt = msp.add_text(
            text_value,
            dxfattribs={
                'height': height,
                'color': color,
                'layer': layer,
                'insert': (0, 0, 0),
                'halign': 4,
                'valign': 2,
                'style': 'ARIAL' if doc else 'Standard',
                'width': 0.85
            }
        )
        try:
            from ezdxf.math import Matrix44
            txt.transform(Matrix44.translate(center[0], center[1], 0))
            return txt
        except:
            try:
                msp.delete_entity(txt)
            except:
                pass
            return msp.add_text(
                text_value,
                dxfattribs={
                    'height': height,
                    'color': color,
                    'layer': layer,
                    'insert': (center[0], center[1], 0),
                    'halign': 4,
                    'valign': 2,
                    'style': 'ARIAL' if doc else 'Standard',
                    'width': 0.85
                }
            )
    except:
        try:
            return msp.add_text(
                text_value,
                dxfattribs={'height': height, 'color': color, 'layer': layer, 'insert': (center[0], center[1], 0), 'halign': 4, 'valign': 2}
            )
        except:
            return None

def create_text_box(msp, text_entity, box_layer="WT_BOX"):
    """텍스트 주변에 박스를 생성하는 함수"""
    try:
        bbox = get_text_bounding_box(text_entity)
        if not bbox:
            return None
        
        # 박스 여백 (텍스트 높이의 10%)
        margin = text_entity.dxf.height * 0.1
        
        # 박스 좌표
        box_min_x = bbox['min_x'] - margin
        box_max_x = bbox['max_x'] + margin
        box_min_y = bbox['min_y'] - margin
        box_max_y = bbox['max_y'] + margin
        
        # 박스 생성 (POLYLINE으로 닫힌 사각형)
        points = [
            (box_min_x, box_min_y),
            (box_max_x, box_min_y),
            (box_max_x, box_max_y),
            (box_min_x, box_max_y),
            (box_min_x, box_min_y)  # 닫힌 폴리라인
        ]
        
        polyline = msp.add_lwpolyline(points, dxfattribs={
            'layer': box_layer,
            'color': 4  # CYAN
        })
        
        return polyline
        
    except Exception as e:
        print(f"텍스트 박스 생성 오류: {e}")
        return None

if __name__ == "__main__":
    # 디버깅을 위한 정보 출력
    import sys
    print("=" * 50)
    print("실행 파일:", sys.argv[0])
    print("Python 버전:", sys.version)
    print("현재 작업 디렉토리:", os.getcwd())
    print("=" * 50)
    
    # 파일 선택 창이 몇 번 열리는지 확인
    print("\n[디버깅] 파일 선택 창을 여는 중... (이 메시지가 두 번 나오면 문제)")
    
    # Tkinter 초기화 및 파일 선택
    try:
        root = Tk()
        root.withdraw()
        print("[디버깅] Tkinter 초기화 완료")
        
        filepaths = filedialog.askopenfilenames(
            title="DXF 파일을 선택하세요",
            filetypes=[("DXF Files", "*.dxf")]
        )
        
        root.destroy()  # Tkinter 창 완전히 종료
        print(f"[디버깅] 파일 선택 완료 - 선택된 파일: {len(filepaths)}개")
        
        # 선택된 파일 목록 출력
        print("\n[디버깅] 선택된 파일 목록:")
        for i, fp in enumerate(filepaths):
            print(f"  {i+1}. {fp}")
        
        # 중복 파일 제거
        unique_filepaths = list(set(filepaths))
        if len(unique_filepaths) != len(filepaths):
            print(f"\n[경고] 중복 파일 발견! {len(filepaths)}개 → {len(unique_filepaths)}개로 정리")
            filepaths = unique_filepaths
        
    except Exception as e:
        print(f"[오류] 파일 선택 중 오류 발생: {e}")
        exit()
    
    if not filepaths:
        print("선택된 파일이 없습니다.")
        exit()

    print("\n=== 파일 처리 시작 ===")
    print(f"총 {len(filepaths)}개 파일 처리 예정\n")
    
    # 각 파일 처리
    processed_files = []  # 처리된 파일 추적
    
    for idx, filepath in enumerate(filepaths):
        print(f"\n{'='*60}")
        print(f"[{idx+1}/{len(filepaths)}] 파일 처리 시작")
        print(f"파일 경로: {filepath}")
        print(f"{'='*60}")
        
        # 이미 처리된 파일인지 확인
        if filepath in processed_files:
            print(f"이미 처리된 파일입니다. 건너뜁니다.")
            continue
        
        processed_files.append(filepath)
        print(f"\n처리 중: {os.path.basename(filepath)}")
        
        try:
            doc = ezdxf.readfile(filepath)
            msp = doc.modelspace()
        except Exception as e:
            print(f"파일 읽기 오류: {e}")
            continue
    
        # 파라미터 설정
        ws_radius = 1.25  # WS 원 반지름 (지름 2.5mm)
        wc_radius = 3.0   # WC 원 반지름 (지름 6mm)
        move_distance = 8.5  # 수직 이동 거리 (8.5mm)
        interference_check_radius = 25.0  # 간섭 체크 범위 (25mm)
        
        ws_circles = []  # WS 원 저장
        wc_groups = []   # WC 그룹 저장
        
        # 1. WS 찾기: WELD 레이어의 원 (지름 2.5mm)
        for circle in msp.query("CIRCLE"):
            if (hasattr(circle.dxf, 'layer') and 
                circle.dxf.layer.upper() == "WELD" and 
                abs(circle.dxf.radius - ws_radius) < 0.1):  # 반지름 1.25mm ± 0.1mm
                
                ws_center = Vec2(circle.dxf.center.x, circle.dxf.center.y)
                
                # 2. WC 생성: WS 중심에 CYAN 6mm 원
                wc_circle = msp.add_circle(
                    center=(ws_center.x, ws_center.y),
                    radius=wc_radius,
                    dxfattribs={'layer': 'WC', 'color': 4}  # CYAN
                )
                
                # 3. WC를 수직으로 10mm 이동 (Y축 방향으로 위쪽)
                moved_center = Vec2(ws_center.x, ws_center.y + move_distance)
                wc_circle.dxf.center = (moved_center.x, moved_center.y, 0)
                
                # 4. WT 텍스트 생성: '00' 텍스트의 실제 중심을 계산하여 WC 중심에 정확히 배치
                wt_text = add_wt_text_to_wc_centered(msp, (moved_center.x, moved_center.y), '00', 2.5, 2, 'WT', doc)  # color=2 (YELLOW)
                
                # WC 그룹 저장 (간섭 체크용)
                wc_entities = [wc_circle, wt_text] if wt_text else [wc_circle]
                
                wc_groups.append({
                    'ws_circle': circle,
                    'ws_center': ws_center,
                    'wc_circle': wc_circle,
                    'wc_center': moved_center,
                    'wt_text': wt_text,
                    'entities': wc_entities
                })
                
                ws_circles.append(circle)
        
        print(f"WS 원 발견: {len(ws_circles)}개")
        print(f"WC 그룹 생성: {len(wc_groups)}개")
        
        if not wc_groups:
            print("처리할 WS 원이 없습니다.")
            continue
        
        print(f"\nWC 회전 처리 시작 - 총 {len(wc_groups)}개 그룹")
        
        # 각 WC 그룹에 대해 회전 처리
        failed_wc_count = 0
        
        for i, wc_group in enumerate(wc_groups):
            try:
                ws_center = wc_group['ws_center']
                wc_center = wc_group['wc_center']
                wc_entities = wc_group['entities']
                
                print(f"\n[{i+1}/{len(wc_groups)}] WC 처리: WS({ws_center.x:.2f}, {ws_center.y:.2f}) -> WC({wc_center.x:.2f}, {wc_center.y:.2f})")
                
                # WS 근처의 PIPE 선 찾기
                pipe_lines = find_pipe_lines_near_ws(ws_center, msp, 5.0)
                
                # 디버깅: PIPE 선 정보 출력
                if pipe_lines:
                    print(f"   PIPE 정보:")
                    for j, pipe in enumerate(pipe_lines):
                        if pipe['segments']:
                            start, end = pipe['segments'][0]
                            angle = math.degrees(math.atan2(end.y - start.y, end.x - start.x)) % 360
                            iso_angles = get_iso_orthogonal_angle(angle)
                            print(f"     - PIPE{j+1} 각도: {angle:.1f}° (ISO 직교: {iso_angles})")
                
                # 간섭 체크를 위한 제외 엔티티 (WS + WC 그룹)
                exclude_entities = [wc_group['ws_circle']] + wc_entities
                
                print(f"   간섭 체크 시작 (25mm 범위 내)")
                
                # 현재 위치(0도)에서 간섭 체크
                current_interference = check_wc_interference_with_priority(
                    wc_entities, ws_center, 0, msp, exclude_entities, pipe_lines
                )
                
                print(f"   현재 위치 간섭 상태:")
                print(f"   - TEXT 간섭: {current_interference['text_interference']}")
                print(f"   - PIPE/ELBO 레이어 간섭: {current_interference['pipe_layer_interference']}")
                print(f"   - PIPE-WC 거리 문제: {current_interference['pc_circle_interference']}")
                print(f"   - 30도 폴리라인 간섭: {current_interference['30degree_polyline_interference']}")
                print(f"   - 일반 간섭 점수: {current_interference['general_score']}")
                
                # 모든 회전 각도에서 간섭 정보 수집 (0도 포함)
                rotation_candidates = []
                for degree in range(0, 360, 30):
                    angle = math.radians(degree)
                    interference_info = check_wc_interference_with_priority(
                        wc_entities, ws_center, angle, msp, exclude_entities, pipe_lines
                    )
                    rotation_candidates.append({
                        'angle': angle,
                        'degree': degree,
                        'interference': interference_info
                    })
                
                # 최적 위치 선택 - ISO 직교 절대 우선
                best_candidate = None
                
                print(f"\n   ISO 직교 위치 우선 체크")
                
                # 현재 WA 라인의 각도 계산
                wa_angle = math.atan2(wc_center.y - ws_center.y, wc_center.x - ws_center.x)
                wa_angle_deg = math.degrees(wa_angle) % 360
                
                # ISO 직교 각도들 가져오기
                iso_orthogonal_angles = get_iso_orthogonal_angle(wa_angle_deg)
                print(f"   WA 각도: {wa_angle_deg:.1f}°, ISO 직교 목표: {iso_orthogonal_angles}")
                
                # 각 회전 각도를 ISO 직교와의 차이로 정렬
                rotation_candidates_sorted = []
                for candidate in rotation_candidates:
                    degree = candidate['degree']
                    # 각 ISO 직교 각도와의 최소 차이 계산
                    min_diff_from_ortho = float('inf')
                    for ortho_angle in iso_orthogonal_angles:
                        # WA가 회전한 후의 각도
                        rotated_wa_angle = (wa_angle_deg + degree) % 360
                        diff = abs(rotated_wa_angle - ortho_angle)
                        if diff > 180:
                            diff = 360 - diff
                        min_diff_from_ortho = min(min_diff_from_ortho, diff)
                    
                    rotation_candidates_sorted.append({
                        'candidate': candidate,
                        'ortho_diff': min_diff_from_ortho
                    })
                
                # ISO 직교에 가까운 순으로 정렬
                rotation_candidates_sorted.sort(key=lambda x: (x['ortho_diff'], x['candidate']['degree']))
                
                # 정렬된 순서대로 간섭 체크
                for sorted_item in rotation_candidates_sorted:
                    candidate = sorted_item['candidate']
                    interference = candidate['interference']
                    
                    # 간섭이 없으면 즉시 선택
                    if (not interference['text_interference'] and
                        not interference['pipe_layer_interference'] and
                        not interference['pc_circle_interference'] and
                        not interference['30degree_polyline_interference'] and
                        interference['general_score'] == 0):
                        
                        best_candidate = candidate
                        print(f"   {candidate['degree']}도에서 간섭 없음 (직교 차이: {sorted_item['ortho_diff']:.1f}도)")
                        break
                    else:
                        # 간섭 정보 출력
                        interference_types = []
                        if interference['text_interference']:
                            interference_types.append("TEXT")
                        if interference['pipe_layer_interference']:
                            interference_types.append("PIPE층")
                        if interference['pc_circle_interference']:
                            interference_types.append("PIPE거리")
                        if interference['30degree_polyline_interference']:
                            interference_types.append("30도선")
                        if interference['general_score'] > 0:
                            interference_types.append(f"일반({interference['general_score']})")
                        
                        print(f"   {candidate['degree']}도: 간섭={', '.join(interference_types)} (직교 차이: {sorted_item['ortho_diff']:.1f}도)")
                
                # 간섭 없는 위치를 찾지 못한 경우 - 간섭이 가장 적은 위치 선택
                if not best_candidate:
                    print(f"\n   모든 위치에서 간섭 발생 - 간섭이 가장 적은 위치 선택")
                    
                    # 우선순위별로 최적 위치 찾기
                    candidates_no_text = [c for c in rotation_candidates_sorted 
                                        if not c['candidate']['interference']['text_interference']]
                    
                    if candidates_no_text:
                        candidates_no_pipe = [c for c in candidates_no_text 
                                            if not c['candidate']['interference']['pipe_layer_interference']]
                        
                        if candidates_no_pipe:
                            candidates_no_pc = [c for c in candidates_no_pipe 
                                              if not c['candidate']['interference']['pc_circle_interference']]
                            
                            if candidates_no_pc:
                                candidates_no_30deg = [c for c in candidates_no_pc 
                                                     if not c['candidate']['interference']['30degree_polyline_interference']]
                                
                                if candidates_no_30deg:
                                    candidates_no_30deg.sort(key=lambda x: x['candidate']['interference']['general_score'])
                                    best_candidate = candidates_no_30deg[0]['candidate']
                                else:
                                    candidates_no_pc.sort(key=lambda x: x['candidate']['interference']['general_score'])
                                    best_candidate = candidates_no_pc[0]['candidate']
                            else:
                                candidates_no_pipe.sort(key=lambda x: x['candidate']['interference']['general_score'])
                                best_candidate = candidates_no_pipe[0]['candidate']
                        else:
                            candidates_no_text.sort(key=lambda x: x['candidate']['interference']['general_score'])
                            best_candidate = candidates_no_text[0]['candidate']
                    else:
                        rotation_candidates_sorted.sort(key=lambda x: (
                            x['candidate']['interference']['text_interference'],
                            x['candidate']['interference']['pipe_layer_interference'],
                            x['candidate']['interference']['pc_circle_interference'],
                            x['candidate']['interference']['30degree_polyline_interference'],
                            x['candidate']['interference']['general_score'],
                            x['ortho_diff']
                        ))
                        best_candidate = rotation_candidates_sorted[0]['candidate']
                    
                    print(f"   차선책: {best_candidate['degree']}도 선택")
                
                if not best_candidate:
                    print(f"   적절한 위치를 찾을 수 없음 - SKIP")
                    failed_wc_count += 1
                    continue
                
                # 선택된 각도로 회전
                final_angle = best_candidate['angle']
                final_degree = best_candidate['degree']
                
                # 간섭 상태 출력
                final_interference = best_candidate['interference']
                print(f"\n   최종 선택: {final_degree}도")
                
                # WC 회전 실행 (회전이 필요한 경우만)
                if final_angle != 0:
                    for entity in wc_entities:
                        rotate_entity_around_point(entity, ws_center, final_angle)
                    
                    # 회전 후 WT 텍스트를 WC 원 중심에 정확히 재정렬
                    wc_center_after_rotation = Vec2(wc_group['wc_circle'].dxf.center.x, wc_group['wc_circle'].dxf.center.y)
                    wt_text = wc_group['wt_text']
                    if wt_text:
                        # 기존 텍스트 삭제 후 새로운 위치에 정확한 중심으로 재생성
                        try:
                            msp.delete_entity(wt_text)
                        except:
                            pass
                        # 정확한 중심 정렬로 재생성
                        wc_group['wt_text'] = add_wt_text_to_wc_centered(
                            msp, (wc_center_after_rotation.x, wc_center_after_rotation.y), '00', 2.5, 2, 'WT', doc
                        )
                    
                    print(f"   WC를 {final_degree}도 회전 완료")
                else:
                    print(f"   현재 위치가 최적 - 회전 불필요")
                
                # 회전된 WC 위치
                rotated_wc_center = Vec2(wc_group['wc_circle'].dxf.center.x, wc_group['wc_circle'].dxf.center.y)
                
                # WA 선 생성 (WS에서 WC로)
                new_wa_line = msp.add_line(
                    start=(ws_center.x, ws_center.y),
                    end=(rotated_wc_center.x, rotated_wc_center.y),
                    dxfattribs={'layer': 'WA'}
                )
                
                # WC 원 안의 WA 라인 제거 (TRIM)
                try:
                    direction = rotated_wc_center - ws_center
                    if direction.magnitude > 0:
                        direction_normalized = direction.normalize()
                        # WC 원의 가장자리까지만 그리기
                        trim_distance = direction.magnitude - wc_radius
                        if trim_distance > 0:
                            trim_end = ws_center + direction_normalized * trim_distance
                            new_wa_line.dxf.end = (trim_end.x, trim_end.y, 0)
                            print(f"   WA 라인을 WC 원 가장자리에서 TRIM 완료")
                    
                    # 최종 거리 확인
                    final_distance = distance(ws_center, rotated_wc_center)
                    print(f"   최종 WS-WC 거리: {final_distance:.2f}mm")
                    
                except Exception as trim_e:
                    print(f"   WA 라인 TRIM 오류: {trim_e}")
                
                print(f"   WC 회전 및 WA 재생성 완료")
                
            except Exception as e:
                print(f"WC 처리 중 오류: {e}")
                failed_wc_count += 1
                continue
        
        # 파일 저장
        output_path = os.path.splitext(filepath)[0] + "_wc_processed.dxf"
        doc.saveas(output_path)
        print(f"저장된 파일: {output_path}")
        
        # 처리 결과 요약
        print(f"\n처리 결과 요약:")
        print(f"   - 전체 WC 그룹: {len(wc_groups)}개")
        print(f"   - 처리 실패: {failed_wc_count}개")
        print(f"   - 성공적으로 처리: {len(wc_groups) - failed_wc_count}개")

    print(f"\n{'='*60}")
    print("모든 파일 처리 완료")
    print(f"{'='*60}")