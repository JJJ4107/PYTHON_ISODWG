import ezdxf
from ezdxf.math import Vec3
import os
import math
import re
import sys

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
        return math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)
    
    def get_entity_bounds(self, entity):
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
        texts = []
        for entity in msp.query('TEXT'):
            if keyword.upper() in entity.dxf.text.upper():
                texts.append(entity)
        for entity in msp.query('MTEXT'):
            if keyword.upper() in entity.text.upper():
                texts.append(entity)
        return texts
    
    def find_text_below(self, msp, base_text, keywords, x_tolerance=50, max_distance=10):
        base_pos = base_text.dxf.insert if hasattr(base_text.dxf, 'insert') else base_text.get_pos()
        candidates = []
        for entity in msp.query('TEXT'):
            if entity in self.used_hc_texts:
                continue
            pos = entity.dxf.insert
            if pos[1] < base_pos[1] and abs(pos[0] - base_pos[0]) <= x_tolerance:
                text = entity.dxf.text.upper().strip()
                if "INSU" in text:
                    continue
                for keyword in keywords:
                    if keyword.upper() == text or keyword.upper() in text:
                        distance = self.get_distance(pos, base_pos)
                        if distance <= max_distance:
                            candidates.append((entity, distance))
                            break
        for entity in msp.query('MTEXT'):
            if entity in self.used_hc_texts:
                continue
            pos = entity.dxf.insert
            if pos[1] < base_pos[1] and abs(pos[0] - base_pos[0]) <= x_tolerance:
                text = entity.text.upper().strip()
                if "INSU" in text:
                    continue
                for keyword in keywords:
                    if keyword.upper() == text or keyword.upper() in text:
                        distance = self.get_distance(pos, base_pos)
                        if distance <= max_distance:
                            candidates.append((entity, distance))
                            break
        if candidates:
            candidates.sort(key=lambda x: x[1])
            return [candidates[0][0]]
        return []
    
    def get_text_bounds(self, text_entity):
        if hasattr(text_entity, 'dxf'):
            pos = text_entity.dxf.insert
            if hasattr(text_entity.dxf, 'height'):
                height = text_entity.dxf.height
                text_str = text_entity.dxf.text
                width = len(text_str) * height * 0.9
                halign = getattr(text_entity.dxf, 'halign', 0)
                valign = getattr(text_entity.dxf, 'valign', 0)
                if halign == 0:
                    min_x = pos[0]; max_x = pos[0] + width
                elif halign == 1:
                    min_x = pos[0] - width / 2; max_x = pos[0] + width / 2
                elif halign == 2:
                    min_x = pos[0] - width; max_x = pos[0]
                else:
                    min_x = pos[0]; max_x = pos[0] + width
                if valign == 0:
                    min_y = pos[1]; max_y = pos[1] + height
                elif valign == 1:
                    min_y = pos[1]; max_y = pos[1] + height
                elif valign == 2:
                    min_y = pos[1] - height / 2; max_y = pos[1] + height / 2
                elif valign == 3:
                    min_y = pos[1] - height; max_y = pos[1]
                else:
                    min_y = pos[1]; max_y = pos[1] + height
                return (min_x, min_y, max_x, max_y)
            elif hasattr(text_entity, 'text'):
                height = getattr(text_entity.dxf, 'char_height', 2.5)
                text_str = text_entity.text
                width = getattr(text_entity.dxf, 'width', len(text_str) * height * 0.9)
                return (pos[0], pos[1] - height, pos[0] + width, pos[1])
        return (pos[0], pos[1], pos[0], pos[1])
    
    def create_box_around_texts(self, texts):
        if not texts:
            return None
        min_x = float('inf'); min_y = float('inf')
        max_x = float('-inf'); max_y = float('-inf')
        for text in texts:
            bounds = self.get_text_bounds(text)
            min_x = min(min_x, bounds[0])
            min_y = min(min_y, bounds[1])
            max_x = max(max_x, bounds[2])
            max_y = max(max_y, bounds[3])
        height = max_y - min_y
        center_y = (max_y + min_y) / 2
        new_height = height * 0.8
        min_y = center_y - new_height / 2
        max_y = center_y + new_height / 2
        margin = 2
        min_x -= margin; min_y -= margin; max_x += margin; max_y += margin
        return [(min_x, min_y), (max_x, min_y), (max_x, max_y), (min_x, max_y)]
    
    def point_in_box(self, point, box_corners):
        x, y = point[0], point[1]
        min_x = min(corner[0] for corner in box_corners)
        max_x = max(corner[0] for corner in box_corners)
        min_y = min(corner[1] for corner in box_corners)
        max_y = max(corner[1] for corner in box_corners)
        return min_x <= x <= max_x and min_y <= y <= max_y
    
    def line_in_box(self, start, end, box_corners):
        return self.point_in_box(start, box_corners) and self.point_in_box(end, box_corners)
    
    def find_lines_near_box(self, msp, box_corners, distance, max_length):
        horizontal_lines = []
        vertical_lines = []
        horizontal_candidates = []
        vertical_candidates = []
        for entity in msp.query('LINE[layer=="DIMLINES"]'):
            if entity.dxf.layer in ["PIPE", "FITTINGS", "WELDS"]:
                continue
            if entity in self.used_dbox_lines:
                continue
            start = Vec3(entity.dxf.start)
            end = Vec3(entity.dxf.end)
            length = (end - start).magnitude
            if length < 5 or length > max_length:
                continue
            if abs(start.y - end.y) < 0.001:
                if self.line_in_box(start, end, box_corners):
                    horizontal_candidates.append((entity, 0))
                elif self.point_in_box(start, box_corners) or self.point_in_box(end, box_corners):
                    horizontal_candidates.append((entity, 1))
            elif abs(start.x - end.x) < 0.001:
                if self.line_in_box(start, end, box_corners):
                    vertical_candidates.append((entity, 0))
                elif self.point_in_box(start, box_corners) or self.point_in_box(end, box_corners):
                    vertical_candidates.append((entity, 1))
        horizontal_candidates.sort(key=lambda x: x[1])
        vertical_candidates.sort(key=lambda x: x[1])
        horizontal_lines = [item[0] for item in horizontal_candidates[:2]]
        vertical_lines = [item[0] for item in vertical_candidates[:2]]
        if len(horizontal_lines) < 2 or len(vertical_lines) < 2:
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
                        if length < 5 or length > max_length:
                            continue
                        if abs(start.y - end.y) < 0.001:
                            dist_start = self.get_distance(start, corner)
                            dist_end = self.get_distance(end, corner)
                            min_dist = min(dist_start, dist_end)
                            if min_dist <= distance and min_dist < best_distance:
                                best_line = entity
                                best_distance = min_dist
                    if best_line:
                        horizontal_lines.append(best_line)
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
                        if length < 5 or length > max_length:
                            continue
                        if abs(start.x - end.x) < 0.001:
                            dist_start = self.get_distance(start, corner)
                            dist_end = self.get_distance(end, corner)
                            min_dist = min(dist_start, dist_end)
                            if min_dist <= distance and min_dist < best_distance:
                                best_line = entity
                                best_distance = min_dist
                    if best_line:
                        vertical_lines.append(best_line)
        lines = horizontal_lines[:2] + vertical_lines[:2]
        for line in lines:
            self.used_dbox_lines.add(line)
        return lines
    
    def is_horizontal_or_vertical(self, start, end):
        return abs(start.y - end.y) < 0.001 or abs(start.x - end.x) < 0.001
    
    def check_ad2_from_ad1_points(self, msp, ad1_lines):
        ad1_endpoints = []
        for ad1 in ad1_lines:
            start = Vec3(ad1.dxf.start)
            end = Vec3(ad1.dxf.end)
            ad1_endpoints.extend([start, end])
        for entity in msp.query('LINE'):
            if entity in ad1_lines:
                continue
            if (entity in self.used_dbox_lines or 
                entity in self.used_ad1_lines or 
                entity in self.used_ad2_lines or
                entity in self.used_ad3_lines or
                entity in self.used_del1_lines):
                continue
            start = Vec3(entity.dxf.start)
            end = Vec3(entity.dxf.end)
            length = (end - start).magnitude
            if length < 2.2:
                continue
            center = Vec3((start.x + end.x) / 2, (start.y + end.y) / 2, 0)
            for endpoint in ad1_endpoints:
                dist_to_start = self.get_distance(endpoint, start)
                dist_to_end = self.get_distance(endpoint, end)
                min_endpoint_dist = min(dist_to_start, dist_to_end)
                dist_center_to_endpoint = self.get_distance(center, endpoint)
                if min_endpoint_dist <= 0.5 or dist_center_to_endpoint <= 0.5:
                    if entity.dxf.layer in ["PIPE", "WELDS", "FITTINGS"]:
                        return True
        return False
    
    def find_line_near_dbox_points(self, msp, dbox_lines, distance, insu_text=None):
        dbox_midpoints = []
        vertical_midpoints = []
        for line in dbox_lines:
            start = Vec3(line.dxf.start)
            end = Vec3(line.dxf.end)
            midpoint = Vec3((start.x + end.x) / 2, (start.y + end.y) / 2, 0)
            dbox_midpoints.append(midpoint)
            if abs(start.x - end.x) < 0.001:
                vertical_midpoints.append(midpoint)
        ad1_candidates = []
        for layer in ["DIMLINES", "ISOTEXT"]:
            for entity in msp.query(f'LINE[layer=="{layer}"]'):
                if entity.dxf.layer in ["PIPE", "FITTINGS", "WELDS"]:
                    continue
                if entity in dbox_lines:
                    continue
                if (entity in self.used_dbox_lines or 
                    entity in self.used_ad1_lines or 
                    entity in self.used_ad2_lines or
                    entity in self.used_ad3_lines or
                    entity in self.used_del1_lines):
                    continue
                start = Vec3(entity.dxf.start)
                end = Vec3(entity.dxf.end)
                length = (end - start).magnitude
                if length < 2.2:
                    continue
                for dbox_midpoint in dbox_midpoints:
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
        ad1_candidates.sort(key=lambda x: x['distance'])
        if len(ad1_candidates) >= 2 and vertical_midpoints:
            for candidate in ad1_candidates:
                line = candidate['line']
                start = Vec3(line.dxf.start)
                end = Vec3(line.dxf.end)
                min_dist_to_vertical = float('inf')
                for v_midpoint in vertical_midpoints:
                    dist_start = self.get_distance(v_midpoint, start)
                    dist_end = self.get_distance(v_midpoint, end)
                    min_dist = min(dist_start, dist_end)
                    if min_dist < min_dist_to_vertical:
                        min_dist_to_vertical = min_dist
                        candidate['closest_vertical_midpoint'] = v_midpoint
                candidate['vertical_distance'] = min_dist_to_vertical
            ad1_candidates.sort(key=lambda x: x['vertical_distance'])
            valid_candidate = ad1_candidates[0]
        else:
            valid_candidate = ad1_candidates[0] if ad1_candidates else None
            if valid_candidate and vertical_midpoints:
                min_dist = float('inf')
                for v_midpoint in vertical_midpoints:
                    dist = self.get_distance(v_midpoint, Vec3(valid_candidate['line'].dxf.start))
                    if dist < min_dist:
                        min_dist = dist
                        valid_candidate['closest_vertical_midpoint'] = v_midpoint
        if valid_candidate:
            best_line = valid_candidate['line']
            best_distance = valid_candidate['distance']
            closest_dbox_midpoint = valid_candidate['dbox_midpoint']
            closest_point_on_line = valid_candidate['closest_point']
            ad1_lines = [best_line]
            self.used_ad1_lines.add(best_line)
            best_line.dxf.color = 4
            best_line.dxf.layer = "AD1"
            continuous_lines = self.find_continuous_lines(msp, best_line, 8.0, 1.0)
            for line in continuous_lines:
                if line not in ad1_lines:
                    ad1_lines.append(line)
                    self.used_ad1_lines.add(line)
                    line.dxf.color = 4
                    line.dxf.layer = "AD1-1"
            return ad1_lines, (valid_candidate.get('closest_vertical_midpoint', dbox_midpoints[0]), closest_point_on_line, best_line)
        return None, None
    
    def point_to_line_distance(self, point, line_start, line_end):
        line_vec = line_end - line_start
        point_vec = point - line_start
        line_len = line_vec.magnitude
        if line_len == 0:
            return point_vec.magnitude
        t = max(0, min(1, point_vec.dot(line_vec) / (line_len * line_len)))
        projection = line_start + line_vec * t
        return (point - projection).magnitude
    
    def find_ad3_near_point(self, msp, ad2e_point, max_distance, max_length):
        best_line = None
        best_distance = float('inf')
        for entity in msp.query('LINE'):
            if entity.dxf.layer in ["PIPE", "FITTINGS", "WELDS"]:
                continue
            if (entity in self.used_dbox_lines or 
                entity in self.used_ad1_lines or 
                entity in self.used_ad2_lines or
                entity in self.used_ad3_lines or
                entity in self.used_del1_lines):
                continue
            start = Vec3(entity.dxf.start)
            end = Vec3(entity.dxf.end)
            length = (end - start).magnitude
            if length > max_length:
                continue
            center = Vec3((start.x + end.x) / 2, (start.y + end.y) / 2, 0)
            distance = self.get_distance(center, ad2e_point)
            if distance <= max_distance and distance < best_distance:
                best_line = entity
                best_distance = distance
        return best_line
    
    def get_line_angle(self, start, end):
        dx = end.x - start.x
        dy = end.y - start.y
        angle = math.atan2(dy, dx) * 180 / math.pi
        if angle < 0:
            angle += 360
        return angle
    
    def find_continuous_lines(self, msp, base_line, max_distance=8.0, angle_tolerance=1.0):
        continuous_lines = []
        base_start = Vec3(base_line.dxf.start)
        base_end = Vec3(base_line.dxf.end)
        base_angle = self.get_line_angle(base_start, base_end)
        self._find_continuous_from_endpoints(msp, base_line, base_angle, max_distance, 
                                           angle_tolerance, continuous_lines, set([base_line]))
        return continuous_lines
    
    def _find_continuous_from_endpoints(self, msp, current_line, base_angle, max_distance, 
                                      angle_tolerance, continuous_lines, visited):
        current_start = Vec3(current_line.dxf.start)
        current_end = Vec3(current_line.dxf.end)
        for layer in ["DIMLINES", "ISOTEXT"]:
            for entity in msp.query(f'LINE[layer=="{layer}"]'):
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
                length = (line_end - line_start).magnitude
                if length < 2.2:
                    continue
                connections = [
                    (current_end, line_start),
                    (current_end, line_end),
                    (current_start, line_start),
                    (current_start, line_end)
                ]
                for point1, point2 in connections:
                    dist = self.get_distance(point1, point2)
                    if dist <= max_distance:
                        line_angle = self.get_line_angle(line_start, line_end)
                        angle_diff = abs(line_angle - base_angle)
                        if angle_diff > 180:
                            angle_diff = 360 - angle_diff
                        if angle_diff > 90:
                            angle_diff = 180 - angle_diff
                        if angle_diff <= angle_tolerance:
                            if dist > 0.001:
                                connection_angle = self.get_line_angle(point1, point2)
                                connection_angle_diff = abs(connection_angle - base_angle)
                                if connection_angle_diff > 180:
                                    connection_angle_diff = 360 - connection_angle_diff
                                if connection_angle_diff > 90:
                                    connection_angle_diff = 180 - connection_angle_diff
                                if connection_angle_diff > angle_tolerance:
                                    continue
                            continuous_lines.append(entity)
                            visited.add(entity)
                            self._find_continuous_from_endpoints(msp, entity, base_angle, 
                                                               max_distance, angle_tolerance, 
                                                               continuous_lines, visited)
                            break
    
    def is_iso_angle(self, angle, tolerance=0.5):
        for iso_angle in range(0, 360, 30):
            diff = abs(angle - iso_angle)
            if diff > 180:
                diff = 360 - diff
            if diff <= tolerance:
                return True
        return False
    
    def find_small_lines_near_points(self, msp, points, max_distances, length_limits, exclude_lines=None):
        lines = []
        if not isinstance(max_distances, list):
            max_distances = [max_distances] * len(points)
        if exclude_lines is None:
            exclude_lines = set()
        for entity in msp.query('LINE'):
            if entity.dxf.layer in ["PIPE", "FITTINGS", "WELDS"]:
                continue
            if (entity in self.used_dbox_lines or 
                entity in self.used_ad1_lines or 
                entity in self.used_ad2_lines or
                entity in self.used_ad3_lines or
                entity in self.used_del1_lines or
                entity in self.used_ex1_lines or
                entity in exclude_lines):
                continue
            start = Vec3(entity.dxf.start)
            end = Vec3(entity.dxf.end)
            length = (end - start).magnitude
            valid_length = False
            for limit in length_limits:
                if length <= limit:
                    valid_length = True
                    break
            if not valid_length:
                continue
            for i, point in enumerate(points):
                max_dist = max_distances[i] if i < len(max_distances) else max_distances[-1]
                if (self.get_distance(start, point) <= max_dist or 
                    self.get_distance(end, point) <= max_dist):
                    lines.append(entity)
                    break
        return lines
    
    def line_segments_intersect(self, p1, p2, p3, p4):
        def ccw(A, B, C):
            return (C[1] - A[1]) * (B[0] - A[0]) > (B[1] - A[1]) * (C[0] - A[0])
        return ccw(p1, p3, p4) != ccw(p2, p3, p4) and ccw(p1, p2, p3) != ccw(p1, p2, p4)
    
    def find_del1_lines_restricted(self, msp, search_points, distances, ad1_lines, ad2, ad3):
        reference_lines = []
        reference_lines.extend(ad1_lines)
        reference_lines.append(ad2)
        if ad3:
            reference_lines.append(ad3)
        first_stage_lines = []
        for entity in msp.query('LINE'):
            if entity.dxf.layer in ["PIPE", "FITTINGS", "WELDS"]:
                continue
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
            if length > 1.0:
                continue
            valid_distance = False
            for i, point in enumerate(search_points):
                max_dist = distances[i] if i < len(distances) else distances[-1]
                if (self.get_distance(start, point) <= max_dist or 
                    self.get_distance(end, point) <= max_dist):
                    valid_distance = True
                    break
            if not valid_distance:
                continue
            intersects = False
            for ref_line in reference_lines:
                ref_start = Vec3(ref_line.dxf.start)
                ref_end = Vec3(ref_line.dxf.end)
                if self.line_segments_intersect(start, end, ref_start, ref_end):
                    intersects = True
                    break
            if intersects:
                first_stage_lines.append(entity)
        second_stage_lines = []
        first_stage_endpoints = []
        for line in first_stage_lines:
            first_stage_endpoints.append(Vec3(line.dxf.start))
            first_stage_endpoints.append(Vec3(line.dxf.end))
        if first_stage_endpoints:
            for entity in msp.query('LINE'):
                if entity.dxf.layer in ["PIPE", "FITTINGS", "WELDS"]:
                    continue
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
                if length <= 1.0 or length > 2.2:
                    continue
                close_to_endpoint = False
                for endpoint in first_stage_endpoints:
                    if (self.get_distance(start, endpoint) <= 0.1 or 
                        self.get_distance(end, endpoint) <= 0.1):
                        close_to_endpoint = True
                        break
                if close_to_endpoint:
                    second_stage_lines.append(entity)
        all_del1_lines = first_stage_lines + second_stage_lines
        return all_del1_lines
    
    def calculate_polygon_area(self, vertices):
        n = len(vertices)
        if n < 3:
            return 0
        area = 0
        for i in range(n):
            j = (i + 1) % n
            area += vertices[i][0] * vertices[j][1]
            area -= vertices[j][0] * vertices[i][1]
        return abs(area) / 2
    
    def find_hatches_near_endpoints(self, msp, endpoints, max_area, max_distance):
        hatches = []
        for entity in msp.query('HATCH'):
            if entity in self.used_hatches:
                continue
            try:
                paths = entity.paths
                if paths and hasattr(paths[0], 'vertices'):
                    vertices = paths[0].vertices
                    area = self.calculate_polygon_area(vertices)
                    if area > max_area:
                        continue
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
        return hatches
    
    def find_hatches_near_points(self, msp, points, max_area):
        hatches = []
        for entity in msp.query('HATCH'):
            if entity in self.used_hatches:
                continue
            try:
                paths = entity.paths
                if paths and hasattr(paths[0], 'vertices'):
                    vertices = paths[0].vertices
                    area = self.calculate_polygon_area(vertices)
                    if area > max_area:
                        continue
                    for point in points:
                        for vertex in vertices:
                            if self.get_distance(vertex, point) <= 5:
                                hatches.append(entity)
                                break
                        if entity in hatches:
                            break
            except:
                pass
        return hatches[:2]
    
    def check_ex1_preservation_condition(self, msp, ex1_lines):
        count = 0
        for ex1 in ex1_lines:
            length = (Vec3(ex1.dxf.end) - Vec3(ex1.dxf.start)).magnitude
            if length <= 6.0:
                continue
            ex1_start = Vec3(ex1.dxf.start)
            ex1_end = Vec3(ex1.dxf.end)
            for entity in msp.query('LINE[layer=="DIMLINES"]'):
                if entity.dxf.layer in ["AD1", "AD1-1", "AD2", "AD3", "EX1", "FITTINGS", "WELDS", "PIPE", "DEL1"]:
                    continue
                if (entity in self.used_ad1_lines or 
                    entity in self.used_ad2_lines or
                    entity in self.used_ad3_lines or
                    entity in self.used_ex1_lines):
                    continue
                if entity == ex1:
                    continue
                start = Vec3(entity.dxf.start)
                end = Vec3(entity.dxf.end)
                length = (end - start).magnitude
                if 1.8 <= length <= 2.2:
                    dist_start = self.point_to_line_distance(start, ex1_start, ex1_end)
                    dist_end = self.point_to_line_distance(end, ex1_start, ex1_end)
                    if dist_start <= 0.5 or dist_end <= 0.5:
                        count += 1
                        if count >= 2:
                            return True
        return False
    
    def check_hc_value_is_zero(self, hc_entity):
        try:
            if hasattr(hc_entity, 'dxf') and hasattr(hc_entity.dxf, 'text'):
                text = hc_entity.dxf.text
            elif hasattr(hc_entity, 'text'):
                text = hc_entity.text
            else:
                return False
            text = text.upper().strip()
            zero_patterns = ['0', '0MM', '0 MM', '0.0', '0.0MM', '0.0 MM', '0.00', '0.00MM', '0.00 MM']
            for pattern in zero_patterns:
                if text == pattern:
                    return True
            match = re.search(r'^(\d+\.?\d*)\s*(MM)?$', text)
            if match:
                value = float(match.group(1))
                if value == 0:
                    return True
            return False
        except:
            return False
    
    def delete_insu_elements(self, msp, elements):
        if 'insu1' in elements and elements['insu1']:
            try:
                msp.delete_entity(elements['insu1'])
                self.used_insu_texts.discard(elements['insu1'])
            except:
                pass
        if 'hc' in elements and elements['hc']:
            try:
                msp.delete_entity(elements['hc'])
                self.used_hc_texts.discard(elements['hc'])
            except:
                pass
        if 'tbox_corners' in elements and elements['tbox_corners']:
            for entity in msp.query('LWPOLYLINE[layer=="INSU_BOX"]'):
                try:
                    if len(entity.get_points()) == len(elements['tbox_corners']):
                        match = True
                        for i, point in enumerate(entity.get_points()):
                            if abs(point[0] - elements['tbox_corners'][i][0]) > 0.01 or \
                               abs(point[1] - elements['tbox_corners'][i][1]) > 0.01:
                                match = False
                                break
                        if match:
                            msp.delete_entity(entity)
                            break
                except:
                    pass
        if 'dbox_lines' in elements:
            for line in elements['dbox_lines']:
                try:
                    msp.delete_entity(line)
                    self.used_dbox_lines.discard(line)
                except:
                    pass
        if 'ad1_lines' in elements:
            for line in elements['ad1_lines']:
                try:
                    msp.delete_entity(line)
                    self.used_ad1_lines.discard(line)
                except:
                    pass
        if 'ad2' in elements and elements['ad2']:
            try:
                msp.delete_entity(elements['ad2'])
                self.used_ad2_lines.discard(elements['ad2'])
            except:
                pass
        if 'ad3' in elements and elements['ad3']:
            try:
                msp.delete_entity(elements['ad3'])
                self.used_ad3_lines.discard(elements['ad3'])
            except:
                pass
        if 'del1_lines' in elements:
            for line in elements['del1_lines']:
                try:
                    msp.delete_entity(line)
                    self.used_del1_lines.discard(line)
                except:
                    pass
        if 'hatches' in elements:
            for hatch in elements['hatches']:
                try:
                    msp.delete_entity(hatch)
                    self.used_hatches.discard(hatch)
                except:
                    pass
        if elements.get('delete_ex1', False) and 'ex1_lines' in elements:
            for line in elements['ex1_lines']:
                try:
                    msp.delete_entity(line)
                    self.used_ex1_lines.discard(line)
                except:
                    pass
    
    def process_dbox_phase(self, msp, insu1, index):
        try:
            if insu1 in self.used_insu_texts:
                return False, f"INSU #{index+1}: 이미 사용된 INSU 텍스트입니다.", None
            hc_texts = self.find_text_below(msp, insu1, ["HC", "MM", "mm"])
            if not hc_texts:
                return False, f"INSU #{index+1}: HC 또는 MM 텍스트를 찾을 수 없습니다. (10mm 이내에 없음, TBOX 생성 안함)", None
            hc = hc_texts[0]
            is_hc_zero = self.check_hc_value_is_zero(hc)
            insu_pos = insu1.dxf.insert if hasattr(insu1.dxf, 'insert') else insu1.get_pos()
            hc_pos = hc.dxf.insert if hasattr(hc.dxf, 'insert') else hc.get_pos()
            _ = self.get_distance(insu_pos, hc_pos)
            self.used_insu_texts.add(insu1)
            self.used_hc_texts.add(hc)
            insu1.dxf.color = 4
            hc.dxf.color = 4
            tbox_corners = self.create_box_around_texts([insu1, hc])
            if not tbox_corners:
                return False, f"INSU #{index+1}: TBOX를 생성할 수 없습니다.", None
            tbox_polyline = msp.add_lwpolyline(tbox_corners, close=True)
            tbox_polyline.dxf.layer = "INSU_BOX"
            tbox_polyline.dxf.color = 4
            tbox_polyline.dxf.lineweight = 13
            dbox_lines = self.find_lines_near_box(msp, tbox_corners, 5, 25)
            if len(dbox_lines) < 4:
                self.used_insu_texts.discard(insu1)
                self.used_hc_texts.discard(hc)
                return False, f"INSU #{index+1}: DBOX 라인을 충분히 찾을 수 없습니다. ({len(dbox_lines)}개 찾음, 최소 5mm 필요)", None
            for line in dbox_lines:
                line.dxf.color = 4
                line.dxf.layer = "DBOX"
            data = {
                'insu1': insu1,
                'hc': hc,
                'tbox_corners': tbox_corners,
                'dbox_lines': dbox_lines,
                'hc_is_zero': is_hc_zero
            }
            return True, f"INSU #{index+1}: DBOX까지 처리 완료", data
        except Exception as e:
            if 'insu1' in locals():
                self.used_insu_texts.discard(insu1)
            if 'hc' in locals():
                self.used_hc_texts.discard(hc)
            return False, f"INSU #{index+1}: DBOX 단계 오류 - {str(e)}", None
    
    def process_ad1_phase(self, msp, data, index):
        try:
            insu1 = data['insu1']
            hc = data['hc']
            dbox_lines = data['dbox_lines']
            ad1_result = self.find_line_near_dbox_points(msp, dbox_lines, 7.0)
            if not ad1_result or not ad1_result[0]:
                return False, f"INSU #{index+1}: AD1을 찾을 수 없습니다. (최소 길이 2.2mm, 최대 거리 7mm, 각도 허용 1도)", None
            ad1_lines, ad1_info = ad1_result
            closest_vertical_midpoint, closest_point_on_line, first_ad1 = ad1_info
            total_ad1_length = 0
            ad1_count = 0
            ad1_1_count = 0
            for ad1 in ad1_lines:
                if ad1.dxf.layer == "AD1":
                    ad1_count += 1
                elif ad1.dxf.layer == "AD1-1":
                    ad1_1_count += 1
                length = (Vec3(ad1.dxf.end) - Vec3(ad1.dxf.start)).magnitude
                total_ad1_length += length
            first_ad1_start = Vec3(first_ad1.dxf.start)
            first_ad1_end = Vec3(first_ad1.dxf.end)
            if closest_point_on_line == "start":
                ap1 = first_ad1_start
                ap2 = first_ad1_end
            else:
                ap1 = first_ad1_end
                ap2 = first_ad1_start
            if len(ad1_lines) > 1:
                all_ad1_points = []
                for ad1 in ad1_lines:
                    all_ad1_points.append(Vec3(ad1.dxf.start))
                    all_ad1_points.append(Vec3(ad1.dxf.end))
                max_dist = 0
                for point in all_ad1_points:
                    dist = self.get_distance(point, ap1)
                    if dist > max_dist:
                        max_dist = dist
                        ap2 = point
            ad1_all_points = []
            for ad1 in ad1_lines:
                start = Vec3(ad1.dxf.start)
                end = Vec3(ad1.dxf.end)
                ad1_all_points.append({'point': start, 'type': 'start', 'line': ad1})
                ad1_all_points.append({'point': end, 'type': 'end', 'line': ad1})
            ad2 = None
            min_dist = float('inf')
            closest_ad1_point = None
            for entity in msp.query('LINE'):
                if entity.dxf.layer in ["PIPE", "FITTINGS", "WELDS"]:
                    continue
                if entity in ad1_lines:
                    continue
                if (entity in self.used_dbox_lines or 
                    entity in self.used_ad1_lines or 
                    entity in self.used_ad2_lines or
                    entity in self.used_ad3_lines or
                    entity in self.used_del1_lines):
                    continue
                start = Vec3(entity.dxf.start)
                end = Vec3(entity.dxf.end)
                length = (end - start).magnitude
                if length < 2.2:
                    continue
                for point_info in ad1_all_points:
                    dist = self.point_to_line_distance(point_info['point'], start, end)
                    if dist <= 0.2:
                        if dist < min_dist:
                            ad2 = entity
                            min_dist = dist
                            closest_ad1_point = point_info
            if not ad2:
                return False, f"INSU #{index+1}: AD2를 찾을 수 없습니다. (AD1 양끝점에서 0.2mm 이내에 접하는 라인 없음)", None
            ad2.dxf.layer = "AD2"
            self.used_ad2_lines.add(ad2)
            ad2_length = (Vec3(ad2.dxf.end) - Vec3(ad2.dxf.start)).magnitude
            ad2_start = Vec3(ad2.dxf.start)
            ad2_end = Vec3(ad2.dxf.end)
            reference_point = closest_ad1_point['point']
            if self.get_distance(reference_point, ad2_start) < self.get_distance(reference_point, ad2_end):
                ad2e = ad2_end
            else:
                ad2e = ad2_start
            ad3 = self.find_ad3_near_point(msp, ad2e, 0.2, 10)
            if ad3:
                ad3.dxf.color = 1
                ad3.dxf.layer = "AD3"
                self.used_ad3_lines.add(ad3)
                _ = (Vec3(ad3.dxf.end) - Vec3(ad3.dxf.start)).magnitude
            del1_search_points = [ap2]
            del1_distances = [2.2]
            del1_search_points.extend([Vec3(ad2.dxf.start), Vec3(ad2.dxf.end)])
            del1_distances.extend([2.2, 2.2])
            if ad3:
                del1_search_points.extend([Vec3(ad3.dxf.start), Vec3(ad3.dxf.end)])
                del1_distances.extend([2.2, 2.2])
            del1_lines = self.find_del1_lines_restricted(msp, del1_search_points, del1_distances, ad1_lines, ad2, ad3)
            if not del1_lines:
                del1_lines = []
            all_endpoints = []
            for ad1 in ad1_lines:
                all_endpoints.append(Vec3(ad1.dxf.start))
                all_endpoints.append(Vec3(ad1.dxf.end))
            all_endpoints.append(Vec3(ad2.dxf.start))
            all_endpoints.append(Vec3(ad2.dxf.end))
            if ad3:
                all_endpoints.append(Vec3(ad3.dxf.start))
                all_endpoints.append(Vec3(ad3.dxf.end))
            for line in del1_lines:
                all_endpoints.append(Vec3(line.dxf.start))
                all_endpoints.append(Vec3(line.dxf.end))
            hatches = self.find_hatches_near_endpoints(msp, all_endpoints, 0.8, 5.0)
            if hatches:
                for hatch in hatches:
                    hatch.dxf.color = 1
                    hatch.dxf.layer = "H1"
                    self.used_hatches.add(hatch)
            else:
                hatches = []
            for line in del1_lines:
                line.dxf.color = 1
                line.dxf.layer = "DEL1"
                self.used_del1_lines.add(line)
            ad2.dxf.color = 6
            for line in dbox_lines:
                line.dxf.color = 1
            ad2_ad3_endpoints = []
            ad2_ad3_endpoints.extend([ad2_start, ad2_end])
            if ad3:
                ad2_ad3_endpoints.extend([Vec3(ad3.dxf.start), Vec3(ad3.dxf.end)])
            ex1_count = 0
            ex1_lines = []
            best_ex1 = None
            best_ex1_distance = float('inf')
            for layer in ["DIMLINES", "ISOTEXT"]:
                for entity in msp.query(f'LINE[layer=="{layer}"]'):
                    if entity.dxf.layer in ["PIPE", "FITTINGS", "WELDS"]:
                        continue
                    if (entity in self.used_dbox_lines or 
                        entity in self.used_ad1_lines or 
                        entity in self.used_ad2_lines or
                        entity in self.used_ad3_lines or
                        entity in self.used_del1_lines):
                        continue
                    start = Vec3(entity.dxf.start)
                    end = Vec3(entity.dxf.end)
                    length = (end - start).magnitude
                    if length <= 3.0:
                        continue
                    angle = self.get_line_angle(start, end)
                    if not self.is_iso_angle(angle):
                        continue
                    min_distance = float('inf')
                    for endpoint in ad2_ad3_endpoints:
                        dist = self.point_to_line_distance(endpoint, start, end)
                        if dist < min_distance:
                            min_distance = dist
                    if min_distance <= 0.2 and min_distance < best_ex1_distance:
                        best_ex1 = entity
                        best_ex1_distance = min_distance
            if best_ex1:
                best_ex1.dxf.layer = "EX1"
                best_ex1.dxf.color = 2
                self.used_ex1_lines.add(best_ex1)
                ex1_lines.append(best_ex1)
                ex1_count = 1
                _ = (Vec3(best_ex1.dxf.end) - Vec3(best_ex1.dxf.start)).magnitude
            preserve_elements = False
            delete_ex1 = True
            if data.get('hc_is_zero', False):
                pass
            elif ex1_lines:
                has_long_ex1 = False
                for ex1 in ex1_lines:
                    length = (Vec3(ex1.dxf.end) - Vec3(ex1.dxf.start)).magnitude
                    if length > 6.0:
                        has_long_ex1 = True
                        break
                if not has_long_ex1:
                    pass
                else:
                    preserve_elements = self.check_ex1_preservation_condition(msp, ex1_lines)
                    if preserve_elements:
                        delete_ex1 = False
            processed_elements = {
                'insu1': insu1,
                'hc': hc,
                'hc_is_zero': data.get('hc_is_zero', False),
                'tbox_corners': data.get('tbox_corners'),
                'dbox_lines': dbox_lines,
                'ad1_lines': ad1_lines,
                'ad2': ad2,
                'ad3': ad3,
                'del1_lines': del1_lines,
                'hatches': hatches,
                'ex1_lines': ex1_lines,
                'preserve': preserve_elements,
                'delete_ex1': delete_ex1
            }
            return True, f"INSU #{index+1}: 성공적으로 처리됨", processed_elements
        except Exception as e:
            import traceback
            _ = traceback.format_exc()
            return False, f"INSU #{index+1}: AD1 단계 오류 - {str(e)}", None
    
    def process_single_file(self, filepath):
        try:
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
            if "EX1" not in doc.layers:
                doc.layers.new("EX1")
            if "INSU_BOX" not in doc.layers:
                doc.layers.new("INSU_BOX")
            if "DBOX" not in doc.layers:
                doc.layers.new("DBOX")
            if "AD1" not in doc.layers:
                doc.layers.new("AD1")
            if "AD1-1" not in doc.layers:
                doc.layers.new("AD1-1")
            if "AD2" not in doc.layers:
                doc.layers.new("AD2")
            if "AD3" not in doc.layers:
                doc.layers.new("AD3")
            if "DEL1" not in doc.layers:
                doc.layers.new("DEL1")
            if "H1" not in doc.layers:
                doc.layers.new("H1")
            all_insu_texts = self.find_all_text_with_keyword(msp, "INSU")
            success_count = 0
            delete_count = 0
            preserve_count = 0
            if all_insu_texts:
                insu_data_list = []
                no_hc_count = 0
                for index, insu1 in enumerate(all_insu_texts):
                    success, message, data = self.process_dbox_phase(msp, insu1, index)
                    if success and data:
                        insu_data_list.append((index, data))
                    elif "HC 또는 MM 텍스트를 찾을 수 없습니다" in message:
                        no_hc_count += 1
                processed_insu_list = []
                for index, data in insu_data_list:
                    success, message, elements = self.process_ad1_phase(msp, data, index)
                    if success and elements:
                        success_count += 1
                        processed_insu_list.append((index, elements))
                for index, elements in processed_insu_list:
                    if elements.get('preserve', False):
                        preserve_count += 1
                    else:
                        self.delete_insu_elements(msp, elements)
                        delete_count += 1
            base_name = os.path.splitext(os.path.basename(filepath))[0]
            dir_name = os.path.dirname(filepath)
            new_filename = os.path.join(dir_name, f"{base_name}_INSUDEL.DXF")
            doc.saveas(new_filename)
            if all_insu_texts:
                pass
            else:
                pass
            return True, f"파일 저장 완료: {new_filename}"
        except Exception as e:
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
    
    def run(self, files):
        if not files:
            return
        for filepath in files:
            self.process_single_file(filepath)

if __name__ == "__main__":
    try:
        import ezdxf  # noqa: F401
    except ImportError:
        # 콘솔 출력 금지 요구사항에 따라 아무것도 출력하지 않음
        sys.exit(1)
    processor = DXFProcessor()
    # 명령행 인자로 받은 모든 DXF 파일 처리
    # 예: python PLTONEWLINE.PY A.DXF B.DXF
    files = sys.argv[1:]
    processor.run(files)
