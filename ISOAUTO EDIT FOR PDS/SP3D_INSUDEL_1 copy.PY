import tkinter as tk
from tkinter import filedialog
import ezdxf
from ezdxf.math import Vec3
import os
import math

class DXFProcessor:
    """
    DXF 파일 처리 클래스
    INSUL = INSU + HC (INSU 텍스트와 HC/MM 텍스트의 조합)
    """
    def __init__(self):
        self.used_dbox_lines = set()  # 이미 사용된 DBOX 라인 추적
        self.used_ad1_lines = set()   # 이미 사용된 AD1 라인 추적
        self.used_ad2_lines = set()   # 이미 사용된 AD2 라인 추적
        self.used_ad3_lines = set()   # 이미 사용된 AD3 라인 추적
        self.used_del1_lines = set()  # 이미 사용된 DEL1 라인 추적
        self.used_ex1_lines = set()   # 이미 사용된 EX1 라인 추적
        self.used_hatches = set()     # 이미 사용된 HATCH 추적
        self.used_insu_texts = set()  # 이미 사용된 INSU 텍스트 추적
        self.used_hc_texts = set()    # 이미 사용된 HC 텍스트 추적
        
    def get_distance(self, p1, p2):
        """두 점 사이의 거리 계산"""
        return math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)
    
    def get_entity_bounds(self, entity):
        """엔티티의 경계 상자 반환"""
        if hasattr(entity, 'get_pos'):
            pos = entity.get_pos()
            return (pos[0], pos[1], pos[0], pos[1])
        elif hasattr(entity, 'dxf') and hasattr(entity.dxf, 'start'):
            start = entity.dxf.start
            end = entity.dxf.end
            return (min(start[0], end[0]), min(start[1], end[1]), 
                   max(start[0], end[0]), max(start[1], end[1]))
        return None
    
    def find_all_text_with_keyword(self, msp, keyword):
        """키워드를 포함하는 모든 TEXT 엔티티 찾기"""
        texts = []
        for entity in msp.query('TEXT'):
            if keyword.upper() in entity.dxf.text.upper():
                texts.append(entity)
        for entity in msp.query('MTEXT'):
            if keyword.upper() in entity.text.upper():
                texts.append(entity)
        return texts
    
    def find_text_below(self, msp, base_text, keywords, x_tolerance=50, max_distance=10):
        """기준 텍스트 아래에서 첫 번째 키워드를 포함하는 텍스트 찾기
        x_tolerance: X 좌표 허용 오차 (기본값 50mm)
        max_distance: 최대 거리 제한 (기본값 10mm)
        """
        base_pos = base_text.dxf.insert if hasattr(base_text.dxf, 'insert') else base_text.get_pos()
        candidates = []
        
        # TEXT 엔티티 검색
        for entity in msp.query('TEXT'):
            # 이미 사용된 HC 텍스트는 제외
            if entity in self.used_hc_texts:
                continue
                
            pos = entity.dxf.insert
            # Y는 아래에 있고, X는 허용 오차 내에 있어야 함
            if pos[1] < base_pos[1] and abs(pos[0] - base_pos[0]) <= x_tolerance:
                text = entity.dxf.text.upper().strip()
                
                # INSU가 포함된 텍스트는 HC로 선택하지 않음
                if "INSU" in text:
                    continue
                
                # HC 또는 MM만 있어도 선택
                for keyword in keywords:
                    if keyword.upper() == text or keyword.upper() in text:
                        # 거리 계산 (X, Y 모두 고려)
                        distance = self.get_distance(pos, base_pos)
                        # 최대 거리 제한 확인
                        if distance <= max_distance:
                            candidates.append((entity, distance))
                            break
                        
        # MTEXT 엔티티 검색
        for entity in msp.query('MTEXT'):
            # 이미 사용된 HC 텍스트는 제외
            if entity in self.used_hc_texts:
                continue
                
            pos = entity.dxf.insert
            # Y는 아래에 있고, X는 허용 오차 내에 있어야 함
            if pos[1] < base_pos[1] and abs(pos[0] - base_pos[0]) <= x_tolerance:
                text = entity.text.upper().strip()
                
                # INSU가 포함된 텍스트는 HC로 선택하지 않음
                if "INSU" in text:
                    continue
                
                # HC 또는 MM만 있어도 선택
                for keyword in keywords:
                    if keyword.upper() == text or keyword.upper() in text:
                        # 거리 계산 (X, Y 모두 고려)
                        distance = self.get_distance(pos, base_pos)
                        # 최대 거리 제한 확인
                        if distance <= max_distance:
                            candidates.append((entity, distance))
                            break
        
        # 가장 가까운 텍스트 반환
        if candidates:
            candidates.sort(key=lambda x: x[1])  # 거리순 정렬
            return [candidates[0][0]]  # 첫 번째 텍스트만 반환
        
        return []
    
    def get_text_bounds(self, text_entity):
        """텍스트 엔티티의 경계 상자 계산
        텍스트 너비 = 문자수 × 높이 × 0.9 (기존 0.85에서 변경)
        """
        if hasattr(text_entity, 'dxf'):
            pos = text_entity.dxf.insert
            
            # TEXT 엔티티인 경우
            if hasattr(text_entity.dxf, 'height'):
                height = text_entity.dxf.height
                text_str = text_entity.dxf.text
                # 너비 추정 (문자 수 × 높이 × 0.9)
                width = len(text_str) * height * 0.9
                
                # 정렬 고려 (기본은 왼쪽 정렬)
                halign = getattr(text_entity.dxf, 'halign', 0)
                valign = getattr(text_entity.dxf, 'valign', 0)
                
                # 수평 정렬에 따른 조정
                if halign == 0:  # LEFT
                    min_x = pos[0]
                    max_x = pos[0] + width
                elif halign == 1:  # CENTER
                    min_x = pos[0] - width / 2
                    max_x = pos[0] + width / 2
                elif halign == 2:  # RIGHT
                    min_x = pos[0] - width
                    max_x = pos[0]
                else:
                    min_x = pos[0]
                    max_x = pos[0] + width
                
                # 수직 정렬에 따른 조정
                if valign == 0:  # BASELINE
                    min_y = pos[1]
                    max_y = pos[1] + height
                elif valign == 1:  # BOTTOM
                    min_y = pos[1]
                    max_y = pos[1] + height
                elif valign == 2:  # MIDDLE
                    min_y = pos[1] - height / 2
                    max_y = pos[1] + height / 2
                elif valign == 3:  # TOP
                    min_y = pos[1] - height
                    max_y = pos[1]
                else:
                    min_y = pos[1]
                    max_y = pos[1] + height
                    
                return (min_x, min_y, max_x, max_y)
            
            # MTEXT 엔티티인 경우
            elif hasattr(text_entity, 'text'):
                height = getattr(text_entity.dxf, 'char_height', 2.5)
                text_str = text_entity.text
                # 설정된 너비가 있으면 사용, 없으면 추정
                width = getattr(text_entity.dxf, 'width', len(text_str) * height * 0.9)
                
                # MTEXT는 일반적으로 왼쪽 상단이 기준점
                return (pos[0], pos[1] - height, pos[0] + width, pos[1])
        
        # 기본값
        return (pos[0], pos[1], pos[0], pos[1])
    
    def create_box_around_texts(self, texts):
        """텍스트들의 실제 크기를 고려한 박스 경계 반환
        텍스트 너비: 문자수 × 높이 × 0.9
        TBOX 높이: 원래 높이 × 0.8로 축소
        """
        if not texts:
            return None
            
        min_x = float('inf')
        min_y = float('inf')
        max_x = float('-inf')
        max_y = float('-inf')
        
        for text in texts:
            bounds = self.get_text_bounds(text)
            min_x = min(min_x, bounds[0])
            min_y = min(min_y, bounds[1])
            max_x = max(max_x, bounds[2])
            max_y = max(max_y, bounds[3])
        
        # 높이를 0.8배로 조정
        height = max_y - min_y
        center_y = (max_y + min_y) / 2
        new_height = height * 0.8
        min_y = center_y - new_height / 2
        max_y = center_y + new_height / 2
        
        # 약간의 여유 공간 추가 (2mm)
        margin = 2
        min_x -= margin
        min_y -= margin
        max_x += margin
        max_y += margin
            
        return [(min_x, min_y), (max_x, min_y), (max_x, max_y), (min_x, max_y)]
    
    def point_in_box(self, point, box_corners):
        """점이 박스 면적 내부에 있는지 확인"""
        x, y = point[0], point[1]
        min_x = min(corner[0] for corner in box_corners)
        max_x = max(corner[0] for corner in box_corners)
        min_y = min(corner[1] for corner in box_corners)
        max_y = max(corner[1] for corner in box_corners)
        
        return min_x <= x <= max_x and min_y <= y <= max_y
    
    def line_in_box(self, start, end, box_corners):
        """라인이 박스 면적 내부에 있는지 확인 (양 끝점이 박스 내부)"""
        return self.point_in_box(start, box_corners) and self.point_in_box(end, box_corners)
    
    def find_lines_near_box(self, msp, box_corners, distance, max_length):
        """TBOX 면적 내에 있는 라인 찾기 - 수평 2개, 수직 2개 선택"""
        horizontal_lines = []
        vertical_lines = []
        
        print(f"  TBOX 면적 내의 DBOX 찾기 (DIMLINES → DBOX 레이어로 이동, 5~25mm, PIPE/FITTINGS/WELDS 제외)...")
        
        # 모든 DIMLINES 라인을 검사하여 TBOX 면적 내에 있는 것 찾기
        horizontal_candidates = []
        vertical_candidates = []
        
        for entity in msp.query('LINE[layer=="DIMLINES"]'):
            # PIPE, FITTINGS, WELDS 레이어는 명시적으로 제외 (안전장치)
            if entity.dxf.layer in ["PIPE", "FITTINGS", "WELDS"]:
                continue
                
            # 이미 다른 INSU에서 사용된 라인 제외
            if entity in self.used_dbox_lines:
                continue
                
            start = Vec3(entity.dxf.start)
            end = Vec3(entity.dxf.end)
            length = (end - start).magnitude
            
            # 길이 조건: 5mm 이상, max_length 이하
            if length < 5 or length > max_length:
                continue
            
            # 수평 라인 (Y 좌표가 거의 같음)
            if abs(start.y - end.y) < 0.001:
                # 라인이 TBOX 면적 내에 있는지 확인
                if self.line_in_box(start, end, box_corners):
                    horizontal_candidates.append((entity, 0))  # 완전히 내부
                elif self.point_in_box(start, box_corners) or self.point_in_box(end, box_corners):
                    horizontal_candidates.append((entity, 1))  # 부분적으로 내부
            # 수직 라인 (X 좌표가 거의 같음)
            elif abs(start.x - end.x) < 0.001:
                # 라인이 TBOX 면적 내에 있는지 확인
                if self.line_in_box(start, end, box_corners):
                    vertical_candidates.append((entity, 0))  # 완전히 내부
                elif self.point_in_box(start, box_corners) or self.point_in_box(end, box_corners):
                    vertical_candidates.append((entity, 1))  # 부분적으로 내부
        
        print(f"  TBOX 면적 내에서 수평 {len(horizontal_candidates)}개, 수직 {len(vertical_candidates)}개 후보 발견 (5mm 이상)")
        
        # 우선순위에 따라 정렬 (완전히 내부인 것 우선)
        horizontal_candidates.sort(key=lambda x: x[1])
        vertical_candidates.sort(key=lambda x: x[1])
        
        # 수평 최대 2개, 수직 최대 2개 선택
        horizontal_lines = [item[0] for item in horizontal_candidates[:2]]
        vertical_lines = [item[0] for item in vertical_candidates[:2]]
        
        # 부족한 경우 TBOX 모서리 근처에서 추가 검색 (면적 확장)
        if len(horizontal_lines) < 2 or len(vertical_lines) < 2:
            print(f"  수평 {len(horizontal_lines)}개, 수직 {len(vertical_lines)}개만 찾음, 모서리 근처 추가 검색...")
            
            # 수평 라인 추가 검색
            if len(horizontal_lines) < 2:
                for corner in box_corners:
                    if len(horizontal_lines) >= 2:
                        break
                        
                    best_line = None
                    best_distance = float('inf')
                    
                    for entity in msp.query('LINE[layer=="DIMLINES"]'):
                        if entity.dxf.layer in ["PIPE", "FITTINGS", "WELDS"]:
                            continue
                            
                        if entity in self.used_dbox_lines or entity in horizontal_lines:
                            continue
                            
                        start = Vec3(entity.dxf.start)
                        end = Vec3(entity.dxf.end)
                        length = (end - start).magnitude
                        
                        # 길이 조건: 5mm 이상, max_length 이하
                        if length < 5 or length > max_length:
                            continue
                            
                        # 수평 라인인지 확인
                        if abs(start.y - end.y) < 0.001:
                            # 모서리와의 거리 확인
                            dist_start = self.get_distance(start, corner)
                            dist_end = self.get_distance(end, corner)
                            min_dist = min(dist_start, dist_end)
                            
                            if min_dist <= distance and min_dist < best_distance:
                                best_line = entity
                                best_distance = min_dist
                    
                    if best_line:
                        horizontal_lines.append(best_line)
                        print(f"    수평 라인 추가 (거리: {best_distance:.2f}mm)")
            
            # 수직 라인 추가 검색
            if len(vertical_lines) < 2:
                for corner in box_corners:
                    if len(vertical_lines) >= 2:
                        break
                        
                    best_line = None
                    best_distance = float('inf')
                    
                    for entity in msp.query('LINE[layer=="DIMLINES"]'):
                        if entity.dxf.layer in ["PIPE", "FITTINGS", "WELDS"]:
                            continue
                            
                        if entity in self.used_dbox_lines or entity in vertical_lines:
                            continue
                            
                        start = Vec3(entity.dxf.start)
                        end = Vec3(entity.dxf.end)
                        length = (end - start).magnitude
                        
                        # 길이 조건: 5mm 이상, max_length 이하
                        if length < 5 or length > max_length:
                            continue
                            
                        # 수직 라인인지 확인
                        if abs(start.x - end.x) < 0.001:
                            # 모서리와의 거리 확인
                            dist_start = self.get_distance(start, corner)
                            dist_end = self.get_distance(end, corner)
                            min_dist = min(dist_start, dist_end)
                            
                            if min_dist <= distance and min_dist < best_distance:
                                best_line = entity
                                best_distance = min_dist
                    
                    if best_line:
                        vertical_lines.append(best_line)
                        print(f"    수직 라인 추가 (거리: {best_distance:.2f}mm)")
        
        # 수평과 수직 라인 합치기
        lines = horizontal_lines[:2] + vertical_lines[:2]
        
        # 찾은 라인들을 used_dbox_lines에 추가
        for line in lines:
            self.used_dbox_lines.add(line)
        
        print(f"  최종 DBOX: 수평 {len(horizontal_lines[:2])}개, 수직 {len(vertical_lines[:2])}개 (총 {len(lines)}개)")
                    
        return lines
    
    def is_horizontal_or_vertical(self, start, end):
        """라인이 수평 또는 수직인지 확인"""
        return abs(start.y - end.y) < 0.001 or abs(start.x - end.x) < 0.001
    
    def check_ad2_from_ad1_points(self, msp, ad1_lines):
        """AD1 양끝점에서 AD2를 찾을 때 PIPE/WELDS/FITTINGS 레이어가 있는지 확인
        조건1: AD1 양끝점에서 AD2 양끝점까지 0.5mm 이내
        조건2: AD2 중심점이 AD1 양끝점에서 0.5mm 이내
        (현재는 사용되지 않음 - INSU TEXT 거리 기준으로 변경됨)"""
        # AD1의 양끝점만 수집 (중심점 제외)
        ad1_endpoints = []
        for ad1 in ad1_lines:
            start = Vec3(ad1.dxf.start)
            end = Vec3(ad1.dxf.end)
            ad1_endpoints.extend([start, end])
        
        # AD1 양끝점에서 0.5mm 이내에 있는 라인 찾기
        # 조건1: AD1 양끝점에서 라인의 양끝점까지 0.5mm 이내
        # 조건2: 라인 중심점이 AD1 양끝점에서 0.5mm 이내
        for entity in msp.query('LINE'):
            # AD1 라인 자체는 제외
            if entity in ad1_lines:
                continue
                
            # 이미 사용된 라인들 제외
            if (entity in self.used_dbox_lines or 
                entity in self.used_ad1_lines or 
                entity in self.used_ad2_lines or
                entity in self.used_ad3_lines or
                entity in self.used_del1_lines):
                continue
                
            start = Vec3(entity.dxf.start)
            end = Vec3(entity.dxf.end)
            
            # 최소 길이 확인 (2.2mm 이상)
            length = (end - start).magnitude
            if length < 2.2:
                continue
            
            # 라인의 중심점 계산
            center = Vec3((start.x + end.x) / 2, (start.y + end.y) / 2, 0)
            
            # AD1 양끝점에서 확인
            for endpoint in ad1_endpoints:
                # 조건1: AD1 양끝점에서 AD2 양끝점까지의 거리
                dist_to_start = self.get_distance(endpoint, start)
                dist_to_end = self.get_distance(endpoint, end)
                min_endpoint_dist = min(dist_to_start, dist_to_end)
                
                # 조건2: 라인 중심점에서 AD1 양끝점까지의 거리
                dist_center_to_endpoint = self.get_distance(center, endpoint)
                
                # 두 조건 중 하나라도 0.5mm 이내인 경우
                if min_endpoint_dist <= 0.5 or dist_center_to_endpoint <= 0.5:
                    # PIPE, WELDS, FITTINGS 레이어이면 True 반환 (문제가 있음)
                    if entity.dxf.layer in ["PIPE", "WELDS", "FITTINGS"]:
                        return True
                    
        return False  # 문제 없음
    
    def find_line_near_dbox_points(self, msp, dbox_lines, distance, insu_text=None):
        """DBOX 각 선분의 중심점에서 가장 가까운 라인 1개만 찾기 및 연속된 라인들 추가
        4개의 DBOX 라인 각각의 중심점을 계산하고, 그 중 어느 하나에서든 가장 가까운 라인 1개를 선택
        여러 후보가 있을 경우 DBOX 수직 선분의 중심점에서 가장 가까운 것 선택
        """
        # DBOX 각 선분의 중심점 계산
        dbox_midpoints = []
        vertical_midpoints = []  # 수직 선분의 중심점만 별도 저장
        
        for line in dbox_lines:
            start = Vec3(line.dxf.start)
            end = Vec3(line.dxf.end)
            # 선분의 중심점 계산
            midpoint = Vec3((start.x + end.x) / 2, (start.y + end.y) / 2, 0)
            dbox_midpoints.append(midpoint)
            
            # 수직 선분인지 확인 (X 좌표가 거의 같음)
            if abs(start.x - end.x) < 0.001:
                vertical_midpoints.append(midpoint)
        
        print(f"  DBOX 4개 라인의 각 중심점 {len(dbox_midpoints)}개 계산됨")
        
        # AD1 후보들을 먼저 수집
        ad1_candidates = []
        
        # DIMLINES와 ISOTEXT 레이어에서 검색 (PIPE, FITTINGS, WELDS 제외)
        for layer in ["DIMLINES", "ISOTEXT"]:
            for entity in msp.query(f'LINE[layer=="{layer}"]'):
                # PIPE, FITTINGS, WELDS 레이어는 명시적으로 제외 (안전장치)
                if entity.dxf.layer in ["PIPE", "FITTINGS", "WELDS"]:
                    continue
                    
                # DBOX 라인 자체는 제외
                if entity in dbox_lines:
                    continue
                
                # 이미 다른 용도로 사용된 라인 제외 (DBOX, AD1, AD2, AD3, DEL1)
                if (entity in self.used_dbox_lines or 
                    entity in self.used_ad1_lines or 
                    entity in self.used_ad2_lines or
                    entity in self.used_ad3_lines or
                    entity in self.used_del1_lines):
                    continue
                    
                start = Vec3(entity.dxf.start)
                end = Vec3(entity.dxf.end)
                
                # 최소 길이 확인 (2.2mm 이상)
                length = (end - start).magnitude
                if length < 2.2:
                    continue
                
                # 각 DBOX 중심점에 대해 거리 계산
                for dbox_midpoint in dbox_midpoints:
                    # 라인의 시작점 또는 끝점과 DBOX 중심점 사이의 거리
                    dist_start = self.get_distance(start, dbox_midpoint)
                    dist_end = self.get_distance(end, dbox_midpoint)
                    
                    if dist_start <= distance:
                        ad1_candidates.append({
                            'line': entity,
                            'distance': dist_start,
                            'dbox_midpoint': dbox_midpoint,
                            'closest_point': "start"
                        })
                    
                    if dist_end <= distance:
                        ad1_candidates.append({
                            'line': entity,
                            'distance': dist_end,
                            'dbox_midpoint': dbox_midpoint,
                            'closest_point': "end"
                        })
        
        # 거리순으로 정렬
        ad1_candidates.sort(key=lambda x: x['distance'])
        
        # 2개 이상의 후보가 있을 경우, DBOX 수직 선분 중심점에서 가장 가까운 것 선택
        if len(ad1_candidates) >= 2 and vertical_midpoints:
            print(f"  AD1 후보 {len(ad1_candidates)}개 발견, DBOX 수직 선분 중심점에서 가장 가까운 것 선택 중...")
            
            # 각 후보에 대해 수직 선분 중심점들과의 최소 거리 계산
            for candidate in ad1_candidates:
                line = candidate['line']
                start = Vec3(line.dxf.start)
                end = Vec3(line.dxf.end)
                
                min_dist_to_vertical = float('inf')
                
                # 모든 수직 선분 중심점에 대해 거리 계산
                for v_midpoint in vertical_midpoints:
                    # 라인의 시작점과 끝점에서 수직 선분 중심점까지의 거리
                    dist_start = self.get_distance(v_midpoint, start)
                    dist_end = self.get_distance(v_midpoint, end)
                    
                    # 더 가까운 거리 선택
                    min_dist = min(dist_start, dist_end)
                    
                    # 전체 최소 거리 업데이트
                    if min_dist < min_dist_to_vertical:
                        min_dist_to_vertical = min_dist
                        candidate['closest_vertical_midpoint'] = v_midpoint
                
                candidate['vertical_distance'] = min_dist_to_vertical
            
            # DBOX 수직 선분 중심점에서의 거리순으로 재정렬
            ad1_candidates.sort(key=lambda x: x['vertical_distance'])
            
            valid_candidate = ad1_candidates[0]
            print(f"    → AD1 선택: DBOX 수직 선분 중심점에서 {valid_candidate['vertical_distance']:.2f}mm (DBOX 중심점에서 {valid_candidate['distance']:.2f}mm)")
        else:
            # 후보가 1개이거나 수직 선분이 없으면 첫 번째 사용
            valid_candidate = ad1_candidates[0] if ad1_candidates else None
            if valid_candidate and vertical_midpoints:
                # 가장 가까운 수직 선분 중심점 찾기
                min_dist = float('inf')
                for v_midpoint in vertical_midpoints:
                    dist = self.get_distance(v_midpoint, Vec3(valid_candidate['line'].dxf.start))
                    if dist < min_dist:
                        min_dist = dist
                        valid_candidate['closest_vertical_midpoint'] = v_midpoint
        
        # 선택된 AD1 처리
        if valid_candidate:
            best_line = valid_candidate['line']
            best_distance = valid_candidate['distance']
            closest_dbox_midpoint = valid_candidate['dbox_midpoint']
            closest_point_on_line = valid_candidate['closest_point']
            
            print(f"  AD1 시작 라인 선택됨 (DBOX 중심점에서 {best_distance:.2f}mm)")
            
            ad1_lines = [best_line]
            self.used_ad1_lines.add(best_line)
            
            # AD1 선택 즉시 CYAN으로 변경
            best_line.dxf.color = 4  # CYAN
            best_line.dxf.layer = "AD1"
            
            # 선택된 하나의 시작 라인에서 연속된 라인들 찾기 (각도 허용 오차 1도)
            continuous_lines = self.find_continuous_lines(msp, best_line, 8.0, 1.0)
            for line in continuous_lines:
                if line not in ad1_lines:
                    ad1_lines.append(line)
                    self.used_ad1_lines.add(line)
                    # 연속된 라인들은 AD1-1 레이어로 설정
                    line.dxf.color = 4  # CYAN
                    line.dxf.layer = "AD1-1"  # AD1이 아닌 AD1-1로 설정
            
            if len(ad1_lines) > 1:
                print(f"  → 연속된 라인 {len(ad1_lines)-1}개 추가 발견 → AD1-1 레이어로 이동 (각도 허용: 1도)")
            print(f"  AD1 라인 총 {len(ad1_lines)}개 선택됨 (AD1: 1개, AD1-1: {len(ad1_lines)-1}개)")
            
            # 반환값 수정: closest_vertical_midpoint, closest_point_on_line, first_ad1 포함
            return ad1_lines, (valid_candidate.get('closest_vertical_midpoint', dbox_midpoints[0]), closest_point_on_line, best_line)
        
        return None, None
    
    def point_to_line_distance(self, point, line_start, line_end):
        """점과 선분 사이의 최소 거리"""
        line_vec = line_end - line_start
        point_vec = point - line_start
        line_len = line_vec.magnitude
        
        if line_len == 0:
            return point_vec.magnitude
            
        t = max(0, min(1, point_vec.dot(line_vec) / (line_len * line_len)))
        projection = line_start + line_vec * t
        return (point - projection).magnitude
    
    def find_ad3_near_point(self, msp, ad2e_point, max_distance, max_length):
        """AD2E 점 근처에서 중심점이 가까운 라인 찾기"""
        best_line = None
        best_distance = float('inf')
        
        for entity in msp.query('LINE'):
            # PIPE, FITTINGS, WELDS 레이어 제외
            if entity.dxf.layer in ["PIPE", "FITTINGS", "WELDS"]:
                continue
                
            # 이미 사용된 라인들 제외
            if (entity in self.used_dbox_lines or 
                entity in self.used_ad1_lines or 
                entity in self.used_ad2_lines or
                entity in self.used_ad3_lines or
                entity in self.used_del1_lines):
                continue
                
            start = Vec3(entity.dxf.start)
            end = Vec3(entity.dxf.end)
            length = (end - start).magnitude
            
            # 길이 제한 확인 (10mm 이하)
            if length > max_length:
                continue
                
            # 라인의 중심점 계산
            center = Vec3((start.x + end.x) / 2, (start.y + end.y) / 2, 0)
            
            # AD2E와 중심점 사이의 거리
            distance = self.get_distance(center, ad2e_point)
            
            if distance <= max_distance and distance < best_distance:
                best_line = entity
                best_distance = distance
        
        return best_line
    
    def get_line_angle(self, start, end):
        """라인의 각도를 계산 (0~360도)"""
        dx = end.x - start.x
        dy = end.y - start.y
        
        # 라디안을 도로 변환
        angle = math.atan2(dy, dx) * 180 / math.pi
        
        # 0~360도로 정규화
        if angle < 0:
            angle += 360
            
        return angle
    
    def find_continuous_lines(self, msp, base_line, max_distance=8.0, angle_tolerance=1.0):
        """기준 라인과 연속된 라인들을 찾기 (같은 기울기, 끝점에서 이어지는)"""
        continuous_lines = []
        
        # 기준 라인의 각도 계산
        base_start = Vec3(base_line.dxf.start)
        base_end = Vec3(base_line.dxf.end)
        base_angle = self.get_line_angle(base_start, base_end)
        
        # 재귀적으로 연속된 라인 찾기
        self._find_continuous_from_endpoints(msp, base_line, base_angle, max_distance, 
                                           angle_tolerance, continuous_lines, set([base_line]))
        
        return continuous_lines
    
    def _find_continuous_from_endpoints(self, msp, current_line, base_angle, max_distance, 
                                      angle_tolerance, continuous_lines, visited):
        """현재 라인의 양 끝점에서 연속된 라인 찾기"""
        current_start = Vec3(current_line.dxf.start)
        current_end = Vec3(current_line.dxf.end)
        
        # DIMLINES와 ISOTEXT 레이어에서 검색
        for layer in ["DIMLINES", "ISOTEXT"]:
            for entity in msp.query(f'LINE[layer=="{layer}"]'):
                # 이미 방문했거나 사용된 라인은 제외
                if (entity in visited or 
                    entity in self.used_dbox_lines or 
                    entity in self.used_ad1_lines or 
                    entity in self.used_ad2_lines or
                    entity in self.used_ad3_lines or
                    entity in self.used_del1_lines or
                    entity.dxf.layer in ["PIPE", "FITTINGS", "WELDS"]):
                    continue
                
                line_start = Vec3(entity.dxf.start)
                line_end = Vec3(entity.dxf.end)
                
                # 최소 길이 확인 (2.2mm 이상)
                length = (line_end - line_start).magnitude
                if length < 2.2:
                    continue
                
                # 현재 라인의 끝점과 다음 라인의 시작점/끝점 사이 거리 확인
                connections = [
                    (current_end, line_start),
                    (current_end, line_end),
                    (current_start, line_start),
                    (current_start, line_end)
                ]
                
                for point1, point2 in connections:
                    dist = self.get_distance(point1, point2)
                    if dist <= max_distance:
                        # 1. 다음 라인 자체의 각도 확인
                        line_angle = self.get_line_angle(line_start, line_end)
                        
                        # 각도 차이 계산 (0-180도 사이로 정규화)
                        angle_diff = abs(line_angle - base_angle)
                        if angle_diff > 180:
                            angle_diff = 360 - angle_diff
                        
                        # 반대 방향(180도 차이)도 같은 기울기로 간주
                        if angle_diff > 90:
                            angle_diff = 180 - angle_diff
                        
                        if angle_diff <= angle_tolerance:
                            # 2. 연결점 사이의 가상선 각도 확인 (일직선상에 있는지)
                            # 거리가 0보다 큰 경우에만 각도 계산
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
                            self._find_continuous_from_endpoints(msp, entity, base_angle, 
                                                               max_distance, angle_tolerance, 
                                                               continuous_lines, visited)
                            break
    
    def is_iso_angle(self, angle, tolerance=0.5):
        """ISO 표준 각도인지 확인 (30도 간격)"""
        # ISO 표준 각도: 0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330
        for iso_angle in range(0, 360, 30):
            # 각도 차이 계산 (360도 주기 고려)
            diff = abs(angle - iso_angle)
            if diff > 180:
                diff = 360 - diff
            
            if diff <= tolerance:
                return True
                
        return False
    
    def find_small_lines_near_points(self, msp, points, max_distances, length_limits, exclude_lines=None):
        """여러 점들 근처의 작은 라인들 찾기
        points: 검색할 점들의 리스트
        max_distances: 각 점에 대한 최대 거리 (점과 같은 수의 리스트 또는 단일 값)
        length_limits: 길이 제한 리스트
        exclude_lines: 추가로 제외할 라인들 (예: DEL1에서 이미 선택된 라인들)
        """
        lines = []
        
        # max_distances가 단일 값이면 리스트로 변환
        if not isinstance(max_distances, list):
            max_distances = [max_distances] * len(points)
        
        # exclude_lines가 없으면 빈 집합으로
        if exclude_lines is None:
            exclude_lines = set()
        
        for entity in msp.query('LINE'):
            # PIPE, FITTINGS, WELDS 레이어 제외
            if entity.dxf.layer in ["PIPE", "FITTINGS", "WELDS"]:
                continue
                
            # 이미 사용된 라인들 제외
            if (entity in self.used_dbox_lines or 
                entity in self.used_ad1_lines or 
                entity in self.used_ad2_lines or
                entity in self.used_ad3_lines or
                entity in self.used_del1_lines or
                entity in self.used_ex1_lines or
                entity in exclude_lines):  # 추가 제외 라인들
                continue
                
            start = Vec3(entity.dxf.start)
            end = Vec3(entity.dxf.end)
            length = (end - start).magnitude
            
            # 길이 제한 확인
            valid_length = False
            for limit in length_limits:
                if length <= limit:
                    valid_length = True
                    break
                    
            if not valid_length:
                continue
                
            # 각 점에서의 거리 확인
            for i, point in enumerate(points):
                max_dist = max_distances[i] if i < len(max_distances) else max_distances[-1]
                if (self.get_distance(start, point) <= max_dist or 
                    self.get_distance(end, point) <= max_dist):
                    lines.append(entity)
                    break  # 한 점에서만 조건을 만족해도 추가
                
        return lines
    
    def line_segments_intersect(self, p1, p2, p3, p4):
        """두 선분이 교차하는지 확인
        p1-p2: 첫 번째 선분
        p3-p4: 두 번째 선분
        """
        def ccw(A, B, C):
            return (C[1] - A[1]) * (B[0] - A[0]) > (B[1] - A[1]) * (C[0] - A[0])
        
        return ccw(p1, p3, p4) != ccw(p2, p3, p4) and ccw(p1, p2, p3) != ccw(p1, p2, p4)
    
    def find_del1_lines_restricted(self, msp, search_points, distances, ad1_lines, ad2, ad3):
        """DEL1 라인을 제한된 조건으로 찾기
        1단계: 1mm 이하 라인 중 AD1/AD2/AD3와 교차하는 라인
        2단계: 1~2.2mm 라인 중 1단계 라인의 끝점에 0.1mm 내로 접하는 라인
        """
        # AD1, AD2, AD3 라인들 수집
        reference_lines = []
        reference_lines.extend(ad1_lines)
        reference_lines.append(ad2)
        if ad3:
            reference_lines.append(ad3)
        
        # 1단계: 1mm 이하 라인 중 AD1/AD2/AD3와 교차하는 라인 찾기
        first_stage_lines = []
        
        for entity in msp.query('LINE'):
            # PIPE, FITTINGS, WELDS 레이어 제외
            if entity.dxf.layer in ["PIPE", "FITTINGS", "WELDS"]:
                continue
                
            # 이미 사용된 라인들 제외
            if (entity in self.used_dbox_lines or 
                entity in self.used_ad1_lines or 
                entity in self.used_ad2_lines or
                entity in self.used_ad3_lines or
                entity in self.used_del1_lines or
                entity in self.used_ex1_lines):
                continue
                
            start = Vec3(entity.dxf.start)
            end = Vec3(entity.dxf.end)
            length = (end - start).magnitude
            
            # 1mm 이하인지 확인
            if length > 1.0:
                continue
            
            # 기본 거리 조건 확인 (원래 검색 위치에서)
            valid_distance = False
            for i, point in enumerate(search_points):
                max_dist = distances[i] if i < len(distances) else distances[-1]
                if (self.get_distance(start, point) <= max_dist or 
                    self.get_distance(end, point) <= max_dist):
                    valid_distance = True
                    break
            
            if not valid_distance:
                continue
            
            # AD1/AD2/AD3와 교차하는지 확인
            intersects = False
            for ref_line in reference_lines:
                ref_start = Vec3(ref_line.dxf.start)
                ref_end = Vec3(ref_line.dxf.end)
                
                if self.line_segments_intersect(start, end, ref_start, ref_end):
                    intersects = True
                    break
            
            if intersects:
                first_stage_lines.append(entity)
        
        # 2단계: 1~2.2mm 라인 중 1단계 라인의 끝점에 0.1mm 내로 접하는 라인 찾기
        second_stage_lines = []
        
        # 1단계 라인들의 끝점 수집
        first_stage_endpoints = []
        for line in first_stage_lines:
            first_stage_endpoints.append(Vec3(line.dxf.start))
            first_stage_endpoints.append(Vec3(line.dxf.end))
        
        if first_stage_endpoints:  # 1단계에서 라인을 찾은 경우에만
            for entity in msp.query('LINE'):
                # PIPE, FITTINGS, WELDS 레이어 제외
                if entity.dxf.layer in ["PIPE", "FITTINGS", "WELDS"]:
                    continue
                    
                # 이미 사용된 라인들 제외 (1단계 라인 포함)
                if (entity in self.used_dbox_lines or 
                    entity in self.used_ad1_lines or 
                    entity in self.used_ad2_lines or
                    entity in self.used_ad3_lines or
                    entity in self.used_del1_lines or
                    entity in self.used_ex1_lines or
                    entity in first_stage_lines):
                    continue
                    
                start = Vec3(entity.dxf.start)
                end = Vec3(entity.dxf.end)
                length = (end - start).magnitude
                
                # 1초과 2.2mm 이하 범위인지 확인
                if length <= 1.0 or length > 2.2:
                    continue
                
                # 1단계 라인의 끝점에 0.1mm 내로 접하는지 확인
                close_to_endpoint = False
                for endpoint in first_stage_endpoints:
                    if (self.get_distance(start, endpoint) <= 0.1 or 
                        self.get_distance(end, endpoint) <= 0.1):
                        close_to_endpoint = True
                        break
                
                if close_to_endpoint:
                    second_stage_lines.append(entity)
        
        # 두 단계의 결과를 합침
        all_del1_lines = first_stage_lines + second_stage_lines
        
        return all_del1_lines
        """여러 점들 근처의 작은 라인들 찾기
        points: 검색할 점들의 리스트
        max_distances: 각 점에 대한 최대 거리 (점과 같은 수의 리스트 또는 단일 값)
        length_limits: 길이 제한 리스트
        exclude_lines: 추가로 제외할 라인들 (예: DEL1에서 이미 선택된 라인들)
        """
        lines = []
        
        # max_distances가 단일 값이면 리스트로 변환
        if not isinstance(max_distances, list):
            max_distances = [max_distances] * len(points)
        
        # exclude_lines가 없으면 빈 집합으로
        if exclude_lines is None:
            exclude_lines = set()
        
        for entity in msp.query('LINE'):
            # PIPE, FITTINGS, WELDS 레이어 제외
            if entity.dxf.layer in ["PIPE", "FITTINGS", "WELDS"]:
                continue
                
            # 이미 사용된 라인들 제외
            if (entity in self.used_dbox_lines or 
                entity in self.used_ad1_lines or 
                entity in self.used_ad2_lines or
                entity in self.used_ad3_lines or
                entity in self.used_del1_lines or
                entity in self.used_ex1_lines or
                entity in exclude_lines):  # 추가 제외 라인들
                continue
                
            start = Vec3(entity.dxf.start)
            end = Vec3(entity.dxf.end)
            length = (end - start).magnitude
            
            # 길이 제한 확인
            valid_length = False
            for limit in length_limits:
                if length <= limit:
                    valid_length = True
                    break
                    
            if not valid_length:
                continue
                
            # 각 점에서의 거리 확인
            for i, point in enumerate(points):
                max_dist = max_distances[i] if i < len(max_distances) else max_distances[-1]
                if (self.get_distance(start, point) <= max_dist or 
                    self.get_distance(end, point) <= max_dist):
                    lines.append(entity)
                    break  # 한 점에서만 조건을 만족해도 추가
                
        return lines
    
    def find_hatches_near_endpoints(self, msp, endpoints, max_area, max_distance):
        """끝점들 근처의 해치 찾기
        endpoints: AD1, AD2, AD3, DEL1의 모든 끝점들
        max_area: 최대 면적 (0.8)
        max_distance: 최대 거리 (5mm)
        """
        hatches = []
        
        for entity in msp.query('HATCH'):
            # 이미 사용된 해치 제외
            if entity in self.used_hatches:
                continue
                
            # 해치 면적 계산 (간단한 근사치)
            try:
                paths = entity.paths
                if paths and hasattr(paths[0], 'vertices'):
                    vertices = paths[0].vertices
                    area = self.calculate_polygon_area(vertices)
                    
                    if area > max_area:
                        continue
                        
                    # 끝점들과의 거리 확인
                    found = False
                    for endpoint in endpoints:
                        for vertex in vertices:
                            if self.get_distance(vertex, endpoint) <= max_distance:
                                hatches.append(entity)
                                found = True
                                break
                        if found:
                            break
            except:
                pass
                
        return hatches  # 모든 조건을 만족하는 해치 반환
    
    def find_hatches_near_points(self, msp, points, max_area):
        """점들 근처의 해치 찾기"""
        hatches = []
        
        for entity in msp.query('HATCH'):
            # 이미 사용된 해치 제외
            if entity in self.used_hatches:
                continue
                
            # 해치 면적 계산 (간단한 근사치)
            try:
                paths = entity.paths
                if paths and hasattr(paths[0], 'vertices'):
                    vertices = paths[0].vertices
                    area = self.calculate_polygon_area(vertices)
                    
                    if area > max_area:
                        continue
                        
                    # 점들과의 거리 확인
                    for point in points:
                        for vertex in vertices:
                            if self.get_distance(vertex, point) <= 5:  # 5mm 이내
                                hatches.append(entity)
                                break
                        if entity in hatches:
                            break
            except:
                pass
                
        return hatches[:2]  # 최대 2개
    
    def calculate_polygon_area(self, vertices):
        """다각형 면적 계산"""
        n = len(vertices)
        area = 0.0
        for i in range(n):
            j = (i + 1) % n
            area += vertices[i][0] * vertices[j][1]
            area -= vertices[j][0] * vertices[i][1]
        return abs(area) / 2.0
    
    def process_dbox_phase(self, msp, insu1, index):
        """첫 번째 단계: DBOX까지만 처리
        INSUL = INSU + HC (INSU 텍스트와 HC 텍스트의 조합)
        """
        try:
            # 이미 사용된 INSU인지 확인
            if insu1 in self.used_insu_texts:
                return False, f"INSU #{index+1}: 이미 사용된 INSU 텍스트입니다.", None
                
            # 2. HC 텍스트 찾기 (INSU1 아래에서 첫 번째 HC/MM 텍스트, 최대 10mm 거리)
            hc_texts = self.find_text_below(msp, insu1, ["HC", "MM", "mm"])
            if not hc_texts:
                # HC가 없으면 TBOX 생성하지 않고 스킵
                return False, f"INSU #{index+1}: HC 또는 MM 텍스트를 찾을 수 없습니다. (10mm 이내에 없음, TBOX 생성 안함)", None
            
            hc = hc_texts[0]
            
            # HC와 INSU 사이의 거리 출력
            insu_pos = insu1.dxf.insert if hasattr(insu1.dxf, 'insert') else insu1.get_pos()
            hc_pos = hc.dxf.insert if hasattr(hc.dxf, 'insert') else hc.get_pos()
            distance = self.get_distance(insu_pos, hc_pos)
            print(f"  INSU #{index+1}: HC/MM 텍스트 찾음 (거리: {distance:.2f}mm) - INSUL 형성, TBOX 생성 가능")
            
            # 사용된 INSU와 HC 추적
            self.used_insu_texts.add(insu1)
            self.used_hc_texts.add(hc)
            
            # 3. INSU1과 HC 색상을 CYAN으로 변경
            insu1.dxf.color = 4  # CYAN
            hc.dxf.color = 4
            
            # 4. TBOX 생성 (INSUL = INSU + HC 텍스트의 실제 크기 반영, 높이 0.8배 조정)
            # HC가 있을 때만 TBOX 생성
            tbox_corners = self.create_box_around_texts([insu1, hc])
            if not tbox_corners:
                return False, f"INSU #{index+1}: TBOX를 생성할 수 없습니다.", None
            
            print(f"  TBOX 생성됨 (INSUL 영역, 높이 0.8배): {[(f'{x:.2f}', f'{y:.2f}') for x, y in tbox_corners]}")
            
            # TBOX를 도면에 그리기 (폴리라인으로)
            tbox_polyline = msp.add_lwpolyline(tbox_corners, close=True)
            tbox_polyline.dxf.layer = "INSU_BOX"  # 전용 레이어
            tbox_polyline.dxf.color = 4  # CYAN 색상
            tbox_polyline.dxf.lineweight = 13  # 얇은 선 (0.13mm)
            
            # 5. DBOX 찾기 (TBOX 면적 내에 있는 DIMLINES 라인 4개: 수평 2개 + 수직 2개)
            dbox_lines = self.find_lines_near_box(msp, tbox_corners, 5, 25)
            if len(dbox_lines) < 4:
                # DBOX를 못 찾으면 사용된 텍스트에서 제거
                self.used_insu_texts.discard(insu1)
                self.used_hc_texts.discard(hc)
                return False, f"INSU #{index+1}: DBOX 라인을 충분히 찾을 수 없습니다. ({len(dbox_lines)}개 찾음, 최소 5mm 필요)", None
            
            # DBOX 색상을 CYAN으로 하고 레이어를 DBOX로 변경
            for line in dbox_lines:
                line.dxf.color = 4
                line.dxf.layer = "DBOX"
            
            # 데이터 저장용 딕셔너리
            data = {
                'insu1': insu1,
                'hc': hc,
                'tbox_corners': tbox_corners,
                'dbox_lines': dbox_lines
            }
            
            return True, f"INSU #{index+1}: DBOX까지 처리 완료", data
            
        except Exception as e:
            # 오류 발생 시 사용된 텍스트에서 제거
            if 'insu1' in locals():
                self.used_insu_texts.discard(insu1)
            if 'hc' in locals():
                self.used_hc_texts.discard(hc)
            return False, f"INSU #{index+1}: DBOX 단계 오류 - {str(e)}", None
    
    def process_ad1_phase(self, msp, data, index):
        """두 번째 단계: AD1부터 나머지 처리"""
        try:
            insu1 = data['insu1']
            hc = data['hc']
            dbox_lines = data['dbox_lines']
            
            # 6. AD1 찾기 (DBOX 선분 중심점들에서 7mm 내에서 가장 가까운 라인 및 연속된 라인들)
            ad1_result = self.find_line_near_dbox_points(msp, dbox_lines, 7.0)
            if not ad1_result or not ad1_result[0]:
                return False, f"INSU #{index+1}: AD1을 찾을 수 없습니다. (최소 길이 2.2mm, 최대 거리 7mm, 각도 허용 1도)"
            
            ad1_lines, ad1_info = ad1_result
            closest_vertical_midpoint, closest_point_on_line, first_ad1 = ad1_info
            
            # AD1 레이어로 변경 및 총 길이 계산 (색상은 이미 CYAN으로 변경됨)
            total_ad1_length = 0
            ad1_count = 0
            ad1_1_count = 0
            
            for ad1 in ad1_lines:
                # ad1.dxf.layer는 이미 설정됨 (AD1 또는 AD1-1)
                # ad1.dxf.color는 이미 CYAN(4)으로 설정됨
                if ad1.dxf.layer == "AD1":
                    ad1_count += 1
                elif ad1.dxf.layer == "AD1-1":
                    ad1_1_count += 1
                length = (Vec3(ad1.dxf.end) - Vec3(ad1.dxf.start)).magnitude
                total_ad1_length += length
            
            print(f"  AD1 선택됨 → AD1: {ad1_count}개, AD1-1: {ad1_1_count}개 (총 길이: {total_ad1_length:.2f}mm, 색상: CYAN)")
            
            # 7. AP1, AP2 결정 (수직선 중심점에 가까운 점이 AP1, 반대편이 AP2)
            first_ad1_start = Vec3(first_ad1.dxf.start)
            first_ad1_end = Vec3(first_ad1.dxf.end)
            
            # 첫 번째 AD1의 어느 점이 수직선 중심점에 가까운지에 따라 AP1 결정
            if closest_point_on_line == "start":
                ap1 = first_ad1_start
                ap2 = first_ad1_end
            else:
                ap1 = first_ad1_end
                ap2 = first_ad1_start
            
            # 연속된 AD1이 있는 경우 AP2 재계산 (가장 먼 끝점)
            if len(ad1_lines) > 1:
                all_ad1_points = []
                for ad1 in ad1_lines:
                    all_ad1_points.append(Vec3(ad1.dxf.start))
                    all_ad1_points.append(Vec3(ad1.dxf.end))
                
                # AP1에서 가장 먼 점을 AP2로
                max_dist = 0
                for point in all_ad1_points:
                    dist = self.get_distance(point, ap1)
                    if dist > max_dist:
                        max_dist = dist
                        ap2 = point
            
            print(f"  AP1: DBOX 수직선 중심점에 가까운 점, AP2: 반대편 점 (거리: {self.get_distance(ap1, ap2):.2f}mm)")
            
            # 8. AD2 찾기 (AD1 양끝점에서 0.2mm 이내에 접하는 가장 가까운 라인)
            # AD1의 양끝점만 수집 (중심점 제외)
            ad1_all_points = []
            for ad1 in ad1_lines:
                start = Vec3(ad1.dxf.start)
                end = Vec3(ad1.dxf.end)
                ad1_all_points.append({'point': start, 'type': 'start', 'line': ad1})
                ad1_all_points.append({'point': end, 'type': 'end', 'line': ad1})
            
            ad2 = None
            min_dist = float('inf')
            closest_ad1_point = None  # 어느 AD1 점에서 가장 가까운지
            
            # 모든 레이어에서 검색 (PIPE, FITTINGS, WELDS 제외)
            for entity in msp.query('LINE'):
                # PIPE, FITTINGS, WELDS 레이어는 명시적으로 제외
                if entity.dxf.layer in ["PIPE", "FITTINGS", "WELDS"]:
                    continue
                    
                if entity in ad1_lines:
                    continue
                
                # 이미 DBOX, AD1, AD2, AD3, DEL1로 사용된 라인 제외
                if (entity in self.used_dbox_lines or 
                    entity in self.used_ad1_lines or 
                    entity in self.used_ad2_lines or
                    entity in self.used_ad3_lines or
                    entity in self.used_del1_lines):
                    continue
                    
                start = Vec3(entity.dxf.start)
                end = Vec3(entity.dxf.end)
                
                # 최소 길이 확인 (2.2mm 이상)
                length = (end - start).magnitude
                if length < 2.2:
                    continue
                
                # AD1 점들에서 선분까지의 거리 계산
                for point_info in ad1_all_points:
                    dist = self.point_to_line_distance(point_info['point'], start, end)
                    
                    # AD1 점에서 0.2mm 이내인지 확인
                    if dist <= 0.2:
                        if dist < min_dist:
                            ad2 = entity
                            min_dist = dist
                            closest_ad1_point = point_info
            
            if not ad2:
                return False, f"INSU #{index+1}: AD2를 찾을 수 없습니다. (AD1 양끝점에서 0.2mm 이내에 접하는 라인 없음)"
            
            # AD2 레이어로 변경
            ad2.dxf.layer = "AD2"
            self.used_ad2_lines.add(ad2)  # AD2로 사용된 라인 추적
            # AD2 길이 계산
            ad2_length = (Vec3(ad2.dxf.end) - Vec3(ad2.dxf.start)).magnitude
            print(f"  AD2 선택됨 → AD2 레이어로 이동 (길이: {ad2_length:.2f}mm, AD1 {closest_ad1_point['type']}점에서 {min_dist:.2f}mm)")
            
            # 9. AP3, AP4 결정 (AD2에서 closest_ad1_point에 가까운 점이 AP3)
            ad2_start = Vec3(ad2.dxf.start)
            ad2_end = Vec3(ad2.dxf.end)
            
            # AD2가 어느 점이 AD1 점에 더 가까운지에 따라 결정
            reference_point = closest_ad1_point['point']
            
            if self.get_distance(reference_point, ad2_start) < self.get_distance(reference_point, ad2_end):
                ap3 = ad2_start
                ap4 = ad2_end
            else:
                ap3 = ad2_end
                ap4 = ad2_start
            
            # AD2E는 AP4 (reference point에서 먼 점)
            ad2e = ap4
            
            # 10. AD3 찾기 (AD2E 점 근처의 중심점이 0.2mm 이내인 10mm 이하 라인)
            ad3 = self.find_ad3_near_point(msp, ad2e, 0.2, 10)
            if ad3:
                ad3.dxf.color = 1  # RED
                ad3.dxf.layer = "AD3"  # AD3 레이어로 변경
                self.used_ad3_lines.add(ad3)
                ad3_length = (Vec3(ad3.dxf.end) - Vec3(ad3.dxf.start)).magnitude
                print(f"  AD3 선택됨 → AD3 레이어로 이동 (길이: {ad3_length:.2f}mm, AD2E와 중심점 거리: 0.2mm 이내)")
            else:
                print(f"  AD3를 찾을 수 없습니다.")
            
            # 11. DEL1 찾기 (제한된 조건으로)
            del1_search_points = [ap2]  # AP2
            del1_distances = [2.2]  # AP2에서 2.2mm 이내
            
            # AD2 양끝점 추가
            del1_search_points.extend([Vec3(ad2.dxf.start), Vec3(ad2.dxf.end)])
            del1_distances.extend([2.2, 2.2])  # AD2 양끝점에서 2.2mm 이내
            
            # AD3 양끝점 추가 (AD3가 있는 경우)
            if ad3:
                del1_search_points.extend([Vec3(ad3.dxf.start), Vec3(ad3.dxf.end)])
                del1_distances.extend([2.2, 2.2])  # AD3 양끝점에서 2.2mm 이내
            
            # 제한된 조건으로 DEL1 찾기
            del1_lines = self.find_del1_lines_restricted(msp, del1_search_points, del1_distances, ad1_lines, ad2, ad3)
            if del1_lines:
                # 1mm 이하와 1~2.2mm 개수 구분
                under_1mm_count = sum(1 for line in del1_lines if (Vec3(line.dxf.end) - Vec3(line.dxf.start)).magnitude <= 1.0)
                over_1mm_count = len(del1_lines) - under_1mm_count
                print(f"  DEL1 {len(del1_lines)}개 선택됨 → DEL1 레이어로 이동")
                print(f"    - 1mm 이하 (AD1/AD2/AD3와 교차): {under_1mm_count}개")
                print(f"    - 1mm 초과 2.2mm 이하 (1mm 라인 끝점에 0.1mm 내): {over_1mm_count}개")
            
            # 12. 모든 라인의 끝점 수집 (AD1, AD2, AD3, DEL1)
            all_endpoints = []
            
            # AD1 라인들의 끝점
            for ad1 in ad1_lines:
                all_endpoints.append(Vec3(ad1.dxf.start))
                all_endpoints.append(Vec3(ad1.dxf.end))
            
            # AD2의 끝점
            all_endpoints.append(Vec3(ad2.dxf.start))
            all_endpoints.append(Vec3(ad2.dxf.end))
            
            # AD3의 끝점
            if ad3:
                all_endpoints.append(Vec3(ad3.dxf.start))
                all_endpoints.append(Vec3(ad3.dxf.end))
            
            # DEL1의 끝점들
            for line in del1_lines:
                all_endpoints.append(Vec3(line.dxf.start))
                all_endpoints.append(Vec3(line.dxf.end))
            
            # 해치 찾기 (면적 0.8 이하, 끝점에서 5mm 이내)
            hatches = self.find_hatches_near_endpoints(msp, all_endpoints, 0.8, 5.0)
            if hatches:
                for hatch in hatches:
                    hatch.dxf.color = 1  # RED
                    hatch.dxf.layer = "H1"  # H1 레이어로 변경
                    self.used_hatches.add(hatch)  # 사용된 해치 추적
                print(f"  HATCH {len(hatches)}개 선택됨 → H1 레이어로 이동 (AD1/AD2/AD3/DEL1 끝점 5mm 이내, 면적 0.8 이하)")
            
            # 13. 색상 변경
            # DEL1을 RED로 변경하고 레이어도 변경
            for line in del1_lines:
                line.dxf.color = 1  # RED
                line.dxf.layer = "DEL1"
                self.used_del1_lines.add(line)  # 사용된 DEL1 추적
                
            # AD1은 CYAN 유지 (이미 설정됨), AD2는 MAGENTA, DBOX도 RED로
            # AD1 색상은 그대로 유지 (CYAN)
            ad2.dxf.color = 6  # MAGENTA
            for line in dbox_lines:
                line.dxf.color = 1  # RED
            
            # 14. EX1 레이어에 라인 할당 (YELLOW 색상, 최대 2개)
            # DIMLINES와 ISOTEXT 레이어에서 검색 (PIPE, FITTINGS, WELDS 제외)
            ex1_count = 0
            for layer in ["DIMLINES", "ISOTEXT"]:
                if ex1_count >= 2:  # 최대 2개 제한
                    break
                    
                for entity in msp.query(f'LINE[layer=="{layer}"]'):
                    if ex1_count >= 2:  # 최대 2개 제한
                        break
                        
                    # PIPE, FITTINGS, WELDS 레이어는 명시적으로 제외 (안전장치)
                    if entity.dxf.layer in ["PIPE", "FITTINGS", "WELDS"]:
                        continue
                        
                    # 이미 다른 레이어로 할당된 라인은 제외 (AD1, AD2, AD3, DBOX, DEL1, EX1 제외)
                    if (entity in self.used_dbox_lines or 
                        entity in self.used_ad1_lines or 
                        entity in self.used_ad2_lines or
                        entity in self.used_ad3_lines or
                        entity in self.used_del1_lines or
                        entity in self.used_ex1_lines):
                        continue
                        
                    start = Vec3(entity.dxf.start)
                    end = Vec3(entity.dxf.end)
                    
                    # ISO 표준 각도 확인 (30도 간격)
                    angle = self.get_line_angle(start, end)
                    if not self.is_iso_angle(angle):
                        continue
                    
                    # AP3 또는 AP4에서 0~2mm 거리 확인
                    for point in [ap3, ap4]:
                        dist_start = self.get_distance(point, start)
                        dist_end = self.get_distance(point, end)
                        
                        # AD2 끝점에서 0~2mm 거리
                        if (0 <= dist_start <= 2.0) or (0 <= dist_end <= 2.0):
                            entity.dxf.layer = "EX1"
                            entity.dxf.color = 2  # YELLOW
                            self.used_ex1_lines.add(entity)  # 사용된 EX1 추적
                            ex1_count += 1
                            break
            
            if ex1_count > 0:
                print(f"  EX1 {ex1_count}개 선택됨 (최대 2개, ISO 표준 각도: 30° 간격, AD2 끝점 0~2mm)")
            else:
                print(f"  EX1을 찾을 수 없습니다. (ISO 표준 각도 제한)")
            
            return True, f"INSU #{index+1}: 성공적으로 처리됨"
            
        except Exception as e:
            return False, f"INSU #{index+1}: AD1 단계 오류 - {str(e)}"
    
    def process_single_file(self, filepath):
        """단일 DXF 파일 처리 - 모든 INSU 처리"""
        try:
            print(f"\n처리 중: {os.path.basename(filepath)}")
            print("-" * 60)
            
            # 각 파일마다 사용된 라인들과 텍스트들 초기화
            self.used_dbox_lines.clear()
            self.used_ad1_lines.clear()
            self.used_ad2_lines.clear()
            self.used_ad3_lines.clear()
            self.used_del1_lines.clear()
            self.used_ex1_lines.clear()
            self.used_hatches.clear()
            self.used_insu_texts.clear()
            self.used_hc_texts.clear()
            
            doc = ezdxf.readfile(filepath)
            msp = doc.modelspace()
            
            # EX1 레이어 생성
            if "EX1" not in doc.layers:
                doc.layers.new("EX1")
            
            # INSU_BOX 레이어 생성 (BOX 출력용)
            if "INSU_BOX" not in doc.layers:
                doc.layers.new("INSU_BOX")
                
            # DBOX 레이어 생성
            if "DBOX" not in doc.layers:
                doc.layers.new("DBOX")
                
            # AD1 레이어 생성
            if "AD1" not in doc.layers:
                doc.layers.new("AD1")
                
            # AD1-1 레이어 생성 (연속된 AD1용)
            if "AD1-1" not in doc.layers:
                doc.layers.new("AD1-1")
                
            # AD2 레이어 생성
            if "AD2" not in doc.layers:
                doc.layers.new("AD2")
                
            # AD3 레이어 생성
            if "AD3" not in doc.layers:
                doc.layers.new("AD3")
                
            # DEL1 레이어 생성
            if "DEL1" not in doc.layers:
                doc.layers.new("DEL1")
                
            # H1 레이어 생성 (HATCH용)
            if "H1" not in doc.layers:
                doc.layers.new("H1")
                
            print("레이어 생성 완료: INSU_BOX, DBOX, AD1, AD1-1, AD2, AD3, DEL1, H1, EX1")
            
            # 1. 모든 INSU 텍스트 찾기
            all_insu_texts = self.find_all_text_with_keyword(msp, "INSU")
            
            success_count = 0
            
            if not all_insu_texts:
                print("INSU 텍스트를 찾을 수 없습니다.")
            else:
                print(f"찾은 INSU 개수: {len(all_insu_texts)}")
                
                # 첫 번째 단계: 모든 INSU에 대해 DBOX까지 처리
                print("\n===== 1단계: 모든 DBOX 찾기 =====")
                insu_data_list = []
                no_hc_count = 0
                
                for index, insu1 in enumerate(all_insu_texts):
                    success, message, data = self.process_dbox_phase(msp, insu1, index)
                    print(message)
                    if success and data:
                        insu_data_list.append((index, data))
                    elif "HC 또는 MM 텍스트를 찾을 수 없습니다" in message:
                        no_hc_count += 1
                
                print(f"\n1단계 완료: {len(all_insu_texts)}개의 INSU 중")
                print(f"  - INSUL 형성 (HC/MM과 함께): {len(insu_data_list)}개 (10mm 이내, TBOX 생성됨)")
                print(f"  - HC/MM이 없는 INSU: {no_hc_count}개 (INSUL 미형성, 처리 스킵)")
                print(f"  - 기타 오류: {len(all_insu_texts) - len(insu_data_list) - no_hc_count}개")
                
                # 두 번째 단계: 모든 INSU에 대해 AD1부터 나머지 처리
                print("\n===== 2단계: 모든 AD1 및 나머지 처리 =====")
                
                for index, data in insu_data_list:
                    success, message = self.process_ad1_phase(msp, data, index)
                    print(message)
                    if success:
                        success_count += 1
            
            # 파일 저장 (무조건 저장)
            base_name = os.path.splitext(os.path.basename(filepath))[0]
            dir_name = os.path.dirname(filepath)
            new_filename = os.path.join(dir_name, f"{base_name}_INSUDEL.DXF")
            
            doc.saveas(new_filename)
            
            if all_insu_texts:
                print(f"\n총 {len(all_insu_texts)}개의 INSU 중 {success_count}개 처리 성공")
            else:
                print(f"\nINSU가 없지만 파일은 저장됨")
            print(f"저장: {new_filename}")
            
            return True, f"파일 저장 완료: {new_filename}"
            
        except Exception as e:
            # 오류가 발생해도 가능하면 저장 시도
            try:
                base_name = os.path.splitext(os.path.basename(filepath))[0]
                dir_name = os.path.dirname(filepath)
                new_filename = os.path.join(dir_name, f"{base_name}_INSUDEL.DXF")
                
                if 'doc' in locals():
                    doc.saveas(new_filename)
                    return True, f"오류 발생했지만 파일 저장됨: {str(e)}"
                else:
                    return False, f"파일 읽기 실패: {str(e)}"
            except:
                return False, f"파일 처리 및 저장 실패: {str(e)}"
    
    def run(self):
        """메인 실행 함수"""
        # Windows 파일 선택 대화상자를 위한 임시 root
        root = tk.Tk()
        root.withdraw()  # 메인 창 숨기기
        
        # 파일 선택 대화상자
        files = filedialog.askopenfilenames(
            title="DXF 파일 선택",
            filetypes=[("DXF files", "*.dxf"), ("All files", "*.*")]
        )
        
        if not files:
            print("선택된 파일이 없습니다.")
            return
        
        print(f"\n{len(files)}개의 파일이 선택되었습니다.")
        print("=" * 60)
        
        success_count = 0
        
        # 각 파일 처리
        for filepath in files:
            success, message = self.process_single_file(filepath)
            if success:
                success_count += 1
        
        # 최종 결과
        print("\n" + "=" * 60)
        print(f"최종 결과: {success_count}/{len(files)} 파일 처리 성공")
        print("=" * 60)

if __name__ == "__main__":
    # 필요한 라이브러리 확인
    try:
        import ezdxf
    except ImportError:
        print("오류: ezdxf 라이브러리가 필요합니다.")
        print("설치 명령: pip install ezdxf")
        exit(1)
    
    processor = DXFProcessor()
    processor.run()