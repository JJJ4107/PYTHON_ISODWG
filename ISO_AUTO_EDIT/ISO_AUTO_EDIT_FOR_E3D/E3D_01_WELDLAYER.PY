import ezdxf
from ezdxf.math import Vec2
import math
import os
import tkinter as tk
from tkinter import filedialog, messagebox
import numpy as np

class PipeLayerRenamer:
    def __init__(self):
        self.doc = None
        self.msp = None
        self.pno_array = []
        self.psize_array = []
        self.pbox_entities = []
        
    def get_2d_pos(self, pos):
        """3D 좌표를 2D로 변환"""
        if hasattr(pos, '__len__') and len(pos) > 2:
            return (pos[0], pos[1])
        return pos
    
    def has_bulge(self, entity):
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
        
    def distance_2d(self, p1, p2):
        """2D 거리 계산 (3D 좌표도 자동으로 2D로 변환)"""
        # 3D 좌표를 2D로 변환
        if len(p1) > 2:
            p1 = (p1[0], p1[1])
        if len(p2) > 2:
            p2 = (p2[0], p2[1])
        return math.sqrt((p2[0] - p1[0])**2 + (p2[1] - p1[1])**2)
    
    def find_text_near_point(self, point, radius, layer=None):
        """특정 지점 근처의 텍스트 찾기"""
        # 3D 좌표를 2D로 변환
        if len(point) > 2:
            point = (point[0], point[1])
            
        texts = []
        for entity in self.msp:
            if entity.dxftype() in ['TEXT', 'MTEXT']:
                if layer and entity.dxf.layer != layer:
                    continue
                    
                if entity.dxftype() == 'TEXT':
                    pos = entity.dxf.insert
                    # 3D 좌표를 2D로 변환
                    if len(pos) > 2:
                        pos = (pos[0], pos[1])
                else:  # MTEXT
                    pos = entity.dxf.insert
                    # 3D 좌표를 2D로 변환
                    if len(pos) > 2:
                        pos = (pos[0], pos[1])
                    
                if self.distance_2d(point, pos) <= radius:
                    texts.append(entity)
        return texts
    
    def find_angle_brackets_near_materials(self, material_type="FABRICATION"):
        """FABRICATION/ERECTION MATERIALS의 첫 문자 X 좌표 근처에서 <> 포함 텍스트 찾기"""
        angle_bracket_texts = []
        
        # MATERIALS 텍스트 찾기
        materials_text = None
        materials_x = None
        
        search_patterns = []
        if material_type == "FABRICATION":
            search_patterns = ['FABRICATION MATERIALS']
        elif material_type == "ERECTION":
            search_patterns = ['ERECTION MATERIALS', 'ERECTION', 'MATERIALS']
        
        for entity in self.msp:
            if entity.dxftype() in ['TEXT', 'MTEXT']:
                text_content = entity.dxf.text if entity.dxftype() == 'TEXT' else entity.text
                
                for pattern in search_patterns:
                    if pattern in text_content.upper():
                        materials_text = entity
                        materials_pos = entity.dxf.insert
                        # 첫 문자의 X 좌표 (텍스트 시작점과 동일하다고 가정)
                        materials_x = materials_pos[0]
                        print(f"   {material_type} MATERIALS 찾음, 첫 문자의 X 좌표: {materials_x:.2f}")
                        break
                
                if materials_text:
                    break
        
        if not materials_x:
            return angle_bracket_texts
        
        # 첫 문자의 X 좌표에서 -15mm까지 범위에서 <> 포함 텍스트 찾기
        search_max_x = materials_x - 15
        print(f"   <> 텍스트 검색 범위: X[0 ~ {search_max_x:.2f}] (MATERIALS X - 15mm)")
        
        for entity in self.msp:
            if entity.dxftype() in ['TEXT', 'MTEXT']:
                text_content = entity.dxf.text if entity.dxftype() == 'TEXT' else entity.text
                pos = entity.dxf.insert
                
                # X 좌표가 0부터 (MATERIALS X - 15mm)까지이고 <>를 포함하는 경우
                if 0 <= pos[0] <= search_max_x and '<' in text_content and '>' in text_content:
                    angle_bracket_texts.append((entity, pos))
                    entity.dxf.color = 3  # GREEN
                    print(f"   <> 텍스트 찾음 at ({pos[0]:.1f}, {pos[1]:.1f}): {text_content}")
        
        return angle_bracket_texts
    
    def find_pt_number_near_angle_bracket(self, angle_bracket_entity, pt_numbers):
        """<> 텍스트 근처에서 PT 번호 찾기 (가장 가까운 것 우선)"""
        bracket_pos = angle_bracket_entity.dxf.insert
        candidate_pts = []
        
        print(f"     <> 텍스트 위치: ({bracket_pos[0]:.2f}, {bracket_pos[1]:.2f})")
        print(f"     PT 번호 검색 범위: X[{bracket_pos[0]-5:.2f} ~ {bracket_pos[0]+20:.2f}], Y[{bracket_pos[1]-5:.2f} ~ {bracket_pos[1]+20:.2f}]")
        
        # <> 텍스트 X좌표에서 -5mm ~ +20mm, Y좌표에서 -5mm ~ +20mm 범위 내에서 숫자 텍스트 찾기
        for entity in self.msp:
            if entity.dxftype() in ['TEXT', 'MTEXT']:
                text_content = entity.dxf.text if entity.dxftype() == 'TEXT' else entity.text
                content = text_content.strip()
                
                # 숫자이고 1~5 사이인지 확인
                if content.isdigit():
                    num_value = int(content)
                    if 1 <= num_value <= 5:
                        pos = entity.dxf.insert
                        
                        # 위치 확인: X는 <>에서 -5mm ~ +20mm 범위, Y는 -5mm ~ +20mm 범위
                        x_in_range = (bracket_pos[0] - 5) <= pos[0] <= (bracket_pos[0] + 20)
                        y_in_range = (bracket_pos[1] - 5) <= pos[1] <= (bracket_pos[1] + 20)
                        
                        if x_in_range and y_in_range:
                            # 거리 계산
                            distance = self.distance_2d(bracket_pos, pos)
                            x_offset = pos[0] - bracket_pos[0]  # 음수면 왼쪽, 양수면 오른쪽
                            y_offset = pos[1] - bracket_pos[1]  # 음수면 아래, 양수면 위
                            print(f"       숫자 '{num_value}' at ({pos[0]:.2f}, {pos[1]:.2f}), X 오프셋: {x_offset:.2f}mm, Y 오프셋: {y_offset:.2f}mm, 거리: {distance:.2f}mm")
                            
                            # PT 번호 배열에 있는지 확인
                            if num_value in pt_numbers:
                                slope = self.get_text_slope(entity)
                                candidate_pts.append({
                                    'pt_number': num_value,
                                    'entity': entity,
                                    'position': pos,
                                    'slope': slope,
                                    'distance': distance,
                                    'bracket_pos': bracket_pos  # <> 텍스트 위치 추가
                                })
                                print(f"       → PT 배열에 있음!")
                            else:
                                print(f"       → PT 배열에 없음 (PT 배열: {pt_numbers})")
        
        # 거리순으로 정렬 (가장 가까운 것부터)
        candidate_pts.sort(key=lambda x: x['distance'])
        
        # 가장 가까운 것만 선택하고 색상 변경
        found_pts = []
        if candidate_pts:
            # 가장 가까운 PT 선택
            closest_pt = candidate_pts[0]
            closest_pt['entity'].dxf.color = 4  # CYAN
            found_pts.append(closest_pt)
            print(f"     PT {closest_pt['pt_number']} 선택됨 at ({closest_pt['position'][0]:.1f}, {closest_pt['position'][1]:.1f}), "
                  f"거리: {closest_pt['distance']:.1f}mm, 기울기: {closest_pt['slope']}°")
        else:
            print("     PT 번호를 찾을 수 없음")
        
        return found_pts
    
    def create_gbox_from_texts(self, bracket_pos, pt_pos):
        """<> 텍스트와 PT 텍스트 위치로부터 GBOX 생성"""
        # 두 텍스트의 중심점 계산
        center_x = (bracket_pos[0] + pt_pos[0]) / 2
        center_y = (bracket_pos[1] + pt_pos[1]) / 2
        
        # 두 텍스트 간의 폭과 높이 계산
        width = abs(pt_pos[0] - bracket_pos[0])
        height = abs(pt_pos[1] - bracket_pos[1])
        
        # 최소 크기 보장 (너무 작으면 기본값 사용)
        min_size = 5.0  # 5mm
        if width < min_size:
            width = min_size
        if height < min_size:
            height = min_size
        
        # GBOX의 4개 모서리 점 계산
        half_width = width / 2
        half_height = height / 2
        
        corners = [
            (center_x - half_width, center_y + half_height),  # 좌상
            (center_x + half_width, center_y + half_height),  # 우상
            (center_x + half_width, center_y - half_height),  # 우하
            (center_x - half_width, center_y - half_height)   # 좌하
        ]
        
        print(f"     GBOX 생성:")
        print(f"       중심: ({center_x:.2f}, {center_y:.2f})")
        print(f"       크기: {width:.2f} x {height:.2f} mm")
        print(f"       모서리 점들:")
        for i, corner in enumerate(corners):
            print(f"         모서리 {i+1}: ({corner[0]:.2f}, {corner[1]:.2f})")
        
        return corners, (center_x, center_y)
    
    def find_g1_from_gbox_corners(self, corners, max_attempts=5):
        """GBOX의 4개 모서리에서 G1 찾기 (여러 시도)"""
        all_g1_candidates = []
        search_radius = 15  # 15mm
        
        # 각 모서리에서 G1 후보 찾기
        for corner_idx, corner in enumerate(corners):
            print(f"       모서리 {corner_idx+1}에서 G1 검색...")
            
            for entity in self.msp:
                if entity.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
                    # 곡선 제외
                    if self.has_bulge(entity):
                        continue
                    
                    # 점 개수 확인
                    poly_points = []
                    if entity.dxftype() == 'LWPOLYLINE':
                        poly_points = [(p[0], p[1]) for p in entity.get_points('xy')]
                    else:
                        for vertex in entity.vertices:
                            poly_points.append((vertex.dxf.location.x, vertex.dxf.location.y))
                    
                    if 2 <= len(poly_points) <= 3:
                        # 폴리라인과 모서리 점 사이의 최소 거리
                        min_dist = float('inf')
                        for pp in poly_points:
                            dist = self.distance_2d(corner, pp)
                            if dist < min_dist:
                                min_dist = dist
                        
                        if min_dist <= search_radius:
                            all_g1_candidates.append({
                                'entity': entity,
                                'points': poly_points,
                                'distance': min_dist,
                                'corner_idx': corner_idx
                            })
        
        # 거리순으로 정렬
        all_g1_candidates.sort(key=lambda x: x['distance'])
        
        # 중복 제거 (같은 엔티티는 한 번만)
        unique_g1_list = []
        seen_entities = set()
        
        for candidate in all_g1_candidates:
            if candidate['entity'] not in seen_entities:
                seen_entities.add(candidate['entity'])
                unique_g1_list.append(candidate)
        
        print(f"       총 {len(unique_g1_list)}개의 G1 후보 발견")
        
        # 최대 max_attempts개 반환
        return unique_g1_list[:max_attempts]
    
    def process_pt_based_on_slope_with_gbox(self, pt_info, psize_array):
        """GBOX를 사용하여 PT 텍스트의 기울기에 따라 PIPE 레이어 처리"""
        pt_number = pt_info['pt_number']
        pt_entity = pt_info['entity']
        pt_pos = pt_info['position']
        slope = pt_info['slope']
        bracket_pos = pt_info.get('bracket_pos', pt_pos)  # <> 위치 가져오기
        
        # PT 번호에 해당하는 SIZE 찾기
        pt_index = None
        for idx, pno in enumerate(self.pno_array):
            if pno == pt_number:
                pt_index = idx
                break
        
        if pt_index is None or pt_index >= len(psize_array):
            print(f"     PT {pt_number}에 대한 SIZE를 찾을 수 없음")
            return
        
        pipe_size = psize_array[pt_index]
        new_layer_name = f"PIPE_{pipe_size}"
        print(f"     PT {pt_number}의 SIZE: {pipe_size}")
        
        if slope != 0:
            # 기울기가 0이 아니면 PT 위치에서 3mm 내에서 PIPE 레이어 찾기
            print(f"     기울기 ≠ 0: PT 위치에서 3mm 반경 내에서 PIPE 레이어 검색...")
            pipe_entities = self.find_pipe_layer_entities_near_point(pt_pos, 3)
            
            if pipe_entities:
                print(f"     {len(pipe_entities)}개의 PIPE 레이어 찾음")
                for entity in pipe_entities:
                    # 새 레이어가 없으면 생성
                    if new_layer_name not in self.doc.layers:
                        self.doc.layers.new(name=new_layer_name)
                    
                    # 레이어 변경 및 색상을 RED로 변경
                    entity.dxf.layer = new_layer_name
                    entity.dxf.color = 1  # RED
                    print(f"     레이어 변경: PIPE → {new_layer_name} (색상: RED)")
            else:
                print(f"     PIPE 레이어를 찾을 수 없음")
        else:
            # 기울기가 0이면 GBOX 사용
            print(f"     기울기 = 0: GBOX 방식으로 G1 검색...")
            
            # GBOX 생성
            gbox_corners, gbox_center = self.create_gbox_from_texts(bracket_pos, pt_pos)
            
            # GBOX 모서리에서 G1 찾기 (최대 5개)
            g1_candidates = self.find_g1_from_gbox_corners(gbox_corners, max_attempts=5)
            
            pipe_found = False
            
            for g1_idx, g1_info in enumerate(g1_candidates):
                if pipe_found:
                    break
                
                g1_entity = g1_info['entity']
                g1_points = g1_info['points']
                
                print(f"       G1 후보 #{g1_idx+1}: {len(g1_points)}점 폴리라인, 거리={g1_info['distance']:.2f}mm")
                
                # G1 점들에서 1mm 내의 PIPE 레이어 엔티티 찾기
                pipe_entities = self.find_pipe_layer_entities_near_polyline(g1_points, 1)
                
                if pipe_entities:
                    print(f"       → {len(pipe_entities)}개의 PIPE 레이어 찾음!")
                    
                    for entity in pipe_entities:
                        # 새 레이어가 없으면 생성
                        if new_layer_name not in self.doc.layers:
                            self.doc.layers.new(name=new_layer_name)
                        
                        # 레이어 변경 및 색상을 RED로 변경
                        entity.dxf.layer = new_layer_name
                        entity.dxf.color = 1  # RED
                        print(f"       레이어 변경: PIPE → {new_layer_name} (색상: RED)")
                    
                    # G1 색상도 변경 (시각적 확인용)
                    g1_entity.dxf.color = 5  # BLUE
                    pipe_found = True
                else:
                    print(f"       → 이 G1에서 PIPE를 찾을 수 없음, 다음 G1 시도...")
            
            if not pipe_found:
                print(f"       모든 G1 후보에서 PIPE를 찾을 수 없음")
    
    def find_pipe_layer_entities_near_polyline(self, polyline_points, radius=1):
        """폴리라인 근처의 PIPE 레이어 엔티티 찾기 (점과 선분 모두 확인)"""
        found_entities = set()  # 중복 제거를 위해 set 사용
        
        # 각 폴리라인 점에서 PIPE 엔티티 찾기
        for point in polyline_points:
            # 3D 좌표를 2D로 변환
            if len(point) > 2:
                point = (point[0], point[1])
                
            for entity in self.msp:
                if entity.dxf.layer == 'PIPE':
                    found = False
                    
                    # 1. 점 기반 검색
                    if hasattr(entity, 'dxf') and hasattr(entity.dxf, 'insert'):
                        if self.distance_2d(point, entity.dxf.insert) <= radius:
                            found = True
                    elif hasattr(entity, 'dxf') and hasattr(entity.dxf, 'start'):
                        if self.distance_2d(point, entity.dxf.start) <= radius:
                            found = True
                    
                    # 2. 폴리라인인 경우 점과 선분 모두 확인
                    if entity.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
                        if entity.dxftype() == 'LWPOLYLINE':
                            pipe_points = [(p[0], p[1]) for p in entity.get_points('xy')]
                        else:
                            pipe_points = []
                            for vertex in entity.vertices:
                                pipe_points.append((vertex.dxf.location.x, vertex.dxf.location.y))
                        
                        # 점 확인
                        for pp in pipe_points:
                            if self.distance_2d(point, pp) <= radius:
                                found = True
                                break
                        
                        # 선분 확인
                        if not found:
                            for i in range(len(pipe_points) - 1):
                                dist = self.point_to_line_distance(point, pipe_points[i], pipe_points[i+1])
                                if dist <= radius:
                                    found = True
                                    break
                    
                    if found:
                        found_entities.add(entity)
        
        return list(found_entities)
    
    def find_pipe_layer_entities_near_point(self, point, radius=1):
        """특정 점 근처의 PIPE 레이어 엔티티 찾기 (점과 선분 모두 확인)"""
        # 3D 좌표를 2D로 변환
        if len(point) > 2:
            point = (point[0], point[1])
            
        pipe_entities = []
        found_entities_set = set()  # 중복 제거를 위해
        
        for entity in self.msp:
            if entity.dxf.layer == 'PIPE':
                found = False
                
                # 엔티티의 대표 점 확인
                if hasattr(entity, 'dxf') and hasattr(entity.dxf, 'insert'):
                    if self.distance_2d(point, entity.dxf.insert) <= radius:
                        found = True
                elif hasattr(entity, 'dxf') and hasattr(entity.dxf, 'start'):
                    if self.distance_2d(point, entity.dxf.start) <= radius:
                        found = True
                
                # 폴리라인인 경우 점과 선분 모두 확인
                if entity.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
                    if entity.dxftype() == 'LWPOLYLINE':
                        poly_points = [(p[0], p[1]) for p in entity.get_points('xy')]
                    else:
                        poly_points = []
                        for vertex in entity.vertices:
                            poly_points.append((vertex.dxf.location.x, vertex.dxf.location.y))
                    
                    # 각 점 확인
                    for pp in poly_points:
                        if self.distance_2d(point, pp) <= radius:
                            found = True
                            break
                    
                    # 각 선분 확인
                    if not found and len(poly_points) > 1:
                        for i in range(len(poly_points) - 1):
                            dist = self.point_to_line_distance(point, poly_points[i], poly_points[i+1])
                            if dist <= radius:
                                found = True
                                break
                
                if found and entity not in found_entities_set:
                    found_entities_set.add(entity)
                    pipe_entities.append(entity)
                    
        return pipe_entities
    
    def point_to_line_distance(self, point, line_start, line_end):
        """점과 선분 사이의 최단 거리 계산"""
        # 3D 좌표를 2D로 변환
        if len(point) > 2:
            point = (point[0], point[1])
        if len(line_start) > 2:
            line_start = (line_start[0], line_start[1])
        if len(line_end) > 2:
            line_end = (line_end[0], line_end[1])
            
        x0, y0 = point
        x1, y1 = line_start
        x2, y2 = line_end
        
        # 선분의 길이 제곱
        line_length_sq = (x2 - x1)**2 + (y2 - y1)**2
        
        if line_length_sq == 0:
            # 선분이 점인 경우
            return self.distance_2d(point, line_start)
        
        # 점을 선분에 투영
        t = max(0, min(1, ((x0 - x1) * (x2 - x1) + (y0 - y1) * (y2 - y1)) / line_length_sq))
        
        # 투영된 점
        projection = (x1 + t * (x2 - x1), y1 + t * (y2 - y1))
        
        # 점과 투영된 점 사이의 거리
        return self.distance_2d(point, projection)
    
    def get_text_slope(self, text_entity):
        """텍스트 엔티티의 기울기 구하기"""
        if text_entity.dxftype() == 'TEXT':
            rotation = text_entity.dxf.rotation
        else:  # MTEXT
            rotation = text_entity.dxf.rotation if hasattr(text_entity.dxf, 'rotation') else 0
            
        return rotation
    
    def find_pipe_items_in_area(self, base_text, y_offset=-50, x_min=-10, x_max=80):
        """특정 텍스트 기준으로 지정된 범위 내에서 PIPE 항목 찾기"""
        pipe_items = []
        if not base_text:
            return pipe_items
            
        base_pos = base_text.dxf.insert
        
        # 지정된 범위 내에서 PIPE 텍스트 찾기
        for entity in self.msp:
            if entity.dxftype() in ['TEXT', 'MTEXT']:
                text_content = entity.dxf.text if entity.dxftype() == 'TEXT' else entity.text
                pos = entity.dxf.insert
                
                # Y: base_pos에서 -50mm 아래까지
                # X: base_pos에서 -10mm ~ +80mm 범위
                y_in_range = (base_pos[1] + y_offset) <= pos[1] <= base_pos[1]
                x_in_range = (base_pos[0] + x_min) <= pos[0] <= (base_pos[0] + x_max)
                
                if y_in_range and x_in_range and 'PIPE' in text_content.upper():
                    pipe_items.append(entity)
                        
        # Y 좌표로 정렬 (위에서 아래로)
        pipe_items.sort(key=lambda e: e.dxf.insert[1], reverse=True)
        
        return pipe_items
    
    def extract_pipe_info_from_pipe_text(self, pipe_entity):
        """PIPE 텍스트에서 직접 PT와 SIZE 정보 추출"""
        pipe_text = pipe_entity.dxf.text if pipe_entity.dxftype() == 'TEXT' else pipe_entity.text
        pipe_pos = pipe_entity.dxf.insert
        
        print(f"     PIPE 텍스트 at ({pipe_pos[0]:.1f}, {pipe_pos[1]:.1f}): {pipe_text}")
        
        # PIPE 텍스트 주변에서 숫자 찾기
        pt_value = None
        size_value = None
        
        # Y 좌표 허용 오차를 더 엄격하게 설정 (1mm)
        y_tolerance = 1.0
        
        # PIPE 텍스트 근처에서 모든 텍스트 검색
        nearby_texts = []
        for entity in self.msp:
            if entity.dxftype() in ['TEXT', 'MTEXT']:
                if entity == pipe_entity:
                    continue
                pos = entity.dxf.insert
                # PIPE 텍스트와 정확히 같은 줄(Y 좌표 차이 1mm 이내)에 있는 텍스트
                if abs(pos[1] - pipe_pos[1]) <= y_tolerance:
                    text_content = entity.dxf.text if entity.dxftype() == 'TEXT' else entity.text
                    nearby_texts.append((pos[0], text_content.strip(), entity, pos[1]))
        
        # X 좌표로 정렬
        nearby_texts.sort(key=lambda x: x[0])
        
        # PIPE 왼쪽에서 가장 가까운 숫자 찾기 (PT)
        left_numbers = [(x, text, entity) for x, text, entity, _ in nearby_texts 
                        if x < pipe_pos[0] and text.isdigit()]
        if left_numbers:
            # 가장 가까운 것 선택
            left_numbers.sort(key=lambda item: pipe_pos[0] - item[0])
            pt_value = int(left_numbers[0][1])
            left_numbers[0][2].dxf.color = 1  # RED
            print(f"     PT 찾음: {pt_value} at X={left_numbers[0][0]:.1f}")
        
        # PIPE 오른쪽에서 가장 가까운 숫자 찾기 (SIZE)
        right_numbers = [(x, text, entity) for x, text, entity, _ in nearby_texts 
                         if x > pipe_pos[0] and text.isdigit()]
        if right_numbers:
            # 가장 가까운 것 선택
            right_numbers.sort(key=lambda item: item[0] - pipe_pos[0])
            size_value = int(right_numbers[0][1])
            right_numbers[0][2].dxf.color = 1  # RED
            print(f"     SIZE 찾음: {size_value} at X={right_numbers[0][0]:.1f}")
        
        if pt_value is None or size_value is None:
            print(f"     주의: PT={pt_value}, SIZE={size_value} - 누락된 값이 있습니다!")
                    
        return pt_value, size_value
    
    # TEE 관련 함수들
    def find_pipe_layer_polylines(self):
        """PIPE 텍스트가 포함된 레이어를 가진 2점 폴리라인 찾기"""
        pipe_polylines = []
        
        for entity in self.msp:
            if entity.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
                # 레이어 이름에 PIPE가 포함되어 있는지 확인
                if 'PIPE' in entity.dxf.layer.upper():
                    # 폴리라인의 점들 가져오기
                    if entity.dxftype() == 'LWPOLYLINE':
                        points = [(p[0], p[1]) for p in entity.get_points('xy')]
                    else:
                        points = []
                        for vertex in entity.vertices:
                            points.append((vertex.dxf.location.x, vertex.dxf.location.y))
                    
                    # 2점 폴리라인인지 확인
                    if len(points) == 2:
                        pipe_polylines.append((entity, points))
        
        return pipe_polylines
    
    def find_3way_intersections(self, pipe_polylines):
        """3개의 폴리라인이 만나는 교차점 찾기"""
        intersections = []
        tolerance = 0.3  # 0.3mm 허용 오차
        
        # 모든 폴리라인의 끝점들을 수집
        all_endpoints = []
        for entity, points in pipe_polylines:
            for point in points:
                all_endpoints.append((point, entity))
        
        # 각 끝점에서 근처의 다른 끝점들을 찾기
        for i, (point1, entity1) in enumerate(all_endpoints):
            nearby_entities = set()
            nearby_entities.add(entity1)
            
            for j, (point2, entity2) in enumerate(all_endpoints):
                if i != j and self.distance_2d(point1, point2) <= tolerance:
                    nearby_entities.add(entity2)
            
            # 정확히 3개의 서로 다른 폴리라인이 만나는 경우
            if len(nearby_entities) == 3:
                # 이미 찾은 교차점인지 확인
                is_duplicate = False
                for existing_intersection, _ in intersections:
                    if self.distance_2d(point1, existing_intersection) <= tolerance:
                        is_duplicate = True
                        break
                
                if not is_duplicate:
                    intersections.append((point1, list(nearby_entities)))
        
        return intersections
    
    def get_polyline_length(self, entity):
        """폴리라인의 길이 계산"""
        if entity.dxftype() == 'LWPOLYLINE':
            points = [(p[0], p[1]) for p in entity.get_points('xy')]
        else:
            points = []
            for vertex in entity.vertices:
                points.append((vertex.dxf.location.x, vertex.dxf.location.y))
        
        if len(points) < 2:
            return 0
        
        total_length = 0
        for i in range(len(points) - 1):
            total_length += self.distance_2d(points[i], points[i + 1])
        
        return total_length
    
    def find_pl2_polyline_near_point(self, point, radius=0.5):
        """특정 점 근처의 PL2 레이어 폴리라인 찾기"""
        for entity in self.msp:
            if entity.dxftype() in ['POLYLINE', 'LWPOLYLINE'] and entity.dxf.layer == 'PL2':
                # 폴리라인의 점들 가져오기
                if entity.dxftype() == 'LWPOLYLINE':
                    points = [(p[0], p[1]) for p in entity.get_points('xy')]
                else:
                    points = []
                    for vertex in entity.vertices:
                        points.append((vertex.dxf.location.x, vertex.dxf.location.y))
                
                # 각 점이 교차점 근처에 있는지 확인
                for p in points:
                    if self.distance_2d(point, p) <= radius:
                        return entity, points
        
        return None, None
    
    def find_x_text_near_point(self, point, radius=20):
        """특정 점 근처에서 'x'를 포함하는 텍스트 찾기"""
        for entity in self.msp:
            if entity.dxftype() in ['TEXT', 'MTEXT']:
                text_content = entity.dxf.text if entity.dxftype() == 'TEXT' else entity.text
                pos = entity.dxf.insert
                
                # 3D 좌표를 2D로 변환
                if len(pos) > 2:
                    pos = (pos[0], pos[1])
                
                if self.distance_2d(point, pos) <= radius and 'x' in text_content.lower():
                    return entity, text_content
        
        return None, None
    
    def extract_numbers_from_x_text(self, text):
        """'x'를 포함하는 텍스트에서 앞뒤 숫자 추출"""
        # 소문자 x로 변환하여 처리
        text = text.lower()
        
        if 'x' not in text:
            return None, None
        
        # x를 기준으로 분리
        parts = text.split('x')
        
        if len(parts) != 2:
            return None, None
        
        # 앞부분에서 숫자 추출
        t1 = None
        for char in parts[0][::-1]:  # 뒤에서부터 검색
            if char.isdigit():
                if t1 is None:
                    t1 = char
                else:
                    t1 = char + t1
            elif t1 is not None:
                break
        
        # 뒷부분에서 숫자 추출
        t3 = None
        for char in parts[1]:  # 앞에서부터 검색
            if char.isdigit():
                if t3 is None:
                    t3 = char
                else:
                    t3 = t3 + char
            elif t3 is not None:
                break
        
        # 숫자로 변환
        t1 = int(t1) if t1 else None
        t3 = int(t3) if t3 else None
        
        return t1, t3
    
    def process_tee_connections(self):
        """TEE 연결부 처리 - 3방향 교차점 찾기 및 레이어 변경"""
        print("\n6. TEE 연결부 처리...")
        
        # PIPE 텍스트가 포함된 레이어의 2점 폴리라인 찾기
        pipe_polylines = self.find_pipe_layer_polylines()
        print(f"   PIPE 레이어의 2점 폴리라인: {len(pipe_polylines)}개")
        
        if not pipe_polylines:
            print("   PIPE 레이어의 2점 폴리라인을 찾을 수 없음")
            return
        
        # 3개의 폴리라인이 만나는 교차점 찾기
        intersections = self.find_3way_intersections(pipe_polylines)
        print(f"   3방향 교차점: {len(intersections)}개")
        
        for idx, (intersection_point, tee_entities) in enumerate(intersections):
            print(f"\n   교차점 #{idx+1} at ({intersection_point[0]:.2f}, {intersection_point[1]:.2f})")
            
            # 3개의 폴리라인을 길이순으로 정렬
            tee_lengths = []
            for entity in tee_entities:
                length = self.get_polyline_length(entity)
                tee_lengths.append((entity, length))
            
            # 길이순으로 정렬 (내림차순)
            tee_lengths.sort(key=lambda x: x[1], reverse=True)
            
            if len(tee_lengths) < 3:
                print("     3개 미만의 폴리라인 - 건너뜀")
                continue
            
            tee1_entity = tee_lengths[0][0]  # 가장 긴 것
            tee2_entity = tee_lengths[1][0]  # 다음 긴 것
            tee3_entity = tee_lengths[2][0]  # 가장 짧은 것
            
            print(f"     TEE1 길이: {tee_lengths[0][1]:.2f}mm")
            print(f"     TEE2 길이: {tee_lengths[1][1]:.2f}mm")
            print(f"     TEE3 길이: {tee_lengths[2][1]:.2f}mm")
            
            # 교차점에서 0.5mm 내의 PL2 레이어 폴리라인(G1) 찾기
            g1_entity, g1_points = self.find_pl2_polyline_near_point(intersection_point, 0.5)
            
            if not g1_entity:
                print("     PL2 레이어(G1)를 찾을 수 없음")
                continue
            
            print(f"     G1(PL2) 폴리라인 찾음: {len(g1_points)}점")
            
            # G1의 교차점에서 먼 쪽 끝점 찾기
            if len(g1_points) >= 2:
                dist1 = self.distance_2d(intersection_point, g1_points[0])
                dist2 = self.distance_2d(intersection_point, g1_points[-1])
                far_point = g1_points[0] if dist1 > dist2 else g1_points[-1]
                print(f"     G1의 먼 쪽 끝점: ({far_point[0]:.2f}, {far_point[1]:.2f})")
                
                # 먼 쪽 끝점에서 20mm 내의 'x' 포함 텍스트 찾기
                x_entity, x_text = self.find_x_text_near_point(far_point, 20)
                
                if x_entity:
                    print(f"     'x' 텍스트 찾음: '{x_text}'")
                    
                    # x 앞뒤의 숫자 추출
                    t1, t3 = self.extract_numbers_from_x_text(x_text)
                    
                    if t1 is not None and t3 is not None:
                        print(f"     T1 = {t1}, T3 = {t3}")
                        
                        # 레이어 이름 변경
                        new_layer_tee1 = f"TEE_{t1}"
                        new_layer_tee2 = f"TEE_{t1}"  # TEE2도 T1 사용
                        new_layer_tee3 = f"TEE_{t3}"
                        
                        # 새 레이어가 없으면 생성
                        if new_layer_tee1 not in self.doc.layers:
                            self.doc.layers.new(name=new_layer_tee1)
                        if new_layer_tee3 not in self.doc.layers:
                            self.doc.layers.new(name=new_layer_tee3)
                        
                        # TEE1 레이어 변경
                        tee1_entity.dxf.layer = new_layer_tee1
                        tee1_entity.dxf.color = 2  # YELLOW
                        print(f"     TEE1 레이어 변경: {new_layer_tee1}")
                        
                        # TEE2 레이어 변경
                        tee2_entity.dxf.layer = new_layer_tee2
                        tee2_entity.dxf.color = 2  # YELLOW
                        print(f"     TEE2 레이어 변경: {new_layer_tee2}")
                        
                        # TEE3 레이어 변경
                        tee3_entity.dxf.layer = new_layer_tee3
                        tee3_entity.dxf.color = 2  # YELLOW
                        print(f"     TEE3 레이어 변경: {new_layer_tee3}")
                        
                    else:
                        print(f"     'x' 텍스트에서 숫자를 추출할 수 없음")
                else:
                    print(f"     'x' 포함 텍스트를 찾을 수 없음")
            else:
                print(f"     G1 폴리라인의 점이 부족함")
    
    def reset_state(self):
        """각 파일 처리 전 상태 초기화"""
        self.doc = None
        self.msp = None
        self.pno_array = []
        self.psize_array = []
        self.pbox_entities = []
    
    def process_dxf(self, filename):
        """DXF 파일 처리"""
        try:
            # 각 파일 처리 전 상태 초기화
            self.reset_state()
            
            self.doc = ezdxf.readfile(filename)
            self.msp = self.doc.modelspace()
            
            print(f"\n처리 중: {os.path.basename(filename)}")
            print("-" * 60)
            
            # 1. FABRICATION MATERIALS 처리
            print("1. FABRICATION MATERIALS 검색...")
            fab_text = None
            for entity in self.msp:
                if entity.dxftype() in ['TEXT', 'MTEXT']:
                    text_content = entity.dxf.text if entity.dxftype() == 'TEXT' else entity.text
                    if 'FABRICATION MATERIALS' in text_content:
                        fab_text = entity
                        break
            
            if fab_text:
                print("   FABRICATION MATERIALS 찾음, 지정 범위에서 PIPE 검색...")
                # -Y 50mm, +X -10~80mm 범위에서 PIPE 찾기
                pipe_items = self.find_pipe_items_in_area(fab_text, y_offset=-50, x_min=-10, x_max=80)
                print(f"   {len(pipe_items)}개의 PIPE 항목 발견")
                
                for pipe in pipe_items:
                    pt, size = self.extract_pipe_info_from_pipe_text(pipe)
                    if pt is not None and size is not None:
                        self.pno_array.append(pt)
                        self.psize_array.append(size)
                        print(f"   PT: {pt}, SIZE: {size}")
            
            # 2. ERECTION MATERIALS 처리
            print("2. ERECTION MATERIALS 검색...")
            erec_text = None
            erec_candidates = []
            
            for entity in self.msp:
                if entity.dxftype() in ['TEXT', 'MTEXT']:
                    text_content = entity.dxf.text if entity.dxftype() == 'TEXT' else entity.text
                    if 'ERECTION' in text_content.upper() and 'MATERIALS' in text_content.upper():
                        erec_candidates.append((entity, text_content))
                        if 'ERECTION MATERIALS' in text_content:
                            erec_text = entity
                            break
            
            if not erec_text and erec_candidates:
                # 정확한 매치가 없으면 첫 번째 후보 사용
                erec_text = erec_candidates[0][0]
                print(f"   정확한 매치 없음, 후보 사용: {erec_candidates[0][1]}")
            
            if erec_text:
                erec_pos = erec_text.dxf.insert
                print(f"   ERECTION MATERIALS 찾음 at ({erec_pos[0]:.2f}, {erec_pos[1]:.2f})")
                
                # -Y 50mm, +X -10~80mm 범위에서 PIPE 찾기
                pipe_items = self.find_pipe_items_in_area(erec_text, y_offset=-50, x_min=-10, x_max=80)
                print(f"   {len(pipe_items)}개의 PIPE 항목 발견")
                
                for pipe in pipe_items:
                    pt, size = self.extract_pipe_info_from_pipe_text(pipe)
                    if pt is not None and size is not None:
                        self.pno_array.append(pt)
                        self.psize_array.append(size)
                        print(f"   PT: {pt}, SIZE: {size}")
            
            # 3. 찾은 PNO, PSIZE 텍스트 색상 변경 (이미 extract_pipe_info_from_pipe_text에서 처리됨)
            print("3. PNO, PSIZE 색상 변경 완료 (추출 시 자동 처리됨)")
            
            # 4. FABRICATION MATERIALS 근처에서 <> 텍스트 찾기
            print("4. FABRICATION MATERIALS 근처에서 <> 포함 텍스트 검색...")
            fab_angle_brackets = self.find_angle_brackets_near_materials("FABRICATION")
            
            if fab_angle_brackets:
                print(f"   {len(fab_angle_brackets)}개의 <> 포함 텍스트 찾음")
                
                # 각 <> 텍스트 근처에서 PT 번호 찾고 처리
                for idx, (bracket_entity, bracket_pos) in enumerate(fab_angle_brackets):
                    print(f"   FABRICATION <> 텍스트 #{idx+1} 처리...")
                    
                    # PT 번호 찾기 (1~5 사이, PT 배열에 있는 것)
                    found_pts = self.find_pt_number_near_angle_bracket(bracket_entity, self.pno_array)
                    
                    if not found_pts:
                        print("   PT 번호를 찾을 수 없음 - G1 선택 불가")
                        continue
                    
                    # 각 PT 번호에 대해 처리 (GBOX 방식 사용)
                    for pt_info in found_pts:
                        self.process_pt_based_on_slope_with_gbox(pt_info, self.psize_array)
            else:
                print("   FABRICATION MATERIALS 근처에서 <> 포함 텍스트를 찾을 수 없음")
            
            # 5. ERECTION MATERIALS 근처에서 <> 텍스트 찾기
            print("5. ERECTION MATERIALS 근처에서 <> 포함 텍스트 검색...")
            erec_angle_brackets = self.find_angle_brackets_near_materials("ERECTION")
            
            if erec_angle_brackets:
                print(f"   {len(erec_angle_brackets)}개의 <> 포함 텍스트 찾음")
                
                # 각 <> 텍스트 근처에서 PT 번호 찾고 처리
                for idx, (bracket_entity, bracket_pos) in enumerate(erec_angle_brackets):
                    print(f"   ERECTION <> 텍스트 #{idx+1} 처리...")
                    
                    # PT 번호 찾기 (1~5 사이, PT 배열에 있는 것)
                    found_pts = self.find_pt_number_near_angle_bracket(bracket_entity, self.pno_array)
                    
                    if not found_pts:
                        print("   PT 번호를 찾을 수 없음 - G1 선택 불가")
                        continue
                    
                    # 각 PT 번호에 대해 처리 (GBOX 방식 사용)
                    for pt_info in found_pts:
                        self.process_pt_based_on_slope_with_gbox(pt_info, self.psize_array)
            else:
                print("   ERECTION MATERIALS 근처에서 <> 포함 텍스트를 찾을 수 없음")
            
            # 6. TEE 연결부 처리
            self.process_tee_connections()
            
            # 7. 파일 저장
            output_filename = filename.replace('.dxf', '_WDLA.dxf')
            self.doc.saveas(output_filename)
            print(f"\n처리 완료! 저장됨: {output_filename}")
            
            return True, output_filename
            
        except Exception as e:
            print(f"오류 발생: {str(e)}")
            import traceback
            traceback.print_exc()
            return False, None

def main():
    """메인 함수"""
    print("="*60)
    print("파이프 레이어 자동 재명명 프로그램 (GBOX 기반)")
    print("="*60)
    print("이 프로그램은 여러 개의 DXF 도면에서 파이프 정보를 추출하고")
    print("PIPE 레이어를 자동으로 PIPE_SIZE로 재명명합니다.")
    print("")
    print("주요 기능:")
    print("1. FABRICATION/ERECTION MATERIALS에서 PT와 SIZE 정보 추출")
    print("2. <> 텍스트와 PT 텍스트로 GBOX 생성")
    print("3. GBOX 4개 모서리에서 G1 검색 (최대 5개 시도)")
    print("4. PIPE 레이어를 PIPE_SIZE로 변경")
    print("5. TEE 연결부 자동 처리")
    print("")
    print("색상 표시:")
    print("- RED: 수정된 PIPE 엔티티")
    print("- GREEN: <> 포함 텍스트")
    print("- CYAN: 선택된 PT 번호")
    print("- BLUE: PIPE를 찾은 G1")
    print("- YELLOW: TEE 연결부")
    print("="*60)
    
    root = tk.Tk()
    root.withdraw()
    
    # 여러 파일 선택
    filenames = filedialog.askopenfilenames(
        title="처리할 DXF 파일들을 선택하세요 (여러 개 선택 가능)",
        filetypes=[("DXF files", "*.dxf"), ("All files", "*.*")]
    )
    
    if not filenames:
        print("파일이 선택되지 않았습니다.")
        return
    
    print(f"\n선택된 파일 개수: {len(filenames)}개")
    
    # 처리 결과 저장
    results = []
    successful_files = []
    failed_files = []
    
    # 각 파일 처리
    processor = PipeLayerRenamer()
    
    for i, filename in enumerate(filenames):
        print(f"\n{'='*60}")
        print(f"[{i+1}/{len(filenames)}] 파일 처리 시작")
        print(f"{'='*60}")
        
        success, output_file = processor.process_dxf(filename)
        
        if success:
            successful_files.append((filename, output_file))
            results.append(f"✓ {os.path.basename(filename)} → {os.path.basename(output_file)}")
        else:
            failed_files.append(filename)
            results.append(f"✗ {os.path.basename(filename)} - 처리 실패")
    
    # 최종 결과 출력
    print(f"\n{'='*60}")
    print("전체 처리 결과")
    print(f"{'='*60}")
    print(f"총 {len(filenames)}개 파일 중:")
    print(f"- 성공: {len(successful_files)}개")
    print(f"- 실패: {len(failed_files)}개")
    print(f"\n상세 결과:")
    for result in results:
        print(result)
    
    root.destroy()

if __name__ == "__main__":
    main()