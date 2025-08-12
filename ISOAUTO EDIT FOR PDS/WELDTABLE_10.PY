import os
import re
import ezdxf
import tkinter as tk
from tkinter import filedialog
from math import hypot, sqrt, radians, cos, sin
import time
import shutil

def get_selected_dxf_files():
    root = tk.Tk()
    root.withdraw()
    return list(filedialog.askopenfilenames(
        title="DXF 파일을 선택하세요",
        filetypes=[("DXF files", "*.dxf")]
    ))

def extract_text_entities(doc):
    return [e for e in doc.modelspace() if e.dxftype() == 'TEXT']

def get_texts_by_position(entities):
    texts = []
    for e in entities:
        pos = e.dxf.insert
        texts.append((e.plain_text().strip(), round(pos.x, 2), round(pos.y, 2), e))
    return sorted(texts, key=lambda t: (-t[2], t[1]))

def extract_bore_from_size(size_text):
    match = re.search(r'(\d+)', size_text)
    return int(match.group(1)) if match else 100

def find_size_value_near_materials(all_texts):
    """FABRICATION MATERIALS 또는 ERECTION MATERIALS 근처에서 SIZE 값 찾기"""
    materials_pos = None
    materials_type = None
    
    # 먼저 FABRICATION MATERIALS 찾기
    for text, x, y, _ in all_texts:
        if "FABRICATION MATERIAL" in text.upper():
            materials_pos = (x, y)
            materials_type = "FABRICATION"
            print(f"✅ FABRICATION MATERIALS 찾음: ({x:.2f}, {y:.2f})")
            break
    
    # FABRICATION MATERIALS가 없으면 ERECTION MATERIALS 찾기
    if not materials_pos:
        for text, x, y, _ in all_texts:
            if "ERECTION MATERIAL" in text.upper():
                materials_pos = (x, y)
                materials_type = "ERECTION"
                print(f"✅ ERECTION MATERIALS 찾음: ({x:.2f}, {y:.2f})")
                break
    
    if not materials_pos:
        print("⚠ 'FABRICATION MATERIALS' 및 'ERECTION MATERIALS' 텍스트를 찾을 수 없습니다.")
        return None
    
    # SIZE 텍스트 찾기
    size_candidates = [
        (text, x, y) for text, x, y, _ in all_texts
        if "SIZE" in text.upper() and hypot(x - materials_pos[0], y - materials_pos[1]) <= 100
    ]
    if not size_candidates:
        print(f"⚠ SIZE 텍스트가 '{materials_type} MATERIALS' 반경 100mm 내에 없습니다.")
        return None
    
    size_text, size_x, size_y = sorted(size_candidates, key=lambda t: hypot(t[1] - materials_pos[0], t[2] - materials_pos[1]))[0]
    below_texts = [t for t in all_texts if abs(t[1] - size_x) < 1 and t[2] < size_y]
    if not below_texts:
        print("⚠ SIZE 아래 텍스트가 없습니다.")
        return None
    
    size_value = sorted(below_texts, key=lambda t: size_y - t[2])[0][0]
    print(f"✅ SIZE 값 찾음: {size_value} ({materials_type} MATERIALS 기준)")
    return size_value

def find_dn_header_x(all_texts):
    """ 'NO', '/FLD', 'DN' 헤더가 수평으로 나열된 경우 그 중 DN 텍스트의 X 좌표를 반환 """
    header_groups = []
    texts_by_y = {}
    for text, x, y, _ in all_texts:
        texts_by_y.setdefault(round(y, 1), []).append((text.strip().upper(), x))

    for y, items in texts_by_y.items():
        headers = {t[0]: t[1] for t in items}
        if all(k in headers for k in ['NO', '/FLD', 'DN']):
            dn_x = headers['DN']
            return dn_x  # DN 텍스트 X 좌표 반환

    return None

def find_header_positions(all_texts):
    headers = {}
    for text, x, y, _ in all_texts:
        txt = text.strip().upper()
        for key in ['NO', 'TYPE', '/FLD']:
            if key in txt:
                headers[key] = (round(x, 2), round(y, 2))
    return headers

def find_circle_entities(doc, radius):
    """주어진 반지름의 원을 찾는 함수"""
    circles = []
    msp = doc.modelspace()
    for e in msp:
        if e.dxftype() == 'CIRCLE' and abs(e.dxf.radius - radius) < 0.5:
            circles.append(e)
    return circles

def find_text_in_circle(all_texts, circle_center, radius):
    """원 안에 있는 텍스트를 찾는 함수"""
    texts_in_circle = []
    for text, x, y, e in all_texts:
        dist = hypot(x - circle_center[0], y - circle_center[1])
        if dist <= radius:
            texts_in_circle.append((text, x, y, e))
    return texts_in_circle

def find_entities_by_layer(doc, layer_names):
    """특정 레이어의 엔티티를 찾는 함수"""
    entities = []
    msp = doc.modelspace()
    for e in msp:
        if hasattr(e, 'dxf') and hasattr(e.dxf, 'layer'):
            layer_upper = e.dxf.layer.upper()
            # TEE_ 패턴 처리
            if any(layer_upper.startswith('TEE_') for name in layer_names if name == 'TEE_'):
                entities.append(e)
                print(f"  TEE 레이어 {e.dxf.layer} 엔티티 발견: {e.dxftype()}")
            # 일반 레이어 처리
            elif layer_upper in [l.upper() for l in layer_names if l != 'TEE_']:
                entities.append(e)
                print(f"  레이어 {e.dxf.layer} 엔티티 발견: {e.dxftype()}")
    return entities

def get_entity_position(entity):
    """엔티티의 위치를 가져오는 함수"""
    if entity.dxftype() in ['TEXT', 'MTEXT']:
        return (entity.dxf.insert.x, entity.dxf.insert.y)
    elif entity.dxftype() == 'INSERT':  # 블록 참조
        return (entity.dxf.insert.x, entity.dxf.insert.y)
    elif entity.dxftype() == 'CIRCLE':
        return (entity.dxf.center.x, entity.dxf.center.y)
    elif entity.dxftype() == 'LINE':
        # 선의 중점
        return ((entity.dxf.start.x + entity.dxf.end.x) / 2,
                (entity.dxf.start.y + entity.dxf.end.y) / 2)
    elif entity.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
        # 폴리라인의 첫 점
        if entity.dxftype() == 'LWPOLYLINE':
            points = list(entity.get_points())
            if points:
                return (points[0][0], points[0][1])
        else:
            vertices = list(entity.vertices)
            if vertices:
                return (vertices[0].dxf.location.x, vertices[0].dxf.location.y)
    elif entity.dxftype() == 'ARC':
        return (entity.dxf.center.x, entity.dxf.center.y)
    return None

def find_circles_by_layer(doc, layer_name):
    """특정 레이어의 원을 찾는 함수"""
    circles = []
    msp = doc.modelspace()
    for e in msp:
        if e.dxftype() == 'CIRCLE' and hasattr(e, 'dxf') and hasattr(e.dxf, 'layer'):
            if e.dxf.layer.upper() == layer_name.upper():
                circles.append(e)
    return circles

def find_entities_touching_circle(doc, circle, layer_names):
    """원에 접하는 특정 레이어의 엔티티를 찾는 함수"""
    entities = []
    center = (circle.dxf.center.x, circle.dxf.center.y)
    radius = circle.dxf.radius
    
    layer_entities = find_entities_by_layer(doc, layer_names)
    
    for e in layer_entities:
        pos = get_entity_position(e)
        if pos:
            dist = hypot(pos[0] - center[0], pos[1] - center[1])
            # 원에 접하는 조건: 거리가 반지름과 비슷 (±2mm 허용)
            if abs(dist - radius) <= 2:
                entities.append(e)
    
    return entities

def has_bulge(entity):
    """폴리라인이 곡선(bulge)을 포함하는지 확인"""
    if entity.dxftype() == 'LWPOLYLINE':
        # LWPOLYLINE의 경우 get_points로 bulge 정보 확인
        points_with_bulge = list(entity.get_points('xyb'))
        for point in points_with_bulge:
            if len(point) > 2 and point[2] != 0:  # bulge가 0이 아니면 곡선
                return True
    elif entity.dxftype() == 'POLYLINE':
        # POLYLINE의 경우 각 vertex의 bulge 확인
        for vertex in entity.vertices:
            if hasattr(vertex.dxf, 'bulge') and vertex.dxf.bulge != 0:
                return True
    return False

def find_polylines_touching_entity(doc, entity, exclude_layers=[]):
    """엔티티의 선분에 접하는 2-3점 폴리라인을 찾는 함수 (최소 길이 5mm)"""
    polylines = []
    msp = doc.modelspace()
    
    # 엔티티의 선분들을 구함
    entity_segments = []
    if entity.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
        if entity.dxftype() == 'LWPOLYLINE':
            points = list(entity.get_points())
        else:
            points = [(v.dxf.location.x, v.dxf.location.y) for v in entity.vertices]
        
        for i in range(len(points) - 1):
            entity_segments.append(((points[i][0], points[i][1]), 
                                  (points[i+1][0], points[i+1][1])))
    elif entity.dxftype() == 'LINE':
        entity_segments.append(((entity.dxf.start.x, entity.dxf.start.y),
                              (entity.dxf.end.x, entity.dxf.end.y)))
    
    # 모든 폴리라인 검사
    for e in msp:
        if e.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
            if hasattr(e.dxf, 'layer') and e.dxf.layer.upper() in [l.upper() for l in exclude_layers]:
                continue
            
            # 곡선(bulge)이 있는 폴리라인은 제외
            if has_bulge(e):
                continue
            
            # 폴리라인의 점들
            if e.dxftype() == 'LWPOLYLINE':
                poly_points = list(e.get_points())
            else:
                poly_points = [(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]
            
            # 2-3점인 경우만
            if 2 <= len(poly_points) <= 3:
                # 길이 계산
                total_length = 0
                for i in range(len(poly_points) - 1):
                    dist = hypot(poly_points[i+1][0] - poly_points[i][0], 
                               poly_points[i+1][1] - poly_points[i][1])
                    total_length += dist
                
                # 길이가 5mm 이상인 경우만
                if total_length >= 5:
                    # 엔티티의 선분과 접하는지 확인
                    touching = False
                    for seg_start, seg_end in entity_segments:
                        for px, py, *_ in poly_points:
                            # 점에서 선분까지의 최단 거리 계산
                            dist = point_to_line_distance((px, py), seg_start, seg_end)
                            if dist <= 1:  # 1mm 이내면 접촉
                                touching = True
                                break
                        if touching:
                            break
                    
                    if touching:
                        polylines.append(e)
    
    return polylines

def point_to_line_distance(point, line_start, line_end):
    """점에서 선분까지의 최단 거리 계산"""
    px, py = point
    x1, y1 = line_start
    x2, y2 = line_end
    
    # 선분의 길이
    line_length = hypot(x2 - x1, y2 - y1)
    if line_length == 0:
        return hypot(px - x1, py - y1)
    
    # 매개변수 t 계산
    t = max(0, min(1, ((px - x1) * (x2 - x1) + (py - y1) * (y2 - y1)) / (line_length ** 2)))
    
    # 선분 위의 가장 가까운 점
    closest_x = x1 + t * (x2 - x1)
    closest_y = y1 + t * (y2 - y1)
    
    return hypot(px - closest_x, py - closest_y)

def get_segment_lengths(entity):
    """엔티티의 각 선분 길이를 계산하여 반환"""
    segments = []
    if entity.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
        if entity.dxftype() == 'LWPOLYLINE':
            points = list(entity.get_points())
        else:
            points = [(v.dxf.location.x, v.dxf.location.y) for v in entity.vertices]
        
        for i in range(len(points) - 1):
            start = (points[i][0], points[i][1])
            end = (points[i+1][0], points[i+1][1])
            length = hypot(end[0] - start[0], end[1] - start[1])
            segments.append({
                'start': start,
                'end': end,
                'length': length,
                'index': i
            })
    elif entity.dxftype() == 'LINE':
        start = (entity.dxf.start.x, entity.dxf.start.y)
        end = (entity.dxf.end.x, entity.dxf.end.y)
        length = hypot(end[0] - start[0], end[1] - start[1])
        segments.append({
            'start': start,
            'end': end,
            'length': length,
            'index': 0
        })
    
    return segments

def find_all_touching_segments(circle_center, radius, segments):
    """원이 접하는 모든 선분을 찾고, 각 선분의 접촉 부분 길이를 계산"""
    touching_segments = []
    for seg in segments:
        dist = point_to_line_distance(circle_center, seg['start'], seg['end'])
        if abs(dist - radius) <= 3:  # 3mm 허용 범위
            # 실제 접촉 구간의 길이 계산 (간단한 근사: 전체 선분이 접촉한다고 가정)
            contact_length = seg['length']
            touching_segments.append({
                'segment': seg,
                'contact_length': contact_length,
                'full_length': seg['length']
            })
    return touching_segments

def get_total_contact_length(circle_center, radius, segments):
    """원이 접하는 모든 선분의 길이 합 계산"""
    touching_segments = find_all_touching_segments(circle_center, radius, segments)
    total_length = sum(seg['contact_length'] for seg in touching_segments)
    return total_length, touching_segments

def find_pipe_entities_near_center(doc, center, search_radius):
    """중심점에서 지정된 반경 내의 PIPE_ 레이어 2점 요소 찾기"""
    msp = doc.modelspace()
    pipe_entities = []
    
    for e in msp:
        if e.dxftype() in ['LINE', 'POLYLINE', 'LWPOLYLINE']:
            if hasattr(e, 'dxf') and hasattr(e.dxf, 'layer'):
                if 'PIPE_' in e.dxf.layer.upper():
                    # 점 개수 확인
                    point_count = 0
                    if e.dxftype() == 'LINE':
                        point_count = 2
                    elif e.dxftype() == 'LWPOLYLINE':
                        point_count = len(list(e.get_points()))
                    elif e.dxftype() == 'POLYLINE':
                        point_count = len(list(e.vertices))
                    
                    # 2점인 경우만
                    if point_count == 2:
                        # 양 끝점의 거리 확인
                        include_entity = False
                        
                        if e.dxftype() == 'LINE':
                            start = (e.dxf.start.x, e.dxf.start.y)
                            end = (e.dxf.end.x, e.dxf.end.y)
                            dist_start = hypot(start[0] - center[0], start[1] - center[1])
                            dist_end = hypot(end[0] - center[0], end[1] - center[1])
                            if dist_start <= search_radius or dist_end <= search_radius:
                                include_entity = True
                        elif e.dxftype() == 'LWPOLYLINE':
                            points = list(e.get_points())
                            if len(points) == 2:
                                dist_start = hypot(points[0][0] - center[0], points[0][1] - center[1])
                                dist_end = hypot(points[1][0] - center[0], points[1][1] - center[1])
                                if dist_start <= search_radius or dist_end <= search_radius:
                                    include_entity = True
                        elif e.dxftype() == 'POLYLINE':
                            vertices = list(e.vertices)
                            if len(vertices) == 2:
                                dist_start = hypot(vertices[0].dxf.location.x - center[0], 
                                                 vertices[0].dxf.location.y - center[1])
                                dist_end = hypot(vertices[1].dxf.location.x - center[0], 
                                               vertices[1].dxf.location.y - center[1])
                                if dist_start <= search_radius or dist_end <= search_radius:
                                    include_entity = True
                        
                        if include_entity:
                            pipe_entities.append(e)
    
    return pipe_entities

def extract_wd_from_pipe_layer(layer_name):
    """PIPE_ 레이어명에서 WD 값 추출"""
    match = re.search(r'PIPE_(\d+)', layer_name.upper())
    if match:
        return int(match.group(1))
    return None

def extract_td_from_tee_layer(layer_name):
    """TEE_ 레이어명에서 TD 값 추출"""
    match = re.search(r'TEE_(\d+)', layer_name.upper())
    if match:
        return int(match.group(1))
    return None

def find_tee_entities_touching_circle(doc, circle):
    """TEE_ 레이어의 엔티티 중 어느 한 점이라도 원에 접하는 것을 찾는 함수"""
    entities = []
    center = (circle.dxf.center.x, circle.dxf.center.y)
    radius = circle.dxf.radius
    msp = doc.modelspace()
    
    for e in msp:
        if hasattr(e, 'dxf') and hasattr(e.dxf, 'layer'):
            layer_upper = e.dxf.layer.upper()
            if layer_upper.startswith('TEE_'):
                touching = False
                
                # 엔티티 타입별로 모든 점 검사
                if e.dxftype() == 'LINE':
                    # 시작점과 끝점 검사
                    points = [(e.dxf.start.x, e.dxf.start.y), 
                              (e.dxf.end.x, e.dxf.end.y)]
                    for px, py in points:
                        dist = hypot(px - center[0], py - center[1])
                        if abs(dist - radius) <= 2:
                            touching = True
                            break
                
                elif e.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
                    # 모든 점 검사
                    if e.dxftype() == 'LWPOLYLINE':
                        points = list(e.get_points())
                    else:
                        points = [(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]
                    
                    for point in points:
                        px, py = point[0], point[1]
                        dist = hypot(px - center[0], py - center[1])
                        if abs(dist - radius) <= 2:
                            touching = True
                            break
                
                elif e.dxftype() == 'CIRCLE':
                    # 원의 중심 검사
                    dist = hypot(e.dxf.center.x - center[0], e.dxf.center.y - center[1])
                    if abs(dist - radius) <= 2:
                        touching = True
                
                elif e.dxftype() in ['TEXT', 'MTEXT', 'INSERT']:
                    # 삽입점 검사
                    dist = hypot(e.dxf.insert.x - center[0], e.dxf.insert.y - center[1])
                    if abs(dist - radius) <= 2:
                        touching = True
                
                elif e.dxftype() == 'ARC':
                    # 아크의 경우 중심점과 시작/끝 각도의 점들 검사
                    cx, cy = e.dxf.center.x, e.dxf.center.y
                    r = e.dxf.radius
                    
                    # 중심점 검사
                    dist = hypot(cx - center[0], cy - center[1])
                    if abs(dist - radius) <= 2:
                        touching = True
                    else:
                        # 시작점과 끝점 검사
                        start_angle = radians(e.dxf.start_angle)
                        end_angle = radians(e.dxf.end_angle)
                        
                        # 시작점
                        sx = cx + r * cos(start_angle)
                        sy = cy + r * sin(start_angle)
                        dist = hypot(sx - center[0], sy - center[1])
                        if abs(dist - radius) <= 2:
                            touching = True
                        
                        # 끝점
                        if not touching:
                            ex = cx + r * cos(end_angle)
                            ey = cy + r * sin(end_angle)
                            dist = hypot(ex - center[0], ey - center[1])
                            if abs(dist - radius) <= 2:
                                touching = True
                
                if touching:
                    entities.append(e)
                    print(f"  TEE 레이어 {e.dxf.layer} 엔티티 발견 (모든 점 검사): {e.dxftype()}")
    
    return entities

def find_sfw_polylines_near_point(doc, point, search_radius):
    """특정 점에서 지정된 반경 내의 SFW 레이어 6점 폴리라인 찾기"""
    msp = doc.modelspace()
    sfw_polylines = []
    
    for e in msp:
        if e.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
            if hasattr(e, 'dxf') and hasattr(e.dxf, 'layer'):
                if e.dxf.layer.upper() == 'SFW':
                    # 점 개수 확인
                    if e.dxftype() == 'LWPOLYLINE':
                        points = list(e.get_points())
                        # 중심점 계산
                        center_x = sum(p[0] for p in points) / 6
                        center_y = sum(p[1] for p in points) / 6
                        # 각 점까지의 최소 거리 계산
                        min_point_dist = float('inf')
                        for p in points:
                            dist = hypot(p[0] - point[0], p[1] - point[1])
                            min_point_dist = min(min_point_dist, dist)
                    else:
                        points = list(e.vertices)
                        # 중심점 계산
                        center_x = sum(v.dxf.location.x for v in points) / 6
                        center_y = sum(v.dxf.location.y for v in points) / 6
                        # 각 점까지의 최소 거리 계산
                        min_point_dist = float('inf')
                        for v in points:
                            dist = hypot(v.dxf.location.x - point[0], v.dxf.location.y - point[1])
                            min_point_dist = min(min_point_dist, dist)
                    
                    if len(points) == 6:
                        # 중심점까지의 거리
                        center_dist = hypot(center_x - point[0], center_y - point[1])
                        
                        # 최소 거리가 검색 반경 내에 있으면 추가
                        if min_point_dist <= search_radius:
                            sfw_polylines.append({
                                'entity': e,
                                'center': (center_x, center_y),
                                'center_distance': center_dist,
                                'min_point_distance': min_point_dist
                            })
    
    return sorted(sfw_polylines, key=lambda x: x['min_point_distance'])

# 새로운 함수 추가 - 검색 거리를 5mm로 변경
def find_a2_polylines_near_sfw_center(doc, sfw_center, search_radius=5.0):
    """SFW 중심에서 지정된 반경 내에 끝점이 있는 2-3점 폴리라인 찾기 (PIPE 레이어 제외)"""
    msp = doc.modelspace()
    a2_candidates = []
    
    for e in msp:
        if e.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
            # PIPE 레이어는 제외
            if hasattr(e.dxf, 'layer') and e.dxf.layer.upper() == 'PIPE':
                continue
                
            # 곡선(bulge)이 있는 폴리라인은 제외
            if has_bulge(e):
                continue
                
            # 점들 가져오기
            if e.dxftype() == 'LWPOLYLINE':
                points = list(e.get_points())
            else:
                points = [(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]
            
            # 2-3점인 경우만
            if 2 <= len(points) <= 3:
                # 점간 거리 계산
                total_length = 0
                for i in range(len(points) - 1):
                    dist = hypot(points[i+1][0] - points[i][0], 
                               points[i+1][1] - points[i][1])
                    total_length += dist
                
                # 점간 거리가 5mm 이상인 경우만
                if total_length >= 5:
                    # 끝점 중 하나가 SFW 중심 5mm 내에 있는지 확인
                    first_point = (points[0][0], points[0][1])
                    last_point = (points[-1][0], points[-1][1])
                    
                    dist_first = hypot(first_point[0] - sfw_center[0], 
                                     first_point[1] - sfw_center[1])
                    dist_last = hypot(last_point[0] - sfw_center[0], 
                                    last_point[1] - sfw_center[1])
                    
                    if dist_first <= search_radius or dist_last <= search_radius:
                        # SFW에서 가장 먼 끝점 찾기
                        if dist_first < dist_last:
                            far_point = last_point
                            far_dist = dist_last
                        else:
                            far_point = first_point
                            far_dist = dist_first
                        
                        a2_candidates.append({
                            'entity': e,
                            'points': points,
                            'far_point': far_point,
                            'far_distance': far_dist,
                            'total_length': total_length
                        })
    
    return a2_candidates

def find_sftype_for_wno(all_texts, wno_x, wno_y):
    """WNO 위치에서 +X 25mm, Y ±1mm 범위 내에서 기울기 0인 'S', 'F', 'FF' 텍스트 찾기"""
    for text, x, y, e in all_texts:
        # X는 WNO보다 25mm 오른쪽, Y는 ±1mm 범위
        if (wno_x < x <= wno_x + 25 and 
            abs(y - wno_y) <= 1 and 
            abs(e.dxf.rotation) < 0.1):  # 회전각 0
            
            text_upper = text.strip().upper()
            if text_upper in ['S', 'F', 'FF']:
                print(f"  📍 SFTYPE 찾음: {text_upper} at ({x:.2f}, {y:.2f})")
                return text_upper
    return None

def process_weld_data(doc, all_texts, headers, dn_x, materials_x, bore_value):
    """용접 관련 데이터 처리 및 수집 - materials_x는 FABRICATION 또는 ERECTION MATERIALS의 x 좌표"""
    if 'NO' not in headers:
        return {}
    
    msp = doc.modelspace()
    no_x, no_y = headers['NO']
    weld_data = {}  # 각 행의 WBORE와 WTYPE 정보를 저장
    redu_sw_data = {}  # REDU에 대한 SW 정보 저장
    all_sw_info = {}  # 모든 WNO의 SW 정보를 저장 (REDU 처리용)
    skip_wtype_search = None  # REDU 처리로 WTYPE 검색을 건너뛸 WNO
    all_wno_sw_info = {}  # 모든 WNO의 SW 정보 저장 (TEE 후처리용)
    
    # 전역 추적 변수 - 사용된 엔티티들 추적
    global_used_sw = set()  # 사용된 SW 원 ID
    global_used_wtype = set()  # 사용된 OLET/WOLET/REDU 엔티티 ID
    global_used_sfw = set()  # 사용된 SFW 엔티티 ID
    
    # NO 아래의 숫자들 찾기 (WNO)
    wno_list = []
    y_positions = sorted(
        set(t[2] for t in all_texts if abs(t[1] - no_x) < 1 and t[2] < no_y and t[0].strip()),
        reverse=True
    )
    
    for y in y_positions:
        no_texts = [t for t in all_texts if abs(t[1] - no_x) < 1 and abs(t[2] - y) < 0.5]
        for text, x, y2, e in no_texts:
            if text.strip().isdigit():  # 정규식 대신 isdigit() 사용
                wno_list.append((text.strip(), x, y2, e))
                e.dxf.color = 4  # CYAN
                print(f"✅ WNO 찾음: {text.strip()} at ({x}, {y2})")
    
    # 각 WNO에 대해 처리
    for idx, (wno, wno_x, wno_y, wno_entity) in enumerate(wno_list):
        # 각 WNO마다 사용된 텍스트 추적 (독립적)
        local_used_texts = set()
        
        # WNO에 대한 SFTYPE 찾기
        sftype = find_sftype_for_wno(all_texts, wno_x, wno_y)
        
        # REDU 처리로 인해 WTYPE 검색을 건너뛸지 확인
        skip_wtype_for_this_wno = (skip_wtype_search is not None and int(wno) == skip_wtype_search)
        if skip_wtype_for_this_wno:
            print(f"🔍 WNO {wno}는 REDU 처리로 인해 WTYPE 검색을 건너뜁니다.")
            skip_wtype_search = None  # 한 번만 건너뛰기
            
        # SWNO 찾기
        swno_candidates = []
        for text, x, y, e in all_texts:
            # 조건: materials_x - 10보다 작고, no_y보다 위에 있고, 회전각 0, WNO와 같은 숫자
            if (x < materials_x - 10 and y > no_y and 
                text.strip() == wno and 
                abs(e.dxf.rotation) < 0.1):  # 회전각 0
                
                # 3mm 이하 원 안에 있는지 확인
                circles_3mm = find_circle_entities(doc, 3)
                for circle in circles_3mm:
                    center = (circle.dxf.center.x, circle.dxf.center.y)
                    if hypot(x - center[0], y - center[1]) <= 3:
                        swno_candidates.append((text, x, y, e, center))
                        e.dxf.color = 4  # CYAN
                        e.dxf.layer = 'WDNO'
                        print(f"✅ SWNO 찾음: {text} at ({x}, {y})")
                        break
        
        # 각 SWNO에 대해 처리
        for swno_text, swno_x, swno_y, swno_entity, circle_center in swno_candidates:
            print(f"\n  SWNO {swno_text} 처리 중...")
            
            # 1. SWNO로부터 30mm 내에 가장 가까운 SW 레이어 원 찾기
            sw_circles = find_circles_by_layer(doc, 'SW')
            print(f"  SW 레이어 원 개수: {len(sw_circles)}")
            
            closest_sw_circle = None
            min_sw_dist = float('inf')
            
            for circle in sw_circles:
                # 이미 사용된 SW는 제외
                if id(circle) in global_used_sw:
                    continue
                    
                center = (circle.dxf.center.x, circle.dxf.center.y)
                dist = hypot(center[0] - swno_x, center[1] - swno_y)
                if dist <= 30 and dist < min_sw_dist:
                    min_sw_dist = dist
                    closest_sw_circle = circle
            
            # SW 원을 찾았고 SFTYPE이 있으면 레이어 변경
            if closest_sw_circle and sftype:
                if sftype == 'F':
                    closest_sw_circle.dxf.layer = 'FW'
                    print(f"  🔄 SW 레이어를 FW로 변경 (SFTYPE: F)")
                elif sftype == 'FF':
                    closest_sw_circle.dxf.layer = 'FFW'
                    print(f"  🔄 SW 레이어를 FFW로 변경 (SFTYPE: FF)")
                # sftype == 'S'인 경우는 변경하지 않음
            
            # 2. SWNO 30mm 내에서 SFW 6점 폴리라인(SD) 찾기
            sfw_polylines = find_sfw_polylines_near_point(doc, (swno_x, swno_y), 30)
            
            # 사용되지 않은 SFW만 필터링
            available_sfw = []
            for sfw in sfw_polylines:
                if id(sfw['entity']) not in global_used_sfw:
                    available_sfw.append(sfw)
            
            # 3. SW와 SFW 중 더 가까운 것 선택
            use_sfw = False
            selected_sfw = None
            
            if available_sfw and closest_sw_circle:
                # 둘 다 있을 때: SFW의 가장 가까운 점과 SW 중심 거리 비교
                closest_sfw = available_sfw[0]  # 가장 가까운 점 기준으로 정렬됨
                if closest_sfw['min_point_distance'] < min_sw_dist:
                    use_sfw = True
                    selected_sfw = closest_sfw
                    print(f"  🔄 SFW가 SW보다 가까움 (SFW 점: {closest_sfw['min_point_distance']:.2f}mm vs SW: {min_sw_dist:.2f}mm)")
            elif available_sfw and not closest_sw_circle:
                # SFW만 있을 때
                use_sfw = True
                selected_sfw = available_sfw[0]
                print(f"  🔄 SW 없음, SFW 사용")
            
            # 4. SFW 처리
            if use_sfw and selected_sfw:
                sd_entity = selected_sfw['entity']
                sd_center = selected_sfw['center']
                sd_entity.dxf.color = 1  # RED로 변경
                
                print(f"  📍 SD 중심: ({sd_center[0]:.2f}, {sd_center[1]:.2f})")
                print(f"  🔴 SFW 색상을 RED로 변경")
                
                # SD 중심에서 0~13mm 내 PIPE_ 레이어 찾기
                pipe_entities = find_pipe_entities_near_center(doc, sd_center, 13.0)
                
                if pipe_entities:
                    # 첫 번째 PIPE_ 엔티티 처리
                    pipe_entity = pipe_entities[0]
                    
                    # WD 추출
                    wd = extract_wd_from_pipe_layer(pipe_entity.dxf.layer)
                    if wd is not None:
                        # WD가 55를 넘으면 SKIP하고 SW 처리로 전환
                        if wd > 55:
                            print(f"  ⚠ WD 값이 55를 초과 (WD={wd}), SFW 중심에서 SW 원 검색으로 전환")
                            
                            # SFW 중심에서 10mm 범위에 SW 원 찾기
                            sw_circles_near_sfw = []
                            sw_circles = find_circles_by_layer(doc, 'SW')
                            
                            for circle in sw_circles:
                                # 이미 사용된 SW는 제외
                                if id(circle) in global_used_sw:
                                    continue
                                    
                                center = (circle.dxf.center.x, circle.dxf.center.y)
                                dist = hypot(center[0] - sd_center[0], center[1] - sd_center[1])
                                if dist <= 10:  # 10mm 범위
                                    sw_circles_near_sfw.append((circle, dist))
                            
                            if sw_circles_near_sfw:
                                # 가장 가까운 SW 원 선택
                                sw_circle, sw_dist = min(sw_circles_near_sfw, key=lambda x: x[1])
                                sw_circle.dxf.color = 1  # RED
                                sw_center = (sw_circle.dxf.center.x, sw_circle.dxf.center.y)
                                sw_radius = sw_circle.dxf.radius
                                print(f"  ✅ SFW 중심에서 SW 원 찾음 (거리: {sw_dist:.2f}mm)")
                                
                                # SFTYPE에 따라 레이어 변경
                                if sftype == 'F':
                                    sw_circle.dxf.layer = 'FW'
                                    print(f"  🔄 SW 레이어를 FW로 변경 (SFTYPE: F)")
                                elif sftype == 'FF':
                                    sw_circle.dxf.layer = 'FFW'
                                    print(f"  🔄 SW 레이어를 FFW로 변경 (SFTYPE: FF)")
                                
                                # 사용된 SW 추적에 추가
                                global_used_sw.add(id(sw_circle))
                                
                                # SW 원에 접하는 OLET 찾기
                                touching_entities = find_entities_touching_circle(doc, sw_circle, ['OLET'])
                                
                                # 사용되지 않은 엔티티만 필터링
                                available_entities = []
                                for entity in touching_entities:
                                    if id(entity) not in global_used_wtype:
                                        available_entities.append(entity)
                                
                                for wtype_entity in available_entities:
                                    wtype_entity.dxf.color = 4  # CYAN
                                    wtype_found = wtype_entity.dxf.layer.upper()
                                    wtype_pos = get_entity_position(wtype_entity)
                                    print(f"  ✅ OLET 찾음, 색상을 CYAN으로 변경")
                                    
                                    # 사용된 OLET 추적에 추가
                                    global_used_wtype.add(id(wtype_entity))
                                    
                                    # OLET의 선분에 접하는 2-3점 폴리라인(A2) 찾기
                                    a2_polylines = find_polylines_touching_entity(doc, wtype_entity, exclude_layers=['PIPE'])
                                    
                                    for poly in a2_polylines:
                                        poly.dxf.color = 4  # CYAN
                                        print(f"  A2 폴리라인 찾음, 색상을 CYAN으로 변경")
                                        
                                        # A2의 점들 중 OLET에서 가장 먼 점 찾기
                                        if poly.dxftype() == 'LWPOLYLINE':
                                            points = list(poly.get_points())
                                        else:
                                            points = [(v.dxf.location.x, v.dxf.location.y) for v in poly.vertices]
                                        
                                        max_dist = 0
                                        far_point = None
                                        for p in points:
                                            px, py = p[0], p[1]
                                            dist = hypot(px - wtype_pos[0], py - wtype_pos[1])
                                            if dist > max_dist:
                                                max_dist = dist
                                                far_point = (px, py)
                                        
                                        if far_point:
                                            # 가장 먼 점에서 x가 포함된 숫자 찾기
                                            for text, x, y, e in all_texts:
                                                if hypot(x - far_point[0], y - far_point[1]) < 25:
                                                    if 'x' in text.lower() and re.search(r'\d+', text):
                                                        # 이 SWNO 내에서 사용된 텍스트인지 확인
                                                        if id(e) not in local_used_texts:
                                                            e.dxf.color = 4  # CYAN
                                                            print(f"  x 포함 텍스트 찾음: {text}")
                                                            
                                                            # x 뒤의 숫자만 추출
                                                            wbore_match = re.search(r'[xX]\s*(\d+)', text)
                                                            if wbore_match:
                                                                wbore = wbore_match.group(1)
                                                                wtype = '  OLET'
                                                                
                                                                weld_data[wno_y] = {
                                                                    'wbore': wbore,
                                                                    'wtype': wtype
                                                                }
                                                                print(f"  ✅ SFW→SW→OLET 방식으로 WBORE: {wbore}, WTYPE: {wtype} 데이터 저장 완료")
                                                                
                                                                # 이 SWNO 내에서만 추적
                                                                local_used_texts.add(id(e))
                                                                # 사용된 SFW 추적에 추가
                                                                global_used_sfw.add(id(sd_entity))
                                                                break
                                    break  # 첫 번째 OLET만 처리
                                
                                if wno_y in weld_data:
                                    continue  # 다음 SWNO로
                                else:
                                    print(f"  ⚠ SFW→SW→OLET 처리 실패")
                            else:
                                print(f"  ⚠ SFW 중심 10mm 내에 SW 원을 찾지 못함")
                        else:
                            # WD가 55 이하인 경우 기존 처리
                            pipe_entity.dxf.color = 4  # CYAN
                            wbore = str(wd)
                            wtype = '  BW' if wd >= 51 else '  SW'
                            
                            weld_data[wno_y] = {
                                'wbore': wbore,
                                'wtype': wtype
                            }
                            print(f"  ✅ SFW(SD) 방식으로 WBORE: {wbore}, WTYPE: {wtype} 데이터 저장 완료")
                            print(f"     레이어명: {pipe_entity.dxf.layer}")
                            
                            # 사용된 SFW 추적에 추가
                            global_used_sfw.add(id(sd_entity))
                            continue  # 다음 SWNO로
                else:
                    print(f"  ⚠ SD 중심 13mm 내에 PIPE_ 레이어를 찾지 못함.")
                    
                    # 새로운 A2 처리 추가
                    print(f"  🔍 SFW 중심에서 A2 폴리라인 검색 시작...")
                    a2_polylines = find_a2_polylines_near_sfw_center(doc, sd_center, 5.0)  # 5mm로 변경
                    
                    if a2_polylines:
                        print(f"  ✅ {len(a2_polylines)}개의 A2 폴리라인 발견")
                        
                        a2_text_found = False
                        for idx, a2_info in enumerate(a2_polylines):
                            a2_entity = a2_info['entity']
                            far_point = a2_info['far_point']
                            
                            print(f"    A2 #{idx+1}: 길이={a2_info['total_length']:.2f}mm")
                            print(f"    가장 먼 점: ({far_point[0]:.2f}, {far_point[1]:.2f})")
                            
                            # A2를 즉시 RED로 변경
                            a2_entity.dxf.color = 1  # RED
                            print(f"    🔴 A2 폴리라인 색상을 RED로 변경")
                            
                            # 가장 먼 끝점에서 30mm 내 'x' 포함 텍스트 찾기 (SW와 동일한 방식으로 변경)
                            for text, x, y, e in all_texts:
                                if hypot(x - far_point[0], y - far_point[1]) <= 30:
                                    # SW와 동일한 조건으로 변경: x가 포함되고 숫자가 있는 텍스트
                                    if 'x' in text.lower() and re.search(r'\d+', text):
                                        # 이 SWNO 내에서 사용된 텍스트인지 확인
                                        if id(e) not in local_used_texts:
                                            # x 뒤의 숫자 추출 (SW와 동일한 패턴)
                                            match = re.search(r'[xX]\s*(\d+)', text)
                                            if match:
                                                wbore = match.group(1)
                                                wtype = '  SW'  # 항상 SW로 설정
                                                
                                                # 데이터 저장
                                                weld_data[wno_y] = {
                                                    'wbore': wbore,
                                                    'wtype': wtype
                                                }
                                                
                                                print(f"    ✅ x 텍스트 발견: {text}")
                                                print(f"    ✅ SFW→A2 방식으로 WBORE: {wbore}, WTYPE: {wtype}")
                                                
                                                # 이 SWNO 내에서만 추적
                                                local_used_texts.add(id(e))
                                                global_used_sfw.add(id(sd_entity))
                                                a2_text_found = True
                                                break
                            
                            if a2_text_found:
                                break
                        
                        if not a2_text_found:
                            print(f"  ⚠ A2 폴리라인은 찾았으나 x 텍스트를 찾지 못함")
                            print(f"  🔄 SFW 대신 SW로 전환하여 처리 시도...")
                            use_sfw = False  # SW 처리로 전환
                    else:
                        print(f"  ⚠ SFW 중심 5mm 내에 조건을 만족하는 A2를 찾지 못함")
                        print(f"  🔄 SFW 대신 SW로 전환하여 처리 시도...")
                        use_sfw = False  # SW 처리로 전환
            
            # 5. SW 처리 (SFW를 사용하지 않는 경우)
            if closest_sw_circle and not use_sfw:
                closest_sw_circle.dxf.color = 1  # RED
                sw_center = (closest_sw_circle.dxf.center.x, closest_sw_circle.dxf.center.y)
                sw_radius = closest_sw_circle.dxf.radius
                print(f"✅ SW 원 찾음 (거리: {min_sw_dist:.2f}mm), 색상을 RED로 변경")
                
                # 사용된 SW 추적에 추가
                global_used_sw.add(id(closest_sw_circle))
                
                # 모든 WNO의 SW 정보 저장 (REDU 처리를 위해)
                all_sw_info[int(wno)] = {
                    'circle': closest_sw_circle,
                    'center': sw_center,
                    'radius': sw_radius,
                    'wno_y': wno_y
                }
                
                # TEE 후처리를 위한 SW 정보 저장
                all_wno_sw_info[wno_y] = {
                    'wno': wno,
                    'circle': closest_sw_circle,
                    'center': sw_center,
                    'radius': sw_radius
                }
                
                # WTYPE 검색을 건너뛰어야 하는 경우
                if skip_wtype_for_this_wno:
                    print(f"  ⏭️ WNO {wno}의 WTYPE 검색을 건너뜁니다 (REDU 후처리에서 처리됨)")
                    continue
                
                # 2. SW 원에 접하는 OLET/WOLET/REDU 레이어 찾기
                touching_entities = find_entities_touching_circle(doc, closest_sw_circle, ['OLET', 'WOLET', 'REDU'])
                
                # 사용되지 않은 엔티티만 필터링
                available_entities = []
                for entity in touching_entities:
                    if id(entity) not in global_used_wtype:
                        available_entities.append(entity)
                
                for wtype_entity in available_entities:
                    wtype_entity.dxf.color = 4  # CYAN
                    wtype_found = wtype_entity.dxf.layer.upper()
                    wtype_pos = get_entity_position(wtype_entity)
                    print(f"✅ WTYPE 찾음: {wtype_found}, 색상을 CYAN으로 변경")
                    
                    # 사용된 WTYPE 추적에 추가
                    global_used_wtype.add(id(wtype_entity))
                    
                    # REDU인 경우 특별 처리
                    if wtype_found == 'REDU':
                        print(f"\n  ⚡ REDU 특별 처리 시작!")
                        print(f"  🔴 REDU 발견! WNO: {wno}")
                        
                        # 다음 WNO는 WTYPE 검색을 건너뛰도록 설정
                        skip_wtype_search = int(wno) + 1
                        print(f"  ⏭️ 다음 WNO {skip_wtype_search}는 WTYPE 검색을 건너뛸 예정")
                        
                        # REDU의 선분들 구하기
                        segments = get_segment_lengths(wtype_entity)
                        print(f"  📏 REDU 선분 개수: {len(segments)}")
                        for i, seg in enumerate(segments):
                            print(f"     선분 {i+1}: 길이 = {seg['length']:.2f}mm")
                        
                        # SW가 접하는 선분 찾기 (모든 접촉 선분의 정보 저장)
                        total_length, touching_segs = get_total_contact_length(sw_center, sw_radius, segments)
                        
                        if total_length > 0:
                            print(f"  🎯 SW 원이 접하는 선분 {len(touching_segs)}개, 총 길이 = {total_length:.2f}mm")
                            
                            # REDU 정보 저장 - 각 REDU마다 고유한 ID 사용
                            redu_key = f"{id(wtype_entity)}_{int(wno)}"  # REDU 엔티티 ID와 WNO 조합
                            print(f"  💾 REDU 엔티티 등록 (키: {redu_key})")
                            redu_sw_data[redu_key] = {
                                'entity': wtype_entity,
                                'segments': segments,
                                'sw_circles': [],
                                'rsize_text': None,
                                'first_wno': int(wno)  # 이 REDU의 첫 번째 WNO
                            }
                            
                            redu_sw_data[redu_key]['sw_circles'].append({
                                'circle': closest_sw_circle,
                                'center': sw_center,
                                'touching_segments': touching_segs,
                                'total_length': total_length,
                                'wno': wno,
                                'wno_y': wno_y,
                                'idx': idx
                            })
                            print(f"  ➕ SW 원 정보 추가 - WNO: {wno}, 접촉 총 길이: {total_length:.2f}mm")
                        else:
                            print(f"  ❌ SW 원이 접하는 선분을 찾지 못함")
                    
                    # 3. WTYPE의 선분에 접하는 2-3점 폴리라인 찾기 (PIPE 레이어 제외)
                    a2_polylines = find_polylines_touching_entity(doc, wtype_entity, exclude_layers=['PIPE'])
                    
                    for poly in a2_polylines:
                        poly.dxf.color = 4  # CYAN
                        print(f"  A2 폴리라인 찾음, 색상을 CYAN으로 변경")
                        
                        # 4. A2의 점들 중 WTYPE에서 가장 먼 점 찾기
                        if poly.dxftype() == 'LWPOLYLINE':
                            points = list(poly.get_points())
                        else:
                            points = [(v.dxf.location.x, v.dxf.location.y) for v in poly.vertices]
                        
                        max_dist = 0
                        far_point = None
                        for p in points:
                            px, py = p[0], p[1]
                            dist = hypot(px - wtype_pos[0], py - wtype_pos[1])
                            if dist > max_dist:
                                max_dist = dist
                                far_point = (px, py)
                        
                        if far_point:
                            # 5. 가장 먼 점에서 x가 포함된 숫자 찾기 (25mm 이내로 변경)
                            for text, x, y, e in all_texts:
                                if hypot(x - far_point[0], y - far_point[1]) < 25:  # 25mm 내
                                    if 'x' in text.lower() and re.search(r'\d+', text):
                                        # 이 SWNO 내에서 사용된 텍스트인지 확인
                                        if id(e) not in local_used_texts:
                                            e.dxf.color = 4  # CYAN
                                            print(f"  x 포함 텍스트 찾음: {text}, 색상을 CYAN으로 변경")
                                            
                                            # REDU인 경우 RSIZE 텍스트 저장
                                            if wtype_found == 'REDU':
                                                # 현재 REDU의 키 찾기
                                                for redu_key, redu_info in redu_sw_data.items():
                                                    if redu_info['entity'] == wtype_entity and redu_info['first_wno'] == int(wno):
                                                        redu_sw_data[redu_key]['rsize_text'] = text
                                                        print(f"  📝 REDU RSIZE 텍스트 저장: {text}")
                                                        break
                                            
                                            # x 뒤의 숫자만 추출 (기본 WBORE)
                                            wbore_match = re.search(r'[xX]\s*(\d+)', text)
                                            if wbore_match:
                                                wbore = wbore_match.group(1)
                                                
                                                # REDU가 아닌 경우 바로 저장
                                                if wtype_found != 'REDU':
                                                    # OLET/WOLET의 경우 WTYPE 설정
                                                    if wtype_found == 'OLET':
                                                        final_wtype = '  OLET'
                                                    elif wtype_found == 'WOLET':
                                                        final_wtype = '  WOLET'
                                                    else:
                                                        final_wtype = wtype_found
                                                    
                                                    weld_data[wno_y] = {
                                                        'wbore': wbore,
                                                        'wtype': final_wtype
                                                    }
                                                    print(f"✅ WBORE: {wbore}, WTYPE: {final_wtype} 데이터 저장 완료")
                                                    
                                                    # 이 SWNO 내에서만 추적
                                                    local_used_texts.add(id(e))
                                                break
                    break  # 첫 번째 WTYPE만 처리
                
                # WTYPE을 찾지 못한 경우 - 추가 처리 시작
                if not available_entities:
                    print(f"  ℹ️ OLET/WOLET/REDU를 찾지 못함.")
                    
                    # 새로운 추가: SW 중심에서 3mm 내 PIPE_ 레이어 찾기
                    print(f"  🔍 SW 중심에서 3mm 내 PIPE_ 레이어 검색 시작...")
                    pipe_entities = find_pipe_entities_near_center(doc, sw_center, 3.0)
                    
                    if pipe_entities:
                        # 첫 번째 PIPE_ 엔티티 처리
                        pipe_entity = pipe_entities[0]
                        pipe_entity.dxf.color = 4  # CYAN
                        
                        # WD 추출
                        wd = extract_wd_from_pipe_layer(pipe_entity.dxf.layer)
                        if wd is not None:
                            wbore = str(wd)
                            wtype = '  BW' if wd >= 51 else '  SW'
                            
                            weld_data[wno_y] = {
                                'wbore': wbore,
                                'wtype': wtype
                            }
                            print(f"  ✅ PIPE_ 방식으로 WBORE: {wbore}, WTYPE: {wtype} 데이터 저장 완료")
                            print(f"     레이어명: {pipe_entity.dxf.layer}")
                            continue  # 다음 WNO로 진행
                    else:
                        print(f"  ℹ️ SW 중심 3mm 내에 PIPE_ 레이어를 찾지 못함.")
                    
                    # 기존 NG2 처리
                    print(f"  ℹ️ NG2 검색 시작...")
                    print(f"     조건: SW 원 중심 2mm 이내 또는 원 둘레 1mm 이내")
                    
                    # NG2 찾기: SW 원 중심에서 2mm 이내 또는 원 둘레에서 1mm 이내인 2-3점 폴리라인 (PIPE 레이어 제외, 길이 합 10mm 초과)
                    ng2_list = []  # NG2 정보를 저장할 리스트
                    
                    for e in msp:
                        if e.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
                            # PIPE 레이어는 제외
                            if hasattr(e.dxf, 'layer') and e.dxf.layer.upper() == 'PIPE':
                                continue
                            
                            # 곡선(bulge)이 있는 폴리라인은 제외
                            if has_bulge(e):
                                continue
                            
                            # 폴리라인의 점들
                            if e.dxftype() == 'LWPOLYLINE':
                                poly_points = list(e.get_points())
                            else:
                                poly_points = [(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]
                            
                            # 2-3점인 경우만
                            if 2 <= len(poly_points) <= 3:
                                # 폴리라인의 중심점 계산
                                center_x = sum(p[0] for p in poly_points) / len(poly_points)
                                center_y = sum(p[1] for p in poly_points) / len(poly_points)
                                
                                # 중심점이 SW 원 중심에서 2mm 이내인지 확인
                                center_to_sw = hypot(center_x - sw_center[0], center_y - sw_center[1])
                                
                                # SW 원에 접하는지 확인 (점만 검사)
                                touching = False
                                min_dist_to_circle = float('inf')
                                
                                # 0. 중심점이 SW 중심에서 2mm 이내면 선택
                                if center_to_sw <= 2:
                                    touching = True
                                    min_dist_to_circle = center_to_sw
                                    print(f"  NG2 중심점이 SW 중심에서 {center_to_sw:.2f}mm")
                                
                                # 1. 점 검사 - SW 원 둘레에서 1mm 이내
                                for p in poly_points:
                                    px, py = p[0], p[1]
                                    dist = hypot(px - sw_center[0], py - sw_center[1])
                                    dist_to_circle = abs(dist - sw_radius)
                                    min_dist_to_circle = min(min_dist_to_circle, dist_to_circle)
                                    if dist_to_circle <= 1:  # 1 mm 공차
                                        touching = True
                                
                                if touching:
                                    # 길이 합 계산
                                    length_sum = 0
                                    segments = []
                                    for i in range(len(poly_points) - 1):
                                        p1 = (poly_points[i][0], poly_points[i][1])
                                        p2 = (poly_points[i+1][0], poly_points[i+1][1])
                                        length = hypot(p2[0] - p1[0], p2[1] - p1[1])
                                        length_sum += length
                                        segments.append(length)
                                    
                                    # 길이 합이 10mm 초과인 경우만
                                    if length_sum > 10:
                                        # SW에서 가장 먼 점 찾기
                                        max_dist_from_sw = 0
                                        far_point = None
                                        for p in poly_points:
                                            px, py = p[0], p[1]
                                            dist = hypot(px - sw_center[0], py - sw_center[1])
                                            if dist > max_dist_from_sw:
                                                max_dist_from_sw = dist
                                                far_point = (px, py)
                                        
                                        ng2_info = {
                                            'entity': e,
                                            'points': [(p[0], p[1]) for p in poly_points],
                                            'length_sum': length_sum,
                                            'far_point': far_point,
                                            'max_dist': max_dist_from_sw,
                                            'min_dist_to_circle': min_dist_to_circle
                                        }
                                        ng2_list.append(ng2_info)
                                        e.dxf.color = 4  # CYAN
                                        print(f"  ✅ NG2 #{len(ng2_list)} 찾음: {len(poly_points)}점 폴리라인")
                                        print(f"     - 길이 합: {length_sum:.2f}mm")
                                        print(f"     - SW 원과의 최소 거리: {min_dist_to_circle:.2f}mm")
                                        print(f"     - SW 중심에서 NG2 중심까지: {center_to_sw:.2f}mm")
                                        print(f"     - SW에서 가장 먼 점 거리: {max_dist_from_sw:.2f}mm")
                    
                    # 모든 NG2 처리 (선택 기준 없이 모두 처리)
                    if ng2_list:
                        text_found = False
                        
                        for idx, ng2_info in enumerate(ng2_list):
                            print(f"\n  🔍 NG2 #{idx+1} 처리 중...")
                            
                            # NG2의 먼 점에서 25mm 내에서 x 텍스트 찾기
                            for text, x, y, e in all_texts:
                                if hypot(x - ng2_info['far_point'][0], y - ng2_info['far_point'][1]) < 25:
                                    if 'x' in text.lower() and re.search(r'\d+', text):
                                        # 이 SWNO 내에서 사용된 텍스트인지 확인
                                        if id(e) not in local_used_texts:
                                            e.dxf.color = 4  # CYAN
                                            print(f"    ✅ NG 관련 x 텍스트 찾음: {text}")
                                            
                                            # x 뒤의 숫자만 추출
                                            wbore_match = re.search(r'[xX]\s*(\d+)', text)
                                            if wbore_match:
                                                wbore = wbore_match.group(1)
                                                wtype = '  SW' if int(wbore) < 51 else '  BW'
                                                
                                                # 첫 번째 유효한 텍스트만 데이터로 저장
                                                if not text_found:
                                                    weld_data[wno_y] = {
                                                        'wbore': wbore,
                                                        'wtype': wtype
                                                    }
                                                    print(f"    ✅ NG 방식으로 WBORE: {wbore}, WTYPE: {wtype} 데이터 저장 완료")
                                                    text_found = True
                                                    
                                                    # 이 SWNO 내에서만 추적
                                                    local_used_texts.add(id(e))
                                                else:
                                                    print(f"    ℹ️ 추가 텍스트 발견 (저장 안함): WBORE: {wbore}")
                                                break
                            
                            if not text_found and idx == len(ng2_list) - 1:
                                print(f"  ⚠ 모든 NG2에서 x 텍스트를 찾지 못했습니다.")
                        
                        if text_found:
                            print(f"\n  📊 NG2 처리 완료: 총 {len(ng2_list)}개의 NG2 발견")
                    else:
                        print(f"  ⚠ 조건을 만족하는 NG2를 찾지 못했습니다.")
                        print(f"     (SW 중심 2mm 이내 또는 원 둘레 1mm 이내, 길이 10mm 초과)")
                
            else:
                print(f"  ⚠ SW 레이어 원을 30mm 내에서 찾지 못했습니다.")
    
    # REDU 후처리: 연속된 두 WNO의 SW가 접하는 선분 비교
    print(f"\n🔧 REDU 후처리 시작...")
    print(f"   총 REDU 그룹 수: {len(redu_sw_data)}")
    
    for redu_key, redu_info in redu_sw_data.items():
        print(f"\n   📌 REDU 그룹 처리 중 (키: {redu_key})...")
        print(f"      SW 원 개수: {len(redu_info['sw_circles'])}")
        print(f"      RSIZE 텍스트: {redu_info['rsize_text']}")
        print(f"      이 REDU의 첫 WNO: {redu_info['first_wno']}")
        
        # 이 REDU의 첫 번째 WNO와 다음 WNO의 SW 찾기
        first_wno = redu_info['first_wno']
        
        # all_sw_info에서 첫 번째와 두 번째 SW 정보 가져오기
        first_sw = all_sw_info.get(first_wno)
        second_sw = all_sw_info.get(first_wno + 1)
        
        if first_sw and second_sw and redu_info['rsize_text']:
            print(f"      첫 번째 SW (WNO {first_wno}) 찾음")
            print(f"      두 번째 SW (WNO {first_wno + 1}) 찾음")
            
            # 각 SW가 REDU의 어느 선분들에 접하는지 확인 (모든 접촉 선분의 길이 합)
            first_total_length, first_touching_segs = get_total_contact_length(
                first_sw['center'], 
                first_sw['radius'], 
                redu_info['segments']
            )
            second_total_length, second_touching_segs = get_total_contact_length(
                second_sw['center'], 
                second_sw['radius'], 
                redu_info['segments']
            )
            
            if first_total_length > 0 and second_total_length > 0:
                print(f"      첫 번째 SW: 접촉 선분 {len(first_touching_segs)}개, 총 길이 = {first_total_length:.2f}mm")
                for seg in first_touching_segs:
                    print(f"         - 선분 {seg['segment']['index']+1}: {seg['contact_length']:.2f}mm")
                    
                print(f"      두 번째 SW: 접촉 선분 {len(second_touching_segs)}개, 총 길이 = {second_total_length:.2f}mm")
                for seg in second_touching_segs:
                    print(f"         - 선분 {seg['segment']['index']+1}: {seg['contact_length']:.2f}mm")
                
                # RSIZE에서 x 앞뒤 숫자 추출
                rsize_match = re.search(r'(\d+)\s*[xX]\s*(\d+)', redu_info['rsize_text'])
                if rsize_match:
                    bore_before_x = rsize_match.group(1)  # x 앞의 숫자
                    bore_after_x = rsize_match.group(2)   # x 뒤의 숫자
                    print(f"      RSIZE 파싱: {bore_before_x} x {bore_after_x}")
                    
                    # 첫 번째와 두 번째 SW의 접촉 선분 총 길이 비교
                    if first_total_length > second_total_length:
                        # 첫 번째가 긴 선분
                        first_wbore = bore_before_x
                        second_wbore = bore_after_x
                        print(f"      🟢 WNO {first_wno}: 긴 선분 (총 {first_total_length:.2f}mm) → WBORE = {first_wbore}")
                        print(f"      🔵 WNO {first_wno + 1}: 짧은 선분 (총 {second_total_length:.2f}mm) → WBORE = {second_wbore}")
                    else:
                        # 두 번째가 긴 선분
                        first_wbore = bore_after_x
                        second_wbore = bore_before_x
                        print(f"      🔵 WNO {first_wno}: 짧은 선분 (총 {first_total_length:.2f}mm) → WBORE = {first_wbore}")
                        print(f"      🟢 WNO {first_wno + 1}: 긴 선분 (총 {second_total_length:.2f}mm) → WBORE = {second_wbore}")
                    
                    # 첫 번째 SW 데이터 저장
                    first_wtype = '  BW' if int(first_wbore) >= 51 else '  SW'
                    weld_data[first_sw['wno_y']] = {
                        'wbore': first_wbore,
                        'wtype': first_wtype
                    }
                    print(f"      ✅ WNO {first_wno} 처리 완료 - WBORE: {first_wbore}, WTYPE: {first_wtype}")
                    
                    # 두 번째 SW 데이터 저장
                    second_wtype = '  BW' if int(second_wbore) >= 51 else '  SW'
                    weld_data[second_sw['wno_y']] = {
                        'wbore': second_wbore,
                        'wtype': second_wtype
                    }
                    print(f"      ✅ WNO {first_wno + 1} 처리 완료 - WBORE: {second_wbore}, WTYPE: {second_wtype}")
                else:
                    print(f"      ❌ RSIZE 텍스트 파싱 실패: {redu_info['rsize_text']}")
            else:
                print(f"      ⚠️ SW가 REDU 선분에 접하지 않음")
                if first_total_length == 0:
                    print(f"         - 첫 번째 SW가 REDU에 접하지 않음")
                if second_total_length == 0:
                    print(f"         - 두 번째 SW가 REDU에 접하지 않음")
        else:
            print(f"      ⚠️ 필요한 정보를 찾지 못함")
            if not first_sw:
                print(f"         - 첫 번째 SW (WNO {first_wno}) 없음")
            if not second_sw:
                print(f"         - 두 번째 SW (WNO {first_wno + 1}) 없음")
            if not redu_info['rsize_text']:
                print(f"         - RSIZE 텍스트 없음")
    
    print(f"\n✅ REDU 후처리 완료!")
    
    # TEE_ 후처리: 모든 처리가 끝난 후 TEE_ 레이어 확인
    print(f"\n🔧 TEE_ 후처리 시작...")
    print(f"   처리 전 weld_data 상태:")
    for y_key, data in weld_data.items():
        print(f"   Y={y_key:.2f}: WBORE={data.get('wbore', 'N/A')}, WTYPE={data.get('wtype', 'N/A')}")
    
    for wno_y, sw_info in all_wno_sw_info.items():
        wno = sw_info['wno']
        sw_circle = sw_info['circle']
        sw_center = sw_info['center']
        sw_radius = sw_info['radius']
        
        print(f"\n   WNO {wno} 처리 중 (Y={wno_y:.2f})...")
        
        # SW 원에 접하는 TEE_ 레이어 찾기 (모든 점 검사)
        tee_entities = find_tee_entities_touching_circle(doc, sw_circle)
        
        for tee_entity in tee_entities:
            layer_name = tee_entity.dxf.layer.upper()
            if layer_name.startswith('TEE_'):
                td = extract_td_from_tee_layer(layer_name)
                if td is not None:
                    wbore = str(td)
                    wtype = '  BW' if td >= 51 else '  SW'
                    
                    # 기존 데이터를 덮어쓰기
                    weld_data[wno_y] = {
                        'wbore': wbore,
                        'wtype': wtype
                    }
                    
                    tee_entity.dxf.color = 4  # CYAN
                    print(f"✅ TEE_ 후처리 - WNO {wno}: WBORE={wbore}, WTYPE={wtype}")
                    print(f"   레이어명: {layer_name}")
                    print(f"   Y 좌표: {wno_y:.2f}")
                    print(f"   기존 데이터를 TEE_ 데이터로 덮어씀")
                    break  # 첫 번째 TEE_만 처리
    
    print(f"\n✅ TEE_ 후처리 완료!")
    print(f"   처리 후 weld_data 상태:")
    for y_key, data in weld_data.items():
        print(f"   Y={y_key:.2f}: WBORE={data.get('wbore', 'N/A')}, WTYPE={data.get('wtype', 'N/A')}")
    
    return weld_data

def modify_fld_column(doc, all_texts, headers):
    if 'NO' not in headers or '/FLD' not in headers:
        return
    msp = doc.modelspace()
    no_x, no_y = headers['NO']
    fld_x, fld_y = headers['/FLD']
    y_positions = sorted(
        set(t[2] for t in all_texts if abs(t[1] - no_x) < 1 and t[2] < no_y and t[0].strip()),
        reverse=True
    )
    for y in y_positions:
        fld_texts = [t for t in all_texts if abs(t[1] - fld_x) < 1 and abs(t[2] - y) < 0.5]
        for text, x, y2, e in fld_texts:
            val = text.strip().upper()
            if val in ['F', 'S']:
                new_val = val + 'W'
                try:
                    msp.delete_entity(e)
                    msp.add_text(new_val, dxfattribs={'height': 2.5, 'insert': (x + 5, y2)})
                except:
                    continue

def modify_table_with_weld_data(doc, all_texts, bore_value, headers, dn_x, weld_data):
    """테이블 수정 - WBORE/WTYPE이 있으면 그것을 사용, 없으면 기본값 사용"""
    if 'NO' not in headers or dn_x is None:
        return
    msp = doc.modelspace()
    no_x, no_y = headers['NO']
    type_x = headers.get('TYPE', (None, None))[0]
    header_y = no_y

    y_positions = sorted(
        set(t[2] for t in all_texts if abs(t[1] - no_x) < 1 and t[2] < header_y and t[0].strip()),
        reverse=True
    )

    for y in y_positions:
        # 기존 DN 텍스트 삭제
        existing = [t for t in all_texts if abs(t[1] - dn_x) < 1 and abs(t[2] - y) < 0.5]
        for t in existing:
            try:
                msp.delete_entity(t[3])
            except:
                continue
        
        # WBORE가 있으면 WBORE 사용, 없으면 기본 BORE 값 사용
        if y in weld_data and 'wbore' in weld_data[y]:
            output_bore = weld_data[y]['wbore']
            color = 4  # CYAN for weld data
            print(f"  📊 테이블 수정 - Y={y:.2f}, WBORE={output_bore} 출력")
        else:
            output_bore = str(bore_value)
            color = 2  # 기본 색상
            print(f"  📊 테이블 수정 - Y={y:.2f}, 기본값={output_bore} 출력")
        
        # BORE 값 출력
        msp.add_text(output_bore, dxfattribs={
            'height': 2.5, 
            'insert': (dn_x + 5, y),
            'color': color
        })

        # TYPE 처리
        if type_x is not None:
            # 기존 TYPE 텍스트 삭제
            type_texts = [t for t in all_texts if abs(t[1] - type_x) < 1 and abs(t[2] - y) < 0.5]
            for t in type_texts:
                try:
                    msp.delete_entity(t[3])
                except:
                    continue
            
            # WTYPE이 있으면 WTYPE 사용, 없으면 기본 BW/SW 사용
            if y in weld_data and 'wtype' in weld_data[y]:
                type_str = weld_data[y]['wtype']
                color = 4  # CYAN for weld data
            else:
                # WBORE가 있으면 그 값으로 판단, 없으면 기본 bore_value로 판단
                check_bore = int(weld_data[y]['wbore']) if y in weld_data and 'wbore' in weld_data[y] else bore_value
                type_str = "  BW" if check_bore >= 65 else "  SW"
                color = 2  # 기본 색상
            
            # TYPE 값 출력
            msp.add_text(type_str, dxfattribs={
                'height': 2.5, 
                'insert': (type_x + 3, y),
                'color': color
            })

def get_table_bounds(headers, dn_x, all_texts):
    xs = [headers[k][0] for k in headers] + ([dn_x] if dn_x else [])
    min_x = min(xs) - 20
    max_x = max(xs) + 20
    no_x, no_y = headers['NO']
    # 정규식 대신 isdigit() 사용
    ys = [t[2] for t in all_texts if abs(t[1] - no_x) < 1 and t[2] < no_y and t[0].strip().isdigit()]
    min_y = min(ys) - 10 if ys else no_y - 100
    max_y = no_y + 15
    return min_x, max_x, min_y, max_y

def stretch_entities(doc, bounds):
    min_x, max_x, min_y, max_y = bounds
    msp = doc.modelspace()
    for e in list(msp):
        if not hasattr(e, "dxf"):
            continue
        try:
            if e.dxftype() in ['TEXT', 'MTEXT']:
                p = e.dxf.insert
                if min_x <= p.x <= max_x and min_y <= p.y <= max_y:
                    e.dxf.insert = (p.x + 25, p.y)
            elif e.dxftype() == 'LWPOLYLINE':
                new_points = []
                for x, y, *rest in e.get_points():
                    if min_x <= x <= max_x and min_y <= y <= max_y:
                        x += 25
                    new_points.append((x, y, *rest))
                e.set_points(new_points)
            elif e.dxftype() == 'POLYLINE':
                for v in e.vertices:
                    loc = v.dxf.location
                    if min_x <= loc.x <= max_x and min_y <= loc.y <= max_y:
                        v.dxf.location = (loc.x + 25, loc.y)
            elif e.dxftype() == 'LINE':
                start = e.dxf.start
                end = e.dxf.end
                if min_x <= start.x <= max_x and min_y <= start.y <= max_y:
                    start = (start.x + 25, start.y)
                if min_x <= end.x <= max_x and min_y <= end.y <= max_y:
                    end = (end.x + 25, end.y)
                e.dxf.start = start
                e.dxf.end = end
        except Exception as err:
            print(f"⚠ {e.dxftype()} stretch 오류: {err}")
            continue

def apply_final_formatting(doc):
    """최종 포맷팅 적용 - 텍스트 스타일과 색상 변경"""
    msp = doc.modelspace()
    
    # 모든 텍스트에 대해 스타일과 색상 적용
    for txt in msp.query('TEXT'):
        if txt.dxf.color != 4:  # CYAN이 아닌 경우만
            txt.dxf.color = 2
        txt.dxf.style = "ARIAL"
        txt.dxf.width = 0.86

    # ARIAL 스타일이 없으면 추가
    if "ARIAL" not in doc.styles:
        doc.styles.new("ARIAL", dxfattribs={"font": "arial.ttf"})

def process_dxf_file(filepath):
    print(f"\n📂 Processing: {os.path.basename(filepath)}")
    doc = ezdxf.readfile(filepath)
    all_texts = get_texts_by_position(extract_text_entities(doc))

    # 처리 완료 플래그
    processing_completed = False
    
    # FABRICATION/ERECTION MATERIALS 찾기
    materials_x = None
    for text, x, y, _ in all_texts:
        if "FABRICATION MATERIAL" in text.upper():
            materials_x = x
            break
    
    # FABRICATION MATERIALS가 없으면 ERECTION MATERIALS 찾기
    if materials_x is None:
        for text, x, y, _ in all_texts:
            if "ERECTION MATERIAL" in text.upper():
                materials_x = x
                break

    # SIZE 값 찾기 (수정된 함수 사용)
    size_text_value = find_size_value_near_materials(all_texts)
    if not size_text_value:
        print("⚠ SIZE 값을 찾을 수 없습니다. 기본 처리를 진행합니다.")
        bore_value = 100  # 기본값
    else:
        bore_value = extract_bore_from_size(size_text_value)
        print(f"✅ BORE 값 추출됨: {bore_value}")
        processing_completed = True

    dn_x = find_dn_header_x(all_texts)
    if dn_x is None:
        print("⚠ 'NO', '/FLD', 'DN' 연속 헤더를 찾을 수 없습니다.")
    else:
        processing_completed = True

    headers = find_header_positions(all_texts)
    
    # 용접 데이터 수집 (출력하지 않고 데이터만 수집)
    weld_data = {}
    if materials_x and headers:
        weld_data = process_weld_data(doc, all_texts, headers, dn_x, materials_x, bore_value)
        if weld_data:
            processing_completed = True
    
    # 테이블 수정 - 수집된 용접 데이터를 기반으로 BORE/TYPE 출력
    if headers and dn_x:
        modify_table_with_weld_data(doc, all_texts, bore_value, headers, dn_x, weld_data)
        processing_completed = True
    
    # FLD 컬럼 수정
    if headers:
        modify_fld_column(doc, all_texts, headers)
        processing_completed = True
    
    # 테이블 영역 확장
    if headers and dn_x:
        bounds = get_table_bounds(headers, dn_x, all_texts)
        stretch_entities(doc, bounds)
        processing_completed = True

    # 최종 포맷팅 적용 (항상 실행)
    apply_final_formatting(doc)

    # 저장 (항상 실행)
    new_filename = os.path.splitext(filepath)[0] + "_wt.dxf"
    doc.saveas(new_filename)
    
    if processing_completed:
        print(f"💾 처리 완료 및 저장: {os.path.basename(new_filename)}")
    else:
        print(f"💾 작업 없이 저장 완료: {os.path.basename(new_filename)}")

def main():
    dxf_files = get_selected_dxf_files()
    if not dxf_files:
        print("❌ DXF 파일이 선택되지 않았습니다.")
        return
    
    print(f"📋 총 {len(dxf_files)}개 파일 처리를 시작합니다.")
    
    for i, dxf in enumerate(dxf_files, 1):
        try:
            print(f"\n[{i}/{len(dxf_files)}] 파일 처리 중...")
            process_dxf_file(dxf)
        except Exception as e:
            print(f"❌ 오류 발생: {os.path.basename(dxf)} / {e}")
            # 오류가 발생해도 최소한 원본 파일을 복사해서 저장
            try:
                time.sleep(0.5)  # 잠시 대기
                new_filename = os.path.splitext(dxf)[0] + "_wt.dxf"  # _WT → _wt로 변경
                shutil.copy2(dxf, new_filename)
                print(f"📄 원본 파일 복사 저장: {os.path.basename(new_filename)}")
            except Exception as copy_error:
                print(f"❌ 파일 복사도 실패: {copy_error}")
    
    print(f"\n🎉 모든 파일 처리 완료!")

if __name__ == "__main__":
    main()