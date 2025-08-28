import ezdxf
import os
import math
import sys
from ezdxf.math import Vec2

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
        return abs(text.dxf.rotation) < 0.1
    return True

def get_text_bounding_box(text):
    """TEXT 엔티티의 바운딩 박스를 계산하는 함수"""
    try:
        insert = Vec2(text.dxf.insert.x, text.dxf.insert.y)
        height = text.dxf.height
        
        text_content = text.dxf.text
        width = len(text_content) * height * 0.7
        
        halign = text.dxf.halign if hasattr(text.dxf, 'halign') else 0
        valign = text.dxf.valign if hasattr(text.dxf, 'valign') else 0
        
        if halign == 0:
            min_x = insert.x
            max_x = insert.x + width
        elif halign == 1:
            min_x = insert.x - width/2
            max_x = insert.x + width/2
        elif halign == 2:
            min_x = insert.x - width
            max_x = insert.x
        else:
            min_x = insert.x
            max_x = insert.x + width
        
        if valign == 0:
            min_y = insert.y
            max_y = insert.y + height
        elif valign == 1:
            min_y = insert.y
            max_y = insert.y + height
        elif valign == 2:
            min_y = insert.y - height/2
            max_y = insert.y + height/2
        elif valign == 3:
            min_y = insert.y - height
            max_y = insert.y
        else:
            min_y = insert.y
            max_y = insert.y + height
        
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
    except Exception:
        return None

def check_text_endpoint_interference(text_entity, msp, exclude_entities, min_distance=5.0, check_center=None, check_radius=25.0):
    """TEXT 엔티티의 시작점/끝점이 다른 TEXT의 시작점/끝점에서 5mm 이내면 간섭으로 판정 - 모든 레이어 포함"""
    try:
        bbox1 = get_text_bounding_box(text_entity)
        if not bbox1:
            return False
        
        if check_center and distance(bbox1['center'], check_center) > check_radius:
            return False
        
        for e in msp:
            if e in exclude_entities or not hasattr(e, "dxf") or e.dxf is None:
                continue
            
            if e.dxftype() in ("TEXT", "MTEXT"):
                if e.dxftype() == "TEXT":
                    bbox2 = get_text_bounding_box(e)
                else:
                    insert_pos = Vec2(e.dxf.insert.x, e.dxf.insert.y)
                    bbox2 = {
                        'center': insert_pos,
                        'width': 5.0,
                        'height': 3.0
                    }
                
                if not bbox2:
                    continue
                
                other_center = bbox2['center']
                if check_center and distance(other_center, check_center) > check_radius:
                    continue
                
                center_distance = distance(bbox1['center'], bbox2['center'])
                min_center_distance = max(bbox1['height'], bbox2['height']) * 1.5
                
                if center_distance < min_center_distance:
                    return True
        
        return False
    except Exception:
        return False

def check_pipe_layer_interference(wc_entities, msp, exclude_entities, check_radius=25.0):
    """PIPE 또는 ELBO를 포함하는 레이어와의 간섭을 체크 (25mm 범위 내만)"""
    try:
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
                
                for e in msp:
                    if e in exclude_entities or not hasattr(e, "dxf") or e.dxf is None:
                        continue
                    
                    if hasattr(e.dxf, 'layer'):
                        layer_name = e.dxf.layer.upper()
                        if any(keyword in layer_name for keyword in ['PIPE', 'ELBO', 'FITTING', 'VALVE', 'FLANGE']):
                            if e.dxftype() in ("LINE", "POLYLINE", "LWPOLYLINE", "ARC", "CIRCLE"):
                                if e.dxftype() == "LINE":
                                    start = Vec2(e.dxf.start.x, e.dxf.start.y)
                                    end = Vec2(e.dxf.end.x, e.dxf.end.y)
                                    
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
                                    if e.dxftype() == "POLYLINE":
                                        pts = [Vec2(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]
                                    else:
                                        pts = [Vec2(x, y) for x, y, *_ in e.get_points()]
                                    
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
    except Exception:
        return False

def check_30degree_polyline_interference(wc_entities, msp, exclude_entities, check_radius=25.0):
    """30도 단위 정각도를 가진 폴리라인/LW폴리라인과의 간섭을 체크 (25mm 범위 내만)"""
    try:
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
                
                for e in msp.query("POLYLINE LWPOLYLINE"):
                    if e in exclude_entities or not hasattr(e, "dxf") or e.dxf is None:
                        continue
                    
                    if e.dxftype() == "POLYLINE":
                        pts = [Vec2(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]
                    else:
                        pts = [Vec2(x, y) for x, y, *_ in e.get_points()]
                    
                    if len(pts) < 2:
                        continue
                    
                    in_range = False
                    for pt in pts:
                        if distance(wc_center, pt) <= check_radius:
                            in_range = True
                            break
                    
                    if not in_range:
                        continue
                    
                    for i in range(len(pts) - 1):
                        p1, p2 = pts[i], pts[i+1]
                        
                        dx = p2.x - p1.x
                        dy = p2.y - p1.y
                        angle_rad = math.atan2(dy, dx)
                        
                        angle_deg = math.degrees(angle_rad) % 360
                        
                        nearest_30 = round(angle_deg / 30) * 30
                        
                        if abs(angle_deg - nearest_30) < 1.0:
                            dist = point_to_segment_distance(circle_center, p1, p2)
                            if dist < circle_radius:
                                return True
        
        return False
    except Exception:
        return False

def check_circle_to_segments_distance(circle_center, circle_radius, segments, min_distance=1.0):
    """원과 선분들 사이의 최소 거리가 min_distance 이하인지 확인"""
    for start, end in segments:
        dist_to_segment = point_to_segment_distance(circle_center, start, end)
        
        dist_from_circle_edge = dist_to_segment - circle_radius
        
        if dist_to_segment < circle_radius:
            return True
        
        if dist_from_circle_edge <= min_distance:
            return True
    
    return False

def get_iso_orthogonal_angle(wa_angle_deg):
    """ISO 도면에서 WA 각도에 대한 직교 각도를 반환"""
    wa_angle_norm = wa_angle_deg % 360
    
    nearest_30 = round(wa_angle_norm / 30) * 30
    nearest_30 = nearest_30 % 360
    
    iso_orthogonal_map = {
        0: [90, 270],
        30: [330],
        60: [150, 330],
        90: [270],
        120: [30, 210],
        150: [210],
        180: [90, 270],
        210: [150],
        240: [150, 330],
        270: [90],
        300: [30, 210],
        330: [30],
    }
    
    if nearest_30 in iso_orthogonal_map:
        return iso_orthogonal_map[nearest_30]
    else:
        return [90, 270]

def calculate_wa_line_to_pipe_angle(wa_angle, pipe_lines):
    """WA 라인과 PIPE 라인 사이의 각도 차이를 계산하고 ISO 도면 직교성을 평가"""
    if not pipe_lines:
        return None
    
    orthogonality_score = float('inf')
    best_pipe_angle = 0
    best_target_angle = 0
    
    wa_angle_deg = math.degrees(wa_angle) % 360
    
    orthogonal_angles = get_iso_orthogonal_angle(wa_angle_deg)
    
    for pipe in pipe_lines:
        for segment in pipe['segments']:
            start, end = segment
            pipe_angle = math.atan2(end.y - start.y, end.x - start.x)
            pipe_angle_deg = math.degrees(pipe_angle) % 360
            
            for ortho_angle in orthogonal_angles:
                diff = abs(pipe_angle_deg - ortho_angle)
                if diff > 180:
                    diff = 360 - diff
                
                if diff < orthogonality_score:
                    orthogonality_score = diff
                    best_pipe_angle = pipe_angle_deg
                    best_target_angle = ortho_angle
    
    return {
        'orthogonality_score': orthogonality_score,
        'pipe_angle': best_pipe_angle,
        'target_angle': best_target_angle,
        'wa_angle': wa_angle_deg,
        'orthogonal_angles': orthogonal_angles
    }

def check_interference_at_position_detailed(test_center, msp, exclude_entities, weld_radius=3.0, check_radius=25.0):
    """특정 위치에서의 간섭을 체크하는 함수 (상세 정보 포함) - 최적화됨"""
    interference_count = 0
    interference_details = []
    
    # 범위 기반 pre-filtering으로 시간복잡도 O(n) -> O(k) 최적화 (k << n)
    candidates = []
    for e in msp:
        if e in exclude_entities or not hasattr(e, "dxf") or e.dxf is None:
            continue
        
        # 빠른 범위 체크로 불필요한 엔티티 제외
        entity_pos = None
        max_entity_radius = 0
        
        if e.dxftype() == "CIRCLE":
            entity_pos = Vec2(e.dxf.center.x, e.dxf.center.y)
            max_entity_radius = e.dxf.radius
        elif e.dxftype() in ("TEXT", "MTEXT"):
            entity_pos = Vec2(e.dxf.insert.x, e.dxf.insert.y)
        elif e.dxftype() == "LINE":
            start = Vec2(e.dxf.start.x, e.dxf.start.y)
            end = Vec2(e.dxf.end.x, e.dxf.end.y)
            entity_pos = Vec2((start.x + end.x) / 2, (start.y + end.y) / 2)
            max_entity_radius = distance(start, end) / 2
        elif e.dxftype() == "INSERT":
            entity_pos = Vec2(e.dxf.insert.x, e.dxf.insert.y)
        elif e.dxftype() == "DIMENSION":
            if hasattr(e.dxf, 'defpoint'):
                entity_pos = Vec2(e.dxf.defpoint.x, e.dxf.defpoint.y)
        
        # 범위 밖 엔티티는 후보에서 제외
        if entity_pos and distance(test_center, entity_pos) > check_radius + max_entity_radius + weld_radius:
            continue
            
        candidates.append(e)
    
    # 필터링된 후보들에 대해서만 상세 간섭 체크
    for e in candidates:
        layer_name = e.dxf.layer if hasattr(e.dxf, 'layer') else 'NO_LAYER'
        interference_found = False
        
        if e.dxftype() in ("TEXT", "MTEXT"):
            text_pos = Vec2(e.dxf.insert.x, e.dxf.insert.y)
            if distance(test_center, text_pos) < weld_radius:
                interference_count += 1
                interference_found = True
                
        elif e.dxftype() == "LINE":
            start = Vec2(e.dxf.start.x, e.dxf.start.y)
            end = Vec2(e.dxf.end.x, e.dxf.end.y)
            
            if (distance(test_center, start) <= check_radius or 
                distance(test_center, end) <= check_radius or
                point_to_segment_distance(test_center, start, end) <= check_radius):
                
                if point_to_segment_distance(test_center, start, end) < weld_radius:
                    interference_count += 1
                    interference_found = True
                
        elif e.dxftype() in ("POLYLINE", "LWPOLYLINE"):
            if e.dxftype() == "POLYLINE":
                pts = [Vec2(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]
            else:
                pts = [Vec2(x, y) for x, y, *_ in e.get_points()]
            
            in_range = any(distance(test_center, pt) <= check_radius for pt in pts)
            
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
            arc_center = Vec2(e.dxf.center.x, e.dxf.center.y)
            if distance(arc_center, test_center) < (e.dxf.radius + weld_radius):
                interference_count += 1
                interference_found = True
                
        elif e.dxftype() == "INSERT":
            insert_pos = Vec2(e.dxf.insert.x, e.dxf.insert.y)
            if distance(test_center, insert_pos) < weld_radius:
                interference_count += 1
                interference_found = True
                
        elif e.dxftype() == "DIMENSION":
            try:
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
    """WS 근처의 PIPE 선을 찾는 함수 - 최적화됨"""
    pipe_lines = []
    
    try:
        # 최적화: PIPE 레이어 엔티티만 미리 필터링
        pipe_entities = [entity for entity in msp.query('LINE') 
                        if (hasattr(entity.dxf, 'layer') and 
                            'PIPE' in entity.dxf.layer.upper())]
        
        for entity in pipe_entities:
            try:
                start = Vec2(entity.dxf.start.x, entity.dxf.start.y)
                end = Vec2(entity.dxf.end.x, entity.dxf.end.y)
                
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
        
        # 폴리라인 처리
        pipe_polys = [poly for poly in msp.query("POLYLINE LWPOLYLINE")
                     if (hasattr(poly.dxf, 'layer') and 
                         'PIPE' in poly.dxf.layer.upper())]
        
        for poly in pipe_polys:
            try:
                if poly.dxftype() == "POLYLINE":
                    points = [Vec2(v.dxf.location.x, v.dxf.location.y) for v in poly.vertices]
                else:
                    points = [Vec2(x, y) for x, y, *_ in poly.get_points()]
                
                if len(points) >= 2:
                    min_dist = min(distance(ws_center, pt) for pt in points)
                    
                    if min_dist <= search_radius:
                        segments = [(points[i], points[i+1]) for i in range(len(points) - 1)]
                        
                        pipe_lines.append({
                            'entity': poly,
                            'type': poly.dxftype(),
                            'segments': segments,
                            'min_distance': min_dist
                        })
            except Exception:
                continue
        
        # 거리 기준 정렬 후 상위 2개 선택
        pipe_lines.sort(key=lambda x: x['min_distance'])
        pipe_lines = pipe_lines[:2]
        
    except Exception:
        pipe_lines = []
    
    return pipe_lines

def check_wc_interference_with_priority(wc_entities, ws_center, rotation_angle, msp, exclude_entities, pipe_lines=None):
    """우선순위 기반 WC 간섭 체크 - 각 간섭 유형별로 별도 체크"""
    try:
        temp_positions = []
        
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
        
        for entity in wc_entities:
            rotate_entity_around_point(entity, ws_center, rotation_angle)
        
        wc_circle = None
        wt_texts = []
        
        for entity in wc_entities:
            if entity.dxftype() == 'CIRCLE' and entity.dxf.radius == 3.0:
                wc_circle = entity
            elif entity.dxftype() == 'TEXT':
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
        
        wc_center_for_check = Vec2(wc_circle.dxf.center.x, wc_circle.dxf.center.y) if wc_circle else ws_center
        
        wa_angle = math.atan2(wc_center_for_check.y - ws_center.y, 
                             wc_center_for_check.x - ws_center.x)
        
        pipe_angle_info = calculate_wa_line_to_pipe_angle(wa_angle, pipe_lines)
        
        has_text_interference = False
        has_pipe_layer_interference = False
        has_pc_circle_interference = False
        has_30degree_polyline_interference = False
        general_interference_score = 0
        
        for entity in wc_entities:
            if entity.dxftype() == 'TEXT':
                if check_text_endpoint_interference(entity, msp, exclude_entities + wc_entities, 5.0, wc_center_for_check, 25.0):
                    has_text_interference = True
                    break
        
        has_pipe_layer_interference = check_pipe_layer_interference(wc_entities, msp, exclude_entities + wc_entities, 25.0)
        
        if pipe_lines:
            for entity in wc_entities:
                if entity.dxftype() == 'CIRCLE' and entity.dxf.radius == 3.0:
                    center = Vec2(entity.dxf.center.x, entity.dxf.center.y)
                    for pipe in pipe_lines:
                        if check_circle_to_segments_distance(center, entity.dxf.radius, pipe['segments'], 1.0):
                            has_pc_circle_interference = True
                            break
                    if has_pc_circle_interference:
                        break
        
        has_30degree_polyline_interference = check_30degree_polyline_interference(wc_entities, msp, exclude_entities + wc_entities, 25.0)
        
        general_interference_details = []
        for entity in wc_entities:
            if entity.dxftype() == 'CIRCLE':
                center = Vec2(entity.dxf.center.x, entity.dxf.center.y)
                check_radius_adjusted = entity.dxf.radius + 1.0
                interference_count, details = check_interference_at_position_detailed(center, msp, exclude_entities + wc_entities, check_radius_adjusted, 25.0)
                general_interference_score += interference_count
                if details:
                    general_interference_details.extend(details)
        
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
        
    except Exception:
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
            old_center = Vec2(entity.dxf.center.x, entity.dxf.center.y)
            dx = old_center.x - center.x
            dy = old_center.y - center.y
            new_x = center.x + dx * cos_a - dy * sin_a
            new_y = center.y + dx * sin_a + dy * cos_a
            entity.dxf.center = (new_x, new_y, 0)
            
        elif entity.dxftype() == 'TEXT':
            old_pos = Vec2(entity.dxf.insert.x, entity.dxf.insert.y)
            dx = old_pos.x - center.x
            dy = old_pos.y - center.y
            new_x = center.x + dx * cos_a - dy * sin_a
            new_y = center.y + dx * sin_a + dy * cos_a
            entity.dxf.insert = (new_x, new_y, 0)
            
        elif entity.dxftype() == 'LINE':
            start = Vec2(entity.dxf.start.x, entity.dxf.start.y)
            end = Vec2(entity.dxf.end.x, entity.dxf.end.y)
            
            dx = start.x - center.x
            dy = start.y - center.y
            new_start_x = center.x + dx * cos_a - dy * sin_a
            new_start_y = center.y + dx * sin_a + dy * cos_a
            
            dx = end.x - center.x
            dy = end.y - center.y
            new_end_x = center.x + dx * cos_a - dy * sin_a
            new_end_y = center.y + dx * sin_a + dy * cos_a
            
            entity.dxf.start = (new_start_x, new_start_y, 0)
            entity.dxf.end = (new_end_x, new_end_y, 0)
            
    except Exception:
        pass

def add_wt_text_to_wc_centered(msp, wc_center, text_value, height, color, layer, doc=None):
    """'00' 텍스트를 (0,0)에 생성하여 중심을 계산한 후 WC 중심으로 이동"""
    try:
        if doc and "TXT" not in doc.styles:
            try:
                doc.styles.new("TXT")
            except:
                pass
        
        text = msp.add_text(
            text_value,
            dxfattribs={
                'height': height,
                'color': color,
                'layer': layer,
                'insert': (0, 0, 0),
                'halign': 0,
                'valign': 0,
                'style': 'TXT' if doc else 'Standard',
                'width': 0.85
            }
        )
        
        bbox = get_text_bounding_box(text)
        
        if bbox:
            text_center = bbox['center']
            offset_x = wc_center[0] - text_center.x
            offset_y = wc_center[1] - text_center.y
            
            current_insert = Vec2(text.dxf.insert.x, text.dxf.insert.y)
            new_insert = current_insert + Vec2(offset_x, offset_y)
            text.dxf.insert = (new_insert.x, new_insert.y, 0)
            
            return text
        else:
            text.dxf.halign = 4
            text.dxf.valign = 2
            text.dxf.insert = (wc_center[0], wc_center[1], 0)
            return text
            
    except Exception:
        try:
            return msp.add_text(
                text_value,
                dxfattribs={
                    'height': height,
                    'color': color,
                    'layer': layer,
                    'insert': (wc_center[0], wc_center[1], 0),
                    'halign': 4,
                    'valign': 2,
                    'style': 'TXT' if doc else 'Standard',
                    'width': 0.85
                }
            )
        except:
            return None

def add_wt_text_to_wc(msp, center, text_value, height, color, layer, doc=None):
    """WC 중심에 WT 텍스트를 생성하는 함수"""
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
        
        margin = text_entity.dxf.height * 0.1
        
        box_min_x = bbox['min_x'] - margin
        box_max_x = bbox['max_x'] + margin
        box_min_y = bbox['min_y'] - margin
        box_max_y = bbox['max_y'] + margin
        
        points = [
            (box_min_x, box_min_y),
            (box_max_x, box_min_y),
            (box_max_x, box_max_y),
            (box_min_x, box_max_y),
            (box_min_x, box_min_y)
        ]
        
        polyline = msp.add_lwpolyline(points, dxfattribs={
            'layer': box_layer,
            'color': 4
        })
        
        return polyline
        
    except Exception:
        return None

def process_document(doc):
    """문서를 처리하는 메인 함수 - in-memory 런너 연동용"""
    try:
        msp = doc.modelspace()
        
        ws_radius = 1.25
        wc_radius = 3.0
        move_distance = 8.5
        interference_check_radius = 25.0
        
        ws_circles = []
        wc_groups = []
        
        # WS 찾기 및 WC 생성
        for circle in msp.query("CIRCLE"):
            if (hasattr(circle.dxf, 'layer') and 
                circle.dxf.layer.upper() == "WELD" and 
                abs(circle.dxf.radius - ws_radius) < 0.1):
                
                ws_center = Vec2(circle.dxf.center.x, circle.dxf.center.y)
                
                wc_circle = msp.add_circle(
                    center=(ws_center.x, ws_center.y),
                    radius=wc_radius,
                    dxfattribs={'layer': 'WC', 'color': 4}
                )
                
                moved_center = Vec2(ws_center.x, ws_center.y + move_distance)
                wc_circle.dxf.center = (moved_center.x, moved_center.y, 0)
                
                wt_text = add_wt_text_to_wc_centered(msp, (moved_center.x, moved_center.y), '00', 2.5, 2, 'WT', doc)
                
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
        
        # WC 회전 처리
        failed_wc_count = 0
        
        for i, wc_group in enumerate(wc_groups):
            try:
                ws_center = wc_group['ws_center']
                wc_center = wc_group['wc_center']
                wc_entities = wc_group['entities']
                
                pipe_lines = find_pipe_lines_near_ws(ws_center, msp, 5.0)
                
                exclude_entities = [wc_group['ws_circle']] + wc_entities
                
                current_interference = check_wc_interference_with_priority(
                    wc_entities, ws_center, 0, msp, exclude_entities, pipe_lines
                )
                
                # 최적화: 간섭이 없으면 회전 체크를 건너뜀
                if (not current_interference['text_interference'] and
                    not current_interference['pipe_layer_interference'] and
                    not current_interference['pc_circle_interference'] and
                    not current_interference['30degree_polyline_interference'] and
                    current_interference['general_score'] == 0):
                    
                    # 현재 위치가 최적 - WA 라인만 생성
                    rotated_wc_center = Vec2(wc_group['wc_circle'].dxf.center.x, wc_group['wc_circle'].dxf.center.y)
                else:
                    # 간섭이 있으므로 최적 회전 각도 찾기
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
                    
                    best_candidate = None
                    
                    wa_angle = math.atan2(wc_center.y - ws_center.y, wc_center.x - ws_center.x)
                    wa_angle_deg = math.degrees(wa_angle) % 360
                    
                    iso_orthogonal_angles = get_iso_orthogonal_angle(wa_angle_deg)
                    
                    rotation_candidates_sorted = []
                    for candidate in rotation_candidates:
                        degree = candidate['degree']
                        min_diff_from_ortho = float('inf')
                        for ortho_angle in iso_orthogonal_angles:
                            rotated_wa_angle = (wa_angle_deg + degree) % 360
                            diff = abs(rotated_wa_angle - ortho_angle)
                            if diff > 180:
                                diff = 360 - diff
                            min_diff_from_ortho = min(min_diff_from_ortho, diff)
                        
                        rotation_candidates_sorted.append({
                            'candidate': candidate,
                            'ortho_diff': min_diff_from_ortho
                        })
                    
                    rotation_candidates_sorted.sort(key=lambda x: (x['ortho_diff'], x['candidate']['degree']))
                    
                    for sorted_item in rotation_candidates_sorted:
                        candidate = sorted_item['candidate']
                        interference = candidate['interference']
                        
                        if (not interference['text_interference'] and
                            not interference['pipe_layer_interference'] and
                            not interference['pc_circle_interference'] and
                            not interference['30degree_polyline_interference'] and
                            interference['general_score'] == 0):
                            
                            best_candidate = candidate
                            break
                    
                    if not best_candidate:
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
                    
                    if not best_candidate:
                        failed_wc_count += 1
                        continue
                    
                    final_angle = best_candidate['angle']
                    final_degree = best_candidate['degree']
                    
                    if final_angle != 0:
                        for entity in wc_entities:
                            rotate_entity_around_point(entity, ws_center, final_angle)
                        
                        wc_center_after_rotation = Vec2(wc_group['wc_circle'].dxf.center.x, wc_group['wc_circle'].dxf.center.y)
                        wt_text = wc_group['wt_text']
                        if wt_text:
                            try:
                                msp.delete_entity(wt_text)
                            except:
                                pass
                            wc_group['wt_text'] = add_wt_text_to_wc_centered(
                                msp, (wc_center_after_rotation.x, wc_center_after_rotation.y), '00', 2.5, 2, 'WT', doc
                            )
                    
                    rotated_wc_center = Vec2(wc_group['wc_circle'].dxf.center.x, wc_group['wc_circle'].dxf.center.y)
                
                # WA 선 생성
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
                        trim_distance = direction.magnitude - wc_radius
                        if trim_distance > 0:
                            trim_end = ws_center + direction_normalized * trim_distance
                            new_wa_line.dxf.end = (trim_end.x, trim_end.y, 0)
                except Exception:
                    pass
                
            except Exception:
                failed_wc_count += 1
                continue
        
        return {
            'total_wc_groups': len(wc_groups),
            'failed_count': failed_wc_count,
            'success_count': len(wc_groups) - failed_wc_count
        }
        
    except Exception:
        return {'total_wc_groups': 0, 'failed_count': 0, 'success_count': 0}

def process_file(filepath):
    """단일 파일을 처리하는 함수"""
    try:
        doc = ezdxf.readfile(filepath)
        result = process_document(doc)
        
        output_path = os.path.splitext(filepath)[0] + "_wc.dxf"
        doc.saveas(output_path)
        
        return True, output_path, result
        
    except Exception as e:
        return False, str(e), None

def main():
    """메인 실행 함수 - 명령행 인자 처리"""
    if len(sys.argv) < 2:
        return
    
    filepaths = sys.argv[1:]
    
    # 중복 제거 및 DXF 파일만 필터링
    unique_filepaths = list(set(filepath for filepath in filepaths 
                               if filepath.lower().endswith('.dxf') and os.path.isfile(filepath)))
    
    if not unique_filepaths:
        return
    
    # 각 파일 처리
    for filepath in unique_filepaths:
        success, result_or_error, stats = process_file(filepath)
        
        if success:
            # 성공적으로 처리됨
            pass
        else:
            # 처리 실패
            pass

if __name__ == "__main__":
    main()