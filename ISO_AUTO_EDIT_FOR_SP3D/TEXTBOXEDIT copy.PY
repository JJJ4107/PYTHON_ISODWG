"""
DXF Text and Polyline Processor

색상 변경:
- EBORE, IBOX, ITAG, OTEXT, A2, A3: CYAN (색상 코드 4)
- A1: GREEN (색상 코드 3)으로 변경 + 추가 시각화
  - 원본 A1을 GREEN으로 직접 변경
  - A1_GREEN 레이어로 이동
  - 동일 위치에 GREEN 라인들 추가 생성
  - 시작/끝점에 GREEN 원과 'A1' 텍스트 추가
- AG 레이어 LINE: WHITE (색상 코드 7)

A1 처리 방식:
1. 원본 A1의 색상을 직접 GREEN으로 변경
2. 원본 A1을 A1_GREEN 레이어로 이동
3. 백업으로 동일 위치에 GREEN 라인들 생성
4. 시각적 확인을 위한 원과 텍스트 추가

A1 선택 조건:
1. 엔티티 타입: POLYLINE 또는 LWPOLYLINE (LINE 제외)
2. 점의 개수: 2점 또는 3점
3. 레이어: PL2 또는 GT_1 (GT-1, GT1도 허용)
4. 폴리라인 총 길이: 10mm 초과
5. 거리: A1의 어느 한 점이 EBORE TEXT BOX의 어느 한 모서리에서 15mm 이내
6. 우선순위: 가장 가까운 거리의 폴리라인 선택
"""

import tkinter as tk
from tkinter import filedialog
import ezdxf
import math
import os
import re

class DXFProcessor:
    def __init__(self):
        self.doc = None
        self.msp = None
        self.AP1 = None  # 가까운 점 (이동됨)
        self.AP2 = None  # 먼 점 (고정됨)
        self.original_AP1 = None  # 원래 AP1 위치
        
    def select_dxf_files(self):
        """DXF 파일 선택 다이얼로그 열기"""
        root = tk.Tk()
        root.withdraw()
        file_paths = filedialog.askopenfilenames(
            title="DXF 파일 선택",
            filetypes=[("DXF files", "*.dxf"), ("All files", "*.*")]
        )
        return file_paths
    
    def set_entity_color(self, entity, color=4):
        """엔티티의 색상 설정 (기본값: CYAN=4)
        
        AutoCAD 색상 코드:
        1 = RED
        2 = YELLOW
        3 = GREEN
        4 = CYAN
        5 = BLUE
        6 = MAGENTA
        7 = WHITE
        """
        try:
            if hasattr(entity, 'dxf'):
                # 색상 설정 전 상태 확인
                old_color = getattr(entity.dxf, 'color', 'BYLAYER')
                
                # 색상 설정
                entity.dxf.color = color
                
                # 색상 설정 후 확인
                new_color = entity.dxf.color
                print(f"  Color change: {old_color} → {new_color} (target: {color})")
                
                # 추가로 true_color 속성도 제거 (있는 경우)
                if hasattr(entity.dxf, 'true_color'):
                    entity.dxf.true_color = None
                    
        except Exception as e:
            print(f"Error setting color for {entity.dxftype()}: {e}")
    
    def force_entity_color(self, entity, color):
        """엔티티의 색상을 강제로 설정 (레이어 색상 무시)"""
        try:
            entity_type = entity.dxftype()
            print(f"  Force setting color for {entity_type}")
            
            # 기본 색상 설정
            entity.dxf.color = color
            
            # 레이어 색상 대신 엔티티 색상 사용하도록 설정
            # 색상 값이 256이면 BYLAYER를 의미하므로 이를 방지
            if hasattr(entity.dxf, 'color') and entity.dxf.color == 256:
                entity.dxf.color = color
            
            # POLYLINE의 경우 각 vertex 색상도 변경
            if entity_type == 'POLYLINE':
                if hasattr(entity, 'vertices'):
                    for vertex in entity.vertices:
                        vertex.dxf.color = color
                        
            # LWPOLYLINE의 경우 추가 처리는 필요 없음
            
            # 디버깅을 위한 색상 확인
            final_color = entity.dxf.color
            print(f"  Final color set to: {final_color}")
            
        except Exception as e:
            print(f"  Error in force_entity_color: {e}")
            import traceback
            traceback.print_exc()
    
    def get_text_rotation(self, text_entity):
        """TEXT 엔티티의 기울기(회전각) 가져오기"""
        if hasattr(text_entity, 'dxf') and hasattr(text_entity.dxf, 'rotation'):
            return text_entity.dxf.rotation
        return 0
    
    def get_entity_position(self, entity):
        """엔티티의 위치 가져오기 (튜플 반환)"""
        if entity.dxftype() == 'TEXT':
            return (entity.dxf.insert.x, entity.dxf.insert.y)
        elif entity.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
            points = list(entity.points())
            if points:
                return (points[0][0], points[0][1])
        return None
    
    def calculate_distance(self, point1, point2):
        """두 점 사이의 거리 계산"""
        return math.sqrt((point2[0] - point1[0])**2 + (point2[1] - point1[1])**2)
    
    def distance_between_entities(self, entity1, entity2):
        """두 엔티티 간의 최소 거리 계산"""
        if entity1.dxftype() == 'TEXT' and entity2.dxftype() == 'TEXT':
            pos1 = self.get_entity_position(entity1)
            pos2 = self.get_entity_position(entity2)
            return self.calculate_distance(pos1, pos2) if pos1 and pos2 else float('inf')
        
        elif entity1.dxftype() == 'TEXT' and entity2.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
            text_pos = self.get_entity_position(entity1)
            if not text_pos:
                return float('inf')
            min_dist = float('inf')
            for point in entity2.points():
                dist = self.calculate_distance(text_pos, (point[0], point[1]))
                min_dist = min(min_dist, dist)
            return min_dist
        
        elif entity1.dxftype() in ['POLYLINE', 'LWPOLYLINE'] and entity2.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
            min_dist = float('inf')
            for p1 in entity1.points():
                for p2 in entity2.points():
                    dist = self.calculate_distance((p1[0], p1[1]), (p2[0], p2[1]))
                    min_dist = min(min_dist, dist)
            return min_dist
        
        return float('inf')
    
    def find_ebore_texts(self):
        """EBORE 조건에 맞는 TEXT 찾기: 기울기 0, 'x'와 'DN' 또는 '"' 포함"""
        ebore_texts = []
        for entity in self.msp:
            if entity.dxftype() == 'TEXT':
                if self.get_text_rotation(entity) == 0:
                    text = entity.dxf.text.upper()
                    if 'X' in text and ('DN' in text or '"' in text):
                        ebore_texts.append(entity)
        return ebore_texts
    
    def find_ibox_polylines(self, ebore_texts):
        """EBORE와 5mm 내에 있는 ITEMNO 5점 폴리라인 찾기"""
        ibox_polylines = []
        for entity in self.msp:
            if entity.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
                points = list(entity.points())
                if len(points) == 5:
                    # 레이어명 체크 (대소문자 구분 없이)
                    if hasattr(entity.dxf, 'layer') and 'ITEMNO' in entity.dxf.layer.upper():
                        # EBORE와의 거리 체크
                        for ebore in ebore_texts:
                            if self.distance_between_entities(ebore, entity) <= 5:
                                ibox_polylines.append(entity)
                                break
        return ibox_polylines
    
    def find_itag_texts(self, ibox_polylines):
        """IBOX 폴리라인 5mm 내에서 기울기 0인 숫자 TEXT 또는 GT_1 레이어의 기울기 0인 TEXT 찾기"""
        itag_texts = []
        for entity in self.msp:
            if entity.dxftype() == 'TEXT':
                if self.get_text_rotation(entity) == 0:
                    # GT_1 레이어 체크 (GT-1, GT1도 허용)
                    layer = entity.dxf.layer.upper() if hasattr(entity.dxf, 'layer') else ''
                    is_gt1_layer = 'GT_1' in layer or 'GT-1' in layer or 'GT1' in layer
                    
                    # 숫자인지 체크
                    is_number = entity.dxf.text.strip().isdigit()
                    
                    # GT_1 레이어이거나 숫자인 경우
                    if is_gt1_layer or is_number:
                        # IBOX와의 거리 체크
                        for ibox in ibox_polylines:
                            if self.distance_between_entities(entity, ibox) <= 5:
                                itag_texts.append(entity)
                                break
        return itag_texts
    
    def find_otext_texts(self, ebore_texts):
        """EBORE 아래에서 기울기 0이고 OFFSET, EL, FL 중 하나가 포함된 TEXT 찾기"""
        otext_texts = []
        for entity in self.msp:
            if entity.dxftype() == 'TEXT':
                if self.get_text_rotation(entity) == 0:
                    text_upper = entity.dxf.text.upper()
                    # OFFSET, EL, FL 중 하나라도 포함되면 선택
                    if 'OFFSET' in text_upper or 'EL' in text_upper or 'FL' in text_upper:
                        # EBORE 아래에 있는지 체크
                        text_pos = self.get_entity_position(entity)
                        if text_pos:
                            for ebore in ebore_texts:
                                ebore_pos = self.get_entity_position(ebore)
                                if ebore_pos and text_pos[1] < ebore_pos[1]:
                                    otext_texts.append(entity)
                                    break
        return otext_texts
    
    def get_text_bounding_box(self, text_entity):
        """TEXT 엔티티의 바운딩 박스 계산 (AutoCAD TEXT의 길이와 높이 기반)"""
        if text_entity.dxftype() != 'TEXT':
            return None
            
        # TEXT의 삽입점
        insert = text_entity.dxf.insert
        x, y = insert.x, insert.y
        
        # TEXT 높이
        height = text_entity.dxf.height
        
        # TEXT 길이 추정 (대략적인 계산)
        text_content = text_entity.dxf.text
        # 문자 길이를 높이의 비율로 추정 (대략 0.7배)
        char_width = height * 0.7
        length = len(text_content) * char_width
        
        # 회전 각도
        rotation = self.get_text_rotation(text_entity)
        rotation_rad = math.radians(rotation)
        
        # 회전이 없는 경우의 4개 모서리
        if rotation == 0:
            corners = [
                (x, y),                          # 왼쪽 아래
                (x + length, y),                 # 오른쪽 아래
                (x + length, y + height),        # 오른쪽 위
                (x, y + height)                  # 왼쪽 위
            ]
        else:
            # 회전이 있는 경우 각 모서리를 회전 변환
            cos_r = math.cos(rotation_rad)
            sin_r = math.sin(rotation_rad)
            
            corners = []
            # 4개 모서리 점
            local_corners = [(0, 0), (length, 0), (length, height), (0, height)]
            
            for lx, ly in local_corners:
                # 회전 변환
                rx = x + lx * cos_r - ly * sin_r
                ry = y + lx * sin_r + ly * cos_r
                corners.append((rx, ry))
        
        return corners
    
    def get_bounding_box(self, entities):
        """엔티티들의 바운딩 박스 계산 (TEXT도 BOX로 처리)"""
        min_x, min_y = float('inf'), float('inf')
        max_x, max_y = float('-inf'), float('-inf')
        
        for entity in entities:
            if entity.dxftype() == 'TEXT':
                # TEXT를 박스로 처리
                text_box = self.get_text_bounding_box(entity)
                if text_box:
                    for corner in text_box:
                        min_x = min(min_x, corner[0])
                        min_y = min(min_y, corner[1])
                        max_x = max(max_x, corner[0])
                        max_y = max(max_y, corner[1])
            elif entity.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
                for point in entity.points():
                    min_x = min(min_x, point[0])
                    min_y = min(min_y, point[1])
                    max_x = max(max_x, point[0])
                    max_y = max(max_y, point[1])
        
        return [(min_x, min_y), (max_x, min_y), (max_x, max_y), (min_x, max_y)]
    
    def calculate_polyline_length(self, polyline):
        """폴리라인의 총 길이 계산"""
        points = list(polyline.points())
        total_length = 0
        for i in range(len(points) - 1):
            total_length += self.calculate_distance(
                (points[i][0], points[i][1]), 
                (points[i+1][0], points[i+1][1])
            )
        return total_length
    
    def check_interference(self, entities, position):
        """주어진 위치에서 간섭 체크"""
        # 간단한 간섭 체크 로직
        for entity in self.msp:
            if entity not in entities:
                if entity.dxftype() in ['TEXT', 'LINE', 'POLYLINE', 'LWPOLYLINE']:
                    entity_pos = self.get_entity_position(entity)
                    if entity_pos and self.calculate_distance(entity_pos, position) < 1:
                        return True
        return False
    
    def count_box_interferences(self, bbox_corners, dx, dy, exclude_entities):
        """바운딩 박스의 간섭 개수 계산 (간섭하는 엔티티 수 반환)"""
        # 이동된 바운딩 박스 코너
        moved_corners = [
            (corner[0] + dx, corner[1] + dy) for corner in bbox_corners
        ]
        
        interference_count = 0
        
        # 다른 엔티티들과 간섭 체크
        for entity in self.msp:
            if entity not in exclude_entities:
                entity_type = entity.dxftype()
                
                if entity_type == 'TEXT':
                    # TEXT를 박스로 처리하여 간섭 체크
                    text_box = self.get_text_bounding_box(entity)
                    if text_box and self.boxes_overlap(moved_corners, text_box):
                        interference_count += 1
                
                elif entity_type == 'LINE':
                    # LINE을 선분으로 처리
                    line_start = (entity.dxf.start.x, entity.dxf.start.y)
                    line_end = (entity.dxf.end.x, entity.dxf.end.y)
                    if self.line_intersects_box(line_start, line_end, moved_corners):
                        interference_count += 1
                
                elif entity_type in ['POLYLINE', 'LWPOLYLINE']:
                    # POLYLINE의 각 선분으로 간섭 체크
                    points = list(entity.points())
                    has_interference = False
                    
                    for i in range(len(points) - 1):
                        seg_start = (points[i][0], points[i][1])
                        seg_end = (points[i+1][0], points[i+1][1])
                        if self.line_intersects_box(seg_start, seg_end, moved_corners):
                            has_interference = True
                            break
                    
                    # 폐합된 폴리라인의 경우 마지막 점과 첫 점 연결
                    if not has_interference and hasattr(entity.dxf, 'flags') and entity.dxf.flags & 1:
                        if len(points) > 2:
                            seg_start = (points[-1][0], points[-1][1])
                            seg_end = (points[0][0], points[0][1])
                            if self.line_intersects_box(seg_start, seg_end, moved_corners):
                                has_interference = True
                    
                    if has_interference:
                        interference_count += 1
                
                elif entity_type == 'CIRCLE':
                    # CIRCLE 간섭 체크
                    center = (entity.dxf.center.x, entity.dxf.center.y)
                    radius = entity.dxf.radius
                    if self.circle_intersects_box(center, radius, moved_corners):
                        interference_count += 1
                
                elif entity_type == 'ARC':
                    # ARC 간섭 체크
                    center = (entity.dxf.center.x, entity.dxf.center.y)
                    radius = entity.dxf.radius
                    start_angle = entity.dxf.start_angle
                    end_angle = entity.dxf.end_angle
                    if self.arc_intersects_box(center, radius, start_angle, end_angle, moved_corners):
                        interference_count += 1
        
        return interference_count
    
    def normalize_vector(self, vector):
        """벡터 정규화"""
        length = math.sqrt(vector[0]**2 + vector[1]**2)
        if length == 0:
            return (0, 0)
        return (vector[0]/length, vector[1]/length)
    
    def move_entity(self, entity, dx, dy):
        """엔티티를 지정된 거리만큼 이동"""
        try:
            if entity.dxftype() == 'TEXT':
                # TEXT 엔티티 이동
                old_pos = entity.dxf.insert
                entity.dxf.insert = (old_pos.x + dx, old_pos.y + dy, old_pos.z)
                
            elif entity.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
                if entity.dxftype() == 'LWPOLYLINE':
                    # LWPOLYLINE의 경우
                    old_points = list(entity.get_points())
                    new_points = []
                    for x, y, *rest in old_points:
                        new_points.append((x + dx, y + dy, *rest))
                    entity.set_points(new_points)
                    
                elif entity.dxftype() == 'POLYLINE':
                    # POLYLINE의 경우
                    for vertex in entity.vertices:
                        vertex.dxf.location = (
                            vertex.dxf.location.x + dx,
                            vertex.dxf.location.y + dy,
                            vertex.dxf.location.z
                        )
                        
        except Exception as e:
            print(f"Error moving entity {entity.dxftype()}: {e}")
    
    def boxes_overlap(self, box1_corners, box2_corners):
        """두 박스가 겹치는지 확인 (박스는 회전된 상태일 수 있음)"""
        # 간단한 AABB(Axis-Aligned Bounding Box) 체크
        # 각 박스의 최소/최대 좌표 계산
        box1_min_x = min(corner[0] for corner in box1_corners)
        box1_max_x = max(corner[0] for corner in box1_corners)
        box1_min_y = min(corner[1] for corner in box1_corners)
        box1_max_y = max(corner[1] for corner in box1_corners)
        
        box2_min_x = min(corner[0] for corner in box2_corners)
        box2_max_x = max(corner[0] for corner in box2_corners)
        box2_min_y = min(corner[1] for corner in box2_corners)
        box2_max_y = max(corner[1] for corner in box2_corners)
        
        # 박스가 겹치지 않는 조건
        if box1_max_x < box2_min_x - 1 or box1_min_x > box2_max_x + 1:
            return False
        if box1_max_y < box2_min_y - 1 or box1_min_y > box2_max_y + 1:
            return False
            
        return True
    
    def line_intersects_box(self, line_start, line_end, box_corners):
        """선분이 박스와 교차하는지 확인"""
        # 박스의 최소/최대 좌표
        min_x = min(corner[0] for corner in box_corners)
        max_x = max(corner[0] for corner in box_corners)
        min_y = min(corner[1] for corner in box_corners)
        max_y = max(corner[1] for corner in box_corners)
        
        # 선분의 양 끝점이 박스 내부에 있는지 확인
        if (min_x <= line_start[0] <= max_x and min_y <= line_start[1] <= max_y):
            return True
        if (min_x <= line_end[0] <= max_x and min_y <= line_end[1] <= max_y):
            return True
        
        # 선분이 박스의 네 변 중 하나와 교차하는지 확인
        box_edges = [
            (box_corners[0], box_corners[1]),  # 아래
            (box_corners[1], box_corners[2]),  # 오른쪽
            (box_corners[2], box_corners[3]),  # 위
            (box_corners[3], box_corners[0])   # 왼쪽
        ]
        
        for edge_start, edge_end in box_edges:
            if self.line_segments_intersect(line_start, line_end, edge_start, edge_end):
                return True
        
        # 선분이 박스를 완전히 관통하는 경우 체크
        # 수평선이 박스를 관통하는 경우
        if line_start[1] == line_end[1]:  # 수평선
            if min_y <= line_start[1] <= max_y:
                if (line_start[0] <= min_x and line_end[0] >= max_x) or \
                   (line_end[0] <= min_x and line_start[0] >= max_x):
                    return True
        
        # 수직선이 박스를 관통하는 경우
        if line_start[0] == line_end[0]:  # 수직선
            if min_x <= line_start[0] <= max_x:
                if (line_start[1] <= min_y and line_end[1] >= max_y) or \
                   (line_end[1] <= min_y and line_start[1] >= max_y):
                    return True
        
        return False
    
    def circle_intersects_box(self, center, radius, box_corners):
        """원이 박스와 교차하는지 확인"""
        # 박스의 최소/최대 좌표
        min_x = min(corner[0] for corner in box_corners)
        max_x = max(corner[0] for corner in box_corners)
        min_y = min(corner[1] for corner in box_corners)
        max_y = max(corner[1] for corner in box_corners)
        
        # 원의 중심에서 박스까지의 최단 거리 계산
        closest_x = max(min_x, min(center[0], max_x))
        closest_y = max(min_y, min(center[1], max_y))
        
        # 최단 거리가 반지름보다 작거나 같으면 교차
        distance = self.calculate_distance(center, (closest_x, closest_y))
        return distance <= radius + 1  # 1mm 여유
    
    def arc_intersects_box(self, center, radius, start_angle, end_angle, box_corners):
        """호가 박스와 교차하는지 확인"""
        # 우선 원 전체가 박스와 교차하는지 확인
        if not self.circle_intersects_box(center, radius, box_corners):
            return False
        
        # 호의 시작점과 끝점 계산
        start_rad = math.radians(start_angle)
        end_rad = math.radians(end_angle)
        
        start_point = (
            center[0] + radius * math.cos(start_rad),
            center[1] + radius * math.sin(start_rad)
        )
        end_point = (
            center[0] + radius * math.cos(end_rad),
            center[1] + radius * math.sin(end_rad)
        )
        
        # 박스의 최소/최대 좌표
        min_x = min(corner[0] for corner in box_corners)
        max_x = max(corner[0] for corner in box_corners)
        min_y = min(corner[1] for corner in box_corners)
        max_y = max(corner[1] for corner in box_corners)
        
        # 호의 끝점들이 박스 내부에 있는지 확인
        if (min_x <= start_point[0] <= max_x and min_y <= start_point[1] <= max_y):
            return True
        if (min_x <= end_point[0] <= max_x and min_y <= end_point[1] <= max_y):
            return True
        
        # 호 상의 여러 점을 샘플링하여 박스와의 교차 확인
        num_samples = 20
        for i in range(num_samples + 1):
            t = i / num_samples
            angle = start_rad + t * (end_rad - start_rad)
            if end_rad < start_rad:  # 호가 0도를 넘어가는 경우
                angle = start_rad + t * (end_rad + 2 * math.pi - start_rad)
            
            point = (
                center[0] + radius * math.cos(angle),
                center[1] + radius * math.sin(angle)
            )
            
            if min_x <= point[0] <= max_x and min_y <= point[1] <= max_y:
                return True
        
        return False
    
    def check_box_interference(self, bbox_corners, dx, dy, exclude_entities):
        """바운딩 박스의 간섭 개수 계산 (간섭하는 엔티티 수 반환)"""
        # 이동된 바운딩 박스 코너
        moved_corners = [
            (corner[0] + dx, corner[1] + dy) for corner in bbox_corners
        ]
        
        interference_count = 0
        
        # 다른 엔티티들과 간섭 체크
        for entity in self.msp:
            if entity not in exclude_entities:
                entity_type = entity.dxftype()
                
                if entity_type == 'TEXT':
                    # TEXT를 박스로 처리하여 간섭 체크
                    text_box = self.get_text_bounding_box(entity)
                    if text_box and self.boxes_overlap(moved_corners, text_box):
                        interference_count += 1
                
                elif entity_type == 'LINE':
                    # LINE을 선분으로 처리
                    line_start = (entity.dxf.start.x, entity.dxf.start.y)
                    line_end = (entity.dxf.end.x, entity.dxf.end.y)
                    if self.line_intersects_box(line_start, line_end, moved_corners):
                        interference_count += 1
                
                elif entity_type in ['POLYLINE', 'LWPOLYLINE']:
                    # POLYLINE의 각 선분으로 간섭 체크
                    points = list(entity.points())
                    has_interference = False
                    
                    for i in range(len(points) - 1):
                        seg_start = (points[i][0], points[i][1])
                        seg_end = (points[i+1][0], points[i+1][1])
                        if self.line_intersects_box(seg_start, seg_end, moved_corners):
                            has_interference = True
                            break
                    
                    # 폐합된 폴리라인의 경우 마지막 점과 첫 점 연결
                    if not has_interference and hasattr(entity.dxf, 'flags') and entity.dxf.flags & 1:
                        if len(points) > 2:
                            seg_start = (points[-1][0], points[-1][1])
                            seg_end = (points[0][0], points[0][1])
                            if self.line_intersects_box(seg_start, seg_end, moved_corners):
                                has_interference = True
                    
                    if has_interference:
                        interference_count += 1
                
                elif entity_type == 'CIRCLE':
                    # CIRCLE 간섭 체크
                    center = (entity.dxf.center.x, entity.dxf.center.y)
                    radius = entity.dxf.radius
                    if self.circle_intersects_box(center, radius, moved_corners):
                        interference_count += 1
                
                elif entity_type == 'ARC':
                    # ARC 간섭 체크
                    center = (entity.dxf.center.x, entity.dxf.center.y)
                    radius = entity.dxf.radius
                    start_angle = entity.dxf.start_angle
                    end_angle = entity.dxf.end_angle
                    if self.arc_intersects_box(center, radius, start_angle, end_angle, moved_corners):
                        interference_count += 1
        
        return interference_count
        """바운딩 박스의 간섭 체크 (TEXT는 BOX로, LINE/POLYLINE/CIRCLE/ARC는 선분으로 처리)"""
        # 이동된 바운딩 박스 코너
        moved_corners = [
            (corner[0] + dx, corner[1] + dy) for corner in bbox_corners
        ]
        
        # 다른 엔티티들과 간섭 체크
        for entity in self.msp:
            if entity not in exclude_entities:
                entity_type = entity.dxftype()
                
                if entity_type == 'TEXT':
                    # TEXT를 박스로 처리하여 간섭 체크
                    text_box = self.get_text_bounding_box(entity)
                    if text_box and self.boxes_overlap(moved_corners, text_box):
                        return True
                
                elif entity_type == 'LINE':
                    # LINE을 선분으로 처리
                    line_start = (entity.dxf.start.x, entity.dxf.start.y)
                    line_end = (entity.dxf.end.x, entity.dxf.end.y)
                    if self.line_intersects_box(line_start, line_end, moved_corners):
                        return True
                
                elif entity_type in ['POLYLINE', 'LWPOLYLINE']:
                    # POLYLINE의 각 선분으로 간섭 체크
                    points = list(entity.points())
                    for i in range(len(points) - 1):
                        seg_start = (points[i][0], points[i][1])
                        seg_end = (points[i+1][0], points[i+1][1])
                        if self.line_intersects_box(seg_start, seg_end, moved_corners):
                            return True
                    
                    # 폐합된 폴리라인의 경우 마지막 점과 첫 점 연결
                    if hasattr(entity.dxf, 'flags') and entity.dxf.flags & 1:  # CLOSED flag
                        if len(points) > 2:
                            seg_start = (points[-1][0], points[-1][1])
                            seg_end = (points[0][0], points[0][1])
                            if self.line_intersects_box(seg_start, seg_end, moved_corners):
                                return True
                
                elif entity_type == 'CIRCLE':
                    # CIRCLE 간섭 체크
                    center = (entity.dxf.center.x, entity.dxf.center.y)
                    radius = entity.dxf.radius
                    if self.circle_intersects_box(center, radius, moved_corners):
                        return True
                
                elif entity_type == 'ARC':
                    # ARC 간섭 체크
                    center = (entity.dxf.center.x, entity.dxf.center.y)
                    radius = entity.dxf.radius
                    start_angle = entity.dxf.start_angle
                    end_angle = entity.dxf.end_angle
                    if self.arc_intersects_box(center, radius, start_angle, end_angle, moved_corners):
                        return True
        
        return False
    
    def find_target_position_and_move_entities(self, a1_polyline, alltxt_entities):
        """ALLTXT를 AP1→AP2 벡터만큼 이동 후 AP1 방향으로 간섭 체크하여 최종 위치 확정"""
        # ALLTXT의 바운딩 박스 계산
        bbox_corners = self.get_bounding_box(alltxt_entities)
        bbox_center = (
            (bbox_corners[0][0] + bbox_corners[2][0]) / 2,
            (bbox_corners[0][1] + bbox_corners[2][1]) / 2
        )
        
        print(f"    ALLTXT bounding box center: ({bbox_center[0]:.2f}, {bbox_center[1]:.2f})")
        print(f"    ALLTXT bounding box size: {abs(bbox_corners[2][0] - bbox_corners[0][0]):.2f} x {abs(bbox_corners[2][1] - bbox_corners[0][1]):.2f}")
        
        # A1의 점들 가져오기
        a1_points = list(a1_polyline.points())
        
        # ALLTXT 중심과 가장 가까운 점(AP1)과 먼 점(AP2) 찾기
        min_dist = float('inf')
        max_dist = 0
        AP1 = None  # 가까운 점
        AP2 = None  # 먼 점
        
        for point in a1_points:
            pt = (point[0], point[1])
            dist = self.calculate_distance(pt, bbox_center)
            if dist < min_dist:
                min_dist = dist
                AP1 = pt
            if dist > max_dist:
                max_dist = dist
                AP2 = pt
        
        if not AP1 or not AP2:
            return None
        
        # AP1과 AP2 저장 (AP2는 원본 위치 고정)
        self.AP1 = AP1
        self.AP2 = AP2  # 고정됨
        self.original_AP1 = AP1  # 원래 AP1 위치 저장
        
        print(f"    AP1 (near point): ({AP1[0]:.2f}, {AP1[1]:.2f})")
        print(f"    AP2 (far point - fixed): ({AP2[0]:.2f}, {AP2[1]:.2f})")
        
        # A1 삭제
        try:
            self.msp.delete_entity(a1_polyline)
            print(f"    A1 polyline deleted before interference check")
        except Exception as e:
            print(f"    Error deleting A1: {e}")
        
        # AP1에서 AP2로의 벡터 (A1의 기울기)
        a1_vector = (AP2[0] - AP1[0], AP2[1] - AP1[1])
        
        # AP2에서 AP1 방향 벡터 계산 (역방향)
        direction = (AP1[0] - AP2[0], AP1[1] - AP2[1])
        direction = self.normalize_vector(direction)
        
        # ALLTXT를 AP1→AP2 벡터만큼 이동하기 위한 변위
        base_dx = a1_vector[0]
        base_dy = a1_vector[1]
        
        print(f"    Moving ALLTXT by A1 vector: ({base_dx:.2f}, {base_dy:.2f})")
        
        # 최초 15mm는 간섭 체크 없이 바로 이동
        initial_move = 15  # -15mm
        initial_dx = base_dx + direction[0] * initial_move
        initial_dy = base_dy + direction[1] * initial_move
        
        print(f"    Skip first 5 steps, start from -15mm position")
        
        # 모든 위치에서의 간섭 정보 저장
        position_results = []
        
        # -15mm부터 시작하여 AP1 방향으로 3mm씩 체크 (step 5부터 시작)
        for step in range(5, 20):  # 5부터 19까지 (15번 체크)
            # AP2에서 AP1 방향으로 이동 거리
            move_distance = step * 3  # 15mm, 18mm, 21mm, ... 57mm
            
            # 총 이동량 계산
            dx = base_dx + direction[0] * move_distance
            dy = base_dy + direction[1] * move_distance
            
            # 간섭 체크
            has_interference = self.check_box_interference(bbox_corners, dx, dy, alltxt_entities)
            
            if has_interference:
                # 간섭이 있는 경우 간섭 개수 계산
                interference_count = self.count_box_interferences(bbox_corners, dx, dy, alltxt_entities)
                print(f"    Checking position at -{move_distance}mm: {interference_count} interferences")
                position_results.append({
                    'distance': move_distance,
                    'dx': dx,
                    'dy': dy,
                    'has_interference': True,
                    'interference_count': interference_count
                })
            else:
                # 간섭이 없는 경우
                print(f"    Checking position at -{move_distance}mm: No interference")
                position_results.append({
                    'distance': move_distance,
                    'dx': dx,
                    'dy': dy,
                    'has_interference': False,
                    'interference_count': 0
                })
                # 첫 번째 간섭 없는 위치에서 중단
                break
        
        # 최적 위치 선택
        final_dx = initial_dx  # 기본값: -15mm 위치
        final_dy = initial_dy
        
        if position_results:
            # 간섭이 없는 위치가 있으면 그 위치 선택
            no_interference_positions = [p for p in position_results if not p['has_interference']]
            if no_interference_positions:
                best_position = no_interference_positions[0]  # 첫 번째 간섭 없는 위치
                final_dx = best_position['dx']
                final_dy = best_position['dy']
                print(f"    Selected position: -{best_position['distance']}mm (no interference)")
            else:
                # 모든 위치에서 간섭이 있으면 간섭이 가장 적은 위치 선택
                best_position = min(position_results, key=lambda p: p['interference_count'])
                final_dx = best_position['dx']
                final_dy = best_position['dy']
                print(f"    All positions have interference, selected -{best_position['distance']}mm (minimum {best_position['interference_count']} interferences)")
        else:
            # position_results가 비어있으면 -15mm 위치 사용
            print(f"    Using initial position at -15mm")
        
        # 실제로 엔티티들 이동
        if final_dx != 0 or final_dy != 0:
            print(f"    Moving ALLTXT entities by ({final_dx:.2f}, {final_dy:.2f})")
            for entity in alltxt_entities:
                self.move_entity(entity, final_dx, final_dy)
            
            # AP1만 이동 (AP2는 고정)
            self.AP1 = (AP1[0] + final_dx, AP1[1] + final_dy)
            # self.AP2는 변경하지 않음 (원래 위치 유지)
            print(f"    AP1 moved to: ({self.AP1[0]:.2f}, {self.AP1[1]:.2f})")
            print(f"    AP2 remains at: ({self.AP2[0]:.2f}, {self.AP2[1]:.2f})")
        
        return (final_dx, final_dy)
    
    def find_a2_arrow_line_with_points(self, a1_points):
        """고정된 AP2 위치에서 3mm 내에서 원본 A1과 교차했던 ARROW 레이어 LINE 찾기"""
        if not hasattr(self, 'AP2'):
            return None
            
        # A1의 선분들 구성
        a1_segments = []
        for i in range(len(a1_points) - 1):
            seg_start = (a1_points[i][0], a1_points[i][1])
            seg_end = (a1_points[i+1][0], a1_points[i+1][1])
            a1_segments.append((seg_start, seg_end))
        
        # ARROW 레이어의 LINE 검사
        for entity in self.msp:
            if entity.dxftype() == 'LINE':
                if hasattr(entity.dxf, 'layer') and entity.dxf.layer.upper() == 'ARROW':
                    # LINE의 끝점들 가져오기
                    line_start = (entity.dxf.start.x, entity.dxf.start.y)
                    line_end = (entity.dxf.end.x, entity.dxf.end.y)
                    
                    # 고정된 AP2와의 거리 체크 (3mm 이내)
                    if (self.calculate_distance(line_start, self.AP2) <= 3 or 
                        self.calculate_distance(line_end, self.AP2) <= 3):
                        
                        # 원본 A1과 교차했는지 확인
                        for seg_start, seg_end in a1_segments:
                            if self.line_segments_intersect(seg_start, seg_end, line_start, line_end):
                                print(f"    Found A2: ARROW LINE intersecting with original A1")
                                return entity
        
        print(f"    No A2 found (ARROW LINE within 3mm of fixed AP2 and intersecting original A1)")
        return None
    
    def find_a2_arrow_line(self, a1_polyline):
        """A1의 먼 점에서 3mm 내에서 A1과 교차하는 ARROW 레이어 LINE 찾기"""
        if not self.far_point:
            return None
            
        # A1의 점들 가져오기
        a1_points = list(a1_polyline.points())
        
        # A1의 선분들 구성
        a1_segments = []
        for i in range(len(a1_points) - 1):
            seg_start = (a1_points[i][0], a1_points[i][1])
            seg_end = (a1_points[i+1][0], a1_points[i+1][1])
            a1_segments.append((seg_start, seg_end))
        
        # ARROW 레이어의 LINE 검사
        for entity in self.msp:
            if entity.dxftype() == 'LINE':
                if hasattr(entity.dxf, 'layer') and entity.dxf.layer.upper() == 'ARROW':
                    # LINE의 끝점들 가져오기
                    line_start = (entity.dxf.start.x, entity.dxf.start.y)
                    line_end = (entity.dxf.end.x, entity.dxf.end.y)
                    
                    # 먼 점과의 거리 체크 (3mm 이내)
                    if (self.calculate_distance(line_start, self.far_point) <= 3 or 
                        self.calculate_distance(line_end, self.far_point) <= 3):
                        
                        # A1과 교차하는지 확인
                        for seg_start, seg_end in a1_segments:
                            if self.line_segments_intersect(seg_start, seg_end, line_start, line_end):
                                print(f"    Found A2: ARROW LINE intersecting with A1")
                                return entity
        
        print(f"    No A2 found (ARROW LINE within 3mm of far point and intersecting A1)")
        return None
    
    def line_segments_intersect(self, p1, p2, p3, p4):
        """두 선분이 교차하는지 확인"""
        def ccw(A, B, C):
            return (C[1]-A[1]) * (B[0]-A[0]) > (B[1]-A[1]) * (C[0]-A[0])
        
        # 두 선분이 교차하는지 확인
        return ccw(p1, p3, p4) != ccw(p2, p3, p4) and ccw(p1, p2, p3) != ccw(p1, p2, p4)
    
    def find_a3_polyline(self, a2_line):
        """A2와 한 점이 접하는 3점 폴리라인 또는 LWPOLYLINE 찾기"""
        if not a2_line:
            return None
            
        a2_start = (a2_line.dxf.start.x, a2_line.dxf.start.y)
        a2_end = (a2_line.dxf.end.x, a2_line.dxf.end.y)
        
        for entity in self.msp:
            if entity.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
                points = list(entity.points())
                if len(points) == 3:
                    # A2와 접하는지 체크 (0.1mm 이내를 접촉으로 간주)
                    for point in points:
                        point_tuple = (point[0], point[1])
                        if (self.calculate_distance(point_tuple, a2_start) < 0.1 or 
                            self.calculate_distance(point_tuple, a2_end) < 0.1):
                            return entity
        return None
    
    def point_to_line_distance(self, point, line_start, line_end):
        """점과 선분 사이의 최단 거리 계산"""
        # 선분의 벡터
        line_vec = (line_end[0] - line_start[0], line_end[1] - line_start[1])
        # 시작점에서 점까지의 벡터
        point_vec = (point[0] - line_start[0], point[1] - line_start[1])
        
        # 선분의 길이 제곱
        line_len_sq = line_vec[0]**2 + line_vec[1]**2
        
        if line_len_sq == 0:
            # 선분이 점인 경우
            return self.calculate_distance(point, line_start)
        
        # 투영 계산
        t = max(0, min(1, (point_vec[0]*line_vec[0] + point_vec[1]*line_vec[1]) / line_len_sq))
        
        # 선분 위의 가장 가까운 점
        projection = (line_start[0] + t * line_vec[0], line_start[1] + t * line_vec[1])
        
        return self.calculate_distance(point, projection)
    
    def find_a1_polyline(self, related_ebore, group_alltxt):
        """A1 폴리라인 찾기 - IBOX 3mm 우선, 그 다음 EBORE BOX 6mm"""
        print(f"\n=== Finding A1 Polyline ===")
        
        # IBOX 찾기 (group_alltxt에서)
        ibox = None
        for entity in group_alltxt:
            if entity.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
                points = list(entity.points())
                if len(points) == 5 and hasattr(entity.dxf, 'layer') and 'ITEMNO' in entity.dxf.layer.upper():
                    ibox = entity
                    break
        
        if not ibox:
            print("No IBOX found in this group!")
            return None
            
        # IBOX 점들 가져오기
        ibox_points = [(pt[0], pt[1]) for pt in ibox.points()]
        print(f"IBOX found with {len(ibox_points)} points")
        
        # 모든 폴리라인 검사
        found_A1 = None
        min_dist = float('inf')
        candidates_ibox = []  # IBOX 기준 후보
        candidates_ebore = []  # EBORE 기준 후보
        
        for entity in self.msp:
            entity_type = entity.dxftype()
            if entity_type in ['POLYLINE', 'LWPOLYLINE']:  # LINE 제외
                try:
                    points = list(entity.points())
                    point_count = len(points)
                    
                    # 2-3점 체크
                    if 2 <= point_count <= 3:
                        layer = entity.dxf.layer.upper() if hasattr(entity.dxf, 'layer') else 'NO_LAYER'
                        
                        # 레이어 체크 (PL2 또는 GT_1)
                        if 'PL2' in layer or 'GT_1' in layer or 'GT-1' in layer or 'GT1' in layer:
                            # 폴리라인 길이 계산
                            poly_length = self.calculate_polyline_length(entity)
                            
                            # 1. IBOX와의 거리 체크 (3mm 이내)
                            min_dist_to_ibox = float('inf')
                            for poly_point in points:
                                poly_pt = (poly_point[0], poly_point[1])
                                for ibox_pt in ibox_points:
                                    dist = self.calculate_distance(poly_pt, ibox_pt)
                                    if dist < min_dist_to_ibox:
                                        min_dist_to_ibox = dist
                            
                            if min_dist_to_ibox <= 3:
                                candidates_ibox.append({
                                    'entity': entity,
                                    'distance': min_dist_to_ibox,
                                    'layer': layer,
                                    'points': point_count,
                                    'type': entity_type,
                                    'length': poly_length
                                })
                                print(f"  Found candidate near IBOX: {entity_type}, layer: '{layer}', distance: {min_dist_to_ibox:.2f}mm")
                                
                except Exception as e:
                    print(f"  Error reading entity: {e}")
        
        # IBOX 3mm 이내에서 후보가 있으면 가장 가까운 것 선택
        if candidates_ibox:
            candidates_ibox.sort(key=lambda x: x['distance'])
            best_candidate = candidates_ibox[0]
            found_A1 = best_candidate['entity']
            print(f"\n*** A1 SELECTED (IBOX 3mm): {best_candidate['type']}, layer: '{best_candidate['layer']}', distance: {best_candidate['distance']:.2f}mm ***")
        else:
            # IBOX에서 못 찾은 경우 EBORE BOX 기준으로 검색
            print("\nNo A1 found within 3mm of IBOX, checking EBORE BOX 6mm...")
            
            if not related_ebore:
                print("No EBORE text found for this group!")
                return None
            
            # EBORE TEXT의 바운딩 박스 계산
            ebore_box = self.get_text_bounding_box(related_ebore)
            if not ebore_box:
                print("Failed to calculate EBORE text bounding box!")
                return None
                
            print(f"EBORE TEXT: '{related_ebore.dxf.text}'")
            
            # 다시 모든 폴리라인 검사 (EBORE BOX 기준)
            for entity in self.msp:
                entity_type = entity.dxftype()
                if entity_type in ['POLYLINE', 'LWPOLYLINE']:
                    try:
                        points = list(entity.points())
                        point_count = len(points)
                        
                        if 2 <= point_count <= 3:
                            layer = entity.dxf.layer.upper() if hasattr(entity.dxf, 'layer') else 'NO_LAYER'
                            
                            if 'PL2' in layer or 'GT_1' in layer or 'GT-1' in layer or 'GT1' in layer:
                                poly_length = self.calculate_polyline_length(entity)
                                
                                # EBORE BOX 점들과의 거리 체크 (6mm 이내)
                                min_dist_to_box = float('inf')
                                for poly_point in points:
                                    poly_pt = (poly_point[0], poly_point[1])
                                    for box_corner in ebore_box:
                                        dist = self.calculate_distance(poly_pt, box_corner)
                                        if dist < min_dist_to_box:
                                            min_dist_to_box = dist
                                
                                if min_dist_to_box <= 6:
                                    candidates_ebore.append({
                                        'entity': entity,
                                        'distance': min_dist_to_box,
                                        'layer': layer,
                                        'points': point_count,
                                        'type': entity_type,
                                        'length': poly_length
                                    })
                                    
                    except Exception as e:
                        print(f"  Error reading entity: {e}")
            
            # EBORE BOX 6mm 이내에서 가장 가까운 것 선택
            if candidates_ebore:
                candidates_ebore.sort(key=lambda x: x['distance'])
                best_candidate = candidates_ebore[0]
                found_A1 = best_candidate['entity']
                print(f"\n*** A1 SELECTED (EBORE BOX 6mm): {best_candidate['type']}, layer: '{best_candidate['layer']}', distance: {best_candidate['distance']:.2f}mm ***")
            else:
                print("\n*** NO A1 FOUND within 6mm of EBORE BOX! ***")
        
        if found_A1:
            # 가까운 점과 먼 점 계산 (ALLTXT 중심 기준)
            alltxt_bbox = self.get_bounding_box(group_alltxt)
            alltxt_center = (
                (alltxt_bbox[0][0] + alltxt_bbox[2][0]) / 2,
                (alltxt_bbox[0][1] + alltxt_bbox[2][1]) / 2
            )
            
            a1_points = list(found_A1.points())
            
            self.near_point = None
            self.far_point = None
            min_d = float('inf')
            max_d = 0
            
            for pt in a1_points:
                pt_tuple = (pt[0], pt[1])
                d = self.calculate_distance(pt_tuple, alltxt_center)
                if d < min_d:
                    min_d = d
                    self.near_point = pt_tuple
                if d > max_d:
                    max_d = d
                    self.far_point = pt_tuple
        
        return found_A1
    
    def process_dxf_file(self, file_path):
        """DXF 파일 처리"""
        try:
            # 각 파일 처리 시작 시 클래스 변수 초기화
            self.AP1 = None
            self.AP2 = None
            self.original_AP1 = None
            
            self.doc = ezdxf.readfile(file_path)
            self.msp = self.doc.modelspace()
            
            # 1. EBORE 찾기
            ebore_texts = self.find_ebore_texts()
            print(f"EBORE texts found: {len(ebore_texts)}")
            # EBORE 색상 변경
            for ebore in ebore_texts:
                self.set_entity_color(ebore, 4)  # CYAN
            
            # 2. IBOX 찾기
            ibox_polylines = self.find_ibox_polylines(ebore_texts)
            print(f"IBOX polylines found: {len(ibox_polylines)}")
            # IBOX 색상 변경
            for ibox in ibox_polylines:
                self.set_entity_color(ibox, 4)  # CYAN
            
            # 3. ITAG 찾기
            itag_texts = self.find_itag_texts(ibox_polylines)
            print(f"ITAG texts found: {len(itag_texts)}")
            # ITAG 색상 변경
            for itag in itag_texts:
                self.set_entity_color(itag, 4)  # CYAN
            
            # 4. OTEXT 찾기
            otext_texts = self.find_otext_texts(ebore_texts)
            print(f"OTEXT texts found: {len(otext_texts)}")
            # OTEXT 색상 변경
            for otext in otext_texts:
                self.set_entity_color(otext, 4)  # CYAN
            
            # 5. 각 IBOX별로 개별 처리
            print(f"\n=== Processing {len(ibox_polylines)} ITEMNO groups ===")
            
            a1_count = 0
            for idx, ibox in enumerate(ibox_polylines):
                print(f"\n--- Processing ITEMNO group {idx + 1}/{len(ibox_polylines)} ---")
                
                # 이 IBOX와 관련된 엔티티들 찾기
                related_ebore = None
                related_itag = None
                related_otext = None
                
                # IBOX와 가장 가까운 EBORE 찾기
                min_dist = float('inf')
                for ebore in ebore_texts:
                    dist = self.distance_between_entities(ebore, ibox)
                    if dist < min_dist:
                        min_dist = dist
                        related_ebore = ebore
                
                # IBOX와 가장 가까운 ITAG 찾기 (5mm 이내)
                min_dist = float('inf')
                for itag in itag_texts:
                    dist = self.distance_between_entities(itag, ibox)
                    if dist <= 5 and dist < min_dist:
                        min_dist = dist
                        related_itag = itag
                
                # 관련 EBORE가 있으면 그 아래의 OTEXT 찾기
                if related_ebore:
                    ebore_pos = self.get_entity_position(related_ebore)
                    for otext in otext_texts:
                        otext_pos = self.get_entity_position(otext)
                        if otext_pos and ebore_pos and otext_pos[1] < ebore_pos[1]:
                            # X 좌표도 가까운지 확인
                            if abs(otext_pos[0] - ebore_pos[0]) < 10:
                                related_otext = otext
                                break
                
                # 이 그룹의 ALLTXT 구성
                group_alltxt = [ibox]
                if related_ebore:
                    group_alltxt.append(related_ebore)
                if related_itag:
                    group_alltxt.append(related_itag)
                if related_otext:
                    group_alltxt.append(related_otext)
                
                print(f"  Group entities: IBOX + {'+EBORE' if related_ebore else ''}{'+ITAG' if related_itag else ''}{'+OTEXT' if related_otext else ''}")
                
                # 이 그룹의 A1 찾기
                self.AP1 = None  # 각 그룹마다 초기화
                self.AP2 = None
                self.original_AP1 = None
                
                a1_polyline = self.find_a1_polyline(related_ebore, group_alltxt)
                
                if a1_polyline:
                    # A1 처리
                    if self.process_single_a1(a1_polyline, group_alltxt, idx + 1):
                        a1_count += 1
                    else:
                        print("  A1 skipped due to length <= 10mm")
                else:
                    print("  No A1 found for this group")
            
            print(f"\n=== Total A1 found and processed: {a1_count}/{len(ibox_polylines)} ===")
            
            # 파일 저장
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            output_path = os.path.join(
                os.path.dirname(file_path),
                f"{base_name}_TXTB.dxf"
            )
            
            self.doc.saveas(output_path)
            print(f"\nSaved: {output_path}")
            print(f"\nProcessed {len(ibox_polylines)} ITEMNO groups")
            print(f"Found and processed {a1_count} A1 polylines")
            
        except Exception as e:
            print(f"Error processing {file_path}: {str(e)}")
            import traceback
            traceback.print_exc()
    
    def process_single_a1(self, a1_polyline, group_alltxt, group_number):
        """단일 A1 처리"""
        print(f"  Processing A1 for group {group_number}")
        
        # A1의 점들 가져오기
        a1_points = list(a1_polyline.points())
        
        # A1의 길이 확인
        a1_length = self.calculate_polyline_length(a1_polyline)
        if a1_length <= 10:
            print(f"    SKIP: A1 length {a1_length:.2f}mm <= 10mm")
            return False
        
        print(f"    A1 length: {a1_length:.2f}mm (> 10mm, processing...)")
        
        # IBOX 찾기 (group_alltxt에서)
        ibox = None
        for entity in group_alltxt:
            if entity.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
                points = list(entity.points())
                if len(points) == 5 and hasattr(entity.dxf, 'layer') and 'ITEMNO' in entity.dxf.layer.upper():
                    ibox = entity
                    break
        
        # ALLTXT 엔티티들을 이동시키며 간섭 체크 (A1은 삭제됨)
        movement_result = self.find_target_position_and_move_entities(a1_polyline, group_alltxt)
        
        if movement_result:
            dx, dy = movement_result
            if dx != 0 or dy != 0:
                print(f"    ALLTXT moved by ({dx:.2f}, {dy:.2f})")
                
                # 이동 완료 후 흰색 LINE 그리기
                if hasattr(self, 'AP1') and hasattr(self, 'AP2') and hasattr(self, 'original_AP1'):
                    # AG 선의 시작점 결정
                    ag_start = self.AP1  # 기본값: 이동된 AP1
                    
                    # 원래 AP1이 IBOX의 한 점과 일치하는지 확인
                    if ibox:
                        ibox_points = list(ibox.points())
                        ap1_on_ibox = False
                        
                        # 원래 AP1과 IBOX 점들 비교 (0.1mm 이내를 일치로 간주)
                        for point in ibox_points:
                            if self.calculate_distance(self.original_AP1, (point[0], point[1])) < 0.1:
                                ap1_on_ibox = True
                                print(f"    Original AP1 is on IBOX vertex")
                                break
                        
                        if ap1_on_ibox:
                            # 원래 AP1과 AP2 사이의 거리
                            original_dist = self.calculate_distance(self.original_AP1, self.AP2)
                            
                            # 이동된 IBOX의 모든 점 중 AP2에 가장 가까운 점 찾기
                            min_dist_to_ap2 = float('inf')
                            closest_ibox_point = None
                            
                            for point in ibox_points:
                                # 이동된 IBOX 점의 위치
                                moved_point = (point[0] + dx, point[1] + dy)
                                dist_to_ap2 = self.calculate_distance(moved_point, self.AP2)
                                
                                if dist_to_ap2 < min_dist_to_ap2:
                                    min_dist_to_ap2 = dist_to_ap2
                                    closest_ibox_point = moved_point
                            
                            # 가장 가까운 IBOX 점이 원래 AP1보다 AP2에 가까우면 사용
                            if closest_ibox_point and min_dist_to_ap2 < original_dist:
                                ag_start = closest_ibox_point
                                print(f"    Using closer IBOX point for AG line: ({closest_ibox_point[0]:.2f}, {closest_ibox_point[1]:.2f})")
                                print(f"    Distance to AP2: {min_dist_to_ap2:.2f}mm (original: {original_dist:.2f}mm)")
                    
                    # AG 선 그리기
                    white_line = self.msp.add_line(
                        start=(ag_start[0], ag_start[1], 0),    # 결정된 시작점
                        end=(self.AP2[0], self.AP2[1], 0)       # 고정된 AP2
                    )
                    white_line.dxf.layer = 'AG'
                    white_line.dxf.color = 7  # WHITE
                    print(f"    Added white LINE on AG layer: ({ag_start[0]:.2f}, {ag_start[1]:.2f}) to AP2({self.AP2[0]:.2f}, {self.AP2[1]:.2f})")
                    
                    # A2 찾기 (고정된 AP2에서 3mm 내에서 원본 A1과 교차했던 ARROW 레이어 LINE)
                    a2_line = self.find_a2_arrow_line_with_points(a1_points)
                    if a2_line:
                        self.set_entity_color(a2_line, 4)  # CYAN
                        print(f"    A2 found and set to CYAN")
                        
                        # A3 찾기 (A2와 한 점이 접하는 3점 폴리라인)
                        a3_polyline = self.find_a3_polyline(a2_line)
                        if a3_polyline:
                            self.set_entity_color(a3_polyline, 4)  # CYAN
                            print(f"    A3 found and set to CYAN")
                        else:
                            print(f"    No A3 found")
                    else:
                        print(f"    No A2 found")
            else:
                print(f"    ALLTXT kept at original position")
                # 이동하지 않은 경우에도 간섭이 최소인 위치로 이동했을 수 있으므로 확인 필요
                
        print(f"    A1 processed successfully for group {group_number}")
        return True

def main():
    processor = DXFProcessor()
    
    # DXF 파일 선택
    file_paths = processor.select_dxf_files()
    
    if not file_paths:
        print("No files selected.")
        return
    
    # 선택된 각 파일 처리
    for file_path in file_paths:
        print(f"\nProcessing: {file_path}")
        processor.process_dxf_file(file_path)
    
    print("\nAll files processed.")

if __name__ == "__main__":
    main()