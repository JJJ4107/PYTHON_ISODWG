import os
import re
import sys
import ezdxf
from math import hypot, sqrt, radians, cos, sin
import time
import shutil

def get_selected_dxf_files():
    # tkinter를 사용하지 않고, 커맨드라인 인자로 받은 파일 목록을 그대로 사용
    return [p for p in sys.argv[1:] if p.lower().endswith(".dxf")]

def extract_text_entities(doc):
    return [e for e in doc.modelspace() if e.dxftype() == 'TEXT']

def get_texts_by_position(entities):
    texts = []
    for e in entities:
        pos = e.dxf.insert
        texts.append((e.plain_text().strip(), round(pos.x, 2), round(pos.y, 2), e))
    return sorted(texts, key=lambda t: (-t[2], t[1]))

def extract_bore_from_size(size_text):
    match = re.search(r'(\d+)', size_text)
    return int(match.group(1)) if match else 100

def find_size_value_near_materials(all_texts):
    materials_pos = None
    materials_type = None
    for text, x, y, _ in all_texts:
        if "FABRICATION MATERIAL" in text.upper():
            materials_pos = (x, y)
            materials_type = "FABRICATION"
            break
    if not materials_pos:
        for text, x, y, _ in all_texts:
            if "ERECTION MATERIAL" in text.upper():
                materials_pos = (x, y)
                materials_type = "ERECTION"
                break
    if not materials_pos:
        return None
    size_candidates = [
        (text, x, y) for text, x, y, _ in all_texts
        if "SIZE" in text.upper() and hypot(x - materials_pos[0], y - materials_pos[1]) <= 100
    ]
    if not size_candidates:
        return None
    size_text, size_x, size_y = sorted(size_candidates, key=lambda t: hypot(t[1] - materials_pos[0], t[2] - materials_pos[1]))[0]
    below_texts = [t for t in all_texts if abs(t[1] - size_x) < 1 and t[2] < size_y]
    if not below_texts:
        return None
    size_value = sorted(below_texts, key=lambda t: size_y - t[2])[0][0]
    return size_value

def find_dn_header_x(all_texts):
    header_groups = []
    texts_by_y = {}
    for text, x, y, _ in all_texts:
        texts_by_y.setdefault(round(y, 1), []).append((text.strip().upper(), x))
    for y, items in texts_by_y.items():
        headers = {t[0]: t[1] for t in items}
        if all(k in headers for k in ['NO', '/FLD', 'DN']):
            dn_x = headers['DN']
            return dn_x
    return None

def find_header_positions_improved(all_texts):
    texts_by_y = {}
    for text, x, y, e in all_texts:
        texts_by_y.setdefault(round(y, 1), []).append((text.strip().upper(), x, y, e))
    for y, items in texts_by_y.items():
        header_dict = {}
        for txt, x, orig_y, e in items:
            if txt == 'NO':
                header_dict['NO'] = (round(x, 2), round(orig_y, 2))
            elif txt == '/FLD':
                header_dict['/FLD'] = (round(x, 2), round(orig_y, 2))
            elif txt == 'DN':
                header_dict['DN'] = (round(x, 2), round(orig_y, 2))
            elif 'TYPE' in txt:
                header_dict['TYPE'] = (round(x, 2), round(orig_y, 2))
        if all(k in header_dict for k in ['NO', '/FLD', 'DN']):
            return header_dict
    return {}

def find_header_positions(all_texts):
    return find_header_positions_improved(all_texts)

def find_circle_entities(doc, radius):
    circles = []
    msp = doc.modelspace()
    for e in msp:
        if e.dxftype() == 'CIRCLE' and abs(e.dxf.radius - radius) < 0.5:
            circles.append(e)
    return circles

def find_text_in_circle(all_texts, circle_center, radius):
    texts_in_circle = []
    for text, x, y, e in all_texts:
        dist = hypot(x - circle_center[0], y - circle_center[1])
        if dist <= radius:
            texts_in_circle.append((text, x, y, e))
    return texts_in_circle

def find_entities_by_layer(doc, layer_names):
    entities = []
    msp = doc.modelspace()
    for e in msp:
        if hasattr(e, 'dxf') and hasattr(e.dxf, 'layer'):
            layer_upper = e.dxf.layer.upper()
            if any(layer_upper.startswith('TEE_') for name in layer_names if name == 'TEE_'):
                entities.append(e)
            elif layer_upper in [l.upper() for l in layer_names if l != 'TEE_']:
                entities.append(e)
    return entities

def get_entity_position(entity):
    if entity.dxftype() in ['TEXT', 'MTEXT']:
        return (entity.dxf.insert.x, entity.dxf.insert.y)
    elif entity.dxftype() == 'INSERT':
        return (entity.dxf.insert.x, entity.dxf.insert.y)
    elif entity.dxftype() == 'CIRCLE':
        return (entity.dxf.center.x, entity.dxf.center.y)
    elif entity.dxftype() == 'LINE':
        return ((entity.dxf.start.x + entity.dxf.end.x) / 2,
                (entity.dxf.start.y + entity.dxf.end.y) / 2)
    elif entity.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
        if entity.dxftype() == 'LWPOLYLINE':
            points = list(entity.get_points())
            if points:
                return (points[0][0], points[0][1])
        else:
            vertices = list(entity.vertices)
            if vertices:
                return (vertices[0].dxf.location.x, vertices[0].dxf.location.y)
    elif entity.dxftype() == 'ARC':
        return (entity.dxf.center.x, entity.dxf.center.y)
    return None

def find_circles_by_layer(doc, layer_name):
    circles = []
    msp = doc.modelspace()
    for e in msp:
        if e.dxftype() == 'CIRCLE' and hasattr(e, 'dxf') and hasattr(e.dxf, 'layer'):
            if e.dxf.layer.upper() == layer_name.upper():
                circles.append(e)
    return circles

def find_entities_touching_circle(doc, circle, layer_names):
    entities = []
    center = (circle.dxf.center.x, circle.dxf.center.y)
    radius = circle.dxf.radius
    layer_entities = find_entities_by_layer(doc, layer_names)
    for e in layer_entities:
        pos = get_entity_position(e)
        if pos:
            dist = hypot(pos[0] - center[0], pos[1] - center[1])
            if abs(dist - radius) <= 2:
                entities.append(e)
    return entities

def has_bulge(entity):
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

def find_polylines_touching_entity(doc, entity, exclude_layers=[]):
    polylines = []
    msp = doc.modelspace()
    entity_segments = []
    if entity.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
        if entity.dxftype() == 'LWPOLYLINE':
            points = list(entity.get_points())
        else:
            points = [(v.dxf.location.x, v.dxf.location.y) for v in entity.vertices]
        for i in range(len(points) - 1):
            entity_segments.append(((points[i][0], points[i][1]),
                                    (points[i+1][0], points[i+1][1])))
    elif entity.dxftype() == 'LINE':
        entity_segments.append(((entity.dxf.start.x, entity.dxf.start.y),
                                (entity.dxf.end.x, entity.dxf.end.y)))
    for e in msp:
        if e.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
            if hasattr(e.dxf, 'layer') and e.dxf.layer.upper() in [l.upper() for l in exclude_layers]:
                continue
            if has_bulge(e):
                continue
            if e.dxftype() == 'LWPOLYLINE':
                poly_points = list(e.get_points())
            else:
                poly_points = [(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]
            if 2 <= len(poly_points) <= 3:
                total_length = 0
                for i in range(len(poly_points) - 1):
                    dist = hypot(poly_points[i+1][0] - poly_points[i][0],
                                 poly_points[i+1][1] - poly_points[i][1])
                    total_length += dist
                if total_length >= 5:
                    touching = False
                    for seg_start, seg_end in entity_segments:
                        for px, py, *_ in poly_points:
                            dist = point_to_line_distance((px, py), seg_start, seg_end)
                            if dist <= 1:
                                touching = True
                                break
                        if touching:
                            break
                    if touching:
                        polylines.append(e)
    return polylines

def point_to_line_distance(point, line_start, line_end):
    px, py = point
    x1, y1 = line_start
    x2, y2 = line_end
    line_length = hypot(x2 - x1, y2 - y1)
    if line_length == 0:
        return hypot(px - x1, py - y1)
    t = max(0, min(1, ((px - x1) * (x2 - x1) + (py - y1) * (y2 - y1)) / (line_length ** 2)))
    closest_x = x1 + t * (x2 - x1)
    closest_y = y1 + t * (y2 - y1)
    return hypot(px - closest_x, py - closest_y)

def get_segment_lengths(entity):
    segments = []
    if entity.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
        if entity.dxftype() == 'LWPOLYLINE':
            points = list(entity.get_points())
        else:
            points = [(v.dxf.location.x, v.dxf.location.y) for v in entity.vertices]
        for i in range(len(points) - 1):
            start = (points[i][0], points[i][1])
            end = (points[i+1][0], points[i+1][1])
            length = hypot(end[0] - start[0], end[1] - start[1])
            segments.append({
                'start': start,
                'end': end,
                'length': length,
                'index': i
            })
    elif entity.dxftype() == 'LINE':
        start = (entity.dxf.start.x, entity.dxf.start.y)
        end = (entity.dxf.end.x, entity.dxf.end.y)
        length = hypot(end[0] - start[0], end[1] - start[1])
        segments.append({
            'start': start,
            'end': end,
            'length': length,
            'index': 0
        })
    return segments

def find_all_touching_segments(circle_center, radius, segments):
    touching_segments = []
    for seg in segments:
        dist = point_to_line_distance(circle_center, seg['start'], seg['end'])
        if abs(dist - radius) <= 3:
            contact_length = seg['length']
            touching_segments.append({
                'segment': seg,
                'contact_length': contact_length,
                'full_length': seg['length']
            })
    return touching_segments

def get_total_contact_length(circle_center, radius, segments):
    touching_segments = find_all_touching_segments(circle_center, radius, segments)
    total_length = sum(seg['contact_length'] for seg in touching_segments)
    return total_length, touching_segments

def find_pipe_entities_near_center(doc, center, search_radius):
    msp = doc.modelspace()
    pipe_entities = []
    for e in msp:
        if e.dxftype() in ['LINE', 'POLYLINE', 'LWPOLYLINE']:
            if hasattr(e, 'dxf') and hasattr(e.dxf, 'layer'):
                if 'PIPE_' in e.dxf.layer.upper():
                    point_count = 0
                    if e.dxftype() == 'LINE':
                        point_count = 2
                    elif e.dxftype() == 'LWPOLYLINE':
                        point_count = len(list(e.get_points()))
                    elif e.dxftype() == 'POLYLINE':
                        point_count = len(list(e.vertices))
                    if point_count == 2:
                        include_entity = False
                        if e.dxftype() == 'LINE':
                            start = (e.dxf.start.x, e.dxf.start.y)
                            end = (e.dxf.end.x, e.dxf.end.y)
                            dist_start = hypot(start[0] - center[0], start[1] - center[1])
                            dist_end = hypot(end[0] - center[0], end[1] - center[1])
                            if dist_start <= search_radius or dist_end <= search_radius:
                                include_entity = True
                        elif e.dxftype() == 'LWPOLYLINE':
                            points = list(e.get_points())
                            if len(points) == 2:
                                dist_start = hypot(points[0][0] - center[0], points[0][1] - center[1])
                                dist_end = hypot(points[1][0] - center[0], points[1][1] - center[1])
                                if dist_start <= search_radius or dist_end <= search_radius:
                                    include_entity = True
                        elif e.dxftype() == 'POLYLINE':
                            vertices = list(e.vertices)
                            if len(vertices) == 2:
                                dist_start = hypot(vertices[0].dxf.location.x - center[0],
                                                   vertices[0].dxf.location.y - center[1])
                                dist_end = hypot(vertices[1].dxf.location.x - center[0],
                                                 vertices[1].dxf.location.y - center[1])
                                if dist_start <= search_radius or dist_end <= search_radius:
                                    include_entity = True
                        if include_entity:
                            pipe_entities.append(e)
    return pipe_entities

def extract_wd_from_pipe_layer(layer_name):
    match = re.search(r'PIPE_(\d+)', layer_name.upper())
    if match:
        return int(match.group(1))
    return None

def extract_td_from_tee_layer(layer_name):
    match = re.search(r'TEE_(\d+)', layer_name.upper())
    if match:
        return int(match.group(1))
    return None

def find_tee_entities_touching_circle(doc, circle):
    entities = []
    center = (circle.dxf.center.x, circle.dxf.center.y)
    radius = circle.dxf.radius
    msp = doc.modelspace()
    for e in msp:
        if hasattr(e, 'dxf') and hasattr(e.dxf, 'layer'):
            layer_upper = e.dxf.layer.upper()
            if layer_upper.startswith('TEE_'):
                touching = False
                if e.dxftype() == 'LINE':
                    points = [(e.dxf.start.x, e.dxf.start.y),
                              (e.dxf.end.x, e.dxf.end.y)]
                    for px, py in points:
                        dist = hypot(px - center[0], py - center[1])
                        if abs(dist - radius) <= 2:
                            touching = True
                            break
                elif e.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
                    if e.dxftype() == 'LWPOLYLINE':
                        points = list(e.get_points())
                    else:
                        points = [(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]
                    for point in points:
                        px, py = point[0], point[1]
                        dist = hypot(px - center[0], py - center[1])
                        if abs(dist - radius) <= 2:
                            touching = True
                            break
                elif e.dxftype() == 'CIRCLE':
                    dist = hypot(e.dxf.center.x - center[0], e.dxf.center.y - center[1])
                    if abs(dist - radius) <= 2:
                        touching = True
                elif e.dxftype() in ['TEXT', 'MTEXT', 'INSERT']:
                    dist = hypot(e.dxf.insert.x - center[0], e.dxf.insert.y - center[1])
                    if abs(dist - radius) <= 2:
                        touching = True
                elif e.dxftype() == 'ARC':
                    cx, cy = e.dxf.center.x, e.dxf.center.y
                    r = e.dxf.radius
                    dist = hypot(cx - center[0], cy - center[1])
                    if abs(dist - radius) <= 2:
                        touching = True
                    else:
                        start_angle = radians(e.dxf.start_angle)
                        end_angle = radians(e.dxf.end_angle)
                        sx = cx + r * cos(start_angle)
                        sy = cy + r * sin(start_angle)
                        dist = hypot(sx - center[0], sy - center[1])
                        if abs(dist - radius) <= 2:
                            touching = True
                        if not touching:
                            ex = cx + r * cos(end_angle)
                            ey = cy + r * sin(end_angle)
                            dist = hypot(ex - center[0], ey - center[1])
                            if abs(dist - radius) <= 2:
                                touching = True
                if touching:
                    entities.append(e)
    return entities

def find_sfw_polylines_near_point(doc, point, search_radius):
    msp = doc.modelspace()
    sfw_polylines = []
    for e in msp:
        if e.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
            if hasattr(e, 'dxf') and hasattr(e.dxf, 'layer'):
                if e.dxf.layer.upper() == 'SFW':
                    if e.dxftype() == 'LWPOLYLINE':
                        points = list(e.get_points())
                        center_x = sum(p[0] for p in points) / 6
                        center_y = sum(p[1] for p in points) / 6
                        min_point_dist = float('inf')
                        for p in points:
                            dist = hypot(p[0] - point[0], p[1] - point[1])
                            min_point_dist = min(min_point_dist, dist)
                    else:
                        points = list(e.vertices)
                        center_x = sum(v.dxf.location.x for v in points) / 6
                        center_y = sum(v.dxf.location.y for v in points) / 6
                        min_point_dist = float('inf')
                        for v in points:
                            dist = hypot(v.dxf.location.x - point[0], v.dxf.location.y - point[1])
                            min_point_dist = min(min_point_dist, dist)
                    if len(points) == 6:
                        center_dist = hypot(center_x - point[0], center_y - point[1])
                        if min_point_dist <= search_radius:
                            sfw_polylines.append({
                                'entity': e,
                                'center': (center_x, center_y),
                                'center_distance': center_dist,
                                'min_point_distance': min_point_dist
                            })
    return sorted(sfw_polylines, key=lambda x: x['min_point_distance'])

def find_a2_polylines_near_sfw_center(doc, sfw_center, search_radius=5.0):
    msp = doc.modelspace()
    a2_candidates = []
    for e in msp:
        if e.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
            if hasattr(e.dxf, 'layer') and e.dxf.layer.upper() == 'PIPE':
                continue
            if has_bulge(e):
                continue
            if e.dxftype() == 'LWPOLYLINE':
                points = list(e.get_points())
            else:
                points = [(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]
            if 2 <= len(points) <= 3:
                total_length = 0
                for i in range(len(points) - 1):
                    dist = hypot(points[i+1][0] - points[i][0],
                                 points[i+1][1] - points[i][1])
                    total_length += dist
                if total_length >= 5:
                    first_point = (points[0][0], points[0][1])
                    last_point = (points[-1][0], points[-1][1])
                    dist_first = hypot(first_point[0] - sfw_center[0],
                                       first_point[1] - sfw_center[1])
                    dist_last = hypot(last_point[0] - sfw_center[0],
                                      last_point[1] - sfw_center[1])
                    if dist_first <= search_radius or dist_last <= search_radius:
                        if dist_first < dist_last:
                            far_point = last_point
                            far_dist = dist_last
                        else:
                            far_point = first_point
                            far_dist = dist_first
                        a2_candidates.append({
                            'entity': e,
                            'points': points,
                            'far_point': far_point,
                            'far_distance': far_dist,
                            'total_length': total_length
                        })
    return a2_candidates

def find_sftype_for_wno(all_texts, wno_x, wno_y):
    for text, x, y, e in all_texts:
        if (wno_x < x <= wno_x + 25 and
            abs(y - wno_y) <= 1 and
            abs(e.dxf.rotation) < 0.1):
            text_upper = text.strip().upper()
            if text_upper in ['S', 'F', 'FF']:
                return text_upper
    return None

def process_weld_data(doc, all_texts, headers, dn_x, materials_x, bore_value):
    if 'NO' not in headers:
        return {}
    msp = doc.modelspace()
    no_x, no_y = headers['NO']
    weld_data = {}
    redu_sw_data = {}
    all_sw_info = {}
    skip_wtype_search = None
    all_wno_sw_info = {}
    global_used_sw = set()
    global_used_wtype = set()
    global_used_sfw = set()
    wno_list = []
    y_positions = sorted(
        set(t[2] for t in all_texts if abs(t[1] - no_x) < 1 and t[2] < no_y and t[0].strip()),
        reverse=True
    )
    for y in y_positions:
        no_texts = [t for t in all_texts if abs(t[1] - no_x) < 1 and abs(t[2] - y) < 0.5]
        for text, x, y2, e in no_texts:
            if text.strip().isdigit():
                wno_list.append((text.strip(), x, y2, e))
                e.dxf.color = 4
    for idx, (wno, wno_x, wno_y, wno_entity) in enumerate(wno_list):
        local_used_texts = set()
        sftype = find_sftype_for_wno(all_texts, wno_x, wno_y)
        skip_wtype_for_this_wno = (skip_wtype_search is not None and int(wno) == skip_wtype_search)
        if skip_wtype_for_this_wno:
            skip_wtype_search = None
        swno_candidates = []
        for text, x, y, e in all_texts:
            if (x < materials_x - 10 and y > no_y and
                text.strip() == wno and
                abs(e.dxf.rotation) < 0.1):
                circles_3mm = find_circle_entities(doc, 3)
                for circle in circles_3mm:
                    center = (circle.dxf.center.x, circle.dxf.center.y)
                    if hypot(x - center[0], y - center[1]) <= 3:
                        swno_candidates.append((text, x, y, e, center))
                        e.dxf.color = 4
                        e.dxf.layer = 'WDNO'
                        break
        for swno_text, swno_x, swno_y, swno_entity, circle_center in swno_candidates:
            sw_circles = find_circles_by_layer(doc, 'SW')
            closest_sw_circle = None
            min_sw_dist = float('inf')
            for circle in sw_circles:
                if id(circle) in global_used_sw:
                    continue
                center = (circle.dxf.center.x, circle.dxf.center.y)
                dist = hypot(center[0] - swno_x, center[1] - swno_y)
                if dist <= 30 and dist < min_sw_dist:
                    min_sw_dist = dist
                    closest_sw_circle = circle
            if closest_sw_circle and sftype:
                if sftype == 'F':
                    closest_sw_circle.dxf.layer = 'FW'
                elif sftype == 'FF':
                    closest_sw_circle.dxf.layer = 'FFW'
            sfw_polylines = find_sfw_polylines_near_point(doc, (swno_x, swno_y), 30)
            available_sfw = []
            for sfw in sfw_polylines:
                if id(sfw['entity']) not in global_used_sfw:
                    available_sfw.append(sfw)
            use_sfw = False
            selected_sfw = None
            if available_sfw and closest_sw_circle:
                closest_sfw = available_sfw[0]
                if closest_sfw['min_point_distance'] < min_sw_dist:
                    use_sfw = True
                    selected_sfw = closest_sfw
            elif available_sfw and not closest_sw_circle:
                use_sfw = True
                selected_sfw = available_sfw[0]
            if use_sfw and selected_sfw:
                sd_entity = selected_sfw['entity']
                sd_center = selected_sfw['center']
                sd_entity.dxf.color = 1
                pipe_entities = find_pipe_entities_near_center(doc, sd_center, 13.0)
                if pipe_entities:
                    pipe_entity = pipe_entities[0]
                    wd = extract_wd_from_pipe_layer(pipe_entity.dxf.layer)
                    if wd is not None:
                        if wd > 55:
                            sw_circles_near_sfw = []
                            sw_circles = find_circles_by_layer(doc, 'SW')
                            for circle in sw_circles:
                                if id(circle) in global_used_sw:
                                    continue
                                center = (circle.dxf.center.x, circle.dxf.center.y)
                                dist = hypot(center[0] - sd_center[0], center[1] - sd_center[1])
                                if dist <= 10:
                                    sw_circles_near_sfw.append((circle, dist))
                            if sw_circles_near_sfw:
                                sw_circle, sw_dist = min(sw_circles_near_sfw, key=lambda x: x[1])
                                sw_circle.dxf.color = 1
                                if sftype == 'F':
                                    sw_circle.dxf.layer = 'FW'
                                elif sftype == 'FF':
                                    sw_circle.dxf.layer = 'FFW'
                                global_used_sw.add(id(sw_circle))
                                touching_entities = find_entities_touching_circle(doc, sw_circle, ['OLET'])
                                available_entities = []
                                for entity in touching_entities:
                                    if id(entity) not in global_used_wtype:
                                        available_entities.append(entity)
                                for wtype_entity in available_entities:
                                    wtype_entity.dxf.color = 4
                                    wtype_pos = get_entity_position(wtype_entity)
                                    global_used_wtype.add(id(wtype_entity))
                                    a2_polylines = find_polylines_touching_entity(doc, wtype_entity, exclude_layers=['PIPE'])
                                    for poly in a2_polylines:
                                        poly.dxf.color = 4
                                        if poly.dxftype() == 'LWPOLYLINE':
                                            points = list(poly.get_points())
                                        else:
                                            points = [(v.dxf.location.x, v.dxf.location.y) for v in poly.vertices]
                                        max_dist = 0
                                        far_point = None
                                        for p in points:
                                            px, py = p[0], p[1]
                                            dist = hypot(px - wtype_pos[0], py - wtype_pos[1])
                                            if dist > max_dist:
                                                max_dist = dist
                                                far_point = (px, py)
                                        if far_point:
                                            for text, x, y, e in all_texts:
                                                if hypot(x - far_point[0], y - far_point[1]) < 25:
                                                    if 'x' in text.lower() and re.search(r'\d+', text):
                                                        if id(e) not in local_used_texts:
                                                            match = re.search(r'[xX]\s*(\d+)', text)
                                                            if match:
                                                                wbore = match.group(1)
                                                                wtype = '  OLET'
                                                                weld_data[wno_y] = {
                                                                    'wbore': wbore,
                                                                    'wtype': wtype
                                                                }
                                                                local_used_texts.add(id(e))
                                                                global_used_sfw.add(id(sd_entity))
                                                                break
                                    break
                                if wno_y in weld_data:
                                    continue
                            else:
                                pass
                        else:
                            pipe_entity.dxf.color = 4
                            wbore = str(wd)
                            wtype = '  BW' if wd >= 51 else '  SW'
                            weld_data[wno_y] = {'wbore': wbore, 'wtype': wtype}
                            global_used_sfw.add(id(sd_entity))
                            continue
                else:
                    a2_polylines = find_a2_polylines_near_sfw_center(doc, sd_center, 5.0)
                    if a2_polylines:
                        a2_text_found = False
                        for idx2, a2_info in enumerate(a2_polylines):
                            a2_entity = a2_info['entity']
                            far_point = a2_info['far_point']
                            a2_entity.dxf.color = 1
                            for text, x, y, e in all_texts:
                                if hypot(x - far_point[0], y - far_point[1]) <= 30:
                                    if 'x' in text.lower() and re.search(r'\d+', text):
                                        if id(e) not in local_used_texts:
                                            match = re.search(r'[xX]\s*(\d+)', text)
                                            if match:
                                                wbore = match.group(1)
                                                wtype = '  SW'
                                                weld_data[wno_y] = {'wbore': wbore, 'wtype': wtype}
                                                local_used_texts.add(id(e))
                                                global_used_sfw.add(id(sd_entity))
                                                a2_text_found = True
                                                break
                            if a2_text_found:
                                break
                    else:
                        use_sfw = False
            if closest_sw_circle and not use_sfw:
                closest_sw_circle.dxf.color = 1
                sw_center = (closest_sw_circle.dxf.center.x, closest_sw_circle.dxf.center.y)
                sw_radius = closest_sw_circle.dxf.radius
                global_used_sw.add(id(closest_sw_circle))
                all_sw_info[int(wno)] = {
                    'circle': closest_sw_circle,
                    'center': sw_center,
                    'radius': sw_radius,
                    'wno_y': wno_y
                }
                all_wno_sw_info[wno_y] = {
                    'wno': wno,
                    'circle': closest_sw_circle,
                    'center': sw_center,
                    'radius': sw_radius
                }
                if skip_wtype_for_this_wno:
                    continue
                touching_entities = find_entities_touching_circle(doc, closest_sw_circle, ['OLET', 'WOLET', 'REDU'])
                available_entities = []
                for entity in touching_entities:
                    if id(entity) not in global_used_wtype:
                        available_entities.append(entity)
                for wtype_entity in available_entities:
                    wtype_entity.dxf.color = 4
                    wtype_found = wtype_entity.dxf.layer.upper()
                    wtype_pos = get_entity_position(wtype_entity)
                    global_used_wtype.add(id(wtype_entity))
                    if wtype_found == 'REDU':
                        skip_wtype_search = int(wno) + 1
                        segments = get_segment_lengths(wtype_entity)
                        total_length, touching_segs = get_total_contact_length(sw_center, sw_radius, segments)
                        if total_length > 0:
                            redu_key = f"{id(wtype_entity)}_{int(wno)}"
                            redu_sw_data[redu_key] = {
                                'entity': wtype_entity,
                                'segments': segments,
                                'sw_circles': [],
                                'rsize_text': None,
                                'first_wno': int(wno)
                            }
                            redu_sw_data[redu_key]['sw_circles'].append({
                                'circle': closest_sw_circle,
                                'center': sw_center,
                                'touching_segments': touching_segs,
                                'total_length': total_length,
                                'wno': wno,
                                'wno_y': wno_y,
                                'idx': idx
                            })
                    a2_polylines = find_polylines_touching_entity(doc, wtype_entity, exclude_layers=['PIPE'])
                    for poly in a2_polylines:
                        poly.dxf.color = 4
                        if poly.dxftype() == 'LWPOLYLINE':
                            points = list(poly.get_points())
                        else:
                            points = [(v.dxf.location.x, v.dxf.location.y) for v in poly.vertices]
                        max_dist = 0
                        far_point = None
                        for p in points:
                            px, py = p[0], p[1]
                            dist = hypot(px - wtype_pos[0], py - wtype_pos[1])
                            if dist > max_dist:
                                max_dist = dist
                                far_point = (px, py)
                        if far_point:
                            for text, x, y, e in all_texts:
                                if hypot(x - far_point[0], y - far_point[1]) < 25:
                                    if 'x' in text.lower() and re.search(r'\d+', text):
                                        if id(e) not in local_used_texts:
                                            if wtype_found == 'REDU':
                                                for redu_key, redu_info in redu_sw_data.items():
                                                    if redu_info['entity'] == wtype_entity and redu_info['first_wno'] == int(wno):
                                                        redu_sw_data[redu_key]['rsize_text'] = text
                                                        break
                                            wbore_match = re.search(r'[xX]\s*(\d+)', text)
                                            if wbore_match:
                                                wbore = wbore_match.group(1)
                                                if wtype_found != 'REDU':
                                                    if wtype_found == 'OLET':
                                                        final_wtype = '  OLET'
                                                    elif wtype_found == 'WOLET':
                                                        final_wtype = '  WOLET'
                                                    else:
                                                        final_wtype = wtype_found
                                                    weld_data[wno_y] = {
                                                        'wbore': wbore,
                                                        'wtype': final_wtype
                                                    }
                                                    local_used_texts.add(id(e))
                                            break
                    break
                if not available_entities:
                    pipe_entities = find_pipe_entities_near_center(doc, sw_center, 3.0)
                    if pipe_entities:
                        pipe_entity = pipe_entities[0]
                        pipe_entity.dxf.color = 4
                        wd = extract_wd_from_pipe_layer(pipe_entity.dxf.layer)
                        if wd is not None:
                            wbore = str(wd)
                            wtype = '  BW' if wd >= 51 else '  SW'
                            weld_data[wno_y] = {'wbore': wbore, 'wtype': wtype}
                            continue
                    ng2_list = []
                    for e in msp:
                        if e.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
                            if hasattr(e.dxf, 'layer') and e.dxf.layer.upper() == 'PIPE':
                                continue
                            if has_bulge(e):
                                continue
                            if e.dxftype() == 'LWPOLYLINE':
                                poly_points = list(e.get_points())
                            else:
                                poly_points = [(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]
                            if 2 <= len(poly_points) <= 3:
                                center_x = sum(p[0] for p in poly_points) / len(poly_points)
                                center_y = sum(p[1] for p in poly_points) / len(poly_points)
                                center_to_sw = hypot(center_x - sw_center[0], center_y - sw_center[1])
                                touching = False
                                min_dist_to_circle = float('inf')
                                if center_to_sw <= 2:
                                    touching = True
                                    min_dist_to_circle = center_to_sw
                                for p in poly_points:
                                    px, py = p[0], p[1]
                                    dist = hypot(px - sw_center[0], py - sw_center[1])
                                    dist_to_circle = abs(dist - sw_radius)
                                    min_dist_to_circle = min(min_dist_to_circle, dist_to_circle)
                                    if dist_to_circle <= 1:
                                        touching = True
                                if touching:
                                    length_sum = 0
                                    segments = []
                                    for i in range(len(poly_points) - 1):
                                        p1 = (poly_points[i][0], poly_points[i][1])
                                        p2 = (poly_points[i+1][0], poly_points[i+1][1])
                                        length = hypot(p2[0] - p1[0], p2[1] - p1[1])
                                        length_sum += length
                                        segments.append(length)
                                    if length_sum > 10:
                                        max_dist_from_sw = 0
                                        far_point = None
                                        for p in poly_points:
                                            px, py = p[0], p[1]
                                            dist = hypot(px - sw_center[0], py - sw_center[1])
                                            if dist > max_dist_from_sw:
                                                max_dist_from_sw = dist
                                                far_point = (px, py)
                                        ng2_info = {
                                            'entity': e,
                                            'points': [(p[0], p[1]) for p in poly_points],
                                            'length_sum': length_sum,
                                            'far_point': far_point,
                                            'max_dist': max_dist_from_sw,
                                            'min_dist_to_circle': min_dist_to_circle
                                        }
                                        ng2_list.append(ng2_info)
                                        e.dxf.color = 4
                    if ng2_list:
                        text_found = False
                        for idx3, ng2_info in enumerate(ng2_list):
                            for text, x, y, e in all_texts:
                                if hypot(x - ng2_info['far_point'][0], y - ng2_info['far_point'][1]) < 25:
                                    if 'x' in text.lower() and re.search(r'\d+', text):
                                        if id(e) not in local_used_texts:
                                            wbore_match = re.search(r'[xX]\s*(\d+)', text)
                                            if wbore_match:
                                                wbore = wbore_match.group(1)
                                                wtype = '  SW' if int(wbore) < 51 else '  BW'
                                                if not text_found:
                                                    weld_data[wno_y] = {'wbore': wbore, 'wtype': wtype}
                                                    text_found = True
                                                    local_used_texts.add(id(e))
                            if not text_found and idx3 == len(ng2_list) - 1:
                                pass
                        if text_found:
                            pass
                    else:
                        pass
            else:
                pass
    for redu_key, redu_info in redu_sw_data.items():
        first_wno = redu_info['first_wno']
        first_sw = all_sw_info.get(first_wno)
        second_sw = all_sw_info.get(first_wno + 1)
        if first_sw and second_sw and redu_info['rsize_text']:
            first_total_length, first_touching_segs = get_total_contact_length(
                first_sw['center'],
                first_sw['radius'],
                redu_info['segments']
            )
            second_total_length, second_touching_segs = get_total_contact_length(
                second_sw['center'],
                second_sw['radius'],
                redu_info['segments']
            )
            if first_total_length > 0 and second_total_length > 0:
                rsize_match = re.search(r'(\d+)\s*[xX]\s*(\d+)', redu_info['rsize_text'])
                if rsize_match:
                    bore_before_x = rsize_match.group(1)
                    bore_after_x = rsize_match.group(2)
                    if first_total_length > second_total_length:
                        first_wbore = bore_before_x
                        second_wbore = bore_after_x
                    else:
                        first_wbore = bore_after_x
                        second_wbore = bore_before_x
                    first_wtype = '  BW' if int(first_wbore) >= 51 else '  SW'
                    weld_data[first_sw['wno_y']] = {'wbore': first_wbore, 'wtype': first_wtype}
                    second_wtype = '  BW' if int(second_wbore) >= 51 else '  SW'
                    weld_data[second_sw['wno_y']] = {'wbore': second_wbore, 'wtype': second_wtype}
                else:
                    pass
            else:
                pass
        else:
            pass
    for wno_y, sw_info in all_wno_sw_info.items():
        wno = sw_info['wno']
        sw_circle = sw_info['circle']
        tee_entities = find_tee_entities_touching_circle(doc, sw_circle)
        for tee_entity in tee_entities:
            layer_name = tee_entity.dxf.layer.upper()
            if layer_name.startswith('TEE_'):
                td = extract_td_from_tee_layer(layer_name)
                if td is not None:
                    wbore = str(td)
                    wtype = '  BW' if td >= 51 else '  SW'
                    weld_data[wno_y] = {'wbore': wbore, 'wtype': wtype}
                    tee_entity.dxf.color = 4
                    break
    return weld_data

def modify_fld_column(doc, all_texts, headers):
    if 'NO' not in headers or '/FLD' not in headers:
        return
    msp = doc.modelspace()
    no_x, no_y = headers['NO']
    fld_x, fld_y = headers['/FLD']
    y_positions = sorted(
        set(t[2] for t in all_texts if abs(t[1] - no_x) < 1 and t[2] < no_y and t[0].strip()),
        reverse=True
    )
    for y in y_positions:
        fld_texts = [t for t in all_texts if abs(t[1] - fld_x) < 1 and abs(t[2] - y) < 0.5]
        for text, x, y2, e in fld_texts:
            val = text.strip().upper()
            if val in ['F', 'S']:
                new_val = val + 'W'
                try:
                    msp.delete_entity(e)
                    msp.add_text(new_val, dxfattribs={'height': 2.5, 'insert': (x + 5, y2)})
                except:
                    continue

def modify_table_with_weld_data(doc, all_texts, bore_value, headers, dn_x, weld_data):
    if 'NO' not in headers or dn_x is None:
        return
    msp = doc.modelspace()
    no_x, no_y = headers['NO']
    type_x = headers.get('TYPE', (None, None))[0]
    header_y = no_y
    y_positions = sorted(
        set(t[2] for t in all_texts if abs(t[1] - no_x) < 1 and t[2] < header_y and t[0].strip()),
        reverse=True
    )
    for y in y_positions:
        existing = [t for t in all_texts if abs(t[1] - dn_x) < 1 and abs(t[2] - y) < 0.5]
        for t in existing:
            try:
                msp.delete_entity(t[3])
            except:
                continue
        if y in weld_data and 'wbore' in weld_data[y]:
            output_bore = weld_data[y]['wbore']
            color = 4
        else:
            output_bore = str(bore_value)
            color = 2
        msp.add_text(output_bore, dxfattribs={
            'height': 2.5,
            'insert': (dn_x + 5, y),
            'color': color
        })
        if type_x is not None:
            type_texts = [t for t in all_texts if abs(t[1] - type_x) < 1 and abs(t[2] - y) < 0.5]
            for t in type_texts:
                try:
                    msp.delete_entity(t[3])
                except:
                    continue
            if y in weld_data and 'wtype' in weld_data[y]:
                type_str = weld_data[y]['wtype']
                color = 4
            else:
                check_bore = int(weld_data[y]['wbore']) if y in weld_data and 'wbore' in weld_data[y] else bore_value
                type_str = "  BW" if check_bore >= 65 else "  SW"
                color = 2
            msp.add_text(type_str, dxfattribs={
                'height': 2.5,
                'insert': (type_x + 3, y),
                'color': color
            })

def get_table_bounds(headers, dn_x, all_texts):
    xs = [headers[k][0] for k in headers] + ([dn_x] if dn_x else [])
    min_x = min(xs) - 20
    max_x = max(xs) + 20
    no_x, no_y = headers['NO']
    ys = [t[2] for t in all_texts if abs(t[1] - no_x) < 1 and t[2] < no_y and t[0].strip().isdigit()]
    min_y = min(ys) - 10 if ys else no_y - 100
    max_y = no_y + 15
    return min_x, max_x, min_y, max_y

def check_polyline_length_near_no(doc, headers):
    if 'NO' not in headers:
        return False
    no_x, no_y = headers['NO']
    msp = doc.modelspace()
    for e in msp:
        if e.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
            if e.dxftype() == 'LWPOLYLINE':
                points = list(e.get_points())
            else:
                points = [(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]
            if len(points) != 2:
                continue
            start_point = (points[0][0], points[0][1])
            end_point = (points[1][0], points[1][1])
            start_in_range = (abs(start_point[0] - no_x) <= 7 and abs(start_point[1] - no_y) <= 7)
            end_in_range = (abs(end_point[0] - no_x) <= 7 and abs(end_point[1] - no_y) <= 7)
            if start_in_range or end_in_range:
                total_length = hypot(end_point[0] - start_point[0],
                                     end_point[1] - start_point[1])
                if total_length < 71:
                    return True
    return False

def stretch_entities(doc, bounds):
    min_x, max_x, min_y, max_y = bounds
    msp = doc.modelspace()
    for e in list(msp):
        if not hasattr(e, "dxf"):
            continue
        try:
            if e.dxftype() in ['TEXT', 'MTEXT']:
                p = e.dxf.insert
                if min_x <= p.x <= max_x and min_y <= p.y <= max_y:
                    e.dxf.insert = (p.x + 25, p.y)
            elif e.dxftype() == 'LWPOLYLINE':
                new_points = []
                for x, y, *rest in e.get_points():
                    if min_x <= x <= max_x and min_y <= y <= max_y:
                        x += 25
                    new_points.append((x, y, *rest))
                e.set_points(new_points)
            elif e.dxftype() == 'POLYLINE':
                for v in e.vertices:
                    loc = v.dxf.location
                    if min_x <= loc.x <= max_x and min_y <= loc.y <= max_y:
                        v.dxf.location = (loc.x + 25, loc.y)
            elif e.dxftype() == 'LINE':
                start = e.dxf.start
                end = e.dxf.end
                if min_x <= start.x <= max_x and min_y <= start.y <= max_y:
                    start = (start.x + 25, start.y)
                if min_x <= end.x <= max_x and min_y <= end.y <= max_y:
                    end = (end.x + 25, end.y)
                e.dxf.start = start
                e.dxf.end = end
        except Exception:
            continue

def apply_final_formatting(doc):
    msp = doc.modelspace()
    for txt in msp.query('TEXT'):
        if txt.dxf.color != 4:
            txt.dxf.color = 2
        txt.dxf.style = "ARIAL"
        txt.dxf.width = 0.86
    if "ARIAL" not in doc.styles:
        doc.styles.new("ARIAL", dxfattribs={"font": "arial.ttf"})

def process_dxf_file(filepath):
    doc = ezdxf.readfile(filepath)
    all_texts = get_texts_by_position(extract_text_entities(doc))
    processing_completed = False
    materials_x = None
    for text, x, y, _ in all_texts:
        if "FABRICATION MATERIAL" in text.upper():
            materials_x = x
            break
    if materials_x is None:
        for text, x, y, _ in all_texts:
            if "ERECTION MATERIAL" in text.upper():
                materials_x = x
                break
    size_text_value = find_size_value_near_materials(all_texts)
    if not size_text_value:
        bore_value = 100
    else:
        bore_value = extract_bore_from_size(size_text_value)
        processing_completed = True
    dn_x = find_dn_header_x(all_texts)
    if dn_x is not None:
        processing_completed = True
    headers = find_header_positions(all_texts)
    weld_data = {}
    if materials_x and headers:
        weld_data = process_weld_data(doc, all_texts, headers, dn_x, materials_x, bore_value)
        if weld_data:
            processing_completed = True
    if headers and dn_x:
        modify_table_with_weld_data(doc, all_texts, bore_value, headers, dn_x, weld_data)
        processing_completed = True
    if headers:
        modify_fld_column(doc, all_texts, headers)
        processing_completed = True
    if headers and dn_x:
        skip_stretch = check_polyline_length_near_no(doc, headers)
        if not skip_stretch:
            bounds = get_table_bounds(headers, dn_x, all_texts)
            stretch_entities(doc, bounds)
            processing_completed = True
    apply_final_formatting(doc)
    new_filename = os.path.splitext(filepath)[0] + "_wt.dxf"
    doc.saveas(new_filename)

def main():
    dxf_files = get_selected_dxf_files()
    if not dxf_files:
        return
    for dxf in dxf_files:
        try:
            process_dxf_file(dxf)
        except Exception:
            try:
                time.sleep(0.5)
                new_filename = os.path.splitext(dxf)[0] + "_wt.dxf"
                shutil.copy2(dxf, new_filename)
            except Exception:
                pass

if __name__ == "__main__":
    main()
