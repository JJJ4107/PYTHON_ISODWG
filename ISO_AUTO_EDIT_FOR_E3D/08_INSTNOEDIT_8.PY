import ezdxf
from ezdxf.math import Vec3
from ezdxf.entities import DXFEntity
import tkinter as tk
from tkinter import filedialog
import math
import numpy as np
from typing import List, Tuple, Optional, Union

class IntegratedDXFProcessor:
    def __init__(self):
        self.doc = None
        self.msp = None
        self.used_entities = set()  # 이미 사용된 엔티티 추적
        self.a1_a2_a3_entities = set()  # A1, A2, A3로 식별된 엔티티 추적
        self.instno_circles = []  # 찾은 INSTNO 원들 저장
        self.instno_data = {}  # 각 INSTNO에 대한 관련 데이터 저장
        self.a2_process_status = {}  # A2 처리 상태 저장 {a2_entity: (success, has_tbox_itag)}
        
    def select_dxf_files(self) -> List[str]:
        """DXF 파일 선택 다이얼로그 열기 (첫 번째 파일 방식)"""
        root = tk.Tk()
        root.withdraw()
        
        file_paths = filedialog.askopenfilenames(
            title="DXF 파일 선택",
            filetypes=[("DXF files", "*.dxf"), ("All files", "*.*")]
        )
        
        return list(file_paths)
    
    def load_dxf(self, filepath: str):
        """DXF 파일 로드"""
        self.doc = ezdxf.readfile(filepath)
        self.msp = self.doc.modelspace()
    
    def get_entity_points(self, entity: DXFEntity) -> List[Vec3]:
        """엔티티에서 점들을 안전하게 추출"""
        try:
            if entity.dxftype() == "LWPOLYLINE":
                points = list(entity.get_points('xy'))
                return [Vec3(p[0], p[1], 0) for p in points]
            elif entity.dxftype() == "POLYLINE":
                points = []
                for vertex in entity.vertices:
                    points.append(Vec3(vertex.dxf.location))
                return points
            else:
                return []
        except Exception as e:
            print(f"Error getting points: {e}")
            return []
    
    # ========== 1단계: 첫 번째 파일의 메서드들 ==========
    
    def find_instno_circles(self) -> List[DXFEntity]:
        """INSTNO 레이어의 원(CIRCLE) 찾기"""
        instno_circles = []
        
        for entity in self.msp:
            if entity.dxf.layer == "INSTNO":
                if entity.dxftype() == "CIRCLE":
                    instno_circles.append(entity)
        
        return instno_circles
    
    def find_a2_polylines(self, center: Vec3, radius: float) -> List[DXFEntity]:
        """INSTNO 원과 관련된 2점 또는 3점 폴리라인들 찾기 (A2) - 여러 개 반환"""
        print(f"    - Looking for A2 polylines near circle: center={center}, radius={radius:.2f}")
        
        candidates = []
        
        for entity in self.msp:
            if entity in self.used_entities:
                continue
            
            if hasattr(entity.dxf, 'color') and entity.dxf.color == 4:  # CYAN = 4
                continue
                
            if entity.dxftype() in ["POLYLINE", "LWPOLYLINE"]:
                points = self.get_entity_points(entity)
                if len(points) == 2 or len(points) == 3:
                    p1 = points[0]
                    p2 = points[-1]
                    
                    dist1_to_center = (p1 - center).magnitude
                    dist2_to_center = (p2 - center).magnitude
                    dist1_to_circle = abs(dist1_to_center - radius)
                    dist2_to_circle = abs(dist2_to_center - radius)
                    
                    if dist1_to_circle <= 1.0 or dist2_to_circle <= 1.0:
                        min_dist_to_circle = min(dist1_to_circle, dist2_to_circle)
                        candidates.append((entity, min_dist_to_circle, "circle_proximity"))
                        print(f"      - Found A2 candidate ({len(points)} points): distance to circle = {min_dist_to_circle:.3f}mm")
                    
                    elif dist1_to_center <= 9.0 or dist2_to_center <= 9.0:
                        min_dist_to_center = min(dist1_to_center, dist2_to_center)
                        candidates.append((entity, min_dist_to_center, "center_proximity"))
                        print(f"      - Found A2 candidate ({len(points)} points): distance to center = {min_dist_to_center:.3f}mm")
        
        if candidates:
            candidates.sort(key=lambda x: (0 if x[2] == "circle_proximity" else 1, x[1]))
            result = [c[0] for c in candidates[:2]]
            print(f"      - Found {len(result)} A2 candidates")
            return result
        
        print("      - No A2 candidates found")
        return []
    
    def find_a1_line(self, a2_entity: DXFEntity) -> Optional[DXFEntity]:
        """A2의 선분을 교차하는 1mm 이하 길이의 LINE 엔티티 찾기 (A1)"""
        if not a2_entity:
            return None
            
        a2_points = self.get_entity_points(a2_entity)
        if len(a2_points) < 2:
            return None
            
        p1 = a2_points[0]
        p2 = a2_points[-1]
        
        print(f"    - Looking for A1 line (length <= 1mm) intersecting A2")
        
        candidates = []
        
        for entity in self.msp:
            if entity in self.used_entities:
                continue
                
            if entity.dxftype() == "LINE":
                start = Vec3(entity.dxf.start)
                end = Vec3(entity.dxf.end)
                length = (end - start).magnitude
                
                if length <= 1.0:
                    if self.lines_intersect(start, end, p1, p2):
                        entity.dxf.color = 4  # CYAN = 4
                        self.used_entities.add(entity)
                        self.a1_a2_a3_entities.add(entity)
                        print(f"      - Found A1: length={length:.3f}mm (intersecting)")
                        print(f"      - A1 color changed to CYAN")
                        return entity
                    
                    min_dist = min(
                        self.point_to_line_distance(start, p1, p2),
                        self.point_to_line_distance(end, p1, p2),
                        self.point_to_line_distance(p1, start, end),
                        self.point_to_line_distance(p2, start, end)
                    )
                    
                    if min_dist < 0.5:
                        candidates.append((entity, length, min_dist))
        
        if candidates:
            candidates.sort(key=lambda x: x[2])
            closest_line, length, dist = candidates[0]
            
            closest_line.dxf.color = 4  # CYAN = 4
            self.used_entities.add(closest_line)
            self.a1_a2_a3_entities.add(closest_line)
            
            print(f"      - Using closest A1: length={length:.3f}mm, distance={dist:.3f}mm")
            print(f"      - A1 color changed to CYAN")
            return closest_line
        
        print("      - A1 not found (no LINE with length <= 1mm)")
        return None
    
    def find_a3_polyline(self, a1_entity: DXFEntity) -> Optional[DXFEntity]:
        """A3의 어느 한 점이 A1의 0.1mm 이내로 접촉하는 3점 폴리라인 찾기 (A3)"""
        if not a1_entity:
            return None
            
        line_start = Vec3(a1_entity.dxf.start)
        line_end = Vec3(a1_entity.dxf.end)
        
        print(f"    - Looking for A3 polyline touching A1")
        
        candidates = []
        
        for entity in self.msp:
            if entity in self.used_entities:
                continue
                
            if entity.dxftype() in ["POLYLINE", "LWPOLYLINE"]:
                points = self.get_entity_points(entity)
                if len(points) == 3:
                    min_dist = float('inf')
                    for point in points:
                        dist = self.point_to_line_distance(point, line_start, line_end)
                        if dist < min_dist:
                            min_dist = dist
                    
                    if min_dist <= 0.1:
                        total_length = 0
                        for i in range(len(points) - 1):
                            total_length += (points[i+1] - points[i]).magnitude
                        
                        entity.dxf.color = 4  # CYAN = 4
                        self.used_entities.add(entity)
                        self.a1_a2_a3_entities.add(entity)
                        
                        print(f"      - Found A3: min distance={min_dist:.3f}mm, total length={total_length:.2f}mm")
                        print(f"      - A3 color changed to CYAN")
                        return entity
                    
                    if min_dist <= 1.0:
                        total_length = 0
                        for i in range(len(points) - 1):
                            total_length += (points[i+1] - points[i]).magnitude
                        candidates.append((entity, min_dist, total_length))
        
        if candidates:
            candidates.sort(key=lambda x: x[1])
            closest_entity, dist, length = candidates[0]
            
            closest_entity.dxf.color = 4  # CYAN = 4
            self.used_entities.add(closest_entity)
            self.a1_a2_a3_entities.add(closest_entity)
            
            print(f"      - Using closest A3: distance={dist:.3f}mm, length={length:.2f}mm")
            print(f"      - A3 color changed to CYAN")
            return closest_entity
        
        print("      - A3 not found")
        return None
    
    def find_tbox(self, a2_entity: DXFEntity, instno_center: Vec3, search_radius: float = 3.0, max_dist_from_instno: float = 15.0) -> Optional[DXFEntity]:
        """INSTNO 중심에서 먼 A2 끝점으로부터 3mm 이내의 5점 폴리라인 찾기 (TBOX)"""
        if not a2_entity:
            return None
            
        a2_points = self.get_entity_points(a2_entity)
        if len(a2_points) < 2:
            return None
            
        dist1 = (a2_points[0] - instno_center).magnitude
        dist2 = (a2_points[-1] - instno_center).magnitude
        
        if dist1 > dist2:
            search_point = a2_points[0]
            print(f"    - Using A2's first point (farther from INSTNO center): {search_point}, distance={dist1:.2f}mm")
        else:
            search_point = a2_points[-1]
            print(f"    - Using A2's last point (farther from INSTNO center): {search_point}, distance={dist2:.2f}mm")
        
        five_point_count = 0
        candidates = []
        
        for entity in self.msp:
            if entity in self.used_entities:
                continue
                
            if entity.dxftype() in ["POLYLINE", "LWPOLYLINE"]:
                points = self.get_entity_points(entity)
                if len(points) == 5:
                    five_point_count += 1
                    
                    min_dist_to_a2 = float('inf')
                    for point in points:
                        dist_to_a2 = (point - search_point).magnitude
                        min_dist_to_a2 = min(min_dist_to_a2, dist_to_a2)
                    
                    if min_dist_to_a2 <= search_radius:
                        total_length = 0
                        for i in range(len(points) - 1):
                            total_length += (points[i+1] - points[i]).magnitude
                        
                        candidates.append((entity, total_length, min_dist_to_a2))
                        
                        if 13.5 <= total_length <= 14.5:
                            self.used_entities.add(entity)
                            print(f"      - Found TBOX: total length={total_length:.2f}mm, min distance from A2={min_dist_to_a2:.2f}mm")
                            return entity
        
        print(f"    - Total 5-point polylines found: {five_point_count}")
        
        if candidates:
            print(f"    - TBOX candidates within 3mm: {len(candidates)}")
            candidates.sort(key=lambda x: x[2])
            
            for entity, length, dist_to_a2 in candidates[:3]:
                print(f"      - Candidate: length={length:.2f}mm, distance from A2={dist_to_a2:.2f}mm")
            
            best_candidate = min(candidates, key=lambda x: abs(x[1] - 14.0))
            entity, length, dist_to_a2 = best_candidate
            
            if 10.0 <= length <= 20.0:
                self.used_entities.add(entity)
                print(f"      - Using closest TBOX: length={length:.2f}mm, distance from A2={dist_to_a2:.2f}mm")
                return entity
        
        return None
    
    def find_itag_text(self, a2_entity: DXFEntity, instno_center: Vec3) -> Optional[DXFEntity]:
        """기울기 0이고 숫자값 3-50이며 A2의 먼 끝점에서 5mm 이내인 TEXT 찾기 (ITAG)"""
        if not a2_entity:
            return None
            
        a2_points = self.get_entity_points(a2_entity)
        if len(a2_points) < 2:
            return None
        
        dist1 = (a2_points[0] - instno_center).magnitude
        dist2 = (a2_points[-1] - instno_center).magnitude
        
        if dist1 > dist2:
            far_point = a2_points[0]
            print(f"    - Using A2's first point (farther from INSTNO): distance={dist1:.2f}mm")
        else:
            far_point = a2_points[-1]
            print(f"    - Using A2's last point (farther from INSTNO): distance={dist2:.2f}mm")
        
        text_count = 0
        candidates = []
        
        for text_entity in self.msp.query('TEXT'):
            if text_entity in self.used_entities:
                continue
                
            text_count += 1
            
            try:
                text_value = text_entity.dxf.text.strip()
                value = float(text_value)
                
                if 3 <= value <= 50:
                    rotation = text_entity.dxf.rotation
                    if abs(rotation) < 0.1:
                        text_pos = Vec3(text_entity.dxf.insert)
                        
                        dist_to_a2 = (text_pos - far_point).magnitude
                        
                        if dist_to_a2 <= 5.0:
                            candidates.append((text_entity, value, dist_to_a2))
                            print(f"      - Found ITAG candidate: '{text_value}', value={value}, distance={dist_to_a2:.2f}mm")
                            
            except ValueError:
                continue
        
        print(f"    - Total TEXTs found: {text_count}")
        print(f"    - Suitable TEXTs (value 3-50, rotation=0, within 5mm): {len(candidates)}")
        
        if candidates:
            candidates.sort(key=lambda x: x[2])
            selected_text, value, dist = candidates[0]
            self.used_entities.add(selected_text)
            print(f"      - Selected ITAG: value={value}, distance={dist:.2f}mm from A2 far point")
            return selected_text
        
        print("      - ITAG not found")
        return None
    
    def find_tpoint(self, instno_circle: DXFEntity) -> Optional[DXFEntity]:
        """INSTNO 원과 접하는 2점 폴리라인 찾기 (TPOINT)"""
        center = Vec3(instno_circle.dxf.center)
        radius = instno_circle.dxf.radius
        
        touching_polylines = []
        
        for entity in self.msp:
            if entity in self.used_entities:
                continue
            
            if hasattr(entity.dxf, 'color') and entity.dxf.color == 4:  # CYAN = 4
                continue
                
            if entity.dxftype() in ["POLYLINE", "LWPOLYLINE"]:
                points = self.get_entity_points(entity)
                if len(points) == 2:
                    p1 = points[0]
                    p2 = points[1]
                    
                    min_distance = self.line_to_circle_distance(p1, p2, center, radius)
                    
                    if min_distance < 0.5:
                        touching_polylines.append((entity, min_distance))
                        
                        if min_distance < 0.1:
                            self.used_entities.add(entity)
                            print(f"      - Found touching TPOINT at distance {min_distance:.3f}mm")
                            return entity
        
        print(f"    - Found {len(touching_polylines)} touching 2-point polylines")
        
        if touching_polylines:
            touching_polylines.sort(key=lambda x: x[1])
            closest_entity, dist = touching_polylines[0]
            self.used_entities.add(closest_entity)
            print(f"      - Using closest TPOINT at distance {dist:.3f}mm")
            return closest_entity
        
        return None
    
    def line_to_circle_distance(self, p1: Vec3, p2: Vec3, center: Vec3, radius: float) -> float:
        """선분과 원 사이의 최소 거리"""
        closest_point = self.closest_point_on_line(center, p1, p2)
        dist_to_center = (closest_point - center).magnitude
        return abs(dist_to_center - radius)
    
    def closest_point_on_line(self, point: Vec3, line_start: Vec3, line_end: Vec3) -> Vec3:
        """점에서 선분까지 가장 가까운 점"""
        line_vec = line_end - line_start
        point_vec = point - line_start
        line_len = line_vec.magnitude
        
        if line_len == 0:
            return line_start
            
        line_unitvec = line_vec.normalize()
        proj_length = point_vec.dot(line_unitvec)
        
        if proj_length < 0:
            return line_start
        elif proj_length > line_len:
            return line_end
        else:
            return line_start + line_unitvec * proj_length
    
    def get_opposite_point(self, center: Vec3, point: Vec3) -> Vec3:
        """중심점 기준 180도 반대편 점 계산 (FTP)"""
        direction = point - center
        return center - direction
    
    def calculate_and_move_to_ftp(self, tbox: DXFEntity, itag: DXFEntity, center: Vec3, tpoint: DXFEntity) -> Vec3:
        """TBOX와 ITAG를 함께 FTP로 이동 - 2단계 이동"""
        tpoint_points = self.get_entity_points(tpoint)
        if not tpoint_points:
            return None
        
        min_dist = float('inf')
        closest_tpoint = None
        for point in tpoint_points:
            dist = (point - center).magnitude
            if dist < min_dist:
                min_dist = dist
                closest_tpoint = point
        
        print(f"    - Closest TPOINT to INSTNO center: {closest_tpoint}, distance: {min_dist:.2f}mm")
        
        tp = self.get_opposite_point(center, closest_tpoint)
        print(f"    - TP (target point): {tp}")
        
        if not tbox or not itag:
            print("    - TBOX or ITAG missing, cannot proceed with combined movement")
            return None
        
        tbox_points = self.get_entity_points(tbox)
        if not tbox_points:
            return None
            
        tbox_center = Vec3(0, 0, 0)
        for point in tbox_points:
            tbox_center += point
        tbox_center = tbox_center / len(tbox_points)
        
        itag_pos = Vec3(itag.dxf.insert)
        
        combined_center = (tbox_center + itag_pos) / 2
        print(f"    - TBOX center: {tbox_center}")
        print(f"    - ITAG position: {itag_pos}")
        print(f"    - Combined center: {combined_center}")
        
        offset1 = tp - combined_center
        
        tbox.translate(offset1.x, offset1.y, offset1.z)
        itag.dxf.insert = Vec3(itag.dxf.insert) + offset1
        
        print(f"    - 1st move: offset = {offset1}")
        
        moved_tbox_points = []
        for point in tbox_points:
            moved_tbox_points.append(point + offset1)
        
        min_dist = float('inf')
        closest_point = None
        for point in moved_tbox_points:
            dist = (point - center).magnitude
            if dist < min_dist:
                min_dist = dist
                closest_point = point
        
        print(f"    - Closest TBOX point to INSTNO center after 1st move: {closest_point}, distance: {min_dist:.2f}mm")
        
        offset2 = tp - closest_point
        
        tbox.translate(offset2.x, offset2.y, offset2.z)
        itag.dxf.insert = Vec3(itag.dxf.insert) + offset2
        
        print(f"    - 2nd move: offset = {offset2}")
        print(f"    - Total movement: {offset1 + offset2}")
        
        if tbox:
            tbox.dxf.color = 2  # YELLOW = 2
            self.used_entities.add(tbox)
            print("    - TBOX color changed to YELLOW")
        if itag:
            itag.dxf.color = 4  # CYAN = 4
            self.used_entities.add(itag)
            print("    - ITAG color changed to CYAN")
        
        ftp = tp
        print(f"    - Final FTP: {ftp}")
        
        return ftp
    
    def find_insttag_texts(self, instno_circle: DXFEntity) -> List[DXFEntity]:
        """INSTNO 원 둘레에서 2.5mm 이내에 있는 조건에 맞는 TEXT 찾기"""
        insttag_texts = []
        
        center = Vec3(instno_circle.dxf.center)
        radius = instno_circle.dxf.radius
        
        for text_entity in self.msp.query('TEXT'):
            if text_entity.dxf.layer == "WDNO":
                continue
                
            rotation = text_entity.dxf.rotation
            if abs(rotation) > 0.1:
                continue
            
            text_content = text_entity.dxf.text.strip()
            
            if '<' in text_content or '>' in text_content or 'x' in text_content.lower():
                continue
            
            text_pos = Vec3(text_entity.dxf.insert)
            
            dist_to_center = (text_pos - center).magnitude
            
            dist_to_circle = abs(dist_to_center - radius)
            
            if dist_to_circle <= 2.5:
                insttag_texts.append(text_entity)
                print(f"        - Found INSTTAG: '{text_entity.dxf.text}' at distance {dist_to_circle:.2f}mm from circle")
        
        return insttag_texts
    
    def get_text_bounding_box_center(self, text_entity: DXFEntity) -> Vec3:
        """TEXT 엔티티의 바운딩 박스 중심 계산"""
        insert_point = Vec3(text_entity.dxf.insert)
        text_height = text_entity.dxf.height
        text_content = text_entity.dxf.text
        text_length = len(text_content) * text_height * 0.7
        rotation = math.radians(text_entity.dxf.rotation)
        
        halign = text_entity.dxf.halign if hasattr(text_entity.dxf, 'halign') else 0
        valign = text_entity.dxf.valign if hasattr(text_entity.dxf, 'valign') else 0
        
        if halign == 0:  # LEFT
            h_offset = text_length / 2
        elif halign == 1:  # CENTER
            h_offset = 0
        elif halign == 2:  # RIGHT
            h_offset = -text_length / 2
        else:
            h_offset = text_length / 2
        
        if valign == 0 or valign == 1:  # BASELINE or BOTTOM
            v_offset = text_height / 2
        elif valign == 2:  # MIDDLE
            v_offset = 0
        elif valign == 3:  # TOP
            v_offset = -text_height / 2
        else:
            v_offset = text_height / 2
        
        dx = h_offset * math.cos(rotation) - v_offset * math.sin(rotation)
        dy = h_offset * math.sin(rotation) + v_offset * math.cos(rotation)
        
        center = Vec3(insert_point.x + dx, insert_point.y + dy, insert_point.z)
        
        return center
    
    def get_polyline_center(self, polyline: DXFEntity) -> Vec3:
        """폴리라인의 중심점 계산 (중복점 제거)"""
        points = self.get_entity_points(polyline)
        if not points:
            return None
        
        unique_points = []
        for i, point in enumerate(points):
            if i == len(points) - 1 and len(unique_points) > 0:
                if (point - unique_points[0]).magnitude < 0.001:
                    continue
            unique_points.append(point)
        
        if len(unique_points) == 4:
            center = (unique_points[0] + unique_points[2]) / 2
        else:
            center = Vec3(0, 0, 0)
            for point in unique_points:
                center += point
            center = center / len(unique_points)
        
        return center
    
    def move_text_center_to_point(self, text_entity: DXFEntity, target_center: Vec3):
        """TEXT 엔티티의 중심을 목표 지점으로 이동"""
        current_center = self.get_text_bounding_box_center(text_entity)
        offset = target_center - current_center
        current_insert = Vec3(text_entity.dxf.insert)
        text_entity.dxf.insert = current_insert + offset
    
    def stretch_entity_point(self, entity: DXFEntity, point_to_move: Vec3, stretch_vector: Vec3):
        """폴리라인의 특정 점만 STRETCH"""
        if entity.dxftype() == "LWPOLYLINE":
            points = list(entity.get_points('xy'))
            new_points = []
            
            for p in points:
                point = Vec3(p[0], p[1], 0)
                if (point - point_to_move).magnitude < 0.001:
                    new_point = point + stretch_vector
                    new_points.append((new_point.x, new_point.y))
                else:
                    new_points.append((p[0], p[1]))
            
            entity.set_points(new_points)
            
        elif entity.dxftype() == "POLYLINE":
            for vertex in entity.vertices:
                vertex_pos = Vec3(vertex.dxf.location)
                if (vertex_pos - point_to_move).magnitude < 0.001:
                    vertex.dxf.location = vertex_pos + stretch_vector
    
    def stretch_entity(self, entity: DXFEntity, base_point: Vec3, stretch_vector: Vec3):
        """엔티티를 base_point 기준으로 stretch_vector만큼 늘이기"""
        if entity.dxftype() == "TEXT":
            current_pos = Vec3(entity.dxf.insert)
            entity.dxf.insert = current_pos + stretch_vector
            
        elif entity.dxftype() in ["POLYLINE", "LWPOLYLINE"]:
            entity.translate(stretch_vector.x, stretch_vector.y, stretch_vector.z)
            
        elif entity.dxftype() == "CIRCLE":
            center = Vec3(entity.dxf.center)
            entity.dxf.center = center + stretch_vector
    
    def process_ig_and_stretch(self):
        """IG 처리 및 STRETCH 작업"""
        ig_polylines = []
        for entity in self.msp:
            if entity.dxftype() in ["POLYLINE", "LWPOLYLINE"]:
                if hasattr(entity.dxf, 'color') and entity.dxf.color == 1:  # RED = 1
                    entity.dxf.layer = "IG"
                    entity.dxf.color = 7  # WHITE = 7
                    ig_polylines.append(entity)
                    print(f"\n  - Found IG polyline (RED), changed layer to 'IG' and color to WHITE")
        
        if not ig_polylines:
            print("\n  - No IG polylines (RED) found")
            return
        
        for instno_idx, instno in enumerate(self.instno_circles):
            print(f"\n  Processing INSTNO group {instno_idx + 1}")
            
            if instno not in self.instno_data:
                print("    - No data found for this INSTNO")
                continue
                
            instno_info = self.instno_data[instno]
            instno_center = instno_info['center']
            
            insttag_texts = self.find_insttag_texts(instno)
            print(f"    - Found {len(insttag_texts)} INSTTAG texts")
            
            tbox = instno_info.get('tbox')
            itag = instno_info.get('itag')
            
            if not insttag_texts or not tbox or not itag:
                missing_components = []
                if not insttag_texts:
                    missing_components.append("INSTTAG")
                if not tbox:
                    missing_components.append("TBOX")
                if not itag:
                    missing_components.append("ITAG")
                print(f"    - INST group incomplete. Missing: {', '.join(missing_components)}")
                print("    - Skipping STRETCH for this INSTNO group")
                continue
            
            print("    - INST group complete (INSTNO + INSTTAG + TBOX + ITAG)")
            
            if tbox:
                print("    - Using previously found TBOX (YELLOW)")
            if itag:
                print(f"    - Using previously found ITAG (CYAN): '{itag.dxf.text}'")
                print("    - Note: ITAG was already moved with TBOX in previous step")
            
            min_dist = float('inf')
            closest_ig = None
            for ig in ig_polylines:
                ig_points = self.get_entity_points(ig)
                for point in ig_points:
                    dist = (point - instno_center).magnitude
                    if dist < min_dist:
                        min_dist = dist
                        closest_ig = ig
            
            if not closest_ig:
                print("    - No suitable IG found")
                continue
            
            ig_points = self.get_entity_points(closest_ig)
            if len(ig_points) < 2:
                continue
            
            dist1 = (ig_points[0] - instno_center).magnitude
            dist2 = (ig_points[-1] - instno_center).magnitude
            
            if dist1 < dist2:
                ig2 = ig_points[0]
                ig1 = ig_points[-1]
            else:
                ig2 = ig_points[-1]
                ig1 = ig_points[0]
            
            print(f"    - IG1: {ig1}, IG2: {ig2}")
            print(f"    - Distance from INSTNO: IG1={max(dist1, dist2):.2f}mm, IG2={min(dist1, dist2):.2f}mm")
            
            direction = (ig2 - ig1).normalize()
            stretch_vector = direction * 9.5
            
            print(f"    - Stretch direction: {direction}")
            print(f"    - Stretch vector: {stretch_vector} (11mm)")
            
            self.stretch_entity_point(closest_ig, ig2, stretch_vector)
            print("    - IG2 point stretched (IG1 remains fixed)")
            
            self.stretch_entity(instno, ig2, stretch_vector)
            
            for text in insttag_texts:
                self.stretch_entity(text, ig2, stretch_vector)
                text.dxf.layer = "INSTNOG"
            if insttag_texts:
                print(f"    - {len(insttag_texts)} INSTTAG texts moved to layer 'INSTNOG'")
            
            if tbox:
                self.stretch_entity(tbox, ig2, stretch_vector)
                tbox.dxf.layer = "INSTBOX"
                print("    - TBOX moved to layer 'INSTBOX'")
            
            if itag:
                self.stretch_entity(itag, ig2, stretch_vector)
                itag.dxf.layer = "INSTITEMNO"
                print("    - ITAG moved to layer 'INSTITEMNO'")
            
            if tbox and itag:
                tbox_center = self.get_polyline_center(tbox)
                
                if tbox_center:
                    self.move_text_center_to_point(itag, tbox_center)
                    print(f"    - TBOX center: {tbox_center}")
                    
                    itag_center = self.get_text_bounding_box_center(itag)
                    print(f"    - ITAG text: '{itag.dxf.text}', height: {itag.dxf.height:.2f}")
                    print(f"    - ITAG final center: {itag_center}")
                    
                    tbox_points = self.get_entity_points(tbox)
                    print(f"    - TBOX has {len(tbox_points)} points")
                    if len(tbox_points) == 5 and (tbox_points[0] - tbox_points[-1]).magnitude < 0.001:
                        print("    - TBOX is a closed polyline (first and last points are same)")
            
            print(f"    - STRETCH completed for INST group {instno_idx + 1}")
    
    def lines_intersect(self, p1: Vec3, p2: Vec3, p3: Vec3, p4: Vec3) -> bool:
        """두 선분이 교차하는지 확인"""
        def ccw(A, B, C):
            return (C.y - A.y) * (B.x - A.x) > (B.y - A.y) * (C.x - A.x)
        
        return ccw(p1, p3, p4) != ccw(p2, p3, p4) and ccw(p1, p2, p3) != ccw(p1, p2, p4)
    
    def point_to_line_distance(self, point: Vec3, line_start: Vec3, line_end: Vec3) -> float:
        """점에서 선분까지의 거리"""
        line_vec = line_end - line_start
        point_vec = point - line_start
        line_len = line_vec.magnitude
        
        if line_len == 0:
            return point_vec.magnitude
            
        line_unitvec = line_vec.normalize()
        proj_length = point_vec.dot(line_unitvec)
        
        if proj_length < 0:
            return point_vec.magnitude
        elif proj_length > line_len:
            return (point - line_end).magnitude
        else:
            proj_point = line_start + line_unitvec * proj_length
            return (point - proj_point).magnitude
    
    def process_step1(self):
        """1단계: 첫 번째 파일의 처리 (파일 저장 없이)"""
        print("\n=== STEP 1: INST Processing ===")
        
        # 사용된 엔티티 초기화
        self.used_entities = set()
        self.a1_a2_a3_entities = set()
        self.instno_data = {}
        
        # 1. INSTNO 레이어의 원(CIRCLE) 찾기
        self.instno_circles = self.find_instno_circles()
        print(f"Found {len(self.instno_circles)} INSTNO circles")
        
        for idx, instno in enumerate(self.instno_circles):
            print(f"\nProcessing INSTNO {idx + 1}/{len(self.instno_circles)}")
            
            self.used_entities.add(instno)
            
            center = Vec3(instno.dxf.center)
            radius = instno.dxf.radius
            
            self.instno_data[instno] = {
                'center': center,
                'radius': radius,
                'a2': None,
                'tbox': None,
                'itag': None,
                'tpoint': None
            }
            
            print(f"  - Circle center: {center}, radius: {radius:.2f}")
            
            # 2. A2 후보들 찾기 (2개)
            a2_candidates = self.find_a2_polylines(center, radius)
            if not a2_candidates:
                print("  - No A2 candidates found")
                continue
            
            if len(a2_candidates) == 1:
                print("  - Only 1 A2 found")
                a2 = a2_candidates[0]
                a2.dxf.color = 4  # CYAN = 4
                self.used_entities.add(a2)
                self.a1_a2_a3_entities.add(a2)
                print("    - A2 color changed to CYAN")
                
                a1 = self.find_a1_line(a2)
                
                if a1:
                    print("    - A1 found, proceeding with normal processing")
                    
                    a3 = self.find_a3_polyline(a1)
                    if not a3:
                        print("    - A3 not found")
                        continue
                    
                    all_group = [a1, a2, a3]
                    print("    - ALL group created (A1 + A2 + A3)")
                    
                    tpoint = self.find_tpoint(instno)
                    if not tpoint:
                        print("    - TPOINT not found, using A2 as TPOINT")
                        tpoint = a2
                        tpoint.dxf.color = 1  # RED = 1
                        print("    - A2 color changed to RED (used as TPOINT)")
                    else:
                        self.used_entities.add(tpoint)
                else:
                    print("    - A1 not found, using A2 as TPOINT")
                    tpoint = a2
                    tpoint.dxf.color = 1  # RED = 1
                    print("    - A2 color changed to RED (used as TPOINT)")
                    all_group = None
                
            else:
                print("  - 2 A2 candidates found")
                
                a2_with_a1_a3 = None
                a2_for_tpoint = None
                all_group = None
                
                for idx_a2, a2_candidate in enumerate(a2_candidates):
                    print(f"    - Checking A2 candidate {idx_a2 + 1}")
                    a2_candidate.dxf.color = 4  # CYAN = 4
                    self.used_entities.add(a2_candidate)
                    self.a1_a2_a3_entities.add(a2_candidate)
                    
                    a1_temp = self.find_a1_line(a2_candidate)
                    
                    if a1_temp:
                        a3_temp = self.find_a3_polyline(a1_temp)
                        
                        if a3_temp:
                            print(f"      - Found A1 and A3 for A2 candidate {idx_a2 + 1}")
                            a2_with_a1_a3 = a2_candidate
                            a2 = a2_candidate
                            a1 = a1_temp
                            a3 = a3_temp
                            all_group = [a1, a2, a3]
                        else:
                            print(f"      - A3 not found for A2 candidate {idx_a2 + 1}")
                            if not a2_for_tpoint:
                                a2_for_tpoint = a2_candidate
                    else:
                        print(f"      - A1 not found for A2 candidate {idx_a2 + 1}")
                        if not a2_for_tpoint:
                            a2_for_tpoint = a2_candidate
                
                if a2_with_a1_a3:
                    print("    - Using A2 with A1 and A3 for ALL group")
                    if a2_for_tpoint:
                        tpoint = a2_for_tpoint
                        tpoint.dxf.color = 1  # RED = 1
                        print("    - Using other A2 as TPOINT, color changed to RED")
                    else:
                        tpoint = a2_candidates[0] if a2_candidates[0] != a2_with_a1_a3 else a2_candidates[1]
                        tpoint.dxf.color = 1  # RED = 1
                        print("    - Using first A2 as TPOINT, color changed to RED")
                else:
                    print("    - No A2 candidate has both A1 and A3")
                    continue
            
            # 공통 처리 부분
            tbox = self.find_tbox(a2, center)
            if tbox:
                print("  - TBOX found")
                self.instno_data[instno]['tbox'] = tbox
            else:
                print("  - TBOX not found (optional)")
            
            itag = self.find_itag_text(a2, center)
            if not itag:
                print("  - ITAG not found")
                continue
            
            self.instno_data[instno]['itag'] = itag
            self.instno_data[instno]['a2'] = a2
            self.instno_data[instno]['tpoint'] = tpoint
            
            ftp = self.calculate_and_move_to_ftp(tbox, itag, center, tpoint)
            
            if ftp:
                print(f"  - Successfully processed INSTNO entity")
            else:
                print("  - Failed to calculate FTP")
        
        # A1, A2, A3로 식별되고 CYAN 색상인 엔티티만 삭제
        entities_to_delete = []
        for entity in self.a1_a2_a3_entities:
            if hasattr(entity.dxf, 'color') and entity.dxf.color == 4:  # CYAN = 4
                entities_to_delete.append(entity)
        
        for entity in entities_to_delete:
            try:
                entity.destroy()
                print(f"Deleted A1/A2/A3 CYAN entity: {entity.dxftype()}")
            except Exception as e:
                print(f"Failed to delete entity: {e}")
        
        print(f"\nTotal A1/A2/A3 CYAN entities deleted: {len(entities_to_delete)}")
        
        # IG 처리 및 STRETCH
        print("\n=== Final Step: IG Processing and STRETCH ===")
        self.process_ig_and_stretch()
    
    # ========== 2단계: 두 번째 파일의 메서드들 ==========
    
    def find_a2_polyline_step2(self, center: Vec3, radius: float) -> Optional[DXFEntity]:
        """INSTNO 원과 관련된 2점 또는 3점 폴리라인 찾기 (A2) - 1개만 반환 (2단계용)"""
        print(f"    - Looking for A2 polyline near circle: center={center}, radius={radius:.2f}")
        
        candidates = []
        
        for entity in self.msp:
            if entity in self.used_entities:
                continue
            
            if hasattr(entity.dxf, 'color') and entity.dxf.color == 4:  # CYAN = 4
                continue
                
            if entity.dxftype() in ["POLYLINE", "LWPOLYLINE"]:
                points = self.get_entity_points(entity)
                if len(points) == 2 or len(points) == 3:
                    p1 = points[0]
                    p2 = points[-1]
                    
                    dist1_to_center = (p1 - center).magnitude
                    dist2_to_center = (p2 - center).magnitude
                    dist1_to_circle = abs(dist1_to_center - radius)
                    dist2_to_circle = abs(dist2_to_center - radius)
                    
                    if dist1_to_circle <= 1.0 or dist2_to_circle <= 1.0:
                        min_dist_to_circle = min(dist1_to_circle, dist2_to_circle)
                        candidates.append((entity, min_dist_to_circle, "circle_proximity"))
                        print(f"      - Found A2 candidate ({len(points)} points): distance to circle = {min_dist_to_circle:.3f}mm")
                    
                    elif dist1_to_center <= 9.0 or dist2_to_center <= 9.0:
                        min_dist_to_center = min(dist1_to_center, dist2_to_center)
                        candidates.append((entity, min_dist_to_center, "center_proximity"))
                        print(f"      - Found A2 candidate ({len(points)} points): distance to center = {min_dist_to_center:.3f}mm")
        
        if candidates:
            candidates.sort(key=lambda x: (0 if x[2] == "circle_proximity" else 1, x[1]))
            result = candidates[0][0]
            result.dxf.color = 4  # CYAN = 4
            self.used_entities.add(result)
            print(f"      - Selected A2, color changed to CYAN, layer: {result.dxf.layer}")
            return result
        
        print("      - No A2 candidate found")
        return None
    
    def get_circle_tangent_points(self, center: Vec3, radius: float) -> List[Vec3]:
        """원의 모든 접선점들을 계산 (36개 점, 10도 간격)"""
        points = []
        for angle in range(0, 360, 10):
            rad = math.radians(angle)
            x = center.x + radius * math.cos(rad)
            y = center.y + radius * math.sin(rad)
            points.append(Vec3(x, y, center.z))
        return points
    
    def find_tbox_near_tangent(self, center: Vec3, radius: float) -> Optional[DXFEntity]:
        """INSTNO 원의 접선에서 10mm 이내의 5점 폴리라인 찾기 (TBOX)"""
        print(f"    - Looking for TBOX near circle tangent")
        
        tangent_points = self.get_circle_tangent_points(center, radius)
        candidates = []
        
        for entity in self.msp:
            if entity in self.used_entities:
                continue
            
            layer_upper = entity.dxf.layer.upper()
            if 'INST' in layer_upper or layer_upper == 'ITEMNO':
                continue
                
            if entity.dxftype() in ["POLYLINE", "LWPOLYLINE"]:
                points = self.get_entity_points(entity)
                if len(points) == 5:
                    min_dist_to_tangent = float('inf')
                    for point in points:
                        for tangent_point in tangent_points:
                            dist = (point - tangent_point).magnitude
                            min_dist_to_tangent = min(min_dist_to_tangent, dist)
                    
                    if min_dist_to_tangent <= 10.0:
                        total_length = 0
                        for i in range(len(points) - 1):
                            total_length += (points[i+1] - points[i]).magnitude
                        
                        candidates.append((entity, total_length, min_dist_to_tangent))
                        print(f"      - Found TBOX candidate: length={total_length:.2f}mm, distance from tangent={min_dist_to_tangent:.2f}mm")
        
        if candidates:
            candidates.sort(key=lambda x: abs(x[1] - 14.0))
            selected = candidates[0][0]
            self.used_entities.add(selected)
            print(f"      - Selected TBOX")
            return selected
        
        print("      - TBOX not found")
        return None
    
    def find_itag_near_tangent(self, center: Vec3, radius: float) -> Optional[DXFEntity]:
        """INSTNO 원의 접선에서 10mm 이내의 조건에 맞는 TEXT 찾기 (ITAG)"""
        print(f"    - Looking for ITAG near circle tangent")
        
        tangent_points = self.get_circle_tangent_points(center, radius)
        candidates = []
        
        for text_entity in self.msp.query('TEXT'):
            if text_entity in self.used_entities:
                continue
            
            layer_upper = text_entity.dxf.layer.upper()
            if 'INST' in layer_upper or layer_upper == 'ITEMNO':
                continue
            
            try:
                text_value = text_entity.dxf.text.strip()
                value = float(text_value)
                
                if 3 <= value <= 50:
                    rotation = text_entity.dxf.rotation
                    if abs(rotation) < 0.1:
                        text_pos = Vec3(text_entity.dxf.insert)
                        
                        min_dist_to_tangent = float('inf')
                        for tangent_point in tangent_points:
                            dist = (text_pos - tangent_point).magnitude
                            min_dist_to_tangent = min(min_dist_to_tangent, dist)
                        
                        if min_dist_to_tangent <= 10.0:
                            candidates.append((text_entity, value, min_dist_to_tangent))
                            print(f"      - Found ITAG candidate: '{text_value}', distance={min_dist_to_tangent:.2f}mm")
                            
            except ValueError:
                continue
        
        if candidates:
            candidates.sort(key=lambda x: x[2])
            selected = candidates[0][0]
            self.used_entities.add(selected)
            print(f"      - Selected ITAG: '{selected.dxf.text}'")
            return selected
        
        print("      - ITAG not found")
        return None
    
    def find_ftp(self, center: Vec3, radius: float) -> Vec3:
        """INSTNO 원 접선 중 Y값이 가장 작은 점 (FTP)"""
        tangent_points = self.get_circle_tangent_points(center, radius)
        ftp = min(tangent_points, key=lambda p: p.y)
        print(f"    - FTP (lowest Y tangent point): {ftp}")
        return ftp
    
    def find_tpos(self, tbox: DXFEntity, ftp: Vec3) -> Vec3:
        """TBOX의 점들 중 FTP와 가장 가까운 점 (TPOS)"""
        if not tbox:
            return None
            
        points = self.get_entity_points(tbox)
        if not points:
            return None
        
        min_dist = float('inf')
        tpos = None
        
        for point in points:
            dist = (point - ftp).magnitude
            if dist < min_dist:
                min_dist = dist
                tpos = point
        
        print(f"    - TPOS (closest TBOX point to FTP): {tpos}, distance={min_dist:.2f}mm")
        return tpos
    
    def move_tbox_and_itag_to_ftp(self, tbox: DXFEntity, itag: DXFEntity, tpos: Vec3, ftp: Vec3):
        """TBOX와 ITAG를 TPOS에서 FTP로 이동"""
        if not tpos or not ftp:
            return
        
        offset = ftp - tpos
        
        if tbox:
            tbox.translate(offset.x, offset.y, offset.z)
            tbox.dxf.color = 2  # YELLOW = 2
            print(f"    - TBOX moved by {offset}, color changed to YELLOW")
        
        if itag:
            current_pos = Vec3(itag.dxf.insert)
            itag.dxf.insert = current_pos + offset
            itag.dxf.color = 4  # CYAN = 4
            print(f"    - ITAG moved by {offset}, color changed to CYAN")
    
    def get_inst_bounding_box(self, instno: DXFEntity, insttag_texts: List[DXFEntity], 
                             tbox: DXFEntity, itag: DXFEntity) -> Tuple[Vec3, Vec3]:
        """INST 그룹의 바운딩 박스 계산"""
        all_points = []
        
        center = Vec3(instno.dxf.center)
        radius = instno.dxf.radius
        all_points.extend([
            Vec3(center.x - radius, center.y - radius, center.z),
            Vec3(center.x + radius, center.y + radius, center.z)
        ])
        
        for text in insttag_texts:
            all_points.append(Vec3(text.dxf.insert))
        
        if tbox:
            all_points.extend(self.get_entity_points(tbox))
        
        if itag:
            all_points.append(Vec3(itag.dxf.insert))
        
        min_x = min(p.x for p in all_points)
        min_y = min(p.y for p in all_points)
        max_x = max(p.x for p in all_points)
        max_y = max(p.y for p in all_points)
        
        return Vec3(min_x, min_y, 0), Vec3(max_x, max_y, 0)
    
    def check_interference(self, bbox_min: Vec3, bbox_max: Vec3, 
                          exclude_entities: set) -> bool:
        """바운딩 박스 내에 다른 엔티티와의 간섭 체크"""
        for entity in self.msp:
            if entity in exclude_entities:
                continue
            
            if entity.dxftype() == "CIRCLE":
                center = Vec3(entity.dxf.center)
                if (bbox_min.x <= center.x <= bbox_max.x and 
                    bbox_min.y <= center.y <= bbox_max.y):
                    return True
            
            elif entity.dxftype() in ["POLYLINE", "LWPOLYLINE"]:
                points = self.get_entity_points(entity)
                for point in points:
                    if (bbox_min.x <= point.x <= bbox_max.x and 
                        bbox_min.y <= point.y <= bbox_max.y):
                        return True
            
            elif entity.dxftype() == "TEXT":
                pos = Vec3(entity.dxf.insert)
                if (bbox_min.x <= pos.x <= bbox_max.x and 
                    bbox_min.y <= pos.y <= bbox_max.y):
                    return True
        
        return False
    
    def move_inst_group(self, entities: List[DXFEntity], offset: Vec3):
        """INST 그룹 전체를 이동"""
        for entity in entities:
            if entity.dxftype() == "CIRCLE":
                center = Vec3(entity.dxf.center)
                entity.dxf.center = center + offset
            elif entity.dxftype() == "TEXT":
                pos = Vec3(entity.dxf.insert)
                entity.dxf.insert = pos + offset
            elif entity.dxftype() in ["POLYLINE", "LWPOLYLINE"]:
                entity.translate(offset.x, offset.y, offset.z)
    
    def create_line_and_trim(self, a2_far_point: Vec3, instno_center: Vec3, instno_radius: float):
        """A2 먼점과 INSTNO 중심 사이에 흰색 선을 그리고 원 안쪽 부분 TRIM"""
        total_distance = (instno_center - a2_far_point).magnitude
        
        if total_distance <= instno_radius:
            print("    - Warning: A2 far point is inside the circle")
            return
        
        ratio = (total_distance - instno_radius) / total_distance
        
        intersection = a2_far_point + (instno_center - a2_far_point) * ratio
        
        trimmed_line = self.msp.add_line(a2_far_point, intersection)
        trimmed_line.dxf.layer = "INSTG"
        trimmed_line.dxf.color = 7  # WHITE
        
        distance_check = (intersection - instno_center).magnitude
        print(f"    - Created trimmed white line, layer='INSTG'")
        print(f"    - Line length: {(intersection - a2_far_point).magnitude:.2f}mm")
        print(f"    - Distance from intersection to center: {distance_check:.3f}mm (radius: {instno_radius:.3f}mm)")
    
    def process_step2(self):
        """2단계: 두 번째 파일의 처리"""
        print("\n\n=== STEP 2: INCV Processing ===")
        
        # 2단계를 위해 used_entities 초기화 (1단계와 독립적으로 처리)
        self.used_entities = set()
        self.a2_process_status = {}
        
        # 1. INSTNO 레이어의 원(CIRCLE) 찾기 (2단계용으로 다시 찾기)
        self.instno_circles = self.find_instno_circles()
        print(f"Found {len(self.instno_circles)} INSTNO circles")
        
        # A2 엔티티들을 저장할 리스트
        a2_entities_to_delete = []
        
        for idx, instno in enumerate(self.instno_circles):
            print(f"\nProcessing INSTNO {idx + 1}/{len(self.instno_circles)} (Step 2)")
            
            self.used_entities.add(instno)
            
            center = Vec3(instno.dxf.center)
            radius = instno.dxf.radius
            
            print(f"  - Circle center: {center}, radius: {radius:.2f}")
            
            # 2. A2 찾기 (1개만)
            a2 = self.find_a2_polyline_step2(center, radius)
            if not a2:
                print("  - No A2 found")
                continue
            
            print(f"  - A2 found on layer: {a2.dxf.layer}")
            a2_entities_to_delete.append(a2)
            
            # A2의 먼점 찾기
            a2_points = self.get_entity_points(a2)
            dist1 = (a2_points[0] - center).magnitude
            dist2 = (a2_points[-1] - center).magnitude
            a2_far_point = a2_points[0] if dist1 > dist2 else a2_points[-1]
            a2_near_point = a2_points[-1] if dist1 > dist2 else a2_points[0]
            
            print(f"  - A2 far point distance: {max(dist1, dist2):.2f}mm")
            print(f"  - A2 near point distance: {min(dist1, dist2):.2f}mm")
            
            # 3. TBOX 찾기
            tbox = self.find_tbox_near_tangent(center, radius)
            
            # 4. ITAG 찾기
            itag = self.find_itag_near_tangent(center, radius)
            
            # TBOX와 ITAG 존재 여부 저장
            has_tbox_itag = bool(tbox and itag)
            
            if not tbox or not itag:
                print("  - TBOX or ITAG not found, skipping")
                self.a2_process_status[a2] = (False, False)
                continue
            
            # 5. FTP 찾기 (Y값이 가장 작은 접선점)
            ftp = self.find_ftp(center, radius)
            
            # 6. TPOS 찾기 (TBOX 점 중 FTP와 가장 가까운 점)
            tpos = self.find_tpos(tbox, ftp)
            
            # 7. TBOX와 ITAG를 FTP로 이동
            self.move_tbox_and_itag_to_ftp(tbox, itag, tpos, ftp)
            
            # 8. INSTTAG 텍스트들 찾기
            insttag_texts = self.find_insttag_texts(instno)
            print(f"  - Found {len(insttag_texts)} INSTTAG texts")
            
            # 9. INST 그룹 생성
            inst_entities = [instno] + insttag_texts
            if tbox:
                inst_entities.append(tbox)
            if itag:
                inst_entities.append(itag)
            
            # 10. INSTNO 중심과 A2 먼점 사이의 벡터
            center_to_far = a2_far_point - center
            current_distance = center_to_far.magnitude
            move_direction = center_to_far.normalize()
            
            # 11. 목표 위치 계산 (INSTNO 중심에서 A2 먼점 방향으로 15mm 지점)
            target_position = a2_far_point - move_direction * 15.0
            target_offset = target_position - center
            
            print(f"  - Current distance (center to A2 far): {current_distance:.2f}mm")
            print(f"  - Target distance: 15.0mm")
            print(f"  - Move offset: {target_offset}")
            
            # 원래 위치 저장
            original_positions = []
            for entity in inst_entities:
                if entity.dxftype() == "CIRCLE":
                    original_positions.append(("CIRCLE", Vec3(entity.dxf.center)))
                elif entity.dxftype() == "TEXT":
                    original_positions.append(("TEXT", Vec3(entity.dxf.insert)))
                elif entity.dxftype() in ["POLYLINE", "LWPOLYLINE"]:
                    original_positions.append(("POLYLINE", self.get_entity_points(entity).copy()))
            
            # 12. INST를 목표 위치로 이동
            self.move_inst_group(inst_entities, target_offset)
            
            # 13. 간섭 체크
            bbox_min, bbox_max = self.get_inst_bounding_box(instno, insttag_texts, tbox, itag)
            exclude_set = set(inst_entities + [a2])
            
            position_found = False
            total_offset = target_offset
            
            if not self.check_interference(bbox_min, bbox_max, exclude_set):
                position_found = True
                print(f"  - No interference at target position (15mm)")
            else:
                print(f"  - Interference detected at target position")
                
                for step in range(1, 6):
                    step_offset = -move_direction * 3.0
                    self.move_inst_group(inst_entities, step_offset)
                    total_offset = total_offset + step_offset
                    
                    bbox_min, bbox_max = self.get_inst_bounding_box(instno, insttag_texts, tbox, itag)
                    
                    if not self.check_interference(bbox_min, bbox_max, exclude_set):
                        position_found = True
                        print(f"  - No interference after {step * 3}mm retreat")
                        break
                    else:
                        print(f"  - Still interference after {step * 3}mm retreat")
                
                if not position_found:
                    print(f"  - Interference at all positions, returning to original")
                    current_offset = -total_offset
                    self.move_inst_group(inst_entities, current_offset)
                    total_offset = Vec3(0, 0, 0)
            
            # 14. 최종 위치 확정 후, 이동된 INSTNO 중심 계산
            final_center = center + total_offset
            print(f"  - Final INSTNO center: {final_center}")
            
            self.a2_process_status[a2] = (position_found, has_tbox_itag)
            
            # 15. 위치 확정 후 선 그리기 및 TRIM (이동된 중심 사용)
            self.create_line_and_trim(a2_far_point, final_center, radius)
            
            # 레이어 변경
            for text in insttag_texts:
                text.dxf.layer = "INSTNOG"
            if tbox:
                tbox.dxf.layer = "INSTBOX"
            if itag:
                itag.dxf.layer = "INSTITEMNO"
            
            print(f"  - INSTNO group {idx + 1} processing completed")
        
        # 16. 모든 A2 삭제 (IG 레이어는 조건부 삭제)
        deleted_count = 0
        for a2 in a2_entities_to_delete:
            try:
                if a2.dxf.layer.upper() == 'IG':
                    if a2 in self.a2_process_status:
                        success, has_tbox_itag = self.a2_process_status[a2]
                        if has_tbox_itag:
                            a2.destroy()
                            deleted_count += 1
                            print(f"Deleted A2 entity on IG layer (TBOX/ITAG found)")
                        else:
                            print(f"Skipping deletion of A2 entity on IG layer (TBOX/ITAG missing)")
                    else:
                        print(f"Skipping deletion of A2 entity on IG layer (not processed)")
                else:
                    a2.destroy()
                    deleted_count += 1
                    print(f"Deleted A2 entity on layer: {a2.dxf.layer}")
            except Exception as e:
                print(f"Failed to delete A2 entity: {e}")
        
        print(f"\nTotal A2 entities deleted: {deleted_count}")
    
    def process_dxf_file(self, filepath: str):
        """DXF 파일 처리 메인 함수"""
        print(f"Processing: {filepath}")
        self.load_dxf(filepath)
        
        # 1단계 처리
        self.process_step1()
        
        # 2단계 처리
        self.process_step2()
        
        # 파일 저장 (두 번째 파일 방식: _INCV.DXF)
        output_path = filepath.replace('.dxf', '_INCV.DXF') 
        self.doc.saveas(output_path)
        print(f"\nSaved to: {output_path}")

def main():
    processor = IntegratedDXFProcessor()
    
    # DXF 파일 선택 (첫 번째 파일 방식)
    files = processor.select_dxf_files()
    
    if not files:
        print("No files selected")
        return
    
    # 각 파일 처리
    for filepath in files:
        try:
            processor.process_dxf_file(filepath)
        except Exception as e:
            print(f"Error processing {filepath}: {str(e)}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    main()