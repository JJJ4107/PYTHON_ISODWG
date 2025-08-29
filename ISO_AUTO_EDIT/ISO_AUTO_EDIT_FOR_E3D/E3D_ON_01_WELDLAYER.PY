import ezdxf
from ezdxf.math import Vec2
import math
import os
import numpy as np
import sys
import uuid

class PipeLayerRenamer:
    def __init__(self):
        self.doc = None
        self.msp = None
        self.pno_array = []
        self.psize_array = []
        self.pbox_entities = []
        
    def get_2d_pos(self, pos):
        if hasattr(pos, '__len__') and len(pos) > 2:
            return (pos[0], pos[1])
        return pos
    
    def has_bulge(self, entity):
        if entity.dxftype() == 'LWPOLYLINE':
            points_with_bulge = list(entity.get_points('xyb'))
            for point in points_with_bulge:
                if len(point) > 2 and point[2] != 0:
                    return True
        elif entity.dxftype() == 'POLYLINE':
            for vertex in entity.vertices:
                if hasattr(vertex.dxf, 'bulge') and vertex.dxf.bulge != 0:
                    return True
        return False
        
    def distance_2d(self, p1, p2):
        if len(p1) > 2:
            p1 = (p1[0], p1[1])
        if len(p2) > 2:
            p2 = (p2[0], p2[1])
        return math.sqrt((p2[0] - p1[0])**2 + (p2[1] - p1[1])**2)
    
    def find_text_near_point(self, point, radius, layer=None):
        if len(point) > 2:
            point = (point[0], point[1])
        texts = []
        for entity in self.msp:
            if entity.dxftype() in ['TEXT', 'MTEXT']:
                if layer and entity.dxf.layer != layer:
                    continue
                if entity.dxftype() == 'TEXT':
                    pos = entity.dxf.insert
                    if len(pos) > 2:
                        pos = (pos[0], pos[1])
                else:
                    pos = entity.dxf.insert
                    if len(pos) > 2:
                        pos = (pos[0], pos[1])
                if self.distance_2d(point, pos) <= radius:
                    texts.append(entity)
        return texts
    
    def find_angle_brackets_near_materials(self, material_type="FABRICATION"):
        angle_bracket_texts = []
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
                        materials_x = materials_pos[0]
                        break
                if materials_text:
                    break
        if not materials_x:
            return angle_bracket_texts
        search_max_x = materials_x - 15
        for entity in self.msp:
            if entity.dxftype() in ['TEXT', 'MTEXT']:
                text_content = entity.dxf.text if entity.dxftype() == 'TEXT' else entity.text
                pos = entity.dxf.insert
                if 0 <= pos[0] <= search_max_x and '<' in text_content and '>' in text_content:
                    angle_bracket_texts.append((entity, pos))
                    entity.dxf.color = 3  # GREEN
        return angle_bracket_texts
    
    def find_pt_number_near_angle_bracket(self, angle_bracket_entity, pt_numbers):
        bracket_pos = angle_bracket_entity.dxf.insert
        candidate_pts = []
        for entity in self.msp:
            if entity.dxftype() in ['TEXT', 'MTEXT']:
                text_content = entity.dxf.text if entity.dxftype() == 'TEXT' else entity.text
                content = text_content.strip()
                if content.isdigit():
                    num_value = int(content)
                    if 2 <= num_value <= 5:
                        pos = entity.dxf.insert
                        x_in_range = (bracket_pos[0] - 5) <= pos[0] <= (bracket_pos[0] + 20)
                        y_in_range = (bracket_pos[1] - 5) <= pos[1] <= (bracket_pos[1] + 20)
                        if x_in_range and y_in_range:
                            distance = self.distance_2d(bracket_pos, pos)
                            if num_value in pt_numbers:
                                slope = self.get_text_slope(entity)
                                candidate_pts.append({
                                    'pt_number': num_value,
                                    'entity': entity,
                                    'position': pos,
                                    'slope': slope,
                                    'distance': distance,
                                    'bracket_pos': bracket_pos
                                })
        candidate_pts.sort(key=lambda x: x['distance'])
        found_pts = []
        if candidate_pts:
            closest_pt = candidate_pts[0]
            closest_pt['entity'].dxf.color = 4  # CYAN
            found_pts.append(closest_pt)
        return found_pts
    
    def process_pt_based_on_slope(self, pt_info, psize_array):
        pt_number = pt_info['pt_number']
        pt_entity = pt_info['entity']
        pt_pos = pt_info['position']
        slope = pt_info['slope']
        bracket_pos = pt_info.get('bracket_pos', pt_pos)
        pt_index = None
        for idx, pno in enumerate(self.pno_array):
            if pno == pt_number:
                pt_index = idx
                break
        if pt_index is None or pt_index >= len(psize_array):
            return
        pipe_size = psize_array[pt_index]
        new_layer_name = f"PIPE_{pipe_size}"
        if slope != 0:
            pipe_entities = self.find_pipe_layer_entities_near_point(pt_pos, 3)
            if pipe_entities:
                for entity in pipe_entities:
                    if new_layer_name not in self.doc.layers:
                        self.doc.layers.new(name=new_layer_name)
                    entity.dxf.layer = new_layer_name
                    entity.dxf.color = 1  # RED
        else:
            max_attempts = 1
            pipe_found = False
            exclude_entities = []
            for _ in range(max_attempts):
                if pipe_found:
                    break
                g1_polyline = self.find_nearest_polyline_near_point(bracket_pos, 15, exclude_list=exclude_entities)
                if not g1_polyline:
                    break
                g1_entity, g1_points = g1_polyline
                exclude_entities.append(g1_entity)
                pipe_entities = self.find_pipe_layer_entities_near_polyline(g1_points, 1)
                if pipe_entities:
                    for entity in pipe_entities:
                        if new_layer_name not in self.doc.layers:
                            self.doc.layers.new(name=new_layer_name)
                        entity.dxf.layer = new_layer_name
                        entity.dxf.color = 1  # RED
                    pipe_found = True
    
    def find_nearest_polyline_near_point(self, point, radius, exclude_list=None):
        if len(point) > 2:
            point = (point[0], point[1])
        if exclude_list is None:
            exclude_list = []
        min_dist = float('inf')
        nearest_polyline = None
        for entity in self.msp:
            if entity.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
                if entity in exclude_list:
                    continue
                if self.has_bulge(entity):
                    continue
                poly_points = []
                if entity.dxftype() == 'LWPOLYLINE':
                    poly_points = [(p[0], p[1]) for p in entity.get_points('xy')]
                else:
                    for vertex in entity.vertices:
                        poly_points.append((vertex.dxf.location.x, vertex.dxf.location.y))
                if 2 <= len(poly_points) <= 3:
                    entity_min_dist = float('inf')
                    for pp in poly_points:
                        dist = self.distance_2d(point, pp)
                        if dist < entity_min_dist:
                            entity_min_dist = dist
                    if entity_min_dist <= radius and entity_min_dist < min_dist:
                        min_dist = entity_min_dist
                        nearest_polyline = (entity, poly_points)
        if nearest_polyline:
            entity, points = nearest_polyline
            entity.dxf.color = 1  # RED
        return nearest_polyline
    
    def find_multiple_polylines_near_point(self, point, radius, max_count=3):
        if len(point) > 2:
            point = (point[0], point[1])
        polyline_distances = []
        for entity in self.msp:
            if entity.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
                if self.has_bulge(entity):
                    continue
                poly_points = []
                if entity.dxftype() == 'LWPOLYLINE':
                    poly_points = [(p[0], p[1]) for p in entity.get_points('xy')]
                else:
                    for vertex in entity.vertices:
                        poly_points.append((vertex.dxf.location.x, vertex.dxf.location.y))
                if 2 <= len(poly_points) <= 3:
                    min_dist = float('inf')
                    for pp in poly_points:
                        dist = self.distance_2d(point, pp)
                        if dist < min_dist:
                            min_dist = dist
                    if min_dist <= radius:
                        polyline_distances.append((min_dist, entity, poly_points))
        polyline_distances.sort(key=lambda x: x[0])
        result = []
        for _, entity, points in polyline_distances[:max_count]:
            entity.dxf.color = 1  # RED
            result.append((entity, points))
        return result
    
    def find_headers_near_text(self, search_text, search_radius=100):
        headers = {'PT': None, 'ITEM': None, 'MATERIAL': None, 'SIZE': None}
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
        if len(base_pos) > 2:
            base_pos = (base_pos[0], base_pos[1])
        for entity in self.msp:
            if entity.dxftype() in ['TEXT', 'MTEXT']:
                text_content = entity.dxf.text if entity.dxftype() == 'TEXT' else entity.text
                pos = entity.dxf.insert
                if len(pos) > 2:
                    pos = (pos[0], pos[1])
                if self.distance_2d(base_pos, pos) <= search_radius:
                    for header in headers:
                        if header in text_content.upper():
                            headers[header] = entity
                            entity.dxf.color = 1  # RED
        return headers
    
    def find_pipe_items_in_area(self, base_text, y_offset=-50, x_min=-10, x_max=80):
        pipe_items = []
        if not base_text:
            return pipe_items
        base_pos = base_text.dxf.insert
        for entity in self.msp:
            if entity.dxftype() in ['TEXT', 'MTEXT']:
                text_content = entity.dxf.text if entity.dxftype() == 'TEXT' else entity.text
                pos = entity.dxf.insert
                y_in_range = (base_pos[1] + y_offset) <= pos[1] <= base_pos[1]
                x_in_range = (base_pos[0] + x_min) <= pos[0] <= (base_pos[0] + x_max)
                if y_in_range and x_in_range and 'PIPE' in text_content.upper():
                    pipe_items.append(entity)
        pipe_items.sort(key=lambda e: e.dxf.insert[1], reverse=True)
        return pipe_items
    
    def extract_pipe_info_from_pipe_text(self, pipe_entity):
        pipe_text = pipe_entity.dxf.text if pipe_entity.dxftype() == 'TEXT' else pipe_entity.text
        pipe_pos = pipe_entity.dxf.insert
        pt_value = None
        size_value = None
        y_tolerance = 1.0
        nearby_texts = []
        for entity in self.msp:
            if entity.dxftype() in ['TEXT', 'MTEXT']:
                if entity == pipe_entity:
                    continue
                pos = entity.dxf.insert
                if abs(pos[1] - pipe_pos[1]) <= y_tolerance:
                    text_content = entity.dxf.text if entity.dxftype() == 'TEXT' else entity.text
                    nearby_texts.append((pos[0], text_content.strip(), entity, pos[1]))
        nearby_texts.sort(key=lambda x: x[0])
        left_numbers = [(x, text, entity) for x, text, entity, _ in nearby_texts 
                        if x < pipe_pos[0] and text.isdigit()]
        if left_numbers:
            left_numbers.sort(key=lambda item: pipe_pos[0] - item[0])
            pt_value = int(left_numbers[0][1])
            left_numbers[0][2].dxf.color = 1  # RED
        right_numbers = [(x, text, entity) for x, text, entity, _ in nearby_texts 
                         if x > pipe_pos[0] and text.isdigit()]
        if right_numbers:
            right_numbers.sort(key=lambda item: item[0] - pipe_pos[0])
            size_value = int(right_numbers[0][1])
            right_numbers[0][2].dxf.color = 1  # RED
        return pt_value, size_value
    
    def extract_pipe_info(self, pipe_entity, pt_x, size_x):
        pipe_pos = pipe_entity.dxf.insert
        if len(pipe_pos) > 2:
            pipe_pos = (pipe_pos[0], pipe_pos[1])
        pipe_y = pipe_pos[1]
        pt_texts = self.find_text_near_point((pt_x, pipe_y), 20)
        pt_value = None
        for text in pt_texts:
            content = text.dxf.text if text.dxftype() == 'TEXT' else text.text
            if content.strip().isdigit():
                pt_value = int(content.strip())
                break
        size_texts = self.find_text_near_point((size_x, pipe_y), 20)
        size_value = None
        for text in size_texts:
            content = text.dxf.text if text.dxftype() == 'TEXT' else text.text
            if content.strip().isdigit():
                size_value = int(content.strip())
                break
        return pt_value, size_value
    
    def find_polylines_with_5_points(self):
        pbox_list = []
        for entity in self.msp:
            if entity.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
                points = []
                if entity.dxftype() == 'LWPOLYLINE':
                    points = [(p[0], p[1]) for p in entity.get_points('xy')]
                else:
                    for vertex in entity.vertices:
                        points.append((vertex.dxf.location.x, vertex.dxf.location.y))
                if len(points) == 5:
                    total_dist = 0
                    for i in range(4):
                        total_dist += self.distance_2d(points[i], points[i+1])
                    if 13.5 <= total_dist <= 14.5:
                        pbox_list.append((entity, points))
                        entity.dxf.color = 1  # RED
        return pbox_list
    
    def find_nearest_pno(self, pbox_center):
        if len(pbox_center) > 2:
            pbox_center = (pbox_center[0], pbox_center[1])
        if len(self.pno_array) < 2:
            return None, None
        min_dist = float('inf')
        nearest_idx = None
        dpno_entity = None
        for i in range(len(self.pno_array)):
            pno = self.pno_array[i]
            if pno == 1:
                continue
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
        return nearest_idx, dpno_entity
    
    def get_text_slope(self, text_entity):
        if text_entity.dxftype() == 'TEXT':
            rotation = text_entity.dxf.rotation
        else:
            rotation = text_entity.dxf.rotation if hasattr(text_entity.dxf, 'rotation') else 0
        return rotation
    
    def find_multiple_polylines_near_pbox(self, pbox_center, radius, max_count=3):
        if len(pbox_center) > 2:
            pbox_center = (pbox_center[0], pbox_center[1])
        polyline_distances = []
        for entity in self.msp:
            if entity.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
                if self.has_bulge(entity):
                    continue
                poly_points = []
                if entity.dxftype() == 'LWPOLYLINE':
                    poly_points = [(p[0], p[1]) for p in entity.get_points('xy')]
                else:
                    for vertex in entity.vertices:
                        poly_points.append((vertex.dxf.location.x, vertex.dxf.location.y))
                if 2 <= len(poly_points) <= 3:
                    min_dist = float('inf')
                    for pp in poly_points:
                        dist = self.distance_2d(pbox_center, pp)
                        if dist < min_dist:
                            min_dist = dist
                    if min_dist <= radius:
                        polyline_distances.append((min_dist, entity, poly_points))
        polyline_distances.sort(key=lambda x: x[0])
        result = []
        for _, entity, points in polyline_distances[:max_count]:
            entity.dxf.color = 1  # RED
            result.append((entity, points))
        return result
    
    def find_pipe_layer_entities_near_polyline(self, polyline_points, radius=1):
        found_entities = set()
        for point in polyline_points:
            if len(point) > 2:
                point = (point[0], point[1])
            for entity in self.msp:
                if entity.dxf.layer == 'PIPE':
                    found = False
                    if hasattr(entity, 'dxf') and hasattr(entity.dxf, 'insert'):
                        if self.distance_2d(point, entity.dxf.insert) <= radius:
                            found = True
                    elif hasattr(entity, 'dxf') and hasattr(entity.dxf, 'start'):
                        if self.distance_2d(point, entity.dxf.start) <= radius:
                            found = True
                    if entity.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
                        if entity.dxftype() == 'LWPOLYLINE':
                            pipe_points = [(p[0], p[1]) for p in entity.get_points('xy')]
                        else:
                            pipe_points = []
                            for vertex in entity.vertices:
                                pipe_points.append((vertex.dxf.location.x, vertex.dxf.location.y))
                        for pp in pipe_points:
                            if self.distance_2d(point, pp) <= radius:
                                found = True
                                break
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
        max_dist = 0
        farthest_point = None
        for point in g1_points:
            if len(point) > 2:
                point = (point[0], point[1])
            dist = self.distance_2d(point, pbox_center)
            if dist > max_dist:
                max_dist = dist
                farthest_point = point
        return farthest_point
    
    def find_pipe_layer_entities_near_point(self, point, radius=1):
        if len(point) > 2:
            point = (point[0], point[1])
        pipe_entities = []
        found_entities_set = set()
        for entity in self.msp:
            if entity.dxf.layer == 'PIPE':
                found = False
                if hasattr(entity, 'dxf') and hasattr(entity.dxf, 'insert'):
                    if self.distance_2d(point, entity.dxf.insert) <= radius:
                        found = True
                elif hasattr(entity, 'dxf') and hasattr(entity.dxf, 'start'):
                    if self.distance_2d(point, entity.dxf.start) <= radius:
                        found = True
                if entity.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
                    if entity.dxftype() == 'LWPOLYLINE':
                        poly_points = [(p[0], p[1]) for p in entity.get_points('xy')]
                    else:
                        poly_points = []
                        for vertex in entity.vertices:
                            poly_points.append((vertex.dxf.location.x, vertex.dxf.location.y))
                    for pp in poly_points:
                        if self.distance_2d(point, pp) <= radius:
                            found = True
                            break
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
    
    def find_pipe_layer_polylines_near_points(self, points, radius=3):
        found_entities = []
        for point in points:
            if len(point) > 2:
                point = (point[0], point[1])
            min_dist = float('inf')
            closest_entity = None
            for entity in self.msp:
                if entity.dxf.layer == 'PIPE' and entity.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
                    if entity.dxftype() == 'LWPOLYLINE':
                        poly_points = [(p[0], p[1]) for p in entity.get_points('xy')]
                    else:
                        poly_points = []
                        for vertex in entity.vertices:
                            poly_points.append((vertex.dxf.location.x, vertex.dxf.location.y))
                    for i in range(len(poly_points) - 1):
                        p1 = poly_points[i]
                        p2 = poly_points[i + 1]
                        dist = self.point_to_line_distance(point, p1, p2)
                        if dist <= radius and dist < min_dist:
                            min_dist = dist
                            closest_entity = entity
            if closest_entity:
                found_entities.append(closest_entity)
        return found_entities
    
    def point_to_line_distance(self, point, line_start, line_end):
        if len(point) > 2:
            point = (point[0], point[1])
        if len(line_start) > 2:
            line_start = (line_start[0], line_start[1])
        if len(line_end) > 2:
            line_end = (line_end[0], line_end[1])
        x0, y0 = point
        x1, y1 = line_start
        x2, y2 = line_end
        line_length_sq = (x2 - x1)**2 + (y2 - y1)**2
        if line_length_sq == 0:
            return self.distance_2d(point, line_start)
        t = max(0, min(1, ((x0 - x1) * (x2 - x1) + (y0 - y1) * (y2 - y1)) / line_length_sq))
        projection = (x1 + t * (x2 - x1), y1 + t * (y2 - y1))
        return self.distance_2d(point, projection)
    
    def find_pipe_layer_polylines(self):
        pipe_polylines = []
        for entity in self.msp:
            if entity.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
                if 'PIPE' in entity.dxf.layer.upper():
                    if entity.dxftype() == 'LWPOLYLINE':
                        points = [(p[0], p[1]) for p in entity.get_points('xy')]
                    else:
                        points = []
                        for vertex in entity.vertices:
                            points.append((vertex.dxf.location.x, vertex.dxf.location.y))
                    if len(points) == 2:
                        pipe_polylines.append((entity, points))
        return pipe_polylines
    
    def find_3way_intersections(self, pipe_polylines):
        intersections = []
        tolerance = 0.3
        all_endpoints = []
        for entity, points in pipe_polylines:
            for point in points:
                all_endpoints.append((point, entity))
        for i, (point1, entity1) in enumerate(all_endpoints):
            nearby_entities = set()
            nearby_entities.add(entity1)
            for j, (point2, entity2) in enumerate(all_endpoints):
                if i != j and self.distance_2d(point1, point2) <= tolerance:
                    nearby_entities.add(entity2)
            if len(nearby_entities) == 3:
                is_duplicate = False
                for existing_intersection, _ in intersections:
                    if self.distance_2d(point1, existing_intersection) <= tolerance:
                        is_duplicate = True
                        break
                if not is_duplicate:
                    intersections.append((point1, list(nearby_entities)))
        return intersections
    
    def get_polyline_length(self, entity):
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
        for entity in self.msp:
            if entity.dxftype() in ['POLYLINE', 'LWPOLYLINE'] and entity.dxf.layer == 'PL2':
                if entity.dxftype() == 'LWPOLYLINE':
                    points = [(p[0], p[1]) for p in entity.get_points('xy')]
                else:
                    points = []
                    for vertex in entity.vertices:
                        points.append((vertex.dxf.location.x, vertex.dxf.location.y))
                for p in points:
                    if self.distance_2d(point, p) <= radius:
                        return entity, points
        return None, None
    
    def find_x_text_near_point(self, point, radius=20):
        for entity in self.msp:
            if entity.dxftype() in ['TEXT', 'MTEXT']:
                text_content = entity.dxf.text if entity.dxftype() == 'TEXT' else entity.text
                pos = entity.dxf.insert
                if len(pos) > 2:
                    pos = (pos[0], pos[1])
                if self.distance_2d(point, pos) <= radius and 'x' in text_content.lower():
                    return entity, text_content
        return None, None
    
    def extract_numbers_from_x_text(self, text):
        text = text.lower()
        if 'x' not in text:
            return None, None
        parts = text.split('x')
        if len(parts) != 2:
            return None, None
        t1 = None
        for char in parts[0][::-1]:
            if char.isdigit():
                if t1 is None:
                    t1 = char
                else:
                    t1 = char + t1
            elif t1 is not None:
                break
        t3 = None
        for char in parts[1]:
            if char.isdigit():
                if t3 is None:
                    t3 = char
                else:
                    t3 = t3 + char
            elif t3 is not None:
                break
        t1 = int(t1) if t1 else None
        t3 = int(t3) if t3 else None
        return t1, t3
    
    def process_tee_connections(self):
        pipe_polylines = self.find_pipe_layer_polylines()
        if not pipe_polylines:
            return
        intersections = self.find_3way_intersections(pipe_polylines)
        for _, tee_entities in intersections:
            tee_lengths = []
            for entity in tee_entities:
                length = self.get_polyline_length(entity)
                tee_lengths.append((entity, length))
            tee_lengths.sort(key=lambda x: x[1], reverse=True)
            if len(tee_lengths) < 3:
                continue
            tee1_entity = tee_lengths[0][0]
            tee2_entity = tee_lengths[1][0]
            tee3_entity = tee_lengths[2][0]
            sample_points = []
            for e in [tee1_entity, tee2_entity, tee3_entity]:
                if e.dxftype() == 'LWPOLYLINE':
                    pts = [(p[0], p[1]) for p in e.get_points('xy')]
                else:
                    pts = []
                    for v in e.vertices:
                        pts.append((v.dxf.location.x, v.dxf.location.y))
                if pts:
                    sample_points.append(pts[0])
            g1_entity = None
            g1_points = None
            for sp in sample_points:
                g1_entity, g1_points = self.find_pl2_polyline_near_point(sp, 0.5)
                if g1_entity:
                    break
            if not g1_entity or not g1_points or len(g1_points) < 2:
                continue
            dist1 = self.distance_2d(sample_points[0], g1_points[0])
            dist2 = self.distance_2d(sample_points[0], g1_points[-1])
            far_point = g1_points[0] if dist1 > dist2 else g1_points[-1]
            x_entity, x_text = self.find_x_text_near_point(far_point, 20)
            if not x_entity:
                continue
            t1, t3 = self.extract_numbers_from_x_text(x_text)
            if t1 is None or t3 is None:
                continue
            new_layer_tee1 = f"TEE_{t1}"
            new_layer_tee2 = f"TEE_{t1}"
            new_layer_tee3 = f"TEE_{t3}"
            if new_layer_tee1 not in self.doc.layers:
                self.doc.layers.new(name=new_layer_tee1)
            if new_layer_tee3 not in self.doc.layers:
                self.doc.layers.new(name=new_layer_tee3)
            tee1_entity.dxf.layer = new_layer_tee1
            tee1_entity.dxf.color = 2  # YELLOW
            tee2_entity.dxf.layer = new_layer_tee2
            tee2_entity.dxf.color = 2  # YELLOW
            tee3_entity.dxf.layer = new_layer_tee3
            tee3_entity.dxf.color = 2  # YELLOW
    
    def reset_state(self):
        self.doc = None
        self.msp = None
        self.pno_array = []
        self.psize_array = []
        self.pbox_entities = []

    # ---------- 추가: 항상 저장되도록 보조 유틸 ----------
    def _preferred_output_path(self, filename):
        base = os.path.splitext(os.path.basename(filename))[0] or "OUTPUT"
        out_dir = os.path.dirname(filename)
        if not out_dir or not os.path.isdir(out_dir):
            out_dir = os.getcwd()
        return os.path.join(out_dir, f"{base}_WDLA.dxf")

    def _safe_save(self, doc, preferred_path):
        # 1차: 선호 경로 저장 시도
        try:
            doc.saveas(preferred_path)
            return preferred_path
        except Exception:
            pass
        # 2차: 현재 작업폴더로 동일 파일명 저장 시도
        try:
            alt_path = os.path.join(os.getcwd(), os.path.basename(preferred_path))
            doc.saveas(alt_path)
            return alt_path
        except Exception:
            pass
        # 3차: 현재 작업폴더에 고유 이름으로 재시도
        try:
            base, ext = os.path.splitext(os.path.basename(preferred_path))
            unique_path = os.path.join(os.getcwd(), f"{base}_{uuid.uuid4().hex[:8]}{ext or '.dxf'}")
            doc.saveas(unique_path)
            return unique_path
        except Exception:
            # 마지막 보호: 시스템이 쓰기를 전혀 허용하지 않는 극단적인 경우
            # ezdxf가 던지는 예외를 더 넘기지 않고 그냥 실패를 무시 (요청: 어떤 경우에도 진행)
            return None
    # ----------------------------------------------------

    def process_dxf(self, filename):
        """DXF 파일 처리: 실패하더라도 결과 파일을 무조건 생성"""
        # 결과 경로 먼저 계산
        output_filename = self._preferred_output_path(filename)

        # 정상 처리 시도
        try:
            self.reset_state()
            self.doc = ezdxf.readfile(filename)
            self.msp = self.doc.modelspace()

            fab_text = None
            for entity in self.msp:
                if entity.dxftype() in ['TEXT', 'MTEXT']:
                    text_content = entity.dxf.text if entity.dxftype() == 'TEXT' else entity.text
                    if 'FABRICATION MATERIALS' in text_content:
                        fab_text = entity
                        break
            if fab_text:
                pipe_items = self.find_pipe_items_in_area(fab_text, y_offset=-50, x_min=-10, x_max=80)
                for pipe in pipe_items:
                    pt, size = self.extract_pipe_info_from_pipe_text(pipe)
                    if pt is not None and size is not None:
                        self.pno_array.append(pt)
                        self.psize_array.append(size)

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
                erec_text = erec_candidates[0][0]
            if erec_text:
                pipe_items = self.find_pipe_items_in_area(erec_text, y_offset=-50, x_min=-10, x_max=80)
                for pipe in pipe_items:
                    pt, size = self.extract_pipe_info_from_pipe_text(pipe)
                    if pt is not None and size is not None:
                        self.pno_array.append(pt)
                        self.psize_array.append(size)

            fab_angle_brackets = self.find_angle_brackets_near_materials("FABRICATION")
            if fab_angle_brackets:
                for bracket_entity, bracket_pos in fab_angle_brackets:
                    found_pts = self.find_pt_number_near_angle_bracket(bracket_entity, self.pno_array)
                    if not found_pts:
                        continue
                    for pt_info in found_pts:
                        if pt_info['pt_number'] == 1:
                            continue
                        self.process_pt_based_on_slope(pt_info, self.psize_array)

            erec_angle_brackets = self.find_angle_brackets_near_materials("ERECTION")
            if erec_angle_brackets:
                for bracket_entity, bracket_pos in erec_angle_brackets:
                    found_pts = self.find_pt_number_near_angle_bracket(bracket_entity, self.pno_array)
                    if not found_pts:
                        continue
                    for pt_info in found_pts:
                        if pt_info['pt_number'] == 1:
                            continue
                        self.process_pt_based_on_slope(pt_info, self.psize_array)

            self.process_tee_connections()

            saved = self._safe_save(self.doc, output_filename)
            if saved:
                return True, saved
            else:
                # 매우 드문 경우: 저장 실패 시에도 마지막으로 빈 문서로 재시도
                blank = ezdxf.new("R2010")
                saved2 = self._safe_save(blank, output_filename)
                return (saved2 is not None), saved2

        except Exception:
            # 읽기 실패/처리 실패 시에도 무조건 결과 파일 생성 (빈 도면)
            try:
                blank = ezdxf.new("R2010")
                msp = blank.modelspace()
                # 최소한의 흔적(레이어)을 남겨도 무방하지만, 요구사항상 메시지/출력 없이 저장만 보장
                saved = self._safe_save(blank, output_filename)
                return (saved is not None), saved
            except Exception:
                # 저장 경로 문제 등으로 또 실패 시: 현재 폴더에 고유 파일명으로 재시도
                try:
                    blank2 = ezdxf.new("R2010")
                    base = os.path.splitext(os.path.basename(output_filename))[0]
                    unique = os.path.join(os.getcwd(), f"{base}_{uuid.uuid4().hex[:8]}.dxf")
                    blank2.saveas(unique)
                    return True, unique
                except Exception:
                    # 시스템이 쓰기 금지인 극단 상황: 조용히 종료(요구: 메시지 없이)
                    return False, None

def main():
    # 예: python E3D_ON_01_WELDLAYER.py A.DXF B.DXF ...
    # 확장자 대소문자 무관하게 .dxf만 처리
    args = sys.argv[1:]
    filenames = [p for p in args if p.lower().endswith(".dxf")]

    # 인자가 없더라도 아무 것도 출력하지 않음 (요구사항: print 제거)
    processor = PipeLayerRenamer()

    # 하나도 주어지지 않은 경우에도 아무 출력 없이 종료
    if not filenames:
        return

    for filename in filenames:
        # 존재 여부와 무관하게 process_dxf가 항상 결과 파일을 만들도록 설계됨
        processor.process_dxf(filename)

if __name__ == "__main__":
    main()
