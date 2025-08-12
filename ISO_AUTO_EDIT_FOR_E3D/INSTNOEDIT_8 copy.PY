import ezdxf
from ezdxf.math import Vec3
from ezdxf.entities import DXFEntity
import tkinter as tk
from tkinter import filedialog
import math
import numpy as np
from typing import List, Tuple, Optional, Union

class DXFProcessor:
    def __init__(self):
        self.doc = None
        self.msp = None
        self.used_entities = set()  # 이미 사용된 엔티티 추적
        self.a1_a2_a3_entities = set()  # A1, A2, A3로 식별된 엔티티 추적
        self.instno_circles = []  # 찾은 INSTNO 원들 저장
        self.instno_data = {}  # 각 INSTNO에 대한 관련 데이터 저장
        
    def select_dxf_files(self) -> List[str]:
        """DXF 파일 선택 다이얼로그 열기"""
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
                # LWPOLYLINE의 경우
                points = list(entity.get_points('xy'))
                return [Vec3(p[0], p[1], 0) for p in points]
            elif entity.dxftype() == "POLYLINE":
                # POLYLINE의 경우
                points = []
                for vertex in entity.vertices:
                    points.append(Vec3(vertex.dxf.location))
                return points
            else:
                return []
        except Exception as e:
            print(f"Error getting points: {e}")
            return []
    
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
            # 이미 사용된 엔티티는 건너뛰기
            if entity in self.used_entities:
                continue
            
            # CYAN 색상 엔티티는 제외
            if hasattr(entity.dxf, 'color') and entity.dxf.color == 4:  # CYAN = 4
                continue
                
            if entity.dxftype() in ["POLYLINE", "LWPOLYLINE"]:
                points = self.get_entity_points(entity)
                if len(points) == 2 or len(points) == 3:  # 2점 또는 3점 폴리라인
                    # 첫 점과 마지막 점으로 거리 계산 (원본 로직 유지)
                    p1 = points[0]
                    p2 = points[-1]  # 마지막 점
                    
                    # 각 점에서 원둘레까지의 거리 계산
                    dist1_to_center = (p1 - center).magnitude
                    dist2_to_center = (p2 - center).magnitude
                    dist1_to_circle = abs(dist1_to_center - radius)
                    dist2_to_circle = abs(dist2_to_center - radius)
                    
                    # 조건 1: 어느 한 점이 원둘레로부터 1mm 이내
                    if dist1_to_circle <= 1.0 or dist2_to_circle <= 1.0:
                        min_dist_to_circle = min(dist1_to_circle, dist2_to_circle)
                        candidates.append((entity, min_dist_to_circle, "circle_proximity"))
                        print(f"      - Found A2 candidate ({len(points)} points): distance to circle = {min_dist_to_circle:.3f}mm")
                    
                    # 조건 2: 어느 한 점이 INSTNO 중심에서 9mm 이내
                    elif dist1_to_center <= 9.0 or dist2_to_center <= 9.0:
                        min_dist_to_center = min(dist1_to_center, dist2_to_center)
                        candidates.append((entity, min_dist_to_center, "center_proximity"))
                        print(f"      - Found A2 candidate ({len(points)} points): distance to center = {min_dist_to_center:.3f}mm")
        
        # 원둘레 근접성을 우선으로 정렬
        if candidates:
            candidates.sort(key=lambda x: (0 if x[2] == "circle_proximity" else 1, x[1]))
            # 상위 2개까지만 반환
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
            
        # 원본 로직: 첫 점과 마지막 점만 사용
        p1 = a2_points[0]
        p2 = a2_points[-1]
        
        print(f"    - Looking for A1 line (length <= 1mm) intersecting A2")
        
        candidates = []
        
        for entity in self.msp:
            # 이미 사용된 엔티티는 건너뛰기
            if entity in self.used_entities:
                continue
                
            if entity.dxftype() == "LINE":
                start = Vec3(entity.dxf.start)
                end = Vec3(entity.dxf.end)
                length = (end - start).magnitude
                
                # 길이가 1mm 이하인 LINE만 검사
                if length <= 1.0:
                    # 교차 검사
                    if self.lines_intersect(start, end, p1, p2):
                        # A1을 찾으면 즉시 CYAN으로 변경
                        entity.dxf.color = 4  # CYAN = 4
                        self.used_entities.add(entity)  # 사용된 엔티티로 표시
                        self.a1_a2_a3_entities.add(entity)  # A1으로 식별된 엔티티 추가
                        print(f"      - Found A1: length={length:.3f}mm (intersecting)")
                        print(f"      - A1 color changed to CYAN")
                        return entity
                    
                    # 근접성 검사 (매우 가까운 경우)
                    min_dist = min(
                        self.point_to_line_distance(start, p1, p2),
                        self.point_to_line_distance(end, p1, p2),
                        self.point_to_line_distance(p1, start, end),
                        self.point_to_line_distance(p2, start, end)
                    )
                    
                    if min_dist < 0.5:  # 0.5mm 이내
                        candidates.append((entity, length, min_dist))
        
        # 교차하는 것이 없으면 가장 가까운 것 선택
        if candidates:
            candidates.sort(key=lambda x: x[2])  # 거리로 정렬
            closest_line, length, dist = candidates[0]
            
            # A1을 찾으면 즉시 CYAN으로 변경
            closest_line.dxf.color = 4  # CYAN = 4
            self.used_entities.add(closest_line)  # 사용된 엔티티로 표시
            self.a1_a2_a3_entities.add(closest_line)  # A1으로 식별된 엔티티 추가
            
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
            # 이미 사용된 엔티티는 건너뛰기
            if entity in self.used_entities:
                continue
                
            if entity.dxftype() in ["POLYLINE", "LWPOLYLINE"]:
                points = self.get_entity_points(entity)
                if len(points) == 3:
                    # 각 점에서 A1까지의 거리 확인
                    min_dist = float('inf')
                    for point in points:
                        dist = self.point_to_line_distance(point, line_start, line_end)
                        if dist < min_dist:
                            min_dist = dist
                    
                    # 어느 한 점이라도 0.1mm 이내면 조건 만족
                    if min_dist <= 0.1:
                        # 전체 길이 계산
                        total_length = 0
                        for i in range(len(points) - 1):
                            total_length += (points[i+1] - points[i]).magnitude
                        
                        # A3를 찾으면 즉시 CYAN으로 변경
                        entity.dxf.color = 4  # CYAN = 4
                        self.used_entities.add(entity)  # 사용된 엔티티로 표시
                        self.a1_a2_a3_entities.add(entity)  # A3로 식별된 엔티티 추가
                        
                        print(f"      - Found A3: min distance={min_dist:.3f}mm, total length={total_length:.2f}mm")
                        print(f"      - A3 color changed to CYAN")
                        return entity
                    
                    # 후보로 저장
                    if min_dist <= 1.0:
                        total_length = 0
                        for i in range(len(points) - 1):
                            total_length += (points[i+1] - points[i]).magnitude
                        candidates.append((entity, min_dist, total_length))
        
        # 정확한 조건을 만족하는 것이 없으면 가장 가까운 것 선택
        if candidates:
            candidates.sort(key=lambda x: x[1])  # 거리로 정렬
            closest_entity, dist, length = candidates[0]
            
            # A3를 찾으면 즉시 CYAN으로 변경
            closest_entity.dxf.color = 4  # CYAN = 4
            self.used_entities.add(closest_entity)  # 사용된 엔티티로 표시
            self.a1_a2_a3_entities.add(closest_entity)  # A3로 식별된 엔티티 추가
            
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
            
        # INSTNO 중심에서 더 먼 A2 끝점 찾기
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
            # 이미 사용된 엔티티는 건너뛰기
            if entity in self.used_entities:
                continue
                
            if entity.dxftype() in ["POLYLINE", "LWPOLYLINE"]:
                points = self.get_entity_points(entity)
                if len(points) == 5:
                    five_point_count += 1
                    
                    # TBOX의 어느 한 점이라도 A2 끝점으로부터 3mm 이내인지 확인
                    min_dist_to_a2 = float('inf')
                    for point in points:
                        dist_to_a2 = (point - search_point).magnitude
                        min_dist_to_a2 = min(min_dist_to_a2, dist_to_a2)
                    
                    if min_dist_to_a2 <= search_radius:  # 3mm 이내
                        # 점들간 거리 합 계산
                        total_length = 0
                        for i in range(len(points) - 1):
                            total_length += (points[i+1] - points[i]).magnitude
                        
                        candidates.append((entity, total_length, min_dist_to_a2))
                        
                        if 13.5 <= total_length <= 14.5:
                            self.used_entities.add(entity)  # 사용된 엔티티로 표시
                            print(f"      - Found TBOX: total length={total_length:.2f}mm, min distance from A2={min_dist_to_a2:.2f}mm")
                            return entity
        
        print(f"    - Total 5-point polylines found: {five_point_count}")
        
        # 조건을 만족하는 것이 없으면 가장 가까운 것 찾기
        if candidates:
            print(f"    - TBOX candidates within 3mm: {len(candidates)}")
            # A2로부터의 거리로 정렬
            candidates.sort(key=lambda x: x[2])
            
            for entity, length, dist_to_a2 in candidates[:3]:  # 상위 3개만 확인
                print(f"      - Candidate: length={length:.2f}mm, distance from A2={dist_to_a2:.2f}mm")
            
            # 길이가 14mm에 가장 가까운 것 선택
            best_candidate = min(candidates, key=lambda x: abs(x[1] - 14.0))
            entity, length, dist_to_a2 = best_candidate
            
            if 10.0 <= length <= 20.0:  # 길이 범위 내
                self.used_entities.add(entity)  # 사용된 엔티티로 표시
                print(f"      - Using closest TBOX: length={length:.2f}mm, distance from A2={dist_to_a2:.2f}mm")
                return entity
        
        return None
    
    def find_itag_text(self, a2_entity: DXFEntity, instno_center: Vec3) -> Optional[DXFEntity]:
        """기울기 0이고 숫자값 3-50이며 A2의 먼 끝점에서 5mm 이내인 TEXT 찾기 (ITAG)"""
        if not a2_entity:
            return None
            
        # A2의 점들 가져오기
        a2_points = self.get_entity_points(a2_entity)
        if len(a2_points) < 2:
            return None
        
        # INSTNO 중심에서 더 먼 A2 끝점 찾기
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
            # 이미 사용된 엔티티는 건너뛰기
            if text_entity in self.used_entities:
                continue
                
            text_count += 1
            
            # 텍스트 값이 숫자인지 확인
            try:
                text_value = text_entity.dxf.text.strip()
                value = float(text_value)
                
                # 숫자값이 3 이상 50 이하인지 확인
                if 3 <= value <= 50:
                    # 기울기 확인 (0도)
                    rotation = text_entity.dxf.rotation
                    if abs(rotation) < 0.1:  # 거의 0도
                        # 텍스트 위치
                        text_pos = Vec3(text_entity.dxf.insert)
                        
                        # A2의 먼 끝점으로부터의 거리
                        dist_to_a2 = (text_pos - far_point).magnitude
                        
                        if dist_to_a2 <= 5.0:  # 5mm 이내
                            candidates.append((text_entity, value, dist_to_a2))
                            print(f"      - Found ITAG candidate: '{text_value}', value={value}, distance={dist_to_a2:.2f}mm")
                            
            except ValueError:
                continue
        
        print(f"    - Total TEXTs found: {text_count}")
        print(f"    - Suitable TEXTs (value 3-50, rotation=0, within 5mm): {len(candidates)}")
        
        # 가장 가까운 것 선택
        if candidates:
            candidates.sort(key=lambda x: x[2])  # 거리로 정렬
            selected_text, value, dist = candidates[0]
            self.used_entities.add(selected_text)  # 사용된 엔티티로 표시
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
            # 이미 사용된 엔티티는 건너뛰기
            if entity in self.used_entities:
                continue
            
            # CYAN 색상 엔티티는 제외
            if hasattr(entity.dxf, 'color') and entity.dxf.color == 4:  # CYAN = 4
                continue
                
            if entity.dxftype() in ["POLYLINE", "LWPOLYLINE"]:
                points = self.get_entity_points(entity)
                if len(points) == 2:
                    # 원과의 접촉 검사
                    p1 = points[0]
                    p2 = points[1]
                    
                    # 선분과 원의 최소 거리 계산
                    min_distance = self.line_to_circle_distance(p1, p2, center, radius)
                    
                    if min_distance < 0.5:  # 0.5mm 이내면 접촉으로 간주
                        touching_polylines.append((entity, min_distance))
                        
                        if min_distance < 0.1:
                            self.used_entities.add(entity)  # 사용된 엔티티로 표시
                            print(f"      - Found touching TPOINT at distance {min_distance:.3f}mm")
                            return entity
        
        print(f"    - Found {len(touching_polylines)} touching 2-point polylines")
        
        # 가장 가까운 것 선택
        if touching_polylines:
            touching_polylines.sort(key=lambda x: x[1])
            closest_entity, dist = touching_polylines[0]
            self.used_entities.add(closest_entity)  # 사용된 엔티티로 표시
            print(f"      - Using closest TPOINT at distance {dist:.3f}mm")
            return closest_entity
        
        return None
    
    def line_to_circle_distance(self, p1: Vec3, p2: Vec3, center: Vec3, radius: float) -> float:
        """선분과 원 사이의 최소 거리"""
        # 선분의 가장 가까운 점 찾기
        closest_point = self.closest_point_on_line(center, p1, p2)
        
        # 원 중심에서 가장 가까운 점까지의 거리
        dist_to_center = (closest_point - center).magnitude
        
        # 원의 가장 가까운 경계까지의 거리
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
        # 1. TPOINT의 점들 중 INSTNO 중심에 가장 가까운 점 찾기
        tpoint_points = self.get_entity_points(tpoint)
        if not tpoint_points:
            return None
        
        # INSTNO 중심에 가장 가까운 TPOINT의 점 찾기
        min_dist = float('inf')
        closest_tpoint = None
        for point in tpoint_points:
            dist = (point - center).magnitude
            if dist < min_dist:
                min_dist = dist
                closest_tpoint = point
        
        print(f"    - Closest TPOINT to INSTNO center: {closest_tpoint}, distance: {min_dist:.2f}mm")
        
        # TP 계산 (INSTNO 중심 기준 가장 가까운 TPOINT 점의 180도 반대편)
        tp = self.get_opposite_point(center, closest_tpoint)
        print(f"    - TP (target point): {tp}")
        
        if not tbox or not itag:
            print("    - TBOX or ITAG missing, cannot proceed with combined movement")
            return None
        
        # 2. TBOX와 ITAG의 전체 중심 계산
        tbox_points = self.get_entity_points(tbox)
        if not tbox_points:
            return None
            
        # TBOX 중심
        tbox_center = Vec3(0, 0, 0)
        for point in tbox_points:
            tbox_center += point
        tbox_center = tbox_center / len(tbox_points)
        
        # ITAG 위치
        itag_pos = Vec3(itag.dxf.insert)
        
        # TBOX+ITAG의 전체 중심
        combined_center = (tbox_center + itag_pos) / 2
        print(f"    - TBOX center: {tbox_center}")
        print(f"    - ITAG position: {itag_pos}")
        print(f"    - Combined center: {combined_center}")
        
        # 3. 1차 이동: 전체 중심을 TP로
        offset1 = tp - combined_center
        
        # TBOX와 ITAG를 함께 이동
        tbox.translate(offset1.x, offset1.y, offset1.z)
        itag.dxf.insert = Vec3(itag.dxf.insert) + offset1
        
        print(f"    - 1st move: offset = {offset1}")
        
        # 4. 이동 후 TBOX 점들 중 INSTNO 중심에서 가장 가까운 점 찾기
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
        
        # 5. 2차 이동: 가장 가까운 점을 TP로 (TBOX와 ITAG 함께)
        offset2 = tp - closest_point
        
        # TBOX와 ITAG를 다시 함께 이동
        tbox.translate(offset2.x, offset2.y, offset2.z)
        itag.dxf.insert = Vec3(itag.dxf.insert) + offset2
        
        print(f"    - 2nd move: offset = {offset2}")
        print(f"    - Total movement: {offset1 + offset2}")
        
        # 6. 색상 변경
        if tbox:
            tbox.dxf.color = 2  # YELLOW = 2
            self.used_entities.add(tbox)  # 사용된 엔티티로 표시
            print("    - TBOX color changed to YELLOW")
        if itag:
            itag.dxf.color = 4  # CYAN = 4
            self.used_entities.add(itag)  # 사용된 엔티티로 표시
            print("    - ITAG color changed to CYAN")
        
        # 최종 FTP는 TP와 동일
        ftp = tp
        print(f"    - Final FTP: {ftp}")
        
        return ftp
    
    def find_insttag_texts(self, instno_circle: DXFEntity) -> List[DXFEntity]:
        """INSTNO 원 둘레에서 2.5mm 이내에 있는 조건에 맞는 TEXT 찾기"""
        insttag_texts = []
        
        # INSTNO 원의 중심과 반지름
        center = Vec3(instno_circle.dxf.center)
        radius = instno_circle.dxf.radius
        
        # 모든 TEXT 엔티티 검사
        for text_entity in self.msp.query('TEXT'):
            # WDNO 레이어 제외
            if text_entity.dxf.layer == "WDNO":
                continue
                
            # 기울기 확인 (0도만)
            rotation = text_entity.dxf.rotation
            if abs(rotation) > 0.1:  # 0도가 아니면 제외
                continue
            
            # 텍스트 내용 확인
            text_content = text_entity.dxf.text.strip()
            
            # <>, x를 포함하는 텍스트 제외
            if '<' in text_content or '>' in text_content or 'x' in text_content.lower():
                continue
            
            text_pos = Vec3(text_entity.dxf.insert)
            
            # 텍스트에서 원 중심까지의 거리
            dist_to_center = (text_pos - center).magnitude
            
            # 원 둘레에서의 거리 계산
            dist_to_circle = abs(dist_to_center - radius)
            
            # 1.5mm 이내면 INSTTAG로 추가
            if dist_to_circle <= 2.5:
                insttag_texts.append(text_entity)
                print(f"        - Found INSTTAG: '{text_entity.dxf.text}' at distance {dist_to_circle:.2f}mm from circle")
        
        return insttag_texts
    
    def get_text_bounding_box_center(self, text_entity: DXFEntity) -> Vec3:
        """TEXT 엔티티의 바운딩 박스 중심 계산"""
        # 텍스트 삽입점
        insert_point = Vec3(text_entity.dxf.insert)
        
        # 텍스트 높이
        text_height = text_entity.dxf.height
        
        # 텍스트 내용
        text_content = text_entity.dxf.text
        
        # 텍스트 길이 추정 (대략적으로 문자 수 * 높이 * 0.7)
        text_length = len(text_content) * text_height * 0.7
        
        # 텍스트 회전 각도
        rotation = math.radians(text_entity.dxf.rotation)
        
        # 텍스트 정렬 확인 (halign: 0=LEFT, 1=CENTER, 2=RIGHT)
        halign = text_entity.dxf.halign if hasattr(text_entity.dxf, 'halign') else 0
        valign = text_entity.dxf.valign if hasattr(text_entity.dxf, 'valign') else 0
        
        # 수평 오프셋 계산
        if halign == 0:  # LEFT
            h_offset = text_length / 2
        elif halign == 1:  # CENTER
            h_offset = 0
        elif halign == 2:  # RIGHT
            h_offset = -text_length / 2
        else:
            h_offset = text_length / 2
        
        # 수직 오프셋 계산 (valign: 0=BASELINE, 1=BOTTOM, 2=MIDDLE, 3=TOP)
        if valign == 0 or valign == 1:  # BASELINE or BOTTOM
            v_offset = text_height / 2
        elif valign == 2:  # MIDDLE
            v_offset = 0
        elif valign == 3:  # TOP
            v_offset = -text_height / 2
        else:
            v_offset = text_height / 2
        
        # 회전을 고려한 중심점 계산
        dx = h_offset * math.cos(rotation) - v_offset * math.sin(rotation)
        dy = h_offset * math.sin(rotation) + v_offset * math.cos(rotation)
        
        center = Vec3(insert_point.x + dx, insert_point.y + dy, insert_point.z)
        
        return center
    
    def get_polyline_center(self, polyline: DXFEntity) -> Vec3:
        """폴리라인의 중심점 계산 (중복점 제거)"""
        points = self.get_entity_points(polyline)
        if not points:
            return None
        
        # 닫힌 폴리라인의 경우 마지막 점이 첫 점과 같을 수 있으므로 확인
        unique_points = []
        for i, point in enumerate(points):
            # 마지막 점이고 첫 점과 같으면 제외
            if i == len(points) - 1 and len(unique_points) > 0:
                if (point - unique_points[0]).magnitude < 0.001:
                    continue
            unique_points.append(point)
        
        # 중심 계산
        if len(unique_points) == 4:  # 사각형인 경우
            # 대각선의 교점을 중심으로 사용
            center = (unique_points[0] + unique_points[2]) / 2
        else:
            # 모든 점의 평균
            center = Vec3(0, 0, 0)
            for point in unique_points:
                center += point
            center = center / len(unique_points)
        
        return center
    
    def move_text_center_to_point(self, text_entity: DXFEntity, target_center: Vec3):
        """TEXT 엔티티의 중심을 목표 지점으로 이동"""
        # 현재 텍스트 박스의 중심
        current_center = self.get_text_bounding_box_center(text_entity)
        
        # 이동 벡터 계산
        offset = target_center - current_center
        
        # 텍스트 삽입점 이동
        current_insert = Vec3(text_entity.dxf.insert)
        text_entity.dxf.insert = current_insert + offset
    
    def stretch_entity_point(self, entity: DXFEntity, point_to_move: Vec3, stretch_vector: Vec3):
        """폴리라인의 특정 점만 STRETCH"""
        if entity.dxftype() == "LWPOLYLINE":
            # LWPOLYLINE의 점들 가져오기
            points = list(entity.get_points('xy'))
            new_points = []
            
            for p in points:
                point = Vec3(p[0], p[1], 0)
                # 이동할 점과 거의 같은 위치의 점을 찾아서 이동
                if (point - point_to_move).magnitude < 0.001:
                    new_point = point + stretch_vector
                    new_points.append((new_point.x, new_point.y))
                else:
                    new_points.append((p[0], p[1]))
            
            # 새로운 점들로 폴리라인 업데이트
            entity.set_points(new_points)
            
        elif entity.dxftype() == "POLYLINE":
            # POLYLINE의 정점들 처리
            for vertex in entity.vertices:
                vertex_pos = Vec3(vertex.dxf.location)
                if (vertex_pos - point_to_move).magnitude < 0.001:
                    vertex.dxf.location = vertex_pos + stretch_vector
    
    def stretch_entity(self, entity: DXFEntity, base_point: Vec3, stretch_vector: Vec3):
        """엔티티를 base_point 기준으로 stretch_vector만큼 늘이기"""
        if entity.dxftype() == "TEXT":
            # TEXT는 단순 이동
            current_pos = Vec3(entity.dxf.insert)
            entity.dxf.insert = current_pos + stretch_vector
            
        elif entity.dxftype() in ["POLYLINE", "LWPOLYLINE"]:
            # 폴리라인의 각 점을 이동
            entity.translate(stretch_vector.x, stretch_vector.y, stretch_vector.z)
            
        elif entity.dxftype() == "CIRCLE":
            # 원은 중심점 이동
            center = Vec3(entity.dxf.center)
            entity.dxf.center = center + stretch_vector
    
    def process_ig_and_stretch(self):
        """IG 처리 및 STRETCH 작업"""
        # 1. RED 색상 폴리라인(IG) 찾기 및 레이어/색상 변경
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
        
        # 앞에서 찾았던 각 INSTNO 원에 대해 처리
        for instno_idx, instno in enumerate(self.instno_circles):
            print(f"\n  Processing INSTNO group {instno_idx + 1}")
            
            # 저장된 INSTNO 데이터 가져오기
            if instno not in self.instno_data:
                print("    - No data found for this INSTNO")
                continue
                
            instno_info = self.instno_data[instno]
            instno_center = instno_info['center']
            
            # INSTTAG 텍스트들 찾기 (INSTNO 원 둘레 2.5mm 이내)
            insttag_texts = self.find_insttag_texts(instno)
            print(f"    - Found {len(insttag_texts)} INSTTAG texts")
            
            # 저장된 TBOX와 ITAG 가져오기
            tbox = instno_info.get('tbox')
            itag = instno_info.get('itag')
            
            if tbox:
                print("    - Using previously found TBOX (YELLOW)")
            if itag:
                print(f"    - Using previously found ITAG (CYAN): '{itag.dxf.text}'")
                print("    - Note: ITAG was already moved with TBOX in previous step")
            
            # 가장 가까운 IG 찾기 (TPOINT로 사용된 A2일 수 있음)
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
            
            # IG1, IG2 점 계산
            ig_points = self.get_entity_points(closest_ig)
            if len(ig_points) < 2:
                continue
            
            # INSTNO 중심에 가까운 점이 IG2, 먼 점이 IG1
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
            
            # STRETCH 방향 벡터 계산 (IG1에서 IG2 방향으로 11mm)
            direction = (ig2 - ig1).normalize()
            stretch_vector = direction * 11.0
            
            print(f"    - Stretch direction: {direction}")
            print(f"    - Stretch vector: {stretch_vector} (11mm)")
            
            # INST 그룹 (INSTNO + INSTTAG + TBOX + ITAG) STRETCH
            # IG2 점만 STRETCH (IG1은 고정, IG2만 이동)
            self.stretch_entity_point(closest_ig, ig2, stretch_vector)
            print("    - IG2 point stretched (IG1 remains fixed)")
            
            # INSTNO (원) 이동
            self.stretch_entity(instno, ig2, stretch_vector)
            
            # INSTTAG 텍스트들 이동
            for text in insttag_texts:
                self.stretch_entity(text, ig2, stretch_vector)
            
            # TBOX 이동
            if tbox:
                self.stretch_entity(tbox, ig2, stretch_vector)
            
            # ITAG 이동
            if itag:
                self.stretch_entity(itag, ig2, stretch_vector)
            
            # STRETCH 완료 후 ITAG를 TBOX 중심으로 이동
            if tbox and itag:
                # TBOX 중심 계산 (중복점 제거하여 정확한 중심 계산)
                tbox_center = self.get_polyline_center(tbox)
                
                if tbox_center:
                    # ITAG 텍스트의 바운딩 박스 중심을 TBOX 중심으로 이동
                    self.move_text_center_to_point(itag, tbox_center)
                    print(f"    - TBOX center: {tbox_center}")
                    
                    # 디버그 정보 출력
                    itag_center = self.get_text_bounding_box_center(itag)
                    print(f"    - ITAG text: '{itag.dxf.text}', height: {itag.dxf.height:.2f}")
                    print(f"    - ITAG final center: {itag_center}")
                    
                    # TBOX 점들 정보
                    tbox_points = self.get_entity_points(tbox)
                    print(f"    - TBOX has {len(tbox_points)} points")
                    if len(tbox_points) == 5 and (tbox_points[0] - tbox_points[-1]).magnitude < 0.001:
                        print("    - TBOX is a closed polyline (first and last points are same)")
            
            print(f"    - STRETCH completed for INST group {instno_idx + 1}")
    
    def move_entity_to_point(self, entity: DXFEntity, target_point: Vec3):
        """엔티티를 목표 지점으로 이동"""
        if entity.dxftype() == "TEXT":
            current_pos = Vec3(entity.dxf.insert)
            offset = target_point - current_pos
            entity.dxf.insert = target_point
        elif entity.dxftype() in ["POLYLINE", "LWPOLYLINE"]:
            points = self.get_entity_points(entity)
            if points:
                offset = target_point - points[0]
                # 폴리라인 이동 구현
                entity.translate(offset.x, offset.y, offset.z)
    
    def lines_intersect(self, p1: Vec3, p2: Vec3, p3: Vec3, p4: Vec3) -> bool:
        """두 선분이 교차하는지 확인"""
        # 2D 교차 검사 간단 구현
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
    
    def process_dxf_file(self, filepath: str):
        """DXF 파일 처리 메인 함수"""
        print(f"Processing: {filepath}")
        self.load_dxf(filepath)
        
        # 사용된 엔티티 초기화
        self.used_entities = set()
        self.a1_a2_a3_entities = set()  # A1, A2, A3 엔티티 추적 초기화
        self.instno_data = {}  # INSTNO 데이터 초기화
        
        # 1. INSTNO 레이어의 원(CIRCLE) 찾기
        self.instno_circles = self.find_instno_circles()
        print(f"Found {len(self.instno_circles)} INSTNO circles")
        
        for idx, instno in enumerate(self.instno_circles):
            print(f"\nProcessing INSTNO {idx + 1}/{len(self.instno_circles)}")
            
            # INSTNO를 사용된 엔티티로 표시
            self.used_entities.add(instno)
            
            # 원의 중심과 반지름 직접 가져오기
            center = Vec3(instno.dxf.center)
            radius = instno.dxf.radius
            
            # INSTNO 데이터 초기화
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
                # A2가 1개만 찾아진 경우
                print("  - Only 1 A2 found")
                a2 = a2_candidates[0]
                a2.dxf.color = 4  # CYAN = 4
                self.used_entities.add(a2)  # 사용된 엔티티로 표시
                self.a1_a2_a3_entities.add(a2)  # A2로 식별된 엔티티 추가
                print("    - A2 color changed to CYAN")
                
                # A1 찾기 시도
                a1 = self.find_a1_line(a2)
                
                if a1:
                    # A1을 찾은 경우 - 정상 처리
                    print("    - A1 found, proceeding with normal processing")
                    
                    # A3 찾기
                    a3 = self.find_a3_polyline(a1)
                    if not a3:
                        print("    - A3 not found")
                        continue
                    
                    # ALL 그룹 생성
                    all_group = [a1, a2, a3]
                    print("    - ALL group created (A1 + A2 + A3)")
                    
                    # TPOINT 찾기
                    tpoint = self.find_tpoint(instno)
                    if not tpoint:
                        print("    - TPOINT not found, using A2 as TPOINT")
                        tpoint = a2  # A2를 TPOINT로 사용
                        # A2를 TPOINT로 사용할 때 RED로 변경
                        tpoint.dxf.color = 1  # RED = 1
                        print("    - A2 color changed to RED (used as TPOINT)")
                    else:
                        self.used_entities.add(tpoint)  # TPOINT를 사용된 엔티티로 표시
                else:
                    # A1을 못 찾은 경우 - A2를 TPOINT로 사용
                    print("    - A1 not found, using A2 as TPOINT")
                    tpoint = a2
                    # A2를 TPOINT로 사용할 때 RED로 변경
                    tpoint.dxf.color = 1  # RED = 1
                    print("    - A2 color changed to RED (used as TPOINT)")
                    all_group = None  # A1과 A3가 없으므로 ALL 그룹 없음
                
            else:
                # A2가 2개 찾아진 경우
                print("  - 2 A2 candidates found")
                
                # 각 A2에 대해 A1과 A3를 찾아보기
                a2_with_a1_a3 = None
                a2_for_tpoint = None
                all_group = None
                
                for idx_a2, a2_candidate in enumerate(a2_candidates):
                    print(f"    - Checking A2 candidate {idx_a2 + 1}")
                    a2_candidate.dxf.color = 4  # CYAN = 4
                    self.used_entities.add(a2_candidate)  # 사용된 엔티티로 표시
                    self.a1_a2_a3_entities.add(a2_candidate)  # A2로 식별된 엔티티 추가
                    
                    # A1 찾기 시도
                    a1_temp = self.find_a1_line(a2_candidate)
                    
                    if a1_temp:
                        # A3 찾기 시도
                        a3_temp = self.find_a3_polyline(a1_temp)
                        
                        if a3_temp:
                            # A1과 A3를 모두 찾은 경우
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
                
                # 결과 처리
                if a2_with_a1_a3:
                    # A1과 A3를 찾은 A2가 있는 경우
                    print("    - Using A2 with A1 and A3 for ALL group")
                    if a2_for_tpoint:
                        tpoint = a2_for_tpoint
                        # A2를 TPOINT로 사용할 때 RED로 변경
                        tpoint.dxf.color = 1  # RED = 1
                        print("    - Using other A2 as TPOINT, color changed to RED")
                    else:
                        # 모든 A2가 A1/A3를 가진 경우, 첫 번째를 TPOINT로 사용
                        tpoint = a2_candidates[0] if a2_candidates[0] != a2_with_a1_a3 else a2_candidates[1]
                        # A2를 TPOINT로 사용할 때 RED로 변경
                        tpoint.dxf.color = 1  # RED = 1
                        print("    - Using first A2 as TPOINT, color changed to RED")
                else:
                    # 어떤 A2도 A1/A3를 찾지 못한 경우
                    print("    - No A2 candidate has both A1 and A3")
                    continue
            
            # 공통 처리 부분
            # TBOX 찾기
            tbox = self.find_tbox(a2, center)
            if tbox:
                print("  - TBOX found")
                self.instno_data[instno]['tbox'] = tbox
            else:
                print("  - TBOX not found (optional)")
            
            # ITAG 찾기
            itag = self.find_itag_text(a2, center)
            if not itag:
                print("  - ITAG not found")
                continue
            
            self.instno_data[instno]['itag'] = itag
            self.instno_data[instno]['a2'] = a2
            self.instno_data[instno]['tpoint'] = tpoint
            
            # FTP 계산 및 이동 (TPOINT 사용)
            ftp = self.calculate_and_move_to_ftp(tbox, itag, center, tpoint)
            
            if ftp:
                print(f"  - Successfully processed INSTNO entity")
            else:
                print("  - Failed to calculate FTP")
        
        # 파일 저장 전에 A1, A2, A3로 식별되고 CYAN 색상인 엔티티만 삭제
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
        
        # 최종 단계: IG 처리 및 STRETCH
        print("\n=== Final Step: IG Processing and STRETCH ===")
        self.process_ig_and_stretch()
        
        # 파일 저장
        output_path = filepath.replace('.dxf', '_INST.DXF').replace('.DXF', '.DXF')
        self.doc.saveas(output_path)
        print(f"\nSaved to: {output_path}")

def main():
    processor = DXFProcessor()
    
    # DXF 파일 선택
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