import ezdxf
import tkinter as tk
from tkinter import filedialog
import math
import os
from ezdxf.math import Vec2
from ezdxf.entities import Circle, Line, Text, MText
import numpy as np

def get_distance(p1, p2):
    """두 점 사이의 거리 계산"""
    return math.sqrt((p2[0] - p1[0])**2 + (p2[1] - p1[1])**2)

def get_circle_diameter(circle):
    """원의 지름 계산"""
    return circle.dxf.radius * 2

def is_point_in_circle(point, circle):
    """점이 원 안에 있는지 확인"""
    center = (circle.dxf.center.x, circle.dxf.center.y)
    return get_distance(point, center) < circle.dxf.radius

def is_text_horizontal(text):
    """텍스트가 수평(기울기 0)인지 확인"""
    if hasattr(text.dxf, 'rotation'):
        return abs(text.dxf.rotation) < 0.1 or abs(text.dxf.rotation - 360) < 0.1
    return True

def is_numeric_text(text):
    """텍스트가 숫자인지 확인"""
    text_content = ""
    if isinstance(text, Text):
        text_content = text.dxf.text
    elif isinstance(text, MText):
        text_content = text.text
    
    # 숫자와 일부 특수문자(., -, 공백 등) 허용
    try:
        # 공백 제거 후 숫자로 변환 시도
        cleaned = text_content.replace(" ", "").replace(",", "")
        if cleaned:
            float(cleaned)
            return True
    except:
        pass
    return False

def get_line_center(line):
    """선분의 중심점 계산"""
    start = (line.dxf.start.x, line.dxf.start.y)
    end = (line.dxf.end.x, line.dxf.end.y)
    return ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)

def get_line_length(line):
    """선분의 길이 계산"""
    start = (line.dxf.start.x, line.dxf.start.y)
    end = (line.dxf.end.x, line.dxf.end.y)
    return get_distance(start, end)

def get_closest_point_to_center(line, center):
    """선분에서 중심점에 가장 가까운 점 찾기"""
    start = (line.dxf.start.x, line.dxf.start.y)
    end = (line.dxf.end.x, line.dxf.end.y)
    
    dist_start = get_distance(start, center)
    dist_end = get_distance(end, center)
    
    return start if dist_start < dist_end else end

def point_to_line_distance(point, line_start, line_end):
    """점과 선분 사이의 최단 거리 계산"""
    x0, y0 = point
    x1, y1 = line_start
    x2, y2 = line_end
    
    # 선분의 길이
    line_length = get_distance(line_start, line_end)
    if line_length == 0:
        return get_distance(point, line_start)
    
    # 점을 선분에 투영
    t = ((x0 - x1) * (x2 - x1) + (y0 - y1) * (y2 - y1)) / (line_length ** 2)
    t = max(0, min(1, t))
    
    # 가장 가까운 점
    closest_x = x1 + t * (x2 - x1)
    closest_y = y1 + t * (y2 - y1)
    
    return get_distance(point, (closest_x, closest_y))

def line_passes_through_line(line1, line2, tolerance=0.1):
    """line1이 line2를 통과하는지 확인"""
    # line1의 양 끝점이 line2의 양쪽에 있는지 확인
    start1 = (line1.dxf.start.x, line1.dxf.start.y)
    end1 = (line1.dxf.end.x, line1.dxf.end.y)
    start2 = (line2.dxf.start.x, line2.dxf.start.y)
    end2 = (line2.dxf.end.x, line2.dxf.end.y)
    
    # 교차점 계산
    x1, y1 = start1
    x2, y2 = end1
    x3, y3 = start2
    x4, y4 = end2
    
    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < 0.0001:
        return False
    
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
    u = -((x1 - x2) * (y1 - y3) - (y1 - y2) * (x1 - x3)) / denom
    
    return 0 <= t <= 1 and 0 <= u <= 1

def get_iso_perpendicular_direction(line, reference_point, towards_point):
    """ISO 도면에 맞춘 직교 방향 계산"""
    start = Vec2(line.dxf.start.x, line.dxf.start.y)
    end = Vec2(line.dxf.end.x, line.dxf.end.y)
    
    # 선분의 각도 계산
    line_angle = math.atan2(end.y - start.y, end.x - start.x)
    line_angle_deg = math.degrees(line_angle) % 360
    
    # ISO 주요 각도 (30, 90, 150, 210, 270, 330)
    iso_angles = [30, 90, 150, 210, 270, 330]
    
    # 가장 가까운 ISO 각도 찾기
    closest_iso = min(iso_angles, key=lambda x: abs(line_angle_deg - x))
    
    # ISO 직교 방향 계산
    if closest_iso in [30, 210]:  # 30도 또는 210도 선분
        perp_angles = [120, 300]  # 직교는 120도 또는 300도
    elif closest_iso in [150, 330]:  # 150도 또는 330도 선분
        perp_angles = [60, 240]  # 직교는 60도 또는 240도
    else:  # 90도 또는 270도 (수직) 선분
        perp_angles = [30, 150]  # 직교는 30도 또는 150도
    
    # towards_point 방향에 가까운 직교 각도 선택
    ref_vec = Vec2(reference_point[0], reference_point[1])
    towards_vec = Vec2(towards_point[0], towards_point[1])
    
    best_angle = None
    min_dist = float('inf')
    
    for angle in perp_angles:
        # 각도를 라디안으로 변환
        angle_rad = math.radians(angle)
        # 단위 벡터 생성
        test_vec = Vec2(math.cos(angle_rad), math.sin(angle_rad))
        # reference_point에서 해당 방향으로 이동한 점
        test_point = ref_vec + test_vec * 10
        # towards_point까지의 거리 계산
        dist = (test_point - towards_vec).magnitude
        
        if dist < min_dist:
            min_dist = dist
            best_angle = angle_rad
    
    # 최적 방향 벡터 반환
    return Vec2(math.cos(best_angle), math.sin(best_angle))

def get_perpendicular_direction(line, point, towards_point):
    """선분에 직교하는 방향 벡터 계산 (towards_point 방향으로)"""
    start = Vec2(line.dxf.start.x, line.dxf.start.y)
    end = Vec2(line.dxf.end.x, line.dxf.end.y)
    
    # 선분의 방향 벡터
    line_dir = (end - start).normalize()
    
    # 직교 벡터 (두 방향 가능)
    perp1 = Vec2(-line_dir.y, line_dir.x)
    perp2 = Vec2(line_dir.y, -line_dir.x)
    
    # towards_point 방향에 가까운 직교 벡터 선택
    point_vec = Vec2(point[0], point[1])
    towards_vec = Vec2(towards_point[0], towards_point[1])
    
    test_point1 = point_vec + perp1
    test_point2 = point_vec + perp2
    
    dist1 = (test_point1 - towards_vec).magnitude
    dist2 = (test_point2 - towards_vec).magnitude
    
    return perp1 if dist1 < dist2 else perp2

def check_interference(entities, all_entities, tolerance=0.5):
    """엔티티들이 다른 엔티티들과 간섭하는지 확인"""
    for entity in entities:
        if isinstance(entity, Circle):
            center = (entity.dxf.center.x, entity.dxf.center.y)
            radius = entity.dxf.radius
            
            # 다른 원과의 간섭 체크
            for other in all_entities:
                if other == entity or other in entities:
                    continue
                if isinstance(other, Circle):
                    other_center = (other.dxf.center.x, other.dxf.center.y)
                    other_radius = other.dxf.radius
                    dist = get_distance(center, other_center)
                    if dist < (radius + other_radius - tolerance):
                        return True
                elif isinstance(other, Line):
                    # 원과 선분의 간섭 체크
                    start = (other.dxf.start.x, other.dxf.start.y)
                    end = (other.dxf.end.x, other.dxf.end.y)
                    dist = point_to_line_distance(center, start, end)
                    if dist < radius - tolerance:
                        return True
                    
                    # DL 레이어의 경우 점과의 간섭도 체크
                    if other.dxf.layer == 'DL':
                        if get_distance(center, start) < radius - tolerance:
                            return True
                        if get_distance(center, end) < radius - tolerance:
                            return True
                        
        elif isinstance(entity, (Text, MText)):
            # 텍스트의 경우 바운딩 박스로 간섭 체크 (간단히 처리)
            if hasattr(entity.dxf, 'insert'):
                text_pos = (entity.dxf.insert[0], entity.dxf.insert[1])
                # 텍스트 크기를 대략적으로 가정 (높이 기준)
                text_size = entity.dxf.height if hasattr(entity.dxf, 'height') else 2.0
                
                for other in all_entities:
                    if other == entity or other in entities:
                        continue
                    if isinstance(other, Circle):
                        other_center = (other.dxf.center.x, other.dxf.center.y)
                        other_radius = other.dxf.radius
                        dist = get_distance(text_pos, other_center)
                        if dist < (other_radius + text_size - tolerance):
                            return True
                    elif isinstance(other, Line):
                        start = (other.dxf.start.x, other.dxf.start.y)
                        end = (other.dxf.end.x, other.dxf.end.y)
                        dist = point_to_line_distance(text_pos, start, end)
                        if dist < text_size - tolerance:
                            return True
                        
                        # DL 레이어의 경우 점과의 간섭도 체크
                        if other.dxf.layer == 'DL':
                            if get_distance(text_pos, start) < text_size - tolerance:
                                return True
                            if get_distance(text_pos, end) < text_size - tolerance:
                                return True
    
    return False

def get_perpendicular_point_on_line(line, reference_point, distance):
    """선분에서 reference_point를 지나는 수직선이 만나는 점에서 distance만큼 떨어진 점 계산"""
    start = Vec2(line.dxf.start.x, line.dxf.start.y)
    end = Vec2(line.dxf.end.x, line.dxf.end.y)
    ref_vec = Vec2(reference_point[0], reference_point[1])
    
    # 선분의 방향 벡터
    line_vec = end - start
    line_length = line_vec.magnitude
    if line_length == 0:
        return reference_point
    
    line_dir = line_vec / line_length
    
    # reference_point를 선분에 투영
    ref_to_start = ref_vec - start
    projection_length = ref_to_start.dot(line_dir)
    
    # 투영점 계산
    projection_point = start + line_dir * projection_length
    
    # 수직 방향 계산
    perp_direction = (ref_vec - projection_point).normalize()
    
    # 최종 위치
    return (projection_point.x + perp_direction.x * distance, 
            projection_point.y + perp_direction.y * distance)

def trim_line_inside_circle(line, circle, msp):
    """원 내부의 선분을 트림"""
    center = Vec2(circle.dxf.center.x, circle.dxf.center.y)
    radius = circle.dxf.radius
    start = Vec2(line.dxf.start.x, line.dxf.start.y)
    end = Vec2(line.dxf.end.x, line.dxf.end.y)
    
    # 선분과 원의 교점 계산
    direction = (end - start).normalize()
    center_to_start = start - center
    
    a = direction.dot(direction)
    b = 2 * direction.dot(center_to_start)
    c = center_to_start.dot(center_to_start) - radius * radius
    
    discriminant = b * b - 4 * a * c
    if discriminant < 0:
        return  # 교점 없음
    
    sqrt_discriminant = math.sqrt(discriminant)
    t1 = (-b - sqrt_discriminant) / (2 * a)
    t2 = (-b + sqrt_discriminant) / (2 * a)
    
    # 교점 계산
    intersections = []
    if 0 <= t1 <= (end - start).magnitude:
        intersections.append(start + direction * t1)
    if 0 <= t2 <= (end - start).magnitude:
        intersections.append(start + direction * t2)
    
    if len(intersections) == 2:
        # 원 외부 부분만 유지
        dist_start_center = (start - center).magnitude
        dist_end_center = (end - center).magnitude
        
        if dist_start_center > radius and dist_end_center > radius:
            # 선분이 원을 관통하는 경우 - 두 개의 새 선분 생성
            new_line1 = msp.add_line(start=(start.x, start.y), 
                                   end=(intersections[0].x, intersections[0].y))
            new_line2 = msp.add_line(start=(intersections[1].x, intersections[1].y), 
                                   end=(end.x, end.y))
            new_line1.dxf.layer = line.dxf.layer
            new_line2.dxf.layer = line.dxf.layer
            new_line1.dxf.color = line.dxf.color
            new_line2.dxf.color = line.dxf.color
            msp.delete_entity(line)
        elif dist_start_center > radius:
            # start가 원 밖에 있는 경우
            line.dxf.end = intersections[0] if (intersections[0] - start).magnitude < (intersections[1] - start).magnitude else intersections[1]
        elif dist_end_center > radius:
            # end가 원 밖에 있는 경우
            line.dxf.start = intersections[0] if (intersections[0] - end).magnitude < (intersections[1] - end).magnitude else intersections[1]

def find_line_near_circle(circle, lines, max_distance=1.0):
    """원의 선분에서 max_distance 내에 접하는 라인 찾기"""
    center = Vec2(circle.dxf.center.x, circle.dxf.center.y)
    radius = circle.dxf.radius
    
    for line in lines:
        start = Vec2(line.dxf.start.x, line.dxf.start.y)
        end = Vec2(line.dxf.end.x, line.dxf.end.y)
        
        # 라인과 원의 최단 거리 계산
        line_vec = end - start
        line_length = line_vec.magnitude
        if line_length == 0:
            continue
            
        line_dir = line_vec / line_length
        center_to_start = center - start
        projection_length = center_to_start.dot(line_dir)
        
        if projection_length < 0:
            closest_point = start
        elif projection_length > line_length:
            closest_point = end
        else:
            closest_point = start + line_dir * projection_length
            
        distance_to_circle = (center - closest_point).magnitude - radius
        
        if abs(distance_to_circle) <= max_distance:
            return line, start, end
            
    return None, None, None

def find_lines_near_point(point, lines, max_distance=0.2, min_length=None, max_length=None):
    """점 근처의 라인들 찾기 (길이 범위 추가)"""
    found_lines = []
    
    for line in lines:
        start = (line.dxf.start.x, line.dxf.start.y)
        end = (line.dxf.end.x, line.dxf.end.y)
        length = get_distance(start, end)
        
        # 길이 조건 확인
        if min_length is not None and length < min_length:
            continue
        if max_length is not None and length > max_length:
            continue
        
        # 점과 라인의 최단 거리 계산
        if get_distance(point, start) <= max_distance or get_distance(point, end) <= max_distance:
            found_lines.append(line)
                
    return found_lines

def get_line_angle(line):
    """라인의 기울기(각도) 계산"""
    dx = line.dxf.end.x - line.dxf.start.x
    dy = line.dxf.end.y - line.dxf.start.y
    return math.atan2(dy, dx)

def move_entities(entities, dx, dy):
    """엔티티들을 이동"""
    for entity in entities:
        if isinstance(entity, Circle):
            entity.dxf.center = Vec2(entity.dxf.center.x + dx, entity.dxf.center.y + dy)
        elif isinstance(entity, Line):
            entity.dxf.start = Vec2(entity.dxf.start.x + dx, entity.dxf.start.y + dy)
            entity.dxf.end = Vec2(entity.dxf.end.x + dx, entity.dxf.end.y + dy)
        elif isinstance(entity, (Text, MText)):
            if hasattr(entity.dxf, 'insert'):
                entity.dxf.insert = Vec2(entity.dxf.insert[0] + dx, entity.dxf.insert[1] + dy)

def extend_line_to_circle(line, point_to_extend, circle):
    """라인을 원까지 확장"""
    center = Vec2(circle.dxf.center.x, circle.dxf.center.y)
    radius = circle.dxf.radius
    
    # 라인의 방향 벡터 계산
    start = Vec2(line.dxf.start.x, line.dxf.start.y)
    end = Vec2(line.dxf.end.x, line.dxf.end.y)
    
    if get_distance(point_to_extend, start) < 0.1:
        # start 점을 확장
        direction = (start - end).normalize()
        # 원과 라인의 교점 계산
        t = 2 * radius  # 충분히 긴 거리
        new_point = start + direction * t
        
        # 실제 교점 찾기
        for i in range(100):
            test_point = start + direction * (t * i / 100)
            if abs(get_distance((test_point.x, test_point.y), (center.x, center.y)) - radius) < 0.1:
                line.dxf.start = test_point
                break
    else:
        # end 점을 확장
        direction = (end - start).normalize()
        t = 2 * radius
        new_point = end + direction * t
        
        for i in range(100):
            test_point = end + direction * (t * i / 100)
            if abs(get_distance((test_point.x, test_point.y), (center.x, center.y)) - radius) < 0.1:
                line.dxf.end = test_point
                break

def find_ilines_near_circle(inno_circle, lines):
    """INNO 원 중심에서 15mm 내에서 3~6.5mm 길이의 ISOTEXT 레이어 LINE 정확히 4개 찾기"""
    inno_center = (inno_circle.dxf.center.x, inno_circle.dxf.center.y)
    ilines = []
    
    for line in lines:
        if line.dxf.layer != 'ISOTEXT':
            continue
            
        # 선분의 길이 확인 (3~6.5mm로 수정)
        length = get_line_length(line)
        if not (3 <= length <= 6.5):
            continue
            
        # 선분의 중심점 계산
        line_center = get_line_center(line)
        
        # INNO 중심에서 15mm 이내인지 확인
        if get_distance(inno_center, line_center) <= 15:
            ilines.append(line)
            
        # 정확히 4개만 찾기
        if len(ilines) == 4:
            break
            
    return ilines

def find_text_near_lines(ilines, texts, max_distance=3.0):
    """ILINE 중심에서 3mm 내의 기울기 0인 숫자 텍스트 찾기"""
    it_texts = []
    
    for line in ilines:
        line_center = get_line_center(line)
        
        for text in texts:
            # 텍스트 위치 확인
            if hasattr(text.dxf, 'insert'):
                text_pos = (text.dxf.insert[0], text.dxf.insert[1])
            else:
                continue
            
            # 거리, 수평성, 숫자 여부 확인
            if (get_distance(line_center, text_pos) <= max_distance and 
                is_text_horizontal(text) and 
                is_numeric_text(text) and
                text not in it_texts):
                it_texts.append(text)
                break  # 각 라인당 하나씩만
                
    return it_texts

def get_circle_top_point(circle):
    """원의 수직 끝점 (Y값이 가장 큰 접점) 계산"""
    center_x = circle.dxf.center.x
    center_y = circle.dxf.center.y
    radius = circle.dxf.radius
    return (center_x, center_y + radius)

def find_info_line_near_point(point, lines, max_distance=2.0):
    """AP2에서 2mm 내에서 LINE의 선분이 지나는 특정 레이어의 LINE 찾기 (DL, WL 제외)"""
    for line in lines:
        # DL, WL 레이어 제외
        if line.dxf.layer in ['DL', 'WL']:
            continue
            
        if line.dxf.layer not in ['WELDS', 'NOZZLES', 'FITTINGS']:
            continue
            
        start = (line.dxf.start.x, line.dxf.start.y)
        end = (line.dxf.end.x, line.dxf.end.y)
        
        # 점과 선분 사이의 거리 계산
        dist = point_to_line_distance(point, start, end)
        if dist <= max_distance:
            return line
            
    return None

def process_dxf_file(filepath):
    """DXF 파일 처리"""
    try:
        # DXF 파일 읽기
        doc = ezdxf.readfile(filepath)
        msp = doc.modelspace()
        
        # 1. ISOTEXT 레이어의 원 중 지름이 11-18mm인 원 찾기
        inno_circles = []
        for entity in msp:
            if isinstance(entity, Circle) and entity.dxf.layer == 'ISOTEXT':
                diameter = get_circle_diameter(entity)
                if 11 <= diameter <= 18:
                    inno_circles.append(entity)
                    entity.dxf.layer = 'INNO'
                    entity.dxf.color = 4  # CYAN
        
        if not inno_circles:
            print(f"No circles with diameter 11-18mm found in ISOTEXT layer in {filepath}")
            return
        
        # 모든 텍스트 엔티티 수집
        all_texts = [e for e in msp if isinstance(e, (Text, MText))]
        
        # 각 INNO 원에 대해 처리
        all_entities_to_modify = []
        used_del2_circles = []  # 이미 사용된 DEL2 원들을 추적
        
        for inno in inno_circles:
            inno_center = (inno.dxf.center.x, inno.dxf.center.y)
            
            # 2. INNO 원 안의 기울기 0인 텍스트 찾기 (ITAG)
            itag_texts = []
            for entity in msp:
                if isinstance(entity, (Text, MText)):
                    if hasattr(entity.dxf, 'insert'):
                        text_pos = (entity.dxf.insert[0], entity.dxf.insert[1])
                    else:
                        continue
                        
                    if is_point_in_circle(text_pos, inno) and is_text_horizontal(entity):
                        itag_texts.append(entity)
                        entity.dxf.color = 2  # YELLOW
            
            # INSTNO = INNO + ITAG
            instno_entities = [inno] + itag_texts
            
            # NEW: ILINE과 IT 찾기
            all_lines = [e for e in msp if isinstance(e, Line)]
            ilines = find_ilines_near_circle(inno, all_lines)
            
            itemno_entities = []
            if ilines:
                # ILINE 색상 변경
                for iline in ilines:
                    iline.dxf.color = 6  # MAGENTA (식별을 위해)
                
                # IT 텍스트 찾기
                it_texts = find_text_near_lines(ilines, all_texts)
                for it in it_texts:
                    it.dxf.color = 6  # MAGENTA
                
                # ITEMNO = ILINE + IT
                itemno_entities = ilines + it_texts
                
                # ILINE 중에서 INNO 중심과 가장 가까운 점 찾기 (IP)
                min_distance = float('inf')
                ip_point = None
                for iline in ilines:
                    closest_point = get_closest_point_to_center(iline, inno_center)
                    dist = get_distance(closest_point, inno_center)
                    if dist < min_distance:
                        min_distance = dist
                        ip_point = closest_point
                
                # ITEMNO를 IP에서 INNO의 수직 끝점으로 이동
                if ip_point:
                    top_point = get_circle_top_point(inno)
                    dx = top_point[0] - ip_point[0]
                    dy = top_point[1] - ip_point[1]
                    move_entities(itemno_entities, dx, dy)
                
                # ITEMNO를 INSTNO에 추가
                instno_entities.extend(itemno_entities)
            
            # 3. 원의 선분에서 1mm 내에 접하는 ISOTEXT 레이어 LINE 찾기 (A1)
            # DL, WL 레이어 제외
            isotext_lines = [e for e in msp if isinstance(e, Line) and e.dxf.layer == 'ISOTEXT' 
                           and e.dxf.layer not in ['DL', 'WL']]
            a1_line, ap1, ap2 = find_line_near_circle(inno, isotext_lines, 1.0)
            
            if not a1_line:
                continue
            
            a1_line.dxf.color = 4  # CYAN
            
            # AP1은 INNO에 가까운 점, AP2는 먼 점
            if get_distance(ap1, inno_center) > get_distance(ap2, inno_center):
                ap1, ap2 = ap2, ap1
            
            # 4. AP2 점 0.2mm 내에서 길이 2mm 이하 LINE 2개와 추가 LINE 찾기 (DEL1)
            # DL, WL 레이어 제외
            all_lines = [e for e in msp if isinstance(e, Line) and e.dxf.layer not in ['DL', 'WL']]
            lines_near_ap2 = find_lines_near_point(ap2, all_lines, 0.2, max_length=2.0)
            
            del1_lines = []
            additional_a1_lines = []  # A1에 추가된 LINE들을 저장
            
            if len(lines_near_ap2) >= 2:
                del1_lines.extend(lines_near_ap2[:2])
                
                # 추가 0.7~0.9mm LINE 찾기 (수정됨)
                for line in lines_near_ap2[:2]:
                    start = (line.dxf.start.x, line.dxf.start.y)
                    end = (line.dxf.end.x, line.dxf.end.y)
                    
                    additional_lines = find_lines_near_point(start, all_lines, 0.2, min_length=0.7, max_length=0.9)
                    additional_lines.extend(find_lines_near_point(end, all_lines, 0.2, min_length=0.7, max_length=0.9))
                    
                    for add_line in additional_lines:
                        if add_line not in del1_lines and len(del1_lines) < 3:
                            del1_lines.append(add_line)
                            break
                    
                    if len(del1_lines) >= 3:
                        break
            
            # DEL1이 찾아지지 않으면 추가 검색
            if len(del1_lines) < 3:
                # AP2에서 0.2mm 내에서 LINE을 찾아서 A0로 명명
                for line in all_lines:
                    if line == a1_line or line in del1_lines:
                        continue
                    
                    start = (line.dxf.start.x, line.dxf.start.y)
                    end = (line.dxf.end.x, line.dxf.end.y)
                    
                    # AP2와 가까운 점 찾기 (A0 찾기)
                    if get_distance(ap2, start) <= 0.2:
                        # A0 찾음 - A1과 병합
                        a0_line = line
                        additional_a1_lines.append(a0_line)  # A0를 추가 LINE으로 저장
                        
                        # A1 라인 연장 (A1 + A0 = A1)
                        if get_distance(ap1, a1_line.dxf.start) < 0.1:
                            a1_line.dxf.start = Vec2(end[0], end[1])
                        else:
                            a1_line.dxf.end = Vec2(end[0], end[1])
                        
                        # A0의 끝점을 새로운 AP2로 설정
                        ap2 = end
                        
                        # 새로운 AP2에서 다시 DEL1 찾기
                        lines_near_ap2 = find_lines_near_point(ap2, all_lines, 0.2, max_length=2.0)
                        del1_lines = []
                        if len(lines_near_ap2) >= 2:
                            del1_lines.extend(lines_near_ap2[:2])
                            
                            for line2 in lines_near_ap2[:2]:
                                start2 = (line2.dxf.start.x, line2.dxf.start.y)
                                end2 = (line2.dxf.end.x, line2.dxf.end.y)
                                
                                additional_lines = find_lines_near_point(start2, all_lines, 0.2, min_length=0.7, max_length=0.9)
                                additional_lines.extend(find_lines_near_point(end2, all_lines, 0.2, min_length=0.7, max_length=0.9))
                                
                                for add_line in additional_lines:
                                    if add_line not in del1_lines and len(del1_lines) < 3:
                                        del1_lines.append(add_line)
                                        break
                                
                                if len(del1_lines) >= 3:
                                    break
                        break
                        
                    elif get_distance(ap2, end) <= 0.2:
                        # A0 찾음 - A1과 병합
                        a0_line = line
                        additional_a1_lines.append(a0_line)  # A0를 추가 LINE으로 저장
                        
                        # A1 라인 연장 (A1 + A0 = A1)
                        if get_distance(ap1, a1_line.dxf.start) < 0.1:
                            a1_line.dxf.start = Vec2(start[0], start[1])
                        else:
                            a1_line.dxf.end = Vec2(start[0], start[1])
                        
                        # A0의 끝점을 새로운 AP2로 설정
                        ap2 = start
                        
                        # 새로운 AP2에서 다시 DEL1 찾기
                        lines_near_ap2 = find_lines_near_point(ap2, all_lines, 0.2, max_length=2.0)
                        del1_lines = []
                        if len(lines_near_ap2) >= 2:
                            del1_lines.extend(lines_near_ap2[:2])
                            
                            for line2 in lines_near_ap2[:2]:
                                start2 = (line2.dxf.start.x, line2.dxf.start.y)
                                end2 = (line2.dxf.end.x, line2.dxf.end.y)
                                
                                additional_lines = find_lines_near_point(start2, all_lines, 0.2, min_length=0.7, max_length=0.9)
                                additional_lines.extend(find_lines_near_point(end2, all_lines, 0.2, min_length=0.7, max_length=0.9))
                                
                                for add_line in additional_lines:
                                    if add_line not in del1_lines and len(del1_lines) < 3:
                                        del1_lines.append(add_line)
                                        break
                                
                                if len(del1_lines) >= 3:
                                    break
                        break
            
            # DEL1 라인들을 CYAN으로 변경
            for line in del1_lines:
                line.dxf.color = 4  # CYAN
            
            # TYPE1 또는 TYPE2 처리
            processed_type = None
            
            # 5. TYPE1: AP2에서 10mm 내의 FITTINGS 레이어 원 찾기 (DEL2)
            del2_circle = None
            for entity in msp:
                if isinstance(entity, Circle) and entity.dxf.layer == 'FITTINGS':
                    # 이미 사용된 DEL2인지 확인
                    if entity in used_del2_circles:
                        continue
                        
                    diameter = get_circle_diameter(entity)
                    if 5 <= diameter <= 8:
                        circle_center = (entity.dxf.center.x, entity.dxf.center.y)
                        if get_distance(ap2, circle_center) <= 10:
                            del2_circle = entity
                            del2_circle.dxf.color = 4  # CYAN
                            used_del2_circles.append(entity)  # 사용된 DEL2로 표시
                            processed_type = "TYPE1"
                            break
            
            if del2_circle:  # TYPE1 처리
                # 6. DEL2 원을 접하는 FITTINGS 레이어 LINE 찾기 (INLINE)
                fittings_lines = [e for e in msp if isinstance(e, Line) and e.dxf.layer == 'FITTINGS']
                inline = None
                ap3 = None
                ap4 = None
                
                for line in fittings_lines:
                    if line == a1_line or line in del1_lines:
                        continue
                        
                    start = (line.dxf.start.x, line.dxf.start.y)
                    end = (line.dxf.end.x, line.dxf.end.y)
                    del2_center = (del2_circle.dxf.center.x, del2_circle.dxf.center.y)
                    
                    # 라인이 DEL2 원을 접하는지 확인
                    dist_start = get_distance(start, del2_center)
                    dist_end = get_distance(end, del2_center)
                    
                    if abs(dist_start - del2_circle.dxf.radius) < 1.0 or abs(dist_end - del2_circle.dxf.radius) < 1.0:
                        inline = line
                        inline.dxf.color = 4  # CYAN
                        if dist_start < dist_end:
                            ap3 = start
                            ap4 = end
                        else:
                            ap3 = end
                            ap4 = start
                        break
                
                if inline:
                    # 7. INSTNO를 INNO 중심에서 DEL2 중심으로 이동
                    dx = del2_circle.dxf.center.x - inno.dxf.center.x
                    dy = del2_circle.dxf.center.y - inno.dxf.center.y
                    move_entities(instno_entities, dx, dy)
                    
                    # 8. INLINE의 기울기로 INSTNO를 AP4에서 AP3 방향으로 15mm 이동
                    angle = get_line_angle(inline)
                    # AP4에서 AP3 방향 벡터
                    direction = Vec2(ap3[0] - ap4[0], ap3[1] - ap4[1]).normalize()
                    move_dx = direction.x * 15
                    move_dy = direction.y * 15
                    move_entities(instno_entities, move_dx, move_dy)
                    
                    # 9. INLINE의 AP3 점을 INNO 선분까지 확장
                    extend_line_to_circle(inline, ap3, inno)
                    
                    # 10. 모든 엔티티를 INSTNO 레이어로 변경하고 CYAN 색상으로
                    # DEL1, DEL2, A1과 A1에 추가된 LINE들은 삭제하고 나머지만 처리
                    entities_to_delete = del1_lines + [del2_circle, a1_line] + additional_a1_lines
                    entities_to_modify = instno_entities + [inline, inno]
                    
                    # 삭제할 엔티티들 삭제
                    for entity in entities_to_delete:
                        if entity:
                            try:
                                msp.delete_entity(entity)
                            except:
                                pass
                    
                    # 나머지 엔티티들 처리
                    for entity in entities_to_modify:
                        if entity:
                            entity.dxf.layer = 'INSTNO'
                            if entity not in itag_texts and entity not in it_texts:  # ITAG와 IT는 색상 유지
                                entity.dxf.color = 4  # CYAN
                            all_entities_to_modify.append(entity)
            
            else:  # TYPE2 처리
                # AP2에서 2mm 내에서 LINE 찾기 (INFO)
                info_line = find_info_line_near_point(ap2, all_lines, 2.0)
                
                if info_line:
                    processed_type = "TYPE2"
                    info_line.dxf.color = 4  # CYAN
                    
                    # 최초 INNO 위치 저장
                    original_inno_center = inno_center
                    
                    # INFO의 중심
                    info_center = get_line_center(info_line)
                    
                    # 1. 먼저 INSTNO를 INFO 중심으로 이동
                    dx_to_center = info_center[0] - inno_center[0]
                    dy_to_center = info_center[1] - inno_center[1]
                    move_entities(instno_entities, dx_to_center, dy_to_center)
                    
                    # 2. INFO에 ISO 직교하는 방향으로 15mm 이동 
                    # AP2에서 최초 INNO를 바라보는 방향
                    perp_direction = get_iso_perpendicular_direction(info_line, ap2, original_inno_center)
                    
                    # AP2를 기준으로 직교 방향 계산
                    # INFO와 AP2의 교점에서 직교 방향으로 이동
                    ap2_to_info_center = Vec2(info_center[0] - ap2[0], info_center[1] - ap2[1])
                    projection_length = ap2_to_info_center.dot(perp_direction)
                    
                    dx_perp = perp_direction.x * 15
                    dy_perp = perp_direction.y * 15
                    move_entities(instno_entities, dx_perp, dy_perp)
                    
                    # INNO의 새 위치 계산 (이동 후)
                    new_inno_center = (inno_center[0] + dx_to_center + dx_perp, 
                                      inno_center[1] + dy_to_center + dy_perp)
                    
                    # 3. 간섭 체크
                    all_entities = list(msp)
                    if check_interference(instno_entities, all_entities):
                        # 간섭이 있으면 추가로 3mm 이동
                        dx_extra = perp_direction.x * 3
                        dy_extra = perp_direction.y * 3
                        move_entities(instno_entities, dx_extra, dy_extra)
                        
                        # 최종 위치 업데이트
                        new_inno_center = (new_inno_center[0] + dx_extra, 
                                         new_inno_center[1] + dy_extra)
                    
                    # 4. AP2와 INNO의 새 중심으로 선 그리기
                    new_line = msp.add_line(start=ap2, end=new_inno_center)
                    new_line.dxf.layer = 'INSTNO'
                    new_line.dxf.color = 4  # CYAN
                    
                    # 5. INNO 내의 선은 TRIM (이동된 INNO 위치 사용)
                    # INNO 원의 새 위치 업데이트
                    inno.dxf.center = Vec2(new_inno_center[0], new_inno_center[1])
                    trim_line_inside_circle(new_line, inno, msp)
                    
                    # DEL1과 A1, A1에 추가된 LINE들 삭제
                    entities_to_delete = del1_lines + [a1_line] + additional_a1_lines
                    for entity in entities_to_delete:
                        if entity:
                            try:
                                msp.delete_entity(entity)
                            except:
                                pass
                    
                    # 엔티티들 처리
                    entities_to_modify = instno_entities + [info_line, inno]
                    for entity in entities_to_modify:
                        if entity:
                            entity.dxf.layer = 'INSTNO'
                            if entity not in itag_texts and entity not in it_texts:
                                entity.dxf.color = 4  # CYAN
                            all_entities_to_modify.append(entity)
        
        # 11. 파일 저장
        base_name = os.path.splitext(os.path.basename(filepath))[0]
        output_path = os.path.join(os.path.dirname(filepath), f"{base_name}_INST.DXF")
        doc.saveas(output_path)
        print(f"Processed file saved as: {output_path}")
        
    except Exception as e:
        print(f"Error processing {filepath}: {str(e)}")

def main():
    """메인 함수 - 파일 선택 대화상자 표시"""
    root = tk.Tk()
    root.withdraw()  # 메인 윈도우 숨기기
    
    # 파일 선택 대화상자
    file_paths = filedialog.askopenfilenames(
        title="Select DXF files",
        filetypes=[("DXF files", "*.dxf"), ("All files", "*.*")]
    )
    
    if not file_paths:
        print("No files selected.")
        return
    
    # 선택된 모든 파일 처리
    for filepath in file_paths:
        print(f"\nProcessing: {filepath}")
        process_dxf_file(filepath)
    
    print("\nAll files processed.")

if __name__ == "__main__":
    main()