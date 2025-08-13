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

def find_lines_near_point(point, lines, max_distance=0.2, max_length=None):
    """점 근처의 라인들 찾기"""
    found_lines = []
    
    for line in lines:
        start = (line.dxf.start.x, line.dxf.start.y)
        end = (line.dxf.end.x, line.dxf.end.y)
        
        # 점과 라인의 최단 거리 계산
        if get_distance(point, start) <= max_distance or get_distance(point, end) <= max_distance:
            if max_length is None or get_distance(start, end) <= max_length:
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
    
    if get_distance(point_to_extend, (start.x, start.y)) < get_distance(point_to_extend, (end.x, end.y)):
        # start 점을 확장
        direction = (start - end).normalize()
        # 원과 라인의 교점 계산
        t = 2 * radius  # 충분히 긴 거리
        
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
        
        for i in range(100):
            test_point = end + direction * (t * i / 100)
            if abs(get_distance((test_point.x, test_point.y), (center.x, center.y)) - radius) < 0.1:
                line.dxf.end = test_point
                break
    """라인을 원까지 강제로 확장 (방향 무관)"""
    center = Vec2(circle.dxf.center.x, circle.dxf.center.y)
    radius = circle.dxf.radius
    
    # 라인의 시작점과 끝점
    start = Vec2(line.dxf.start.x, line.dxf.start.y)
    end = Vec2(line.dxf.end.x, line.dxf.end.y)
    
    # point_to_extend가 start에 가까운지 end에 가까운지 확인
    dist_to_start = get_distance(point_to_extend, (start.x, start.y))
    dist_to_end = get_distance(point_to_extend, (end.x, end.y))
    
    if dist_to_start < dist_to_end:
        # start 점을 확장
        # start에서 원 중심으로의 방향
        to_center = center - start
        if to_center.magnitude > radius:
            # 원 외부에서 시작
            direction = to_center.normalize()
            # 원의 경계까지의 거리
            distance = to_center.magnitude - radius
            new_start = start + direction * distance
            line.dxf.start = new_start
    else:
        # end 점을 확장
        # end에서 원 중심으로의 방향
        to_center = center - end
        if to_center.magnitude > radius:
            # 원 외부에서 시작
            direction = to_center.normalize()
            # 원의 경계까지의 거리
            distance = to_center.magnitude - radius
            new_end = end + direction * distance
            line.dxf.end = new_end

def check_line_circle_intersection(line, circle):
    """라인과 원의 교차 여부 확인 (개선된 버전)"""
    center = Vec2(circle.dxf.center.x, circle.dxf.center.y)
    radius = circle.dxf.radius
    
    start = Vec2(line.dxf.start.x, line.dxf.start.y)
    end = Vec2(line.dxf.end.x, line.dxf.end.y)
    
    # 선분의 길이가 0인 경우 (점인 경우)
    if (end - start).magnitude < 0.001:
        # 점과 원의 거리로 판단
        return (start - center).magnitude <= radius
    
    # 선분을 매개변수 형태로 표현: P = start + t*(end-start), 0 <= t <= 1
    d = end - start
    f = start - center
    
    a = d.dot(d)
    b = 2 * f.dot(d)
    c = f.dot(f) - radius * radius
    
    # 선분의 시작점 또는 끝점이 원 내부에 있는지 먼저 체크
    start_dist = (start - center).magnitude
    end_dist = (end - center).magnitude
    
    if start_dist <= radius or end_dist <= radius:
        return True
    
    discriminant = b*b - 4*a*c
    
    if discriminant < 0:
        return False
    
    discriminant = math.sqrt(discriminant)
    
    if a != 0:  # 일반적인 경우
        t1 = (-b - discriminant) / (2*a)
        t2 = (-b + discriminant) / (2*a)
        
        # 선분 내에서 교차하는지 확인 (약간의 여유 포함)
        if (-0.001 <= t1 <= 1.001) or (-0.001 <= t2 <= 1.001):
            return True
        
        # 선분이 원 내부를 완전히 통과하는 경우
        if t1 < 0 and t2 > 1:
            return True
    
    # 추가로 선분과 원 중심의 최단 거리 체크
    # 선분 위의 가장 가까운 점 찾기
    t = max(0, min(1, -f.dot(d) / a))
    closest_point = start + d * t
    distance = (closest_point - center).magnitude
    
    return distance <= radius + 0.001  # 약간의 오차 허용

def find_ilines_near_circle(inno_circle, lines):
    """INNO 원 중심에서 15mm 내에서 3~5mm 길이의 ISOTEXT 레이어 LINE 4개 찾기"""
    inno_center = (inno_circle.dxf.center.x, inno_circle.dxf.center.y)
    ilines = []
    
    for line in lines:
        if line.dxf.layer != 'ISOTEXT':
            continue
            
        # 선분의 길이 확인 (3~5mm)
        length = get_line_length(line)
        if not (3 <= length <= 6.5):
            continue
            
        # 선분의 중심점 계산
        line_center = get_line_center(line)
        
        # INNO 중심에서 15mm 이내인지 확인
        if get_distance(inno_center, line_center) <= 15:
            ilines.append(line)
            
        # 4개만 찾으면 중단
        if len(ilines) >= 4:
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
            
            # A1 확장에 사용된 라인들을 추적
            a1_extension_lines = []
            
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
            it_texts = []  # it_texts를 미리 초기화
            
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
            isotext_lines = [e for e in msp if isinstance(e, Line) and e.dxf.layer == 'ISOTEXT']
            a1_line, ap1, ap2 = find_line_near_circle(inno, isotext_lines, 1.0)
            
            if not a1_line:
                continue
            
            a1_line.dxf.color = 4  # CYAN
            
            # AP1은 INNO에 가까운 점, AP2는 먼 점
            if get_distance(ap1, inno_center) > get_distance(ap2, inno_center):
                ap1, ap2 = ap2, ap1
            
            # 4. AP2 점 0.2mm 내에서 길이 2mm 이하 LINE 2개와 추가 LINE 찾기 (DEL1)
            all_lines = [e for e in msp if isinstance(e, Line)]
            lines_near_ap2 = find_lines_near_point(ap2, all_lines, 0.2, 2.0)
            
            del1_lines = []
            if len(lines_near_ap2) >= 2:
                del1_lines.extend(lines_near_ap2[:2])
                
                # 추가 1mm 이하 LINE 찾기
                for line in lines_near_ap2[:2]:
                    start = (line.dxf.start.x, line.dxf.start.y)
                    end = (line.dxf.end.x, line.dxf.end.y)
                    
                    additional_lines = find_lines_near_point(start, all_lines, 0.2, 1.0)
                    additional_lines.extend(find_lines_near_point(end, all_lines, 0.2, 1.0))
                    
                    for add_line in additional_lines:
                        if add_line not in del1_lines and len(del1_lines) < 3:
                            del1_lines.append(add_line)
                            break
                    
                    if len(del1_lines) >= 3:
                        break
            
            # DEL1이 찾아지지 않으면 추가 검색
            if len(del1_lines) < 3:
                # AP2에서 0.2mm 내에 접하는 A1과 동일한 방향의 LINE 찾기
                for line in all_lines:
                    if line == a1_line:
                        continue
                    
                    start = (line.dxf.start.x, line.dxf.start.y)
                    end = (line.dxf.end.x, line.dxf.end.y)
                    
                    # AP2와 가까운 점 찾기
                    if get_distance(ap2, start) <= 0.2:
                        # A1 라인 연장 (합치기)
                        if get_distance(ap1, a1_line.dxf.start) < 0.1:
                            a1_line.dxf.start = Vec2(end[0], end[1])
                        else:
                            a1_line.dxf.end = Vec2(end[0], end[1])
                        ap2 = end
                        
                        # 확장에 사용된 라인 추적
                        a1_extension_lines.append(line)
                        
                        # 새로운 AP2에서 다시 DEL1 찾기
                        lines_near_ap2 = find_lines_near_point(ap2, all_lines, 0.2, 2.0)
                        del1_lines = []
                        if len(lines_near_ap2) >= 2:
                            del1_lines.extend(lines_near_ap2[:2])
                            
                            for line2 in lines_near_ap2[:2]:
                                start2 = (line2.dxf.start.x, line2.dxf.start.y)
                                end2 = (line2.dxf.end.x, line2.dxf.end.y)
                                
                                additional_lines = find_lines_near_point(start2, all_lines, 0.2, 1.0)
                                additional_lines.extend(find_lines_near_point(end2, all_lines, 0.2, 1.0))
                                
                                for add_line in additional_lines:
                                    if add_line not in del1_lines and len(del1_lines) < 3:
                                        del1_lines.append(add_line)
                                        break
                                
                                if len(del1_lines) >= 3:
                                    break
                        break
                    elif get_distance(ap2, end) <= 0.2:
                        # A1 라인 연장 (합치기)
                        if get_distance(ap1, a1_line.dxf.start) < 0.1:
                            a1_line.dxf.start = Vec2(start[0], start[1])
                        else:
                            a1_line.dxf.end = Vec2(start[0], start[1])
                        ap2 = start
                        
                        # 확장에 사용된 라인 추적
                        a1_extension_lines.append(line)
                        
                        # 새로운 AP2에서 다시 DEL1 찾기
                        lines_near_ap2 = find_lines_near_point(ap2, all_lines, 0.2, 2.0)
                        del1_lines = []
                        if len(lines_near_ap2) >= 2:
                            del1_lines.extend(lines_near_ap2[:2])
                            
                            for line2 in lines_near_ap2[:2]:
                                start2 = (line2.dxf.start.x, line2.dxf.start.y)
                                end2 = (line2.dxf.end.x, line2.dxf.end.y)
                                
                                additional_lines = find_lines_near_point(start2, all_lines, 0.2, 1.0)
                                additional_lines.extend(find_lines_near_point(end2, all_lines, 0.2, 1.0))
                                
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
            
            # 5. AP2에서 10mm 내의 FITTINGS 레이어 원 찾기 (TYPE1/DEL2)
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
                            break
            
            if not del2_circle:
                continue
            
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
            
            if not inline:
                continue
            
            # 7. INSTNO를 INNO 중심에서 DEL2 중심으로 이동 (ITEMNO 포함)
            dx = del2_circle.dxf.center.x - inno.dxf.center.x
            dy = del2_circle.dxf.center.y - inno.dxf.center.y
            move_entities(instno_entities, dx, dy)
            
            # 8. INLINE의 기울기로 INSTNO를 AP4에서 AP3 방향으로 15mm 이동 (ITEMNO 포함)
            angle = get_line_angle(inline)
            # AP4에서 AP3 방향 벡터
            direction = Vec2(ap3[0] - ap4[0], ap3[1] - ap4[1]).normalize()
            move_dx = direction.x * 15
            move_dy = direction.y * 15
            move_entities(instno_entities, move_dx, move_dy)
            
            # 8-1. DL 레이어 LINE과 INNO 원의 간섭 체크
            # 레이어 이름 대소문자 무시
            dl_lines = [e for e in msp if isinstance(e, Line) and e.dxf.layer.upper() == 'DL']
            interference_found = False
            
            print(f"\n=== Interference Check for INNO at ({inno.dxf.center.x:.2f}, {inno.dxf.center.y:.2f}) ===")
            print(f"INNO radius: {inno.dxf.radius:.2f}")
            
            if dl_lines:  # DL 레이어가 있는 경우에만 체크
                print(f"Found {len(dl_lines)} DL layer lines")
                for idx, dl_line in enumerate(dl_lines):
                    start = (dl_line.dxf.start.x, dl_line.dxf.start.y)
                    end = (dl_line.dxf.end.x, dl_line.dxf.end.y)
                    
                    # 선분과 원 중심의 최단 거리 계산 (디버깅용)
                    line_vec = Vec2(end[0] - start[0], end[1] - start[1])
                    line_length = line_vec.magnitude
                    if line_length > 0:
                        line_dir = line_vec / line_length
                        center_to_start = Vec2(inno.dxf.center.x - start[0], inno.dxf.center.y - start[1])
                        projection = center_to_start.dot(line_dir)
                        projection = max(0, min(line_length, projection))
                        closest_point = Vec2(start[0], start[1]) + line_dir * projection
                        min_distance = (Vec2(inno.dxf.center.x, inno.dxf.center.y) - closest_point).magnitude
                        
                        print(f"  DL line {idx}: ({start[0]:.2f},{start[1]:.2f}) to ({end[0]:.2f},{end[1]:.2f})")
                        print(f"    Min distance to INNO center: {min_distance:.2f} (radius: {inno.dxf.radius:.2f})")
                    
                    if check_line_circle_intersection(dl_line, inno):
                        interference_found = True
                        print(f"  >>> INTERFERENCE DETECTED with DL line {idx}!")
                        break
                    
                if not interference_found:
                    print("  No interference detected with any DL lines")
            else:
                # 모든 레이어의 선분을 확인하여 DL 유사 레이어가 있는지 체크
                all_layers = set(e.dxf.layer for e in msp if isinstance(e, Line))
                print(f"No DL layer lines found. Available line layers: {list(all_layers)}")
                
                # DL과 유사한 레이어 이름 찾기
                dl_like_layers = [layer for layer in all_layers if 'DL' in layer.upper()]
                if dl_like_layers:
                    print(f"Found similar layers: {dl_like_layers}")
            
            # 8-2. 간섭이 발생하면 4mm 추가 이동
            if interference_found:
                additional_move_dx = direction.x * 4
                additional_move_dy = direction.y * 4
                move_entities(instno_entities, additional_move_dx, additional_move_dy)
                print(f">>> Additional 4mm movement applied: dx={additional_move_dx:.2f}, dy={additional_move_dy:.2f}")
            
            # 9. INLINE의 AP3 점을 INNO 선분까지 확장 (모든 경우에 동일한 방식 사용)
            # AP3가 start인지 end인지 확인
            start = (inline.dxf.start.x, inline.dxf.start.y)
            end = (inline.dxf.end.x, inline.dxf.end.y)
            
            # AP3는 DEL2에 가까운 점
            dist_start_to_del2 = get_distance(start, (del2_circle.dxf.center.x, del2_circle.dxf.center.y))
            dist_end_to_del2 = get_distance(end, (del2_circle.dxf.center.x, del2_circle.dxf.center.y))
            
            if dist_start_to_del2 < dist_end_to_del2:
                # start가 AP3 (DEL2에 가까운 점)
                inno_center = Vec2(inno.dxf.center.x, inno.dxf.center.y)
                start_vec = Vec2(start[0], start[1])
                to_start = start_vec - inno_center
                if to_start.magnitude > 0:
                    direction_to_boundary = to_start.normalize()
                    boundary_point = inno_center + direction_to_boundary * inno.dxf.radius
                    inline.dxf.start = boundary_point
                    print(f"Extended INLINE start to INNO boundary: ({boundary_point.x:.2f}, {boundary_point.y:.2f})")
            else:
                # end가 AP3 (DEL2에 가까운 점)
                inno_center = Vec2(inno.dxf.center.x, inno.dxf.center.y)
                end_vec = Vec2(end[0], end[1])
                to_end = end_vec - inno_center
                if to_end.magnitude > 0:
                    direction_to_boundary = to_end.normalize()
                    boundary_point = inno_center + direction_to_boundary * inno.dxf.radius
                    inline.dxf.end = boundary_point
                    print(f"Extended INLINE end to INNO boundary: ({boundary_point.x:.2f}, {boundary_point.y:.2f})")
            
            # 10. 모든 엔티티를 INSTNO 레이어로 변경하고 CYAN 색상으로
            # DEL1, DEL2, A1, A1 확장 라인들은 삭제하고 나머지만 처리
            entities_to_delete = del1_lines + [del2_circle, a1_line] + a1_extension_lines
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