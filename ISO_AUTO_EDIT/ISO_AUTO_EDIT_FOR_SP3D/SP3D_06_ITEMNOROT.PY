import ezdxf
import os
import math
from ezdxf.math import Vec2
from tkinter import Tk, filedialog

# TextBoxLineFinder 클래스 추가
class TextBoxLineFinder:
    """TEXT를 BOX화하여 가장 가까운 LINE을 찾는 유틸리티 클래스"""
    
    def __init__(self):
        pass
    
    @staticmethod
    def get_text_position(text):
        """TEXT 엔티티의 위치를 Vec2로 반환"""
        try:
            # insert 속성 확인
            if hasattr(text.dxf, "insert"):
                ins = text.dxf.insert
                # Vec3 또는 3D 좌표인 경우
                if hasattr(ins, '__getitem__'):
                    return Vec2(float(ins[0]), float(ins[1]))
                # x, y 속성이 있는 경우
                elif hasattr(ins, 'x') and hasattr(ins, 'y'):
                    return Vec2(float(ins.x), float(ins.y))
                # 단일 값인 경우 (거의 없겠지만)
                else:
                    return Vec2(float(ins), 0)
            
            # location 속성 확인 (구버전 호환)
            if hasattr(text.dxf, "location"):
                loc = text.dxf.location
                if hasattr(loc, '__getitem__') and len(loc) >= 2:
                    return Vec2(float(loc[0]), float(loc[1]))
                elif hasattr(loc, 'x') and hasattr(loc, 'y'):
                    return Vec2(float(loc.x), float(loc.y))
                    
        except Exception as e:
            print(f"   [경고] TEXT 위치 가져오기 오류: {e}")
            if hasattr(text, 'dxf') and hasattr(text.dxf, 'text'):
                print(f"   [경고] TEXT 내용: '{text.dxf.text}'")
        
        # 기본값 반환
        return Vec2(0.0, 0.0)
    
    @staticmethod
    def get_text_bbox(text, box_height_offset=0.3):
        """
        TEXT 엔티티의 경계 상자 계산
        
        Args:
            text: TEXT 엔티티
            box_height_offset: BOX 높이 = TEXT 높이 + offset (기본값 0.3mm)
            
        Returns:
            dict: BOX 정보 {'min_x', 'max_x', 'min_y', 'max_y', 'rotation', 'pos'}
        """
        pos = TextBoxLineFinder.get_text_position(text)
        # TEXT 높이 가져오기 (기본값 2.2mm)
        height = getattr(text.dxf, 'height', 2.2)
        # 텍스트 길이를 대략적으로 계산 (문자 수 * 높이 * 0.8)
        text_len = len(text.dxf.text) * height * 0.8
        
        # BOX 높이는 TEXT 높이 + offset
        box_height = height + box_height_offset
        
        # TEXT의 현재 회전 각도 가져오기
        rotation = getattr(text.dxf, 'rotation', 0)
        
        # 회전되지 않은 상태의 BOX (TEXT 원점 기준)
        return {
            'min_x': pos.x,
            'max_x': pos.x + text_len,
            'min_y': pos.y - box_height_offset/2,  # 아래로 offset/2
            'max_y': pos.y + height + box_height_offset/2,  # 위로 height + offset/2
            'rotation': rotation,  # TEXT의 회전 각도 포함
            'pos': pos  # TEXT의 위치 (회전 중심점)
        }
    
    @staticmethod
    def get_text_reference_points(text, num_points=3):
        """
        TEXT BOX의 참조점들을 계산
        
        Args:
            text: TEXT 엔티티
            num_points: 참조점 개수 (기본값 3: 좌측, 중앙, 우측)
            
        Returns:
            list: Vec2 참조점들의 리스트
        """
        bbox = TextBoxLineFinder.get_text_bbox(text)
        pos = bbox['pos']
        
        if num_points == 3:
            # 좌측, 중앙, 우측 점
            left_point = pos  # 왼쪽 기준점 (insert point)
            center_point = Vec2((bbox['min_x'] + bbox['max_x']) / 2, pos.y)  # 중앙점
            right_point = Vec2(bbox['max_x'], pos.y)  # 오른쪽 끝점
            return [left_point, center_point, right_point]
        else:
            # 균등 분할
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
    def find_closest_line_to_text(text, lines, exclude_layers=None, min_length=None, debug=False):
        """
        TEXT에서 가장 가까운 LINE 찾기
        
        Args:
            text: TEXT 엔티티
            lines: 검색할 LINE들의 iterable (예: msp.query('LINE'))
            exclude_layers: 제외할 레이어 이름 리스트 (대소문자 무시)
            min_length: 최소 LINE 길이 (이보다 짧은 LINE은 제외)
            debug: 디버그 출력 여부
            
        Returns:
            tuple: (가장 가까운 LINE, LINE의 가까운 끝점, LINE의 먼 끝점) 또는 (None, None, None)
        """
        if exclude_layers is None:
            exclude_layers = []
        
        # 대문자로 변환하여 비교
        exclude_layers_upper = [layer.upper() for layer in exclude_layers]
        
        # TEXT의 참조점들 계산
        ref_points = TextBoxLineFinder.get_text_reference_points(text)
        
        if debug:
            print(f"\n[TEXT BOX 분석] TEXT: '{text.dxf.text}'")
            for i, pt in enumerate(ref_points):
                print(f"   참조점{i+1}: ({pt.x:.2f}, {pt.y:.2f})")
        
        found_line = None
        closest_point = None
        farthest_point = None
        min_dist = float("inf")
        
        lines_checked = 0
        
        for line in lines:
            # LINE 타입 확인
            if line.dxftype() != 'LINE':
                continue
                
            # 레이어 확인
            if line.dxf.layer.upper() in exclude_layers_upper:
                continue
            
            # 길이 확인
            if min_length is not None:
                line_len = TextBoxLineFinder.get_line_length(line)
                if line_len < min_length:
                    continue
            
            lines_checked += 1
            
            # LINE의 끝점들
            start = Vec2(line.dxf.start.x, line.dxf.start.y)
            end = Vec2(line.dxf.end.x, line.dxf.end.y)
            
            # 모든 참조점에서 LINE의 각 끝점까지 거리 계산
            distances = []
            for ref_point in ref_points:
                distances.append(TextBoxLineFinder.distance(start, ref_point))
                distances.append(TextBoxLineFinder.distance(end, ref_point))
            
            min_pt_dist = min(distances)
            
            if min_pt_dist < min_dist:
                min_dist = min_pt_dist
                found_line = line
                
                # 어느 점이 가장 가까운지 확인
                min_idx = distances.index(min_pt_dist)
                
                # 최소 거리가 LINE의 start점인지 end점인지 확인
                if min_idx % 2 == 0:  # start점이 더 가까움
                    closest_point = start
                    farthest_point = end
                else:  # end점이 더 가까움
                    closest_point = end
                    farthest_point = start
        
        if debug:
            print(f"   검사한 LINE 수: {lines_checked}개")
            if found_line:
                print(f"   가장 가까운 LINE: {found_line.dxf.handle} (거리: {min_dist:.2f}mm)")
                print(f"   가까운 점: ({closest_point.x:.2f}, {closest_point.y:.2f})")
                print(f"   먼 점: ({farthest_point.x:.2f}, {farthest_point.y:.2f})")
            else:
                print(f"   결과: 적합한 LINE을 찾을 수 없음")
        
        return found_line, closest_point, farthest_point
    
    @staticmethod
    def find_closest_line_to_group(entities, lines, exclude_entities=None, exclude_layers=None, min_length=None, debug=False):
        """
        엔티티 그룹 전체의 BOX에서 가장 가까운 LINE 찾기
        
        Args:
            entities: TEXT와 LINE으로 구성된 엔티티 그룹
            lines: 검색할 LINE들의 iterable
            exclude_entities: 제외할 엔티티 리스트
            exclude_layers: 제외할 레이어 이름 리스트
            min_length: 최소 LINE 길이
            debug: 디버그 출력 여부
            
        Returns:
            tuple: (가장 가까운 LINE, LINE의 가까운 끝점, LINE의 먼 끝점) 또는 (None, None, None)
        """
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
            print(f"   참조점 개수: {len(ref_points)}개")
        
        exclude_layers_upper = [layer.upper() for layer in exclude_layers]
        
        found_line = None
        closest_point = None
        farthest_point = None
        min_dist = float("inf")
        
        lines_checked = 0
        
        for line in lines:
            # 제외할 엔티티 확인
            if line in exclude_entities:
                continue
                
            # LINE 타입 확인
            if line.dxftype() != 'LINE':
                continue
                
            # 레이어 확인
            if line.dxf.layer.upper() in exclude_layers_upper:
                continue
            
            # 길이 확인
            if min_length is not None:
                line_len = TextBoxLineFinder.get_line_length(line)
                if line_len < min_length:
                    continue
            
            lines_checked += 1
            
            # LINE의 끝점들
            start = Vec2(line.dxf.start.x, line.dxf.start.y)
            end = Vec2(line.dxf.end.x, line.dxf.end.y)
            
            # 모든 참조점에서 LINE의 각 끝점까지 거리 계산
            distances = []
            for ref_point in ref_points:
                distances.append(TextBoxLineFinder.distance(start, ref_point))
                distances.append(TextBoxLineFinder.distance(end, ref_point))
            
            min_pt_dist = min(distances)
            
            if min_pt_dist < min_dist:
                min_dist = min_pt_dist
                found_line = line
                
                # 어느 점이 가장 가까운지 확인
                min_idx = distances.index(min_pt_dist)
                
                # 최소 거리가 LINE의 start점인지 end점인지 확인
                if min_idx % 2 == 0:  # start점이 더 가까움
                    closest_point = start
                    farthest_point = end
                else:  # end점이 더 가까움
                    closest_point = end
                    farthest_point = start
        
        if debug:
            print(f"   검사한 LINE 수: {lines_checked}개")
            if found_line:
                print(f"   가장 가까운 LINE: {found_line.dxf.handle} (거리: {min_dist:.2f}mm)")
                print(f"   가까운 점: ({closest_point.x:.2f}, {closest_point.y:.2f})")
                print(f"   먼 점: ({farthest_point.x:.2f}, {farthest_point.y:.2f})")
            else:
                print(f"   결과: 적합한 LINE을 찾을 수 없음")
        
        return found_line, closest_point, farthest_point

# TextBoxLineFinder 클래스는 위에 포함됨

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

def get_line_midpoint(line):
    try:
        start = line.dxf.start
        end = line.dxf.end
        return Vec2((start.x + end.x) / 2, (start.y + end.y) / 2)
    except:
        return Vec2(0, 0)

def get_text_position(text):
    """TEXT 엔티티의 위치를 Vec2로 반환 - TextBoxLineFinder 메서드 호출"""
    return TextBoxLineFinder.get_text_position(text)

def rotate_point(pt, center, angle_deg):
    angle_rad = math.radians(angle_deg)
    dx, dy = pt.x - center.x, pt.y - center.y
    cos_a, sin_a = math.cos(angle_rad), math.sin(angle_rad)
    rx = dx * cos_a - dy * sin_a + center.x
    ry = dx * sin_a + dy * cos_a + center.y
    return Vec2(rx, ry)

def move_point(pt, offset):
    return Vec2(pt.x + offset.x, pt.y + offset.y)

def rotate_entity_around(entity, center, angle_deg):
    try:
        t = entity.dxftype()
        if t == "TEXT":
            pos = get_text_position(entity)
            rpos = rotate_point(pos, center, angle_deg)
            entity.dxf.insert = (rpos.x, rpos.y, 0)
            
            # 회전 각도 설정
            orig_angle = getattr(entity.dxf, 'rotation', 0)
            new_angle = (orig_angle + angle_deg) % 360
            entity.dxf.rotation = new_angle
            
            # 디버깅: 회전 결과 확인
            actual_rotation = getattr(entity.dxf, 'rotation', -999)
            print(f"     [회전 적용] TEXT '{entity.dxf.text}': {orig_angle:.1f}° → {new_angle:.1f}° (실제: {actual_rotation:.1f}°)")
            
        elif t == "LINE":
            a = Vec2(entity.dxf.start.x, entity.dxf.start.y)
            b = Vec2(entity.dxf.end.x, entity.dxf.end.y)
            ra = rotate_point(a, center, angle_deg)
            rb = rotate_point(b, center, angle_deg)
            entity.dxf.start = (ra.x, ra.y, 0)
            entity.dxf.end = (rb.x, rb.y, 0)
    except Exception as e:
        print(f"▶ 회전 오류: {entity} / {e}")

def move_entity(entity, offset):
    try:
        t = entity.dxftype()
        if t == "TEXT":
            pos = get_text_position(entity)
            npos = move_point(pos, offset)
            entity.dxf.insert = (npos.x, npos.y, 0)
        elif t == "LINE":
            a = Vec2(entity.dxf.start.x, entity.dxf.start.y)
            b = Vec2(entity.dxf.end.x, entity.dxf.end.y)
            na = move_point(a, offset)
            nb = move_point(b, offset)
            entity.dxf.start = (na.x, na.y, 0)
            entity.dxf.end = (nb.x, nb.y, 0)
    except Exception as e:
        print(f"▶ 이동 오류: {entity} / {e}")

def calc_angle_deg(pt1, pt2):
    dx = pt2.x - pt1.x
    dy = pt2.y - pt1.y
    return math.degrees(math.atan2(dy, dx))

def get_perpendicular_offset(angle_deg, length):
    angle_rad = math.radians(angle_deg + 90)
    return Vec2(math.cos(angle_rad) * length, math.sin(angle_rad) * length)

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

def get_line_center(line):
    """LINE 엔티티의 중심점 계산"""
    if line.dxftype() == "LINE":
        start = Vec2(line.dxf.start.x, line.dxf.start.y)
        end = Vec2(line.dxf.end.x, line.dxf.end.y)
        return Vec2((start.x + end.x) / 2, (start.y + end.y) / 2)
    return None

def get_line_angle(line):
    """LINE의 기울기(각도) 계산"""
    if line.dxftype() == "LINE":
        start = Vec2(line.dxf.start.x, line.dxf.start.y)
        end = Vec2(line.dxf.end.x, line.dxf.end.y)
        return calc_angle_deg(start, end)
    return 0

def check_line_passes_near_point(line, point, threshold=2.0):
    """LINE이 점 근처를 지나는지 확인"""
    if line.dxftype() == "LINE":
        start = Vec2(line.dxf.start.x, line.dxf.start.y)
        end = Vec2(line.dxf.end.x, line.dxf.end.y)
        # 점에서 선분까지의 최단거리 계산
        line_vec = Vec2(end.x - start.x, end.y - start.y)
        line_len = math.sqrt(line_vec.x**2 + line_vec.y**2)
        if line_len == 0:
            return distance(point, start) <= threshold
        
        t = max(0, min(1, ((point.x - start.x) * line_vec.x + (point.y - start.y) * line_vec.y) / (line_len**2)))
        closest_point = Vec2(start.x + t * line_vec.x, start.y + t * line_vec.y)
        return distance(point, closest_point) <= threshold
    return False

def get_line_length(line):
    """LINE의 길이 계산"""
    if line.dxftype() == "LINE":
        start = Vec2(line.dxf.start.x, line.dxf.start.y)
        end = Vec2(line.dxf.end.x, line.dxf.end.y)
        return distance(start, end)
    return 0

def set_mirrtext_zero(doc):
    try:
        doc.header['$MIRRTEXT'] = 0
        print("   [MIRRTEXT=0] 설정 완료")
    except Exception as e:
        print(f"▶ MIRRTEXT=0 설정 오류: {e}")

def get_text_bbox(text):
    """TEXT 엔티티의 경계 상자 계산 - TextBoxLineFinder 메서드 호출"""
    return TextBoxLineFinder.get_text_bbox(text)

def get_rotated_bbox_bounds(bbox):
    """회전된 BOX의 실제 경계 좌표 계산"""
    # bbox가 dictionary인지 확인
    if not isinstance(bbox, dict):
        print(f"   [경고] bbox가 dictionary가 아닙니다: {type(bbox)}")
        return {'min_x': 0, 'max_x': 0, 'min_y': 0, 'max_y': 0}
    
    # 필수 키 확인
    if 'min_x' not in bbox or 'max_x' not in bbox or 'min_y' not in bbox or 'max_y' not in bbox:
        print(f"   [경고] bbox에 필수 키가 없습니다: {bbox.keys()}")
        return {'min_x': 0, 'max_x': 0, 'min_y': 0, 'max_y': 0}
    
    # TEXT의 insert point (회전 중심점)
    pos = bbox.get('pos')
    if not pos:
        # pos가 없으면 bbox의 좌하단을 기준점으로 사용
        pos = Vec2(bbox['min_x'], bbox['min_y'])
    
    # 회전되지 않은 상태의 4개 모서리 (insert point 기준 상대 좌표)
    corners = [
        (bbox['min_x'] - pos.x, bbox['min_y'] - pos.y),
        (bbox['max_x'] - pos.x, bbox['min_y'] - pos.y),
        (bbox['max_x'] - pos.x, bbox['max_y'] - pos.y),
        (bbox['min_x'] - pos.x, bbox['max_y'] - pos.y)
    ]
    
    # 회전 적용
    rotation = bbox.get('rotation', 0)
    if abs(rotation) > 0.01:  # 0도가 아닌 경우만 회전
        rotation_rad = math.radians(rotation)
        cos_r = math.cos(rotation_rad)
        sin_r = math.sin(rotation_rad)
        
        rotated_corners = []
        for dx, dy in corners:
            # 회전 변환
            rx = dx * cos_r - dy * sin_r
            ry = dx * sin_r + dy * cos_r
            # 원래 위치로 이동
            rotated_corners.append((rx + pos.x, ry + pos.y))
    else:
        # 회전이 없으면 원래 좌표 사용
        rotated_corners = [(x + pos.x, y + pos.y) for x, y in corners]
    
    # 회전된 BOX의 실제 min/max 좌표
    x_coords = [c[0] for c in rotated_corners]
    y_coords = [c[1] for c in rotated_corners]
    
    return {
        'min_x': min(x_coords),
        'max_x': max(x_coords),
        'min_y': min(y_coords),
        'max_y': max(y_coords)
    }

def check_bbox_overlap(bbox1, bbox2, threshold=0.5):
    """두 경계 상자가 겹치는지 확인 (회전 고려)"""
    # bbox가 dictionary인지 확인
    if not isinstance(bbox1, dict) or not isinstance(bbox2, dict):
        return False
        
    # 필수 키가 있는지 확인
    required_keys = ['min_x', 'max_x', 'min_y', 'max_y']
    for key in required_keys:
        if key not in bbox1 or key not in bbox2:
            return False
    
    # 회전된 BOX의 실제 경계 계산
    bounds1 = get_rotated_bbox_bounds(bbox1)
    bounds2 = get_rotated_bbox_bounds(bbox2)
    
    # 각 방향의 간격 계산
    x_gap = max(bounds1['min_x'] - bounds2['max_x'], bounds2['min_x'] - bounds1['max_x'])
    y_gap = max(bounds1['min_y'] - bounds2['max_y'], bounds2['min_y'] - bounds1['max_y'])
    
    # 실제 겹침이 있는지 확인 (gap이 0보다 작으면 겹침)
    if x_gap < 0 and y_gap < 0:
        # 실제 겹침 영역 계산
        overlap_x = min(bounds1['max_x'], bounds2['max_x']) - max(bounds1['min_x'], bounds2['min_x'])
        overlap_y = min(bounds1['max_y'], bounds2['max_y']) - max(bounds1['min_y'], bounds2['min_y'])
        
        # 겹침 영역이 threshold보다 큰 경우만 간섭으로 판단
        overlap = (overlap_x > threshold and overlap_y > threshold)
        
        if overlap:
            print(f"        겹침 영역: X방향 {overlap_x:.2f}mm, Y방향 {overlap_y:.2f}mm")
            print(f"        간격: X_gap={x_gap:.2f}mm, Y_gap={y_gap:.2f}mm (threshold={threshold}mm)")
        
        return overlap
    else:
        # gap이 양수면 겹치지 않음
        return False

def draw_bbox(msp, bbox, layer_name, color):
    """BOX를 도면에 그리기 (회전된 BOX를 4개의 LINE으로 구성)"""
    # TEXT의 insert point (회전 중심점)
    pos = bbox.get('pos')
    if not pos:
        pos = Vec2(bbox['min_x'], bbox['min_y'])
    
    # 회전되지 않은 상태의 4개 모서리
    corners = [
        Vec2(bbox['min_x'], bbox['min_y']),
        Vec2(bbox['max_x'], bbox['min_y']),
        Vec2(bbox['max_x'], bbox['max_y']),
        Vec2(bbox['min_x'], bbox['max_y'])
    ]
    
    # 회전 적용
    rotation = bbox.get('rotation', 0)
    if abs(rotation) > 0.01:  # 0도가 아닌 경우만 회전
        rotated_corners = []
        for corner in corners:
            rotated = rotate_point(corner, pos, rotation)
            rotated_corners.append(rotated)
        corners = rotated_corners
    
    # 4개의 LINE 그리기
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
        print(f"   [BOX 삭제] {len(entities_to_delete)}개 BOX LINE 삭제 (레이어: {', '.join(layer_names)})")

def check_interference(itno_entities, msp, exclude_entities, threshold=0.5, draw_all_itno_boxes=True):
    """ITEMNO 그룹이 다른 TEXT와 간섭하는지 BOX 기준으로 확인하고 BOX 그리기"""
    # ITEMNO 그룹의 각 TEXT 개별 BOX 수집 (항상 새로 계산)
    itno_text_boxes = []
    itno_text_list = []
    itno_text_entities = []
    
    for ent in itno_entities:
        if ent.dxftype() == "TEXT":
            # TEXT 속성 디버깅
            text_content = ent.dxf.text
            actual_rotation = getattr(ent.dxf, 'rotation', -999)
            print(f"   [TEXT 속성] '{text_content}' - rotation 속성: {actual_rotation:.1f}°")
            
            # bbox 계산 (회전 정보 포함)
            bbox = get_text_bbox(ent)  # 현재 위치/회전 상태로 bbox 계산
            print(f"   [bbox 계산 후] '{text_content}' bbox rotation: {bbox.get('rotation', -999):.1f}°")
            
            itno_text_boxes.append(bbox)
            itno_text_list.append(ent.dxf.text)
            itno_text_entities.append(ent)
    
    print(f"\n   [간섭 체크 시작]")
    print(f"   - ITEMNO 텍스트: {', '.join(itno_text_list)}")
    
    # 모든 ITEMNO TEXT BOX 그리기 (옵션)
    if draw_all_itno_boxes:
        for i, (text, bbox, ent) in enumerate(zip(itno_text_list, itno_text_boxes, itno_text_entities)):
            draw_bbox(msp, bbox, "ITEMNO_BOX", 6)  # MAGENTA
            rotation = bbox.get('rotation', 0)
            actual_rotation = getattr(ent.dxf, 'rotation', 0)
            print(f"   [BOX 그리기] ITEMNO '{text}' BOX 그림 (MAGENTA, 회전: {rotation:.1f}°)")
    
    # 개별 TEXT BOX 정보 출력
    for i, (text, bbox) in enumerate(zip(itno_text_list, itno_text_boxes)):
        box_height = bbox['max_y'] - bbox['min_y']
        rotation = bbox.get('rotation', 0)
        bounds = get_rotated_bbox_bounds(bbox)
        print(f"   - '{text}' BOX: X({bbox['min_x']:.2f}~{bbox['max_x']:.2f}), Y({bbox['min_y']:.2f}~{bbox['max_y']:.2f}) [높이: {box_height:.2f}mm, 회전: {rotation:.1f}°]")
        if abs(rotation) > 0.01:
            print(f"     실제 영역: X({bounds['min_x']:.2f}~{bounds['max_x']:.2f}), Y({bounds['min_y']:.2f}~{bounds['max_y']:.2f})")
    
    print(f"   - 제외 엔티티 수: {len(exclude_entities)}개")
    print(f"   - Threshold: {threshold}mm")
    
    checked_count = 0
    interfered_texts = []
    interfered_with_itno = []  # 간섭이 발생한 ITEMNO BOX 인덱스
    
    # 다른 TEXT 엔티티와의 간섭 검사
    for text in msp.query('TEXT'):
        if text in itno_entities or text in exclude_entities:
            continue
        
        checked_count += 1
        
        # 상대 TEXT의 경계 상자 계산 (회전 정보 포함)
        text_bbox = get_text_bbox(text)
        
        # ITEMNO의 각 TEXT와 개별적으로 겹침 확인
        for idx, itno_bbox in enumerate(itno_text_boxes):
            if check_bbox_overlap(itno_bbox, text_bbox, threshold):
                # 디버깅: 어떤 ITEMNO BOX와 겹치는지 확인
                print(f"        [간섭 감지] ITEMNO '{itno_text_list[idx]}'와 '{text.dxf.text}' 간섭")
                
                # 중복 추가 방지
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
    
    print(f"   - 검사한 TEXT 수: {checked_count}개")
    
    if interfered_texts:
        print(f"   [간섭 발견] {len(interfered_texts)}개 TEXT와 간섭:")
        
        # 간섭이 발생한 ITEMNO BOX 강조 표시 (CYAN 색상)
        for idx in interfered_with_itno:
            draw_bbox(msp, itno_text_boxes[idx], "INTERFERENCE_ITNO", 4)  # CYAN
            print(f"   [간섭 BOX] ITEMNO '{itno_text_list[idx]}' 간섭 BOX 강조 (CYAN)")
        
        # 간섭된 TEXT BOX 그리기 (RED 색상)
        for i, item in enumerate(interfered_texts):
            box_height = item['bbox']['max_y'] - item['bbox']['min_y']
            rotation = item['bbox'].get('rotation', 0)
            actual_text_rotation = getattr(item['entity'].dxf, 'rotation', 0)
            
            # TEXT 엔티티의 모든 회전 관련 속성 확인
            print(f"     {i+1}. '{item['text']}' (레이어: {item['layer']})")
            print(f"        위치: ({item['pos'].x:.2f}, {item['pos'].y:.2f})")
            print(f"        BOX: X({item['bbox']['min_x']:.2f}~{item['bbox']['max_x']:.2f}), Y({item['bbox']['min_y']:.2f}~{item['bbox']['max_y']:.2f}) [높이: {box_height:.2f}mm, 회전: {rotation:.1f}°]")
            
            # 간섭된 TEXT BOX 그리기
            draw_bbox(msp, item['bbox'], "INTERFERENCE_TEXT", 1)  # RED
            print(f"        [간섭 BOX] 간섭 TEXT BOX 그림 (RED, 회전: {rotation:.1f}°)")
        
        return True
    else:
        print(f"   [간섭 없음] 다른 TEXT와 간섭 없음")
        return False

def process_dxf(file_path):
    try:
        doc = ezdxf.readfile(file_path)
    except Exception as e:
        print(f"파일 열기 실패: {file_path} / {e}")
        return

    msp = doc.modelspace()
    modified = False

    # === 유첨2 방식으로 ITEMNO 찾기 시작 ===
    for st1 in msp.query('TEXT'):
        if '<' not in st1.dxf.text or '>' not in st1.dxf.text:
            continue
        st1_pos = get_text_position(st1)

        # 유첨2 방식: TEXT LINE 동시 검색, 회전 체크 없음
        candidate_st2 = []
        for e in msp.query('TEXT LINE'):
            if e is st1:
                continue
            pos = get_text_position(e) if e.dxftype() == 'TEXT' else get_line_midpoint(e)
            dx = pos.x - st1_pos.x
            dy = abs(pos.y - st1_pos.y)
            if 0 < dx <= 15 and dy <= 5:  # 범위: 0~15mm, Y±5mm
                candidate_st2.append(e)

        text_st2s = [e for e in candidate_st2 if e.dxftype() == 'TEXT' and abs(get_text_position(e).y - st1_pos.y) <= 0.5]
        line_st2s = []
        for e in candidate_st2:
            if e.dxftype() == 'LINE':
                start = e.dxf.start
                end = e.dxf.end
                length = distance(Vec2(start.x, start.y), Vec2(end.x, end.y))
                if 2.8 <= length <= 4.5:  # LINE 길이 조건 확대 (4.4mm 포함)
                   line_st2s.append(e)

        # ITNO 조건: TEXT가 있고 LINE이 최소 4개 이상일 때!
        if not (text_st2s and len(line_st2s) >= 4):
            continue
        
        # LINE 선택 관련 변수 초기화
        original_line_count = len(line_st2s)
        all_original_lines = line_st2s.copy()  # 원본 LINE 리스트 복사
            
        # LINE이 4개 이상이면 < 텍스트에서 가장 가까운 첫 LINE 찾기
        if len(line_st2s) > 4:
            # 각 LINE과 ST1(<포함 텍스트)까지의 최소 거리 계산
            line_distances = []
            for line in line_st2s:
                start = Vec2(line.dxf.start.x, line.dxf.start.y)
                end = Vec2(line.dxf.end.x, line.dxf.end.y)
                # LINE의 두 끝점 중 ST1에 더 가까운 거리
                min_dist = min(distance(start, st1_pos), distance(end, st1_pos))
                line_distances.append((min_dist, line))
            
            # 거리순으로 정렬
            line_distances.sort(key=lambda x: x[0])
            
            # 가장 가까운 첫 LINE 선택
            first_line = line_distances[0][1]
            first_line_start = Vec2(first_line.dxf.start.x, first_line.dxf.start.y)
            first_line_end = Vec2(first_line.dxf.end.x, first_line.dxf.end.y)
            
            # 나머지 LINE들 중에서 첫 LINE에 접하거나 가장 가까운 3개 선택
            remaining_lines = [item[1] for item in line_distances[1:]]
            remaining_distances = []
            
            for line in remaining_lines:
                start = Vec2(line.dxf.start.x, line.dxf.start.y)
                end = Vec2(line.dxf.end.x, line.dxf.end.y)
                # 첫 LINE의 끝점들과의 최소 거리 계산
                min_dist_to_first = min(
                    distance(start, first_line_start),
                    distance(start, first_line_end),
                    distance(end, first_line_start),
                    distance(end, first_line_end)
                )
                remaining_distances.append((min_dist_to_first, line))
            
            # 거리순으로 정렬하여 가장 가까운 3개 선택
            remaining_distances.sort(key=lambda x: x[0])
            selected_lines = [first_line] + [item[1] for item in remaining_distances[:3]]
            
            # 선택되지 않은 LINE들 (나중에 A1 후보가 될 수 있음)
            unselected_lines = [item[1] for item in line_distances[4:]] + [item[1] for item in remaining_distances[3:]]
            
            # line_st2s를 선택된 4개로 재설정
            line_st2s = selected_lines
            print(f"   [LINE 선택] 총 {len(line_distances)}개 LINE 발견")
            print(f"   [LINE 선택] 4개 선택 (ST1에서 가장 가까운 LINE + 그에 가까운 3개)")
            print(f"   [LINE 제외] {len(unselected_lines)}개 LINE은 A1 후보로 남김")
            
            # 선택되지 않은 LINE들의 정보 출력
            for i, line in enumerate(unselected_lines):
                line_len = get_line_length(line)
                print(f"     - 제외된 LINE {i+1}: 길이 {line_len:.2f}mm")
        else:
            # LINE이 정확히 4개인 경우
            print(f"   [LINE 선택] 정확히 4개 LINE 발견 - 모두 사용")
        
        line_group = line_st2s  # 선택된 LINE을 line_group으로 사용
        print(f"   [ITNO 그룹] line_group에 {len(line_group)}개 LINE 포함됨 (원래 {original_line_count}개에서 선택)")
            
        # === ITEMNO 찾기 완료, 이후 유첨1 방식으로 처리 ===
        
        # ITNO 그룹 설정
        st1.dxf.layer = "ITNO"
        text_st2 = text_st2s[0]  # 첫 번째 TEXT를 text_st2로 사용
        text_st2.dxf.layer = "ITNO"
        line_group = line_st2s  # 모든 LINE을 line_group으로 사용
        
        for l in line_group:
            l.dxf.layer = "ITNO"
            
        set_entity_color(st1, 1)
        set_entity_color(text_st2, 1)
        for l in line_group:
            set_entity_color(l, 1)
            
        modified = True
        print(f"\n[ITNO 처리] ITEM: {st1.dxf.text}, 우측: {text_st2.dxf.text}, LINE: {len(line_group)}개")
        
        # 처리 전 회전 상태 확인
        st1_rot_before = getattr(st1.dxf, 'rotation', -999)
        st2_rot_before = getattr(text_st2.dxf, 'rotation', -999)
        print(f"   [처리 전 회전] ST1: {st1_rot_before:.1f}°, ST2: {st2_rot_before:.1f}°")

        # ITNODN (DN 또는 " 포함) TEXT
        text_st2_pos = get_text_position(text_st2)
        itno_dn_text = None
        for e in msp.query('TEXT'):
            if e is st1 or e is text_st2:
                continue
            pos = get_text_position(e)
            dx = abs(pos.x - st1_pos.x)
            dy = st1_pos.y - pos.y
            if dx <= 2.0 and 0 < dy <= 4.0:
                text_upper = e.dxf.text.upper()
                if "DN" in text_upper or '"' in e.dxf.text:
                    itno_dn_text = e
                    break
        if itno_dn_text:
            itno_dn_text.dxf.layer = "ITNODN"
            set_entity_color(itno_dn_text, 1)
            print(f"   [ITNODN 추가] DN 또는 \" 포함 TEXT: '{itno_dn_text.dxf.text}' 포함")

        # 변수 초기화
        found_PLINE = None
        SPOS = None  # 이동 전 위치 저장용
        
        # 1. 가장 가까운 LINE (A1) 찾기 - ITNO 전체 BOX 기준
        print(f"\n   [A1 찾기] ITNO 그룹 전체 BOX에서 가장 가까운 LINE 검색")
        
        # ITNO 그룹 구성 (st1, text_st2, line_group, itno_dn_text)
        itno_group_for_a1 = [st1, text_st2] + line_group
        if itno_dn_text:
            itno_group_for_a1.append(itno_dn_text)
        
        # TextBoxLineFinder를 사용하여 ITNO 전체 BOX에서 가장 가까운 LINE 찾기
        found_A1, AP1, AP2 = TextBoxLineFinder.find_closest_line_to_group(
            entities=itno_group_for_a1,
            lines=msp.query('LINE'),
            exclude_entities=line_group,  # ITNO 그룹의 LINE들 제외
            exclude_layers=['FRAME'],  # FRAME 레이어 제외
            min_length=None,  # 길이 제한 없음
            debug=True
        )
        
        if not found_A1:
            print(f"   [A1 없음] ITNO BOX에서 가장 가까운 LINE을 찾을 수 없습니다")
            continue
            
        found_A1.dxf.layer = "A1"
        set_entity_color(found_A1, 4)  # CYAN = 4
        
        # A1이 원래 candidate LINE 중 하나였는지 확인
        line_len = get_line_length(found_A1)
        was_original_candidate = False
        
        # 원래 찾았던 모든 LINE과 비교
        if 'all_original_lines' in locals() and original_line_count > 4:
            if found_A1 in all_original_lines:
                was_original_candidate = True
                if found_A1 in line_group:
                    print(f"   [A1 확인] 선택된 A1은 ITNO 그룹의 LINE입니다 (오류!)")
                else:
                    print(f"   [A1 확인] 선택된 A1은 원래 {original_line_count}개 중 제외된 LINE입니다 (정상)")
        
        print(f"   [A1] ITNO BOX에서 가장 가까운 LINE {found_A1.dxf.handle} (길이: {line_len:.2f}mm)")
        print(f"   [A1] AP1(가까운점): ({AP1.x:.2f}, {AP1.y:.2f}), AP2(먼점): ({AP2.x:.2f}, {AP2.y:.2f})")
        
        if not was_original_candidate and 'all_original_lines' in locals() and original_line_count > 4:
            print(f"   [A1 주의] 선택된 A1은 원래 찾았던 {original_line_count}개 LINE이 아닌 다른 LINE입니다")

        # 추가 A1 LINE들을 저장할 리스트 초기화
        additional_a1_lines = []
        
        # DEL1: A1 끝에서 2mm 접하는 2mm 이하 LINE 3개 찾기
        del1_lines = []
        
        # DEL1 찾기 시도 (최대 10번 반복)
        for attempt in range(10):
            del1_lines = []
            
            if found_A1:
                # 현재 A1과 추가 LINE들의 끝점 수집
                all_endpoints = []
                
                # 원래 A1의 끝점들
                a1_start = Vec2(found_A1.dxf.start.x, found_A1.dxf.start.y)
                a1_end = Vec2(found_A1.dxf.end.x, found_A1.dxf.end.y)
                all_endpoints.extend([a1_start, a1_end])
                
                # 추가 LINE들의 끝점들
                for add_line in additional_a1_lines:
                    add_start = Vec2(add_line.dxf.start.x, add_line.dxf.start.y)
                    add_end = Vec2(add_line.dxf.end.x, add_line.dxf.end.y)
                    all_endpoints.extend([add_start, add_end])
                
                # 모든 끝점에서 DEL1 찾기
                for line in msp.query('LINE'):
                    if line is found_A1 or line in line_group:
                        continue
                    if line in additional_a1_lines:
                        continue
                    if line in del1_lines:  # 이미 DEL1에 포함된 경우 제외
                        continue
                        
                    # FRAME 레이어 제외
                    if line.dxf.layer.upper() == "FRAME":
                        continue
                        
                    line_len = get_line_length(line)
                    if line_len > 2.0:
                        continue
                    
                    start = Vec2(line.dxf.start.x, line.dxf.start.y)
                    end = Vec2(line.dxf.end.x, line.dxf.end.y)
                    
                    # 모든 A1 끝점들과의 거리 확인
                    for endpoint in all_endpoints:
                        if (distance(start, endpoint) <= 2.0 or distance(end, endpoint) <= 2.0):
                            del1_lines.append(line)
                            break
                    
                    if len(del1_lines) >= 3:
                        break
                
                # DEL1을 찾았으면 종료
                if del1_lines:
                    print(f"   [DEL1 찾기] {attempt+1}차 시도에서 {len(del1_lines)}개 발견")
                    break
                
                # DEL1을 못 찾았으면 A1 끝점에서 0.2mm 범위 내 LINE 찾기
                print(f"   [DEL1 없음] {attempt+1}차 시도 - A1 끝점 0.2mm 범위 내 LINE 검색")
                
                # 디버깅: 검색 대상 끝점들 출력
                print(f"   [검색 끝점] 총 {len(all_endpoints)}개 끝점에서 검색:")
                for i, ep in enumerate(all_endpoints):
                    print(f"     끝점{i+1}: ({ep.x:.3f}, {ep.y:.3f})")
                
                found_additional = False
                candidates_checked = 0
                
                for line in msp.query('LINE'):
                    if line is found_A1 or line in line_group:
                        continue
                    if line in additional_a1_lines:
                        continue
                    if line.dxf.layer.upper() == "FRAME":
                        continue
                    
                    candidates_checked += 1
                    start = Vec2(line.dxf.start.x, line.dxf.start.y)
                    end = Vec2(line.dxf.end.x, line.dxf.end.y)
                    
                    # 모든 A1 끝점에서 0.3mm 범위 내 점 확인 (여유 증가)
                    for endpoint in all_endpoints:
                        dist_to_start = distance(start, endpoint)
                        dist_to_end = distance(end, endpoint)
                        
                        if dist_to_start <= 0.3:  # 0.2 -> 0.3으로 증가
                            additional_a1_lines.append(line)
                            # 새로운 AP2 설정 (연결되지 않은 끝점)
                            AP2 = end
                            print(f"   [A1 확장] LINE {line.dxf.handle} 추가 (시작점 거리: {dist_to_start:.3f}mm)")
                            print(f"   [A1 확장] 새 AP2: ({AP2.x:.2f}, {AP2.y:.2f})")
                            found_additional = True
                            break
                        elif dist_to_end <= 0.3:  # 0.2 -> 0.3으로 증가
                            additional_a1_lines.append(line)
                            # 새로운 AP2 설정 (연결되지 않은 끝점)
                            AP2 = start
                            print(f"   [A1 확장] LINE {line.dxf.handle} 추가 (끝점 거리: {dist_to_end:.3f}mm)")
                            print(f"   [A1 확장] 새 AP2: ({AP2.x:.2f}, {AP2.y:.2f})")
                            found_additional = True
                            break
                    
                    if found_additional:
                        break
                
                print(f"   [A1 검색 결과] {candidates_checked}개 LINE 검사")
                
                if not found_additional:
                    print(f"   [DEL1 검색 종료] 더 이상 연결된 LINE을 찾을 수 없습니다.")
                    break
        
        # DEL1 검색 결과 최종 확인
        if not del1_lines:
            print(f"   [DEL1 없음] DEL1을 찾지 못했습니다.")
            
            # ==== 수정된 부분: DEL1을 찾지 못한 경우에만 ISOTEXT 레이어 LINE 추가 ====
            print(f"   [ISOTEXT 검색] DEL1을 찾지 못하여 ISOTEXT 레이어 LINE을 검색합니다.")
            
            # A1에 추가: AP2 끝에서 가장 가까운 2mm 이상의 ISOTEXT 레이어 LINE 1개
            isotext_line = None
            min_isotext_dist = float("inf")
            
            for line in msp.query('LINE'):
                if line is found_A1 or line in line_group:
                    continue
                
                # ISOTEXT 레이어만 대상
                if line.dxf.layer.upper() != "ISOTEXT":
                    continue
                
                # 길이가 2mm 이상인 LINE만
                line_len = get_line_length(line)
                if line_len < 2.0:
                    continue
                
                # AP2에서 각 끝점까지의 거리 계산
                start = Vec2(line.dxf.start.x, line.dxf.start.y)
                end = Vec2(line.dxf.end.x, line.dxf.end.y)
                dist_to_start = distance(AP2, start)
                dist_to_end = distance(AP2, end)
                min_dist_to_ap2 = min(dist_to_start, dist_to_end)
                
                if min_dist_to_ap2 < min_isotext_dist:
                    min_isotext_dist = min_dist_to_ap2
                    isotext_line = line
            
            # ISOTEXT LINE을 찾았으면 A1 그룹에 추가
            if isotext_line:
                isotext_line.dxf.layer = "A1"
                set_entity_color(isotext_line, 4)  # CYAN = 4
                additional_a1_lines.append(isotext_line)
                
                # 새로운 AP2 설정 (ISOTEXT LINE의 AP2에서 먼 끝점)
                start = Vec2(isotext_line.dxf.start.x, isotext_line.dxf.start.y)
                end = Vec2(isotext_line.dxf.end.x, isotext_line.dxf.end.y)
                if distance(AP2, start) < distance(AP2, end):
                    AP2 = end  # end가 더 멀면 end를 새 AP2로
                else:
                    AP2 = start  # start가 더 멀면 start를 새 AP2로
                
                line_len = get_line_length(isotext_line)
                print(f"   [A1 추가] ISOTEXT LINE {isotext_line.dxf.handle} 추가 (길이={line_len:.2f}mm, AP2에서 거리={min_isotext_dist:.2f}mm)")
                print(f"   [A1 추가] 새로운 AP2: ({AP2.x:.2f}, {AP2.y:.2f})")
                
                # ISOTEXT를 추가한 후 DEL1 재검색
                print(f"   [DEL1 재검색] ISOTEXT 추가 후 DEL1을 다시 검색합니다.")
                
                # 모든 A1 끝점 재수집
                all_endpoints = []
                all_endpoints.extend([Vec2(found_A1.dxf.start.x, found_A1.dxf.start.y), 
                                    Vec2(found_A1.dxf.end.x, found_A1.dxf.end.y)])
                
                for add_line in additional_a1_lines:
                    all_endpoints.extend([Vec2(add_line.dxf.start.x, add_line.dxf.start.y),
                                        Vec2(add_line.dxf.end.x, add_line.dxf.end.y)])
                
                # DEL1 재검색
                for line in msp.query('LINE'):
                    if line is found_A1 or line in line_group:
                        continue
                    if line in additional_a1_lines:
                        continue
                    if line in del1_lines:
                        continue
                        
                    if line.dxf.layer.upper() == "FRAME":
                        continue
                        
                    line_len = get_line_length(line)
                    if line_len > 2.0:
                        continue
                    
                    start = Vec2(line.dxf.start.x, line.dxf.start.y)
                    end = Vec2(line.dxf.end.x, line.dxf.end.y)
                    
                    for endpoint in all_endpoints:
                        if (distance(start, endpoint) <= 2.0 or distance(end, endpoint) <= 2.0):
                            del1_lines.append(line)
                            break
                    
                    if len(del1_lines) >= 3:
                        break
                
                if del1_lines:
                    print(f"   [DEL1 재검색 성공] {len(del1_lines)}개 DEL1 발견")
                else:
                    print(f"   [DEL1 재검색 실패] 여전히 DEL1을 찾지 못했습니다.")
            else:
                print(f"   [ISOTEXT 없음] AP2에서 가장 가까운 2mm 이상의 ISOTEXT 레이어를 찾을 수 없습니다.")
            
            print(f"   [작업 계속 진행] DEL1 없이 작업을 계속 진행합니다.")
        
        # AP2가 변경되었을 수 있으므로 PLINE 재검색이 필요한 경우

        # 2. PLINE 찾기 (AP2에서 2mm 이내를 지나는 PIPE 텍스트 포함 레이어)
        found_PLINE = None
        min_pline_dist = float("inf")
        pipe_too_short = False  # PIPE 길이 체크용 변수 초기화
        
        for line in msp.query('LINE'):
            if line is found_A1 or line in line_group:
                continue
            
            # 레이어에 PIPE 텍스트 포함 확인
            if "PIPE" not in line.dxf.layer.upper():
                continue
            
            # 길이가 1.8mm 이하인 LINE 제외
            if get_line_length(line) <= 1.8:
                continue
                
            # AP2에서 2mm 이내를 지나는지 확인
            if check_line_passes_near_point(line, AP2, 2.0):
                # 중심점과 AP2의 거리로 우선순위 결정
                center = get_line_center(line)
                if center:
                    dist = distance(center, AP2)
                    if dist < min_pline_dist:
                        min_pline_dist = dist
                        found_PLINE = line

        if not found_PLINE:
            print(f"   [PLINE 없음] AP2에서 2mm 이내를 지나는 PIPE 포함 레이어(1.8mm 초과)를 찾을 수 없습니다.")
            continue
        else:
            line_len = get_line_length(found_PLINE)
            print(f"   [PLINE] PIPE 포함 레이어 발견: {found_PLINE.dxf.handle} ({found_PLINE.dxf.layer} 레이어, 길이={line_len:.2f}mm)")
            
            # PIPE 길이가 10mm 이하면 회전까지만 수행
            pipe_too_short = line_len <= 10.0
            if pipe_too_short:
                print(f"   [PIPE 짧음] PIPE 길이가 10mm 이하({line_len:.2f}mm)이지만 모든 작업을 수행합니다.")

        # PPOS 계산
        ppos = get_line_center(found_PLINE)
        if not ppos:
            print(f"   [PPOS 오류] PLINE 중심점 계산 실패. 처리 건너뜁니다.")
            continue
        print(f"   [PPOS] PLINE 중심점: ({ppos.x:.2f}, {ppos.y:.2f})")
        
        # PLINE 기울기 계산
        pline_angle = get_line_angle(found_PLINE)
        print(f"   [PLINE 기울기] {pline_angle:.2f}° (수평=0°, 수직위=90°, 수직아래=-90°)")

        # 3. AD1 찾기 (AP2에서 가장 가까운 짧은 LINE, 길이 5mm 이하)
        found_AD1 = None
        min_ad1_dist = float("inf")
        
        for line in msp.query('LINE'):
            if line is found_A1 or line is found_PLINE or line in line_group:
                continue
            
            # 길이 계산
            line_len = get_line_length(line)
            if line_len > 5:
                continue
                
            # AP2에서 가장 가까운 점까지의 거리
            start = Vec2(line.dxf.start.x, line.dxf.start.y)
            end = Vec2(line.dxf.end.x, line.dxf.end.y)
            min_dist_to_ap2 = min(distance(start, AP2), distance(end, AP2))
            
            if min_dist_to_ap2 < min_ad1_dist:
                min_ad1_dist = min_dist_to_ap2
                found_AD1 = line
        
        if found_AD1:
            found_AD1.dxf.layer = "AD1"
            set_entity_color(found_AD1, 3)  # GREEN = 3
            line_len = get_line_length(found_AD1)
            print(f"   [AD1] 짧은 LINE 발견: {found_AD1.dxf.handle}, 길이={line_len:.2f}mm, AP2에서 거리={min_ad1_dist:.2f}mm")
        else:
            print(f"   [AD1 없음] 조건에 맞는 짧은 LINE을 찾을 수 없습니다.")

        # 추가된 A1 LINE들도 A1 레이어로 설정
        for add_line in additional_a1_lines:
            add_line.dxf.layer = "A1"
            set_entity_color(add_line, 4)  # CYAN = 4
            print(f"   [A1 추가] 확장된 LINE {add_line.dxf.handle} (CYAN 색상)")
            
        # DEL1 레이어 설정
        for i, line in enumerate(del1_lines):
            line.dxf.layer = "DEL1"
            set_entity_color(line, 5)  # BLUE = 5
            print(f"   [DEL1-{i+1}] A1 근처 2mm 이하 LINE: {line.dxf.handle} (FRAME 제외)")

        # 4. ITEMNO 그룹 이동 및 회전
        # ITNO 그룹 구성
        itno_entities = [st1, text_st2] + line_group
        if itno_dn_text:
            itno_entities.append(itno_dn_text)

        # 원본 위치에서 간섭 체크를 위한 제외 목록
        exclude_entities = [st1, text_st2, itno_dn_text] if itno_dn_text else [st1, text_st2]
        print(f"\n   [제외 엔티티] 간섭 체크에서 제외할 원본 TEXT:")
        for ent in exclude_entities:
            if ent and ent.dxftype() == "TEXT":
                print(f"   - '{ent.dxf.text}' (원본 위치)")

        print("\n   ========== ITEMNO 변환 상세 정보 ==========")
        
        # 이동 전 ITEMNO 중심점 (SPOS)
        itno_center_before = get_entity_center(itno_entities)
        SPOS = Vec2(itno_center_before.x, itno_center_before.y)  # SPOS 저장
        print(f"   [이동 전] ITEMNO 중심점 (SPOS): ({SPOS.x:.2f}, {SPOS.y:.2f})")
        
        # 1. ITEMNO 중심을 PPOS로 이동
        itno_to_ppos_offset = Vec2(ppos.x - itno_center_before.x, ppos.y - itno_center_before.y)
        move_distance = math.sqrt(itno_to_ppos_offset.x**2 + itno_to_ppos_offset.y**2)
        print(f"   [이동1] ITEMNO중심→PPOS 오프셋: ({itno_to_ppos_offset.x:.2f}, {itno_to_ppos_offset.y:.2f})")
        print(f"   [이동1] 이동 거리: {move_distance:.2f}mm")
        
        for ent in itno_entities:
            move_entity(ent, itno_to_ppos_offset)
        print(f"   [이동1 실행] ITEMNO 중심을 PPOS로 이동 완료")
        
        # 2. PPOS 중심으로 PLINE 기울기만큼 회전
        for ent in itno_entities:
            rotate_entity_around(ent, ppos, pline_angle)
        print(f"   [회전 실행] PPOS 중심으로 {pline_angle:.2f}° 회전 완료")
        
        # 회전 후 상태 확인
        if st1.dxftype() == "TEXT":
            st1_rot_after = getattr(st1.dxf, 'rotation', -999)
            st2_rot_after = getattr(text_st2.dxf, 'rotation', -999)
            print(f"   [회전 후 확인] ST1: {st1_rot_after:.1f}°, ST2: {st2_rot_after:.1f}°")

        # 3. PLINE 수직 방향으로 이동 (DN/" 포함 여부에 따라 거리 조정)
        perp_angle = pline_angle + 90
        move_distance_perp = 1.65 if itno_dn_text else 2.5
        perp_offset = get_perpendicular_offset(pline_angle, move_distance_perp)
        print(f"   [이동2] PLINE 수직 방향: {perp_angle:.2f}°")
        print(f"   [이동2] 수직 이동 거리: {move_distance_perp}mm (DN/\" {'포함' if itno_dn_text else '미포함'})")
        print(f"   [이동2] 수직 이동 벡터: ({perp_offset.x:.2f}, {perp_offset.y:.2f})")
        
        for ent in itno_entities:
            move_entity(ent, perp_offset)
        print(f"   [이동2 실행] PLINE 수직 방향으로 {move_distance_perp}mm 이동 완료")
        
        # 최종 위치 확인
        itno_center_final = get_entity_center(itno_entities)
        print(f"   [최종 위치] ITEMNO 중심점: ({itno_center_final.x:.2f}, {itno_center_final.y:.2f})")
        print("   ==========================================\n")

        # 5. 각도 보정 및 텍스트 순서 보정
        # 5-1. PLINE 각도가 -89도 이하일 때 180도 회전
        if pline_angle <= -89:
            set_mirrtext_zero(doc)
            print(f"\n   [각도 보정] PLINE 각도가 {pline_angle:.2f}° (≤-89°)이므로 PPOS 중심으로 180도 회전")
            for ent in itno_entities:
                rotate_entity_around(ent, ppos, 180)
            print("   [각도 보정] 180도 회전 완료, MIRRTEXT=0 설정")

        # 5-2. ST1.x > ST2.x일 때 180도 회전 후 PLINE 직교 방향 -6mm 이동
        st1_pos_current = get_text_position(st1)
        st2_pos_current = get_text_position(text_st2)
        
        if st1_pos_current.x > st2_pos_current.x:
            set_mirrtext_zero(doc)
            print(f"\n   [텍스트 순서 보정] <...> 텍스트가 숫자보다 오른쪽에 있음")
            print(f"   [텍스트 순서 보정] ST1 X: {st1_pos_current.x:.2f} > ST2 X: {st2_pos_current.x:.2f}")
            
            # ITEMNO 그룹 중심점 계산
            itno_center_before_correction = get_entity_center(itno_entities)
            
            # 180도 회전 (중심점 기준)
            for ent in itno_entities:
                rotate_entity_around(ent, itno_center_before_correction, 180)
            print(f"   [텍스트 순서 보정] 중심점({itno_center_before_correction.x:.2f}, {itno_center_before_correction.y:.2f}) 기준 180도 회전 완료")
            
            # PLINE 직교 방향으로 -6mm 이동
            perp_offset_correction = get_perpendicular_offset(pline_angle, -6)
            for ent in itno_entities:
                move_entity(ent, perp_offset_correction)
            print(f"   [텍스트 순서 보정] PLINE 직교 방향으로 -6mm 추가 이동 완료")
            print(f"   [텍스트 순서 보정] 이동 벡터: ({perp_offset_correction.x:.2f}, {perp_offset_correction.y:.2f})")

        # 6. 간섭 체크 및 추가 이동
        print(f"\n   ========== 이동/회전 후 간섭 체크 ==========")
        if check_interference(itno_entities, msp, exclude_entities):
            print(f"\n   [간섭 처리] 간섭이 감지되어 PIPE 반대편으로 이동합니다")
            
            # ITEMNO 현재 위치
            current_itno_center = get_entity_center(itno_entities)
            
            # PLINE(PIPE) 위치  
            pline_center = get_line_center(found_PLINE)
            
            # PIPE에서 ITEMNO 방향의 벡터 (현재 위치 유지 방향)
            from_pipe_vector = Vec2(current_itno_center.x - pline_center.x,
                                   current_itno_center.y - pline_center.y)
            
            # PIPE를 기준으로 반대편으로 이동
            # 현재 벡터의 반대 방향으로 같은 거리만큼 이동
            vector_length = math.sqrt(from_pipe_vector.x**2 + from_pipe_vector.y**2)
            
            if vector_length > 0:
                # 반대편 = -2 * 현재벡터 (PIPE 중심 기준 대칭 이동)
                interference_offset = Vec2(
                    -2 * from_pipe_vector.x,
                    -2 * from_pipe_vector.y
                )
            else:
                # 만약 중심이 겹치면 직교 방향으로 이동
                # DN 텍스트 여부에 따라 거리 결정
                fallback_distance = 1.65 if itno_dn_text else 2.5
                interference_offset = get_perpendicular_offset(pline_angle, fallback_distance * 2)
            
            for ent in itno_entities:
                move_entity(ent, interference_offset)
            
            print(f"   [간섭 회피] PIPE를 중심으로 반대편으로 이동")
            print(f"   [간섭 회피] 이동 벡터: ({interference_offset.x:.2f}, {interference_offset.y:.2f})")
            
            # 최종 위치 재확인
            itno_center_after_interference = get_entity_center(itno_entities)
            final_distance = distance(itno_center_after_interference, pline_center)
            print(f"   [간섭 회피 후] ITEMNO 최종 중심점: ({itno_center_after_interference.x:.2f}, {itno_center_after_interference.y:.2f})")
            print(f"   [간섭 회피 후] PIPE에서의 거리: {final_distance:.2f}mm")
            
            # 이동 후 재검사 (두 번째 간섭 체크이므로 모든 ITEMNO BOX 그리지 않음)
            print(f"\n   ========== 간섭 회피 후 재검사 ==========")
            if check_interference(itno_entities, msp, exclude_entities, draw_all_itno_boxes=False):
                print(f"   [경고] 반대편에도 간섭이 존재합니다!")
            else:
                print(f"   [성공] 반대편에는 간섭이 없습니다")
        else:
            print(f"   [간섭 없음] 이동/회전 후 간섭이 없습니다")

        # 7. A1, AD1, DEL1 삭제 또는 PIPE 짧음 처리
        if pipe_too_short:
            # PIPE가 짧으면 삭제하지 않고 원래 위치로 되돌림
            print(f"\n   [PIPE 짧음 처리] PIPE 길이가 10mm 이하이므로 ITNO를 원래 위치로 되돌립니다.")
            
            # 현재 ITEMNO 중심점 (FPOS)
            itno_center_final = get_entity_center(itno_entities)
            FPOS = Vec2(itno_center_final.x, itno_center_final.y)
            print(f"   [최종 위치] ITEMNO 중심점 (FPOS): ({FPOS.x:.2f}, {FPOS.y:.2f})")
            
            # FPOS에서 SPOS로 이동
            restore_offset = Vec2(SPOS.x - FPOS.x, SPOS.y - FPOS.y)
            for ent in itno_entities:
                move_entity(ent, restore_offset)
            
            restore_distance = math.sqrt(restore_offset.x**2 + restore_offset.y**2)
            print(f"   [원위치 복원] FPOS→SPOS 이동 벡터: ({restore_offset.x:.2f}, {restore_offset.y:.2f})")
            print(f"   [원위치 복원] 이동 거리: {restore_distance:.2f}mm")
            
            # 복원 후 위치 확인
            itno_center_restored = get_entity_center(itno_entities)
            print(f"   [복원 확인] ITEMNO 중심점: ({itno_center_restored.x:.2f}, {itno_center_restored.y:.2f})")
            
            # DEL1 색상을 CYAN으로 변경
            if del1_lines:
                print(f"   [DEL1 색상 변경] {len(del1_lines)}개 DEL1을 CYAN 색상으로 변경")
                for line in del1_lines:
                    set_entity_color(line, 4)  # CYAN = 4
            
            # A1, AD1, DEL1은 삭제하지 않음
            print(f"   [보존] A1, AD1, DEL1 LINE들을 삭제하지 않고 유지합니다.")
        else:
            # PIPE가 충분히 길면 정상적으로 삭제 수행
            to_remove = []
            removed_entities = set()  # 중복 삭제 방지
            
            if found_A1:
                to_remove.append((found_A1, f"A1: {getattr(found_A1.dxf, 'handle', 'unknown')}"))
                removed_entities.add(found_A1)
            
            # 추가된 A1 LINE들도 삭제 목록에 추가
            for i, add_line in enumerate(additional_a1_lines):
                if add_line not in removed_entities:
                    to_remove.append((add_line, f"A1-추가{i+1}: {getattr(add_line.dxf, 'handle', 'unknown')}"))
                    removed_entities.add(add_line)
                
            if found_AD1 and found_AD1 not in removed_entities:
                to_remove.append((found_AD1, f"AD1: {getattr(found_AD1.dxf, 'handle', 'unknown')}"))
                removed_entities.add(found_AD1)
            
            # DEL1 LINE들 삭제 목록에 추가
            for i, line in enumerate(del1_lines):
                if line not in removed_entities:
                    to_remove.append((line, f"DEL1-{i+1}: {getattr(line.dxf, 'handle', 'unknown')}"))
                    removed_entities.add(line)
                
            # 8. AD1의 어느 한점과 접하는 1mm 이하의 ARROW 레이어 LINE 삭제
            if found_AD1:
                ad1_start = Vec2(found_AD1.dxf.start.x, found_AD1.dxf.start.y)
                ad1_end = Vec2(found_AD1.dxf.end.x, found_AD1.dxf.end.y)
                ad1_points = [ad1_start, ad1_end]
                
                for line in msp.query('LINE'):
                    try:
                        if not hasattr(line, 'dxf') or not hasattr(line.dxf, 'layer'):
                            continue
                        if line.dxf.layer.upper() != "ARROW":
                            continue
                            
                        start = Vec2(line.dxf.start.x, line.dxf.start.y)
                        end = Vec2(line.dxf.end.x, line.dxf.end.y)
                        line_length = distance(start, end)
                        
                        # 1mm 이하 LINE만
                        if line_length > 1.0:
                            continue
                            
                        # AD1의 어느 한점과 접하는지 확인
                        for ad1_pt in ad1_points:
                            if distance(ad1_pt, start) < 0.01 or distance(ad1_pt, end) < 0.01:
                                handle = getattr(line.dxf, 'handle', 'unknown')
                                to_remove.append((line, f"ARROW LINE: {handle} (AD1 접촉, 길이={line_length:.3f}mm)"))
                                break
                    except Exception as ex:
                        print(f"   [검사오류] ARROW LINE 검사 중 오류: {ex}")
                        continue
            
            # 삭제 실행
            deleted_count = 0
            for entity, description in to_remove:
                try:
                    msp.delete_entity(entity)
                    print(f"   [삭제] {description}")
                    deleted_count += 1
                except Exception as ex:
                    print(f"   [삭제오류] {description} / {ex}")

            print(f"   [삭제완료] 총 {deleted_count}개 엔티티 삭제")

    # 9. 간섭 체크에서 생성된 모든 BOX 삭제
    print(f"\n   ========== 간섭 체크 BOX 정리 ==========")
    box_layers = ["ITEMNO_BOX", "INTERFERENCE_ITNO", "INTERFERENCE_TEXT"]
    delete_boxes_by_layer(msp, box_layers)
    print(f"   [BOX 정리 완료] 간섭 체크 관련 모든 BOX 삭제")

    save_path = os.path.splitext(file_path)[0] + "_ITNO.dxf"
    try:
        doc.saveas(save_path)
        print(f"[✔] 저장 완료: {os.path.basename(save_path)}")
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