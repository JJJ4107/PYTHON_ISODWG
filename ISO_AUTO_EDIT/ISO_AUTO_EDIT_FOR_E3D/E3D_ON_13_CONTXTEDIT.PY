import ezdxf
import math
import os
import re
import sys

class DXFProcessor:
    def __init__(self):
        self.doc = None
        self.msp = None
        self.AP1 = None  # 가까운 점 (이동됨)
        self.AP2 = None  # 먼 점 (고정됨)
        self.AP3 = None  # 3점 폴리라인의 3번째 점
        self.original_AP1 = None  # 원래 AP1 위치

    def set_entity_color(self, entity, color=4):
        try:
            if hasattr(entity, 'dxf'):
                entity.dxf.color = color
                if hasattr(entity.dxf, 'true_color'):
                    entity.dxf.true_color = None
        except Exception:
            pass

    def force_entity_color(self, entity, color):
        try:
            entity_type = entity.dxftype()
            entity.dxf.color = color
            if hasattr(entity.dxf, 'color') and entity.dxf.color == 256:
                entity.dxf.color = color
            if entity_type == 'POLYLINE' and hasattr(entity, 'vertices'):
                for vertex in entity.vertices:
                    vertex.dxf.color = color
        except Exception:
            pass

    def get_text_rotation(self, text_entity):
        if hasattr(text_entity, 'dxf') and hasattr(text_entity.dxf, 'rotation'):
            return text_entity.dxf.rotation
        return 0

    def get_entity_position(self, entity):
        if entity.dxftype() == 'TEXT':
            return (entity.dxf.insert.x, entity.dxf.insert.y)
        elif entity.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
            points = list(entity.points())
            if points:
                return (points[0][0], points[0][1])
        return None

    def calculate_distance(self, point1, point2):
        return math.sqrt((point2[0] - point1[0])**2 + (point2[1] - point1[1])**2)

    def distance_between_entities(self, entity1, entity2):
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

    def find_con_texts(self):
        con_texts = []
        for entity in self.msp:
            if entity.dxftype() == 'TEXT':
                text = entity.dxf.text.upper()
                if 'CONN.' in text or 'CONT.' in text:
                    con_texts.append(entity)
        return con_texts

    def find_texts_below_con(self, con_text):
        con_pos = self.get_entity_position(con_text)
        if not con_pos:
            return []
        found_texts = []
        current_y = con_pos[1]
        for _ in range(1, 21):
            current_y -= 5
            for entity in self.msp:
                if entity.dxftype() == 'TEXT':
                    text_pos = self.get_entity_position(entity)
                    if text_pos:
                        if abs(text_pos[1] - current_y) <= 2 and abs(text_pos[0] - con_pos[0]) <= 15:
                            text_upper = entity.dxf.text.upper().strip()
                            if text_upper.startswith('E') or text_upper.startswith('W'):
                                return found_texts
                            found_texts.append(entity)
                            break
        return found_texts

    def find_position_texts_below(self, last_text):
        if not last_text:
            return None, None, None
        last_pos = self.get_entity_position(last_text)
        if not last_pos:
            return None, None, None
        epos = None
        npos = None
        elev = None
        for entity in self.msp:
            if entity.dxftype() == 'TEXT':
                text_pos = self.get_entity_position(entity)
                if text_pos:
                    y_diff = last_pos[1] - text_pos[1]
                    if 0 < y_diff <= 30 and abs(text_pos[0] - last_pos[0]) <= 15:
                        text_upper = entity.dxf.text.upper().strip()
                        if not epos and (text_upper.startswith('E') or text_upper.startswith('W')):
                            epos = entity
                        elif not npos and (text_upper.startswith('S') or text_upper.startswith('N')):
                            npos = entity
                        elif not elev and (text_upper.startswith('FL') or text_upper.startswith('EL')):
                            elev = entity
        return epos, npos, elev

    def get_text_bounding_box(self, text_entity):
        if text_entity.dxftype() != 'TEXT':
            return None
        insert = text_entity.dxf.insert
        x, y = insert.x, insert.y
        height = text_entity.dxf.height
        text_content = text_entity.dxf.text
        char_width = height * 0.7
        length = len(text_content) * char_width
        rotation = self.get_text_rotation(text_entity)
        rotation_rad = math.radians(rotation)
        if rotation == 0:
            corners = [
                (x, y),
                (x + length, y),
                (x + length, y + height),
                (x, y + height)
            ]
        else:
            cos_r = math.cos(rotation_rad)
            sin_r = math.sin(rotation_rad)
            corners = []
            local_corners = [(0, 0), (length, 0), (length, height), (0, height)]
            for lx, ly in local_corners:
                rx = x + lx * cos_r - ly * sin_r
                ry = y + lx * sin_r + ly * cos_r
                corners.append((rx, ry))
        return corners

    def get_bounding_box(self, entities):
        min_x, min_y = float('inf'), float('inf')
        max_x, max_y = float('-inf'), float('-inf')
        for entity in entities:
            if entity.dxftype() == 'TEXT':
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
        points = list(polyline.points())
        total_length = 0
        for i in range(len(points) - 1):
            total_length += self.calculate_distance(
                (points[i][0], points[i][1]),
                (points[i+1][0], points[i+1][1])
            )
        return total_length

    def check_interference(self, entities, position):
        for entity in self.msp:
            if entity not in entities:
                if entity.dxftype() in ['TEXT', 'LINE', 'POLYLINE', 'LWPOLYLINE']:
                    entity_pos = self.get_entity_position(entity)
                    if entity_pos and self.calculate_distance(entity_pos, position) < 1:
                        return True
        return False

    def normalize_vector(self, vector):
        length = math.sqrt(vector[0]**2 + vector[1]**2)
        if length == 0:
            return (0, 0)
        return (vector[0]/length, vector[1]/length)

    def move_entity(self, entity, dx, dy):
        try:
            if entity.dxftype() == 'TEXT':
                old_pos = entity.dxf.insert
                entity.dxf.insert = (old_pos.x + dx, old_pos.y + dy, old_pos.z)
            elif entity.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
                if entity.dxftype() == 'LWPOLYLINE':
                    old_points = list(entity.get_points())
                    new_points = []
                    for x, y, *rest in old_points:
                        new_points.append((x + dx, y + dy, *rest))
                    entity.set_points(new_points)
                elif entity.dxftype() == 'POLYLINE':
                    for vertex in entity.vertices:
                        vertex.dxf.location = (
                            vertex.dxf.location.x + dx,
                            vertex.dxf.location.y + dy,
                            vertex.dxf.location.z
                        )
        except Exception:
            pass

    def boxes_overlap(self, box1_corners, box2_corners):
        box1_min_x = min(corner[0] for corner in box1_corners)
        box1_max_x = max(corner[0] for corner in box1_corners)
        box1_min_y = min(corner[1] for corner in box1_corners)
        box1_max_y = max(corner[1] for corner in box1_corners)
        box2_min_x = min(corner[0] for corner in box2_corners)
        box2_max_x = max(corner[0] for corner in box2_corners)
        box2_min_y = min(corner[1] for corner in box2_corners)
        box2_max_y = max(corner[1] for corner in box2_corners)
        if box1_max_x < box2_min_x - 1 or box1_min_x > box2_max_x + 1:
            return False
        if box1_max_y < box2_min_y - 1 or box1_min_y > box2_max_y + 1:
            return False
        return True

    def line_intersects_box(self, line_start, line_end, box_corners):
        min_x = min(corner[0] for corner in box_corners)
        max_x = max(corner[0] for corner in box_corners)
        min_y = min(corner[1] for corner in box_corners)
        max_y = max(corner[1] for corner in box_corners)
        if (min_x <= line_start[0] <= max_x and min_y <= line_start[1] <= max_y):
            return True
        if (min_x <= line_end[0] <= max_x and min_y <= line_end[1] <= max_y):
            return True
        box_edges = [
            (box_corners[0], box_corners[1]),
            (box_corners[1], box_corners[2]),
            (box_corners[2], box_corners[3]),
            (box_corners[3], box_corners[0])
        ]
        for edge_start, edge_end in box_edges:
            if self.line_segments_intersect(line_start, line_end, edge_start, edge_end):
                return True
        if line_start[1] == line_end[1]:
            if min_y <= line_start[1] <= max_y:
                if (line_start[0] <= min_x and line_end[0] >= max_x) or \
                   (line_end[0] <= min_x and line_start[0] >= max_x):
                    return True
        if line_start[0] == line_end[0]:
            if min_x <= line_start[0] <= max_x:
                if (line_start[1] <= min_y and line_end[1] >= max_y) or \
                   (line_end[1] <= min_y and line_start[1] >= max_y):
                    return True
        return False

    def circle_intersects_box(self, center, radius, box_corners):
        min_x = min(corner[0] for corner in box_corners)
        max_x = max(corner[0] for corner in box_corners)
        min_y = min(corner[1] for corner in box_corners)
        max_y = max(corner[1] for corner in box_corners)
        closest_x = max(min_x, min(center[0], max_x))
        closest_y = max(min_y, min(center[1], max_y))
        distance = self.calculate_distance(center, (closest_x, closest_y))
        return distance <= radius + 1

    def arc_intersects_box(self, center, radius, start_angle, end_angle, box_corners):
        if not self.circle_intersects_box(center, radius, box_corners):
            return False
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
        min_x = min(corner[0] for corner in box_corners)
        max_x = max(corner[0] for corner in box_corners)
        min_y = min(corner[1] for corner in box_corners)
        max_y = max(corner[1] for corner in box_corners)
        if (min_x <= start_point[0] <= max_x and min_y <= start_point[1] <= max_y):
            return True
        if (min_x <= end_point[0] <= max_x and min_y <= end_point[1] <= max_y):
            return True
        num_samples = 20
        for i in range(num_samples + 1):
            t = i / num_samples
            angle = start_rad + t * (end_rad - start_rad)
            if end_rad < start_rad:
                angle = start_rad + t * (end_rad + 2 * math.pi - start_rad)
            point = (
                center[0] + radius * math.cos(angle),
                center[1] + radius * math.sin(angle)
            )
            if min_x <= point[0] <= max_x and min_y <= point[1] <= max_y:
                return True
        return False

    def check_box_interference_dual(self, apos_bbox, cont_bbox, dx, dy, exclude_entities):
        moved_apos_corners = [(corner[0] + dx, corner[1] + dy) for corner in apos_bbox]
        moved_cont_corners = [(corner[0] + dx, corner[1] + dy) for corner in cont_bbox]
        for box_corners in [moved_apos_corners, moved_cont_corners]:
            min_x = min(corner[0] for corner in box_corners) - 1
            max_x = max(corner[0] for corner in box_corners) + 1
            min_y = min(corner[1] for corner in box_corners) - 1
            max_y = max(corner[1] for corner in box_corners) + 1
            expanded_corners = [(min_x, min_y), (max_x, min_y), (max_x, max_y), (min_x, max_y)]
            for entity in self.msp:
                if entity not in exclude_entities:
                    entity_type = entity.dxftype()
                    if entity_type == 'TEXT':
                        text_box = self.get_text_bounding_box(entity)
                        if text_box and self.boxes_overlap(expanded_corners, text_box):
                            return True
                    elif entity_type == 'LINE':
                        line_start = (entity.dxf.start.x, entity.dxf.start.y)
                        line_end = (entity.dxf.end.x, entity.dxf.end.y)
                        if self.line_intersects_box(line_start, line_end, expanded_corners):
                            return True
                    elif entity_type in ['POLYLINE', 'LWPOLYLINE']:
                        points = list(entity.points())
                        for i in range(len(points) - 1):
                            seg_start = (points[i][0], points[i][1])
                            seg_end = (points[i+1][0], points[i+1][1])
                            if self.line_intersects_box(seg_start, seg_end, expanded_corners):
                                return True
                        if hasattr(entity.dxf, 'flags') and entity.dxf.flags & 1:
                            if len(points) > 2:
                                seg_start = (points[-1][0], points[-1][1])
                                seg_end = (points[0][0], points[0][1])
                                if self.line_intersects_box(seg_start, seg_end, expanded_corners):
                                    return True
                    elif entity_type == 'CIRCLE':
                        center = (entity.dxf.center.x, entity.dxf.center.y)
                        radius = entity.dxf.radius
                        if self.circle_intersects_box(center, radius, expanded_corners):
                            return True
                    elif entity_type == 'ARC':
                        center = (entity.dxf.center.x, entity.dxf.center.y)
                        radius = entity.dxf.radius
                        start_angle = entity.dxf.start_angle
                        end_angle = entity.dxf.end_angle
                        if self.arc_intersects_box(center, radius, start_angle, end_angle, expanded_corners):
                            return True
        return False

    def count_box_interferences_dual(self, apos_bbox, cont_bbox, dx, dy, exclude_entities):
        moved_apos_corners = [(corner[0] + dx, corner[1] + dy) for corner in apos_bbox]
        moved_cont_corners = [(corner[0] + dx, corner[1] + dy) for corner in cont_bbox]
        interference_count = 0
        interfered_entities = set()
        for box_corners in [moved_apos_corners, moved_cont_corners]:
            min_x = min(corner[0] for corner in box_corners) - 1
            max_x = max(corner[0] for corner in box_corners) + 1
            min_y = min(corner[1] for corner in box_corners) - 1
            max_y = max(corner[1] for corner in box_corners) + 1
            expanded_corners = [(min_x, min_y), (max_x, min_y), (max_x, max_y), (min_x, max_y)]
            for entity in self.msp:
                if entity not in exclude_entities and entity not in interfered_entities:
                    entity_type = entity.dxftype()
                    has_interference = False
                    if entity_type == 'TEXT':
                        text_box = self.get_text_bounding_box(entity)
                        if text_box and self.boxes_overlap(expanded_corners, text_box):
                            has_interference = True
                    elif entity_type == 'LINE':
                        line_start = (entity.dxf.start.x, entity.dxf.start.y)
                        line_end = (entity.dxf.end.x, entity.dxf.end.y)
                        if self.line_intersects_box(line_start, line_end, expanded_corners):
                            has_interference = True
                    elif entity_type in ['POLYLINE', 'LWPOLYLINE']:
                        points = list(entity.points())
                        for i in range(len(points) - 1):
                            seg_start = (points[i][0], points[i][1])
                            seg_end = (points[i+1][0], points[i+1][1])
                            if self.line_intersects_box(seg_start, seg_end, expanded_corners):
                                has_interference = True
                                break
                        if not has_interference and hasattr(entity.dxf, 'flags') and entity.dxf.flags & 1:
                            if len(points) > 2:
                                seg_start = (points[-1][0], points[-1][1])
                                seg_end = (points[0][0], points[0][1])
                                if self.line_intersects_box(seg_start, seg_end, expanded_corners):
                                    has_interference = True
                    elif entity_type == 'CIRCLE':
                        center = (entity.dxf.center.x, entity.dxf.center.y)
                        radius = entity.dxf.radius
                        if self.circle_intersects_box(center, radius, expanded_corners):
                            has_interference = True
                    elif entity_type == 'ARC':
                        center = (entity.dxf.center.x, entity.dxf.center.y)
                        radius = entity.dxf.radius
                        start_angle = entity.dxf.start_angle
                        end_angle = entity.dxf.end_angle
                        if self.arc_intersects_box(center, radius, start_angle, end_angle, expanded_corners):
                            has_interference = True
                    if has_interference:
                        interfered_entities.add(entity)
                        interference_count += 1
        return interference_count

    def find_target_position_and_move_entities(self, a1_polyline, alltxt_entities, apos_entities, cont_entities):
        bbox_corners = self.get_bounding_box(alltxt_entities)
        bbox_center = (
            (bbox_corners[0][0] + bbox_corners[2][0]) / 2,
            (bbox_corners[0][1] + bbox_corners[2][1]) / 2
        )
        apos_bbox = self.get_bounding_box(apos_entities) if apos_entities else bbox_corners
        cont_bbox = self.get_bounding_box(cont_entities) if cont_entities else bbox_corners
        a1_points = list(a1_polyline.points())
        min_dist = float('inf')
        max_dist = 0
        AP1 = None
        AP2 = None
        for point in a1_points:
            pt = (point[0], point[1])
            dist = self.calculate_distance(pt, bbox_center)
            if dist < min_dist:
                min_dist = dist
                AP1 = pt
            if dist > max_dist:
                max_dist = dist
                AP2 = pt
        if len(a1_points) == 3:
            self.AP3 = (a1_points[2][0], a1_points[2][1])
        else:
            self.AP3 = None
        if not AP1 or not AP2:
            return None
        self.AP1 = AP1
        self.AP2 = AP2
        self.original_AP1 = AP1
        try:
            self.msp.delete_entity(a1_polyline)
        except Exception:
            pass
        a1_vector = (AP2[0] - AP1[0], AP2[1] - AP1[1])
        direction = (AP1[0] - AP2[0], AP1[1] - AP2[1])
        direction = self.normalize_vector(direction)
        base_dx = a1_vector[0]
        base_dy = a1_vector[1]
        initial_move = 15
        initial_dx = base_dx + direction[0] * initial_move
        initial_dy = base_dy + direction[1] * initial_move
        position_results = []
        for step in range(5, 20):
            move_distance = step * 3
            dx = base_dx + direction[0] * move_distance
            dy = base_dy + direction[1] * move_distance
            has_interference = self.check_box_interference_dual(apos_bbox, cont_bbox, dx, dy, alltxt_entities)
            if has_interference:
                interference_count = self.count_box_interferences_dual(apos_bbox, cont_bbox, dx, dy, alltxt_entities)
                position_results.append({
                    'distance': move_distance,
                    'dx': dx,
                    'dy': dy,
                    'has_interference': True,
                    'interference_count': interference_count
                })
            else:
                position_results.append({
                    'distance': move_distance,
                    'dx': dx,
                    'dy': dy,
                    'has_interference': False,
                    'interference_count': 0
                })
                break
        final_dx = initial_dx
        final_dy = initial_dy
        if position_results:
            no_interference_positions = [p for p in position_results if not p['has_interference']]
            if no_interference_positions:
                best_position = no_interference_positions[0]
                final_dx = best_position['dx']
                final_dy = best_position['dy']
            else:
                best_position = min(position_results, key=lambda p: p['interference_count'])
                final_dx = best_position['dx']
                final_dy = best_position['dy']
        if final_dx != 0 or final_dy != 0:
            for entity in alltxt_entities:
                self.move_entity(entity, final_dx, final_dy)
            self.AP1 = (AP1[0] + final_dx, AP1[1] + final_dy)
        return (final_dx, final_dy)

    def find_a2_arrow_line_with_points(self, a1_points):
        if not hasattr(self, 'AP2'):
            return None
        a1_segments = []
        for i in range(len(a1_points) - 1):
            seg_start = (a1_points[i][0], a1_points[i][1])
            seg_end = (a1_points[i+1][0], a1_points[i+1][1])
            a1_segments.append((seg_start, seg_end))
        for entity in self.msp:
            if entity.dxftype() == 'LINE':
                if hasattr(entity.dxf, 'layer') and entity.dxf.layer.upper() == 'ARROW':
                    line_start = (entity.dxf.start.x, entity.dxf.start.y)
                    line_end = (entity.dxf.end.x, entity.dxf.end.y)
                    if (self.calculate_distance(line_start, self.AP2) <= 3 or
                        self.calculate_distance(line_end, self.AP2) <= 3):
                        for seg_start, seg_end in a1_segments:
                            if self.line_segments_intersect(seg_start, seg_end, line_start, line_end):
                                return entity
        return None

    def line_segments_intersect(self, p1, p2, p3, p4):
        def ccw(A, B, C):
            return (C[1]-A[1]) * (B[0]-A[0]) > (B[1]-A[1]) * (C[0]-A[0])
        return ccw(p1, p3, p4) != ccw(p2, p3, p4) and ccw(p1, p2, p3) != ccw(p1, p2, p4)

    def find_a3_polyline(self, a2_line):
        if not a2_line:
            return None
        a2_start = (a2_line.dxf.start.x, a2_line.dxf.start.y)
        a2_end = (a2_line.dxf.end.x, a2_line.dxf.end.y)
        for entity in self.msp:
            if entity.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
                points = list(entity.points())
                if len(points) == 3:
                    for point in points:
                        point_tuple = (point[0], point[1])
                        if (self.calculate_distance(point_tuple, a2_start) < 0.1 or
                            self.calculate_distance(point_tuple, a2_end) < 0.1):
                            return entity
        return None

    def rotate_line_around_point(self, line_entity, center_point, angle_rad):
        start = (line_entity.dxf.start.x, line_entity.dxf.start.y)
        end = (line_entity.dxf.end.x, line_entity.dxf.end.y)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)
        dx_start = start[0] - center_point[0]
        dy_start = start[1] - center_point[1]
        new_start_x = center_point[0] + dx_start * cos_a - dy_start * sin_a
        new_start_y = center_point[1] + dx_start * sin_a + dy_start * cos_a
        dx_end = end[0] - center_point[0]
        dy_end = end[1] - center_point[1]
        new_end_x = center_point[0] + dx_end * cos_a - dy_end * sin_a
        new_end_y = center_point[1] + dx_end * sin_a + dy_end * cos_a
        line_entity.dxf.start = (new_start_x, new_start_y, line_entity.dxf.start.z)
        line_entity.dxf.end = (new_end_x, new_end_y, line_entity.dxf.end.z)

    def rotate_polyline_around_point(self, polyline_entity, center_point, angle_rad):
        if polyline_entity.dxftype() == 'LWPOLYLINE':
            old_points = list(polyline_entity.get_points())
            new_points = []
            cos_a = math.cos(angle_rad)
            sin_a = math.sin(angle_rad)
            for x, y, *rest in old_points:
                dx = x - center_point[0]
                dy = y - center_point[1]
                new_x = center_point[0] + dx * cos_a - dy * sin_a
                new_y = center_point[1] + dx * sin_a + dy * cos_a
                new_points.append((new_x, new_y, *rest))
            polyline_entity.set_points(new_points)
        elif polyline_entity.dxftype() == 'POLYLINE':
            cos_a = math.cos(angle_rad)
            sin_a = math.sin(angle_rad)
            for vertex in polyline_entity.vertices:
                dx = vertex.dxf.location.x - center_point[0]
                dy = vertex.dxf.location.y - center_point[1]
                new_x = center_point[0] + dx * cos_a - dy * sin_a
                new_y = center_point[1] + dx * sin_a + dy * cos_a
                vertex.dxf.location = (new_x, new_y, vertex.dxf.location.z)

    def calculate_rotation_angle_for_intersection(self, ap1, ap2, a2_line):
        a2_start = (a2_line.dxf.start.x, a2_line.dxf.start.y)
        a2_end = (a2_line.dxf.end.x, a2_line.dxf.end.y)
        dist_to_start = self.calculate_distance(ap2, a2_start)
        dist_to_end = self.calculate_distance(ap2, a2_end)
        if dist_to_start < dist_to_end:
            other_end = a2_end
        else:
            other_end = a2_start
        a2_mid = ((ap2[0] + other_end[0]) / 2, (ap2[1] + other_end[1]) / 2)
        ag_vector = (ap2[0] - ap1[0], ap2[1] - ap1[1])
        ag_length = math.sqrt(ag_vector[0]**2 + ag_vector[1]**2)
        if ag_length == 0:
            return 0
        ag_unit = (ag_vector[0] / ag_length, ag_vector[1] / ag_length)
        ag_perpendicular = (ag_unit[1], -ag_unit[0])
        current_vector = (other_end[0] - ap2[0], other_end[1] - ap2[1])
        current_length = math.sqrt(current_vector[0]**2 + current_vector[1]**2)
        if current_length == 0:
            return 0
        current_unit = (current_vector[0] / current_length, current_vector[1] / current_length)
        dot_product = current_unit[0] * ag_perpendicular[0] + current_unit[1] * ag_perpendicular[1]
        cross_product = current_unit[0] * ag_perpendicular[1] - current_unit[1] * ag_perpendicular[0]
        rotation_angle = math.atan2(cross_product, dot_product)
        cos_r = math.cos(rotation_angle)
        sin_r = math.sin(rotation_angle)
        rotated_x = ap2[0] + (other_end[0] - ap2[0]) * cos_r - (other_end[1] - ap2[1]) * sin_r
        rotated_y = ap2[1] + (other_end[0] - ap2[0]) * sin_r + (other_end[1] - ap2[1]) * cos_r
        rotated_mid = ((ap2[0] + rotated_x) / 2, (ap2[1] + rotated_y) / 2)
        ap1_to_mid = (rotated_mid[0] - ap1[0], rotated_mid[1] - ap1[1])
        projection = (ap1_to_mid[0] * ag_unit[0] + ap1_to_mid[1] * ag_unit[1])
        projected_point = (ap1[0] + projection * ag_unit[0], ap1[1] + projection * ag_unit[1])
        distance_to_line = self.calculate_distance(rotated_mid, projected_point)
        if distance_to_line > 1.0:
            rotation_angle += math.pi
        while rotation_angle > math.pi:
            rotation_angle -= 2 * math.pi
        while rotation_angle < -math.pi:
            rotation_angle += 2 * math.pi
        return rotation_angle

    def point_to_line_distance(self, point, line_start, line_end):
        line_vec = (line_end[0] - line_start[0], line_end[1] - line_start[1])
        point_vec = (point[0] - line_start[0], point[1] - line_start[1])
        line_len_sq = line_vec[0]**2 + line_vec[1]**2
        if line_len_sq == 0:
            return self.calculate_distance(point, line_start)
        t = max(0, min(1, (point_vec[0]*line_vec[0] + point_vec[1]*line_vec[1]) / line_len_sq))
        projection = (line_start[0] + t * line_vec[0], line_start[1] + t * line_vec[1])
        return self.calculate_distance(point, projection)

    def find_a1_polyline_from_cont(self, cont_entities):
        cont_bbox = self.get_bounding_box(cont_entities)
        found_A1 = None
        candidates = []
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
                            min_dist_to_box = float('inf')
                            for poly_point in points:
                                poly_pt = (poly_point[0], poly_point[1])
                                for corner in cont_bbox:
                                    dist = self.calculate_distance(poly_pt, corner)
                                    if dist < min_dist_to_box:
                                        min_dist_to_box = dist
                            if min_dist_to_box <= 7.5:
                                candidates.append({
                                    'entity': entity,
                                    'distance': min_dist_to_box,
                                    'layer': layer,
                                    'points': point_count,
                                    'type': entity_type,
                                    'length': poly_length
                                })
                except Exception:
                    pass
        if candidates:
            candidates.sort(key=lambda x: x['distance'])
            best_candidate = candidates[0]
            found_A1 = best_candidate['entity']
        if found_A1:
            cont_center = (
                (cont_bbox[0][0] + cont_bbox[2][0]) / 2,
                (cont_bbox[0][1] + cont_bbox[2][1]) / 2
            )
            a1_points = list(found_A1.points())
            self.near_point = None
            self.far_point = None
            min_d = float('inf')
            max_d = 0
            for pt in a1_points:
                pt_tuple = (pt[0], pt[1])
                d = self.calculate_distance(pt_tuple, cont_center)
                if d < min_d:
                    min_d = d
                    self.near_point = pt_tuple
                if d > max_d:
                    max_d = d
                    self.far_point = pt_tuple
        return found_A1

    def process_dxf_file(self, file_path):
        try:
            self.AP1 = None
            self.AP2 = None
            self.AP3 = None
            self.original_AP1 = None
            self.doc = ezdxf.readfile(file_path)
            self.msp = self.doc.modelspace()
            con_texts = self.find_con_texts()
            a1_count = 0
            for con in con_texts:
                self.set_entity_color(con, 4)
                texts_below = self.find_texts_below_con(con)
                cont_entities = [con]
                for text in texts_below:
                    self.set_entity_color(text, 4)
                    cont_entities.append(text)
                last_text = texts_below[-1] if texts_below else con
                epos, npos, elev = self.find_position_texts_below(last_text)
                apos_entities = []
                missing_apos = []
                if epos:
                    self.set_entity_color(epos, 4)
                    apos_entities.append(epos)
                else:
                    missing_apos.append("EPOS")
                if npos:
                    self.set_entity_color(npos, 4)
                    apos_entities.append(npos)
                else:
                    missing_apos.append("NPOS")
                if elev:
                    self.set_entity_color(elev, 4)
                    apos_entities.append(elev)
                else:
                    missing_apos.append("ELEV")
                if not apos_entities and not cont_entities:
                    continue
                if missing_apos:
                    continue
                alltxt_entities = cont_entities + apos_entities
                self.AP1 = None
                self.AP2 = None
                self.AP3 = None
                self.original_AP1 = None
                a1_polyline = self.find_a1_polyline_from_cont(cont_entities)
                if a1_polyline:
                    if self.process_single_a1(a1_polyline, alltxt_entities, apos_entities, cont_entities, 0):
                        a1_count += 1
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            output_path = os.path.join(
                os.path.dirname(file_path),
                f"{base_name}_CONT.dxf"
            )
            self.doc.saveas(output_path)
        except Exception:
            pass

    def process_single_a1(self, a1_polyline, alltxt_entities, apos_entities, cont_entities, group_number):
        a1_points = list(a1_polyline.points())
        if len(a1_points) == 3:
            return False
        a1_length = self.calculate_polyline_length(a1_polyline)
        if a1_length <= 10:
            return False
        movement_result = self.find_target_position_and_move_entities(a1_polyline, alltxt_entities, apos_entities, cont_entities)
        if movement_result:
            dx, dy = movement_result
            if dx != 0 or dy != 0:
                if hasattr(self, 'AP1') and hasattr(self, 'AP2') and hasattr(self, 'original_AP1'):
                    ag_start = self.AP1
                    white_line = self.msp.add_line(
                        start=(ag_start[0], ag_start[1], 0),
                        end=(self.AP2[0], self.AP2[1], 0)
                    )
                    white_line.dxf.layer = 'AG'
                    white_line.dxf.color = 7
                    a2_line = self.find_a2_arrow_line_with_points(a1_points)
                    if a2_line:
                        a3_polyline = self.find_a3_polyline(a2_line)
                        try:
                            self.msp.delete_entity(a2_line)
                        except Exception:
                            pass
                        if a3_polyline:
                            try:
                                self.msp.delete_entity(a3_polyline)
                            except Exception:
                                pass
                    ag_vector = (ag_start[0] - self.AP2[0], ag_start[1] - self.AP2[1])
                    ag_length = math.sqrt(ag_vector[0]**2 + ag_vector[1]**2)
                    if ag_length > 0:
                        ag_unit = (ag_vector[0] / ag_length, ag_vector[1] / ag_length)
                        angle_plus11 = math.radians(11)
                        cos_p11 = math.cos(angle_plus11)
                        sin_p11 = math.sin(angle_plus11)
                        vec_plus11 = (
                            ag_unit[0] * cos_p11 - ag_unit[1] * sin_p11,
                            ag_unit[0] * sin_p11 + ag_unit[1] * cos_p11
                        )
                        angle_minus11 = math.radians(-11)
                        cos_m11 = math.cos(angle_minus11)
                        sin_m11 = math.sin(angle_minus11)
                        vec_minus11 = (
                            ag_unit[0] * cos_m11 - ag_unit[1] * sin_m11,
                            ag_unit[0] * sin_m11 + ag_unit[1] * cos_m11
                        )
                        line_length = 2
                        end_plus11 = (
                            self.AP2[0] + vec_plus11[0] * line_length,
                            self.AP2[1] + vec_plus11[1] * line_length
                        )
                        end_minus11 = (
                            self.AP2[0] + vec_minus11[0] * line_length,
                            self.AP2[1] + vec_minus11[1] * line_length
                        )
                        line_plus11 = self.msp.add_line(
                            start=(self.AP2[0], self.AP2[1], 0),
                            end=(end_plus11[0], end_plus11[1], 0)
                        )
                        line_plus11.dxf.layer = 'AG'
                        line_plus11.dxf.color = 4
                        line_minus11 = self.msp.add_line(
                            start=(self.AP2[0], self.AP2[1], 0),
                            end=(end_minus11[0], end_minus11[1], 0)
                        )
                        line_minus11.dxf.layer = 'AG'
                        line_minus11.dxf.color = 4
                        connecting_line = self.msp.add_line(
                            start=(end_plus11[0], end_plus11[1], 0),
                            end=(end_minus11[0], end_minus11[1], 0)
                        )
                        connecting_line.dxf.layer = 'AG'
                        connecting_line.dxf.color = 4
            else:
                pass
        return True

def main():
    # CLI: python PLTONEWLINE.PY A.DXF B.DXF ...
    file_paths = [p for p in sys.argv[1:] if p.lower().endswith(".dxf")]
    if not file_paths:
        return
    processor = DXFProcessor()
    for file_path in file_paths:
        processor.process_dxf_file(file_path)

if __name__ == "__main__":
    main()
