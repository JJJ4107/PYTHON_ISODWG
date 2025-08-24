import ezdxf
import os
import sys
import glob
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
        angle = math.atan2(dy, dx) * 180 / math.pi
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
        Returns: (merged_a1_line, ap1, ap2)
        """
        candidates = []
        for entity in msp:
            if entity.dxftype() == 'LINE' and entity.dxf.layer == 'ISOTEXT':
                if entity in self.used_lines:
                    continue
                start = entity.dxf.start
                end = entity.dxf.end
                dist_start = self.distance_2d(wdc_center, start)
                dist_end = self.distance_2d(wdc_center, end)
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

        if len(candidates) == 1:
            selected = candidates[0]
        else:
            candidates_with_welds = []
            candidates_without_welds = []
            for candidate in candidates:
                ap2 = candidate['ap2']
                has_welds = False
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

            if len(candidates_with_welds) == 1:
                selected = candidates_with_welds[0]
            elif len(candidates_with_welds) > 1:
                selected = min(candidates_with_welds, key=lambda x: x['length'])
            elif candidates_without_welds:
                selected = min(candidates_without_welds, key=lambda x: x['distance'])
            else:
                return None, None, None

        first_line = selected['line']
        self.used_lines.add(first_line)

        has_welds_at_ap2 = self.check_welds_at_ap2(msp, selected['ap2'])
        if has_welds_at_ap2:
            first_line.dxf.layer = 'A1'
            return first_line, selected['ap1'], selected['ap2']
        else:
            continuous_lines = self.find_continuous_lines(msp, first_line)
            for line in continuous_lines:
                self.used_lines.add(line)

            all_lines = [first_line] + continuous_lines
            if len(all_lines) == 1:
                first_line.dxf.layer = 'A1'
                return first_line, selected['ap1'], selected['ap2']
            else:
                all_points = []
                for line in all_lines:
                    all_points.append(line.dxf.start)
                    all_points.append(line.dxf.end)
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
                merged_line = msp.add_line(merged_start, merged_end)
                merged_line.dxf.layer = 'A1'
                for line in all_lines:
                    msp.delete_entity(line)
                dist_start = self.distance_2d(wdc_center, merged_start)
                dist_end = self.distance_2d(wdc_center, merged_end)
                if dist_start < dist_end:
                    return merged_line, merged_start, merged_end
                else:
                    return merged_line, merged_end, merged_start

    def find_continuous_lines(self, msp, base_line, max_distance=8.0, angle_tolerance=1.0):
        """기준 라인과 연속된 라인들을 찾기"""
        continuous_lines = []
        base_start = base_line.dxf.start
        base_end = base_line.dxf.end
        base_angle = self.get_line_angle(base_start, base_end)
        visited = set([base_line])
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
                if entity in visited or entity in self.used_lines:
                    continue
                line_start = entity.dxf.start
                line_end = entity.dxf.end
                connections = [
                    (current_end, line_start),
                    (current_end, line_end),
                    (current_start, line_start),
                    (current_start, line_end)
                ]
                for point1, point2 in connections:
                    dist = self.distance_2d(point1, point2)
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
                            self._find_continuous_from_endpoints(
                                msp, entity, base_angle, max_distance,
                                angle_tolerance, continuous_lines, visited
                            )
                            break


class DXFProcessor:
    def __init__(self):
        self.a1_finder = A1LineFinder()  # A1 찾기 객체 생성

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
        dx = line_end[0] - line_start[0]
        dy = line_end[1] - line_start[1]
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
        text_width = len(text_content) * text_height * 0.7
        insert_point = text_entity.dxf.insert
        rotation = math.radians(text_entity.dxf.rotation)
        corners = [
            (0, -text_height * 0.2),
            (text_width, -text_height * 0.2),
            (text_width, text_height),
            (0, text_height)
        ]
        box_center_local = (text_width / 2, text_height * 0.4)
        rotated_corners = []
        for x, y in corners:
            rx = x * math.cos(rotation) - y * math.sin(rotation) + insert_point[0]
            ry = x * math.sin(rotation) + y * math.cos(rotation) + insert_point[1]
            rotated_corners.append((rx, ry))
        box_center = (
            box_center_local[0] * math.cos(rotation) - box_center_local[1] * math.sin(rotation) + insert_point[0],
            box_center_local[1] * math.cos(rotation) + box_center_local[0] * math.sin(rotation) + insert_point[1]
        )
        return rotated_corners, box_center

    def move_text_box_by_center(self, text_entity, new_center):
        """텍스트 박스의 중심을 새로운 위치로 이동"""
        if text_entity:
            _, current_center = self.create_text_box(text_entity)
            offset_x = new_center[0] - current_center[0]
            offset_y = new_center[1] - current_center[1]
            current_insert = text_entity.dxf.insert
            text_entity.dxf.insert = (
                current_insert[0] + offset_x,
                current_insert[1] + offset_y,
                current_insert[2]
            )

    def check_wd_interference_with_self_exclude(self, msp, wdc_center, wdc_radius, wdt_text, current_wdc, check_boundary=None):
        """WD(WDC+WDT) 전체의 간섭 체크 - 자기 자신만 제외"""
        check_radius = wdc_radius + 0.1
        text_box_corners = None
        if wdt_text:
            text_box_corners, _ = self.create_text_box(wdt_text)
        for entity in msp:
            if entity == current_wdc:
                continue
            if entity == wdt_text:
                continue
            if entity.dxf.layer in ['WL', 'WL1', 'A1']:
                continue
            if entity.dxftype() == 'LINE' and entity.dxf.layer == 'WELDS':
                continue
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
            if entity.dxftype() == 'TEXT':
                text_box_corners_other, _ = self.create_text_box(entity)
                if text_box_corners_other:
                    for corner in text_box_corners_other:
                        if self.distance_2d(corner, wdc_center) < check_radius:
                            return True
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
        dx = line_end[0] - line_start[0]
        dy = line_end[1] - line_start[1]
        line_angle = math.degrees(math.atan2(dy, dx))
        if line_angle < 0:
            line_angle += 360
        iso_angles = [0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330]
        closest_iso = min(iso_angles, key=lambda x: min(abs(x - line_angle), abs(x - line_angle + 360), abs(x - line_angle - 360)))
        if closest_iso in [30, 210]:
            perp_angle = closest_iso + 60
        elif closest_iso in [150, 330]:
            perp_angle = closest_iso - 60
        else:
            perp_angle = closest_iso + 90
        return perp_angle % 360

    def rotate_point_around_center(self, point, center, angle_degrees):
        """점을 중심점 주위로 회전"""
        angle_rad = math.radians(angle_degrees)
        cos_angle = math.cos(angle_rad)
        sin_angle = math.sin(angle_rad)
        dx = point[0] - center[0]
        dy = point[1] - center[1]
        new_x = dx * math.cos(angle_rad) - dy * math.sin(angle_rad)
        new_y = dx * math.sin(angle_rad) + dy * math.cos(angle_rad)
        return (new_x + center[0], new_y + center[1], point[2])

    def find_ap2_from_wl_line(self, wl_line, wdc_center):
        """WL 라인에서 WDC 원 중심에서 먼 끝점을 AP2로 찾기"""
        if not wl_line:
            return None
        start = wl_line.dxf.start
        end = wl_line.dxf.end
        dist_start = self.distance_2d(wdc_center, start)
        dist_end = self.distance_2d(wdc_center, end)
        if dist_start > dist_end:
            return start
        else:
            return end

    def process_welds_circles(self, msp):
        """WELDS 레이어의 원들을 처리하는 메서드"""
        welds_processed = 0
        small_circles_created = 0
        for entity in msp:
            if entity.dxftype() == 'CIRCLE' and entity.dxf.layer == 'WELDS':
                radius = entity.dxf.radius
                if 0.4 <= radius <= 1.2:
                    welds_processed += 1
                    entity.dxf.color = 6  # YELLOW
                    center = entity.dxf.center
                    for i in range(1, 6):
                        new_radius = radius - (0.2 * i)
                        if new_radius > 0.1:
                            concentric_circle = msp.add_circle(center, new_radius)
                            concentric_circle.dxf.layer = 'WELDS'
                            concentric_circle.dxf.color = 6
                            small_circles_created += 1
                        else:
                            break
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
            st_position = wdc_data['st_position']
            if not wl_line:
                continue
            if not pipe1:
                continue
            wl_start = wl_line.dxf.start
            wl_end = wl_line.dxf.end
            wl_length = self.distance_2d(wl_start, wl_end)
            if wl_length < 4.0:
                continue
            wdc.dxf.color = 1  # RED
            st2_position = wdc.dxf.center
            a1_length = self.distance_2d(st2_position, ap2)
            check_boundary = wdc.dxf.radius + a1_length
            direction = np.array([st2_position[0] - ap2[0], st2_position[1] - ap2[1]])
            direction_norm = direction / np.linalg.norm(direction)
            mo_position = (
                ap2[0] + direction_norm[0] * (wdc.dxf.radius + 2.9),
                ap2[1] + direction_norm[1] * (wdc.dxf.radius + 2.9),
                st2_position[2]
            )
            wdc.dxf.center = mo_position
            if wdt_text:
                self.move_text_box_by_center(wdt_text, mo_position)
            original_wdc_center = wdc.dxf.center
            original_wdt_center = None
            if wdt_text:
                _, original_wdt_center = self.create_text_box(wdt_text)
            wdc.dxf.center = mo_position
            if wdt_text:
                self.move_text_box_by_center(wdt_text, mo_position)
            if not self.check_wd_interference_with_self_exclude(msp, mo_position, wdc.dxf.radius, wdt_text, wdc, check_boundary):
                final_position = mo_position
                final_angle = 0
                found_position = True
            else:
                perp_angle = self.get_iso_perpendicular_angle(pipe1.dxf.start, pipe1.dxf.end)
                interference_free_positions = []
                for angle in range(0, 360, 10):
                    test_position = self.rotate_point_around_center(mo_position, ap2, angle)
                    wdc.dxf.center = test_position
                    if wdt_text:
                        self.move_text_box_by_center(wdt_text, test_position)
                    has_interference = self.check_wd_interference_with_self_exclude(msp, test_position, wdc.dxf.radius, wdt_text, wdc, check_boundary)
                    if not has_interference:
                        interference_free_positions.append({
                            'position': test_position,
                            'angle': angle,
                            'abs_angle': (perp_angle + angle) % 360
                        })
                    wdc.dxf.center = original_wdc_center
                    if wdt_text and original_wdt_center:
                        self.move_text_box_by_center(wdt_text, original_wdt_center)
                if interference_free_positions:
                    iso_orthogonal_angles = [0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330]
                    for pos in interference_free_positions:
                        min_diff = min([min(abs(pos['abs_angle'] - iso_angle),
                                            abs(pos['abs_angle'] - iso_angle + 360),
                                            abs(pos['abs_angle'] - iso_angle - 360))
                                        for iso_angle in iso_orthogonal_angles])
                        pos['orthogonal_diff'] = min_diff
                    best_position = min(interference_free_positions, key=lambda x: x['orthogonal_diff'])
                    final_position = best_position['position']
                    final_angle = best_position['angle']
                    found_position = True
                else:
                    found_position = False
            if found_position:
                wdc.dxf.center = final_position
                if wdt_text:
                    self.move_text_box_by_center(wdt_text, final_position)
            else:
                wdc.dxf.center = st_position
                if wdt_text:
                    self.move_text_box_by_center(wdt_text, st_position)
                final_position = st_position
            if final_position != st2_position:
                if wl_line:
                    msp.delete_entity(wl_line)
                intersections = self.get_circle_line_intersection(final_position, wdc.dxf.radius, final_position, ap2)
                if intersections and len(intersections) > 0:
                    exit_point = min(intersections, key=lambda p: self.distance_2d(p, ap2))
                    new_wl = msp.add_line(exit_point, ap2)
                    new_wl.dxf.layer = 'WL1'
                    new_wl.dxf.color = 7
                else:
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
                if distance <= 4.0 and abs(rotation) < 0.1:
                    entity.dxf.layer = 'WDT'
                    return entity
        return None

    def find_pipe_lines(self, msp, ap2):
        """AP2에서 가장 가까운 PIPE 이름을 포함하는 레이어의 선 찾기 (거리 제한 없음, 최대 2개)"""
        pipe_lines = []
        pipe_candidates = []
        for entity in msp:
            if entity.dxftype() == 'LINE':
                start = entity.dxf.start
                end = entity.dxf.end
                min_dist = min(self.distance_2d(ap2, start), self.distance_2d(ap2, end))
                if 'PIPE' in entity.dxf.layer.upper():
                    pipe_candidates.append({
                        'entity': entity,
                        'distance': min_dist,
                        'layer': entity.dxf.layer
                    })
        pipe_candidates.sort(key=lambda x: x['distance'])
        for i, candidate in enumerate(pipe_candidates[:2]):
            pipe = candidate['entity']
            pipe.pipe_name = f'PIPE{i+1}'
            pipe_lines.append(pipe)
        return pipe_lines

    def find_elbo_arc(self, msp, ap2):
        """AP2에서 가장 가까운 ELBO 이름을 포함하는 레이어의 호 찾기 (거리 제한 없음)"""
        closest_elbo = None
        closest_distance = float('inf')
        for entity in msp:
            if entity.dxftype() == 'ARC' and 'ELBO' in entity.dxf.layer.upper():
                center = entity.dxf.center
                radius = entity.dxf.radius
                dist_to_center = self.distance_2d(ap2, center)
                min_dist = abs(dist_to_center - radius)
                if min_dist < closest_distance:
                    closest_distance = min_dist
                    closest_elbo = entity
        if closest_elbo:
            closest_elbo.elbo_name = 'ELBO1'
            return closest_elbo
        return None

    def process_dxf_file(self, file_path):
        """DXF 파일 처리"""
        try:
            doc = ezdxf.readfile(file_path)
            msp = doc.modelspace()
            welds_processed, small_circles_count = self.process_welds_circles(msp)
            wdc_circles = self.find_wdc_circles(msp)
            wdc_data_collection = []
            for wdc in wdc_circles:
                wdc_center = wdc.dxf.center
                wdc_radius = wdc.dxf.radius
                wdt_text = self.find_wdt_text(msp, wdc)
                a1_line, ap1, ap2 = self.a1_finder.find_a1_from_wdc(msp, wdc_center)
                if not a1_line or not ap2:
                    continue
                pipe_lines = self.find_pipe_lines(msp, ap2)
                elbo_arc = self.find_elbo_arc(msp, ap2)
                st_position = wdc_center
                if wdt_text:
                    self.move_text_box_by_center(wdt_text, wdc_center)
                direction = np.array([wdc_center[0] - ap2[0], wdc_center[1] - ap2[1], 0])
                direction_length = np.linalg.norm(direction[:2])
                if direction_length == 0:
                    continue
                direction_norm = direction[:2] / direction_length
                target_distance = wdc_radius + 2.9
                mo_position = (
                    ap2[0] + direction_norm[0] * target_distance,
                    ap2[1] + direction_norm[1] * target_distance,
                    ap2[2]
                )
                a1_length = self.distance_2d(wdc_center, ap2)
                check_boundary = wdc_radius + a1_length
                wdc.dxf.center = mo_position
                if wdt_text:
                    self.move_text_box_by_center(wdt_text, mo_position)
                interference = self.check_wd_interference_with_self_exclude(msp, mo_position, wdc_radius, wdt_text, wdc, check_boundary)
                final_position = mo_position
                if interference:
                    back_direction = np.array([st_position[0] - mo_position[0], st_position[1] - mo_position[1]])
                    back_distance = np.linalg.norm(back_direction)
                    if back_distance == 0:
                        pass
                    else:
                        back_direction_norm = back_direction / back_distance
                        step = 1.0
                        max_distance = np.linalg.norm(back_direction)
                        max_steps = int(max_distance / step)
                        found_position = False
                        for i in range(1, max_steps + 1):
                            test_position = (
                                mo_position[0] + back_direction_norm[0] * (step * i),
                                mo_position[1] + back_direction_norm[1] * (step * i),
                                mo_position[2]
                            )
                            wdc.dxf.center = test_position
                            if wdt_text:
                                self.move_text_box_by_center(wdt_text, test_position)
                            if not self.check_wd_interference_with_self_exclude(msp, test_position, wdc_radius, wdt_text, wdc, check_boundary):
                                final_position = test_position
                                found_position = True
                                break
                        if not found_position:
                            final_position = st_position
                            wdc.dxf.center = final_position
                            if wdt_text:
                                self.move_text_box_by_center(wdt_text, final_position)
                intersections = self.get_circle_line_intersection(final_position, wdc_radius, final_position, ap2)
                wl_line = None
                if intersections and len(intersections) > 0:
                    exit_point = min(intersections, key=lambda p: self.distance_2d(p, ap2))
                    wl_line = msp.add_line(exit_point, ap2)
                    wl_line.dxf.layer = 'WL'
                    wl_line.dxf.color = 7
                else:
                    dist_to_ap2 = self.distance_2d(final_position, ap2)
                    if dist_to_ap2 > wdc_radius:
                        wl_line = msp.add_line(final_position, ap2)
                        wl_line.dxf.layer = 'WL'
                        wl_line.dxf.color = 7
                    else:
                        wl_line = None
                if a1_line:
                    msp.delete_entity(a1_line)
                wdc_data_collection.append({
                    'wdc': wdc,
                    'wdt': wdt_text,
                    'ap2': ap2,
                    'pipe_lines': pipe_lines,
                    'wl_line': wl_line,
                    'st_position': st_position,
                    'final_position': final_position,
                    'a1_line': a1_line
                })
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            output_path = os.path.join(
                os.path.dirname(file_path),
                f"{base_name}_WDNO.DXF"
            )
            doc.saveas(output_path)
            doc2 = ezdxf.readfile(output_path)
            msp2 = doc2.modelspace()
            wdc_data_list = []
            for entity in msp2:
                if entity.dxftype() == 'CIRCLE' and entity.dxf.layer == 'WDC':
                    wdc = entity
                    wdc_center = wdc.dxf.center
                    wdc_radius = wdc.dxf.radius
                    wdt_text = None
                    wl_line = None
                    ap2 = None
                    pipe1 = None
                    for text in msp2:
                        if text.dxftype() == 'TEXT' and text.dxf.layer == 'WDT':
                            try:
                                _, text_center = self.create_text_box(text)
                                if text_center and self.distance_2d(wdc_center, text_center) < 0.5:
                                    wdt_text = text
                                    break
                            except:
                                continue
                    for line in msp2:
                        if line.dxftype() == 'LINE' and line.dxf.layer == 'WL':
                            dist_start = self.distance_2d(wdc_center, line.dxf.start)
                            dist_end = self.distance_2d(wdc_center, line.dxf.end)
                            if dist_start <= wdc_radius + 2.0 or dist_end <= wdc_radius + 2.0:
                                wl_line = line
                                ap2 = self.find_ap2_from_wl_line(wl_line, wdc_center)
                                wl_length = self.distance_2d(line.dxf.start, line.dxf.end)
                                if wl_length >= 4.0:
                                    wl_line.dxf.color = 4  # CYAN
                                break
                    if not wl_line:
                        continue
                    if ap2:
                        closest_pipe = None
                        closest_distance = float('inf')
                        closest_layer = None
                        for line in msp2:
                            if line.dxftype() == 'LINE' and 'PIPE' in line.dxf.layer.upper():
                                dist_to_wl_start_from_pipe_start = self.distance_2d(wl_line.dxf.start, line.dxf.start)
                                dist_to_wl_start_from_pipe_end = self.distance_2d(wl_line.dxf.start, line.dxf.end)
                                dist_to_wl_end_from_pipe_start = self.distance_2d(wl_line.dxf.end, line.dxf.start)
                                dist_to_wl_end_from_pipe_end = self.distance_2d(wl_line.dxf.end, line.dxf.end)
                                min_dist = min(dist_to_wl_start_from_pipe_start, dist_to_wl_start_from_pipe_end,
                                               dist_to_wl_end_from_pipe_start, dist_to_wl_end_from_pipe_end)
                                if min_dist < closest_distance:
                                    closest_distance = min_dist
                                    closest_pipe = line
                                    closest_layer = line.dxf.layer
                        if closest_pipe:
                            pipe1 = closest_pipe
                        wdc_data = {
                            'wdc': wdc,
                            'wdt': wdt_text,
                            'ap2': ap2,
                            'pipe1': pipe1,
                            'wl_line': wl_line,
                            'st_position': wdc_center
                        }
                        wdc_data_list.append(wdc_data)
            if wdc_data_list:
                self.second_stage_processing(doc2, wdc_data_list)
                doc2.saveas(output_path)
            return True, output_path
        except Exception as e:
            return False, str(e)

    def run_cli(self, file_paths):
        """커맨드라인 인자로 전달된 여러 DXF 파일 처리"""
        results = []
        for file_path in file_paths:
            success, result = self.process_dxf_file(file_path)
            results.append((file_path, success, result))
        return results


def _expand_cli_paths(argv):
    """명령행 인자(와일드카드 포함)를 파일 경로 리스트로 확장"""
    paths = []
    for a in argv:
        expanded = glob.glob(a)
        if expanded:
            paths.extend(expanded)
        else:
            paths.append(a)
    uniq = []
    seen = set()
    for p in paths:
        ap = os.path.abspath(p)
        if ap not in seen and os.path.isfile(ap):
            seen.add(ap)
            uniq.append(ap)
    return uniq


def main():
    # 사용법: python SP3D_ON_03_WELDNOEDIT.PY A_PL_INSUDEL.DXF B.DXF ".\batch\*.dxf"
    args = sys.argv[1:]
    if not args:
        return
    dxf_files = _expand_cli_paths(args)
    processor = DXFProcessor()
    processor.run_cli(dxf_files)


if __name__ == "__main__":
    main()
