import ezdxf
import os
import sys
import glob
import math
from ezdxf.math import Vec2

# TextBoxLineFinder 클래스
class TextBoxLineFinder:
    """TEXT를 BOX화하여 가장 가까운 LINE을 찾는 유틸리티 클래스"""

    def __init__(self):
        pass

    @staticmethod
    def get_text_position(text):
        try:
            if hasattr(text.dxf, "insert"):
                ins = text.dxf.insert
                if hasattr(ins, '__getitem__'):
                    return Vec2(float(ins[0]), float(ins[1]))
                elif hasattr(ins, 'x') and hasattr(ins, 'y'):
                    return Vec2(float(ins.x), float(ins.y))
                else:
                    return Vec2(float(ins), 0)
            if hasattr(text.dxf, "location"):
                loc = text.dxf.location
                if hasattr(loc, '__getitem__') and len(loc) >= 2:
                    return Vec2(float(loc[0]), float(loc[1]))
                elif hasattr(loc, 'x') and hasattr(loc, 'y'):
                    return Vec2(float(loc.x), float(loc.y))
        except Exception:
            pass
        return Vec2(0.0, 0.0)

    @staticmethod
    def get_text_bbox(text, box_height_offset=0.3):
        pos = TextBoxLineFinder.get_text_position(text)
        height = getattr(text.dxf, 'height', 2.2)
        text_len = len(text.dxf.text) * height * 0.8
        rotation = getattr(text.dxf, 'rotation', 0)
        return {
            'min_x': pos.x,
            'max_x': pos.x + text_len,
            'min_y': pos.y - box_height_offset/2,
            'max_y': pos.y + height + box_height_offset/2,
            'rotation': rotation,
            'pos': pos
        }

    @staticmethod
    def get_text_reference_points(text, num_points=3):
        bbox = TextBoxLineFinder.get_text_bbox(text)
        pos = bbox['pos']
        if num_points == 3:
            left_point = pos
            center_point = Vec2((bbox['min_x'] + bbox['max_x']) / 2, pos.y)
            right_point = Vec2(bbox['max_x'], pos.y)
            return [left_point, center_point, right_point]
        else:
            points = []
            for i in range(num_points):
                ratio = i / (num_points - 1) if num_points > 1 else 0
                x = bbox['min_x'] + (bbox['max_x'] - bbox['min_x']) * ratio
                points.append(Vec2(x, pos.y))
            return points

    @staticmethod
    def distance(p1, p2):
        return math.hypot(p2.x - p1.x, p2.y - p1.y)

    @staticmethod
    def get_line_length(line):
        if line.dxftype() == "LINE":
            start = Vec2(line.dxf.start.x, line.dxf.start.y)
            end = Vec2(line.dxf.end.x, line.dxf.end.y)
            return TextBoxLineFinder.distance(start, end)
        return 0

    @staticmethod
    def find_closest_line_to_text(text, lines, exclude_layers=None, min_length=None, debug=False):
        if exclude_layers is None:
            exclude_layers = []
        exclude_layers_upper = [layer.upper() for layer in exclude_layers]
        ref_points = TextBoxLineFinder.get_text_reference_points(text)
        found_line = None
        closest_point = None
        farthest_point = None
        min_dist = float("inf")
        for line in lines:
            if line.dxftype() != 'LINE':
                continue
            if line.dxf.layer.upper() in exclude_layers_upper:
                continue
            if min_length is not None:
                line_len = TextBoxLineFinder.get_line_length(line)
                if line_len < min_length:
                    continue
            start = Vec2(line.dxf.start.x, line.dxf.start.y)
            end = Vec2(line.dxf.end.x, line.dxf.end.y)
            distances = []
            for ref_point in ref_points:
                distances.append(TextBoxLineFinder.distance(start, ref_point))
                distances.append(TextBoxLineFinder.distance(end, ref_point))
            min_pt_dist = min(distances)
            if min_pt_dist < min_dist:
                min_dist = min_pt_dist
                found_line = line
                min_idx = distances.index(min_pt_dist)
                if min_idx % 2 == 0:
                    closest_point = start
                    farthest_point = end
                else:
                    closest_point = end
                    farthest_point = start
        return found_line, closest_point, farthest_point

    @staticmethod
    def find_closest_line_to_group(entities, lines, exclude_entities=None, exclude_layers=None, min_length=None, debug=False):
        if exclude_entities is None:
            exclude_entities = []
        if exclude_layers is None:
            exclude_layers = []
        min_x = float('inf'); max_x = float('-inf')
        min_y = float('inf'); max_y = float('-inf')
        for ent in entities:
            if ent.dxftype() == "TEXT":
                bbox = TextBoxLineFinder.get_text_bbox(ent)
                min_x = min(min_x, bbox['min_x'])
                max_x = max(max_x, bbox['max_x'])
                min_y = min(min_y, bbox['min_y'])
                max_y = max(max_y, bbox['max_y'])
            elif ent.dxftype() == "LINE":
                start = Vec2(ent.dxf.start.x, ent.dxf.start.y)
                end = Vec2(ent.dxf.end.x, ent.dxf.end.y)
                min_x = min(min_x, start.x, end.x)
                max_x = max(max_x, start.x, end.x)
                min_y = min(min_y, start.y, end.y)
                max_y = max(max_y, start.y, end.y)
        ref_points = [
            Vec2(min_x, min_y),
            Vec2(max_x, min_y),
            Vec2(max_x, max_y),
            Vec2(min_x, max_y),
            Vec2((min_x + max_x) / 2, min_y),
            Vec2(max_x, (min_y + max_y) / 2),
            Vec2((min_x + max_x) / 2, max_y),
            Vec2(min_x, (min_y + max_y) / 2),
            Vec2((min_x + max_x) / 2, (min_y + max_y) / 2)
        ]
        exclude_layers_upper = [layer.upper() for layer in exclude_layers]
        found_line = None
        closest_point = None
        farthest_point = None
        min_dist = float("inf")
        for line in lines:
            if line in exclude_entities:
                continue
            if line.dxftype() != 'LINE':
                continue
            if line.dxf.layer.upper() in exclude_layers_upper:
                continue
            if min_length is not None:
                line_len = TextBoxLineFinder.get_line_length(line)
                if line_len < min_length:
                    continue
            start = Vec2(line.dxf.start.x, line.dxf.start.y)
            end = Vec2(line.dxf.end.x, line.dxf.end.y)
            distances = []
            for ref_point in ref_points:
                distances.append(TextBoxLineFinder.distance(start, ref_point))
                distances.append(TextBoxLineFinder.distance(end, ref_point))
            min_pt_dist = min(distances)
            if min_pt_dist < min_dist:
                min_dist = min_pt_dist
                found_line = line
                min_idx = distances.index(min_pt_dist)
                if min_idx % 2 == 0:
                    closest_point = start
                    farthest_point = end
                else:
                    closest_point = end
                    farthest_point = start
        return found_line, closest_point, farthest_point

def distance(p1, p2):
    return math.hypot(p2.x - p1.x, p2.y - p1.y)

def set_entity_color(entity, color=1):
    try:
        if entity and hasattr(entity, "dxf") and hasattr(entity.dxf, "color"):
            entity.dxf.color = color
    except:
        pass

def get_line_midpoint(line):
    try:
        start = line.dxf.start
        end = line.dxf.end
        return Vec2((start.x + end.x) / 2, (start.y + end.y) / 2)
    except:
        return Vec2(0, 0)

def get_text_position(text):
    return TextBoxLineFinder.get_text_position(text)

def rotate_point(pt, center, angle_deg):
    angle_rad = math.radians(angle_deg)
    dx, dy = pt.x - center.x, pt.y - center.y
    cos_a, sin_a = math.cos(angle_rad), math.sin(angle_rad)
    rx = dx * cos_a - dy * sin_a + center.x
    ry = dx * sin_a + dy * cos_a + center.y
    return Vec2(rx, ry)

def move_point(pt, offset):
    return Vec2(pt.x + offset.x, pt.y + offset.y)

def rotate_entity_around(entity, center, angle_deg):
    try:
        t = entity.dxftype()
        if t == "TEXT":
            pos = get_text_position(entity)
            rpos = rotate_point(pos, center, angle_deg)
            entity.dxf.insert = (rpos.x, rpos.y, 0)
            orig_angle = getattr(entity.dxf, 'rotation', 0)
            new_angle = (orig_angle + angle_deg) % 360
            entity.dxf.rotation = new_angle
        elif t == "LINE":
            a = Vec2(entity.dxf.start.x, entity.dxf.start.y)
            b = Vec2(entity.dxf.end.x, entity.dxf.end.y)
            ra = rotate_point(a, center, angle_deg)
            rb = rotate_point(b, center, angle_deg)
            entity.dxf.start = (ra.x, ra.y, 0)
            entity.dxf.end = (rb.x, rb.y, 0)
    except Exception:
        pass

def move_entity(entity, offset):
    try:
        t = entity.dxftype()
        if t == "TEXT":
            pos = get_text_position(entity)
            npos = move_point(pos, offset)
            entity.dxf.insert = (npos.x, npos.y, 0)
        elif t == "LINE":
            a = Vec2(entity.dxf.start.x, entity.dxf.start.y)
            b = Vec2(entity.dxf.end.x, entity.dxf.end.y)
            na = move_point(a, offset)
            nb = move_point(b, offset)
            entity.dxf.start = (na.x, na.y, 0)
            entity.dxf.end = (nb.x, nb.y, 0)
    except Exception:
        pass

def calc_angle_deg(pt1, pt2):
    dx = pt2.x - pt1.x
    dy = pt2.y - pt1.y
    return math.degrees(math.atan2(dy, dx))

def get_perpendicular_offset(angle_deg, length):
    angle_rad = math.radians(angle_deg + 90)
    return Vec2(math.cos(angle_rad) * length, math.sin(angle_rad) * length)

def get_entity_center(entities):
    x_sum = 0; y_sum = 0; n = 0
    for ent in entities:
        if ent.dxftype() == "TEXT":
            pos = get_text_position(ent)
            x_sum += pos.x; y_sum += pos.y; n += 1
        elif ent.dxftype() == "LINE":
            a = Vec2(ent.dxf.start.x, ent.dxf.start.y)
            b = Vec2(ent.dxf.end.x, ent.dxf.end.y)
            x_sum += (a.x + b.x) / 2; y_sum += (a.y + b.y) / 2; n += 1
    return Vec2(x_sum/n, y_sum/n) if n else Vec2(0,0)

def get_line_center(line):
    if line.dxftype() == "LINE":
        start = Vec2(line.dxf.start.x, line.dxf.start.y)
        end = Vec2(line.dxf.end.x, line.dxf.end.y)
        return Vec2((start.x + end.x) / 2, (start.y + end.y) / 2)
    return None

def get_line_angle(line):
    if line.dxftype() == "LINE":
        start = Vec2(line.dxf.start.x, line.dxf.start.y)
        end = Vec2(line.dxf.end.x, line.dxf.end.y)
        return calc_angle_deg(start, end)
    return 0

def check_line_passes_near_point(line, point, threshold=2.0):
    if line.dxftype() == "LINE":
        start = Vec2(line.dxf.start.x, line.dxf.start.y)
        end = Vec2(line.dxf.end.x, line.dxf.end.y)
        line_vec = Vec2(end.x - start.x, end.y - start.y)
        line_len = math.sqrt(line_vec.x**2 + line_vec.y**2)
        if line_len == 0:
            return distance(point, start) <= threshold
        t = max(0, min(1, ((point.x - start.x) * line_vec.x + (point.y - start.y) * line_vec.y) / (line_len**2)))
        closest_point = Vec2(start.x + t * line_vec.x, start.y + t * line_vec.y)
        return distance(point, closest_point) <= threshold
    return False

def get_line_length(line):
    if line.dxftype() == "LINE":
        start = Vec2(line.dxf.start.x, line.dxf.start.y)
        end = Vec2(line.dxf.end.x, line.dxf.end.y)
        return distance(start, end)
    return 0

def set_mirrtext_zero(doc):
    try:
        doc.header['$MIRRTEXT'] = 0
    except Exception:
        pass

def get_text_bbox(text):
    return TextBoxLineFinder.get_text_bbox(text)

def get_rotated_bbox_bounds(bbox):
    if not isinstance(bbox, dict):
        return {'min_x': 0, 'max_x': 0, 'min_y': 0, 'max_y': 0}
    if 'min_x' not in bbox or 'max_x' not in bbox or 'min_y' not in bbox or 'max_y' not in bbox:
        return {'min_x': 0, 'max_x': 0, 'min_y': 0, 'max_y': 0}
    pos = bbox.get('pos')
    if not pos:
        pos = Vec2(bbox['min_x'], bbox['min_y'])
    corners = [
        (bbox['min_x'] - pos.x, bbox['min_y'] - pos.y),
        (bbox['max_x'] - pos.x, bbox['min_y'] - pos.y),
        (bbox['max_x'] - pos.x, bbox['max_y'] - pos.y),
        (bbox['min_x'] - pos.x, bbox['max_y'] - pos.y)
    ]
    rotation = bbox.get('rotation', 0)
    if abs(rotation) > 0.01:
        rotation_rad = math.radians(rotation)
        cos_r = math.cos(rotation_rad)
        sin_r = math.sin(rotation_rad)
        rotated_corners = []
        for dx, dy in corners:
            rx = dx * cos_r - dy * sin_r
            ry = dx * sin_r + dy * cos_r
            rotated_corners.append((rx + pos.x, ry + pos.y))
    else:
        rotated_corners = [(x + pos.x, y + pos.y) for x, y in corners]
    x_coords = [c[0] for c in rotated_corners]
    y_coords = [c[1] for c in rotated_corners]
    return {
        'min_x': min(x_coords),
        'max_x': max(x_coords),
        'min_y': min(y_coords),
        'max_y': max(y_coords)
    }

def check_bbox_overlap(bbox1, bbox2, threshold=0.5):
    if not isinstance(bbox1, dict) or not isinstance(bbox2, dict):
        return False
    required_keys = ['min_x', 'max_x', 'min_y', 'max_y']
    for key in required_keys:
        if key not in bbox1 or key not in bbox2:
            return False
    bounds1 = get_rotated_bbox_bounds(bbox1)
    bounds2 = get_rotated_bbox_bounds(bbox2)
    x_gap = max(bounds1['min_x'] - bounds2['max_x'], bounds2['min_x'] - bounds1['max_x'])
    y_gap = max(bounds1['min_y'] - bounds2['max_y'], bounds2['min_y'] - bounds1['max_y'])
    if x_gap < 0 and y_gap < 0:
        overlap_x = min(bounds1['max_x'], bounds2['max_x']) - max(bounds1['min_x'], bounds2['min_x'])
        overlap_y = min(bounds1['max_y'], bounds2['max_y']) - max(bounds1['min_y'], bounds2['min_y'])
        overlap = (overlap_x > threshold and overlap_y > threshold)
        return overlap
    else:
        return False

def rotate_point_wrapper(corner, pos, rotation):
    angle_rad = math.radians(rotation)
    dx, dy = corner.x - pos.x, corner.y - pos.y
    rx = dx * math.cos(angle_rad) - dy * math.sin(angle_rad) + pos.x
    ry = dx * math.sin(angle_rad) + dy * math.cos(angle_rad) + pos.y
    return Vec2(rx, ry)

def draw_bbox(msp, bbox, layer_name, color):
    pos = bbox.get('pos') or Vec2(bbox['min_x'], bbox['min_y'])
    corners = [
        Vec2(bbox['min_x'], bbox['min_y']),
        Vec2(bbox['max_x'], bbox['min_y']),
        Vec2(bbox['max_x'], bbox['max_y']),
        Vec2(bbox['min_x'], bbox['max_y'])
    ]
    rotation = bbox.get('rotation', 0)
    if abs(rotation) > 0.01:
        rotated_corners = []
        for corner in corners:
            rotated = rotate_point_wrapper(corner, pos, rotation)
            rotated_corners.append(rotated)
        corners = rotated_corners
    for i in range(4):
        start = corners[i]
        end = corners[(i + 1) % 4]
        line = msp.add_line((start.x, start.y, 0), (end.x, end.y, 0))
        line.dxf.layer = layer_name
        line.dxf.color = color

def delete_boxes_by_layer(msp, layer_names):
    entities_to_delete = []
    for entity in msp:
        if entity.dxftype() == 'LINE' and entity.dxf.layer in layer_names:
            entities_to_delete.append(entity)
    for entity in entities_to_delete:
        try:
            msp.delete_entity(entity)
        except Exception:
            pass

def check_interference(itno_entities, msp, exclude_entities, threshold=0.5, draw_all_itno_boxes=True):
    itno_text_boxes = []
    itno_text_list = []
    itno_text_entities = []
    for ent in itno_entities:
        if ent.dxftype() == "TEXT":
            bbox = get_text_bbox(ent)
            itno_text_boxes.append(bbox)
            itno_text_list.append(ent.dxf.text)
            itno_text_entities.append(ent)
    if draw_all_itno_boxes:
        for i, (text, bbox, ent) in enumerate(zip(itno_text_list, itno_text_boxes, itno_text_entities)):
            draw_bbox(msp, bbox, "ITEMNO_BOX", 6)
    interfered_texts = []
    interfered_with_itno = []
    for text in msp.query('TEXT'):
        if text in itno_entities or text in exclude_entities:
            continue
        text_bbox = get_text_bbox(text)
        for idx, itno_bbox in enumerate(itno_text_boxes):
            if check_bbox_overlap(itno_bbox, text_bbox, threshold):
                if not any(item['text'] == text.dxf.text and
                           abs(item['pos'].x - get_text_position(text).x) < 0.01 and
                           abs(item['pos'].y - get_text_position(text).y) < 0.01
                           for item in interfered_texts):
                    interfered_texts.append({
                        'text': text.dxf.text,
                        'pos': get_text_position(text),
                        'bbox': text_bbox,
                        'layer': text.dxf.layer,
                        'entity': text
                    })
                    if idx not in interfered_with_itno:
                        interfered_with_itno.append(idx)
                break
    if interfered_texts:
        for idx in interfered_with_itno:
            draw_bbox(msp, itno_text_boxes[idx], "INTERFERENCE_ITNO", 4)
        for item in interfered_texts:
            draw_bbox(msp, item['bbox'], "INTERFERENCE_TEXT", 1)
        return True
    else:
        return False

def process_dxf(file_path):
    try:
        doc = ezdxf.readfile(file_path)
    except Exception:
        return
    msp = doc.modelspace()
    modified = False
    for st1 in msp.query('TEXT'):
        if '<' not in st1.dxf.text or '>' not in st1.dxf.text:
            continue
        st1_pos = get_text_position(st1)
        candidate_st2 = []
        for e in msp.query('TEXT LINE'):
            if e is st1:
                continue
            pos = get_text_position(e) if e.dxftype() == 'TEXT' else get_line_midpoint(e)
            dx = pos.x - st1_pos.x
            dy = abs(pos.y - st1_pos.y)
            if 0 < dx <= 15 and dy <= 5:
                candidate_st2.append(e)
        text_st2s = [e for e in candidate_st2 if e.dxftype() == 'TEXT' and abs(get_text_position(e).y - st1_pos.y) <= 0.5]
        line_st2s = []
        for e in candidate_st2:
            if e.dxftype() == 'LINE':
                start = e.dxf.start
                end = e.dxf.end
                length = distance(Vec2(start.x, start.y), Vec2(end.x, end.y))
                if 2.8 <= length <= 4.5:
                    line_st2s.append(e)
        if not (text_st2s and len(line_st2s) >= 4):
            continue
        original_line_count = len(line_st2s)
        all_original_lines = line_st2s.copy()
        if len(line_st2s) > 4:
            line_distances = []
            for line in line_st2s:
                start = Vec2(line.dxf.start.x, line.dxf.start.y)
                end = Vec2(line.dxf.end.x, line.dxf.end.y)
                min_dist_val = min(distance(start, st1_pos), distance(end, st1_pos))
                line_distances.append((min_dist_val, line))
            line_distances.sort(key=lambda x: x[0])
            first_line = line_distances[0][1]
            first_line_start = Vec2(first_line.dxf.start.x, first_line.dxf.start.y)
            first_line_end = Vec2(first_line.dxf.end.x, first_line.dxf.end.y)
            remaining_lines = [item[1] for item in line_distances[1:]]
            remaining_distances = []
            for line in remaining_lines:
                start = Vec2(line.dxf.start.x, line.dxf.start.y)
                end = Vec2(line.dxf.end.x, line.dxf.end.y)
                min_dist_to_first = min(
                    distance(start, first_line_start),
                    distance(start, first_line_end),
                    distance(end, first_line_start),
                    distance(end, first_line_end)
                )
                remaining_distances.append((min_dist_to_first, line))
            remaining_distances.sort(key=lambda x: x[0])
            selected_lines = [first_line] + [item[1] for item in remaining_distances[:3]]
            unselected_lines = [item[1] for item in line_distances[4:]] + [item[1] for item in remaining_distances[3:]]
            line_st2s = selected_lines
        line_group = line_st2s
        st1.dxf.layer = "ITNO"
        text_st2 = text_st2s[0]
        text_st2.dxf.layer = "ITNO"
        for l in line_group:
            l.dxf.layer = "ITNO"
        set_entity_color(st1, 1)
        set_entity_color(text_st2, 1)
        for l in line_group:
            set_entity_color(l, 1)
        modified = True
        itno_dn_text = None
        for e in msp.query('TEXT'):
            if e is st1 or e is text_st2:
                continue
            pos = get_text_position(e)
            dx = abs(pos.x - st1_pos.x)
            dy = st1_pos.y - pos.y
            if dx <= 2.0 and 0 < dy <= 4.0:
                text_upper = e.dxf.text.upper()
                if "DN" in text_upper or '"' in e.dxf.text:
                    itno_dn_text = e
                    break
        if itno_dn_text:
            itno_dn_text.dxf.layer = "ITNODN"
            set_entity_color(itno_dn_text, 1)
        found_PLINE = None
        SPOS = None
        itno_group_for_a1 = [st1, text_st2] + line_group
        if itno_dn_text:
            itno_group_for_a1.append(itno_dn_text)
        found_A1, AP1, AP2 = TextBoxLineFinder.find_closest_line_to_group(
            entities=itno_group_for_a1,
            lines=msp.query('LINE'),
            exclude_entities=line_group,
            exclude_layers=['FRAME'],
            min_length=None,
            debug=False
        )
        if not found_A1:
            continue
        found_A1.dxf.layer = "A1"
        set_entity_color(found_A1, 4)
        additional_a1_lines = []
        del1_lines = []
        for attempt in range(10):
            del1_lines = []
            if found_A1:
                all_endpoints = []
                a1_start = Vec2(found_A1.dxf.start.x, found_A1.dxf.start.y)
                a1_end = Vec2(found_A1.dxf.end.x, found_A1.dxf.end.y)
                all_endpoints.extend([a1_start, a1_end])
                for add_line in additional_a1_lines:
                    add_start = Vec2(add_line.dxf.start.x, add_line.dxf.start.y)
                    add_end = Vec2(add_line.dxf.end.x, add_line.dxf.end.y)
                    all_endpoints.extend([add_start, add_end])
                for line in msp.query('LINE'):
                    if line is found_A1 or line in line_group:
                        continue
                    if line in additional_a1_lines:
                        continue
                    if line in del1_lines:
                        continue
                    if line.dxf.layer.upper() == "FRAME":
                        continue
                    line_len = get_line_length(line)
                    if line_len > 2.0:
                        continue
                    start = Vec2(line.dxf.start.x, line.dxf.start.y)
                    end = Vec2(line.dxf.end.x, line.dxf.end.y)
                    for endpoint in all_endpoints:
                        if (distance(start, endpoint) <= 2.0 or distance(end, endpoint) <= 2.0):
                            del1_lines.append(line)
                            break
                    if len(del1_lines) >= 3:
                        break
                if del1_lines:
                    break
                found_additional = False
                for line in msp.query('LINE'):
                    if line is found_A1 or line in line_group:
                        continue
                    if line in additional_a1_lines:
                        continue
                    if line.dxf.layer.upper() == "FRAME":
                        continue
                    line_len = get_line_length(line)
                    if line_len <= 2.0:
                        continue
                    start = Vec2(line.dxf.start.x, line.dxf.start.y)
                    end = Vec2(line.dxf.end.x, line.dxf.end.y)
                    for endpoint in all_endpoints:
                        dist_to_start = distance(start, endpoint)
                        dist_to_end = distance(end, endpoint)
                        if dist_to_start <= 0.3:
                            additional_a1_lines.append(line)
                            AP2 = end
                            found_additional = True
                            break
                        elif dist_to_end <= 0.3:
                            additional_a1_lines.append(line)
                            AP2 = start
                            found_additional = True
                            break
                    if found_additional:
                        break
                if not found_additional:
                    break
        if not del1_lines:
            isotext_line = None
            min_isotext_dist = float("inf")
            for line in msp.query('LINE'):
                if line is found_A1 or line in line_group:
                    continue
                if line.dxf.layer.upper() != "ISOTEXT":
                    continue
                line_len = get_line_length(line)
                if line_len < 2.0:
                    continue
                start = Vec2(line.dxf.start.x, line.dxf.start.y)
                end = Vec2(line.dxf.end.x, line.dxf.end.y)
                dist_to_start = distance(AP2, start)
                dist_to_end = distance(AP2, end)
                min_dist_to_ap2 = min(dist_to_start, dist_to_end)
                if min_dist_to_ap2 < min_isotext_dist:
                    min_isotext_dist = min_dist_to_ap2
                    isotext_line = line
            if isotext_line:
                isotext_line.dxf.layer = "A1"
                set_entity_color(isotext_line, 4)
                additional_a1_lines.append(isotext_line)
                start = Vec2(isotext_line.dxf.start.x, isotext_line.dxf.start.y)
                end = Vec2(isotext_line.dxf.end.x, isotext_line.dxf.end.y)
                if distance(AP2, start) < distance(AP2, end):
                    AP2 = end
                else:
                    AP2 = start
                all_endpoints = []
                all_endpoints.extend([Vec2(found_A1.dxf.start.x, found_A1.dxf.start.y),
                                      Vec2(found_A1.dxf.end.x, found_A1.dxf.end.y)])
                for add_line in additional_a1_lines:
                    all_endpoints.extend([Vec2(add_line.dxf.start.x, add_line.dxf.start.y),
                                          Vec2(add_line.dxf.end.x, add_line.dxf.end.y)])
                for line in msp.query('LINE'):
                    if line is found_A1 or line in line_group:
                        continue
                    if line in additional_a1_lines:
                        continue
                    if line in del1_lines:
                        continue
                    if line.dxf.layer.upper() == "FRAME":
                        continue
                    line_len = get_line_length(line)
                    if line_len > 2.0:
                        continue
                    start = Vec2(line.dxf.start.x, line.dxf.start.y)
                    end = Vec2(line.dxf.end.x, line.dxf.end.y)
                    for endpoint in all_endpoints:
                        if (distance(start, endpoint) <= 2.0 or distance(end, endpoint) <= 2.0):
                            del1_lines.append(line)
                            break
        found_PLINE = None
        min_pline_dist = float("inf")
        pipe_too_short = False
        for line in msp.query('LINE'):
            if line is found_A1 or line in line_group:
                continue
            if "PIPE" not in line.dxf.layer.upper():
                continue
            if get_line_length(line) <= 1.8:
                continue
            if check_line_passes_near_point(line, AP2, 2.0):
                center = get_line_center(line)
                if center:
                    dist = distance(center, AP2)
                    if dist < min_pline_dist:
                        min_pline_dist = dist
                        found_PLINE = line
        if not found_PLINE:
            continue
        else:
            line_len = get_line_length(found_PLINE)
            pipe_too_short = line_len <= 10.0
        ppos = get_line_center(found_PLINE)
        if not ppos:
            continue
        pline_angle = get_line_angle(found_PLINE)
        found_AD1 = None
        min_ad1_dist = float("inf")
        for line in msp.query('LINE'):
            if line is found_A1 or line is found_PLINE or line in line_group:
                continue
            line_len = get_line_length(line)
            if line_len > 5:
                continue
            start = Vec2(line.dxf.start.x, line.dxf.start.y)
            end = Vec2(line.dxf.end.x, line.dxf.end.y)
            min_dist_to_ap2 = min(distance(start, AP2), distance(end, AP2))
            if min_dist_to_ap2 < min_ad1_dist:
                min_ad1_dist = min_dist_to_ap2
                found_AD1 = line
        if found_AD1:
            found_AD1.dxf.layer = "AD1"
            set_entity_color(found_AD1, 3)
        for add_line in additional_a1_lines:
            add_line.dxf.layer = "A1"
            set_entity_color(add_line, 4)
        for i, line in enumerate(del1_lines):
            line.dxf.layer = "DEL1"
            set_entity_color(line, 5)
        itno_entities = [st1, text_st2] + line_group
        if itno_dn_text:
            itno_entities.append(itno_dn_text)
        exclude_entities = [st1, text_st2, itno_dn_text] if itno_dn_text else [st1, text_st2]
        itno_center_before = get_entity_center(itno_entities)
        SPOS = Vec2(itno_center_before.x, itno_center_before.y)
        itno_to_ppos_offset = Vec2(ppos.x - itno_center_before.x, ppos.y - itno_center_before.y)
        for ent in itno_entities:
            move_entity(ent, itno_to_ppos_offset)
        for ent in itno_entities:
            rotate_entity_around(ent, ppos, pline_angle)
        perp_angle = pline_angle + 90
        move_distance_perp = 1.65 if itno_dn_text else 2.5
        perp_offset = get_perpendicular_offset(pline_angle, move_distance_perp)
        for ent in itno_entities:
            move_entity(ent, perp_offset)
        if pline_angle <= -89:
            set_mirrtext_zero(doc)
            for ent in itno_entities:
                rotate_entity_around(ent, ppos, 180)
        st1_pos_current = get_text_position(st1)
        st2_pos_current = get_text_position(text_st2)
        if st1_pos_current.x > st2_pos_current.x:
            set_mirrtext_zero(doc)
            itno_center_before_correction = get_entity_center(itno_entities)
            for ent in itno_entities:
                rotate_entity_around(ent, itno_center_before_correction, 180)
            perp_offset_correction = get_perpendicular_offset(pline_angle, -6)
            for ent in itno_entities:
                move_entity(ent, perp_offset_correction)
        if check_interference(itno_entities, msp, exclude_entities):
            current_itno_center = get_entity_center(itno_entities)
            pline_center = get_line_center(found_PLINE)
            from_pipe_vector = Vec2(current_itno_center.x - pline_center.x,
                                    current_itno_center.y - pline_center.y)
            vector_length = math.sqrt(from_pipe_vector.x**2 + from_pipe_vector.y**2)
            if vector_length > 0:
                interference_offset = Vec2(
                    -2 * from_pipe_vector.x,
                    -2 * from_pipe_vector.y
                )
            else:
                fallback_distance = 1.65 if itno_dn_text else 2.5
                interference_offset = get_perpendicular_offset(pline_angle, fallback_distance * 2)
            for ent in itno_entities:
                move_entity(ent, interference_offset)
            check_interference(itno_entities, msp, exclude_entities, draw_all_itno_boxes=False)
        if pipe_too_short:
            itno_center_final = get_entity_center(itno_entities)
            FPOS = Vec2(itno_center_final.x, itno_center_final.y)
            restore_offset = Vec2(SPOS.x - FPOS.x, SPOS.y - FPOS.y)
            for ent in itno_entities:
                move_entity(ent, restore_offset)
            if del1_lines:
                for line in del1_lines:
                    set_entity_color(line, 4)
        else:
            to_remove = []
            removed_entities = set()
            if found_A1:
                to_remove.append((found_A1, "A1"))
                removed_entities.add(found_A1)
            for i, add_line in enumerate(additional_a1_lines):
                if add_line not in removed_entities:
                    to_remove.append((add_line, f"A1-ADD{i+1}"))
                    removed_entities.add(add_line)
            if found_AD1 and found_AD1 not in removed_entities:
                to_remove.append((found_AD1, "AD1"))
                removed_entities.add(found_AD1)
            for i, line in enumerate(del1_lines):
                if line not in removed_entities:
                    to_remove.append((line, f"DEL1-{i+1}"))
                    removed_entities.add(line)
            if found_AD1:
                ad1_start = Vec2(found_AD1.dxf.start.x, found_AD1.dxf.start.y)
                ad1_end = Vec2(found_AD1.dxf.end.x, found_AD1.dxf.end.y)
                ad1_points = [ad1_start, ad1_end]
                for line in msp.query('LINE'):
                    try:
                        if not hasattr(line, 'dxf') or not hasattr(line.dxf, 'layer'):
                            continue
                        if line.dxf.layer.upper() != "ARROW":
                            continue
                        start = Vec2(line.dxf.start.x, line.dxf.start.y)
                        end = Vec2(line.dxf.end.x, line.dxf.end.y)
                        line_length = distance(start, end)
                        if line_length > 1.0:
                            continue
                        for ad1_pt in ad1_points:
                            if distance(ad1_pt, start) < 0.01 or distance(ad1_pt, end) < 0.01:
                                to_remove.append((line, "ARROW"))
                                break
                    except Exception:
                        continue
            for entity, _ in to_remove:
                try:
                    msp.delete_entity(entity)
                except Exception:
                    pass
    box_layers = ["ITEMNO_BOX", "INTERFERENCE_ITNO", "INTERFERENCE_TEXT"]
    delete_boxes_by_layer(msp, box_layers)
    save_path = os.path.splitext(file_path)[0] + "_ITNO.dxf"
    try:
        doc.saveas(save_path)
    except Exception:
        pass

def _expand_cli_paths(argv):
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

if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        sys.exit(0)
    files = _expand_cli_paths(args)
    for f in files:
        process_dxf(f)
