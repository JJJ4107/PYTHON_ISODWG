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

def get_text_start_end_points(text):
    """TEXT 엔티티의 시작점과 끝점을 계산하는 함수"""
    try:
        # 텍스트 기본 속성
        insert = Vec2(text.dxf.insert.x, text.dxf.insert.y)
        height = text.dxf.height
        text_content = text.dxf.text
        
        # 텍스트 너비 계산 (대략적인 비율)
        width = len(text_content) * height * 0.7
        
        # 회전 각도 (라디안)
        rotation = text.dxf.rotation if hasattr(text.dxf, 'rotation') else 0
        rotation_rad = math.radians(rotation)
        
        # 정렬 방식
        halign = text.dxf.halign if hasattr(text.dxf, 'halign') else 0
        
        # 기본 시작점과 끝점 (회전 전)
        if halign == 0:  # LEFT
            start_x = 0
            end_x = width
        elif halign == 1:  # CENTER
            start_x = -width/2
            end_x = width/2
        elif halign == 2:  # RIGHT
            start_x = -width
            end_x = 0
        else:
            start_x = 0
            end_x = width
        
        # 회전 적용
        cos_r = math.cos(rotation_rad)
        sin_r = math.sin(rotation_rad)
        
        # 시작점
        start_rotated_x = start_x * cos_r
        start_rotated_y = start_x * sin_r
        start_point = Vec2(insert.x + start_rotated_x, insert.y + start_rotated_y)
        
        # 끝점
        end_rotated_x = end_x * cos_r
        end_rotated_y = end_x * sin_r
        end_point = Vec2(insert.x + end_rotated_x, insert.y + end_rotated_y)
        
        return start_point, end_point
        
    except Exception as e:
        print(f"텍스트 시작/끝점 계산 오류: {e}")
        return None, None

def check_text_endpoint_interference(text_entity, msp, exclude_entities, min_distance=5.0, check_center=None, check_radius=25.0):
    """TEXT 엔티티의 시작점/끝점이 다른 TEXT의 시작점/끝점에서 5mm 이내면 간섭으로 판정 - 모든 레이어 포함"""
    try:
        # 현재 텍스트의 시작점과 끝점
        start1, end1 = get_text_start_end_points(text_entity)
        if not start1 or not end1:
            return False
        
        # 체크 중심이 주어진 경우, 텍스트가 범위 내에 있는지 확인
        text_center = Vec2((start1.x + end1.x) / 2, (start1.y + end1.y) / 2)
        if check_center and distance(text_center, check_center) > check_radius:
            return False
        
        # 현재 텍스트의 바운딩 박스도 가져오기
        bbox1 = get_text_bounding_box(text_entity)
        if not bbox1:
            return False
        
        for e in msp:
            if e in exclude_entities or not hasattr(e, "dxf") or e.dxf is None:
                continue
            
            # 모든 TEXT/MTEXT 체크 - 레이어 구분 없음
            if e.dxftype() in ("TEXT", "MTEXT"):
                # 상대 텍스트도 범위 내에 있는지 확인
                if e.dxftype() == "TEXT":
                    start2, end2 = get_text_start_end_points(e)
                    if not start2 or not end2:
                        continue
                    bbox2 = get_text_bounding_box(e)
                else:  # MTEXT
                    # MTEXT의 경우 insert point만 체크
                    insert_pos = Vec2(e.dxf.insert.x, e.dxf.insert.y)
                    start2 = end2 = insert_pos
                    bbox2 = None
                
                other_center = Vec2((start2.x + end2.x) / 2, (start2.y + end2.y) / 2)
                if check_center and distance(other_center, check_center) > check_radius:
                    continue
                
                # 1. 끝점 간 거리 체크 (기존 방식)
                endpoints_too_close = (
                    distance(start1, start2) < min_distance or
                    distance(start1, end2) < min_distance or
                    distance(end1, start2) < min_distance or
                    distance(end1, end2) < min_distance
                )
                
                # 2. 바운딩 박스 중심 간 거리 체크 (추가)
                bbox_too_close = False
                if bbox1 and bbox2:
                    center_distance = distance(bbox1['center'], bbox2['center'])
                    # 두 텍스트의 크기를 고려한 최소 거리
                    # 텍스트 높이 기준으로 최소 거리 계산
                    min_center_distance = max(bbox1['height'], bbox2['height']) * 1.5
                    bbox_too_close = center_distance < min_center_distance
                
                if endpoints_too_close or bbox_too_close:
                    return True
        
        return False
    except Exception as e:
        print(f"텍스트 끝점 간섭 체크 오류: {e}")
        return False

def check_pipe_layer_interference(wd_entities, msp, exclude_entities, check_radius=25.0):
    """PIPE 또는 ELBO를 포함하는 레이어와의 간섭을 체크 (25mm 범위 내만)"""
    try:
        # WDC 원 찾기
        wdc_center = None
        for wd_entity in wd_entities:
            if wd_entity.dxftype() == 'CIRCLE' and 1.5 <= wd_entity.dxf.radius <= 3.2:  # 지름 3~6.4mm
                wdc_center = Vec2(wd_entity.dxf.center.x, wd_entity.dxf.center.y)
                break
        
        if not wdc_center:
            return False
        
        for wd_entity in wd_entities:
            if wd_entity.dxftype() == 'CIRCLE':
                circle_center = Vec2(wd_entity.dxf.center.x, wd_entity.dxf.center.y)
                circle_radius = wd_entity.dxf.radius
                
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
                                    if (distance(wdc_center, start) > check_radius and 
                                        distance(wdc_center, end) > check_radius):
                                        continue
                                    
                                    dist = point_to_segment_distance(circle_center, start, end)
                                    if dist < circle_radius:
                                        return True
                                elif e.dxftype() == "ARC":
                                    arc_center = Vec2(e.dxf.center.x, e.dxf.center.y)
                                    if distance(wdc_center, arc_center) <= check_radius:
                                        if distance(circle_center, arc_center) < (e.dxf.radius + circle_radius):
                                            return True
                                elif e.dxftype() == "CIRCLE":
                                    entity_center = Vec2(e.dxf.center.x, e.dxf.center.y)
                                    if distance(wdc_center, entity_center) <= check_radius:
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
                                        if distance(wdc_center, pt) <= check_radius:
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

def check_30degree_polyline_interference(wd_entities, msp, exclude_entities, check_radius=25.0):
    """30도 단위 정각도를 가진 폴리라인/LW폴리라인과의 간섭을 체크 (25mm 범위 내만)"""
    try:
        # WDC 원 찾기
        wdc_center = None
        for wd_entity in wd_entities:
            if wd_entity.dxftype() == 'CIRCLE' and 1.5 <= wd_entity.dxf.radius <= 3.2:  # 지름 3~6.4mm
                wdc_center = Vec2(wd_entity.dxf.center.x, wd_entity.dxf.center.y)
                break
        
        if not wdc_center:
            return False
        
        for wd_entity in wd_entities:
            if wd_entity.dxftype() == 'CIRCLE':
                circle_center = Vec2(wd_entity.dxf.center.x, wd_entity.dxf.center.y)
                circle_radius = wd_entity.dxf.radius
                
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
                        if distance(wdc_center, pt) <= check_radius:
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
    """ISO 도면에서 WA 각도에 대한 직교 각도를 반환
    배관 ISO 도면의 표준 직교 관계:
    - 30° ↔ 330° (서로 직교)
    - 90° ↔ 270° (서로 직교)
    - 150° ↔ 210° (서로 직교)
    """
    
    # WA 각도를 0-360 범위로 정규화
    wa_angle_norm = wa_angle_deg % 360
    
    # 가장 가까운 30도 단위 각도로 반올림
    nearest_30 = round(wa_angle_norm / 30) * 30
    nearest_30 = nearest_30 % 360
    
    # 배관 ISO 도면의 직교 관계 매핑
    # 각 WA 각도에 대해 가능한 PIPE 직교 각도들
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
    """WA 라인과 PIPE 라인 사이의 각도 차이를 계산하고 ISO 도면 직교성을 평가
    배관 ISO 도면의 표준 직교 관계 사용:
    - 30° ↔ 330°
    - 90° ↔ 270°
    - 150° ↔ 210°
    """
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
        
        # 레이어별 제외 없음 - DIMLINES 포함 모든 레이어 체크
        
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
            
            # 20mm 범위 내인지 확인
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
            
            # 폴리라인이 20mm 범위 내에 있는지 확인
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
                
        elif e.dxftype() == "LEADER":
            # 지시선 체크
            try:
                if hasattr(e, 'vertices'):
                    for vertex in e.vertices:
                        vertex_pos = Vec2(vertex[0], vertex[1])
                        if distance(test_center, vertex_pos) < weld_radius:
                            interference_count += 1
                            interference_found = True
                            break
            except:
                pass
                
        elif e.dxftype() == "SPLINE":
            # 스플라인 체크
            try:
                if hasattr(e, 'control_points'):
                    for cp in e.control_points:
                        cp_pos = Vec2(cp[0], cp[1])
                        if distance(test_center, cp_pos) < weld_radius:
                            interference_count += 1
                            interference_found = True
                            break
            except:
                pass
                
        elif e.dxftype() == "ELLIPSE":
            # 타원 체크
            try:
                ellipse_center = Vec2(e.dxf.center.x, e.dxf.center.y)
                if distance(test_center, ellipse_center) < weld_radius:
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

def find_welds_along_line(start_point, end_point, msp, used_welds_circles, max_search_distance=50.0):
    """A1 선을 따라 WELDS를 찾는 함수"""
    best_welds = None
    best_distance = float('inf')
    
    # 선의 방향 벡터
    direction = end_point - start_point
    line_length = direction.magnitude
    
    if line_length > 0:
        direction_normalized = direction.normalize()
        
        # WELDS 검색
        for circle in msp.query('CIRCLE'):
            if (hasattr(circle.dxf, 'layer') and circle.dxf.layer == 'WELDS' and
                0.75 <= circle.dxf.radius <= 1.0):  # 반지름 0.75-1.0 = 지름 1.5-2mm
                
                circle_center = Vec2(circle.dxf.center.x, circle.dxf.center.y)
                
                # 1. 선의 연장선상에 있는지 확인
                # 시작점에서 원까지의 벡터
                to_circle = circle_center - start_point
                
                # 선의 방향으로의 투영 거리
                projection_distance = to_circle.dot(direction_normalized)
                
                # 투영점 계산
                projection_point = start_point + direction_normalized * projection_distance
                
                # 원과 투영점 사이의 거리 (선에서 벗어난 정도)
                perpendicular_distance = distance(circle_center, projection_point)
                
                # 선상 또는 가까운 위치에 있는지 확인 (2mm 허용)
                if perpendicular_distance <= 2.0:
                    # 시작점으로부터의 거리
                    distance_from_start = distance(start_point, circle_center)
                    
                    # 최대 검색 거리 내에 있고, 가장 가까운 WELDS 선택
                    if distance_from_start <= max_search_distance and distance_from_start < best_distance:
                        if circle not in used_welds_circles:
                            best_welds = circle
                            best_distance = distance_from_start
    
    return best_welds, best_distance

def find_pipe_lines_near_sw(sw_center, msp, search_radius=5.0):
    """SW 근처의 PIPE 선을 찾는 함수"""
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
                        
                        # SW 중심에서의 거리
                        dist_to_start = distance(sw_center, start)
                        dist_to_end = distance(sw_center, end)
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
                                dist = distance(sw_center, pt)
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
        
        print(f"   🔧 SW 근처 PC 검색 완료: {len(pipe_lines)}개 발견")
        
    except Exception as e:
        print(f"PIPE 선 찾기 오류: {e}")
        pipe_lines = []
    
    return pipe_lines

def check_wd_interference_with_priority(wd_entities, sw_center, rotation_angle, msp, exclude_entities, pipe_lines=None):
    """우선순위 기반 WD 간섭 체크 - 각 간섭 유형별로 별도 체크"""
    try:
        # 임시로 회전시켜서 간섭 체크
        temp_positions = []
        
        # 모든 엔티티의 현재 위치 백업
        for entity in wd_entities:
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
        for entity in wd_entities:
            rotate_entity_around_point(entity, sw_center, rotation_angle)
        
        # 회전 후 WELDNO 텍스트를 WDC 원 중심으로 재정렬
        wdc_circle = None
        weldno_texts = []
        
        for entity in wd_entities:
            if entity.dxftype() == 'CIRCLE' and 1.5 <= entity.dxf.radius <= 3.2:  # 지름 3~6.4mm
                wdc_circle = entity
            elif entity.dxftype() == 'TEXT':
                # 텍스트가 수평인지 확인
                if is_horizontal_text(entity):
                    weldno_texts.append(entity)
        
        if wdc_circle and weldno_texts:
            wdc_center = Vec2(wdc_circle.dxf.center.x, wdc_circle.dxf.center.y)
            for txt in weldno_texts:
                bbox = get_text_bounding_box(txt)
                if bbox:
                    offset = wdc_center - bbox['center']
                    new_insert = Vec2(txt.dxf.insert.x + offset.x, 
                                    txt.dxf.insert.y + offset.y)
                    txt.dxf.insert = (new_insert.x, new_insert.y, 0)
        
        # 회전 후 WDC 중심 위치
        wdc_center_for_check = Vec2(wdc_circle.dxf.center.x, wdc_circle.dxf.center.y) if wdc_circle else sw_center
        
        # WA 라인의 각도 계산 (SW에서 WDC로의 방향)
        wa_angle = math.atan2(wdc_center_for_check.y - sw_center.y, 
                             wdc_center_for_check.x - sw_center.x)
        
        # PIPE와의 직교성 계산
        pipe_angle_info = calculate_wa_line_to_pipe_angle(wa_angle, pipe_lines)
        
        # 각 간섭 유형별로 체크
        has_text_interference = False
        has_pipe_layer_interference = False
        has_pc_circle_interference = False
        has_30degree_polyline_interference = False
        general_interference_score = 0
        
        # 1. TEXT 간섭 체크 (최우선) - 25mm 범위 내만
        for entity in wd_entities:
            if entity.dxftype() == 'TEXT':
                if check_text_endpoint_interference(entity, msp, exclude_entities + wd_entities, 5.0, wdc_center_for_check, 25.0):
                    has_text_interference = True
                    break
        
        # 2. PIPE/ELBO 레이어 간섭 체크 (두번째 우선순위) - 25mm 범위 내만
        has_pipe_layer_interference = check_pipe_layer_interference(wd_entities, msp, exclude_entities + wd_entities, 25.0)
        
        # 3. PC와 WDC 원 사이 1mm 체크 (세번째 우선순위)
        if pipe_lines:
            for entity in wd_entities:
                if entity.dxftype() == 'CIRCLE' and 1.5 <= entity.dxf.radius <= 3.2:  # WDC 원 (지름 3~6.4mm)
                    center = Vec2(entity.dxf.center.x, entity.dxf.center.y)
                    for pc in pipe_lines:
                        if check_circle_to_segments_distance(center, entity.dxf.radius, pc['segments'], 1.0):  # 2mm → 1mm로 완화
                            has_pc_circle_interference = True
                            break
                    if has_pc_circle_interference:
                        break
        
        # 4. 30도 단위 정각도 폴리라인 간섭 체크 (네번째 우선순위) - 25mm 범위 내만
        has_30degree_polyline_interference = check_30degree_polyline_interference(wd_entities, msp, exclude_entities + wd_entities, 25.0)
        
        # 5. 일반 간섭 점수 계산 (최하위 우선순위) - 25mm 범위 내만
        general_interference_details = []
        for entity in wd_entities:
            if entity.dxftype() == 'CIRCLE':
                center = Vec2(entity.dxf.center.x, entity.dxf.center.y)
                # WDC 원의 경우 반지름을 약간 늘려서 체크 (여유 공간 확보)
                check_radius_adjusted = entity.dxf.radius + 1.0  # 1mm 여유
                interference_count, details = check_interference_at_position_detailed(center, msp, exclude_entities + wd_entities, check_radius_adjusted, 25.0)
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

def delete_isotext_entities(msp, wd_group):
    """WD 그룹과 관련된 ISOTEXT 레이어의 엔티티들을 삭제"""
    deleted_count = 0
    
    try:
        # 삭제할 엔티티 목록
        entities_to_delete = []
        
        # WDC 원 중심 찾기
        wdc_center = None
        for entity in wd_group['entities']:
            if entity.dxftype() == 'CIRCLE' and 1.5 <= entity.dxf.radius <= 3.2:
                wdc_center = Vec2(entity.dxf.center.x, entity.dxf.center.y)
                break
        
        if not wdc_center:
            return deleted_count
        
        # ISOTEXT 레이어의 엔티티들 중 WDC 근처(10mm 이내)의 엔티티 찾기
        for entity in msp:
            if hasattr(entity.dxf, 'layer') and entity.dxf.layer == 'ISOTEXT':
                # 엔티티가 이미 WD 그룹에 포함되어 있으면 건너뛰기
                if entity in wd_group['entities']:
                    continue
                
                # 엔티티와 WDC 중심 사이의 거리 계산
                entity_pos = None
                if entity.dxftype() == 'CIRCLE':
                    entity_pos = Vec2(entity.dxf.center.x, entity.dxf.center.y)
                elif entity.dxftype() in ('TEXT', 'MTEXT'):
                    entity_pos = Vec2(entity.dxf.insert.x, entity.dxf.insert.y)
                elif entity.dxftype() == 'LINE':
                    start = Vec2(entity.dxf.start.x, entity.dxf.start.y)
                    end = Vec2(entity.dxf.end.x, entity.dxf.end.y)
                    # 선분의 한 끝점이라도 WDC 근처에 있으면 삭제
                    if distance(start, wdc_center) <= 10.0 or distance(end, wdc_center) <= 10.0:
                        entities_to_delete.append(entity)
                        continue
                
                if entity_pos and distance(entity_pos, wdc_center) <= 10.0:
                    entities_to_delete.append(entity)
        
        # 엔티티 삭제
        for entity in entities_to_delete:
            try:
                msp.delete_entity(entity)
                deleted_count += 1
            except Exception as e:
                print(f"   ❗ ISOTEXT 엔티티 삭제 오류: {e}")
        
        if deleted_count > 0:
            print(f"   🗑️  ISOTEXT 레이어에서 {deleted_count}개 엔티티 삭제")
    
    except Exception as e:
        print(f"   ❗ ISOTEXT 삭제 처리 오류: {e}")
    
    return deleted_count

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
        print("❌ 선택된 파일이 없습니다.")
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
            print(f"⚠️  이미 처리된 파일입니다. 건너뜁니다.")
            continue
        
        processed_files.append(filepath)
        print(f"\n📂 처리 중: {os.path.basename(filepath)}")
        
        try:
            doc = ezdxf.readfile(filepath)
            msp = doc.modelspace()
        except Exception as e:
            print(f"❌ 파일 읽기 오류: {e}")
            continue
    
        # 파라미터 설정
        min_radius = 1.5  # 최소 반지름 (지름 3mm)
        max_radius = 3.2  # 최대 반지름 (지름 6.4mm)
        text_search_radius = 4.0
        a1_search_radius = 3.0  # WDC 중심에서 A1 라인 찾기 위한 반경
        interference_check_radius = 25.0  # 간섭 체크 범위 (20mm → 25mm로 확대)
        
        # 사용된 WELDS 원 추적 리스트
        used_welds_circles = []
        
        wdc_blocks = []  # WDC (원) 저장
        wd_groups = []   # WD (WDC + WDT) 그룹 저장
        
        # 1. WDC 찾기: ISOTEXT 레이어의 원 (지름 3~6.4mm)
        for circle in msp.query("CIRCLE"):
            if circle.dxf.layer == "ISOTEXT" and min_radius <= circle.dxf.radius <= max_radius:
                center = Vec2(circle.dxf.center.x, circle.dxf.center.y)
                circle.dxf.layer = "WDC"
                circle.dxf.color = 4  # CYAN
                
                # 2. WDT 찾기: WDC 반경 4.0 이내의 기울기 0인 TEXT
                wdt_texts = []
                for txt in msp.query("TEXT"):
                    if is_horizontal_text(txt):
                        pos = Vec2(txt.dxf.insert.x, txt.dxf.insert.y)
                        if distance(pos, center) <= text_search_radius:
                            txt.dxf.layer = "WDT"
                            wdt_texts.append(txt)
                
                wdc_blocks.append({
                    "circle": circle,
                    "center": center,
                    "radius": circle.dxf.radius,
                    "texts": wdt_texts
                })
        
        print(f"✅ WDC 블록 수: {len(wdc_blocks)}")
        
        # 3. 각 WDC에 대해 A1 (접하는 라인) 찾기 및 처리
        for wdc in wdc_blocks:
            circle = wdc["circle"]
            center = wdc["center"]
            radius = wdc["radius"]
            texts = wdc["texts"]
            
            # A1 찾기: WDC 중심에서 3mm 이내의 가장 가까운 ISOTEXT 레이어의 LINE
            closest_line = None
            closest_distance = float('inf')
            closest_ap1 = None
            closest_ap2 = None
            
            for line in msp.query("LINE"):
                if line.dxf.layer == "ISOTEXT":
                    start = Vec2(line.dxf.start.x, line.dxf.start.y)
                    end = Vec2(line.dxf.end.x, line.dxf.end.y)
                    
                    # 각 끝점과 원 중심까지의 거리 계산
                    dist_start = distance(start, center)
                    dist_end = distance(end, center)
                    
                    # 더 가까운 점 찾기
                    if dist_start < dist_end:
                        if dist_start <= 3.0:  # WDC 중심에서 3mm 이내
                            if dist_start < closest_distance:
                                closest_distance = dist_start
                                closest_line = line
                                closest_ap1 = start
                                closest_ap2 = end
                    else:
                        if dist_end <= 3.0:  # WDC 중심에서 3mm 이내
                            if dist_end < closest_distance:
                                closest_distance = dist_end
                                closest_line = line
                                closest_ap1 = end
                                closest_ap2 = start
            
            if closest_line:
                # 가장 가까운 라인을 A1으로 설정
                closest_line.dxf.color = 7  # 흰색
                
                # A1의 기울기 계산
                angle = get_line_angle(closest_ap1, closest_ap2)
                
                # WD = WDC + WDT
                wd_entities = [circle] + texts
                
                # A1 라인은 나중에 삭제하기 위해 저장
                # (WA가 성공적으로 생성된 경우에만 삭제)
                
                # WD 그룹 저장 (회전에 사용) - 이동은 나중에 WELDS를 찾은 후에 수행
                wd_groups.append({
                    'wdc_circle': circle,
                    'wdc_center': center,  # 원래 위치 저장
                    'wdt_texts': texts,
                    'entities': wd_entities,
                    'ap2': closest_ap2,  # AP2 위치 저장
                    'a1_angle': angle,  # A1 라인의 각도 저장
                    'radius': radius,  # WDC 반지름 저장
                    'a1_line': closest_line,  # A1 라인 참조 저장 (나중에 삭제용)
                    'wa_created': False  # WA 생성 여부 플래그
                })
        
        print(f"✅ WD 그룹 생성: {len(wd_groups)}개")
        print(f"\n🔄 WD 회전 처리 시작 - 총 {len(wd_groups)}개 그룹")
        
        # 각 WD 그룹에 대해 회전 처리
        failed_wd_count = 0
        long_wa_count = 0
        
        for i, wd_group in enumerate(wd_groups):
            try:
                wdc_circle = wd_group['wdc_circle']
                original_wdc_center = wd_group['wdc_center']  # 원래 위치
                ap2 = wd_group['ap2']  # AP2 위치
                a1_angle = wd_group['a1_angle']  # A1 선의 각도
                
                print(f"\n[{i+1}/{len(wd_groups)}] WD 처리: ({original_wdc_center.x:.2f}, {original_wdc_center.y:.2f})")
                
                # 1. 먼저 A1 선을 따라 WELDS 찾기 (A1 선의 연장선상)
                # A1 방향으로 연장된 선상에서 WELDS 찾기
                direction = Vec2(math.cos(a1_angle), math.sin(a1_angle))
                search_start = original_wdc_center
                search_end = ap2 + direction * 50.0  # AP2에서 50mm 더 연장
                
                welds_circle, welds_distance = find_welds_along_line(
                    search_start, search_end, msp, used_welds_circles, 50.0
                )
                
                if welds_circle:
                    welds_center = Vec2(welds_circle.dxf.center.x, welds_circle.dxf.center.y)
                    print(f"   ✅ A1 연장선상에서 WELDS 발견: 거리 {welds_distance:.1f}mm")
                    used_welds_circles.append(welds_circle)
                else:
                    # 2. A1 선상에서 못 찾으면 AP2 근처에서 찾기 (점진적 확대)
                    print(f"   ⚠️  A1 선상에서 WELDS를 찾지 못함, AP2 근처 검색")
                    
                    search_radii = [5.0, 10.0, 15.0, 20.0, 30.0]
                    for search_radius in search_radii:
                        # WELDS 레이어의 1.5-2mm 원 찾기 (AP2 근처)
                        for circle in msp.query('CIRCLE'):
                            if (hasattr(circle.dxf, 'layer') and circle.dxf.layer == 'WELDS' and
                                0.75 <= circle.dxf.radius <= 1.0):  # 반지름 0.75-1.0 = 지름 1.5-2mm
                                circle_center = Vec2(circle.dxf.center.x, circle.dxf.center.y)
                                if distance(circle_center, ap2) <= search_radius:
                                    # 이미 사용된 WELDS인지 확인
                                    if circle not in used_welds_circles:
                                        welds_circle = circle
                                        welds_center = circle_center
                                        welds_distance = distance(circle_center, ap2)
                                        used_welds_circles.append(circle)
                                        print(f"   ✅ {search_radius:.0f}mm 범위에서 WELDS 발견")
                                        break
                        if welds_circle:
                            break
                
                # 3. 그래도 못 찾으면 이미 사용된 WELDS 중에서라도 찾기
                if not welds_circle:
                    print(f"   ⚠️  미사용 WELDS를 찾지 못함, 사용된 WELDS 재검색")
                    min_distance = float('inf')
                    for circle in msp.query('CIRCLE'):
                        if (hasattr(circle.dxf, 'layer') and circle.dxf.layer == 'WELDS' and
                            0.75 <= circle.dxf.radius <= 1.0):
                            circle_center = Vec2(circle.dxf.center.x, circle.dxf.center.y)
                            dist = distance(circle_center, ap2)
                            if dist < min_distance and dist <= 30.0:
                                welds_circle = circle
                                welds_center = circle_center
                                welds_distance = dist
                                min_distance = dist
                    
                    if welds_circle:
                        print(f"   ⚠️  기존 사용 WELDS 재사용 (거리: {min_distance:.1f}mm)")
                
                if not welds_circle:
                    print(f"   ❌ WELDS를 전혀 찾을 수 없음 - WA 선 없이 진행")
                    failed_wd_count += 1
                    # WDC 색상을 빨간색으로 변경하여 문제 표시
                    wdc_circle.dxf.color = 1  # RED
                    continue
                
                print(f"   🔗 WELDS 원 발견: ({welds_center.x:.2f}, {welds_center.y:.2f})")
                
                # WD를 WELDS로부터 (WDC 반지름 + 2.8mm) 거리로 이동
                # A1의 방향을 사용하여 초기 위치 설정
                radius = wd_group['radius']
                move_distance = radius + 2.8
                
                # WELDS에서 AP2 방향으로 이동 (만약 AP2가 WELDS보다 가까우면 반대 방향)
                if distance(welds_center, original_wdc_center) < distance(welds_center, ap2):
                    # WDC가 AP2보다 WELDS에 가까운 경우 (정상적인 경우)
                    direction = original_wdc_center - welds_center
                else:
                    # AP2가 WELDS에 더 가까운 경우
                    direction = ap2 - welds_center
                
                if direction.magnitude > 0:
                    direction_normalized = direction.normalize()
                    new_wdc_center = welds_center + direction_normalized * move_distance
                    
                    # WD 엔티티들 이동
                    move_vec = new_wdc_center - original_wdc_center
                    
                    # WDC 이동
                    wdc_circle.dxf.center = (new_wdc_center.x, new_wdc_center.y, 0)
                    
                    # WDT 텍스트들 이동
                    for txt in wd_group['wdt_texts']:
                        pos = Vec2(txt.dxf.insert.x, txt.dxf.insert.y)
                        new_pos = pos + move_vec
                        txt.dxf.insert = (new_pos.x, new_pos.y, 0)
                    
                    # 이동된 WDC 중심 업데이트
                    wdc_center = new_wdc_center
                    
                    # WA 거리 확인 및 경고
                    actual_wa_distance = distance(welds_center, wdc_center)
                    if actual_wa_distance > 10.0:  # 10mm 이상이면 경고
                        print(f"   ⚠️  WA 거리가 비정상적으로 깁니다: {actual_wa_distance:.1f}mm")
                        long_wa_count += 1
                        # WDC 색상을 노란색으로 변경하여 경고 표시
                        wdc_circle.dxf.color = 2  # YELLOW
                else:
                    print(f"   ⚠️  방향 계산 오류 - 기존 위치 유지")
                    wdc_center = original_wdc_center
                    failed_wd_count += 1
                    # WDC 색상을 빨간색으로 변경
                    wdc_circle.dxf.color = 1  # RED
                    continue
                
                # WELDS 근처의 PIPE 선 찾기
                pipe_lines = find_pipe_lines_near_sw(welds_center, msp, 5.0)
                
                # 디버깅: PIPE 선 정보 출력
                if pipe_lines:
                    print(f"   PIPE 정보:")
                    for i, pipe in enumerate(pipe_lines):
                        if pipe['segments']:
                            start, end = pipe['segments'][0]
                            angle = math.degrees(math.atan2(end.y - start.y, end.x - start.x)) % 360
                            # PIPE에 대한 ISO 직교 각도
                            iso_angles = get_iso_orthogonal_angle(angle)
                            print(f"     - PIPE{i+1} 각도: {angle:.1f}° (ISO 직교: {iso_angles})")
                
                # 간섭 체크를 위한 제외 엔티티
                exclude_entities = [welds_circle] + wd_group['entities']
                
                print(f"   🔍 간섭 체크 시작 (25mm 범위 내)")
                
                # 디버깅: WDC 원 정보 출력
                wdc_info = f"중심=({wdc_center.x:.1f}, {wdc_center.y:.1f}), 반지름={radius:.1f}mm"
                print(f"   WDC 원: {wdc_info}")
                print(f"   WELDS와의 거리: {distance(welds_center, wdc_center):.1f}mm (목표: {move_distance:.1f}mm)")
                
                # 먼저 현재 위치(0도)에서 간섭 체크
                current_interference = check_wd_interference_with_priority(
                    wd_group['entities'], welds_center, 0, msp, exclude_entities, pipe_lines
                )
                
                print(f"   현재 위치 간섭 상태:")
                print(f"   - TEXT 간섭: {current_interference['text_interference']}")
                print(f"   - PIPE/ELBO 레이어 간섭: {current_interference['pipe_layer_interference']}")
                print(f"   - PC-WDC 거리 문제: {current_interference['pc_circle_interference']}")
                print(f"   - 30도 폴리라인 간섭: {current_interference['30degree_polyline_interference']}")
                print(f"   - 일반 간섭 점수: {current_interference['general_score']}")
                if current_interference['pipe_angle_info']:
                    ortho_info = current_interference['pipe_angle_info']
                    print(f"   - PIPE와의 직교성: {ortho_info['orthogonality_score']:.1f}도 (목표각도: {ortho_info.get('target_angle', 'N/A')}°)")
                
                # 모든 회전 각도에서 간섭 정보 수집 (0도 포함)
                rotation_candidates = []
                for degree in range(0, 360, 30):
                    angle = math.radians(degree)
                    interference_info = check_wd_interference_with_priority(
                        wd_group['entities'], welds_center, angle, msp, exclude_entities, pipe_lines
                    )
                    rotation_candidates.append({
                        'angle': angle,
                        'degree': degree,
                        'interference': interference_info
                    })
                
                # 최적 위치 선택 - ISO 직교 절대 우선
                best_candidate = None
                
                # 1. ISO 직교 각도들을 우선 체크
                print(f"\n   🎯 ISO 직교 위치 우선 체크")
                
                # 현재 WA 라인의 각도 계산
                wa_angle = math.atan2(wdc_center.y - welds_center.y, wdc_center.x - welds_center.x)
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
                        print(f"   ✅ {candidate['degree']}도에서 간섭 없음 (직교 차이: {sorted_item['ortho_diff']:.1f}도)")
                        break
                    else:
                        # 간섭 정보 출력
                        interference_types = []
                        if interference['text_interference']:
                            interference_types.append("TEXT")
                        if interference['pipe_layer_interference']:
                            interference_types.append("PIPE층")
                        if interference['pc_circle_interference']:
                            interference_types.append("PC거리")
                        if interference['30degree_polyline_interference']:
                            interference_types.append("30도선")
                        if interference['general_score'] > 0:
                            interference_types.append(f"일반({interference['general_score']})")
                        
                        print(f"   ❌ {candidate['degree']}도: 간섭={', '.join(interference_types)} (직교 차이: {sorted_item['ortho_diff']:.1f}도)")
                
                # 간섭 없는 위치를 찾지 못한 경우 - 간섭이 가장 적은 위치 선택
                if not best_candidate:
                    print(f"\n   ⚠️  모든 위치에서 간섭 발생 - 간섭이 가장 적은 위치 선택")
                    
                    # 우선순위별로 최적 위치 찾기
                    # 1. TEXT 간섭이 없는 위치들
                    candidates_no_text = [c for c in rotation_candidates_sorted 
                                        if not c['candidate']['interference']['text_interference']]
                    
                    if candidates_no_text:
                        # 2. PIPE 레이어 간섭이 없는 위치들
                        candidates_no_pipe = [c for c in candidates_no_text 
                                            if not c['candidate']['interference']['pipe_layer_interference']]
                        
                        if candidates_no_pipe:
                            # 3. PC 거리 문제가 없는 위치들
                            candidates_no_pc = [c for c in candidates_no_pipe 
                                              if not c['candidate']['interference']['pc_circle_interference']]
                            
                            if candidates_no_pc:
                                # 4. 30도 폴리라인 간섭이 없는 위치들
                                candidates_no_30deg = [c for c in candidates_no_pc 
                                                     if not c['candidate']['interference']['30degree_polyline_interference']]
                                
                                if candidates_no_30deg:
                                    # 5. 일반 간섭 점수가 가장 낮은 위치
                                    candidates_no_30deg.sort(key=lambda x: x['candidate']['interference']['general_score'])
                                    best_candidate = candidates_no_30deg[0]['candidate']
                                else:
                                    # 일반 간섭 점수가 가장 낮은 위치
                                    candidates_no_pc.sort(key=lambda x: x['candidate']['interference']['general_score'])
                                    best_candidate = candidates_no_pc[0]['candidate']
                            else:
                                # 일반 간섭 점수가 가장 낮은 위치
                                candidates_no_pipe.sort(key=lambda x: x['candidate']['interference']['general_score'])
                                best_candidate = candidates_no_pipe[0]['candidate']
                        else:
                            # 일반 간섭 점수가 가장 낮은 위치
                            candidates_no_text.sort(key=lambda x: x['candidate']['interference']['general_score'])
                            best_candidate = candidates_no_text[0]['candidate']
                    else:
                        # 모든 위치에서 TEXT 간섭이 있는 경우 - 전체 중 최선 선택
                        rotation_candidates_sorted.sort(key=lambda x: (
                            x['candidate']['interference']['text_interference'],
                            x['candidate']['interference']['pipe_layer_interference'],
                            x['candidate']['interference']['pc_circle_interference'],
                            x['candidate']['interference']['30degree_polyline_interference'],
                            x['candidate']['interference']['general_score'],
                            x['ortho_diff']
                        ))
                        best_candidate = rotation_candidates_sorted[0]['candidate']
                    
                    print(f"   📌 차선책: {best_candidate['degree']}도 선택")
                
                if not best_candidate:
                    print(f"   ❌ 적절한 위치를 찾을 수 없음 - SKIP")
                    continue
                
                # 선택된 각도로 회전
                final_angle = best_candidate['angle']
                final_degree = best_candidate['degree']
                
                # 간섭 상태 출력
                final_interference = best_candidate['interference']
                print(f"\n   📌 최종 선택: {final_degree}도")
                
                # 최종 WA 각도와 ISO 직교 차이 계산
                final_wa_angle = math.atan2(wdc_circle.dxf.center.y - welds_center.y, 
                                           wdc_circle.dxf.center.x - welds_center.x)
                final_wa_angle_deg = (math.degrees(final_wa_angle) + final_degree) % 360
                final_iso_angles = get_iso_orthogonal_angle(final_wa_angle_deg)
                
                min_ortho_diff = float('inf')
                closest_ortho = None
                for ortho_angle in final_iso_angles:
                    diff = abs(final_wa_angle_deg - ortho_angle)
                    if diff > 180:
                        diff = 360 - diff
                    if diff < min_ortho_diff:
                        min_ortho_diff = diff
                        closest_ortho = ortho_angle
                
                print(f"   - 최종 WA 각도: {final_wa_angle_deg:.1f}° (ISO 직교 {closest_ortho}°와 {min_ortho_diff:.1f}° 차이)")
                print(f"   - TEXT 간섭: {final_interference['text_interference']}")
                print(f"   - PIPE/ELBO 간섭: {final_interference['pipe_layer_interference']}")
                print(f"   - PC-WDC 거리 문제: {final_interference['pc_circle_interference']}")
                print(f"   - 30도 폴리라인 간섭: {final_interference['30degree_polyline_interference']}")
                print(f"   - 일반 간섭 점수: {final_interference['general_score']}")
                if final_interference.get('general_details'):
                    print(f"   - 일반 간섭 항목: {', '.join(final_interference['general_details'])}")
                
                # WD 회전 실행 (회전이 필요한 경우만)
                if final_angle != 0:
                    for entity in wd_group['entities']:
                        rotate_entity_around_point(entity, welds_center, final_angle)
                    
                    # 회전 후 텍스트를 WDC 원 중심으로 재정렬
                    wdc_center_after_rotation = Vec2(wdc_circle.dxf.center.x, wdc_circle.dxf.center.y)
                    for txt in wd_group['wdt_texts']:
                        if is_horizontal_text(txt):
                            bbox = get_text_bounding_box(txt)
                            if bbox:
                                offset = wdc_center_after_rotation - bbox['center']
                                new_insert = Vec2(txt.dxf.insert.x + offset.x, 
                                                txt.dxf.insert.y + offset.y)
                                txt.dxf.insert = (new_insert.x, new_insert.y, 0)
                    print(f"   🔄 WD를 {final_degree}도 회전 완료")
                else:
                    print(f"   ✅ 현재 위치가 최적 - 회전 불필요")
                
                # 회전된 WDC 위치
                rotated_wdc_center = Vec2(wdc_circle.dxf.center.x, wdc_circle.dxf.center.y)
                
                # 새로운 WA 선 생성 (WELDS에서 WDC로)
                new_wa_line = msp.add_line(
                    start=(welds_center.x, welds_center.y),
                    end=(rotated_wdc_center.x, rotated_wdc_center.y),
                    dxfattribs={'layer': 'WA'}
                )
                
                # 새로 생성한 WA 라인만 WDC 원 안에서 TRIM
                try:
                    direction = rotated_wdc_center - welds_center
                    if direction.magnitude > 0:
                        direction_normalized = direction.normalize()
                        # WDC 원의 가장자리까지만 그리기
                        trim_distance = direction.magnitude - wdc_circle.dxf.radius
                        if trim_distance > 0:
                            trim_end = welds_center + direction_normalized * trim_distance
                            new_wa_line.dxf.end = (trim_end.x, trim_end.y, 0)
                            print(f"   ✂️  WA 라인을 WDC 원 가장자리에서 TRIM 완료")
                    
                    # 최종 거리 확인
                    final_distance = distance(welds_center, rotated_wdc_center)
                    print(f"   📏 최종 WELDS-WDC 거리: {final_distance:.2f}mm (목표: {move_distance:.1f}mm)")
                    
                    # 최종 거리가 목표와 1mm 이상 차이나면 경고
                    if abs(final_distance - move_distance) > 1.0:
                        print(f"   ⚠️  최종 거리가 목표와 차이남: {abs(final_distance - move_distance):.2f}mm")
                        # WDC 색상을 주황색으로 변경
                        wdc_circle.dxf.color = 30  # ORANGE
                    
                    # WA 생성 성공 표시
                    wd_group['wa_created'] = True
                    print(f"   ✅ WD 회전 및 WA 재생성 완료")
                    
                    # WA가 성공적으로 생성되었으므로 A1 라인 삭제
                    if 'a1_line' in wd_group and wd_group['a1_line']:
                        try:
                            msp.delete_entity(wd_group['a1_line'])
                            print(f"   🗑️  A1 라인 삭제 완료")
                        except Exception as del_e:
                            print(f"   ❗ A1 라인 삭제 오류: {del_e}")
                    
                    # ISOTEXT 레이어의 관련 엔티티들 삭제
                    delete_isotext_entities(msp, wd_group)
                    
                except Exception as trim_e:
                    print(f"   ❌ WA 라인 TRIM 오류: {trim_e}")
                
            except Exception as e:
                print(f"❌ WD 처리 중 오류: {e}")
                continue
        
        # 파일 저장
        output_path = os.path.splitext(filepath)[0] + "_wno.dxf"
        doc.saveas(output_path)
        print(f"📁 저장된 파일: {output_path}")
        
        # 처리 결과 요약
        successful_wa_count = sum(1 for wd in wd_groups if wd.get('wa_created', False))
        print(f"\n📊 처리 결과 요약:")
        print(f"   - 전체 WD 그룹: {len(wd_groups)}개")
        print(f"   - 처리 실패: {failed_wd_count}개")
        print(f"   - 긴 WA 거리 (10mm 이상): {long_wa_count}개")
        print(f"   - WA 생성 성공: {successful_wa_count}개")
        print(f"   - WA 생성 실패: {len(wd_groups) - successful_wa_count}개")