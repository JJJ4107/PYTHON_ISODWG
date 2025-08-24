import ezdxf
import os
import math
import sys
from ezdxf.math import Vec2

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

def is_entity_touching_olet(entity, dolet_points, tolerance=0.1):
    """엔티티가 OLET과 접하는지 확인"""
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

def process_file(filepath):
    """DXF 파일 처리"""
    doc = ezdxf.readfile(filepath)
    msp = doc.modelspace()
    
    # 삭제할 엔티티 리스트
    entities_to_delete = []
    
    # 이미 다른 OLET에서 사용된 엔티티 추적
    used_entities = set()
    
    # 1. OLET 레이어 폴리라인 찾기 (DOLET)
    dolet_entities = []
    for entity in msp.query('LWPOLYLINE POLYLINE'):
        layer = get_entity_layer(entity).upper()
        if layer == 'OLET':
            dolet_entities.append(entity)
    
    # 각 DOLET에 대해 처리
    for dolet in dolet_entities:
        dolet_points = extract_points(dolet)
        if not dolet_points:
            continue
            
        # DOLET 색상을 CYAN으로 변경
        set_entity_color(dolet, 4)  # CYAN
        
        # 2. OLET의 어느 한 점으로부터 PIPE의 어느 한 점이 1mm 이내에 위치하는 PIPE 레이어 찾기
        pipe = None
        pipe_points = None
        pipe_dist = float('inf')
        
        # 폴리라인에서 PIPE 찾기
        for entity in msp.query('LWPOLYLINE POLYLINE'):
            layer = get_entity_layer(entity).upper()
            if layer == 'PIPE':
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
            if layer == 'PIPE':
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
            continue
            
        if len(pipe_points) < 2:
            continue
            
        # PIPE의 각도 계산
        pipe_angle = get_angle(pipe_points[0], pipe_points[1])
        pipe_type = "LINE" if pipe.dxftype() == 'LINE' else "POLYLINE"
        opposite_angle = (pipe_angle + 180) % 360
        
        # 3. PIPE와 평행하고 GT 또는 PL 포함, 길이 5-15mm, 2점 폴리라인, OLET의 점에서 1.5-5mm 범위 2개 찾기 (DEL1)
        del1_list = []  # 2개 찾기
        del1_candidates = []
        
        for entity in msp.query('LWPOLYLINE POLYLINE'):
            if entity == dolet or entity == pipe:
                continue
                
            # 이미 다른 OLET에서 사용된 엔티티 제외
            if entity in used_entities:
                continue
                
            # OLET과 접하는 엔티티 제외
            if is_entity_touching_olet(entity, dolet_points):
                continue
                
            layer_name = get_entity_layer(entity).upper()
            if not ('GT' in layer_name or 'PL' in layer_name):
                continue
                
            points = extract_points(entity)
            # 정확히 2점만 허용
            if len(points) != 2:
                continue
                
            # 길이 확인
            length = get_polyline_length(points)
            if not (5 <= length <= 15):
                continue
                
            # 각도 확인 (평행 여부) - 시작점이 반대인 경우도 평행으로 인식
            entity_angle = get_angle(points[0], points[1])
            if not are_parallel(pipe_angle, entity_angle):
                continue
                
            # OLET의 점에서 폴리라인의 점까지 1.5mm 이상 5mm 이내에 있는지 확인
            is_in_range = False
            min_dist_to_olet = float('inf')
            
            for entity_pt in points:
                for dolet_pt in dolet_points:
                    dist = distance(entity_pt, dolet_pt)
                    min_dist_to_olet = min(min_dist_to_olet, dist)
                    if 1.5 <= dist <= 5.0:  # 1.5mm 이상 5mm 이내로 변경
                        is_in_range = True
            
            if not is_in_range:
                continue
                
            # DEL1 후보로 추가
            del1_candidates.append({
                'entity': entity,
                'distance_to_dolet': min_dist_to_olet,
                'length': length
            })
        
        # 길이가 동일한(오차 0.3mm) 2개 찾기
        del1_candidates.sort(key=lambda x: x['distance_to_dolet'])
        
        for i, candidate1 in enumerate(del1_candidates):
            if len(del1_list) >= 2:
                break
                
            for j, candidate2 in enumerate(del1_candidates[i+1:], i+1):
                # 두 폴리라인의 길이 차이가 0.3mm 이내인지 확인
                if abs(candidate1['length'] - candidate2['length']) <= 0.3:
                    del1_list = [candidate1['entity'], candidate2['entity']]
                    
                    # 첫 번째 DEL1 정보 출력 및 색상 변경
                    entity = candidate1['entity']
                    set_entity_color(entity, 1)  # RED로 즉시 변경
                    used_entities.add(entity)  # 사용된 엔티티로 추가
                    
                    # 두 번째 DEL1 정보 출력 및 색상 변경
                    entity = candidate2['entity']
                    set_entity_color(entity, 1)  # RED로 즉시 변경
                    used_entities.add(entity)  # 사용된 엔티티로 추가
                    break
        
        if len(del1_list) < 2:
            if len(del1_list) == 0:
                continue
        
        # DEL1을 하나라도 찾은 경우에만 계속 진행
        if not del1_list:
            continue
            
        # 첫 번째 DEL1을 기준으로 진행
        del1 = del1_list[0]
        
        # 4. DEL1의 점 중 OLET과 먼 점에서 3점 폴리라인의 2번째 점과 가장 가까운 것 찾기 (DEL2) - 무조건 1개
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
        
        # OLET과 먼 DEL1 점에서 3점 폴리라인의 2번째 점(중간점)과 가장 가까운 것 찾기
        min_del2_dist = float('inf')
        del2_candidates = []
        
        for entity in msp.query('LWPOLYLINE POLYLINE'):
            if entity == dolet:  # OLET 자신은 제외
                continue
                
            # 이미 다른 OLET에서 사용된 엔티티 제외
            if entity in used_entities:
                continue
                
            # OLET과 접하는 엔티티 제외
            if is_entity_touching_olet(entity, dolet_points):
                continue
                
            points = extract_points(entity)
            if len(points) != 3:
                continue
                
            # OLET과 먼 DEL1 점에서 3점 폴리라인의 2번째 점(중간점)까지의 거리
            dist_to_second_point = distance(farthest_del1_point, points[1])  # points[1]이 2번째 점
            
            # 점간 거리합 계산 (참고용)
            total_dist = distance(points[0], points[1]) + distance(points[1], points[2])
            
            del2_candidates.append({
                'entity': entity,
                'distance': dist_to_second_point,
                'total_dist': total_dist,
                'layer': get_entity_layer(entity)
            })
        
        # 거리가 가장 가까운 것 선택
        if del2_candidates:
            del2_candidates.sort(key=lambda x: x['distance'])
            selected = del2_candidates[0]
            del2 = selected['entity']
            min_del2_dist = selected['distance']
            
            set_entity_color(del2, 1)  # RED로 즉시 변경
            used_entities.add(del2)  # 사용된 엔티티로 추가
        else:
            continue
            
        # 5. DEL2의 각 점에서 ARROW 레이어, 길이 1mm 이하 LINE 찾기 (DEL3)
        del3_list = []
        del2_points = extract_points(del2)
        
        for line in msp.query('LINE'):
            # 이미 다른 OLET에서 사용된 엔티티 제외
            if line in used_entities:
                continue
                
            # OLET과 접하는 LINE 제외
            if is_entity_touching_olet(line, dolet_points):
                continue
                
            layer = get_entity_layer(line).upper()
            if layer != 'ARROW':
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
                    set_entity_color(line, 1)  # RED로 즉시 변경
                    used_entities.add(line)  # 사용된 엔티티로 추가
                    break
        
        if not del3_list:
            continue
            
        # 6. GT/PL2 포함, 길이 3.5-100mm, 2점 또는 3점, DEL3 점과 3mm 이내 폴리라인 찾기 (DEL4)
        del4 = None
        del4_candidates = []
        
        for entity in msp.query('LWPOLYLINE POLYLINE'):
            if entity == dolet:  # OLET 자신은 제외
                continue
                
            # 이미 다른 OLET에서 사용된 엔티티 제외
            if entity in used_entities:
                continue
                
            # DEL2로 선택된 엔티티 제외
            if entity == del2:
                continue
                
            # OLET과 접하는 엔티티 제외
            if is_entity_touching_olet(entity, dolet_points):
                continue
                
            layer_name = get_entity_layer(entity).upper()
            if not ('GT' in layer_name or 'PL2' in layer_name):
                continue
                
            points = extract_points(entity)
            # 2점 또는 3점만 허용
            if len(points) != 2 and len(points) != 3:
                continue
                
            # 길이 확인 (3.5mm ~ 100mm)
            length = get_polyline_length(points)
            if length < 3.5 or length > 100:
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
            set_entity_color(del4, 1)  # RED로 즉시 변경
            used_entities.add(del4)  # 사용된 엔티티로 추가
        else:
            continue
            
        # 7. DEL4 25mm 내의 60-400 숫자 텍스트 찾기 (DEL5) - 기울기 0인 1개만
        del5 = None
        del4_points = extract_points(del4)
        min_dist_for_del5 = float('inf')
        
        for text in msp.query('TEXT'):
            # 이미 다른 OLET에서 사용된 텍스트 제외
            if text in used_entities:
                continue
                
            # 텍스트 기울기 확인 (0도인지)
            try:
                rotation = text.dxf.rotation
                if abs(rotation) > 0.01:  # 0.01도 이상 기울어져 있으면 제외
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
            set_entity_color(del5, 1)  # RED로 즉시 변경
            used_entities.add(del5)  # 사용된 엔티티로 추가
        
        # 8. 찾은 모든 엔티티를 삭제 리스트에 추가 (색상은 이미 변경됨)
        for del1 in del1_list:
            entities_to_delete.append(del1)
            
        if del2:
            entities_to_delete.append(del2)
            
        for line in del3_list:
            entities_to_delete.append(line)
            
        if del4:
            entities_to_delete.append(del4)
            
        if del5:
            entities_to_delete.append(del5)
    
    # 9. 엔티티 삭제 (DOLET과 PIPE 제외, RED 색상만)
    deleted_count = 0
    for entity in entities_to_delete:
        try:
            # 색상이 RED(1)인 경우만 삭제
            if get_entity_color(entity) == 1:
                msp.delete_entity(entity)
                deleted_count += 1
        except Exception as e:
            pass
    
    # 10. 파일 저장
    save_path = os.path.splitext(filepath)[0] + "_ODEL.dxf"
    doc.saveas(save_path)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(1)
    
    # Command line에서 전달된 DXF 파일들 처리
    for filepath in sys.argv[1:]:
        if os.path.exists(filepath) and filepath.lower().endswith('.dxf'):
            try:
                process_file(filepath)
            except Exception as e:
                pass