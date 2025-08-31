import ezdxf
import tkinter as tk
from tkinter import filedialog
import os
import math
import numpy as np
from ezdxf.math import Vec3, intersection_line_line_2d
from ezdxf.entities import Circle, Text, Line, Arc, LWPolyline, Polyline


class A1LineFinder:
    """A1 및 연속된 A1-1 라인을 찾는 클래스"""
    
    def __init__(self):
        self.used_lines = set()  # 이미 사용된 라인 추적
    
    def distance_2d(self, p1, p2):
        """두 점 사이의 거리 계산"""
        return math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)
    
    def get_line_angle(self, start, end):
        """라인의 각도를 계산 (0~360도)"""
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        
        # 라디안을 도로 변환
        angle = math.atan2(dy, dx) * 180 / math.pi
        
        # 0~360도로 정규화
        if angle < 0:
            angle += 360
            
        return angle
    
    def check_welds_at_ap2(self, msp, ap2):
        """AP2에서 WELDS 원이 있는지 확인"""
        for entity in msp:
            if entity.dxftype() == 'CIRCLE' and entity.dxf.layer == 'WELDS':
                if 0.4 <= entity.dxf.radius <= 1.2:
                    dist_to_ap2 = self.distance_2d(ap2, entity.dxf.center)
                    if dist_to_ap2 <= 2.0:
                        return True
        return False
    
    def find_a1_from_wdc(self, msp, wdc_center, max_distance=3.0):
        """
        WDC 원 중심에서 가장 가까운 A1 라인과 연속된 라인들을 찾아 하나로 병합
        
        Returns:
        - (merged_a1_line, ap1, ap2) 튜플
        """
        
        # A1 후보들 수집
        candidates = []
        
        for entity in msp:
            if entity.dxftype() == 'LINE' and entity.dxf.layer == 'ISOTEXT':
                # 이미 사용된 라인 제외
                if entity in self.used_lines:
                    continue
                    
                start = entity.dxf.start
                end = entity.dxf.end
                
                # WDC 중심과 라인 양끝점 사이의 거리
                dist_start = self.distance_2d(wdc_center, start)
                dist_end = self.distance_2d(wdc_center, end)
                
                # 더 가까운 점 찾기
                if dist_start < dist_end:
                    if dist_start <= max_distance:
                        line_length = self.distance_2d(start, end)
                        candidates.append({
                            'line': entity,
                            'ap1': start,
                            'ap2': end,
                            'distance': dist_start,
                            'length': line_length
                        })
                else:
                    if dist_end <= max_distance:
                        line_length = self.distance_2d(start, end)
                        candidates.append({
                            'line': entity,
                            'ap1': end,
                            'ap2': start,
                            'distance': dist_end,
                            'length': line_length
                        })
        
        if not candidates:
            return None, None, None
        
        # 단일 후보인 경우
        if len(candidates) == 1:
            selected = candidates[0]
        else:
            # 여러 후보가 있는 경우 - WELDS 원 확인
            candidates_with_welds = []
            candidates_without_welds = []
            
            for candidate in candidates:
                ap2 = candidate['ap2']
                has_welds = False
                
                # AP2에서 2mm 이내의 WELDS 원 찾기
                for entity in msp:
                    if entity.dxftype() == 'CIRCLE' and entity.dxf.layer == 'WELDS':
                        if 0.4 <= entity.dxf.radius <= 1.2:
                            dist_to_ap2 = self.distance_2d(ap2, entity.dxf.center)
                            if dist_to_ap2 <= 2.0:
                                has_welds = True
                                break
                
                if has_welds:
                    candidates_with_welds.append(candidate)
                else:
                    candidates_without_welds.append(candidate)
            
            # 선택 우선순위
            if len(candidates_with_welds) == 1:
                selected = candidates_with_welds[0]
            elif len(candidates_with_welds) > 1:
                selected = min(candidates_with_welds, key=lambda x: x['length'])
            elif candidates_without_welds:
                selected = min(candidates_without_welds, key=lambda x: x['distance'])
            else:
                return None, None, None
        
        # 선택된 A1 라인
        first_line = selected['line']
        self.used_lines.add(first_line)
        
        # AP2에 WELDS 원이 있는지 확인
        has_welds_at_ap2 = self.check_welds_at_ap2(msp, selected['ap2'])
        
        if has_welds_at_ap2:
            # WELDS 원이 있으면 연속 라인 찾기를 하지 않음
            print("  → AP2에 WELDS 원이 있어 연속 라인 찾기 제외")
            first_line.dxf.layer = 'A1'
            return first_line, selected['ap1'], selected['ap2']
        else:
            # WELDS 원이 없으면 연속된 라인들 찾기
            continuous_lines = self.find_continuous_lines(msp, first_line)
            
            # 찾은 모든 라인들을 used_lines에 추가
            for line in continuous_lines:
                self.used_lines.add(line)
            
            # 병합할 라인들 (첫 번째 라인 + 연속된 라인들)
            all_lines = [first_line] + continuous_lines
            
            if len(all_lines) == 1:
                # 연속된 라인이 없는 경우, 원래 라인을 A1으로 변경
                first_line.dxf.layer = 'A1'
                return first_line, selected['ap1'], selected['ap2']
            else:
                # 여러 라인을 하나로 병합
                print(f"  → {len(all_lines)}개의 연속된 라인을 하나의 A1으로 병합")
                
                # 모든 라인의 시작점과 끝점 수집
                all_points = []
                for line in all_lines:
                    all_points.append(line.dxf.start)
                    all_points.append(line.dxf.end)
                
                # 가장 먼 두 점 찾기
                max_distance = 0
                merged_start = None
                merged_end = None
                
                for i, p1 in enumerate(all_points):
                    for j, p2 in enumerate(all_points):
                        if i < j:
                            dist = self.distance_2d(p1, p2)
                            if dist > max_distance:
                                max_distance = dist
                                merged_start = p1
                                merged_end = p2
                
                # 새로운 병합된 라인 생성
                merged_line = msp.add_line(merged_start, merged_end)
                merged_line.dxf.layer = 'A1'
                
                # 기존 라인들 삭제
                for line in all_lines:
                    msp.delete_entity(line)
                
                # AP1과 AP2 결정 (WDC에 가까운 점이 AP1)
                dist_start = self.distance_2d(wdc_center, merged_start)
                dist_end = self.distance_2d(wdc_center, merged_end)
                
                if dist_start < dist_end:
                    return merged_line, merged_start, merged_end
                else:
                    return merged_line, merged_end, merged_start
    
    def find_continuous_lines(self, msp, base_line, max_distance=8.0, angle_tolerance=1.0):
        """기준 라인과 연속된 라인들을 찾기"""
        continuous_lines = []
        
        # 기준 라인의 각도 계산
        base_start = base_line.dxf.start
        base_end = base_line.dxf.end
        base_angle = self.get_line_angle(base_start, base_end)
        
        # 방문한 라인 추적
        visited = set([base_line])
        
        # 재귀적으로 연속된 라인 찾기
        self._find_continuous_from_endpoints(
            msp, base_line, base_angle, max_distance, 
            angle_tolerance, continuous_lines, visited
        )
        
        return continuous_lines
    
    def _find_continuous_from_endpoints(self, msp, current_line, base_angle, max_distance, 
                                      angle_tolerance, continuous_lines, visited):
        """현재 라인의 양 끝점에서 연속된 라인 찾기 (재귀)"""
        current_start = current_line.dxf.start
        current_end = current_line.dxf.end
        
        for entity in msp:
            if entity.dxftype() == 'LINE' and entity.dxf.layer == 'ISOTEXT':
                # 이미 방문했거나 사용된 라인은 제외
                if entity in visited or entity in self.used_lines:
                    continue
                
                line_start = entity.dxf.start
                line_end = entity.dxf.end
                
                # 현재 라인의 끝점과 다음 라인의 시작점/끝점 사이 거리 확인
                connections = [
                    (current_end, line_start),
                    (current_end, line_end),
                    (current_start, line_start),
                    (current_start, line_end)
                ]
                
                for point1, point2 in connections:
                    dist = self.distance_2d(point1, point2)
                    if dist <= max_distance:
                        # 다음 라인 자체의 각도 확인
                        line_angle = self.get_line_angle(line_start, line_end)
                        
                        # 각도 차이 계산 (0-180도 사이로 정규화)
                        angle_diff = abs(line_angle - base_angle)
                        if angle_diff > 180:
                            angle_diff = 360 - angle_diff
                        
                        # 반대 방향(180도 차이)도 같은 기울기로 간주
                        if angle_diff > 90:
                            angle_diff = 180 - angle_diff
                        
                        if angle_diff <= angle_tolerance:
                            # 연결점 사이의 가상선 각도 확인 (일직선상에 있는지)
                            if dist > 0.001:  # 거의 같은 점이 아닌 경우
                                connection_angle = self.get_line_angle(point1, point2)
                                
                                # 연결선 각도와 base_angle 차이 계산
                                connection_angle_diff = abs(connection_angle - base_angle)
                                if connection_angle_diff > 180:
                                    connection_angle_diff = 360 - connection_angle_diff
                                
                                # 반대 방향도 같은 기울기로 간주
                                if connection_angle_diff > 90:
                                    connection_angle_diff = 180 - connection_angle_diff
                                
                                # 연결선도 같은 기울기여야 함 (일직선상)
                                if connection_angle_diff > angle_tolerance:
                                    continue
                            
                            # 모든 조건을 만족하면 연속된 라인으로 추가
                            continuous_lines.append(entity)
                            visited.add(entity)
                            
                            # 재귀적으로 이 라인에서 또 연속된 라인 찾기
                            self._find_continuous_from_endpoints(
                                msp, entity, base_angle, max_distance, 
                                angle_tolerance, continuous_lines, visited
                            )
                            break


class DXFProcessor:
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.a1_finder = A1LineFinder()  # A1 찾기 객체 생성
        
    def open_files(self):
        """DXF 파일 선택 대화상자 열기"""
        file_paths = filedialog.askopenfilenames(
            title="DXF 파일 선택",
            filetypes=[("DXF files", "*.dxf"), ("All files", "*.*")]
        )
        return file_paths
    
    def distance_2d(self, p1, p2):
        """2D 거리 계산"""
        return math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)
    
    def point_to_line_distance(self, point, line_start, line_end):
        """점과 선분 사이의 최단 거리 계산"""
        A = np.array([line_start[0], line_start[1]])
        B = np.array([line_end[0], line_end[1]])
        P = np.array([point[0], point[1]])
        
        AB = B - A
        AP = P - A
        
        if np.dot(AB, AB) == 0:
            return np.linalg.norm(AP)
        
        t = max(0, min(1, np.dot(AP, AB) / np.dot(AB, AB)))
        projection = A + t * AB
        
        return np.linalg.norm(P - projection), projection
    
    def get_circle_line_intersection(self, center, radius, line_start, line_end):
        """원과 선의 교점 찾기"""
        # 선을 매개변수 형태로 표현
        dx = line_end[0] - line_start[0]
        dy = line_end[1] - line_start[1]
        
        # 원의 중심을 원점으로 이동
        fx = line_start[0] - center[0]
        fy = line_start[1] - center[1]
        
        a = dx * dx + dy * dy
        b = 2 * (fx * dx + fy * dy)
        c = fx * fx + fy * fy - radius * radius
        
        discriminant = b * b - 4 * a * c
        
        if discriminant < 0:
            return []
            
        discriminant = math.sqrt(discriminant)
        
        t1 = (-b - discriminant) / (2 * a)
        t2 = (-b + discriminant) / (2 * a)
        
        # 선분 내의 교점만 찾기
        intersections = []
        if 0 <= t1 <= 1:
            intersections.append((line_start[0] + t1 * dx, line_start[1] + t1 * dy))
        if 0 <= t2 <= 1:
            intersections.append((line_start[0] + t2 * dx, line_start[1] + t2 * dy))
            
        return intersections
    
    def create_text_box(self, text_entity):
        """텍스트를 박스화하여 경계 상자와 중심 반환"""
        if not text_entity:
            return None, None
            
        text_height = text_entity.dxf.height
        text_content = text_entity.dxf.text
        text_width = len(text_content) * text_height * 0.7  # 대략적인 너비
        
        insert_point = text_entity.dxf.insert
        rotation = math.radians(text_entity.dxf.rotation)
        
        # 텍스트 박스의 네 모서리 계산 (원점 기준)
        corners = [
            (0, -text_height * 0.2),
            (text_width, -text_height * 0.2),
            (text_width, text_height),
            (0, text_height)
        ]
        
        # 박스 중심 계산 (원점 기준)
        box_center_local = (text_width / 2, text_height * 0.4)
        
        # 회전 적용
        rotated_corners = []
        for x, y in corners:
            rx = x * math.cos(rotation) - y * math.sin(rotation) + insert_point[0]
            ry = x * math.sin(rotation) + y * math.cos(rotation) + insert_point[1]
            rotated_corners.append((rx, ry))
        
        # 박스 중심의 실제 위치 계산
        box_center = (
            box_center_local[0] * math.cos(rotation) - box_center_local[1] * math.sin(rotation) + insert_point[0],
            box_center_local[1] * math.cos(rotation) + box_center_local[0] * math.sin(rotation) + insert_point[1]
        )
            
        return rotated_corners, box_center
    
    def move_text_box_by_center(self, text_entity, new_center):
        """텍스트 박스의 중심을 새로운 위치로 이동"""
        if text_entity:
            # 현재 박스의 중심 위치 계산
            _, current_center = self.create_text_box(text_entity)
            
            # 중심 이동에 필요한 오프셋 계산
            offset_x = new_center[0] - current_center[0]
            offset_y = new_center[1] - current_center[1]
            
            # 텍스트 엔티티 이동
            current_insert = text_entity.dxf.insert
            text_entity.dxf.insert = (
                current_insert[0] + offset_x,
                current_insert[1] + offset_y,
                current_insert[2]
            )
    
    def check_wd_interference_with_self_exclude(self, msp, wdc_center, wdc_radius, wdt_text, current_wdc, check_boundary=None):
        """WD(WDC+WDT) 전체의 간섭 체크 - 자기 자신만 제외"""
        check_radius = wdc_radius + 0.1  # WCHK
        
        # WDT 박스 corners 계산
        text_box_corners = None
        if wdt_text:
            text_box_corners, _ = self.create_text_box(wdt_text)
        
        for entity in msp:
            # 자기 자신의 WDC는 제외
            if entity == current_wdc:
                continue
            # 자기 자신의 WDT는 제외
            if entity == wdt_text:
                continue
            # WL, WELDS, A1 레이어는 제외
            if entity.dxf.layer in ['WL', 'WL1', 'A1']:
                continue
            # WELDS 레이어의 선은 제외
            if entity.dxftype() == 'LINE' and entity.dxf.layer == 'WELDS':
                continue
            
            # 간섭 체크 범위 제한
            if check_boundary is not None:
                entity_approx_pos = None
                entity_approx_radius = 0
                
                if entity.dxftype() == 'CIRCLE':
                    entity_approx_pos = entity.dxf.center
                    entity_approx_radius = entity.dxf.radius
                elif entity.dxftype() == 'LINE':
                    start = entity.dxf.start
                    end = entity.dxf.end
                    entity_approx_pos = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
                    entity_approx_radius = self.distance_2d(start, end) / 2
                elif entity.dxftype() == 'TEXT':
                    entity_approx_pos = entity.dxf.insert
                    entity_approx_radius = entity.dxf.height * 2
                elif entity.dxftype() == 'ARC':
                    entity_approx_pos = entity.dxf.center
                    entity_approx_radius = entity.dxf.radius
                
                if entity_approx_pos:
                    dist_to_entity = self.distance_2d(wdc_center, entity_approx_pos)
                    if dist_to_entity > check_boundary + entity_approx_radius:
                        continue
                        
            # 텍스트인 경우 BOX화하여 체크
            if entity.dxftype() == 'TEXT':
                text_box_corners_other, _ = self.create_text_box(entity)
                if text_box_corners_other:
                    # WDC와 텍스트 박스의 간섭 체크
                    for corner in text_box_corners_other:
                        if self.distance_2d(corner, wdc_center) < check_radius:
                            return True
                    
                    # WDT 박스와 다른 텍스트 박스의 간섭 체크
                    if text_box_corners:
                        for wdt_corner in text_box_corners:
                            for text_corner in text_box_corners_other:
                                if self.distance_2d(wdt_corner, text_corner) < 0.5:
                                    return True
                                    
            elif entity.dxftype() == 'CIRCLE':
                center = entity.dxf.center
                radius = entity.dxf.radius
                distance = self.distance_2d(wdc_center, center)
                if distance < check_radius + radius:
                    return True
                    
            elif entity.dxftype() == 'LINE':
                start = entity.dxf.start
                end = entity.dxf.end
                dist, _ = self.point_to_line_distance(wdc_center, start, end)
                if dist < check_radius:
                    return True
                    
        return False
    
    def get_iso_perpendicular_angle(self, line_start, line_end):
        """ISO 도면에서 선분에 대한 직교 각도 계산"""
        # ISO 도면의 기본 각도: 30°, 90°, 150°, 210°, 270°, 330°
        dx = line_end[0] - line_start[0]
        dy = line_end[1] - line_start[1]
        
        # 선분의 각도 계산
        line_angle = math.degrees(math.atan2(dy, dx))
        if line_angle < 0:
            line_angle += 360
            
        # ISO 직교 각도 계산 (90도 추가, 하지만 ISO 그리드에 맞춤)
        # ISO 그리드의 주요 각도에 가장 가까운 직교 각도 찾기
        iso_angles = [0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330]
        
        # 현재 선분 각도에 가장 가까운 ISO 각도 찾기
        closest_iso = min(iso_angles, key=lambda x: min(abs(x - line_angle), abs(x - line_angle + 360), abs(x - line_angle - 360)))
        
        # ISO 직교 각도 계산
        if closest_iso in [30, 210]:  # 30도 선
            perp_angle = closest_iso + 60  # 90도가 아닌 60도 회전 (ISO 특성)
        elif closest_iso in [150, 330]:  # 150도 선
            perp_angle = closest_iso - 60
        else:  # 수직/수평선
            perp_angle = closest_iso + 90
            
        return perp_angle % 360
    
    def rotate_point_around_center(self, point, center, angle_degrees):
        """점을 중심점 주위로 회전"""
        angle_rad = math.radians(angle_degrees)
        cos_angle = math.cos(angle_rad)
        sin_angle = math.sin(angle_rad)
        
        # 중심점을 원점으로 이동
        dx = point[0] - center[0]
        dy = point[1] - center[1]
        
        # 회전
        new_x = dx * cos_angle - dy * sin_angle
        new_y = dx * sin_angle + dy * cos_angle
        
        # 원래 위치로 이동
        return (new_x + center[0], new_y + center[1], point[2])
    
    def find_ap2_from_wl_line(self, wl_line, wdc_center):
        """WL 라인에서 WDC 원 중심에서 먼 끝점을 AP2로 찾기"""
        if not wl_line:
            return None
            
        start = wl_line.dxf.start
        end = wl_line.dxf.end
        
        dist_start = self.distance_2d(wdc_center, start)
        dist_end = self.distance_2d(wdc_center, end)
        
        # WDC 원 중심에서 더 먼 점이 AP2
        if dist_start > dist_end:
            return start
        else:
            return end
    
    def process_welds_circles(self, msp):
        """WELDS 레이어의 원들을 처리하는 메서드"""
        welds_count = 0
        welds_processed = 0
        small_circles_created = 0
        
        print("\n=== WELDS 원 처리 시작 ===")
        print("처리 조건: WELDS 레이어, 반지름 0.4~1.2mm")
        
        # WELDS 레이어의 모든 원 찾기
        for entity in msp:
            if entity.dxftype() == 'CIRCLE' and entity.dxf.layer == 'WELDS':
                welds_count += 1
                radius = entity.dxf.radius
                
                # 반지름이 0.4~1.2mm 범위인 경우만 처리
                if 0.4 <= radius <= 1.2:
                    welds_processed += 1
                    
                    # 색상을 YELLOW (6)로 변경
                    entity.dxf.color = 6  # YELLOW
                    
                    # 원의 중심과 반지름 가져오기
                    center = entity.dxf.center
                    
                    print(f"\nWELDS 원 {welds_processed} - 중심: ({center[0]:.2f}, {center[1]:.2f}), 반지름: {radius:.2f}mm")
                    print(f"  → 색상을 YELLOW로 변경")
                    
                    # 0.2mm씩 작게 5개의 동심원 생성
                    print(f"  → 동심원 5개 생성 (0.2mm씩 감소)")
                    
                    for i in range(1, 6):  # 1부터 5까지
                        # 0.2mm씩 감소
                        new_radius = radius - (0.2 * i)
                        
                        # 반지름이 0.1mm 이상인 경우만 생성
                        if new_radius > 0.1:
                            # 동심원 생성 (같은 중심)
                            concentric_circle = msp.add_circle(center, new_radius)
                            concentric_circle.dxf.layer = 'WELDS'
                            concentric_circle.dxf.color = 6  # YELLOW
                            
                            small_circles_created += 1
                            print(f"  → 동심원 {i} 생성 - 중심: ({center[0]:.2f}, {center[1]:.2f}), 반지름: {new_radius:.2f}mm")
                        else:
                            print(f"  → 동심원 {i} 스킵 - 반지름 {new_radius:.2f}mm (너무 작음)")
                            break
                else:
                    print(f"\n[스킵] WELDS 원 - 반지름: {radius:.2f}mm (범위 벗어남)")
        
        print(f"\n=== WELDS 원 처리 완료 ===")
        print(f"전체 WELDS 원: {welds_count}개")
        print(f"처리된 WELDS 원 (0.4~1.2mm): {welds_processed}개")
        print(f"생성된 동심원: {small_circles_created}개")
        
        return welds_processed, small_circles_created
    
    def second_stage_processing(self, doc, wdc_data_list):
        """2단계 처리: WL이 4mm 이상인 WD를 회전하여 최적 위치 찾기"""
        msp = doc.modelspace()
        
        for wdc_data in wdc_data_list:
            wdc = wdc_data['wdc']
            wdt_text = wdc_data['wdt']
            ap2 = wdc_data['ap2']
            pipe1 = wdc_data.get('pipe1')
            wl_line = wdc_data.get('wl_line')
            st_position = wdc_data['st_position']  # 1차 작업의 원래 위치
            
            if not wl_line:
                print(f"\n[스킵] WL 선이 없음")
                continue
                
            if not pipe1:
                print(f"\n[스킵] PIPE가 없음")
                continue
                
            # WL 선의 실제 길이 계산 (원 경계에서 AP2까지)
            wl_start = wl_line.dxf.start
            wl_end = wl_line.dxf.end
            wl_length = self.distance_2d(wl_start, wl_end)
            
            # WDC 중심과 AP2 사이의 거리 계산
            wdc_to_ap2_distance = self.distance_2d(wdc.dxf.center, ap2)
            
            print(f"\nWL 길이 확인: {wl_length:.2f}mm (기준: 4mm)")
            print(f"WDC 중심-AP2 거리: {wdc_to_ap2_distance:.2f}mm")
            
            if wl_length < 4.0:
                continue
            
            # 2단계 대상 WDC 색상을 RED로 변경하고 터미널에 표시
            wdc.dxf.color = 1  # RED
            print(f"2단계 작업 대상 WDC - 중심: ({wdc.dxf.center[0]:.2f}, {wdc.dxf.center[1]:.2f})")
            print(f"  - WL 길이: {wl_length:.2f}mm")
            print(f"  - WDC-AP2 거리: {wdc_to_ap2_distance:.2f}mm")
                
            # 현재 위치를 ST2로 저장
            st2_position = wdc.dxf.center
            
            # 간섭 체크 범위 계산 (WD + A1 길이)
            a1_length = self.distance_2d(st2_position, ap2)
            check_boundary = wdc.dxf.radius + a1_length
            
            print(f"  AP2 위치: ({ap2[0]:.2f}, {ap2[1]:.2f})")
            print(f"  간섭 체크 범위: {check_boundary:.2f}mm")
            
            # MO 위치로 이동 (AP2에서 WDC 반지름 + 2.9mm)
            direction = np.array([st2_position[0] - ap2[0], st2_position[1] - ap2[1]])
            direction_norm = direction / np.linalg.norm(direction)
            mo_position = (
                ap2[0] + direction_norm[0] * (wdc.dxf.radius + 2.9),
                ap2[1] + direction_norm[1] * (wdc.dxf.radius + 2.9),
                st2_position[2]
            )
            
            # WDC와 WDT를 MO 위치로 이동
            wdc.dxf.center = mo_position
            if wdt_text:
                self.move_text_box_by_center(wdt_text, mo_position)
            
            # MO 위치에서 먼저 간섭 체크
            print(f"  MO 위치에서 간섭 체크...")
            # 임시로 MO 위치로 이동하여 체크
            original_wdc_center = wdc.dxf.center
            original_wdt_center = None
            if wdt_text:
                _, original_wdt_center = self.create_text_box(wdt_text)
                
            wdc.dxf.center = mo_position
            if wdt_text:
                self.move_text_box_by_center(wdt_text, mo_position)
                
            if not self.check_wd_interference_with_self_exclude(msp, mo_position, wdc.dxf.radius, wdt_text, wdc, check_boundary):
                # MO 위치에서 간섭 없음 - 이동 확정
                final_position = mo_position
                final_angle = 0
                found_position = True
                print(f"  → MO 위치에서 간섭 없음, 이동 확정")
            else:
                print(f"  → MO 위치에서 간섭 발생, 회전 검사 시작")
                
                # PIPE1의 직교 각도 계산 (ISO 도면 기준)
                perp_angle = self.get_iso_perpendicular_angle(pipe1.dxf.start, pipe1.dxf.end)
                
                # 10도 간격으로 360도 회전하며 간섭 체크 (시계방향)
                interference_free_positions = []
                
                print(f"  회전 간섭 체크 시작 (10도 간격)...")
                for angle in range(0, 360, 10):  # 0도부터 350도까지 10도 간격 (시계방향)
                    # AP2를 중심으로 회전
                    test_position = self.rotate_point_around_center(mo_position, ap2, angle)
                    
                    # 임시로 위치 이동
                    wdc.dxf.center = test_position
                    if wdt_text:
                        self.move_text_box_by_center(wdt_text, test_position)
                    
                    # 간섭 체크 (자기 자신만 제외)
                    has_interference = self.check_wd_interference_with_self_exclude(msp, test_position, wdc.dxf.radius, wdt_text, wdc, check_boundary)
                    
                    if not has_interference:
                        # 간섭 없는 위치 저장
                        interference_free_positions.append({
                            'position': test_position,
                            'angle': angle,
                            'abs_angle': (perp_angle + angle) % 360  # 절대 각도
                        })
                        print(f"    {angle:3d}도: 간섭 없음 ✓")
                    else:
                        print(f"    {angle:3d}도: 간섭 있음 ✗")
                    
                    # 다음 체크를 위해 원래 위치로 복원
                    wdc.dxf.center = original_wdc_center
                    if wdt_text and original_wdt_center:
                        self.move_text_box_by_center(wdt_text, original_wdt_center)
                
                print(f"  간섭 없는 위치 개수: {len(interference_free_positions)}")
                
                if interference_free_positions:
                    # ISO 직교 각도들 (30도 간격)
                    iso_orthogonal_angles = [0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330]
                    
                    # 각 위치의 직교 근접도 계산
                    for pos in interference_free_positions:
                        # 가장 가까운 직교 각도와의 차이 계산
                        min_diff = min([min(abs(pos['abs_angle'] - iso_angle), 
                                           abs(pos['abs_angle'] - iso_angle + 360),
                                           abs(pos['abs_angle'] - iso_angle - 360)) 
                                       for iso_angle in iso_orthogonal_angles])
                        pos['orthogonal_diff'] = min_diff
                    
                    # 직교에 가장 가까운 위치 찾기
                    best_position = min(interference_free_positions, key=lambda x: x['orthogonal_diff'])
                    
                    final_position = best_position['position']
                    final_angle = best_position['angle']
                    found_position = True
                    
                    print(f"  → 최적 위치 선택: 회전 각도 {final_angle}도 (직교 차이: {best_position['orthogonal_diff']:.1f}도)")
                else:
                    # 간섭 없는 위치를 찾지 못함
                    found_position = False
                    print(f"  → 모든 각도에서 간섭 발생, ST1(원래 위치)로 이동")
            
            # 최종 위치 결정
            if found_position:
                wdc.dxf.center = final_position
                if wdt_text:
                    # 해당 WDC의 WDT만 이동
                    self.move_text_box_by_center(wdt_text, final_position)
                print(f"  최종 위치: ({final_position[0]:.2f}, {final_position[1]:.2f}) - 회전 각도: {final_angle}°")
            else:
                # 모든 위치에서 간섭 발생 시 ST1(원래 위치)로
                wdc.dxf.center = st_position
                if wdt_text:
                    self.move_text_box_by_center(wdt_text, st_position)
                final_position = st_position
                print(f"  최종 위치: ST1 (원래 위치) - 모든 각도에서 간섭 발생")
                print(f"  ※ WDCD는 MO 위치에 유지됨")
            
            # WD 위치가 변경된 경우
            if final_position != st2_position:
                # 기존 WL 삭제
                if wl_line:
                    msp.delete_entity(wl_line)
                
                # 새로운 WL1 생성 및 TRIM
                intersections = self.get_circle_line_intersection(final_position, wdc.dxf.radius, final_position, ap2)
                
                if intersections and len(intersections) > 0:
                    # AP2에 가장 가까운 교점 선택 (원을 나가는 점)
                    exit_point = min(intersections, key=lambda p: self.distance_2d(p, ap2))
                    
                    # WDC 원 경계에서 AP2까지의 선만 생성
                    new_wl = msp.add_line(exit_point, ap2)
                    new_wl.dxf.layer = 'WL1'
                    new_wl.dxf.color = 7  # 흰색
                else:
                    # 교점을 못 찾은 경우 전체 선 생성
                    new_wl = msp.add_line(final_position, ap2)
                    new_wl.dxf.layer = 'WL1'
                    new_wl.dxf.color = 7
    
    def find_wdc_circles(self, msp):
        """반지름 1.5~3.4mm인 ISOTEXT 레이어 원 찾기"""
        wdc_circles = []
        for entity in msp:
            if entity.dxftype() == 'CIRCLE' and entity.dxf.layer == 'ISOTEXT':
                radius = entity.dxf.radius
                if 1.5 <= radius <= 3.4:
                    # WDC 레이어로 변경하고 색상을 CYAN으로 설정
                    entity.dxf.layer = 'WDC'
                    entity.dxf.color = 4  # CYAN
                    wdc_circles.append(entity)
        return wdc_circles
    
    def find_wdt_text(self, msp, wdc_circle):
        """WDC에서 4mm 범위 내의 수평 ISOTEXT 텍스트 찾기"""
        center = wdc_circle.dxf.center
        for entity in msp:
            if entity.dxftype() == 'TEXT' and entity.dxf.layer == 'ISOTEXT':
                text_pos = entity.dxf.insert
                distance = self.distance_2d(center, text_pos)
                rotation = entity.dxf.rotation
                
                # 기울기가 0 (수평)이고 4mm 이내
                if distance <= 4.0 and abs(rotation) < 0.1:
                    entity.dxf.layer = 'WDT'
                    return entity
        return None
    
    def find_pipe_lines(self, msp, ap2):
        """AP2에서 가장 가까운 PIPE 이름을 포함하는 레이어의 선 찾기 (거리 제한 없음, 최대 2개)"""
        pipe_lines = []
        
        # 디버깅: AP2 근처의 모든 레이어 확인
        found_layers = set()
        pipe_candidates = []
        
        for entity in msp:
            if entity.dxftype() == 'LINE':
                start = entity.dxf.start
                end = entity.dxf.end
                min_dist = min(self.distance_2d(ap2, start), self.distance_2d(ap2, end))
                
                if min_dist <= 10.0:  # 10mm 내의 레이어만 표시
                    found_layers.add(entity.dxf.layer)
                
                # PIPE 이름을 포함하는 모든 선을 후보로 저장
                if 'PIPE' in entity.dxf.layer.upper():
                    pipe_candidates.append({
                        'entity': entity,
                        'distance': min_dist,
                        'layer': entity.dxf.layer
                    })
        
        if found_layers:
            print(f"  AP2 근처(10mm 내) 레이어: {', '.join(sorted(found_layers))}")
        
        # 거리순으로 정렬하여 가장 가까운 2개 선택
        pipe_candidates.sort(key=lambda x: x['distance'])
        
        for i, candidate in enumerate(pipe_candidates[:2]):  # 최대 2개
            pipe = candidate['entity']
            pipe.pipe_name = f'PIPE{i+1}'
            pipe_lines.append(pipe)
            print(f"  PIPE{i+1} 찾음 (레이어: {candidate['layer']}, 거리: {candidate['distance']:.3f}mm)")
        
        return pipe_lines
    
    def find_elbo_arc(self, msp, ap2):
        """AP2에서 가장 가까운 ELBO 이름을 포함하는 레이어의 호 찾기 (거리 제한 없음)"""
        closest_elbo = None
        closest_distance = float('inf')
        
        for entity in msp:
            if entity.dxftype() == 'ARC' and 'ELBO' in entity.dxf.layer.upper():
                center = entity.dxf.center
                radius = entity.dxf.radius
                
                # 호 중심까지의 거리 - 반지름으로 호와의 최단 거리 계산
                dist_to_center = self.distance_2d(ap2, center)
                min_dist = abs(dist_to_center - radius)  # 호 위의 가장 가까운 점까지의 거리
                
                if min_dist < closest_distance:
                    closest_distance = min_dist
                    closest_elbo = entity
        
        if closest_elbo:
            closest_elbo.elbo_name = 'ELBO1'
            print(f"  ELBO 찾음 (레이어: {closest_elbo.dxf.layer}, 거리: {closest_distance:.3f}mm)")
            return closest_elbo
        
        return None
    
    def process_dxf_file(self, file_path):
        """DXF 파일 처리"""
        try:
            # DXF 파일 열기
            doc = ezdxf.readfile(file_path)
            msp = doc.modelspace()
            
            # WELDS 원 처리 (첫 번째 단계로 추가)
            welds_processed, small_circles_count = self.process_welds_circles(msp)
            
            # 1. WDC 원 찾기
            wdc_circles = self.find_wdc_circles(msp)
            
            # 각 WDC에 대한 데이터 저장
            wdc_data_collection = []
            
            for wdc in wdc_circles:
                wdc_center = wdc.dxf.center
                wdc_radius = wdc.dxf.radius
                
                print(f"\n처리 중 WDC - 중심: ({wdc_center[0]:.2f}, {wdc_center[1]:.2f})")
                
                # 2. WDT 텍스트 찾기
                wdt_text = self.find_wdt_text(msp, wdc)
                
                # 3. A1 및 연속된 라인들 찾기 (새로운 방식)
                a1_line, ap1, ap2 = self.a1_finder.find_a1_from_wdc(msp, wdc_center)
                
                if not a1_line or not ap2:
                    print(f"  → A1을 찾을 수 없음")
                    continue
                
                print(f"  → A1 찾음 (병합된 단일 라인)")
                
                # 4. PIPE 선 찾기
                pipe_lines = self.find_pipe_lines(msp, ap2)
                
                # 5. ELBO 호 찾기
                elbo_arc = self.find_elbo_arc(msp, ap2)
                
                # 6. WDT 텍스트 박스화 및 BOX 중심을 WDC 중심으로 이동
                st_position = wdc_center  # ST 위치 저장
                
                if wdt_text:
                    # 텍스트 박스의 중심을 WDC 중심으로 이동
                    self.move_text_box_by_center(wdt_text, wdc_center)
                
                # 7. WD 이동 위치 계산
                direction = np.array([wdc_center[0] - ap2[0], wdc_center[1] - ap2[1], 0])
                direction_length = np.linalg.norm(direction[:2])
                
                if direction_length == 0:
                    # WDC 중심과 AP2가 같은 위치인 경우
                    continue
                    
                direction_norm = direction[:2] / direction_length
                
                # 목표 거리: WDC 반지름 + 2.9mm
                target_distance = wdc_radius + 2.9
                
                # MO 위치 계산 (AP2에서 target_distance만큼 떨어진 위치)
                mo_position = (
                    ap2[0] + direction_norm[0] * target_distance,
                    ap2[1] + direction_norm[1] * target_distance,
                    ap2[2]
                )
                
                # 간섭 체크 범위 계산 (WD + A1 길이)
                a1_length = self.distance_2d(wdc_center, ap2)
                check_boundary = wdc_radius + a1_length
                
                # 8. WDC와 WDT를 MO 위치로 함께 이동
                wdc.dxf.center = mo_position
                if wdt_text:
                    self.move_text_box_by_center(wdt_text, mo_position)
                
                # 9. 간섭 체크
                interference = self.check_wd_interference_with_self_exclude(msp, mo_position, wdc_radius, wdt_text, wdc, check_boundary)
                
                final_position = mo_position
                
                if interference:
                    # 간섭이 있으면 1mm씩 ST 위치(원래 WDC 중심) 방향으로 이동
                    # 이동 방향: MO에서 ST로
                    back_direction = np.array([st_position[0] - mo_position[0], st_position[1] - mo_position[1]])
                    back_distance = np.linalg.norm(back_direction)
                    
                    if back_distance == 0:
                        # ST와 MO가 같은 위치인 경우 (이동할 곳이 없음)
                        continue
                        
                    back_direction_norm = back_direction / back_distance
                    
                    step = 1.0
                    max_distance = np.linalg.norm(back_direction)
                    max_steps = int(max_distance / step)
                    
                    found_position = False
                    
                    for i in range(1, max_steps + 1):
                        # 이동할 위치 계산 (MO에서 ST 방향으로)
                        test_position = (
                            mo_position[0] + back_direction_norm[0] * (step * i),
                            mo_position[1] + back_direction_norm[1] * (step * i),
                            mo_position[2]
                        )
                        
                        # WDC와 WDT를 함께 테스트 위치로 이동
                        wdc.dxf.center = test_position
                        if wdt_text:
                            self.move_text_box_by_center(wdt_text, test_position)
                        
                        # 간섭 체크
                        if not self.check_wd_interference_with_self_exclude(msp, test_position, wdc_radius, wdt_text, wdc, check_boundary):
                            final_position = test_position
                            found_position = True
                            break
                    
                    # 간섭 없는 위치를 찾지 못한 경우 ST 위치로
                    if not found_position:
                        final_position = st_position
                        wdc.dxf.center = final_position
                        if wdt_text:
                            self.move_text_box_by_center(wdt_text, final_position)
                
                # 10. WL 선 생성 및 WDC 원 안 부분 TRIM
                # 원과 선의 교점 찾기
                intersections = self.get_circle_line_intersection(final_position, wdc_radius, final_position, ap2)
                
                wl_line = None  # WL 라인 초기화
                
                if intersections and len(intersections) > 0:
                    # 교점들 중 AP2에 가장 가까운 점 선택 (원을 나가는 점)
                    exit_point = min(intersections, key=lambda p: self.distance_2d(p, ap2))
                    
                    # WDC 원 경계에서 AP2까지의 선만 생성 (원 안 부분은 TRIM)
                    wl_line = msp.add_line(exit_point, ap2)
                    wl_line.dxf.layer = 'WL'
                    wl_line.dxf.color = 7  # 흰색
                    
                    wl_length = self.distance_2d(exit_point, ap2)
                    print(f"  WL 생성 - 길이: {wl_length:.2f}mm")
                else:
                    # 교점이 없는 경우 (AP2가 원 안에 있거나 선이 원과 만나지 않는 경우)
                    dist_to_ap2 = self.distance_2d(final_position, ap2)
                    
                    if dist_to_ap2 > wdc_radius:
                        # AP2가 원 밖에 있지만 교점을 못 찾은 경우
                        # 전체 선 생성
                        wl_line = msp.add_line(final_position, ap2)
                        wl_line.dxf.layer = 'WL'
                        wl_line.dxf.color = 7
                        
                        wl_length = self.distance_2d(final_position, ap2)
                        print(f"  WL 생성 (전체) - 길이: {wl_length:.2f}mm")
                    else:
                        # AP2가 원 안에 있는 경우 - WL 생성하지 않음
                        print(f"  WL 생성 안함 - AP2가 WDC 원 안에 있음")
                
                # 11. A1 삭제
                if a1_line:
                    msp.delete_entity(a1_line)
                
                # 데이터 저장 (2차 처리를 위해)
                wdc_data_collection.append({
                    'wdc': wdc,
                    'wdt': wdt_text,
                    'ap2': ap2,
                    'pipe_lines': pipe_lines,
                    'wl_line': wl_line,
                    'st_position': st_position,
                    'final_position': final_position,
                    'a1_line': a1_line  # 병합된 A1 라인 저장
                })
            
            # 12. 파일 저장 (1차 작업 완료)
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            output_path = os.path.join(
                os.path.dirname(file_path),
                f"{base_name}_WDNO.DXF"
            )
            doc.saveas(output_path)
            print(f"\n1차 처리 완료: {output_path}")
            
            # 13. 2차 처리를 위해 파일 다시 열기
            doc2 = ezdxf.readfile(output_path)
            msp2 = doc2.modelspace()
            
            # 2차 처리를 위한 데이터 수집
            wdc_data_list = []
            
            # 디버깅: WDC와 WL 수 확인
            wdc_count = 0
            wl_count = 0
            
            for entity in msp2:
                if entity.dxftype() == 'CIRCLE' and entity.dxf.layer == 'WDC':
                    wdc_count += 1
                elif entity.dxftype() == 'LINE' and entity.dxf.layer == 'WL':
                    wl_count += 1
            
            print(f"\n2차 처리 준비 - WDC: {wdc_count}개, WL: {wl_count}개")
            
            # WDC 원 다시 찾기
            for entity in msp2:
                if entity.dxftype() == 'CIRCLE' and entity.dxf.layer == 'WDC':
                    wdc = entity
                    wdc_center = wdc.dxf.center
                    wdc_radius = wdc.dxf.radius
                    
                    print(f"\nWDC 확인 - 중심: ({wdc_center[0]:.2f}, {wdc_center[1]:.2f}), 반지름: {wdc_radius:.2f}")
                    
                    # 관련 요소들 찾기
                    wdt_text = None
                    wl_line = None
                    ap2 = None
                    pipe1 = None
                    
                    # WDT 찾기 (WDC 중심과 매우 가까운 텍스트만)
                    for text in msp2:
                        if text.dxftype() == 'TEXT' and text.dxf.layer == 'WDT':
                            try:
                                # 텍스트 박스의 중심 계산
                                _, text_center = self.create_text_box(text)
                                if text_center:
                                    # WDC 중심과 텍스트 박스 중심의 거리가 매우 가까운 경우만 (0.5mm 이내)
                                    if self.distance_2d(wdc_center, text_center) < 0.5:
                                        wdt_text = text
                                        break
                            except:
                                # 텍스트 박스 생성 실패 시 스킵
                                continue
                    
                    # WL 찾기 
                    for line in msp2:
                        if line.dxftype() == 'LINE' and line.dxf.layer == 'WL':
                            # WDC 근처의 WL 찾기 (더 넓은 범위로 확인)
                            dist_start = self.distance_2d(wdc_center, line.dxf.start)
                            dist_end = self.distance_2d(wdc_center, line.dxf.end)
                            
                            # 시작점 또는 끝점이 WDC 근처에 있는지 확인 (반지름 + 2mm 여유)
                            if dist_start <= wdc_radius + 2.0 or dist_end <= wdc_radius + 2.0:
                                wl_line = line
                                # AP2 찾기: WL 라인의 끝점 중 WDC 원 중심에서 먼 점
                                ap2 = self.find_ap2_from_wl_line(wl_line, wdc_center)
                                
                                wl_length = self.distance_2d(line.dxf.start, line.dxf.end)
                                wdc_to_ap2_distance = self.distance_2d(wdc_center, ap2)
                                
                                # WL 길이가 4mm 이상인 경우에만 CYAN으로 변경
                                if wl_length >= 4.0:
                                    wl_line.dxf.color = 4  # CYAN
                                    print(f"  WL 찾음 - 길이: {wl_length:.2f}mm (색상: CYAN)")
                                else:
                                    print(f"  WL 찾음 - 길이: {wl_length:.2f}mm (4mm 미만, 색상 유지)")
                                
                                print(f"  AP2 설정 - ({ap2[0]:.2f}, {ap2[1]:.2f})")
                                print(f"  WDC 중심-AP2 거리: {wdc_to_ap2_distance:.2f}mm")
                                break
                    
                    if not wl_line:
                        print(f"  WL을 찾을 수 없음")
                        continue
                    
                    if ap2:
                        # PIPE 찾기 - WL 라인의 끝점들에서 가장 가까운 PIPE 찾기 (거리 제한 없음)
                        closest_pipe = None
                        closest_distance = float('inf')
                        closest_layer = None
                        
                        for line in msp2:
                            if line.dxftype() == 'LINE' and 'PIPE' in line.dxf.layer.upper():
                                # WL의 시작점 또는 끝점에서 PIPE까지의 최소 거리 계산
                                dist_to_wl_start_from_pipe_start = self.distance_2d(wl_line.dxf.start, line.dxf.start)
                                dist_to_wl_start_from_pipe_end = self.distance_2d(wl_line.dxf.start, line.dxf.end)
                                dist_to_wl_end_from_pipe_start = self.distance_2d(wl_line.dxf.end, line.dxf.start)
                                dist_to_wl_end_from_pipe_end = self.distance_2d(wl_line.dxf.end, line.dxf.end)
                                
                                min_dist = min(dist_to_wl_start_from_pipe_start, dist_to_wl_start_from_pipe_end,
                                             dist_to_wl_end_from_pipe_start, dist_to_wl_end_from_pipe_end)
                                
                                # 가장 가까운 PIPE 업데이트
                                if min_dist < closest_distance:
                                    closest_distance = min_dist
                                    closest_pipe = line
                                    closest_layer = line.dxf.layer
                        
                        if closest_pipe:
                            pipe1 = closest_pipe
                            print(f"  PIPE 찾음 (레이어: {closest_layer}, 거리: {closest_distance:.3f}mm)")
                        else:
                            print(f"  PIPE를 찾을 수 없음 (PIPE 레이어가 없음)")
                        
                        # 데이터 저장
                        wdc_data = {
                            'wdc': wdc,
                            'wdt': wdt_text,
                            'ap2': ap2,
                            'pipe1': pipe1,
                            'wl_line': wl_line,
                            'st_position': wdc_center  # 현재 위치를 ST로 사용
                        }
                        wdc_data_list.append(wdc_data)
                        
                        # WL 길이가 4mm 미만인 경우 표시
                        if self.distance_2d(wl_line.dxf.start, wl_line.dxf.end) < 4.0:
                            print(f"  → WL < 4mm - 2차 처리 대상 아님")
                        else:
                            print(f"  → 2차 처리 후보로 추가")
            
            # 2차 처리 실행
            if wdc_data_list:
                print(f"\n=== 2차 처리 시작 (파일: {os.path.basename(file_path)}) ===")
                self.second_stage_processing(doc2, wdc_data_list)
                
                # 2차 처리 결과 저장
                doc2.saveas(output_path)
                print(f"=== 2차 처리 완료 ===\n")
            else:
                print("2차 처리 대상 없음 (WL < 4mm)\n")
            
            return True, output_path
            
        except Exception as e:
            return False, str(e)
    
    def run(self):
        """메인 실행 함수"""
        file_paths = self.open_files()
        
        if not file_paths:
            print("선택된 파일이 없습니다.")
            return
        
        for file_path in file_paths:
            success, result = self.process_dxf_file(file_path)
            
            if not success:
                print(f"처리 실패: {file_path} - {result}")
            else:
                print(f"처리 완료: {result}")

if __name__ == "__main__":
    print("="*50)
    print("DXF WELD NO. 처리 프로그램")
    print("="*50)
    processor = DXFProcessor()
    processor.run()