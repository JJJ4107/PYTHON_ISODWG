import ezdxf
from pathlib import Path
import tkinter as tk
from tkinter import filedialog
from typing import List, Tuple, Optional
import math
from dataclasses import dataclass
from ezdxf.math import Vec2
import os
from tkinter import messagebox
import numpy as np

# =============== PLTONEWLINE 관련 클래스와 함수들 ===============
@dataclass
class LineInfo:
    entity_type: str
    layer: str
    points: List[Tuple[float, float]]
    width: Optional[float]
    source: str

class DxfModifier:
    def __init__(self, input_file: str):
        self.input_file = Path(input_file)

    def _direct_parse_dxf(self) -> List[LineInfo]:
        lines: List[LineInfo] = []
        try:
            with open(self.input_file, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.readlines()
            i = 0
            while i < len(content):
                line = content[i].strip()
                
                # LWPOLYLINE 처리 추가
                if line == "LWPOLYLINE":
                    layer = "0"
                    const_width = None
                    points = []
                    i += 1
                    
                    # LWPOLYLINE 헤더 정보 파싱
                    while i < len(content):
                        code = content[i].strip()
                        if code == "10":  # 첫 번째 X 좌표를 만나면 좌표 수집 시작
                            break
                        if code == "8":  # Layer
                            i += 1
                            if i < len(content):
                                layer = content[i].strip()
                        elif code == "43":  # Constant width
                            i += 1
                            if i < len(content):
                                const_width = float(content[i].strip())
                        i += 1
                    
                    # 좌표 수집
                    while i < len(content):
                        code = content[i].strip()
                        if code == "10":  # X coordinate
                            x = None
                            y = None
                            i += 1
                            if i < len(content):
                                x = float(content[i].strip())
                            i += 1
                            # 다음은 20 (Y coordinate)이어야 함
                            if i < len(content) and content[i].strip() == "20":
                                i += 1
                                if i < len(content):
                                    y = float(content[i].strip())
                                if x is not None and y is not None:
                                    points.append((x, y))
                        elif code == "0":  # 다음 엔티티 시작
                            break
                        else:
                            i += 1
                    
                    # width가 0.6인 경우만 저장
                    if const_width and const_width == 0.6 and len(points) >= 2:
                        lines.append(LineInfo(
                            entity_type="LWPOLYLINE",
                            layer=layer,
                            points=points,
                            width=const_width,
                            source="direct_parsing"
                        ))
                    i += 1
                    
                elif line == "POLYLINE":
                    layer = "0"
                    start_width: Optional[float] = None
                    end_width: Optional[float] = None
                    i += 1
                    # 헤더 파싱
                    while i < len(content):
                        code = content[i].strip()
                        if code == "VERTEX":
                            break
                        if code == "8":
                            i += 1
                            if i < len(content):
                                layer = content[i].strip()
                        elif code == "40":
                            i += 1
                            if i < len(content):
                                try:
                                    start_width = float(content[i].strip())
                                except ValueError:
                                    start_width = None
                        elif code == "41":
                            i += 1
                            if i < len(content):
                                try:
                                    end_width = float(content[i].strip())
                                except ValueError:
                                    end_width = None
                        i += 1
                    # 꼭지점 파싱
                    points: List[Tuple[float,float]] = []
                    while i < len(content):
                        token = content[i].strip()
                        if token == "VERTEX":
                            x = None; y = None
                            i += 1
                            while i < len(content) and content[i].strip() not in ["VERTEX", "SEQEND"]:
                                code = content[i].strip()
                                if code == "10":
                                    i += 1
                                    if i < len(content):
                                        try:
                                            x = float(content[i].strip())
                                        except ValueError:
                                            x = None
                                elif code == "20":
                                    i += 1
                                    if i < len(content):
                                        try:
                                            y = float(content[i].strip())
                                        except ValueError:
                                            y = None
                                i += 1
                            if x is not None and y is not None:
                                points.append((x,y))
                        elif token == "SEQEND":
                            break
                        else:
                            i += 1
                    width = start_width if start_width and start_width > 0 else end_width
                    # width가 0.6인 경우만 저장
                    if width and width == 0.6 and len(points) >= 2:
                        lines.append(LineInfo(
                            entity_type="POLYLINE",
                            layer=layer,
                            points=points,
                            width=width,
                            source="direct_parsing"
                        ))
                    i += 1
                else:
                    i += 1
        except Exception as e:
            print(f"직접 파싱 중 오류: {e}")
        return lines

    def find_and_modify_green_lines(self, doc):
        direct_lines = self._direct_parse_dxf()
        c_lines_key = set()
        msp = doc.modelspace()
        modified_count = 0
        
        # width가 0.6인 라인들만 필터링
        width_06_lines = [line for line in direct_lines if line.width and line.width == 0.6]
        
        for entity in msp:
            entity_type = entity.dxftype()
            # POLYLINE과 LWPOLYLINE 모두 처리
            if entity_type in ["POLYLINE", "LWPOLYLINE"]:
                if entity_type == "POLYLINE":
                    pts = [(v.dxf.location.x, v.dxf.location.y) for v in entity.vertices]
                elif entity_type == "LWPOLYLINE":
                    pts = [(pt[0], pt[1]) for pt in entity.get_points('xy')]
                else:
                    continue
                    
                key = tuple((round(x,6), round(y,6)) for x,y in pts)
                
                for dl in width_06_lines:
                    # 동일한 엔티티 타입인지도 확인
                    if (dl.entity_type == entity_type and
                        len(dl.points) == len(pts) and 
                        self._points_match(pts, dl.points)):
                        try:
                            entity.dxf.color = 3  # Green
                            entity.dxf.lineweight = 50
                            c_lines_key.add(key)
                            modified_count += 1
                            break
                        except Exception as e:
                            print(f"엔티티 수정 실패 ({entity_type}): {e}")
        
        print(f"width = 0.6인 라인으로 수정된 개수: {modified_count}개")
        return c_lines_key, direct_lines

    def _points_match(self, p1: List[Tuple[float,float]], p2: List[Tuple[float,float]], tol=1e-3) -> bool:
        if len(p1) != len(p2): return False
        for a,b in zip(p1,p2):
            if abs(a[0]-b[0])>tol or abs(a[1]-b[1])>tol:
                return False
        return True

# PLTONEWLINE 유틸리티 함수들
def has_bulge(ent):
    if ent.dxftype() == 'LWPOLYLINE':
        for x, y, bulge in ent.get_points('xyb'):
            if abs(bulge) > 1e-7:
                return True
        return False
    elif ent.dxftype() == 'POLYLINE':
        for v in ent.vertices:
            if hasattr(v.dxf, 'bulge') and abs(v.dxf.bulge) > 1e-7:
                return True
        return False
    return False

def get_bulge_radius(ent):
    pts = polypoints(ent)
    n = len(pts)
    if n < 2:
        return None

    if ent.dxftype() == 'LWPOLYLINE':
        points = list(ent.get_points('xyb'))
        for idx, (x, y, bulge) in enumerate(points[:-1]):
            if abs(bulge) > 1e-7:
                chord = distance(pts[idx], pts[idx+1])
                theta = 4 * math.atan(abs(bulge))
                if theta == 0:
                    continue
                return abs(chord / (2 * math.sin(theta/2)))
    else:
        verts = list(ent.vertices)
        for idx, v in enumerate(verts[:-1]):
            if hasattr(v.dxf, 'bulge') and abs(v.dxf.bulge) > 1e-7:
                chord = distance(pts[idx], pts[idx+1])
                theta = 4 * math.atan(abs(v.dxf.bulge))
                if theta == 0:
                    continue
                return abs(chord / (2 * math.sin(theta/2)))
    return None

def centroid(pts):
    return (sum(p[0] for p in pts)/len(pts), sum(p[1] for p in pts)/len(pts))

def scale_triangle(pts, center, scale):
    return [(center[0]+(x-center[0])*scale, center[1]+(y-center[1])*scale) for x,y in pts]

def distance(p1, p2):
    return math.dist(p1, p2)
          
def draw_line(msp, p1, p2, color=7, layer=None):
    attrib = {"color": color}
    if layer:
        attrib["layer"] = layer
    msp.add_line(p1, p2, dxfattribs=attrib)

def polypoints(ent):
    if ent.dxftype()=='LWPOLYLINE':
        return [(pt[0], pt[1]) for pt in ent.get_points('xy')]
    elif ent.dxftype()=='POLYLINE':
        return [(v.dxf.location.x, v.dxf.location.y) for v in ent.vertices]
    return []

def all_pair_distances(pts):
    return [distance(pts[i], pts[i+1]) for i in range(len(pts)-1)]

def line_exists_between_points(msp, p1, p2, tolerance=1e-6):
    """두 점 사이에 이미 LINE이 존재하는지 확인"""
    for line in msp.query('LINE'):
        start = (line.dxf.start.x, line.dxf.start.y)
        end = (line.dxf.end.x, line.dxf.end.y)
        
        # 양방향 모두 체크
        if ((abs(start[0] - p1[0]) < tolerance and 
             abs(start[1] - p1[1]) < tolerance and
             abs(end[0] - p2[0]) < tolerance and 
             abs(end[1] - p2[1]) < tolerance) or
            (abs(start[0] - p2[0]) < tolerance and 
             abs(start[1] - p2[1]) < tolerance and
             abs(end[0] - p1[0]) < tolerance and 
             abs(end[1] - p1[1]) < tolerance)):
            return True
    return False

# =============== CROSCHK 관련 클래스 ===============
class PipeLayerRenamer:
    def __init__(self):
        self.doc = None
        self.msp = None
        self.pno_array = []
        self.psize_array = []
        self.pbox_entities = []
        
    def distance_2d(self, p1, p2):
        """2D 거리 계산"""
        return math.sqrt((p2[0] - p1[0])**2 + (p2[1] - p1[1])**2)
    
    def find_text_near_point(self, point, radius, layer=None):
        """특정 지점 근처의 텍스트 찾기"""
        texts = []
        for entity in self.msp:
            if entity.dxftype() in ['TEXT', 'MTEXT']:
                if layer and entity.dxf.layer != layer:
                    continue
                    
                if entity.dxftype() == 'TEXT':
                    pos = entity.dxf.insert
                else:  # MTEXT
                    pos = entity.dxf.insert
                    
                if self.distance_2d(point, pos) <= radius:
                    texts.append(entity)
        return texts
    
    def find_headers_near_text(self, search_text, search_radius=100):
        """특정 텍스트 근처에서 헤더 찾기"""
        headers = {'PT': None, 'ITEM': None, 'MATERIAL': None, 'SIZE': None}
        
        # 먼저 search_text 찾기
        base_text = None
        for entity in self.msp:
            if entity.dxftype() in ['TEXT', 'MTEXT']:
                text_content = entity.dxf.text if entity.dxftype() == 'TEXT' else entity.text
                if search_text in text_content:
                    base_text = entity
                    break
        
        if not base_text:
            return headers
        
        base_pos = base_text.dxf.insert
        
        # 근처에서 헤더 찾기
        for entity in self.msp:
            if entity.dxftype() in ['TEXT', 'MTEXT']:
                text_content = entity.dxf.text if entity.dxftype() == 'TEXT' else entity.text
                pos = entity.dxf.insert
                
                if self.distance_2d(base_pos, pos) <= search_radius:
                    for header in headers:
                        if header in text_content.upper():
                            headers[header] = entity
                            # 헤더 색상을 RED로 변경
                            entity.dxf.color = 1  # RED
                            
        return headers
    
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
        
        # 디버깅: 같은 줄의 모든 텍스트 출력
        print(f"     같은 줄의 텍스트들 (Y 오차 ≤ {y_tolerance}mm):")
        for x, text, _, y in nearby_texts:
            y_diff = abs(y - pipe_pos[1])
            print(f"       X={x:.1f}, Y={y:.1f} (차이={y_diff:.2f}mm): '{text}'")
        
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
    
    def extract_pipe_info(self, pipe_entity, pt_x, size_x):
        """PIPE 엔티티에서 PT와 SIZE 정보 추출"""
        pipe_pos = pipe_entity.dxf.insert
        pipe_y = pipe_pos[1]
        
        # PT 값 찾기 (PIPE -X 20mm 내)
        pt_texts = self.find_text_near_point((pt_x, pipe_y), 20)
        pt_value = None
        for text in pt_texts:
            content = text.dxf.text if text.dxftype() == 'TEXT' else text.text
            if content.strip().isdigit():
                pt_value = int(content.strip())
                break
        
        # SIZE 값 찾기 (PIPE +X 85mm)
        size_texts = self.find_text_near_point((size_x, pipe_y), 20)
        size_value = None
        for text in size_texts:
            content = text.dxf.text if text.dxftype() == 'TEXT' else text.text
            # 문자가 포함되지 않은 순수 숫자만
            if content.strip().isdigit():
                size_value = int(content.strip())
                break
                
        return pt_value, size_value
    
    def find_polylines_with_5_points(self):
        """5개 점을 가진 폴리라인 찾기 (점간 거리 합 13.5~14.5)"""
        pbox_list = []
        
        for entity in self.msp:
            if entity.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
                points = []
                
                if entity.dxftype() == 'LWPOLYLINE':
                    points = list(entity.get_points('xy'))
                else:  # POLYLINE
                    for vertex in entity.vertices:
                        points.append((vertex.dxf.location.x, vertex.dxf.location.y))
                
                if len(points) == 5:
                    # 점간 거리 합 계산
                    total_dist = 0
                    for i in range(4):
                        total_dist += self.distance_2d(points[i], points[i+1])
                    
                    if 13.5 <= total_dist <= 14.5:
                        pbox_list.append((entity, points))
                        # RED 색상으로 변경
                        entity.dxf.color = 1  # RED
                        
        return pbox_list
    
    def find_nearest_pno(self, pbox_center):
        """PBOX 중심에서 가장 가까운 PNO 찾기"""
        if len(self.pno_array) < 2:
            return None, None
            
        min_dist = float('inf')
        nearest_idx = 1  # 1번 제외하고 2번부터
        
        for i in range(1, len(self.pno_array)):
            pno = self.pno_array[i]
            # PNO 텍스트 위치 찾기
            for entity in self.msp:
                if entity.dxftype() in ['TEXT', 'MTEXT']:
                    content = entity.dxf.text if entity.dxftype() == 'TEXT' else entity.text
                    if content.strip() == str(pno):
                        pos = entity.dxf.insert
                        dist = self.distance_2d(pbox_center, pos)
                        if dist < min_dist:
                            min_dist = dist
                            nearest_idx = i
                            dpno_entity = entity
                            
        return nearest_idx, dpno_entity if 'dpno_entity' in locals() else None
    
    def get_text_slope(self, text_entity):
        """텍스트 엔티티의 기울기 구하기"""
        if text_entity.dxftype() == 'TEXT':
            rotation = text_entity.dxf.rotation
        else:  # MTEXT
            rotation = text_entity.dxf.rotation if hasattr(text_entity.dxf, 'rotation') else 0
            
        return rotation
    
    def find_multiple_polylines_near_pbox(self, pbox_center, radius, max_count=3):
        """PBOX 중심에서 가까운 순서대로 최대 max_count개의 2-3점 폴리라인 찾기"""
        polyline_distances = []
        
        for entity in self.msp:
            if entity.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
                poly_points = []
                
                if entity.dxftype() == 'LWPOLYLINE':
                    poly_points = list(entity.get_points('xy'))
                else:
                    for vertex in entity.vertices:
                        poly_points.append((vertex.dxf.location.x, vertex.dxf.location.y))
                
                if 2 <= len(poly_points) <= 3:
                    # 폴리라인의 모든 점과 PBOX 중심 사이의 최소 거리
                    min_dist = float('inf')
                    for pp in poly_points:
                        dist = self.distance_2d(pbox_center, pp)
                        if dist < min_dist:
                            min_dist = dist
                    
                    if min_dist <= radius:
                        polyline_distances.append((min_dist, entity, poly_points))
        
        # 거리순으로 정렬
        polyline_distances.sort(key=lambda x: x[0])
        
        # 최대 max_count개만 반환
        result = []
        for i, (dist, entity, points) in enumerate(polyline_distances[:max_count]):
            entity.dxf.color = 1  # RED
            result.append((entity, points))
        
        return result
    
    def find_pipe_layer_entities_near_polyline(self, polyline_points, radius=1):
        """폴리라인 근처의 PIPE 레이어 엔티티 찾기 (점과 선분 모두 확인)"""
        found_entities = set()  # 중복 제거를 위해 set 사용
        
        # 각 폴리라인 점에서 PIPE 엔티티 찾기
        for point in polyline_points:
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
                            pipe_points = list(entity.get_points('xy'))
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
    
    def find_farthest_point_from_pbox(self, g1_points, pbox_center):
        """PBOX 중심에서 가장 먼 G1 점 찾기"""
        max_dist = 0
        farthest_point = None
        
        for point in g1_points:
            dist = self.distance_2d(point, pbox_center)
            if dist > max_dist:
                max_dist = dist
                farthest_point = point
                    
        return farthest_point
    
    def find_pipe_layer_entities_near_point(self, point, radius=1):
        """특정 점 근처의 PIPE 레이어 엔티티 찾기"""
        pipe_entities = []
        
        for entity in self.msp:
            if entity.dxf.layer == 'PIPE':
                # 엔티티의 대표 점 찾기
                if hasattr(entity, 'dxf') and hasattr(entity.dxf, 'insert'):
                    pos = entity.dxf.insert
                elif hasattr(entity, 'dxf') and hasattr(entity.dxf, 'start'):
                    pos = entity.dxf.start
                elif entity.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
                    # 폴리라인의 첫 점 사용
                    if entity.dxftype() == 'LWPOLYLINE':
                        points = list(entity.get_points('xy'))
                        if points:
                            pos = points[0]
                        else:
                            continue
                    else:
                        vertices = list(entity.vertices)
                        if vertices:
                            pos = (vertices[0].dxf.location.x, vertices[0].dxf.location.y)
                        else:
                            continue
                else:
                    continue
                    
                if self.distance_2d(point, pos) <= radius:
                    pipe_entities.append(entity)
                    
        return pipe_entities
    
    def find_pipe_layer_polylines_near_points(self, points, radius=3):
        """PBOX 각 점 근처를 지나가는 PIPE 레이어 폴리라인 찾기"""
        found_entities = []
        
        for point in points:
            min_dist = float('inf')
            closest_entity = None
            
            for entity in self.msp:
                if entity.dxf.layer == 'PIPE' and entity.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
                    # 폴리라인의 점들 가져오기
                    if entity.dxftype() == 'LWPOLYLINE':
                        poly_points = list(entity.get_points('xy'))
                    else:
                        poly_points = []
                        for vertex in entity.vertices:
                            poly_points.append((vertex.dxf.location.x, vertex.dxf.location.y))
                    
                    # 각 선분에 대해 점과의 거리 계산
                    for i in range(len(poly_points) - 1):
                        p1 = poly_points[i]
                        p2 = poly_points[i + 1]
                        
                        # 선분과 점 사이의 최단 거리 계산
                        dist = self.point_to_line_distance(point, p1, p2)
                        
                        if dist <= radius and dist < min_dist:
                            min_dist = dist
                            closest_entity = entity
            
            if closest_entity:
                found_entities.append(closest_entity)
                        
        return found_entities
    
    def point_to_line_distance(self, point, line_start, line_end):
        """점과 선분 사이의 최단 거리 계산"""
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
    
    def process_croschk(self, doc, msp):
        """CROSCHK 처리 - doc과 msp를 매개변수로 받음"""
        self.doc = doc
        self.msp = msp
        
        print("\n" + "="*60)
        print("CROSCHK 처리 시작...")
        print("="*60)
        
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
            print(f"   텍스트 내용: {erec_text.dxf.text if erec_text.dxftype() == 'TEXT' else erec_text.text}")
            
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
        
        # 4. 5점 폴리라인 찾기
        print("4. 5점 폴리라인(PBOX) 검색...")
        self.pbox_entities = self.find_polylines_with_5_points()
        print(f"   {len(self.pbox_entities)}개 PBOX 찾음")
        
        # 5. 각 PBOX 처리
        for idx, (pbox, points) in enumerate(self.pbox_entities):
            print(f"5-{idx+1}. PBOX #{idx+1} 처리...")
            
            # PBOX 중심점 계산
            center_x = sum(p[0] for p in points) / len(points)
            center_y = sum(p[1] for p in points) / len(points)
            pbox_center = (center_x, center_y)
            
            # 가장 가까운 PNO 찾기 (1번 제외)
            pno_idx, dpno_entity = self.find_nearest_pno(pbox_center)
            if not dpno_entity:
                print("   DPNO를 찾을 수 없음 - 이 PBOX는 건너뜀")
                continue
            
            # PSIZE가 있는지 확인
            if pno_idx >= len(self.psize_array):
                print("   대응하는 PSIZE가 없음 - 이 PBOX는 건너뜀")
                continue
                
            print(f"   가장 가까운 PNO: {self.pno_array[pno_idx]}, SIZE: {self.psize_array[pno_idx]}")
            
            # 찾은 PNO 텍스트를 CYAN으로 변경
            dpno_entity.dxf.color = 4  # CYAN
            print(f"   PNO {self.pno_array[pno_idx]} 텍스트를 CYAN으로 변경")
            
            # DPNO 기울기 확인
            slope = self.get_text_slope(dpno_entity)
            
            print(f"   DPNO 기울기: {slope}°")
            
            new_layer_name = f"PIPE_{self.psize_array[pno_idx]}"
            
            if slope == 0:
                # 기울기가 0인 경우: PBOX 중심에서 가까운 순서대로 최대 3개의 G1 찾기
                print("   기울기 0: PBOX 중심에서 10mm 반경 내 2-3점 폴리라인 검색 (최대 3개)...")
                g1_polylines = self.find_multiple_polylines_near_pbox(pbox_center, 10, max_count=3)
                
                if not g1_polylines:
                    print("   G1 폴리라인을 찾을 수 없음")
                    continue
                
                print(f"   {len(g1_polylines)}개의 G1 폴리라인 찾음")
                
                # 각 G1에 대해 PIPE 찾기 시도
                pipe_found = False
                for g1_idx, (g1_entity, g1_points) in enumerate(g1_polylines):
                    print(f"   G1 #{g1_idx+1} ({len(g1_points)}점) 검사 중...")
                    
                    # G1 점들에서 1mm 내의 PIPE 레이어 엔티티 찾기 (점과 선분 모두)
                    pipe_entities = self.find_pipe_layer_entities_near_polyline(g1_points, 1)
                    
                    if pipe_entities:
                        print(f"   G1 #{g1_idx+1}에서 {len(pipe_entities)}개의 PIPE 레이어 찾음")
                        
                        for entity in pipe_entities:
                            # 새 레이어가 없으면 생성
                            if new_layer_name not in self.doc.layers:
                                self.doc.layers.new(name=new_layer_name)
                            
                            # 레이어 변경
                            entity.dxf.layer = new_layer_name
                            print(f"   레이어 변경: PIPE → {new_layer_name}")
                        
                        pipe_found = True
                        break  # PIPE를 찾았으므로 다음 G1은 검사하지 않음
                    else:
                        print(f"   G1 #{g1_idx+1}에서 PIPE를 찾을 수 없음")
                
                if not pipe_found:
                    print(f"   {len(g1_polylines)}개의 G1 모두에서 PIPE를 찾을 수 없음")
                    
            else:
                # 기울기가 0이 아닌 경우: PBOX 점 근처를 지나가는 PIPE 레이어 폴리라인 찾기
                print("   기울기 ≠ 0: 3mm 반경에서 선분이 지나가는 PIPE 레이어 폴리라인 검색...")
                pipe_entities = self.find_pipe_layer_polylines_near_points(points, 3)
                
                if not pipe_entities:
                    print("   PIPE 레이어 폴리라인을 찾을 수 없음")
                    continue
                
                for entity in pipe_entities:
                    # 새 레이어가 없으면 생성
                    if new_layer_name not in self.doc.layers:
                        self.doc.layers.new(name=new_layer_name)
                    
                    # 레이어 변경
                    entity.dxf.layer = new_layer_name
                    print(f"   레이어 변경: PIPE → {new_layer_name}")
        
        print("\nCROSCHK 처리 완료!")
        return True

# =============== 통합 처리 함수 ===============
def process_dxf_integrated(filepath: str):
    """PLTONEWLINE과 CROSCHK를 순차적으로 실행하는 통합 함수"""
    print(f"\n📁 통합 처리 시작: {Path(filepath).name}")
    
    # 1단계: PLTONEWLINE 처리
    print("\n[1단계] PLTONEWLINE 처리 중...")
    doc = ezdxf.readfile(filepath)
    modifier = DxfModifier(filepath)
    c_keys, direct_ls = modifier.find_and_modify_green_lines(doc)
    msp = doc.modelspace()

    # 1. C_LINES 분류: width 0.6 -> ELBO or PIPE
    for dl in direct_ls:
        if not dl.width or abs(dl.width-0.6)>1e-3: continue
        pts = dl.points
        n = len(pts)
        
        # POLYLINE과 LWPOLYLINE 모두 처리하도록 수정
        for ent in msp:
            if ent.dxftype() not in ['POLYLINE', 'LWPOLYLINE']:
                continue
                
            # 각 타입에 맞게 좌표 추출
            if ent.dxftype() == 'POLYLINE':
                epts = [(v.dxf.location.x, v.dxf.location.y) for v in ent.vertices]
            else:  # LWPOLYLINE
                epts = [(pt[0], pt[1]) for pt in ent.get_points('xy')]
                
            # 좌표가 일치하는 엔티티를 찾아서 레이어 설정
            if len(epts)==n and all(abs(epts[i][0]-pts[i][0])<1e-4 and abs(epts[i][1]-pts[i][1])<1e-4 for i in range(n)):
                # bulge가 있으면 ELBO, 없으면 PIPE 레이어로 설정
                ent.dxf.layer = 'ELBO' if has_bulge(ent) else 'PIPE'
                break

    # 2. PL 처리: 다양한 점 개수별 레이어 변경
    for ent in list(msp):
        if ent.dxftype() not in ['LWPOLYLINE','POLYLINE']: continue
        pts = polypoints(ent)
        n = len(pts)
        key = tuple((round(x,6),round(y,6)) for x,y in pts)
        if ent.dxftype()=='POLYLINE' and key in c_keys: continue
        if getattr(ent.dxf,'const_width',0)!=0: continue

        # 3점 polyline (PL3)
        if n==3:
            if has_bulge(ent):
                r = get_bulge_radius(ent)
                if r and 2 <= r <= 3:
                    ent.dxf.layer = 'weldno'
                    ent.dxf.color = 2
                elif r and 5 <= r <= 8:
                    ent.dxf.layer = 'instno'
                    ent.dxf.color = 2
                else:
                    ent.dxf.layer = 'ARROW'
                    ent.dxf.color = 7
            else:
                if 1.9 <= distance(pts[0], pts[1]) <= 2.1:
                    ent.dxf.layer = 'ARROW'
                    ent.dxf.color = 7
            ent.dxf.layer = 'ARROW'

        # 4점 polyline (PL4) - FALL 조건 추가
        elif n==4:
            # 점간 거리 계산 (마지막 점에서 첫 점으로의 거리 포함)
            dists = all_pair_distances(pts)
            last_to_first = distance(pts[3], pts[0])
            
            # FALL 패턴 확인 (허용 오차 0.1mm)
            tolerance = 0.1
            if (len(dists) >= 3 and
                abs(dists[0] - 7.445) <= tolerance and  # 점1→점2
                abs(dists[1] - 1.612) <= tolerance and  # 점2→점3
                abs(dists[2] - 7.592) <= tolerance and  # 점3→점4
                abs(last_to_first - 0) <= tolerance):   # 점4→점1
                ent.dxf.layer = 'FALL'
                ent.dxf.color = 2
            else:
                ent.dxf.layer = 'PL4'
                ent.dxf.color = 7

        # 5점 polyline (PL5)
        elif n==5:
            dists = all_pair_distances(pts)
            if all(d<=4.5 for d in dists):
                ent.dxf.layer = 'itemno'
            elif any(d>=30 for d in dists):
                ent.dxf.layer = 'spoolno'
            else:
                ent.dxf.layer = 'PL5'
            ent.dxf.color = 7

        # 6점 polyline (PL6)
        elif n==6:
            dists = all_pair_distances(pts)
            total_dist = sum(dists)  # 모든 점간 거리의 합
            
            # 길이값 합계 기준으로 레이어 지정
            if 10 <= total_dist <= 11:
                ent.dxf.layer = 'SFW'
                ent.dxf.color = 2
            elif 17.5 <= total_dist <= 22:
                ent.dxf.layer = 'REDU'
                ent.dxf.color = 2
            elif 16 <= total_dist <= 16.5:
                ent.dxf.layer = 'REDU'
                ent.dxf.color = 2
            elif 17 <= total_dist <= 17.3:
                ent.dxf.layer = 'FLOW'
                ent.dxf.color = 2
            elif 12 <= total_dist <= 13.3:
                ent.dxf.layer = 'OLET'
                ent.dxf.color = 2
            elif any(d<=1.0 for d in dists):
                ent.dxf.layer = 'FLAN'
                ent.dxf.color = 2
            elif sum(1 for d in dists if 6<=d<=15)>=2:
                ent.dxf.layer = 'VALV'
                ent.dxf.color = 2
            else:
                ent.dxf.layer = 'PL6'
                ent.dxf.color = 7

        elif n==7:
            dists = all_pair_distances(pts)
            mov_idx = [i for i,d in enumerate(dists) if 3<=d<=5]
            if len(mov_idx)>=2:
                ent.dxf.layer = 'MOV'
                ent.dxf.color = 2
            elif all(d<=2.2 for d in dists):
                ent.dxf.layer='weld'
                ent.dxf.color=2
            else:
                ent.dxf.layer = 'PL7'
                ent.dxf.color = 4

        elif n==8:
            dists = all_pair_distances(pts)
            if sum(1 for d in dists if 1.5<=d<=4)>=5:
                ent.dxf.layer = 'WOLET'
                ent.dxf.color = 2
            else:
                ent.dxf.layer = 'PL8'
                ent.dxf.color = 7

        elif n==9:
            dists = all_pair_distances(pts)
            if all(d<=5 for d in dists):
                ent.dxf.layer = 'CV'
                ent.dxf.color = 2
            else:
                ent.dxf.layer = 'PL9'
                ent.dxf.color = 7

        elif n==10:
            dists = all_pair_distances(pts)
            total_dist = sum(dists)  # 모든 점간 거리의 합
            
            if 13.5 <= total_dist <= 14.5:
                ent.dxf.layer = 'CAP'
                ent.dxf.color = 2  # Yellow
            else:
                ent.dxf.layer = 'PL10'
                ent.dxf.color = 7

        elif n==12:
            dists = all_pair_distances(pts)
            total_dist = sum(dists)  # 모든 점간 거리의 합
            
            if 34 <= total_dist <= 35:
                ent.dxf.layer = 'SFW'
                ent.dxf.color = 2  # Yellow
            else:
                ent.dxf.layer = 'PL12'
                ent.dxf.color = 7

        elif n==2:
            ent.dxf.layer = 'PL2'
            ent.dxf.color = 7
    
    # 3. TEXT 레이어 지정
    for ent in msp.query('TEXT'):
        txt = ent.dxf.text.upper()
        if '<' in txt and '>' in txt:
            ent.dxf.layer = 'itemno'
        elif any(tag in txt for tag in ['EL+','EL-','FL+','FL-']):
            ent.dxf.layer = 'ELEV'
        elif any(letter in txt for letter in ['F','G']):
            ent.dxf.layer = 'FLAN'
        elif 'FALL' in txt:
            ent.dxf.layer = 'FALL'

    # 4. SP3, SP7 처리 (레이어만 지정)
    for ent in msp:
        if ent.dxftype() not in ['LWPOLYLINE','POLYLINE']: continue
        pts = polypoints(ent)
        n = len(pts)
        # ARROW 선긋기 - 중복 체크 추가
        if n==3:
            dists = all_pair_distances(pts)
            if all(1.5 <= d <= 2.3 for d in dists) and distance(pts[0], pts[2]) <= 1:
                # LINE이 이미 존재하는지 확인
                if not line_exists_between_points(msp, pts[2], pts[0]):
                    # 원래 삼각형 세 변
                    line20 = msp.add_line(pts[2], pts[0], dxfattribs={'color': 7, 'layer': 'ARROW'})
                    print(f"새 LINE 추가: {pts[2]} -> {pts[0]}")
                else:
                    print(f"LINE 이미 존재: {pts[2]} -> {pts[0]} (SKIP)")
        elif n==7:
            dists = all_pair_distances(pts)
            if any(d>30 for d in dists):
                ent.dxf.layer = 'SUPP'

    # 5. PIPE 레이어 처리 (삭제 X, color 만 처리)
    for ent in list(msp):
        if ent.dxftype() in ['LWPOLYLINE','POLYLINE'] and ent.dxf.layer=='PIPE':
            ent.dxf.color = 3

    # FALL 레이어의 2점 폴리라인 색상을 흰색으로 변경
    for ent in list(msp):
        if ent.dxftype() in ['LWPOLYLINE','POLYLINE'] and ent.dxf.layer=='FALL':
            pts = polypoints(ent)
            if len(pts) == 2:
                ent.dxf.color = 7  # 흰색

    for txt in msp.query('TEXT'):
        txt.dxf.color = 2
        txt.dxf.style = "ARIAL"

    def set_width_by_f_x(msp):
        # 1. FABRICATION MATERIALS 텍스트의 'F' 문자 위치(X좌표) 찾기
        f_x = None
        for txt in msp.query('TEXT'):
            if txt.dxf.text and txt.dxf.text.strip().upper().startswith('F'):
                f_x = txt.dxf.insert[0]
                break  # 첫 'F'만 찾으면 됨

        if f_x is None:
            print("FABRICATION MATERIALS의 F 위치를 찾지 못했습니다.")
            return

        # 2. 전체 TEXT를 돌면서 F 기준 왼쪽/오른쪽에 width 적용
        for txt in msp.query('TEXT'):
            if not txt.dxf.text:
                continue
            x = txt.dxf.insert[0]
            # 폭은 모두 float으로 비교
            if x < f_x - 1e-4:  # F의 X보다 왼쪽
                txt.dxf.width = 0.87
            else:  # F 포함 오른쪽(포함)
                txt.dxf.width = 0.8
            txt.dxf.style = "ARIAL"
            txt.dxf.color = 2

        if "ARIAL" not in doc.styles:
            doc.styles.new("ARIAL", dxfattribs={"font": "arial.ttf"})
    
    set_width_by_f_x(msp)
    
    print("✅ PLTONEWLINE 처리 완료")
    
    # 2단계: CROSCHK 처리
    print("\n[2단계] CROSCHK 처리 중...")
    pipe_renamer = PipeLayerRenamer()
    croschk_success = pipe_renamer.process_croschk(doc, msp)
    
    if croschk_success:
        print("✅ CROSCHK 처리 완료")
    else:
        print("❌ CROSCHK 처리 중 오류 발생")
    
    # 파일 저장
    outname = Path(filepath).with_stem(Path(filepath).stem + '_Integrated')
    doc.saveas(str(outname))
    print(f"\n✅ 통합 처리 완료! 저장: {outname}")
    
    return str(outname)

def select_files_and_process():
    root = tk.Tk()
    root.withdraw()
    files = filedialog.askopenfilenames(filetypes=[('DXF files','*.dxf')])
    for f in files:
        process_dxf_integrated(f)

if __name__ == '__main__':
    select_files_and_process()