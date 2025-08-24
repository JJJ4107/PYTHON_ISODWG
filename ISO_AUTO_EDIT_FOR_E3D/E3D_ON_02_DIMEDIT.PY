import os
import sys
import ezdxf
import math
import numpy as np
from ezdxf.entities import Line, LWPolyline, Polyline, Text

# ─────────────── 설정 값 ───────────────
ANGLE_TOLERANCE = 5.0  # 각도 허용 오차 (°)
DIM_LAYER_PREFIXES = ("GT_", "PL2")  # 치수선 레이어 접두사들

# TBOX 캐시를 위한 전역 딕셔너리
TBOX_CACHE = {}

# ─────────────── 유틸 함수 ───────────────
def to2d(pt):
    if hasattr(pt, "__getitem__"):
        return np.array((pt[0], pt[1]), float)
    return np.array((pt.x, pt.y), float)

def distance(a, b):
    return float(np.linalg.norm(a - b))

def angle_deg(a, b):
    dx, dy = b - a
    return (math.degrees(math.atan2(dy, dx)) + 360) % 360

def get_entity_handle(entity):
    try:
        if hasattr(entity, 'dxf') and hasattr(entity.dxf, 'handle'):
            return entity.dxf.handle
        elif hasattr(entity, 'handle'):
            return entity.handle
        else:
            return str(id(entity))
    except:
        return "unknown"

def extract_segments(ent):
    if isinstance(ent, Line):
        return [(ent.dxf.start, ent.dxf.end)]
    if isinstance(ent, LWPolyline):
        pts = list(ent.get_points("xyb"))
        z = ent.dxf.elevation
        return [
            ((x0, y0, z), (x1, y1, z)) for (x0, y0, _), (x1, y1, _) in zip(pts, pts[1:])
        ]
    if isinstance(ent, Polyline):
        verts = list(ent.vertices)
        return [
            (verts[i].dxf.location, verts[i + 1].dxf.location)
            for i in range(len(verts) - 1)
        ]
    return []

def is_enclosed(point, msp):
    x, y = float(point[0]), float(point[1])
    for entity in msp.query("LWPOLYLINE POLYLINE"):
        try:
            if not entity.is_closed:
                continue
        except Exception:
            continue
        if hasattr(entity, 'get_points'):
            points = list(entity.get_points("xy"))
        else:
            points = [(v.dxf.location[0], v.dxf.location[1]) for v in entity.vertices]
        if len(points) < 3:
            continue
        if point_in_polygon(x, y, points):
            return True
    return False

def point_in_polygon(x, y, polygon_points):
    n = len(polygon_points)
    inside = False
    p1x, p1y = polygon_points[0]
    for i in range(1, n + 1):
        p2x, p2y = polygon_points[i % n]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y
    return inside

def point_to_line_distance(point, line_start, line_end):
    line_vec = line_end - line_start
    line_length_sq = np.dot(line_vec, line_vec)
    if line_length_sq == 0:
        return distance(point, line_start)
    point_vec = point - line_start
    t = np.dot(point_vec, line_vec) / line_length_sq
    t = max(0, min(1, t))
    closest_point = line_start + t * line_vec
    return distance(point, closest_point)

# ─────────────── TBOX 관련 함수 ───────────────
def get_text_key(txt):
    try:
        handle = get_entity_handle(txt)
        if hasattr(txt.dxf, 'insert'):
            pos = txt.dxf.insert
            return f"{handle}_{pos[0]}_{pos[1]}"
        return handle
    except:
        return str(id(txt))

def create_tbox(txt):
    text_key = get_text_key(txt)
    if text_key in TBOX_CACHE:
        return TBOX_CACHE[text_key]
    if hasattr(txt.dxf, 'insert') and txt.dxf.insert is not None:
        txt_pt = to2d(txt.dxf.insert)
    elif hasattr(txt.dxf, 'align_point') and txt.dxf.align_point is not None:
        txt_pt = to2d(txt.dxf.align_point)
    else:
        return None
    text_length, text_height = get_text_dimensions(txt)
    tbox_left = txt_pt[0]
    tbox_right = txt_pt[0] + text_length
    tbox_bottom = txt_pt[1]
    tbox_top = txt_pt[1] + text_height
    move_x = text_length / 2.0
    tbox_left += move_x
    tbox_right += move_x
    tbox_corners = [
        np.array([tbox_left, tbox_bottom]),
        np.array([tbox_right, tbox_bottom]),
        np.array([tbox_right, tbox_top]),
        np.array([tbox_left, tbox_top])
    ]
    tbox_info = {
        'corners': tbox_corners,
        'left': tbox_left,
        'right': tbox_right,
        'bottom': tbox_bottom,
        'top': tbox_top,
        'text_length': text_length,
        'text_height': text_height,
        'original_position': txt_pt
    }
    TBOX_CACHE[text_key] = tbox_info
    return tbox_info

def clear_tbox_cache():
    global TBOX_CACHE
    TBOX_CACHE = {}

# ─────────────── DB1, CH1 시스템 함수들 ───────────────
def find_dim_pairs_optimized(all_line_entities):
    two_point_entities = []
    for ent in all_line_entities:
        try:
            if not ent.dxf.layer.startswith(DIM_LAYER_PREFIXES):
                continue
            segments = extract_segments(ent)
            if len(segments) != 1:
                continue
            p0, p1 = segments[0]
            v0, v1 = to2d(p0), to2d(p1)
            length = distance(v0, v1)
            if 1.5 <= length <= 12:
                two_point_entities.append((ent, v0, v1, length))
        except Exception:
            continue

    dim_pairs = []
    overlapped_entities = []
    close_tolerance = 0.2
    far_threshold = 3.0
    tolerance_len = 0.5

    for i in range(len(two_point_entities)):
        for j in range(i + 1, len(two_point_entities)):
            ent1, v0_1, v1_1, len1 = two_point_entities[i]
            ent2, v0_2, v1_2, len2 = two_point_entities[j]
            length_diff = abs(len1 - len2)
            if length_diff > tolerance_len:
                continue

            connection_cases = [
                (v0_1, v0_2, v1_1, v1_2, "v0_1-v0_2"),
                (v0_1, v1_2, v1_1, v0_2, "v0_1-v1_2"),
                (v1_1, v0_2, v0_1, v1_2, "v1_1-v0_2"),
                (v1_1, v1_2, v0_1, v0_2, "v1_1-v1_2"),
            ]

            valid_pair_found = False
            overlap_found = False

            for close_pt1, close_pt2, far_pt1, far_pt2, case_name in connection_cases:
                try:
                    close_dist = distance(close_pt1, close_pt2)
                    far_dist = distance(far_pt1, far_pt2)
                except Exception:
                    continue

                if close_dist <= close_tolerance:
                    if far_dist <= close_tolerance:
                        if ent1 not in overlapped_entities:
                            ent1.dxf.color = 3
                            overlapped_entities.append(ent1)
                        if ent2 not in overlapped_entities:
                            ent2.dxf.color = 3
                            overlapped_entities.append(ent2)
                        overlap_found = True
                        break
                    elif far_dist >= far_threshold:
                        if case_name == "v0_1-v0_2":
                            vec1 = v1_1 - v0_1
                            vec2 = v1_2 - v0_2
                            dim1_common, dim1_opposite = v0_1, v1_1
                            dim2_common, dim2_opposite = v0_2, v1_2
                        elif case_name == "v0_1-v1_2":
                            vec1 = v1_1 - v0_1
                            vec2 = v0_2 - v1_2
                            dim1_common, dim1_opposite = v0_1, v1_1
                            dim2_common, dim2_opposite = v1_2, v0_2
                        elif case_name == "v1_1-v0_2":
                            vec1 = v0_1 - v1_1
                            vec2 = v1_2 - v0_2
                            dim1_common, dim1_opposite = v1_1, v0_1
                            dim2_common, dim2_opposite = v0_2, v1_2
                        else:
                            vec1 = v0_1 - v1_1
                            vec2 = v0_2 - v1_2
                            dim1_common, dim1_opposite = v1_1, v0_1
                            dim2_common, dim2_opposite = v1_2, v0_2

                        dot_product = np.dot(vec1, vec2)
                        if dot_product < 0:
                            if ent1 not in overlapped_entities and ent2 not in overlapped_entities:
                                dim_pairs.append({
                                    'DIM1': ent1, 'DIM1_common': dim1_common, 'DIM1_opposite': dim1_opposite,
                                    'DIM2': ent2, 'DIM2_common': dim2_common, 'DIM2_opposite': dim2_opposite,
                                    'common_point': (close_pt1 + close_pt2) / 2,
                                    'length': (len1 + len2) / 2
                                })
                                valid_pair_found = True
                                break
                if valid_pair_found or overlap_found:
                    break

            if not overlap_found and not valid_pair_found:
                reverse_dist1 = distance(v0_1, v1_2)
                reverse_dist2 = distance(v1_1, v0_2)
                if reverse_dist1 <= close_tolerance and reverse_dist2 <= close_tolerance:
                    if ent1 not in overlapped_entities:
                        ent1.dxf.color = 3
                        overlapped_entities.append(ent1)
                    if ent2 not in overlapped_entities:
                        ent2.dxf.color = 3
                        overlapped_entities.append(ent2)
    return dim_pairs, overlapped_entities

def find_arrow_entities_optimized(all_line_entities, point, tolerance=0.5):
    arrows = []
    for ent in all_line_entities:
        try:
            if not ent.dxf.layer.startswith(DIM_LAYER_PREFIXES):
                continue
            if isinstance(ent, LWPolyline):
                points = list(ent.get_points("xy"))
            elif isinstance(ent, Polyline):
                points = [v.dxf.location for v in ent.vertices]
            else:
                continue
            if len(points) != 3:
                continue
            pts = [to2d(p) for p in points]
            min_dist_to_point = min(distance(pt, point) for pt in pts)
            if min_dist_to_point <= tolerance:
                arrows.append(ent)
        except Exception:
            continue
    return arrows

def find_ad3_entities_optimized(all_line_entities, dim_pair, ad1_entities, ad2_entities, tolerance=0.5):
    ad3_candidates = []
    common_point = dim_pair['common_point']
    dim1_common = dim_pair['DIM1_common']
    dim1_opposite = dim_pair['DIM1_opposite']
    dim2_common = dim_pair['DIM2_common']
    dim2_opposite = dim_pair['DIM2_opposite']
    dim_far_endpoints = [dim1_opposite, dim2_opposite]
    excluded_handles = set()
    for ad1 in ad1_entities:
        excluded_handles.add(get_entity_handle(ad1))
    for ad2 in ad2_entities:
        excluded_handles.add(get_entity_handle(ad2))

    for ent in all_line_entities:
        try:
            if not (ent.dxf.layer.startswith(DIM_LAYER_PREFIXES) or ent.dxf.layer.upper() == "ARROW"):
                continue
            if get_entity_handle(ent) in excluded_handles:
                continue
            if isinstance(ent, LWPolyline):
                points = list(ent.get_points("xy"))
            elif isinstance(ent, Polyline):
                points = [v.dxf.location for v in ent.vertices]
            else:
                continue
            if len(points) != 3:
                continue
            pts = [to2d(p) for p in points]
            if ent.dxf.layer.upper() == "ARROW":
                is_near_far_endpoint = False
                for pt in pts:
                    for far_endpoint in dim_far_endpoints:
                        if distance(pt, far_endpoint) <= 0.5:
                            is_near_far_endpoint = True
                            break
                    if is_near_far_endpoint:
                        break
                if is_near_far_endpoint:
                    continue
            min_dist_to_cp = min(distance(pt, common_point) for pt in pts)
            if min_dist_to_cp <= tolerance:
                ad3_candidates.append((ent, min_dist_to_cp))
        except Exception:
            continue

    if ad3_candidates:
        ad3_candidates.sort(key=lambda x: x[1])
        return [ad3_candidates[0][0]]
    return []

def find_ad3_touching_dims(all_line_entities, dim1_ent, dim2_ent, ad1_entities, ad2_entities, tolerance=0.2):
    touching_ad3 = []
    dim1_segments = extract_segments(dim1_ent)
    dim2_segments = extract_segments(dim2_ent)
    if not dim1_segments or not dim2_segments:
        return []
    dim1_start, dim1_end = to2d(dim1_segments[0][0]), to2d(dim1_segments[0][1])
    dim2_start, dim2_end = to2d(dim2_segments[0][0]), to2d(dim2_segments[0][1])
    dim_endpoints = [dim1_start, dim1_end, dim2_start, dim2_end]
    excluded_handles = {get_entity_handle(dim1_ent), get_entity_handle(dim2_ent)}
    for ad1 in ad1_entities:
        excluded_handles.add(get_entity_handle(ad1))
    for ad2 in ad2_entities:
        excluded_handles.add(get_entity_handle(ad2))

    for ent in all_line_entities:
        try:
            if ent.dxf.layer.upper() != "GT_1":
                continue
            if get_entity_handle(ent) in excluded_handles:
                continue
            if isinstance(ent, LWPolyline):
                points = list(ent.get_points("xy"))
            elif isinstance(ent, Polyline):
                points = [v.dxf.location for v in ent.vertices]
            else:
                continue
            if len(points) != 3:
                continue
            pts = [to2d(p) for p in points]
            is_near_endpoint = False
            for pt in pts:
                for endpoint in dim_endpoints:
                    if distance(pt, endpoint) <= 0.5:
                        is_near_endpoint = True
                        break
                if is_near_endpoint:
                    break
            if is_near_endpoint:
                continue
            is_touching = False
            for pt in pts:
                dist_to_dim1 = point_to_line_distance(pt, dim1_start, dim1_end)
                dist_to_dim2 = point_to_line_distance(pt, dim2_start, dim2_end)
                if dist_to_dim1 <= tolerance or dist_to_dim2 <= tolerance:
                    is_touching = True
                    break
            if is_touching:
                touching_ad3.append(ent)
        except Exception:
            continue
    return touching_ad3

def find_arrow_lines_touching_ad3(all_line_entities, ad3_entities, tolerance=0.1):
    arrow_lines_to_delete = []
    ad3_points = []
    for ad3 in ad3_entities:
        try:
            if isinstance(ad3, LWPolyline):
                points = list(ad3.get_points("xy"))
            elif isinstance(ad3, Polyline):
                points = [v.dxf.location for v in ad3.vertices]
            else:
                continue
            for p in points:
                ad3_points.append(to2d(p))
        except Exception:
            continue
    for ent in all_line_entities:
        if not isinstance(ent, Line):
            continue
        try:
            if ent.dxf.layer.upper() != "ARROW":
                continue
            segments = extract_segments(ent)
            if not segments:
                continue
            p0, p1 = segments[0]
            v0, v1 = to2d(p0), to2d(p1)
            line_length = distance(v0, v1)
            if line_length > 1.0:
                continue
            is_touching_ad3 = False
            for ad3_pt in ad3_points:
                if distance(v0, ad3_pt) <= tolerance or distance(v1, ad3_pt) <= tolerance:
                    is_touching_ad3 = True
                    break
            if is_touching_ad3:
                arrow_lines_to_delete.append(ent)
        except Exception:
            continue
    return arrow_lines_to_delete

def find_g1_entities_optimized_with_all_dims(all_line_entities, dim1_ent, dim2_ent, dim_pair, all_used_dim_handles, tolerance=0.2):
    g1_candidates = []
    dim1_segments = extract_segments(dim1_ent)
    dim2_segments = extract_segments(dim2_ent)
    if not dim1_segments or not dim2_segments:
        return []
    dim1_start, dim1_end = to2d(dim1_segments[0][0]), to2d(dim1_segments[0][1])
    dim2_start, dim2_end = to2d(dim2_segments[0][0]), to2d(dim2_segments[0][1])
    common_point = dim_pair['common_point']
    dim1_common = dim_pair['DIM1_common']
    dim1_opposite = dim_pair['DIM1_opposite']
    dim2_common = dim_pair['DIM2_common']
    dim2_opposite = dim_pair['DIM2_opposite']

    for ent in all_line_entities:
        try:
            if not ent.dxf.layer.startswith(DIM_LAYER_PREFIXES):
                continue
            if get_entity_handle(ent) in all_used_dim_handles:
                continue
            segments = extract_segments(ent)
            if len(segments) != 1:
                continue
            p0, p1 = segments[0]
            v0, v1 = to2d(p0), to2d(p1)
            min_dist_to_far_ends = min(
                distance(v0, dim1_opposite), distance(v1, dim1_opposite),
                distance(v0, dim2_opposite), distance(v1, dim2_opposite)
            )
            far_end_exclusion_distance = 0.5
            if min_dist_to_far_ends <= far_end_exclusion_distance:
                continue
            min_dist_to_valid_area = float('inf')
            for g1_pt in [v0, v1]:
                dist_to_common = distance(g1_pt, common_point)
                if dist_to_common < min_dist_to_valid_area:
                    min_dist_to_valid_area = dist_to_common
            for g1_pt in [v0, v1]:
                dist_to_dim1_common = distance(g1_pt, dim1_common)
                dist_to_dim1_line = point_to_line_distance(g1_pt, dim1_start, dim1_end)
                min_dist_dim1 = min(dist_to_dim1_common, dist_to_dim1_line)
                if min_dist_dim1 < min_dist_to_valid_area:
                    min_dist_to_valid_area = min_dist_dim1
            for g1_pt in [v0, v1]:
                dist_to_dim2_common = distance(g1_pt, dim2_common)
                dist_to_dim2_line = point_to_line_distance(g1_pt, dim2_start, dim2_end)
                min_dist_dim2 = min(dist_to_dim2_common, dist_to_dim2_line)
                if min_dist_dim2 < min_dist_to_valid_area:
                    min_dist_to_valid_area = min_dist_dim2
            if min_dist_to_valid_area <= tolerance:
                g1_candidates.append((ent, v0, v1, min_dist_to_valid_area))
        except Exception:
            continue
    if g1_candidates:
        g1_candidates.sort(key=lambda x: x[3])
        closest_g1 = g1_candidates[0]
        return [(closest_g1[0], closest_g1[1], closest_g1[2])]
    return []

def find_ct_texts(msp, g1_entities, text_entities, dim_pair, search_radius=10.0):
    ct_texts = []
    common_point = dim_pair['common_point']
    for g1_ent, v0, v1 in g1_entities:
        dist_to_common_v0 = distance(v0, common_point)
        dist_to_common_v1 = distance(v1, common_point)
        search_point = v0 if dist_to_common_v0 > dist_to_common_v1 else v1
        candidates = []
        for txt in text_entities:
            try:
                if hasattr(txt.dxf, 'color') and txt.dxf.color == 1:
                    continue
                if hasattr(txt.dxf, 'layer') and 'WDNO' in txt.dxf.layer.upper():
                    continue
                if hasattr(txt.dxf, 'insert') and txt.dxf.insert is not None:
                    txt_pt = to2d(txt.dxf.insert)
                elif (hasattr(txt.dxf, 'align_point') and txt.dxf.align_point is not None):
                    txt_pt = to2d(txt.dxf.align_point)
                else:
                    continue
            except:
                continue
            dist = distance(txt_pt, search_point)
            if dist > search_radius:
                continue
            rotation = float(getattr(txt.dxf, "rotation", 0.0))
            if abs(rotation) > 0.1:
                continue
            text_val = txt.plain_text() if hasattr(txt, "plain_text") else txt.dxf.text
            if not text_val.isdigit():
                continue
            try:
                text_numeric_value = int(text_val)
                if text_numeric_value <= 10:
                    continue
            except:
                continue
            if is_enclosed(txt_pt, msp):
                continue
            tbox_info = create_tbox(txt)
            if tbox_info is None:
                continue
            min_dist_to_tbox = min(distance(search_point, corner) for corner in tbox_info['corners'])
            candidates.append((min_dist_to_tbox, txt, text_numeric_value, tbox_info))
        if candidates:
            candidates.sort(key=lambda x: x[0])
            selected_candidate = candidates[0]
            closest_txt = selected_candidate[1]
            ct_texts.append(closest_txt)
            break
    return ct_texts

def get_text_dimensions(txt):
    try:
        if txt.dxftype() == "TEXT":
            text_val = txt.dxf.text
            height = float(txt.dxf.height)
            char_width = height * 0.6
            text_length = len(text_val) * char_width
            return text_length, height
        elif txt.dxftype() == "MTEXT":
            text_val = txt.plain_text() if hasattr(txt, "plain_text") else txt.dxf.text
            height = float(txt.dxf.char_height) if hasattr(txt.dxf, 'char_height') else 1.0
            char_width = height * 0.6
            text_length = len(text_val) * char_width
            return text_length, height
    except Exception:
        return 0.0, 0.0
    return 0.0, 0.0

def check_ct_dim_interference(ct_position, text_length, text_height, dim1_start, dim1_end, dim2_start, dim2_end):
    interference_threshold = text_height * 0.6
    dist_to_dim1 = point_to_line_distance(ct_position, dim1_start, dim1_end)
    dist_to_dim2 = point_to_line_distance(ct_position, dim2_start, dim2_end)
    dim1_interference = dist_to_dim1 < interference_threshold
    dim2_interference = dist_to_dim2 < interference_threshold
    return dim1_interference or dim2_interference, dist_to_dim1, dist_to_dim2

def calculate_chain_direction(dim1_ent, dim2_ent):
    dim1_segments = extract_segments(dim1_ent)
    if dim1_segments:
        p0, p1 = dim1_segments[0]
        v0, v1 = to2d(p0), to2d(p1)
        chain_dir = angle_deg(v0, v1)
        return chain_dir
    return 0.0

def calculate_text_angle(chain_dir):
    angle = chain_dir % 360
    if abs(angle - 90) <= ANGLE_TOLERANCE or abs(angle - 270) <= ANGLE_TOLERANCE:
        angle = 90.0
    else:
        if 90 < angle < 270:
            angle = (angle + 180) % 360
    return angle

def find_parallel_polylines_for_ang(msp, dim_pair, tolerance=0.5):
    dim1_opposite = dim_pair['DIM1_opposite']
    dim2_opposite = dim_pair['DIM2_opposite']
    excluded_handles = {
        get_entity_handle(dim_pair['DIM1']),
        get_entity_handle(dim_pair['DIM2'])
    }
    search_points = [dim1_opposite, dim2_opposite]
    found_polylines = []
    for search_point in search_points:
        for ent in msp.query("LWPOLYLINE POLYLINE"):
            try:
                if not ent.dxf.layer.startswith(DIM_LAYER_PREFIXES):
                    continue
                if get_entity_handle(ent) in excluded_handles:
                    continue
                if isinstance(ent, LWPolyline):
                    points = list(ent.get_points("xy"))
                else:
                    points = [v.dxf.location for v in ent.vertices]
                if len(points) != 2:
                    continue
                pts = [to2d(p) for p in points]
                min_distance = min(distance(pt, search_point) for pt in pts)
                if min_distance <= tolerance:
                    polyline_angle = angle_deg(pts[0], pts[1])
                    found_polylines.append((ent, polyline_angle, min_distance, search_point))
            except Exception:
                continue
    if found_polylines:
        found_polylines.sort(key=lambda x: x[2])
        closest_polyline = found_polylines[0]
        ang_angle = closest_polyline[1]
        return ang_angle
    else:
        return 0.0

def find_and_color_ct1_polylines(msp, dim_pair, tolerance=0.5):
    dim1_common = dim_pair['DIM1_common']
    dim1_opposite = dim_pair['DIM1_opposite']
    excluded_handles = {
        get_entity_handle(dim_pair['DIM1']),
        get_entity_handle(dim_pair['DIM2'])
    }
    search_points = [dim1_common, dim1_opposite]
    found_polylines = []
    for search_point in search_points:
        for ent in msp.query("LWPOLYLINE POLYLINE"):
            try:
                if not ent.dxf.layer.startswith(DIM_LAYER_PREFIXES):
                    continue
                if get_entity_handle(ent) in excluded_handles:
                    continue
                if isinstance(ent, LWPolyline):
                    points = list(ent.get_points("xy"))
                else:
                    points = [v.dxf.location for v in ent.vertices]
                if len(points) != 2:
                    continue
                pts = [to2d(p) for p in points]
                min_distance = min(distance(pt, search_point) for pt in pts)
                if min_distance <= tolerance:
                    found_polylines.append((ent, min_distance))
            except Exception:
                continue
    if found_polylines:
        found_polylines.sort(key=lambda x: x[1])
        closest_polyline = found_polylines[0][0]
        closest_polyline.dxf.color = 7

def process_ct_text_with_enhanced_interference_check(txt, g1_ent, v0, v1, text_angle, common_point, dim_pair, msp):
    try:
        if hasattr(txt.dxf, 'insert') and txt.dxf.insert is not None:
            current_pos = to2d(txt.dxf.insert)
        elif (hasattr(txt.dxf, 'align_point') and txt.dxf.align_point is not None):
            current_pos = to2d(txt.dxf.align_point)
        else:
            return
    except:
        return

    dim1_ent = dim_pair['DIM1']
    dim2_ent = dim_pair['DIM2']
    dim1_segments = extract_segments(dim1_ent)
    dim2_segments = extract_segments(dim2_ent)
    if not dim1_segments or not dim2_segments:
        return
    dim1_start, dim1_end = to2d(dim1_segments[0][0]), to2d(dim1_segments[0][1])
    dim2_start, dim2_end = to2d(dim2_segments[0][0]), to2d(dim2_segments[0][1])

    dim_length = dim_pair['length']
    is_ct1 = 1.2 <= dim_length <= 1.5

    if is_ct1:
        final_angle = 0.0
        find_and_color_ct1_polylines(msp, dim_pair)
    else:
        use_ang_angle = 1.5 <= dim_length <= 2.0
        if use_ang_angle:
            ang_angle = find_parallel_polylines_for_ang(msp, dim_pair)
            final_angle = ang_angle
        else:
            final_angle = text_angle

    text_length, text_height = get_text_dimensions(txt)
    text_half_length = text_length / 2.0
    text_angle_rad = math.radians(final_angle)
    text_direction = np.array([math.cos(text_angle_rad), math.sin(text_angle_rad)])
    text_perpendicular = np.array([-math.sin(text_angle_rad), math.cos(text_angle_rad)])

    cp_centered_point = common_point - text_direction * text_half_length
    current_text_center = cp_centered_point + text_direction * text_half_length
    cp_to_text_center_vec = current_text_center - common_point
    cp_to_text_center_distance = np.linalg.norm(cp_to_text_center_vec)
    if cp_to_text_center_distance > 0:
        cp_to_text_center_direction = cp_to_text_center_vec / cp_to_text_center_distance
        move_0_6mm = cp_to_text_center_direction * 0.6
        intermediate_point = cp_centered_point + move_0_6mm
    else:
        move_0_6mm = text_direction * 0.6
        intermediate_point = cp_centered_point + move_0_6mm

    interference_detected, _, _ = check_ct_dim_interference(
        intermediate_point, text_length, text_height, dim1_start, dim1_end, dim2_start, dim2_end
    )
    final_position = intermediate_point

    if interference_detected:
        if cp_to_text_center_distance > 0:
            interference_avoid_move = -cp_to_text_center_direction * 1.2
            candidate_position = intermediate_point + interference_avoid_move
        else:
            interference_avoid_move = -text_direction * 1.2
            candidate_position = intermediate_point + interference_avoid_move

        interference_still_detected, _, _ = check_ct_dim_interference(
            candidate_position, text_length, text_height, dim1_start, dim1_end, dim2_start, dim2_end
        )
        if not interference_still_detected:
            final_position = candidate_position
        else:
            positions_to_try = []
            for offset in [1.0, -1.0, 2.0, -2.0, 3.0, -3.0, 4.0, -4.0]:
                side_move = text_perpendicular * offset
                test_position = candidate_position + side_move
                positions_to_try.append(test_position)
            for offset in [1.0, -1.0, 2.0, -2.0, 3.0, -3.0, 4.0, -4.0]:
                vertical_move = text_direction * offset
                test_position = candidate_position + vertical_move
                positions_to_try.append(test_position)
            best_position = candidate_position
            for test_pos in positions_to_try:
                test_interference, _, _ = check_ct_dim_interference(
                    test_pos, text_length, text_height, dim1_start, dim1_end, dim2_start, dim2_end
                )
                if not test_interference:
                    best_position = test_pos
                    break
            final_position = best_position

    final_to_cp_vec = common_point - final_position
    final_to_cp_distance = np.linalg.norm(final_to_cp_vec)
    if final_to_cp_distance > 0:
        final_to_cp_direction = final_to_cp_vec / final_to_cp_distance
        cp_move_2mm = final_to_cp_direction * 2.0
        final_position = final_position + cp_move_2mm

    move_distance = -2
    dim1_segments = extract_segments(dim_pair['DIM1'])
    if dim1_segments:
        dim1_start, dim1_end = to2d(dim1_segments[0][0]), to2d(dim1_segments[0][1])
        dim1_vec = dim1_end - dim1_start
        dim1_length = np.linalg.norm(dim1_vec)
        if dim1_length > 0:
            dim1_unit = dim1_vec / dim1_length
            to_cp_vec = common_point - final_position
            projection_length = np.dot(to_cp_vec, dim1_unit)
            if projection_length > 0:
                move_direction = dim1_unit
            else:
                move_direction = -dim1_unit
            final_position = final_position + move_direction * move_distance

    if txt.dxftype() == "TEXT":
        old_z = float(txt.dxf.insert[2]) if len(txt.dxf.insert) > 2 else 0.0
        txt.dxf.insert = (float(final_position[0]), float(final_position[1]), old_z)
        txt.dxf.halign = 0
        txt.dxf.valign = 0
        try:
            if hasattr(txt.dxf, 'align_point'):
                delattr(txt.dxf, 'align_point')
        except:
            pass
        txt.dxf.rotation = float(final_angle)
    elif txt.dxftype() == "MTEXT":
        old_z = float(txt.dxf.insert[2]) if len(txt.dxf.insert) > 2 else 0.0
        txt.dxf.insert = (float(final_position[0]), float(final_position[1]), old_z)
        txt.dxf.attachment_point = 1
        txt.dxf.rotation = float(final_angle)
    return is_ct1

def process_dimension_system(msp, text_entities):
    all_line_entities = list(msp.query("LINE LWPOLYLINE POLYLINE"))
    dim_pairs, overlapped_entities = find_dim_pairs_optimized(all_line_entities)

    all_processed_entities = []
    all_ct_texts = []
    all_ct1_texts = []
    g1_entities_to_delete = []
    ad3_entities_to_delete = []
    arrow_lines_to_delete = []
    protected_entities = set()
    protected_entities_list = []
    all_ad1_ad2_entities = []
    all_dim_far_endpoints = []

    all_used_dim_handles = set()
    for dim_pair in dim_pairs:
        all_used_dim_handles.add(get_entity_handle(dim_pair['DIM1']))
        all_used_dim_handles.add(get_entity_handle(dim_pair['DIM2']))

    all_processed_entities.extend(overlapped_entities)

    for dim_pair in dim_pairs:
        dim1 = dim_pair['DIM1']
        dim2 = dim_pair['DIM2']
        dim1_opposite = dim_pair['DIM1_opposite']
        dim2_opposite = dim_pair['DIM2_opposite']
        dim1_common = dim_pair['DIM1_common']
        dim2_common = dim_pair['DIM2_common']

        all_dim_far_endpoints.extend([dim1_opposite, dim2_opposite])

        protected_entities.add(get_entity_handle(dim1))
        protected_entities.add(get_entity_handle(dim2))
        protected_entities_list.append(dim1)
        protected_entities_list.append(dim2)

        chain_dir = calculate_chain_direction(dim1, dim2)
        text_angle = calculate_text_angle(chain_dir)

        dim1.dxf.color = 3
        dim2.dxf.color = 3
        all_processed_entities.extend([dim1, dim2])

        ad1_entities = find_arrow_entities_optimized(all_line_entities, dim1_opposite)
        ad2_entities = find_arrow_entities_optimized(all_line_entities, dim2_opposite)

        for ad1 in ad1_entities:
            protected_entities.add(get_entity_handle(ad1))
            protected_entities_list.append(ad1)
            all_ad1_ad2_entities.append(ad1)
        for ad2 in ad2_entities:
            protected_entities.add(get_entity_handle(ad2))
            protected_entities_list.append(ad2)
            all_ad1_ad2_entities.append(ad2)

        for ad1 in ad1_entities:
            ad1.dxf.color = 2
            all_processed_entities.append(ad1)
        for ad2 in ad2_entities:
            ad2.dxf.color = 2
            all_processed_entities.append(ad2)

        ad3_entities = find_ad3_entities_optimized(all_line_entities, dim_pair, ad1_entities, ad2_entities)
        g1_entities = find_g1_entities_optimized_with_all_dims(
            all_line_entities, dim1, dim2, dim_pair, all_used_dim_handles
        )

        ct_found = False
        for g1_ent, v0, v1 in g1_entities:
            g1_ent.dxf.color = 1
            all_processed_entities.append(g1_ent)
            g1_entities_to_delete.append(g1_ent)
            ct_texts = find_ct_texts(msp, [(g1_ent, v0, v1)], text_entities, dim_pair)
            if ct_texts:
                ct_found = True
                for ct in ct_texts:
                    ct.dxf.color = 2
                    is_ct1 = process_ct_text_with_enhanced_interference_check(
                        ct, g1_ent, v0, v1, text_angle, dim_pair['common_point'], dim_pair, msp
                    )
                    if is_ct1:
                        all_ct1_texts.append(ct)
                    else:
                        all_ct_texts.append(ct)

        if ct_found:
            for ad3 in ad3_entities:
                if (get_entity_handle(ad3) not in protected_entities and
                    ad3 not in all_ad1_ad2_entities and
                    ad3 not in protected_entities_list):
                    ad3.dxf.color = 4
                    all_processed_entities.append(ad3)
                    ad3_entities_to_delete.append(ad3)
                else:
                    ad3.dxf.color = 2
                    all_processed_entities.append(ad3)
        else:
            for ad3 in ad3_entities:
                ad3.dxf.color = 2
                all_processed_entities.append(ad3)

        touching_ad3 = find_ad3_touching_dims(all_line_entities, dim1, dim2, ad1_entities, ad2_entities)
        for touching_ad3_ent in touching_ad3:
            if (get_entity_handle(touching_ad3_ent) not in protected_entities and
                touching_ad3_ent not in ad3_entities_to_delete and
                touching_ad3_ent not in all_ad1_ad2_entities and
                touching_ad3_ent not in protected_entities_list):
                touching_ad3_ent.dxf.color = 4
                all_processed_entities.append(touching_ad3_ent)
                ad3_entities_to_delete.append(touching_ad3_ent)

    for ent in all_line_entities:
        try:
            if ent.dxf.layer.upper() == "ARROW":
                if isinstance(ent, LWPolyline):
                    points = list(ent.get_points("xy"))
                elif isinstance(ent, Polyline):
                    points = [v.dxf.location for v in ent.vertices]
                else:
                    continue
                pts = [to2d(p) for p in points]
                for pt in pts:
                    for far_endpoint in all_dim_far_endpoints:
                        if distance(pt, far_endpoint) <= 0.5:
                            protected_entities.add(get_entity_handle(ent))
                            break
        except Exception:
            continue

    arrow_lines = find_arrow_lines_touching_ad3(all_line_entities, ad3_entities_to_delete)
    for arrow_line in arrow_lines:
        if (get_entity_handle(arrow_line) not in protected_entities and
            arrow_line not in protected_entities_list):
            arrow_line.dxf.color = 4
            all_processed_entities.append(arrow_line)
            arrow_lines_to_delete.append(arrow_line)

    ad3_entities_to_delete_final = []
    for ad3_ent in ad3_entities_to_delete:
        if (ad3_ent not in all_ad1_ad2_entities and
            ad3_ent not in protected_entities_list and
            get_entity_handle(ad3_ent) not in protected_entities):
            ad3_entities_to_delete_final.append(ad3_ent)

    arrow_lines_to_delete_final = []
    for arrow_line in arrow_lines_to_delete:
        if (arrow_line not in all_ad1_ad2_entities and
            arrow_line not in protected_entities_list and
            get_entity_handle(arrow_line) not in protected_entities):
            arrow_lines_to_delete_final.append(arrow_line)

    for ad3_ent in ad3_entities_to_delete_final:
        try:
            if (get_entity_handle(ad3_ent) not in protected_entities and
                ad3_ent not in protected_entities_list and
                ad3_ent not in all_ad1_ad2_entities):
                msp.delete_entity(ad3_ent)
        except:
            pass

    for g1_ent in g1_entities_to_delete:
        try:
            if get_entity_handle(g1_ent) not in protected_entities:
                msp.delete_entity(g1_ent)
        except:
            pass

    for arrow_line in arrow_lines_to_delete_final:
        try:
            if (get_entity_handle(arrow_line) not in protected_entities and
                arrow_line not in protected_entities_list):
                msp.delete_entity(arrow_line)
        except:
            pass

    return all_processed_entities, all_ct_texts, all_ct1_texts

# ─────────────── 메인 파이프라인 ───────────────
def auto_align_dxf(input_dxf, output_dxf):
    if not os.path.isfile(input_dxf):
        return False
    try:
        clear_tbox_cache()
        doc = ezdxf.readfile(input_dxf)
        msp = doc.modelspace()
        text_entities = list(msp.query("TEXT MTEXT"))
        processed_entities, ct_texts, ct1_texts = process_dimension_system(msp, text_entities)
        doc.saveas(output_dxf)
        clear_tbox_cache()
        return True
    except Exception:
        clear_tbox_cache()
        return False

def process_cli_files(file_list):
    for input_file in file_list:
        try:
            file_dir = os.path.dirname(input_file)
            base = os.path.splitext(os.path.basename(input_file))[0]
            output_file = os.path.join(file_dir, f"{base}_DIM.dxf")
            auto_align_dxf(input_file, output_file)
        except Exception:
            pass

if __name__ == "__main__":
    # CLI: 여러 DXF 파일 경로를 인자로 받아 각 파일을 *_DIM.dxf로 저장
    # 예) python PLTONEWLINE.PY A.dxf B.dxf C.dxf
    args = [a for a in sys.argv[1:] if a.lower().endswith(".dxf")]
    if args:
        process_cli_files(args)
