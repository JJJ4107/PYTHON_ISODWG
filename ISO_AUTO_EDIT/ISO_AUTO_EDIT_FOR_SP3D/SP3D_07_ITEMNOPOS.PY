import ezdxf
import os
import math
from ezdxf.math import Vec2
from tkinter import Tk, filedialog

# TextBoxLineFinder 클래스
class TextBoxLineFinder:
    """TEXT를 BOX화하여 가장 가까운 LINE을 찾는 유틸리티 클래스"""
    
    def __init__(self):
        pass
    
    @staticmethod
    def get_text_position(text):
        """TEXT 엔티티의 위치를 Vec2로 반환"""
        try:
            if hasattr(text.dxf, "insert"):
                ins = text.dxf.insert
                if hasattr(ins, '__getitem__'):
                    return Vec2(float(ins[0]), float(ins[1]))
                elif hasattr(ins, 'x') and hasattr(ins, 'y'):
                    return Vec2(float(ins.x), float(ins.y))
                else:
                    return Vec2(float(ins), 0)
            
            if hasattr(text.dxf, "location"):
                loc = text.dxf.location
                if hasattr(loc, '__getitem__') and len(loc) >= 2:
                    return Vec2(float(loc[0]), float(loc[1]))
                elif hasattr(loc, 'x') and hasattr(loc, 'y'):
                    return Vec2(float(loc.x), float(loc.y))
                    
        except Exception as e:
            print(f"   [경고] TEXT 위치 가져오기 오류: {e}")
        
        return Vec2(0.0, 0.0)
    
    @staticmethod
    def get_text_bbox(text, box_height_offset=0.3):
        """
        TEXT 엔티티의 경계 상자 계산
        BOX 높이 = TEXT 높이(2.2) + offset(1.3) = 3.5mm 고정
        BOX 최소 너비 = 6.5mm
        """
        pos = TextBoxLineFinder.get_text_position(text)
        # TEXT 높이는 2.2mm 고정
        height = 2.2
        # 텍스트 길이를 대략적으로 계산 (문자 수 * 높이 * 0.8)
        text_len = len(text.dxf.text) * height * 0.8
        
        # 최소 너비 6.5mm 보장
        text_len = max(text_len, 6.5)
        
        # BOX 높이는 3.5mm 고정 (2.2 + 0.65 + 0.65)
        box_height = 3.5
        
        # TEXT의 현재 회전 각도 가져오기
        rotation = getattr(text.dxf, 'rotation', 0)
        
        # 회전되지 않은 상태의 BOX (TEXT 원점 기준)
        return {
            'min_x': pos.x,
            'max_x': pos.x + text_len,
            'min_y': pos.y - 0.65,  # 아래로 0.65
            'max_y': pos.y + height + 0.65,  # 위로 height + 0.65
            'rotation': rotation,  # TEXT의 회전 각도 포함
            'pos': pos  # TEXT의 위치 (회전 중심점)
        }
    
    @staticmethod
    def get_text_reference_points(text, num_points=3):
        """TEXT BOX의 참조점들을 계산"""
        bbox = TextBoxLineFinder.get_text_bbox(text)
        pos = bbox['pos']
        
        if num_points == 3:
            left_point = pos
            center_point = Vec2((bbox['min_x'] + bbox['max_x']) / 2, pos.y)
            right_point = Vec2(bbox['max_x'], pos.y)
            return [left_point, center_point, right_point]
        else:
            points = []
            for i in range(num_points):
                ratio = i / (num_points - 1) if num_points > 1 else 0
                x = bbox['min_x'] + (bbox['max_x'] - bbox['min_x']) * ratio
                points.append(Vec2(x, pos.y))
            return points
    
    @staticmethod
    def distance(p1, p2):
        """두 점 사이의 거리 계산"""
        return math.hypot(p2.x - p1.x, p2.y - p1.y)
    
    @staticmethod
    def get_line_length(line):
        """LINE의 길이 계산"""
        if line.dxftype() == "LINE":
            start = Vec2(line.dxf.start.x, line.dxf.start.y)
            end = Vec2(line.dxf.end.x, line.dxf.end.y)
            return TextBoxLineFinder.distance(start, end)
        return 0
    
    @staticmethod
    def find_closest_line_to_group(entities, lines, exclude_entities=None, exclude_layers=None, min_length=None, max_distance=None, debug=False):
        """엔티티 그룹 전체의 BOX에서 가장 가까운 LINE 찾기"""
        if exclude_entities is None:
            exclude_entities = []
        if exclude_layers is None:
            exclude_layers = []
        
        # 그룹의 전체 경계 계산
        min_x = float('inf')
        max_x = float('-inf')
        min_y = float('inf')
        max_y = float('-inf')
        
        # TEXT와 LINE의 모든 점들을 수집
        for ent in entities:
            if ent.dxftype() == "TEXT":
                bbox = TextBoxLineFinder.get_text_bbox(ent)
                min_x = min(min_x, bbox['min_x'])
                max_x = max(max_x, bbox['max_x'])
                min_y = min(min_y, bbox['min_y'])
                max_y = max(max_y, bbox['max_y'])
            elif ent.dxftype() == "LINE":
                start = Vec2(ent.dxf.start.x, ent.dxf.start.y)
                end = Vec2(ent.dxf.end.x, ent.dxf.end.y)
                min_x = min(min_x, start.x, end.x)
                max_x = max(max_x, start.x, end.x)
                min_y = min(min_y, start.y, end.y)
                max_y = max(max_y, start.y, end.y)
        
        # 그룹의 중심점
        group_center = Vec2((min_x + max_x) / 2, (min_y + max_y) / 2)
        
        # 전체 BOX의 참조점들 (9개: 모서리 4개, 변 중점 4개, 중심 1개)
        ref_points = [
            Vec2(min_x, min_y),  # 좌하
            Vec2(max_x, min_y),  # 우하
            Vec2(max_x, max_y),  # 우상
            Vec2(min_x, max_y),  # 좌상
            Vec2((min_x + max_x) / 2, min_y),  # 하단 중점
            Vec2(max_x, (min_y + max_y) / 2),  # 우측 중점
            Vec2((min_x + max_x) / 2, max_y),  # 상단 중점
            Vec2(min_x, (min_y + max_y) / 2),  # 좌측 중점
            Vec2((min_x + max_x) / 2, (min_y + max_y) / 2)  # 중심점
        ]
        
        if debug:
            print(f"\n[ITNO BOX 분석]")
            print(f"   전체 BOX: X({min_x:.2f}~{max_x:.2f}), Y({min_y:.2f}~{max_y:.2f})")
            print(f"   중심점: ({group_center.x:.2f}, {group_center.y:.2f})")
            if max_distance:
                print(f"   검색 범위: 중심에서 {max_distance}mm 이내")
            print(f"   제외 레이어: {', '.join(exclude_layers)}")
            print(f"   제외 엔티티: {len(exclude_entities)}개")
        
        exclude_layers_upper = [layer.upper() for layer in exclude_layers]
        
        found_line = None
        closest_point = None
        farthest_point = None
        min_dist = float("inf")
        
        lines_checked = 0
        lines_in_range = 0
        
        for line in lines:
            if line in exclude_entities:
                continue
                
            if line.dxftype() != 'LINE':
                continue
                
            if line.dxf.layer.upper() in exclude_layers_upper:
                continue
            
            # LINE의 중점 계산
            start = Vec2(line.dxf.start.x, line.dxf.start.y)
            end = Vec2(line.dxf.end.x, line.dxf.end.y)
            line_center = Vec2((start.x + end.x) / 2, (start.y + end.y) / 2)
            
            # 최대 거리 제한 확인
            if max_distance is not None:
                if TextBoxLineFinder.distance(group_center, line_center) > max_distance:
                    continue
            
            lines_in_range += 1
            
            if min_length is not None:
                line_len = TextBoxLineFinder.get_line_length(line)
                if line_len < min_length:
                    continue
            
            lines_checked += 1
            
            distances = []
            for ref_point in ref_points:
                distances.append(TextBoxLineFinder.distance(start, ref_point))
                distances.append(TextBoxLineFinder.distance(end, ref_point))
            
            min_pt_dist = min(distances)
            
            if min_pt_dist < min_dist:
                min_dist = min_pt_dist
                found_line = line
                
                min_idx = distances.index(min_pt_dist)
                
                if min_idx % 2 == 0:
                    closest_point = start
                    farthest_point = end
                else:
                    closest_point = end
                    farthest_point = start
        
        if debug:
            print(f"   범위 내 LINE 수: {lines_in_range}개")
            print(f"   조건 만족 LINE 수: {lines_checked}개")
            if found_line:
                print(f"   가장 가까운 LINE: {found_line.dxf.handle} (거리: {min_dist:.2f}mm)")
                print(f"   가까운 점: ({closest_point.x:.2f}, {closest_point.y:.2f})")
                print(f"   먼 점: ({farthest_point.x:.2f}, {farthest_point.y:.2f})")
            else:
                print(f"   결과: 적합한 LINE을 찾을 수 없음")
        
        return found_line, closest_point, farthest_point


def select_files():
    Tk().withdraw()
    return filedialog.askopenfilenames(
        title="DXF 파일 선택 (여러 개 가능)",
        filetypes=[("DXF files", "*.dxf")])


def distance(p1, p2):
    return math.hypot(p2.x - p1.x, p2.y - p1.y)


def set_entity_color(entity, color=1):
    try:
        if entity and hasattr(entity, "dxf") and hasattr(entity.dxf, "color"):
            entity.dxf.color = color
    except:
        pass


def get_text_position(text):
    """TEXT 엔티티의 위치를 Vec2로 반환"""
    return TextBoxLineFinder.get_text_position(text)


def get_line_midpoint(line):
    try:
        start = line.dxf.start
        end = line.dxf.end
        return Vec2((start.x + end.x) / 2, (start.y + end.y) / 2)
    except:
        return Vec2(0, 0)


def stretch_line(line, fixed_point, moving_point):
    """LINE의 한 끝점을 고정하고 다른 끝점을 이동 (stretch)"""
    try:
        start = Vec2(line.dxf.start.x, line.dxf.start.y)
        end = Vec2(line.dxf.end.x, line.dxf.end.y)
        
        # 어느 끝점이 고정점에 더 가까운지 확인
        if distance(start, fixed_point) < distance(end, fixed_point):
            # start가 고정점, end를 이동
            line.dxf.start = (fixed_point.x, fixed_point.y, 0)
            line.dxf.end = (moving_point.x, moving_point.y, 0)
        else:
            # end가 고정점, start를 이동
            line.dxf.end = (fixed_point.x, fixed_point.y, 0)
            line.dxf.start = (moving_point.x, moving_point.y, 0)
    except Exception as e:
        print(f"▶ LINE stretch 오류: {e}")


def draw_square(msp, center, size, layer_name, color):
    """중심점에 정사각형 그리기"""
    half_size = size / 2
    corners = [
        Vec2(center.x - half_size, center.y - half_size),
        Vec2(center.x + half_size, center.y - half_size),
        Vec2(center.x + half_size, center.y + half_size),
        Vec2(center.x - half_size, center.y + half_size)
    ]
    
    for i in range(4):
        start = corners[i]
        end = corners[(i + 1) % 4]
        line = msp.add_line((start.x, start.y, 0), (end.x, end.y, 0))
        line.dxf.layer = layer_name
        line.dxf.color = color


def find_elbo_entity(msp, point, search_radius=5.0):
    """주어진 점에서 반경 내의 ELBO 레이어 ARC 또는 LINE 찾기"""
    found_arc = None
    found_line = None
    min_arc_dist = float('inf')
    min_line_dist = float('inf')
    
    # ARC 검색
    for arc in msp.query('ARC'):
        if arc.dxf.layer.upper() != "ELBO":
            continue
            
        # ARC 중심점까지의 거리
        center = Vec2(arc.dxf.center.x, arc.dxf.center.y)
        dist = distance(point, center)
        
        if dist <= search_radius and dist < min_arc_dist:
            min_arc_dist = dist
            found_arc = arc
    
    # LINE 검색
    for line in msp.query('LINE'):
        if line.dxf.layer.upper() != "ELBO":
            continue
            
        start = Vec2(line.dxf.start.x, line.dxf.start.y)
        end = Vec2(line.dxf.end.x, line.dxf.end.y)
        
        # 두 끝점 중 가까운 점까지의 거리
        dist_to_start = distance(point, start)
        dist_to_end = distance(point, end)
        min_dist = min(dist_to_start, dist_to_end)
        
        if min_dist <= search_radius and min_dist < min_line_dist:
            min_line_dist = min_dist
            found_line = line
    
    # ARC가 우선순위
    if found_arc:
        # ARC의 꼭지점(중심점)을 EPOS로
        epos = Vec2(found_arc.dxf.center.x, found_arc.dxf.center.y)
        return 'ARC', found_arc, epos, min_arc_dist
    elif found_line:
        # LINE의 가까운 점을 EPOS로
        start = Vec2(found_line.dxf.start.x, found_line.dxf.start.y)
        end = Vec2(found_line.dxf.end.x, found_line.dxf.end.y)
        if distance(point, start) < distance(point, end):
            epos = start
        else:
            epos = end
        return 'LINE', found_line, epos, min_line_dist
    else:
        return None, None, None, None


def move_entity(entity, offset):
    try:
        t = entity.dxftype()
        if t == "TEXT":
            pos = get_text_position(entity)
            npos = Vec2(pos.x + offset.x, pos.y + offset.y)
            entity.dxf.insert = (npos.x, npos.y, 0)
        elif t == "LINE":
            start = Vec2(entity.dxf.start.x, entity.dxf.start.y)
            end = Vec2(entity.dxf.end.x, entity.dxf.end.y)
            entity.dxf.start = (start.x + offset.x, start.y + offset.y, 0)
            entity.dxf.end = (end.x + offset.x, end.y + offset.y, 0)
    except Exception as e:
        print(f"▶ 이동 오류: {entity} / {e}")


def get_entity_center(entities):
    """엔티티 그룹의 중심점 계산"""
    x_sum = 0; y_sum = 0; n = 0
    for ent in entities:
        if ent.dxftype() == "TEXT":
            pos = get_text_position(ent)
            x_sum += pos.x; y_sum += pos.y; n += 1
        elif ent.dxftype() == "LINE":
            a = Vec2(ent.dxf.start.x, ent.dxf.start.y)
            b = Vec2(ent.dxf.end.x, ent.dxf.end.y)
            x_sum += (a.x + b.x) / 2; y_sum += (a.y + b.y) / 2; n += 1
    return Vec2(x_sum/n, y_sum/n) if n else Vec2(0,0)


def get_line_angle(line):
    """LINE의 기울기(각도) 계산"""
    if line.dxftype() == "LINE":
        start = Vec2(line.dxf.start.x, line.dxf.start.y)
        end = Vec2(line.dxf.end.x, line.dxf.end.y)
        dx = end.x - start.x
        dy = end.y - start.y
        return math.degrees(math.atan2(dy, dx))
    return 0


def get_line_length(line):
    """LINE의 길이 계산"""
    if line.dxftype() == "LINE":
        start = Vec2(line.dxf.start.x, line.dxf.start.y)
        end = Vec2(line.dxf.end.x, line.dxf.end.y)
        return distance(start, end)
    return 0


def get_text_bbox(text):
    """TEXT 엔티티의 경계 상자 계산"""
    return TextBoxLineFinder.get_text_bbox(text)


def rotate_point(pt, center, angle_deg):
    angle_rad = math.radians(angle_deg)
    dx, dy = pt.x - center.x, pt.y - center.y
    cos_a, sin_a = math.cos(angle_rad), math.sin(angle_rad)
    rx = dx * cos_a - dy * sin_a + center.x
    ry = dx * sin_a + dy * cos_a + center.y
    return Vec2(rx, ry)


def get_rotated_bbox_bounds(bbox):
    """회전된 BOX의 실제 경계 좌표 계산"""
    if not isinstance(bbox, dict):
        return {'min_x': 0, 'max_x': 0, 'min_y': 0, 'max_y': 0}
    
    if 'min_x' not in bbox or 'max_x' not in bbox or 'min_y' not in bbox or 'max_y' not in bbox:
        return {'min_x': 0, 'max_x': 0, 'min_y': 0, 'max_y': 0}
    
    pos = bbox.get('pos')
    if not pos:
        pos = Vec2(bbox['min_x'], bbox['min_y'])
    
    corners = [
        (bbox['min_x'] - pos.x, bbox['min_y'] - pos.y),
        (bbox['max_x'] - pos.x, bbox['min_y'] - pos.y),
        (bbox['max_x'] - pos.x, bbox['max_y'] - pos.y),
        (bbox['min_x'] - pos.x, bbox['max_y'] - pos.y)
    ]
    
    rotation = bbox.get('rotation', 0)
    if abs(rotation) > 0.01:
        rotation_rad = math.radians(rotation)
        cos_r = math.cos(rotation_rad)
        sin_r = math.sin(rotation_rad)
        
        rotated_corners = []
        for dx, dy in corners:
            rx = dx * cos_r - dy * sin_r
            ry = dx * sin_r + dy * cos_r
            rotated_corners.append((rx + pos.x, ry + pos.y))
    else:
        rotated_corners = [(x + pos.x, y + pos.y) for x, y in corners]
    
    x_coords = [c[0] for c in rotated_corners]
    y_coords = [c[1] for c in rotated_corners]
    
    return {
        'min_x': min(x_coords),
        'max_x': max(x_coords),
        'min_y': min(y_coords),
        'max_y': max(y_coords)
    }


def line_intersects_bbox(line_start, line_end, bbox):
    """선분과 BOX의 교차 여부 확인"""
    # 회전된 BOX의 실제 경계 좌표
    bounds = get_rotated_bbox_bounds(bbox)
    
    # BOX의 네 변을 선분으로 정의
    box_edges = [
        (Vec2(bounds['min_x'], bounds['min_y']), Vec2(bounds['max_x'], bounds['min_y'])),  # 하단
        (Vec2(bounds['max_x'], bounds['min_y']), Vec2(bounds['max_x'], bounds['max_y'])),  # 우측
        (Vec2(bounds['max_x'], bounds['max_y']), Vec2(bounds['min_x'], bounds['max_y'])),  # 상단
        (Vec2(bounds['min_x'], bounds['max_y']), Vec2(bounds['min_x'], bounds['min_y']))   # 좌측
    ]
    
    # LINE이 BOX 내부에 완전히 포함되는 경우
    if (bounds['min_x'] <= line_start.x <= bounds['max_x'] and
        bounds['min_y'] <= line_start.y <= bounds['max_y'] and
        bounds['min_x'] <= line_end.x <= bounds['max_x'] and
        bounds['min_y'] <= line_end.y <= bounds['max_y']):
        return True
    
    # LINE이 BOX의 변과 교차하는지 확인
    for edge_start, edge_end in box_edges:
        if line_segments_intersect(line_start, line_end, edge_start, edge_end):
            return True
    
    return False


def line_segments_intersect(p1, p2, p3, p4):
    """두 선분의 교차 여부 확인"""
    def ccw(A, B, C):
        return (C.y - A.y) * (B.x - A.x) > (B.y - A.y) * (C.x - A.x)
    
    return ccw(p1, p3, p4) != ccw(p2, p3, p4) and ccw(p1, p2, p3) != ccw(p1, p2, p4)


def check_bbox_overlap(bbox1, bbox2, threshold=0.5):
    """두 경계 상자가 겹치는지 확인 (회전 고려)"""
    if not isinstance(bbox1, dict) or not isinstance(bbox2, dict):
        return False
        
    required_keys = ['min_x', 'max_x', 'min_y', 'max_y']
    for key in required_keys:
        if key not in bbox1 or key not in bbox2:
            return False
    
    bounds1 = get_rotated_bbox_bounds(bbox1)
    bounds2 = get_rotated_bbox_bounds(bbox2)
    
    x_gap = max(bounds1['min_x'] - bounds2['max_x'], bounds2['min_x'] - bounds1['max_x'])
    y_gap = max(bounds1['min_y'] - bounds2['max_y'], bounds2['min_y'] - bounds1['max_y'])
    
    if x_gap < 0 and y_gap < 0:
        overlap_x = min(bounds1['max_x'], bounds2['max_x']) - max(bounds1['min_x'], bounds2['min_x'])
        overlap_y = min(bounds1['max_y'], bounds2['max_y']) - max(bounds1['min_y'], bounds2['min_y'])
        
        overlap = (overlap_x > threshold and overlap_y > threshold)
        
        return overlap
    else:
        return False


def draw_bbox(msp, bbox, layer_name, color):
    """BOX를 도면에 그리기 (회전된 BOX를 4개의 LINE으로 구성)"""
    pos = bbox.get('pos')
    if not pos:
        pos = Vec2(bbox['min_x'], bbox['min_y'])
    
    corners = [
        Vec2(bbox['min_x'], bbox['min_y']),
        Vec2(bbox['max_x'], bbox['min_y']),
        Vec2(bbox['max_x'], bbox['max_y']),
        Vec2(bbox['min_x'], bbox['max_y'])
    ]
    
    rotation = bbox.get('rotation', 0)
    if abs(rotation) > 0.01:
        rotated_corners = []
        for corner in corners:
            rotated = rotate_point(corner, pos, rotation)
            rotated_corners.append(rotated)
        corners = rotated_corners
    
    for i in range(4):
        start = corners[i]
        end = corners[(i + 1) % 4]
        line = msp.add_line((start.x, start.y, 0), (end.x, end.y, 0))
        line.dxf.layer = layer_name
        line.dxf.color = color


def delete_boxes_by_layer(msp, layer_names):
    """특정 레이어의 모든 LINE(BOX) 삭제"""
    entities_to_delete = []
    for entity in msp:
        if entity.dxftype() == 'LINE' and entity.dxf.layer in layer_names:
            entities_to_delete.append(entity)
    
    for entity in entities_to_delete:
        msp.delete_entity(entity)
    
    if entities_to_delete:
        print(f"   [BOX 삭제] {len(entities_to_delete)}개 BOX LINE 삭제")


# -------------------------
# A1 필터: 원/호 접촉 배제 유틸
# -------------------------
def angle_in_arc(theta, start_deg, end_deg):
    """각도 theta(도)가 ARC의 start~end 스윕 안에 있는지 판단 (시계/반시계 모두 대응)"""
    # 0~360 정규화
    def norm(a):
        a = a % 360.0
        return a + 360.0 if a < 0 else a
    t = norm(theta)
    s = norm(start_deg)
    e = norm(end_deg)
    if s <= e:
        return s - 1e-9 <= t <= e + 1e-9
    else:
        # 랩어라운드 (예: s=300, e=30)
        return t >= s - 1e-9 or t <= e + 1e-9


def is_point_near_any_circle_or_arc(msp, pt: Vec2, tol: float = 0.5) -> bool:
    """포인트가 지름 4mm 이상 CIRCLE/ARC의 둘레에 tol(mm) 이내로 접하는지 검사"""
    # CIRCLE
    for c in msp.query("CIRCLE"):
        try:
            center = Vec2(c.dxf.center.x, c.dxf.center.y)
            r = float(c.dxf.radius)
            
            # 지름 4mm 이상만 체크 (반지름 2mm 이상)
            if r < 2.0:
                continue
                
            d = abs(distance(pt, center) - r)
            if d <= tol:
                return True
        except Exception:
            continue
    # ARC
    for a in msp.query("ARC"):
        try:
            center = Vec2(a.dxf.center.x, a.dxf.center.y)
            r = float(a.dxf.radius)
            
            # 지름 4mm 이상만 체크 (반지름 2mm 이상)
            if r < 2.0:
                continue
                
            # 반지름 근접
            d_rad = abs(distance(pt, center) - r)
            if d_rad > tol:
                continue
            # 각도 스윕 안에 있는지
            vec = Vec2(pt.x - center.x, pt.y - center.y)
            theta = math.degrees(math.atan2(vec.y, vec.x))  # -180~180
            if angle_in_arc(theta, float(a.dxf.start_angle), float(a.dxf.end_angle)):
                return True
        except Exception:
            continue
    return False


def check_interference(itno_entities, msp, exclude_entities, threshold=0.5, draw_all_itno_boxes=True):
    """ITEMNO 그룹이 다른 TEXT 및 모든 LINE과 간섭하는지 BOX 기준으로 확인"""
    # ITNO 그룹에서 TEXT만 추출하여 BOX 계산
    itno_text_boxes = []
    itno_text_list = []
    itno_text_entities = []
    itno_line_entities = []
    
    for ent in itno_entities:
        if ent.dxftype() == "TEXT":
            bbox = get_text_bbox(ent)
            itno_text_boxes.append(bbox)
            itno_text_list.append(ent.dxf.text)
            itno_text_entities.append(ent)
        elif ent.dxftype() == "LINE":
            itno_line_entities.append(ent)
    
    # ITNO 그룹의 중심점 계산 (간섭 체크 범위 제한용)
    itno_center = get_entity_center(itno_entities)
    check_radius = 40.0  # 40mm 반경
    
    if draw_all_itno_boxes:
        print(f"\n   [간섭 체크] ITEMNO: {', '.join(itno_text_list)}, 반경: {check_radius}mm")
        for i, (text, bbox, ent) in enumerate(zip(itno_text_list, itno_text_boxes, itno_text_entities)):
            draw_bbox(msp, bbox, "ITEMNO_BOX", 2)  # YELLOW
    
    checked_text_count = 0
    checked_line_count = 0
    total_line_count = 0
    interfered_texts = []
    interfered_lines = []
    interfered_with_itno = []
    
    # 다른 모든 TEXT와 간섭 검사
    for text in msp.query('TEXT'):
        # ITNO 그룹의 TEXT나 제외 목록에 있는 TEXT는 건너뜀
        if text in itno_text_entities or text in exclude_entities:
            continue
        
        # 거리 체크 - 40mm 범위 밖은 건너뜀
        text_pos = get_text_position(text)
        if distance(itno_center, text_pos) > check_radius:
            continue
            
        checked_text_count += 1
        
        text_bbox = get_text_bbox(text)
        
        for idx, itno_bbox in enumerate(itno_text_boxes):
            if check_bbox_overlap(itno_bbox, text_bbox, threshold):
                if not any(item['text'] == text.dxf.text and 
                          abs(item['pos'].x - get_text_position(text).x) < 0.01 and 
                          abs(item['pos'].y - get_text_position(text).y) < 0.01 
                          for item in interfered_texts):
                    interfered_texts.append({
                        'text': text.dxf.text,
                        'pos': get_text_position(text),
                        'bbox': text_bbox,
                        'layer': text.dxf.layer,
                        'entity': text
                    })
                    if idx not in interfered_with_itno:
                        interfered_with_itno.append(idx)
                break
    
    # 모든 LINE과 간섭 검사 (ITNO 자신의 LINE과 제외 목록의 LINE만 제외)
    for line in msp.query('LINE'):
        total_line_count += 1
        
        if line in itno_line_entities or line in exclude_entities:
            continue
        
        # FRAME, PIPE 및 ITNO 관련 레이어는 간섭 체크에서 제외
        if line.dxf.layer.upper() in ["FRAME", "ITNO", "ITEMPOS"]:
            continue
            
        # 간섭 체크 관련 레이어들 제외
        if line.dxf.layer in ["ITEMNO_BOX", "INTERFERENCE_ITNO", "INTERFERENCE_TEXT", "INTERFERENCE_LINE", "ITNO", "ITEMPOS"]:
            continue
        
        # 거리 체크 - 40mm 범위 밖은 건너뜀
        line_center = get_line_midpoint(line)
        if distance(itno_center, line_center) > check_radius:
            continue
            
        checked_line_count += 1
        
        # LINE의 시작점과 끝점
        start = Vec2(line.dxf.start.x, line.dxf.start.y)
        end = Vec2(line.dxf.end.x, line.dxf.end.y)
        
        # 각 ITNO BOX와 LINE의 교차 확인
        for idx, itno_bbox in enumerate(itno_text_boxes):
            if line_intersects_bbox(start, end, itno_bbox):
                # 동일한 LINE이 이미 추가되었는지 체크
                already_added = False
                for item in interfered_lines:
                    if item['entity'] is line:
                        already_added = True
                        break
                
                if not already_added:
                    interfered_lines.append({
                        'start': start,
                        'end': end,
                        'layer': line.dxf.layer,
                        'entity': line
                    })
                    if idx not in interfered_with_itno:
                        interfered_with_itno.append(idx)
                break
    
    if draw_all_itno_boxes:
        print(f"   검사: TEXT {checked_text_count}개, LINE {checked_line_count}개 (전체 LINE {total_line_count}개)")
    
    if interfered_texts or interfered_lines:
        if draw_all_itno_boxes:
            print(f"   [간섭] TEXT {len(interfered_texts)}개, LINE {len(interfered_lines)}개")
        
        for idx in interfered_with_itno:
            draw_bbox(msp, itno_text_boxes[idx], "INTERFERENCE_ITNO", 1)  # RED
            
        for item in interfered_texts:
            draw_bbox(msp, item['bbox'], "INTERFERENCE_TEXT", 1)  # RED
            
        for item in interfered_lines:
            # 간섭된 LINE을 별도로 표시하지 않음 (원래 상태 유지)
            pass
        
        return True
    else:
        if draw_all_itno_boxes:
            print(f"   [간섭 없음]")
        return False


def is_numeric_text(text_content):
    """텍스트가 숫자이거나 G를 포함하는지 확인"""
    try:
        # 공백 제거
        text_content = text_content.strip()
        
        # G를 포함하는 경우 확인 (예: G1, G10, G15 등)
        if 'G' in text_content.upper():
            # G 뒤의 숫자 추출 시도
            g_text = text_content.upper().replace('G', '').strip()
            if g_text:  # G 뒤에 문자가 있는 경우
                num = float(g_text)
                return True, num
            else:  # G만 있는 경우
                return True, 0
        else:
            # 일반 숫자로 변환 시도
            num = float(text_content)
            return True, num
    except:
        return False, None


def process_dxf(file_path):
    try:
        doc = ezdxf.readfile(file_path)
    except Exception as e:
        print(f"파일 열기 실패: {file_path} / {e}")
        return

    msp = doc.modelspace()
    modified = False
    
    # 이미 선택된 A1 LINE들을 추적
    used_a1_lines = []

    # ISOTEXT 레이어의 기울기 0도, 숫자 20 이하 또는 G 포함 TEXT 찾기
    for st1 in msp.query('TEXT'):
        # 레이어가 ISOTEXT가 아니면 제외
        if st1.dxf.layer.upper() != "ISOTEXT":
            continue
            
        # 기울기가 0도가 아니면 제외
        rotation = getattr(st1.dxf, 'rotation', 0)
        if abs(rotation) > 0.01:  # 0도가 아님
            continue
            
        # 숫자 또는 G 포함 확인하고 20 이하인지 확인
        is_num, num_value = is_numeric_text(st1.dxf.text)
        if not is_num or num_value > 20:
            continue
            
        st1_pos = get_text_position(st1)
        print(f"\n[ITNO 후보] ISOTEXT 발견: '{st1.dxf.text}' (값={num_value:.1f}, 위치=({st1_pos.x:.2f}, {st1_pos.y:.2f}))")
        print(f"   [LINE 검색] 제외 레이어: FRAME, DL, AD1, DIM, ITNO, ITEMPOS, PIPE")

        # ISOTEXT 숫자 중심에서 ±X 5mm, ±Y 5mm 범위에서 LINE 찾기
        candidate_lines = []
        exclude_layers_for_itno = ['FRAME', 'DL', 'AD1', 'DIM', 'ITNO', 'ITEMPOS', 'PIPE']
        
        for e in msp.query('LINE'):
            # 제외 레이어 확인
            if e.dxf.layer.upper() in [layer.upper() for layer in exclude_layers_for_itno]:
                continue
                
            pos = get_line_midpoint(e)
            dx = pos.x - st1_pos.x
            dy = pos.y - st1_pos.y
            if abs(dx) <= 5 and abs(dy) <= 5:
                candidate_lines.append(e)

        # LINE 길이 필터링 (2.8~7mm)
        line_st2s = []
        for e in candidate_lines:
            start = e.dxf.start
            end = e.dxf.end
            length = distance(Vec2(start.x, start.y), Vec2(end.x, end.y))
            if 2.8 <= length <= 7.0:
                line_st2s.append(e)

        # LINE이 4개 미만이면 건너뛰기
        if len(line_st2s) < 4:
            print(f"   [LINE 부족] {len(line_st2s)}개 LINE 발견 (최소 4개 필요)")
            print(f"   - 제외 레이어: {', '.join(exclude_layers_for_itno)}")
            continue
            
        # LINE이 4개 이상이면 가장 가까운 4개 선택
        if len(line_st2s) > 4:
            line_distances = []
            for line in line_st2s:
                start = Vec2(line.dxf.start.x, line.dxf.start.y)
                end = Vec2(line.dxf.end.x, line.dxf.end.y)
                min_dist = min(distance(start, st1_pos), distance(end, st1_pos))
                line_distances.append((min_dist, line))
            
            line_distances.sort(key=lambda x: x[0])
            line_st2s = [item[1] for item in line_distances[:4]]
            print(f"   [LINE 선택] 총 {len(line_distances)}개 중 가장 가까운 4개 선택")
        
        # -Y 5mm 이내에서 "°", "DN", '"' 포함 TEXT 찾기
        itno_dn_text = None
        for e in msp.query('TEXT'):
            if e is st1:
                continue
            pos = get_text_position(e)
            dx = abs(pos.x - st1_pos.x)
            dy = st1_pos.y - pos.y  # Y 차이 (아래쪽이 양수)
            
            # X 범위 2mm, Y 범위 0~5mm
            if dx <= 2.0 and 0 < dy <= 5.0:
                if "°" in e.dxf.text or "DN" in e.dxf.text.upper() or '"' in e.dxf.text:
                    itno_dn_text = e
                    print(f"   [ITNODN 발견] 특수 텍스트: '{e.dxf.text}'")
                    break

        # ITNO 그룹 설정 - 모두 YELLOW 색상, ITEMPOS 레이어
        st1.dxf.layer = "ITEMPOS"
        set_entity_color(st1, 2)  # YELLOW
        
        for l in line_st2s:
            l.dxf.layer = "ITEMPOS"
            set_entity_color(l, 2)  # YELLOW
            
        if itno_dn_text:
            itno_dn_text.dxf.layer = "ITEMPOS"
            set_entity_color(itno_dn_text, 2)  # YELLOW
            
        modified = True
        print(f"\n[ITNO 처리] '{st1.dxf.text}', LINE: {len(line_st2s)}개 (2.8~7mm)")
        
        # 이전 간섭 체크 BOX 정리 (이전 ITNO의 간섭 BOX 제거)
        temp_box_layers = ["ITEMNO_BOX", "INTERFERENCE_ITNO", "INTERFERENCE_TEXT", "INTERFERENCE_LINE"]
        delete_boxes_by_layer(msp, temp_box_layers)
        
        # ITNO 그룹 구성
        itno_entities = [st1] + line_st2s
        if itno_dn_text:
            itno_entities.append(itno_dn_text)

        # 현재 위치 저장 (ST)
        ST = get_entity_center(itno_entities)
        print(f"   [ST] 현재 ITNO 중심점: ({ST.x:.2f}, {ST.y:.2f})")

        # A1 찾기 - ITNO 전체 BOX 기준
        print(f"\n   [A1 찾기] ITNO 그룹 전체 BOX에서 가장 가까운 LINE 검색 (25mm 이내)")
        print(f"   - 이미 사용된 A1 수: {len(used_a1_lines)}개")
        
        # A1이 될 수 없는 레이어들 (치수 관련 레이어 등 + ITNO + PIPE)
        exclude_layers_for_a1 = ['FRAME', 'DL', 'AD1', 'DIM', 'ITNO', 'ITEMPOS', 'PIPE']
        
        # 제외할 엔티티 목록 (ITNO 자신의 LINE + 이미 선택된 A1들)
        exclude_entities_for_a1 = line_st2s + used_a1_lines
        
        # ---- A1 재시도 루프: 원/호 0.5mm 접촉 배제 ----
        rejected_a1 = []
        while True:
            found_A1, AP1, AP2 = TextBoxLineFinder.find_closest_line_to_group(
                entities=itno_entities,
                lines=msp.query('LINE'),
                exclude_entities=exclude_entities_for_a1,
                exclude_layers=exclude_layers_for_a1,
                min_length=None,
                max_distance=25.0,  # ITNO BOX 중심에서 25mm 이내
                debug=True
            )
            
            if not found_A1:
                break
            
            # A1 끝점이 원/호 둘레에 0.5mm 이내면 후보 제외하고 다음 후보 탐색
            if is_point_near_any_circle_or_arc(msp, AP1, 0.5) or is_point_near_any_circle_or_arc(msp, AP2, 0.5):
                print(f"   [A1 제외] 끝점이 원/호에 0.5mm 이내 접촉 → LINE {found_A1.dxf.handle} 제외")
                rejected_a1.append(found_A1)
                exclude_entities_for_a1.append(found_A1)
                continue
            else:
                # 조건 통과
                break
        
        if not found_A1:
            print(f"   [A1 없음] ITNO BOX에서 조건을 만족하는 LINE을 찾을 수 없습니다 (원/호 접촉 배제 포함)")
            continue
        
        # A1: 레이어 유지(변경하지 않음), 색상만 CYAN
        # found_A1.dxf.layer = "ITEMPOS"  # ← 변경 금지
        set_entity_color(found_A1, 4)  # CYAN
        
        # 선택된 A1을 사용된 목록에 추가
        used_a1_lines.append(found_A1)
        
        line_len = get_line_length(found_A1)
        print(f"   [A1] LINE {found_A1.dxf.handle} (길이: {line_len:.2f}mm)")
        print(f"   - 이 A1은 다른 ITNO에서 사용 불가")
        
        # AP1 원래 위치 저장 (나중에 복원용)
        original_AP1 = Vec2(AP1.x, AP1.y)

        # DEL1 찾기: A1 끝에서 2mm 이내 접하는 2mm 이하 LINE 3개
        del1_lines = []
        a1_start = Vec2(found_A1.dxf.start.x, found_A1.dxf.start.y)
        a1_end = Vec2(found_A1.dxf.end.x, found_A1.dxf.end.y)
        all_endpoints = [a1_start, a1_end]
        
        for line in msp.query('LINE'):
            if line is found_A1 or line in line_st2s:
                continue
            if line.dxf.layer.upper() in ["FRAME", "ITNO", "ITEMPOS", "PIPE"]:
                continue
                
            line_len = get_line_length(line)
            if line_len > 2.0:
                continue
            
            start = Vec2(line.dxf.start.x, line.dxf.start.y)
            end = Vec2(line.dxf.end.x, line.dxf.end.y)
            
            for endpoint in all_endpoints:
                if distance(start, endpoint) <= 2.0 or distance(end, endpoint) <= 2.0:
                    del1_lines.append(line)
                    break
            
            if len(del1_lines) >= 3:
                break
        
        # DEL1: 레이어 유지(변경하지 않음), 색상만 CYAN
        for i, line in enumerate(del1_lines):
            # line.dxf.layer = "ITEMPOS"  # ← 변경 금지
            set_entity_color(line, 4)  # CYAN
            print(f"   [DEL1-{i+1}] LINE {line.dxf.handle}")
        
        # DEL1이 없으면 이 ITNO는 건너뛰기
        if len(del1_lines) == 0:
            print(f"   [DEL1 없음] DEL1을 찾을 수 없어 이 ITNO 건너뛰기")
            continue

        # A1 기울기 계산
        a1_angle = get_line_angle(found_A1)
        print(f"\n   [A1 기울기] {a1_angle:.2f}°")

        # MO 계산: AP2에서 AP1 방향으로 3.8mm 지점 (A1이 3.8mm가 되는 위치)
        # AP2에서 AP1로의 방향 벡터
        ap_direction = Vec2(AP1.x - AP2.x, AP1.y - AP2.y)
        ap_length = distance(AP1, AP2)
        if ap_length > 0:
            # 정규화된 방향 벡터
            ap_unit = Vec2(ap_direction.x / ap_length, ap_direction.y / ap_length)
            # MO는 AP2에서 3.8mm 떨어진 지점
            MO = Vec2(AP2.x + ap_unit.x * 3.8, AP2.y + ap_unit.y * 3.8)
            print(f"   [MO] A1이 3.8mm가 되는 지점: ({MO.x:.2f}, {MO.y:.2f})")
            print(f"   - 현재 A1 길이: {ap_length:.2f}mm")
            print(f"   - MO에서 A1 길이: 3.8mm")
        else:
            # A1 길이가 0인 경우 ST 사용
            MO = ST
            print(f"   [MO] A1 길이가 0이므로 ST 위치 사용")

        # 간섭 체크를 위한 제외 목록 (ITNO 자신과 A1만 제외)
        # DEL1은 원위치에 고정되어 간섭 체크 대상에 포함됨
        exclude_entities = [st1]
        if itno_dn_text:
            exclude_entities.append(itno_dn_text)
        if found_A1:
            exclude_entities.append(found_A1)  # A1만 제외

        # ST에서 MO 방향으로 1mm씩 이동하면서 간섭 체크
        print(f"\n   ========== 간섭 체크 및 위치 조정 ==========")
        
        # A1의 현재 길이가 3.8mm보다 큰 경우에만 이동
        if distance(AP1, AP2) > 3.8:
            # ITNO가 이동해야 할 거리: MO에서 ST까지의 거리
            # MO 위치에서의 ITNO 중심점 계산
            mo_offset = Vec2(MO.x - AP1.x, MO.y - AP1.y)
            mo_itno_center = Vec2(ST.x + mo_offset.x, ST.y + mo_offset.y)
            
            # MO 위치에서 ST까지의 이동 거리
            total_distance = distance(mo_itno_center, ST)
            
            print(f"   [이동 계획]")
            print(f"   - ST (원위치): ({ST.x:.2f}, {ST.y:.2f})")
            print(f"   - MO에서의 ITNO 중심: ({mo_itno_center.x:.2f}, {mo_itno_center.y:.2f})")
            print(f"   - 총 이동가능 거리: {total_distance:.2f}mm")
            
            steps = int(total_distance / 1.0) + 1  # 1mm 단위, +1로 ST 위치 포함
            print(f"   - 이동 단계: {steps}회 (1mm씩)")
            
            final_position = None
            found_position = False
            
            # MO부터 ST까지 1mm씩 이동하면서 간섭 체크
            for step in range(steps + 1):
                # 현재 테스트 위치 계산 (MO에서 ST 방향으로)
                if steps > 0:
                    ratio = 1.0 - (step / steps)
                else:
                    ratio = 0
                    
                # ITNO 중심점 위치
                test_center = Vec2(
                    ST.x + (mo_itno_center.x - ST.x) * ratio,
                    ST.y + (mo_itno_center.y - ST.y) * ratio
                )
                
                # 현재 위치에서 테스트 위치까지의 offset
                current_center = get_entity_center(itno_entities)
                test_offset = Vec2(test_center.x - current_center.x, test_center.y - current_center.y)
                
                # ITNO를 테스트 위치로 이동
                for ent in itno_entities:
                    move_entity(ent, test_offset)
                
                # A1 stretch (AP1을 ITNO와 함께 이동, AP2는 고정)
                if found_A1:
                    # AP1의 새 위치 계산
                    new_AP1 = Vec2(original_AP1.x + (test_center.x - ST.x), original_AP1.y + (test_center.y - ST.y))
                    stretch_line(found_A1, AP2, new_AP1)
                    current_a1_length = distance(new_AP1, AP2)
                    
                    if step == 0:
                        print(f"   [Step {step}] MO 위치 테스트 (A1=3.8mm), 실제 A1 길이: {current_a1_length:.2f}mm")
                    elif step == steps:
                        print(f"   [Step {step}] ST 위치 테스트, A1 길이: {current_a1_length:.2f}mm")
                
                # 간섭 체크 (BOX 그리지 않음)
                has_interference = check_interference(itno_entities, msp, exclude_entities, draw_all_itno_boxes=False)
                
                if not has_interference:
                    final_position = test_center
                    found_position = True
                    final_AP1 = new_AP1
                    final_a1_length = distance(final_AP1, AP2)
                    print(f"   [위치 확정] Step {step}에서 간섭 없는 위치 발견")
                    print(f"   - 최종 A1 길이: {final_a1_length:.2f}mm")
                    print(f"   - ST에서 이동 거리: {distance(ST, final_position):.2f}mm")
                    break
                else:
                    # 원위치로 복원 (다음 step을 위해)
                    for ent in itno_entities:
                        move_entity(ent, Vec2(-test_offset.x, -test_offset.y))
                    
                    if step < 5 or step % 10 == 0 or step == steps:  # 처음 5개, 10의 배수, 마지막
                        print(f"   [Step {step}] 간섭 체크 중...")
            
            # 간섭 없는 위치를 못 찾았으면 원위치로
            if not found_position:
                print(f"   [위치 유지] 간섭 없는 위치를 찾지 못해 원래 위치 유지")
                # 이미 원위치에 있으므로 A1만 원래 상태로 유지
                if found_A1:
                    stretch_line(found_A1, AP2, original_AP1)
                final_position = ST
        else:
            # A1이 이미 3.8mm 이하면 이동하지 않음
            print(f"   [이동 없음] A1 길이가 이미 3.8mm 이하이므로 위치 유지")
            final_position = ST
        
        # 최종 간섭 체크 (시각화를 위해 BOX 그리기)
        print(f"\n   ========== 최종 위치 확인 ==========")
        check_interference(itno_entities, msp, exclude_entities, draw_all_itno_boxes=True)

    # 간섭 체크에서 생성된 모든 BOX 삭제
    print(f"\n   ========== 간섭 체크 BOX 정리 ==========")
    box_layers = ["ITEMNO_BOX", "INTERFERENCE_ITNO", "INTERFERENCE_TEXT", "INTERFERENCE_LINE"]
    delete_boxes_by_layer(msp, box_layers)
    print(f"   [BOX 정리 완료] 모든 간섭 체크 BOX 삭제")

    # 파일 저장
    save_path = os.path.splitext(file_path)[0] + "_ITPOS.dxf"
    try:
        doc.saveas(save_path)
        print(f"\n[✔] 저장 완료: {os.path.basename(save_path)}")
        print(f"[✔] 처리된 ITNO 수: {len(used_a1_lines)}개")
    except Exception as e:
        print(f"[!] 저장 오류: {e}")


if __name__ == "__main__":
    files = select_files()
    if not files:
        print("❗ DXF 파일을 선택하지 않았습니다.")
    else:
        for f in files:
            process_dxf(f)
        print("▶ 모든 파일 처리 완료.")
