import ezdxf
import os
import math
import re
import sys
from ezdxf.math import Vec2

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
    """TEXT 엔티티의 위치를 Vec2로 반환"""
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
    except:
        pass
    
    return Vec2(0.0, 0.0)

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
    except:
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
    except:
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
    except:
        pass

def get_text_bbox(text):
    pos = get_text_position(text)
    height = getattr(text.dxf, 'height', 2.2)
    text_len = len(text.dxf.text) * height * 0.8
    
    box_height = height + 0.3
    
    rotation = getattr(text.dxf, 'rotation', 0)
    
    return {
        'min_x': pos.x,
        'max_x': pos.x + text_len,
        'min_y': pos.y - 0.15,
        'max_y': pos.y + box_height - 0.15,
        'rotation': rotation,
        'pos': pos
    }

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

def point_to_line_distance(point, line_start, line_end):
    line_vec = Vec2(line_end.x - line_start.x, line_end.y - line_start.y)
    line_len = math.sqrt(line_vec.x**2 + line_vec.y**2)
    
    if line_len == 0:
        return distance(point, line_start)
    
    t = max(0, min(1, ((point.x - line_start.x) * line_vec.x + (point.y - line_start.y) * line_vec.y) / (line_len**2)))
    
    closest_point = Vec2(
        line_start.x + t * line_vec.x,
        line_start.y + t * line_vec.y
    )
    
    return distance(point, closest_point)

def check_fl_el_text(text):
    text_upper = text.upper()
    pattern = r'(FL|EL)\s*[+\-]'
    return bool(re.search(pattern, text_upper))

def is_matlist_entity(e):
    try:
        return hasattr(e, "dxf") and hasattr(e.dxf, "layer") and str(e.dxf.layer).upper() == "MATLIST"
    except:
        return False

def iter_texts_excluding_matlist(msp):
    for t in msp.query('TEXT'):
        if is_matlist_entity(t):
            continue
        yield t

def iter_lines_excluding_matlist(msp):
    for ln in msp.query('LINE'):
        if is_matlist_entity(ln):
            continue
        yield ln

def count_small_lines_near_endpoints(msp, line, radius=3.0, max_length=2.0):
    if line.dxftype() != "LINE":
        return 0
    
    start = Vec2(line.dxf.start.x, line.dxf.start.y)
    end = Vec2(line.dxf.end.x, line.dxf.end.y)
    endpoints = [start, end]
    
    small_lines_found = set()
    
    for other_line in iter_lines_excluding_matlist(msp):
        if other_line is line:
            continue
            
        layer_upper = other_line.dxf.layer.upper()
        if layer_upper != "DIMLINES" and not layer_upper.startswith("AD"):
            continue
            
        other_length = get_line_length(other_line)
        if other_length > max_length:
            continue
            
        other_start = Vec2(other_line.dxf.start.x, other_line.dxf.start.y)
        other_end = Vec2(other_line.dxf.end.x, other_line.dxf.end.y)
        
        for endpoint in endpoints:
            if distance(endpoint, other_start) <= radius or distance(endpoint, other_end) <= radius:
                small_lines_found.add(other_line.dxf.handle)
                break
    
    return len(small_lines_found)

def process(doc):
    """In-memory processing entry point for runner integration"""
    msp = doc.modelspace()
    modified = False
    processed_count = 0

    all_texts = list(iter_texts_excluding_matlist(msp))
    
    fl_el_texts = []
    for text in all_texts:
        if check_fl_el_text(text.dxf.text):
            rotation = getattr(text.dxf, 'rotation', 0)
            fl_el_texts.append((text, rotation))

    for st1 in iter_texts_excluding_matlist(msp):
        if not check_fl_el_text(st1.dxf.text):
            continue
        
        st1_original_rotation = getattr(st1.dxf, 'rotation', 0)
        if st1_original_rotation != 0:
            continue
            
        st1_pos = get_text_position(st1)
        
        initial_fl_bbox = get_text_bbox(st1)
        
        skip_this_fl = False
        for text in iter_texts_excluding_matlist(msp):
            if text is st1:
                continue
            text_pos = get_text_position(text)
            
            dy = text_pos.y - st1_pos.y
            dx = abs(text_pos.x - st1_pos.x)
            
            if 0 <= dy <= 4 and dx <= 0.5:
                text_upper = text.dxf.text.upper()
                if 'N' in text_upper or 'S' in text_upper:
                    skip_this_fl = True
                    break
        
        if skip_this_fl:
            continue

        st1.dxf.layer = "ELEDIT"
        set_entity_color(st1, 4)
        
        modified = True

        eledit_dn_text = None
        for e in iter_texts_excluding_matlist(msp):
            if e is st1:
                continue
            pos = get_text_position(e)
            dx = abs(pos.x - st1_pos.x)
            dy = st1_pos.y - pos.y
            if dx <= 2.0 and 0 < dy <= 4.0:
                text_upper = e.dxf.text.upper()
                if "DN" in text_upper or '"' in e.dxf.text:
                    eledit_dn_text = e
                    break
        if eledit_dn_text:
            eledit_dn_text.dxf.layer = "ELEDITDN"
            set_entity_color(eledit_dn_text, 4)

        found_DIMLINE = None
        
        fl_bbox = get_text_bbox(st1)
        fl_left_point = st1_pos
        fl_center_point = Vec2((fl_bbox['min_x'] + fl_bbox['max_x']) / 2, st1_pos.y)
        fl_right_point = Vec2(fl_bbox['max_x'], st1_pos.y)
        
        found_A1 = None
        AP1, AP2 = None, None
        min_dist = float("inf")
        
        for line in iter_lines_excluding_matlist(msp):
            if line.dxf.layer.upper() == "FRAME":
                continue
            
            if line.dxf.layer.upper() in ["FLBOX", "FL_BOX"]:
                continue
            
            if line.dxf.layer.upper() == "DEL1":
                continue
            
            line_len = get_line_length(line)
            if line_len <= 2.0:
                continue
                
            start = Vec2(line.dxf.start.x, line.dxf.start.y)
            end = Vec2(line.dxf.end.x, line.dxf.end.y)
            
            distances = []
            for fl_point in [fl_left_point, fl_center_point, fl_right_point]:
                distances.append(distance(start, fl_point))
                distances.append(distance(end, fl_point))
            
            min_pt_dist = min(distances)
            
            if min_pt_dist < min_dist:
                min_dist = min_pt_dist
                found_A1 = line
                
                min_idx = distances.index(min_pt_dist)
                
                if min_idx % 2 == 0:
                    AP1 = start
                    AP2 = end
                else:
                    AP1 = end
                    AP2 = start
                
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
                
                for line in iter_lines_excluding_matlist(msp):
                    if line is found_A1:
                        continue
                    if line in additional_a1_lines:
                        continue
                    if line in del1_lines:
                        continue
                        
                    if line.dxf.layer.upper() == "FRAME":
                        continue
                    
                    if line.dxf.layer.upper() == "FLBOX":
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
                candidates_checked = 0
                
                for line in iter_lines_excluding_matlist(msp):
                    if line is found_A1:
                        continue
                    if line in additional_a1_lines:
                        continue
                    if line.dxf.layer.upper() == "FRAME":
                        continue
                    
                    if line.dxf.layer.upper() == "FLBOX":
                        continue
                    
                    if line.dxf.layer.upper() == "DEL1":
                        continue
                    
                    line_len = get_line_length(line)
                    if line_len <= 2.0:
                        continue
                    
                    candidates_checked += 1
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
            
            for line in iter_lines_excluding_matlist(msp):
                if line is found_A1:
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
                
                for line in iter_lines_excluding_matlist(msp):
                    if line is found_A1:
                        continue
                    if line in additional_a1_lines:
                        continue
                    if line in del1_lines:
                        continue
                        
                    if line.dxf.layer.upper() == "FLBOX":
                        continue
                        
                    if line.dxf.layer.upper() != "ISOTEXT":
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

        found_DIMLINE = None
        min_dimline_dist = float("inf")
        
        dimline_candidates = []
        
        for line in iter_lines_excluding_matlist(msp):
            if line is found_A1:
                continue
            
            if line.dxf.layer.upper() == "FLBOX":
                continue
            
            if line.dxf.layer.upper() != "DIMLINES":
                continue
            
            line_len = get_line_length(line)
            if line_len <= 1.8:
                continue
            
            line_angle = get_line_angle(line)
            if (85 <= abs(line_angle) <= 95):
                continue
                
            if check_line_passes_near_point(line, AP2, 2.0):
                center = get_line_center(line)
                if center:
                    dist = distance(center, AP2)
                    dimline_candidates.append((line, dist, line_len))
        
        if len(dimline_candidates) >= 2:
            filtered_candidates = []
            for line, dist, line_len in dimline_candidates:
                small_lines_count = count_small_lines_near_endpoints(msp, line, radius=3.0, max_length=2.0)
                if small_lines_count < 4:
                    filtered_candidates.append((line, dist, line_len))
            
            dimline_candidates = filtered_candidates
        
        if dimline_candidates:
            dimline_candidates.sort(key=lambda x: x[1])
            found_DIMLINE, min_dimline_dist, line_len = dimline_candidates[0]
        
        if not found_DIMLINE:
            continue
        else:
            line_len = get_line_length(found_DIMLINE)
            
            found_DIMLINE.dxf.layer = "DIM"
            set_entity_color(found_DIMLINE, 4)
            
            if line_len <= 10.0:
                continue

        dpos = get_line_center(found_DIMLINE)
        if not dpos:
            continue
        
        dimline_angle = get_line_angle(found_DIMLINE)

        found_AD1 = None
        min_ad1_dist = float("inf")
        
        for line in iter_lines_excluding_matlist(msp):
            if line is found_A1 or line is found_DIMLINE:
                continue
            
            if line.dxf.layer.upper() == "FLBOX":
                continue
            
            line_len = get_line_length(line)
            if line_len > 1.5:
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
            set_entity_color(line, 4)

        eledit_entities = [st1]
        if eledit_dn_text:
            eledit_entities.append(eledit_dn_text)
        
        fl_insert_point = get_text_position(st1)
        
        dim_start = Vec2(found_DIMLINE.dxf.start.x, found_DIMLINE.dxf.start.y)
        dim_end = Vec2(found_DIMLINE.dxf.end.x, found_DIMLINE.dxf.end.y)
        dim_vector = Vec2(dim_end.x - dim_start.x, dim_end.y - dim_start.y)
        dim_length = math.sqrt(dim_vector.x**2 + dim_vector.y**2)
        
        if dim_length > 0:
            dim_unit_vector = Vec2(dim_vector.x / dim_length, dim_vector.y / dim_length)
        else:
            dim_unit_vector = Vec2(1, 0)
        
        fl_to_start = Vec2(fl_insert_point.x - dim_start.x, fl_insert_point.y - dim_start.y)
        projection_length = (fl_to_start.x * dim_unit_vector.x + fl_to_start.y * dim_unit_vector.y)
        
        projection_length = max(0, min(dim_length, projection_length))
        
        projection_point = Vec2(
            dim_start.x + dim_unit_vector.x * projection_length,
            dim_start.y + dim_unit_vector.y * projection_length
        )
        
        perp_offset = get_perpendicular_offset(dimline_angle, 0.8)
        if perp_offset.y < 0:
            perp_offset = Vec2(-perp_offset.x, -perp_offset.y)
        
        target_fl_pos = Vec2(
            projection_point.x + perp_offset.x,
            projection_point.y + perp_offset.y
        )
        
        move_to_target = Vec2(
            target_fl_pos.x - fl_insert_point.x,
            target_fl_pos.y - fl_insert_point.y
        )
        
        for ent in eledit_entities:
            move_entity(ent, move_to_target)
        
        current_fl_pos = get_text_position(st1)
        for ent in eledit_entities:
            rotate_entity_around(ent, current_fl_pos, dimline_angle)
        
        rotated_fl_pos = get_text_position(st1)
        
        fl_to_start = Vec2(rotated_fl_pos.x - dim_start.x, rotated_fl_pos.y - dim_start.y)
        projection_length = (fl_to_start.x * dim_unit_vector.x + fl_to_start.y * dim_unit_vector.y)
        projection_length = max(0, min(dim_length, projection_length))
        
        projection_point = Vec2(
            dim_start.x + dim_unit_vector.x * projection_length,
            dim_start.y + dim_unit_vector.y * projection_length
        )
        
        perp_offset = get_perpendicular_offset(dimline_angle, 0.8)
        if perp_offset.y < 0:
            perp_offset = Vec2(-perp_offset.x, -perp_offset.y)
        
        final_fl_pos = Vec2(
            projection_point.x + perp_offset.x,
            projection_point.y + perp_offset.y
        )
        
        final_adjustment = Vec2(
            final_fl_pos.x - rotated_fl_pos.x,
            final_fl_pos.y - rotated_fl_pos.y
        )
        
        if abs(final_adjustment.x) > 0.01 or abs(final_adjustment.y) > 0.01:
            for ent in eledit_entities:
                move_entity(ent, final_adjustment)

        if dimline_angle > 90 or dimline_angle <= -90:
            set_mirrtext_zero(doc)
            
            fl_pos_for_rotation = get_text_position(st1)
            for ent in eledit_entities:
                rotate_entity_around(ent, fl_pos_for_rotation, 180)
            
            rotated_fl_pos = get_text_position(st1)
            
            fl_to_start = Vec2(rotated_fl_pos.x - dim_start.x, rotated_fl_pos.y - dim_start.y)
            projection_length = (fl_to_start.x * dim_unit_vector.x + fl_to_start.y * dim_unit_vector.y)
            projection_length = max(0, min(dim_length, projection_length))
            
            projection_point = Vec2(
                dim_start.x + dim_unit_vector.x * projection_length,
                dim_start.y + dim_unit_vector.y * projection_length
            )
            
            perp_offset = get_perpendicular_offset(dimline_angle, 0.8)
            if perp_offset.y < 0:
                perp_offset = Vec2(-perp_offset.x, -perp_offset.y)
            
            final_fl_pos = Vec2(
                projection_point.x + perp_offset.x,
                projection_point.y + perp_offset.y
            )
            
            final_adjustment = Vec2(
                final_fl_pos.x - rotated_fl_pos.x,
                final_fl_pos.y - rotated_fl_pos.y
            )
            
            if abs(final_adjustment.x) > 0.01 or abs(final_adjustment.y) > 0.01:
                for ent in eledit_entities:
                    move_entity(ent, final_adjustment)

        current_fl_bbox = get_text_bbox(st1)
        fl_bounds = get_rotated_bbox_bounds(current_fl_bbox)
        
        fl_corners = [
            Vec2(fl_bounds['min_x'], fl_bounds['min_y']),
            Vec2(fl_bounds['max_x'], fl_bounds['min_y']),
            Vec2(fl_bounds['max_x'], fl_bounds['max_y']),
            Vec2(fl_bounds['min_x'], fl_bounds['max_y'])
        ]
        
        dim_start = Vec2(found_DIMLINE.dxf.start.x, found_DIMLINE.dxf.start.y)
        dim_end = Vec2(found_DIMLINE.dxf.end.x, found_DIMLINE.dxf.end.y)
        dim_vector = Vec2(dim_end.x - dim_start.x, dim_end.y - dim_start.y)
        dim_length = math.sqrt(dim_vector.x**2 + dim_vector.y**2)
        
        if dim_length > 0:
            dim_unit_vector = Vec2(dim_vector.x / dim_length, dim_vector.y / dim_length)
        else:
            dim_unit_vector = Vec2(1, 0)
        
        min_projection = float('inf')
        max_projection = float('-inf')
        
        for corner in fl_corners:
            corner_to_start = Vec2(corner.x - dim_start.x, corner.y - dim_start.y)
            projection = (corner_to_start.x * dim_unit_vector.x + corner_to_start.y * dim_unit_vector.y)
            min_projection = min(min_projection, projection)
            max_projection = max(max_projection, projection)
        
        fl_text_length = current_fl_bbox['max_x'] - current_fl_bbox['min_x']
        max_extend = fl_text_length * 0.5
        min_extend = fl_text_length * 0.25
        
        fl_position_adjustment_needed = False
        fl_adjustment_offset = Vec2(0, 0)
        
        if min_projection < 0:
            original_extend = abs(min_projection)
            extend_length = original_extend
            
            if extend_length > max_extend:
                extend_length = max_extend
                adjustment_distance = original_extend - extend_length
                fl_adjustment_offset = Vec2(
                    dim_unit_vector.x * adjustment_distance,
                    dim_unit_vector.y * adjustment_distance
                )
                fl_position_adjustment_needed = True
            elif extend_length < min_extend:
                extend_length = min_extend
                
            new_start = Vec2(
                dim_start.x - dim_unit_vector.x * extend_length,
                dim_start.y - dim_unit_vector.y * extend_length
            )
            found_DIMLINE.dxf.start = (new_start.x, new_start.y, 0)
            
        if max_projection > dim_length:
            original_extend = max_projection - dim_length
            extend_length = original_extend
            
            if extend_length > max_extend:
                extend_length = max_extend
                adjustment_distance = original_extend - extend_length
                fl_adjustment_offset = Vec2(
                    -dim_unit_vector.x * adjustment_distance,
                    -dim_unit_vector.y * adjustment_distance
                )
                fl_position_adjustment_needed = True
            elif extend_length < min_extend:
                extend_length = min_extend
                
            new_end = Vec2(
                dim_end.x + dim_unit_vector.x * extend_length,
                dim_end.y + dim_unit_vector.y * extend_length
            )
            found_DIMLINE.dxf.end = (new_end.x, new_end.y, 0)
        
        if fl_position_adjustment_needed:
            for ent in eledit_entities:
                move_entity(ent, fl_adjustment_offset)

        processed_count += 1

        to_remove = []
        removed_entities = set()
        
        if found_A1:
            to_remove.append(found_A1)
            removed_entities.add(found_A1)
        
        for add_line in additional_a1_lines:
            if add_line not in removed_entities:
                to_remove.append(add_line)
                removed_entities.add(add_line)
            
        if found_AD1 and found_AD1 not in removed_entities:
            to_remove.append(found_AD1)
            removed_entities.add(found_AD1)
        
        for line in del1_lines:
            if line not in removed_entities:
                to_remove.append(line)
                removed_entities.add(line)
            
        if found_AD1:
            ad1_start = Vec2(found_AD1.dxf.start.x, found_AD1.dxf.start.y)
            ad1_end = Vec2(found_AD1.dxf.end.x, found_AD1.dxf.end.y)
            ad1_points = [ad1_start, ad1_end]
            
            for line in iter_lines_excluding_matlist(msp):
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
                            to_remove.append(line)
                            break
                except:
                    continue
        
        for entity in to_remove:
            try:
                msp.delete_entity(entity)
            except:
                pass

    entities_to_delete = []
    
    for entity in msp:
        if entity.dxftype() == 'LINE':
            if entity.dxf.layer in ["FLBOX", "FL_BOX"]:
                entities_to_delete.append(entity)
    
    for entity in entities_to_delete:
        try:
            msp.delete_entity(entity)
        except:
            pass

    return doc

def process_dxf_file(file_path):
    """Process a single DXF file and save the result"""
    try:
        doc = ezdxf.readfile(file_path)
    except Exception as e:
        print(f"Error reading file {file_path}: {e}")
        return False
    
    # Process the document
    doc = process(doc)
    
    # Save the modified document
    save_path = os.path.splitext(file_path)[0] + "_ELEDIT.dxf"
    try:
        doc.saveas(save_path)
        print(f"Saved: {os.path.basename(save_path)}")
        return True
    except Exception as e:
        print(f"Error saving file {save_path}: {e}")
        return False

def main():
    """Main entry point for command-line execution"""
    if len(sys.argv) < 2:
        print("Usage: python PLTONEWLINE.py file1.dxf file2.dxf ...")
        print("Example: python PLTONEWLINE.py A.DXF B.DXF C.DXF")
        sys.exit(1)
    
    # Process each DXF file from command line arguments
    files_processed = 0
    files_failed = 0
    
    for file_path in sys.argv[1:]:
        if not os.path.exists(file_path):
            print(f"File not found: {file_path}")
            files_failed += 1
            continue
        
        if not file_path.lower().endswith('.dxf'):
            print(f"Not a DXF file: {file_path}")
            files_failed += 1
            continue
        
        print(f"Processing: {file_path}")
        if process_dxf_file(file_path):
            files_processed += 1
        else:
            files_failed += 1
    
    print(f"\nProcessing complete:")
    print(f"  Successfully processed: {files_processed} files")
    if files_failed > 0:
        print(f"  Failed: {files_failed} files")

if __name__ == "__main__":
    main()

"""
시간복잡도 분석:
- 주요 반복문: O(n × m) where n = TEXT 개수, m = LINE 개수
- 각 FL/EL 텍스트당: O(m) for LINE 검색
- 전체: O(n × m) 
- 최적화 완료: 불필요한 print 제거, 캐싱 및 조기 종료 조건 활용

사용법:
python PLTONEWLINE.py file1.dxf file2.dxf file3.dxf

In-memory runner 연동:
from PLTONEWLINE import process
doc = ezdxf.readfile("input.dxf")
doc = process(doc)
doc.saveas("output.dxf")
"""