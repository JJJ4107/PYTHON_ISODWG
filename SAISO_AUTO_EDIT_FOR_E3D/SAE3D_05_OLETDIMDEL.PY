"""
OLET 처리 프로그램
- OLET 주변의 불필요한 엔티티들을 찾아 삭제
- DEL1~DEL11, AD1~AD10 엔티티를 삭제
- OLET은 CYAN 색상 유지, PIPE를 포함하는 레이어는 원래 상태 유지
"""

import ezdxf
import os
import math
from ezdxf.math import Vec2
from tkinter import Tk, filedialog

def select_dxf_files():
    """DXF 파일 선택 대화상자"""
    root = Tk()
    root.withdraw()
    file_paths = filedialog.askopenfilenames(
        title="DXF 파일 선택",
        filetypes=[("DXF Files", "*.dxf")]
    )
    root.destroy()
    return file_paths

def extract_points(entity):
    """폴리라인에서 점 추출"""
    if entity.dxftype() == 'LWPOLYLINE':
        return [Vec2(x, y) for x, y, *_ in entity.get_points()]
    elif entity.dxftype() == 'POLYLINE':
        try:
            # POLYLINE vertices 접근 방식
            points = []
            for vertex in entity.vertices:
                if hasattr(vertex, 'dxf'):
                    location = vertex.dxf.location
                    points.append(Vec2(location.x, location.y))
                else:
                    # 다른 방식으로 시도
                    points.append(Vec2(vertex.location[0], vertex.location[1]))
            return points
        except:
            try:
                # 대체 방식
                return [Vec2(v.dxf.location.x, v.dxf.location.y) for v in entity]
            except:
                return []
    return []

def distance(p1, p2):
    """두 점 사이의 거리"""
    return math.hypot(p2.x - p1.x, p2.y - p1.y)

def get_entity_layer(entity):
    """엔티티의 레이어 이름을 안전하게 가져오기"""
    try:
        if hasattr(entity, 'dxf') and hasattr(entity.dxf, 'layer'):
            return entity.dxf.layer
        elif hasattr(entity, 'get_dxf_attrib'):
            return entity.get_dxf_attrib('layer', default='')
        else:
            return ''
    except:
        return ''

def get_entity_color(entity):
    """엔티티의 색상을 안전하게 가져오기"""
    try:
        if hasattr(entity, 'dxf') and hasattr(entity.dxf, 'color'):
            return entity.dxf.color
        elif hasattr(entity, 'get_dxf_attrib'):
            return entity.get_dxf_attrib('color', default=7)
        else:
            return 7
    except:
        return 7

def set_entity_color(entity, color):
    """엔티티의 색상을 안전하게 설정하기"""
    try:
        if hasattr(entity, 'dxf'):
            entity.dxf.color = color
        elif hasattr(entity, 'set_dxf_attrib'):
            entity.set_dxf_attrib('color', color)
    except:
        pass

def get_entity_handle(entity):
    """엔티티의 핸들을 안전하게 가져오기"""
    try:
        if hasattr(entity, 'dxf') and hasattr(entity.dxf, 'handle'):
            return entity.dxf.handle
        elif hasattr(entity, 'get_dxf_attrib'):
            return entity.get_dxf_attrib('handle', default='')
        elif hasattr(entity, 'handle'):
            return entity.handle
        else:
            return 'UNKNOWN'
    except:
        return 'UNKNOWN'

def get_polyline_length(points):
    """폴리라인의 총 길이 계산"""
    if len(points) < 2:
        return 0
    total_length = 0
    for i in range(len(points) - 1):
        total_length += distance(points[i], points[i+1])
    return total_length

def get_angle(p1, p2):
    """두 점 사이의 각도 (도 단위)"""
    return math.degrees(math.atan2(p2.y - p1.y, p2.x - p1.x))

def are_parallel(angle1, angle2, tolerance=5):
    """두 각도가 평행한지 확인 (허용 오차 내)
    
    시작점과 끝점이 반대인 경우(180도 차이)도 평행으로 인식
    예: 45도와 225도는 같은 선이지만 방향이 반대 -> 평행으로 처리
    """
    diff = abs(angle1 - angle2) % 180
    return diff <= tolerance or diff >= (180 - tolerance)

def find_nearest_polyline(ref_points, polylines, max_dist):
    """참조 폴리라인에서 가장 가까운 폴리라인 찾기"""
    min_dist = float('inf')
    nearest = None
    
    for pl in polylines:
        pl_points = extract_points(pl)
        if not pl_points:
            continue
            
        # 두 폴리라인 간 최소 거리 계산
        for ref_pt in ref_points:
            for pl_pt in pl_points:
                d = distance(ref_pt, pl_pt)
                if d < min_dist and d <= max_dist:
                    min_dist = d
                    nearest = pl
    
    return nearest, min_dist

def point_to_line_distance(point, line_start, line_end):
    """점에서 선분까지의 수직 거리 계산"""
    line_vec = line_end - line_start
    point_vec = point - line_start
    line_len = distance(line_start, line_end)
    
    if line_len < 0.001:  # 선분이 점인 경우
        return distance(point, line_start)
    
    # 점을 선분에 투영
    t = max(0, min(1, (point_vec.x * line_vec.x + point_vec.y * line_vec.y) / (line_len * line_len)))
    projection = line_start + line_vec * t
    
    return distance(point, projection)

def polyline_to_polyline_min_distance(points1, points2):
    """두 폴리라인 간의 최소 수직 거리 계산"""
    min_dist = float('inf')
    
    # points1의 각 점에서 points2의 각 선분까지의 거리
    for pt1 in points1:
        for i in range(len(points2) - 1):
            dist = point_to_line_distance(pt1, points2[i], points2[i+1])
            min_dist = min(min_dist, dist)
    
    # points2의 각 점에서 points1의 각 선분까지의 거리
    for pt2 in points2:
        for i in range(len(points1) - 1):
            dist = point_to_line_distance(pt2, points1[i], points1[i+1])
            min_dist = min(min_dist, dist)
    
    return min_dist

def is_entity_touching_olet(entity, dolet_points, tolerance=2.2):
    """엔티티가 OLET과 접하는지 확인 (DEL6용 2.2mm 범위)"""
    if entity.dxftype() == 'LINE':
        start = Vec2(entity.dxf.start.x, entity.dxf.start.y)
        end = Vec2(entity.dxf.end.x, entity.dxf.end.y)
        points = [start, end]
    else:
        points = extract_points(entity)
    
    if not points:
        return False
    
    # 엔티티의 각 점이 OLET의 점과 접하는지 확인
    for entity_pt in points:
        for dolet_pt in dolet_points:
            if distance(entity_pt, dolet_pt) <= tolerance:
                return True
    
    # 엔티티의 각 선분이 OLET의 선분과 접하는지 확인
    for i in range(len(points) - 1):
        for j in range(len(dolet_points) - 1):
            # 두 선분 간의 최소 거리가 tolerance 이하면 접촉
            dist = point_to_line_distance(points[i], dolet_points[j], dolet_points[j+1])
            if dist <= tolerance:
                return True
            dist = point_to_line_distance(dolet_points[j], points[i], points[i+1])
            if dist <= tolerance:
                return True
                
    return False

def line_passes_through_polyline(line_start, line_end, polyline_points):
    """라인이 폴리라인을 통과하는지 확인"""
    def ccw(A, B, C):
        return (C.y - A.y) * (B.x - A.x) > (B.y - A.y) * (C.x - A.x)
    
    def segments_intersect(A, B, C, D):
        return ccw(A, C, D) != ccw(B, C, D) and ccw(A, B, C) != ccw(A, B, D)
    
    # 폴리라인의 각 선분과 교차 확인
    for i in range(len(polyline_points) - 1):
        if segments_intersect(line_start, line_end, polyline_points[i], polyline_points[i+1]):
            return True
    return False

def polyline_passes_through_line(polyline_points, line_start, line_end):
    """폴리라인의 선분 중 하나가 라인을 통과하는지 확인"""
    def ccw(A, B, C):
        return (C.y - A.y) * (B.x - A.x) > (B.y - A.y) * (C.x - A.x)
    
    def segments_intersect(A, B, C, D):
        return ccw(A, C, D) != ccw(B, C, D) and ccw(A, B, C) != ccw(A, B, D)
    
    # 폴리라인의 각 선분이 라인과 교차하는지 확인
    for i in range(len(polyline_points) - 1):
        if segments_intersect(polyline_points[i], polyline_points[i+1], line_start, line_end):
            return True
    return False

def polyline_passes_through_polyline(entity_points, ref_polyline_points):
    """폴리라인이 다른 폴리라인의 선분을 통과하는지 확인"""
    def ccw(A, B, C):
        return (C.y - A.y) * (B.x - A.x) > (B.y - A.y) * (C.x - A.x)
    
    def segments_intersect(A, B, C, D):
        return ccw(A, C, D) != ccw(B, C, D) and ccw(A, B, C) != ccw(A, B, D)
    
    # entity의 각 선분이 ref_polyline의 선분과 교차하는지 확인
    for i in range(len(entity_points) - 1):
        for j in range(len(ref_polyline_points) - 1):
            if segments_intersect(entity_points[i], entity_points[i+1], 
                                ref_polyline_points[j], ref_polyline_points[j+1]):
                return True
    return False

def is_entity_touching_olet_for_ad3(entity, dolet_points, tolerance=0.1):
    """AD3를 위한 접촉 확인 - 점 대 점만 확인"""
    if entity.dxftype() == 'LINE':
        start = Vec2(entity.dxf.start.x, entity.dxf.start.y)
        end = Vec2(entity.dxf.end.x, entity.dxf.end.y)
        points = [start, end]
    else:
        points = extract_points(entity)
    
    if not points:
        return False
    
    # 엔티티의 각 점이 OLET의 점과 접하는지만 확인 (선분 대 선분 제외)
    for entity_pt in points:
        for dolet_pt in dolet_points:
            if distance(entity_pt, dolet_pt) <= tolerance:
                return True
                
    return False

def find_nearest_point_to_point_distance(points1, points2, max_dist):
    """두 폴리라인의 점들 간 최소 거리 찾기
    
    max_dist 이내의 가장 가까운 점 쌍의 거리를 반환
    """
    min_dist = float('inf')
    
    for pt1 in points1:
        for pt2 in points2:
            d = distance(pt1, pt2)
            if d <= max_dist and d < min_dist:
                min_dist = d
    
    return min_dist if min_dist != float('inf') else None

def get_farthest_point_from_polyline(entity_points, ref_points):
    """엔티티의 점 중 참조 폴리라인에서 가장 먼 점 찾기"""
    farthest_point = None
    max_min_dist = 0
    
    for entity_pt in entity_points:
        # 이 점에서 ref_points의 모든 점까지의 최소 거리
        min_dist = float('inf')
        for ref_pt in ref_points:
            dist = distance(entity_pt, ref_pt)
            min_dist = min(min_dist, dist)
        
        # 최소 거리가 가장 큰 점을 선택
        if min_dist > max_min_dist:
            max_min_dist = min_dist
            farthest_point = entity_pt
    
    return farthest_point, max_min_dist

def find_texts_in_rectangle(msp, center_point, x_range, y_range, slope_tolerance=0.01):
    """특정 점 주변의 직사각형 범위 내 텍스트 찾기
    x_range: (min_x_offset, max_x_offset) - 중심점 기준 X 오프셋
    y_range: (min_y_offset, max_y_offset) - 중심점 기준 Y 오프셋
    """
    texts = []
    for text in msp.query('TEXT'):
        try:
            # 기울기 확인
            rotation = text.dxf.rotation
            if abs(rotation) > slope_tolerance:
                continue
                
            # 위치 확인
            insert = text.dxf.insert
            text_pos = Vec2(insert[0], insert[1])
            
            # 직사각형 범위 확인
            x_diff = text_pos.x - center_point.x
            y_diff = text_pos.y - center_point.y
            
            if x_range[0] <= x_diff <= x_range[1] and y_range[0] <= y_diff <= y_range[1]:
                texts.append({
                    'entity': text,
                    'position': text_pos,
                    'text': text.dxf.text.strip(),
                    'x_diff': x_diff,
                    'y_diff': y_diff
                })
        except:
            continue
    
    return texts

def is_protected_layer(layer_name):
    """보호된 레이어인지 확인 (PIPE, ELBL, TEE TEXT, PL4를 포함하는 레이어)"""
    layer_upper = layer_name.upper()
    protected_keywords = ['PIPE', 'ELBL', 'TEE TEXT', 'PL4']
    
    for keyword in protected_keywords:
        if keyword in layer_upper:
            return True
    
    return False

def check_del1_pair_distance(entity1, entity2):
    """두 DEL1 후보 간에 4mm 이내의 점이 있는지 확인"""
    points1 = extract_points(entity1)
    points2 = extract_points(entity2)
    
    if not points1 or not points2:
        return False
    
    # 두 폴리라인의 점들 간 최소 거리 확인
    for pt1 in points1:
        for pt2 in points2:
            if distance(pt1, pt2) <= 4.0:
                return True
    
    return False

def is_line_touching_entity(line, entity_points, tolerance=0.1):
    """LINE이 엔티티의 점과 접하는지 확인"""
    start = Vec2(line.dxf.start.x, line.dxf.start.y)
    end = Vec2(line.dxf.end.x, line.dxf.end.y)
    
    # LINE의 각 점이 엔티티의 점과 접하는지 확인
    for entity_pt in entity_points:
        if distance(start, entity_pt) <= tolerance or distance(end, entity_pt) <= tolerance:
            return True
    
    return False

def process_file(filepath):
    """DXF 파일 처리 - OLET 주변 엔티티 삭제"""
    doc = ezdxf.readfile(filepath)
    msp = doc.modelspace()
    
    print(f"\n처리 중: {os.path.basename(filepath)}")
    
    # 이미 다른 OLET에서 사용된 엔티티 추적
    used_entities = set()
    
    # 삭제할 엔티티들을 저장할 리스트
    entities_to_delete = []
    
    # 전체 처리된 엔티티 개수
    total_processed = 0
    
    # 1. OLET 레이어 폴리라인 찾기 (DOLET)
    dolet_entities = []
    for entity in msp.query('LWPOLYLINE POLYLINE'):
        layer = get_entity_layer(entity).upper()
        if layer == 'OLET':
            dolet_entities.append(entity)
            handle = get_entity_handle(entity)
            print(f"[DOLET] OLET 레이어 폴리라인 발견: {handle}")
    
    # 각 DOLET에 대해 처리
    for dolet in dolet_entities:
        dolet_points = extract_points(dolet)
        if not dolet_points:
            continue
            
        # DOLET 색상을 CYAN으로 변경
        set_entity_color(dolet, 4)  # CYAN
        
        print(f"\n[DOLET {get_entity_handle(dolet)}] 처리 시작")
        
        # 2. OLET의 어느 한 점으로부터 PIPE의 어느 한 점이 1mm 이내에 위치하는 PIPE 레이어 찾기
        pipe = None
        pipe_points = None
        pipe_dist = float('inf')
        
        # 폴리라인에서 PIPE 찾기
        for entity in msp.query('LWPOLYLINE POLYLINE'):
            layer = get_entity_layer(entity).upper()
            if 'PIPE' in layer:  # PIPE를 포함하는 레이어
                entity_points = extract_points(entity)
                if not entity_points:
                    continue
                    
                # OLET의 점과 PIPE의 점 간 최소 거리 확인
                for dolet_pt in dolet_points:
                    for entity_pt in entity_points:
                        d = distance(dolet_pt, entity_pt)
                        if d <= 1.0 and d < pipe_dist:
                            pipe = entity
                            pipe_dist = d
                            pipe_points = entity_points
        
        # LINE에서도 PIPE 찾기
        for line in msp.query('LINE'):
            layer = get_entity_layer(line).upper()
            if 'PIPE' in layer:  # PIPE를 포함하는 레이어
                start = Vec2(line.dxf.start.x, line.dxf.start.y)
                end = Vec2(line.dxf.end.x, line.dxf.end.y)
                line_points = [start, end]
                
                # OLET의 점과 LINE의 점 간 최소 거리 확인
                for dolet_pt in dolet_points:
                    for line_pt in line_points:
                        d = distance(dolet_pt, line_pt)
                        if d <= 1.0 and d < pipe_dist:
                            pipe = line
                            pipe_dist = d
                            pipe_points = line_points
        
        if not pipe:
            print(f"  [경고] OLET의 점으로부터 1mm 내에 PIPE를 포함하는 레이어를 찾을 수 없습니다.")
            continue
            
        if len(pipe_points) < 2:
            continue
            
        # PIPE 색상은 원래 그대로 유지
        # set_entity_color(pipe, 6)  # MAGENTA로 변경하려면 주석 해제
            
        # PIPE의 각도 계산
        pipe_angle = get_angle(pipe_points[0], pipe_points[1])
        pipe_type = "LINE" if pipe.dxftype() == 'LINE' else "POLYLINE"
        pipe_layer = get_entity_layer(pipe)
        opposite_angle = (pipe_angle + 180) % 360
        print(f"  [PIPE] 발견 ({pipe_type}, 레이어: {pipe_layer}, 점 간 거리: {pipe_dist:.3f}mm, 각도: {pipe_angle:.1f}° 또는 {opposite_angle:.1f}°)")
        
        # 3. GT/PL 포함, 길이 5-25mm, 2점 폴리라인 찾기 (DEL1)
        del1_list = []  # 2개 찾기
        del1_candidates = []
        pipe_parallel_candidates = []  # PIPE와 평행한 후보들
        
        for entity in msp.query('LWPOLYLINE POLYLINE'):
            if entity == dolet or entity == pipe:
                continue
                
            # 이미 다른 OLET에서 사용된 엔티티 제외
            if entity in used_entities:
                continue
                
            # OLET과 접하는 엔티티 제외 (0.1mm 기준)
            if is_entity_touching_olet(entity, dolet_points, tolerance=0.1):
                continue
                
            layer_name = get_entity_layer(entity)
            
            # PL4 레이어 제외
            if is_protected_layer(layer_name):
                continue
                
            if not ('GT' in layer_name.upper() or 'PL' in layer_name.upper()):
                continue
                
            points = extract_points(entity)
            # 정확히 2점만 허용
            if len(points) != 2:
                continue
                
            # 길이 확인 (5mm ~ 25mm)
            length = get_polyline_length(points)
            if not (5 <= length <= 25):
                continue
                
            # OLET의 점에서 폴리라인의 점까지 1.5mm 이상 5mm 이내에 있는지 확인
            is_in_range = False
            min_dist_to_olet = float('inf')
            
            for entity_pt in points:
                for dolet_pt in dolet_points:
                    dist = distance(entity_pt, dolet_pt)
                    min_dist_to_olet = min(min_dist_to_olet, dist)
                    if 1.5 <= dist <= 5.0:
                        is_in_range = True
            
            if not is_in_range:
                continue
                
            # 각도 계산
            entity_angle = get_angle(points[0], points[1])
            
            # DEL1 후보 정보 저장
            candidate_info = {
                'entity': entity,
                'distance_to_dolet': min_dist_to_olet,
                'length': length,
                'angle': entity_angle,
                'is_pipe_parallel': are_parallel(pipe_angle, entity_angle)
            }
            
            # 모든 후보에 추가
            del1_candidates.append(candidate_info)
            
            # PIPE와 평행한 경우 별도 리스트에도 추가
            if candidate_info['is_pipe_parallel']:
                pipe_parallel_candidates.append(candidate_info)
        
        # DEL1 선택 로직 - 우선순위: 1) PIPE와 평행, 2) 서로 평행
        
        # 먼저 PIPE와 평행한 후보들 중에서 선택
        if len(pipe_parallel_candidates) >= 2:
            pipe_parallel_candidates.sort(key=lambda x: x['distance_to_dolet'])
            
            for i, candidate1 in enumerate(pipe_parallel_candidates):
                if len(del1_list) >= 2:
                    break
                    
                for j, candidate2 in enumerate(pipe_parallel_candidates[i+1:], i+1):
                    # 두 폴리라인의 길이 차이가 0.1mm 이내인지 확인
                    if abs(candidate1['length'] - candidate2['length']) <= 0.1:
                        # 두 폴리라인 간에 4mm 이내의 점이 있는지 확인
                        if check_del1_pair_distance(candidate1['entity'], candidate2['entity']):
                            del1_list = [candidate1['entity'], candidate2['entity']]
                            
                            # 첫 번째 DEL1 정보 출력
                            entity = candidate1['entity']
                            orig_layer = get_entity_layer(entity)
                            used_entities.add(entity)
                            entities_to_delete.append(entity)  # 삭제 목록에 추가
                            print(f"  [DEL1-1] 발견: {get_entity_handle(entity)} (레이어: {orig_layer}, 길이: {candidate1['length']:.1f}mm, 각도: {candidate1['angle']:.1f}°, PIPE와 평행)")
                            
                            # 두 번째 DEL1 정보 출력
                            entity = candidate2['entity']
                            orig_layer = get_entity_layer(entity)
                            used_entities.add(entity)
                            entities_to_delete.append(entity)  # 삭제 목록에 추가
                            print(f"  [DEL1-2] 발견: {get_entity_handle(entity)} (레이어: {orig_layer}, 길이: {candidate2['length']:.1f}mm, 각도: {candidate2['angle']:.1f}°, PIPE와 평행)")
                            
                            print(f"  [DEL1] 길이 차이: {abs(candidate1['length'] - candidate2['length']):.3f}mm, 점간 거리 4mm 이내 (PIPE와 평행)")
                            break
        
        # PIPE와 평행한 2개를 못 찾은 경우, 전체 후보에서 서로 평행하고 길이가 같은 2개 찾기
        if len(del1_list) < 2:
            del1_candidates.sort(key=lambda x: x['distance_to_dolet'])
            
            for i, candidate1 in enumerate(del1_candidates):
                if len(del1_list) >= 2:
                    break
                    
                for j, candidate2 in enumerate(del1_candidates[i+1:], i+1):
                    # 두 폴리라인의 길이 차이가 0.1mm 이내인지 확인
                    if abs(candidate1['length'] - candidate2['length']) <= 0.1:
                        # 서로 평행한지 확인
                        if are_parallel(candidate1['angle'], candidate2['angle'], tolerance=1.0):
                            # 두 폴리라인 간에 4mm 이내의 점이 있는지 확인
                            if check_del1_pair_distance(candidate1['entity'], candidate2['entity']):
                                del1_list = [candidate1['entity'], candidate2['entity']]
                                
                                # 첫 번째 DEL1 정보 출력
                                entity = candidate1['entity']
                                orig_layer = get_entity_layer(entity)
                                used_entities.add(entity)
                                entities_to_delete.append(entity)  # 삭제 목록에 추가
                                print(f"  [DEL1-1] 발견: {get_entity_handle(entity)} (레이어: {orig_layer}, 길이: {candidate1['length']:.1f}mm, 각도: {candidate1['angle']:.1f}°)")
                                
                                # 두 번째 DEL1 정보 출력
                                entity = candidate2['entity']
                                orig_layer = get_entity_layer(entity)
                                used_entities.add(entity)
                                entities_to_delete.append(entity)  # 삭제 목록에 추가
                                print(f"  [DEL1-2] 발견: {get_entity_handle(entity)} (레이어: {orig_layer}, 길이: {candidate2['length']:.1f}mm, 각도: {candidate2['angle']:.1f}°)")
                                
                                print(f"  [DEL1] 길이 차이: {abs(candidate1['length'] - candidate2['length']):.3f}mm, 서로 평행, 점간 거리 4mm 이내")
                                break
        
        if len(del1_list) < 2:
            print(f"  [경고] 길이가 동일하고 평행하며 점간 거리가 4mm 이내인 DEL1 2개를 찾을 수 없습니다. ({len(del1_list)}개 발견)")
            if len(del1_list) == 0:
                continue
        
        # DEL1을 하나라도 찾은 경우에만 계속 진행
        if not del1_list:
            print(f"  [경고] DEL1을 찾을 수 없습니다.")
            continue
            
        # 첫 번째 DEL1을 기준으로 진행
        del1 = del1_list[0]
        
        # 4. DEL1의 점 중 OLET과 먼 점에서 3점 폴리라인의 2번째 점과 가장 가까운 것 찾기 (DEL2)
        del2 = None
        del1_points = extract_points(del1)
        
        # DEL1의 점 중 OLET과 가장 먼 점 찾기
        farthest_del1_point = None
        max_dist_to_olet = 0
        
        for del1_pt in del1_points:
            min_dist_to_olet = float('inf')
            for dolet_pt in dolet_points:
                dist = distance(del1_pt, dolet_pt)
                min_dist_to_olet = min(min_dist_to_olet, dist)
            
            if min_dist_to_olet > max_dist_to_olet:
                max_dist_to_olet = min_dist_to_olet
                farthest_del1_point = del1_pt
        
        print(f"  [DEL1-OLET] DEL1의 점 중 OLET과 가장 먼 점의 거리: {max_dist_to_olet:.3f}mm")
        
        # 3점 폴리라인 찾기
        del2_candidates = []
        for entity in msp.query('LWPOLYLINE POLYLINE'):
            if entity == dolet:
                continue
                
            # 이미 다른 OLET에서 사용된 엔티티 제외
            if entity in used_entities:
                continue
                
            # 보호된 레이어 확인 (PL4 포함)
            layer = get_entity_layer(entity)
            if is_protected_layer(layer):
                continue
                
            # OLET과 접하는 엔티티 제외 (0.1mm 기준)
            if is_entity_touching_olet(entity, dolet_points, tolerance=0.1):
                continue
                
            points = extract_points(entity)
            if len(points) == 3:  # 3점 폴리라인
                # OLET과 먼 DEL1 점에서 3점 폴리라인의 2번째 점(중간점)까지의 거리
                dist_to_second_point = distance(farthest_del1_point, points[1])
                
                # 점간 거리합 계산 (참고용)
                total_dist = distance(points[0], points[1]) + distance(points[1], points[2])
                
                del2_candidates.append({
                    'entity': entity,
                    'distance': dist_to_second_point,
                    'total_dist': total_dist,
                    'layer': layer
                })
        
        # 거리가 가장 가까운 것 선택
        if del2_candidates:
            del2_candidates.sort(key=lambda x: x['distance'])
            selected = del2_candidates[0]
            del2 = selected['entity']
            
            used_entities.add(del2)
            entities_to_delete.append(del2)  # 삭제 목록에 추가
            handle = get_entity_handle(del2)
            print(f"  [DEL2] 발견: {handle} (레이어: {selected['layer']}, 점간 거리합: {selected['total_dist']:.1f}mm)")
            print(f"  [DEL2] 총 {len(del2_candidates)}개의 3점 폴리라인 중 선택됨")
        else:
            print(f"  [경고] DEL2를 찾을 수 없습니다. (3점 폴리라인이 없음)")
            continue
            
        # 5. DEL2의 각 점에서 ARROW 레이어, 길이 1mm 이하 LINE 찾기 (DEL3)
        del3_list = []
        del2_points = extract_points(del2)
        
        for line in msp.query('LINE'):
            # 이미 다른 OLET에서 사용된 엔티티 제외
            if line in used_entities:
                continue
                
            # 보호된 레이어 확인 (PL4 포함)
            layer = get_entity_layer(line)
            if is_protected_layer(layer):
                continue
                
            # OLET과 접하는 LINE 제외 (0.1mm 기준)
            if is_entity_touching_olet(line, dolet_points, tolerance=0.1):
                continue
                
            if layer.upper() != 'ARROW':
                continue
                
            start = Vec2(line.dxf.start.x, line.dxf.start.y)
            end = Vec2(line.dxf.end.x, line.dxf.end.y)
            
            # 길이 확인
            line_length = distance(start, end)
            if line_length > 1.0:
                continue
                
            # DEL2의 점들과의 거리 확인
            for pt in del2_points:
                if distance(pt, start) < 0.1 or distance(pt, end) < 0.1:
                    del3_list.append(line)
                    used_entities.add(line)
                    entities_to_delete.append(line)  # 삭제 목록에 추가
                    handle = get_entity_handle(line)
                    print(f"  [DEL3] 발견: LINE {handle} (길이: {line_length:.3f}mm)")
                    break
        
        if not del3_list:
            print(f"  [경고] DEL3를 찾을 수 없습니다.")
            continue
            
        # 6. GT/PL2 포함, 길이 4-100mm, 2점 또는 3점, DEL3 점과 3mm 이내 폴리라인 찾기 (DEL4)
        del4 = None
        del4_candidates = []
        
        for entity in msp.query('LWPOLYLINE POLYLINE'):
            if entity == dolet:
                continue
                
            # 이미 다른 OLET에서 사용된 엔티티 제외
            if entity in used_entities:
                continue
                
            # DEL2로 선택된 엔티티 제외
            if entity == del2:
                continue
                
            # 보호된 레이어 확인 (PL4 포함)
            layer_name = get_entity_layer(entity)
            if is_protected_layer(layer_name):
                continue
                
            # OLET과 접하는 엔티티 제외 (0.1mm 기준)
            if is_entity_touching_olet(entity, dolet_points, tolerance=0.1):
                continue
                
            if not ('GT' in layer_name.upper() or 'PL2' in layer_name.upper()):
                continue
                
            points = extract_points(entity)
            # 2점 또는 3점만 허용
            if len(points) != 2 and len(points) != 3:
                continue
                
            # 길이 확인 (4mm ~ 100mm)
            length = get_polyline_length(points)
            if length < 4.0 or length > 100:
                continue
                
            # DEL3들의 점과 3mm 이내에 있는지 확인
            min_dist_to_del3 = float('inf')
            is_within_3mm = False
            
            for line in del3_list:
                start = Vec2(line.dxf.start.x, line.dxf.start.y)
                end = Vec2(line.dxf.end.x, line.dxf.end.y)
                
                # 폴리라인의 각 점에서 DEL3의 점까지 거리
                for pt in points:
                    dist_to_start = distance(pt, start)
                    dist_to_end = distance(pt, end)
                    
                    min_dist_to_del3 = min(min_dist_to_del3, dist_to_start, dist_to_end)
                    
                    # 3mm 이내인지 확인
                    if dist_to_start <= 3.0 or dist_to_end <= 3.0:
                        is_within_3mm = True
            
            # 3mm 이내에 있는 것만 후보로 추가
            if is_within_3mm:
                del4_candidates.append({
                    'entity': entity,
                    'distance_to_del3': min_dist_to_del3,
                    'length': length,
                    'points': len(points)
                })
        
        # DEL3에 가장 가까운 것을 선택
        if del4_candidates:
            del4_candidates.sort(key=lambda x: x['distance_to_del3'])
            selected = del4_candidates[0]
            del4 = selected['entity']
            orig_layer = get_entity_layer(del4)
            used_entities.add(del4)
            entities_to_delete.append(del4)  # 삭제 목록에 추가
            handle = get_entity_handle(del4)
            print(f"  [DEL4] 발견: {handle} (레이어: {orig_layer}, 길이: {selected['length']:.1f}mm, 점 개수: {selected['points']}, DEL3와의 거리: {selected['distance_to_del3']:.1f}mm)")
            print(f"  [DEL4] 총 {len(del4_candidates)}개 후보 중 DEL3에 가장 가까운 것 선택")
        else:
            print(f"  [경고] DEL4를 찾을 수 없습니다.")
            continue
            
        # 7. DEL4 25mm 내의 60-400 숫자 텍스트 찾기 (DEL5)
        del5 = None
        del4_points = extract_points(del4)
        min_dist_for_del5 = float('inf')
        
        for text in msp.query('TEXT'):
            # 이미 다른 OLET에서 사용된 텍스트 제외
            if text in used_entities:
                continue
                
            # 보호된 레이어 확인 (PL4 포함)
            text_layer = get_entity_layer(text)
            if is_protected_layer(text_layer):
                continue
                
            # 텍스트 기울기 확인 (0도인지)
            try:
                rotation = text.dxf.rotation
                if abs(rotation) > 0.01:
                    continue
            except:
                continue
                
            text_str = text.dxf.text.strip()
            
            # 숫자인지 확인
            try:
                value = float(text_str)
                if not (60 <= value <= 400):
                    continue
            except:
                continue
                
            # DEL4와의 최소 거리 확인
            insert = text.dxf.insert
            text_pos = Vec2(insert[0], insert[1])
            
            for pt in del4_points:
                dist = distance(pt, text_pos)
                if dist <= 25 and dist < min_dist_for_del5:
                    min_dist_for_del5 = dist
                    del5 = text
        
        if del5:
            used_entities.add(del5)
            entities_to_delete.append(del5)  # 삭제 목록에 추가
            print(f"  [DEL5] 발견: TEXT '{del5.dxf.text}' (거리: {min_dist_for_del5:.1f}mm, 기울기: 0°)")
        
        # 8. OLET에 접하는 엔티티 찾기 (DEL6, AD1~AD3)
        del6_list = []  # OLET 선분과 0.2mm 이내 점, 길이 2mm 이하
        ad_list = []   # OLET 선분과 0.1mm 이내 점, 길이 3mm 이상, 최대 3개
        ad_candidates = []  # AD 후보들을 거리순으로 정렬하기 위해
        
        # 폴리라인 검사
        for entity in msp.query('LWPOLYLINE POLYLINE'):
            if entity == dolet:  # OLET 자신 제외
                continue
                
            # 이미 사용된 엔티티 제외
            if entity in used_entities:
                continue
            
            # 레이어 확인
            layer = get_entity_layer(entity)
            
            # PL4 레이어 확인 (DEL6용)
            if 'PL4' in layer.upper():
                continue
                
            points = extract_points(entity)
            if not points:
                continue
                
            # OLET 선분과의 최소 거리 계산
            min_dist_to_olet_segment = float('inf')
            
            # 각 점에서 OLET 선분까지의 거리 확인
            for pt in points:
                for j in range(len(dolet_points) - 1):
                    dist = point_to_line_distance(pt, dolet_points[j], dolet_points[j+1])
                    min_dist_to_olet_segment = min(min_dist_to_olet_segment, dist)
            
            length = get_polyline_length(points)
            
            # DEL6 조건: 0.2mm 이내, 길이 2mm 이하
            if min_dist_to_olet_segment <= 0.2 and length <= 2.0:
                del6_list.append(entity)
                used_entities.add(entity)
                entities_to_delete.append(entity)  # 삭제 목록에 추가
                handle = get_entity_handle(entity)
                print(f"  [DEL6] OLET 선분과 {min_dist_to_olet_segment:.3f}mm, 길이 {length:.3f}mm 폴리라인: {handle} (레이어: {layer})")
            
            # AD 조건: 0.1mm 이내, 길이 3mm 이상, PIPE 포함 레이어 제외, DEL6에 선택되지 않은 것
            if min_dist_to_olet_segment <= 0.1 and length >= 3.0 and 'PIPE' not in layer.upper() and entity not in used_entities:
                ad_candidates.append({
                    'entity': entity,
                    'distance': min_dist_to_olet_segment,
                    'length': length,
                    'layer': layer,
                    'points': points
                })
        
        # LINE 검사 (DEL6만 해당)
        for line in msp.query('LINE'):
            # 이미 사용된 엔티티 제외
            if line in used_entities:
                continue
                
            layer = get_entity_layer(line)
            
            # PL4 레이어 확인
            if 'PL4' in layer.upper():
                continue
                
            start = Vec2(line.dxf.start.x, line.dxf.start.y)
            end = Vec2(line.dxf.end.x, line.dxf.end.y)
            line_length = distance(start, end)
            
            # 길이가 2mm 이하인 경우만
            if line_length <= 2.0:
                # OLET 선분과의 최소 거리 계산
                min_dist_to_olet_segment = float('inf')
                
                # 시작점과 끝점에서 OLET 선분까지의 거리
                for j in range(len(dolet_points) - 1):
                    dist_start = point_to_line_distance(start, dolet_points[j], dolet_points[j+1])
                    dist_end = point_to_line_distance(end, dolet_points[j], dolet_points[j+1])
                    min_dist_to_olet_segment = min(min_dist_to_olet_segment, dist_start, dist_end)
                
                # DEL6 조건: 0.2mm 이내
                if min_dist_to_olet_segment <= 0.2:
                    del6_list.append(line)
                    used_entities.add(line)
                    entities_to_delete.append(line)  # 삭제 목록에 추가
                    handle = get_entity_handle(line)
                    print(f"  [DEL6] OLET 선분과 {min_dist_to_olet_segment:.3f}mm, 길이 {line_length:.3f}mm LINE: {handle} (레이어: {layer})")
        
        # AD 후보 중 거리가 가까운 순으로 최대 10개 선택
        if ad_candidates:
            ad_candidates.sort(key=lambda x: x['distance'])
            selected_count = 0
            
            for candidate in ad_candidates:
                if selected_count >= 10:  # 최대 10개
                    break
                    
                entity = candidate['entity']
                ad_list.append({
                    'entity': entity,
                    'points': candidate['points'],
                    'name': f'AD{selected_count + 1}'
                })
                
                used_entities.add(entity)
                entities_to_delete.append(entity)  # 삭제 목록에 추가
                handle = get_entity_handle(entity)
                print(f"  [AD{selected_count + 1}] OLET 선분과 {candidate['distance']:.3f}mm, 길이 {candidate['length']:.3f}mm 폴리라인: {handle} (레이어: {candidate['layer']})")
                selected_count += 1
            
            if len(ad_candidates) > 10:
                print(f"  [AD] 총 {len(ad_candidates)}개 후보 중 10개 선택")
        
        # 9. AD의 먼 점에서 가장 가까운 텍스트 1개 찾기 (DEL7, DEL8, DEL9 중 1개)
        for ad_info in ad_list:
            ad = ad_info['entity']
            ad_points = ad_info['points']
            ad_name = ad_info['name']
            
            # AD의 OLET에서 가장 먼 점 찾기
            farthest_point, _ = get_farthest_point_from_polyline(ad_points, dolet_points)
            
            if farthest_point:
                # 직사각형 범위의 텍스트 찾기 (X: -60~+15mm, Y: ±10mm)
                texts = find_texts_in_rectangle(msp, farthest_point, (-60, 15), (-10, 10))
                
                # 이미 사용된 텍스트 제외
                available_texts = []
                for text_info in texts:
                    text_entity = text_info['entity']
                    if text_entity in used_entities:
                        continue
                        
                    # 보호된 레이어 확인
                    text_layer = get_entity_layer(text_entity)
                    if is_protected_layer(text_layer):
                        continue
                        
                    text_content = text_info['text'].upper()
                    
                    # CON, X, EL, FL 포함 확인
                    if 'CON' in text_content:
                        text_info['type'] = 'DEL7'
                        available_texts.append(text_info)
                    elif 'X' in text_content:
                        text_info['type'] = 'DEL8'
                        available_texts.append(text_info)
                    elif 'EL' in text_content or 'FL' in text_content:
                        text_info['type'] = 'DEL9'
                        available_texts.append(text_info)
                
                # AD의 먼 점에서 가장 가까운 텍스트 1개 선택
                if available_texts:
                    # 거리 계산하여 정렬
                    for text_info in available_texts:
                        text_pos = text_info['position']
                        text_info['distance'] = distance(farthest_point, text_pos)
                    
                    available_texts.sort(key=lambda x: x['distance'])
                    selected_text = available_texts[0]
                    
                    text_entity = selected_text['entity']
                    used_entities.add(text_entity)
                    entities_to_delete.append(text_entity)  # 삭제 목록에 추가
                    print(f"  [{selected_text['type']}] {ad_name}에서 텍스트 발견: '{text_entity.dxf.text}' (거리: {selected_text['distance']:.1f}mm)")
                    
                    # CON 텍스트인 경우 아래 텍스트도 찾기
                    if selected_text['type'] == 'DEL7' and 'CON' in text_entity.dxf.text.upper():
                        text_pos = selected_text['position']
                        
                        # -Y로 5~8mm 아래 텍스트 찾기
                        additional_texts = []
                        for text2 in msp.query('TEXT'):
                            if text2 == text_entity or text2 in used_entities:
                                continue
                                
                            # 보호된 레이어 확인
                            text2_layer = get_entity_layer(text2)
                            if is_protected_layer(text2_layer):
                                continue
                                
                            try:
                                insert2 = text2.dxf.insert
                                text2_pos = Vec2(insert2[0], insert2[1])
                                
                                # Y 차이가 -5~-8mm 범위인지 확인
                                y_diff = text2_pos.y - text_pos.y
                                x_diff = abs(text2_pos.x - text_pos.x)
                                
                                if -8 <= y_diff <= -5 and x_diff <= 5:  # X는 비슷한 위치
                                    additional_texts.append((text2, y_diff))
                            except:
                                continue
                        
                        # Y 차이가 -5mm에 가장 가까운 것 선택
                        if additional_texts:
                            additional_texts.sort(key=lambda x: abs(x[1] + 5))
                            next_text = additional_texts[0][0]
                            used_entities.add(next_text)
                            entities_to_delete.append(next_text)  # 삭제 목록에 추가
                            print(f"  [DEL7-2] CON 아래 텍스트: '{next_text.dxf.text}' (Y 차이: {additional_texts[0][1]:.1f}mm)")
        
        # 10. ORIENTATION 텍스트 찾기 및 방향 텍스트 찾기 (DEL10)
        del10_list = []  # ORIENTATION 및 방향 텍스트
        orientation_texts = []
        
        for text in msp.query('TEXT'):
            # 이미 사용된 텍스트 제외
            if text in used_entities:
                continue
                
            # 보호된 레이어 확인 (PL4 포함)
            text_layer = get_entity_layer(text)
            if is_protected_layer(text_layer):
                continue
                
            text_str = text.dxf.text.strip().upper()
            if 'ORIENTATION' in text_str:
                orientation_texts.append(text)
                # ORIENTATION 텍스트도 삭제
                used_entities.add(text)
                entities_to_delete.append(text)  # 삭제 목록에 추가
                del10_list.append(text)
                print(f"  [DEL10] ORIENTATION 텍스트 발견: '{text.dxf.text}'")
        
        # ORIENTATION 텍스트 아래 8mm 내의 방향 텍스트 찾기
        for orient_text in orientation_texts:
            try:
                orient_insert = orient_text.dxf.insert
                orient_pos = Vec2(orient_insert[0], orient_insert[1])
                
                # ORIENTATION 아래 8mm 범위에서 W, S, N, E 텍스트 찾기
                for text in msp.query('TEXT'):
                    if text in used_entities or text == orient_text:
                        continue
                        
                    text_layer = get_entity_layer(text)
                    if is_protected_layer(text_layer):
                        continue
                        
                    try:
                        insert = text.dxf.insert
                        text_pos = Vec2(insert[0], insert[1])
                        
                        # Y 차이 확인 (-8mm 이내)
                        y_diff = text_pos.y - orient_pos.y
                        x_diff = abs(text_pos.x - orient_pos.x)
                        
                        if -8 <= y_diff <= 0 and x_diff <= 10:  # Y는 아래쪽, X는 비슷한 위치
                            text_str = text.dxf.text.strip().upper()
                            
                            # W, S, N, E 포함 확인
                            if any(direction in text_str for direction in ['W', 'S', 'N', 'E']):
                                used_entities.add(text)
                                entities_to_delete.append(text)  # 삭제 목록에 추가
                                del10_list.append(text)
                                print(f"  [DEL10] 방향 텍스트 발견: '{text.dxf.text}' (ORIENTATION 아래 {abs(y_diff):.1f}mm)")
                    except:
                        continue
            except:
                continue
        
        # 11. AD1, AD2, AD3에 0.1mm 접하는 0.6~0.8mm LINE 찾기 (DEL11)
        del11_list = []
        
        # AD1, AD2, AD3의 점들 수집
        ad123_points = []
        for ad_info in ad_list:
            if ad_info['name'] in ['AD1', 'AD2', 'AD3']:
                ad123_points.extend(ad_info['points'])
        
        if ad123_points:
            for line in msp.query('LINE'):
                # 이미 사용된 엔티티 제외
                if line in used_entities:
                    continue
                    
                # 보호된 레이어 확인
                layer = get_entity_layer(line)
                if is_protected_layer(layer):
                    continue
                    
                start = Vec2(line.dxf.start.x, line.dxf.start.y)
                end = Vec2(line.dxf.end.x, line.dxf.end.y)
                line_length = distance(start, end)
                
                # 길이 확인 (0.6~0.8mm)
                if not (0.6 <= line_length <= 0.8):
                    continue
                    
                # AD1, AD2, AD3의 점과 0.1mm 이내에 있는지 확인
                if is_line_touching_entity(line, ad123_points, tolerance=0.1):
                    del11_list.append(line)
                    used_entities.add(line)
                    entities_to_delete.append(line)  # 삭제 목록에 추가
                    handle = get_entity_handle(line)
                    print(f"  [DEL11] 발견: LINE {handle} (레이어: {layer}, 길이: {line_length:.3f}mm)")
        
        # 12. 처리된 엔티티 개수 집계
        processed_count = len(entities_to_delete) - total_processed
        print(f"\n[DOLET {get_entity_handle(dolet)}] 처리 완료: {processed_count}개 엔티티가 삭제 예정")
        total_processed = len(entities_to_delete)
    
    # 13. 엔티티 삭제
    for entity in entities_to_delete:
        try:
            msp.delete_entity(entity)
        except Exception as e:
            print(f"  [에러] 엔티티 삭제 실패: {e}")
    
    # 14. 처리 요약
    print(f"\n총 {len(entities_to_delete)}개 엔티티가 삭제됨")
    print(f"\n처리 정보:")
    print(f"  - OLET (DOLET): CYAN 색상 유지, 원래 레이어 유지")
    print(f"  - PIPE 포함 레이어: 원래 색상 및 레이어 유지")
    print(f"  - DEL1~DEL11, AD1~AD10: 삭제됨")
    print(f"\n보호된 레이어: PIPE 포함, ELBL 포함, TEE TEXT 포함, PL4 포함")
    print(f"중복 방지: 각 엔티티는 하나의 OLET에서만 선택됨")
    
    # 15. 파일 저장
    save_path = os.path.splitext(filepath)[0] + "_ODEL.dxf"
    doc.saveas(save_path)
    print(f"✅ 저장 완료: {os.path.basename(save_path)}")
    print(f"   - 선택된 엔티티들이 삭제됨")

if __name__ == "__main__":
    files = select_dxf_files()
    if not files:
        print("❌ 선택된 파일이 없습니다.")
    else:
        for file in files:
            try:
                process_file(file)
            except Exception as e:
                print(f"❌ 파일 처리 중 오류 발생: {e}")
        print("\n🎉 모든 파일 처리 완료!")