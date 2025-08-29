#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import ezdxf
import os
import math
import re
import sys
from ezdxf.math import Vec2

### 공통 유틸 함수들 ###
def distance(p1, p2):
    if isinstance(p1, Vec2) and isinstance(p2, Vec2):
        return math.hypot(p2.x - p1.x, p2.y - p1.y)
    return math.hypot(p2[0] - p1[0], p2[1] - p1[1])

def midpoint(points):
    x = sum(p[0] for p in points) / len(points)
    y = sum(p[1] for p in points) / len(points)
    return (x, y)

def polyline_length(pl):
    try:
        if pl.dxftype() == 'LWPOLYLINE':
            points = [p[:2] for p in pl.get_points()]
        elif pl.dxftype() == 'POLYLINE':
            points = []
            for v in pl.vertices:
                if hasattr(v.dxf, 'location'):
                    pt = (v.dxf.location.x, v.dxf.location.y)
                    points.append(pt)
            if not points:
                return 0
        else:
            return 0
        return sum(distance(points[i], points[i+1]) for i in range(len(points)-1))
    except Exception:
        return 0

def get_poly_points(pl):
    try:
        if pl.dxftype() == 'LWPOLYLINE':
            points = list(pl.get_points())
            points = [pt for pt in points if abs(pt[0]) > 1e-8 or abs(pt[1]) > 1e-8]
            return points
        elif pl.dxftype() == 'POLYLINE':
            pts = []
            for v in pl.vertices:
                if hasattr(v.dxf, 'location'):
                    x, y = v.dxf.location.x, v.dxf.location.y
                    if abs(x) > 1e-8 or abs(y) > 1e-8:
                        pts.append((x, y, 0, 0))
            return pts
        else:
            return []
    except Exception:
        return []

def move_single_point_to(line, target_point, fixed_point):
    try:
        d_start = distance((line.dxf.start[0], line.dxf.start[1]), fixed_point)
        d_end = distance((line.dxf.end[0], line.dxf.end[1]), fixed_point)
        if d_start < d_end:
            line.dxf.end = target_point
        else:
            line.dxf.start = target_point
    except Exception:
        pass

def is_valid_center(center):
    if center is None:
        return False
    x, y = center
    if abs(x) < 1e-5 and abs(y) < 1e-5:
        return False
    if abs(x) > 1e5 or abs(y) > 1e5:
        return False
    return True

def is_nearly_same_points(points, tol=0.05):
    if len(points) < 2:
        return True
    base = points[0][:2]
    for pt in points[1:]:
        if distance(base, pt[:2]) > tol:
            return False
    return True

def is_valid_wdno_text(text_content):
    """WDNO로 유효한 텍스트인지 확인하는 함수"""
    try:
        if 'INST' in text_content.upper():
            return False
        if 'TEXT' in text_content.upper():
            return False
        if '<' in text_content:
            return False
        numbers = re.findall(r'\d+', text_content)
        if not numbers:
            return False
        return True
    except:
        return False

def is_valid_wdno_entity(text_entity):
    """TEXT 엔티티가 WDNO로 유효한지 확인 (내용 + 기울기 확인)"""
    try:
        text_content = text_entity.dxf.text.strip()
        if not is_valid_wdno_text(text_content):
            return False
        if hasattr(text_entity.dxf, 'rotation'):
            if abs(text_entity.dxf.rotation) > 0.1:  # 허용 오차
                return False
        return True
    except:
        return False

### 간섭 체크 함수 ###
def point_to_segment_distance(p: Vec2, a: Vec2, b: Vec2) -> float:
    ap = p - a
    ab = b - a
    ab_len_squared = ab.dot(ab)
    if ab_len_squared == 0:
        return distance(p, a)
    t = max(0, min(1, ap.dot(ab) / ab_len_squared))
    projection = a + ab * t
    return distance(p, projection)

def check_box_overlap(box1, box2):
    if not box1 or not box2:
        return False
    if (box1['max_x'] < box2['min_x'] or 
        box1['min_x'] > box2['max_x'] or
        box1['max_y'] < box2['min_y'] or 
        box1['min_y'] > box2['max_y']):
        return False
    return True

def check_text_box_interference(text_entity, msp, exclude_entities):
    text_bbox = get_text_bounding_box(text_entity)
    if not text_bbox:
        return False
    half_width = text_bbox['width'] / 2
    adjusted_bbox = {
        'center': Vec2(text_bbox['center'].x + half_width, text_bbox['center'].y),
        'width': text_bbox['width'],
        'height': text_bbox['height'],
        'min_x': text_bbox['min_x'] + half_width,
        'max_x': text_bbox['max_x'] + half_width,
        'min_y': text_bbox['min_y'],
        'max_y': text_bbox['max_y']
    }
    for e in msp:
        if e in exclude_entities or not hasattr(e, "dxf") or e.dxf is None:
            continue
        if e.dxftype() == "TEXT":
            other_bbox = get_text_bounding_box(e)
            if other_bbox:
                other_half_width = other_bbox['width'] / 2
                other_adjusted_bbox = {
                    'min_x': other_bbox['min_x'] + other_half_width,
                    'max_x': other_bbox['max_x'] + other_half_width,
                    'min_y': other_bbox['min_y'],
                    'max_y': other_bbox['max_y']
                }
                if check_box_overlap(adjusted_bbox, other_adjusted_bbox):
                    return True
    return False

def check_circle_box_overlap(circle_center, circle_radius, box):
    if not box:
        return False
    closest_x = max(box['min_x'], min(circle_center.x, box['max_x']))
    closest_y = max(box['min_y'], min(circle_center.y, box['max_y']))
    dist = distance(circle_center, Vec2(closest_x, closest_y))
    return dist < circle_radius

def find_pipe_lines_near_sw_improved(sw_entity, sw_center, sw_type, msp, search_radius=1.0):
    """SW/SFW 근처의 PIPE 선을 찾는 개선된 함수"""
    pipe_lines_candidates = []
    try:
        # SFW 점 리스트 (검색반경 조정)
        if sw_type == 'POLYLINE' or sw_type == 'SFW':
            if sw_entity.dxftype() == "POLYLINE":
                _ = [Vec2(v.dxf.location.x, v.dxf.location.y) for v in sw_entity.vertices]
            else:
                _ = [Vec2(x, y) for x, y, *_ in sw_entity.get_points()]
            search_radius = 7.0

        for entity in msp.query('LINE'):
            try:
                if hasattr(entity.dxf, 'layer'):
                    layer_name = entity.dxf.layer.upper()
                    if 'PIPE' in layer_name:
                        start = Vec2(entity.dxf.start.x, entity.dxf.start.y)
                        end = Vec2(entity.dxf.end.x, entity.dxf.end.y)
                        min_dist = min(distance(sw_center, start), distance(sw_center, end))
                        if min_dist <= search_radius:
                            pipe_lines_candidates.append({
                                'entity': entity,
                                'type': 'LINE',
                                'segments': [(start, end)],
                                'min_distance': min_dist
                            })
            except Exception:
                continue

        for poly in msp.query("POLYLINE LWPOLYLINE"):
            try:
                if hasattr(poly.dxf, 'layer'):
                    layer_name = poly.dxf.layer.upper()
                    if 'PIPE' in layer_name:
                        if poly.dxftype() == "POLYLINE":
                            points = [Vec2(v.dxf.location.x, v.dxf.location.y) for v in poly.vertices]
                        else:
                            points = [Vec2(x, y) for x, y, *_ in poly.get_points()]
                        if len(points) >= 2:
                            min_dist = min(distance(sw_center, pt) for pt in points)
                            if min_dist <= search_radius:
                                segments = [(points[i], points[i+1]) for i in range(len(points)-1)]
                                pipe_lines_candidates.append({
                                    'entity': poly,
                                    'type': poly.dxftype(),
                                    'segments': segments,
                                    'min_distance': min_dist
                                })
            except Exception:
                continue

        pipe_lines_candidates.sort(key=lambda x: x['min_distance'])
        pipe_lines = pipe_lines_candidates[:2]
    except Exception:
        pipe_lines = []
    return pipe_lines

def check_circle_to_segments_distance(circle_center, circle_radius, segments, min_distance=2.0):
    for start, end in segments:
        dist_to_segment = point_to_segment_distance(circle_center, start, end)
        dist_to_circle = dist_to_segment - circle_radius
        if dist_to_circle <= min_distance:
            return True
    return False

def check_interference_at_position(test_center, msp, exclude_entities, weld_radius=3.0):
    for e in msp:
        if e in exclude_entities or not hasattr(e, "dxf") or e.dxf is None:
            continue
        if e.dxftype() == "TEXT":
            text_pos = Vec2(e.dxf.insert.x, e.dxf.insert.y)
            if distance(test_center, text_pos) < weld_radius:
                return True
        elif e.dxftype() in ("POLYLINE", "LWPOLYLINE"):
            if e.dxftype() == "POLYLINE":
                pts = [Vec2(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]
            else:
                pts = [Vec2(x, y) for x, y, *_ in e.get_points()]
            for i in range(len(pts) - 1):
                if point_to_segment_distance(test_center, pts[i], pts[i+1]) < weld_radius:
                    return True
        elif e.dxftype() == "CIRCLE":
            circle_center = Vec2(e.dxf.center.x, e.dxf.center.y)
            if distance(circle_center, test_center) < (e.dxf.radius + weld_radius):
                return True
    return False

def check_text_interference_only(test_center, msp, exclude_entities, weld_radius=3.0):
    for e in msp:
        if e in exclude_entities or not hasattr(e, "dxf") or e.dxf is None:
            continue
        if e.dxftype() == "TEXT":
            text_pos = Vec2(e.dxf.insert.x, e.dxf.insert.y)
            if distance(test_center, text_pos) < weld_radius:
                return True
    return False

### WELDNOEDIT 기능 ###
def is_overlap_and_text(center: Vec2, msp, exclude_entities, weld_radius=3.0):
    overlap = False
    is_text = False
    for e in msp:
        if e in exclude_entities or not hasattr(e, "dxf") or e.dxf is None:
            continue
        if e.dxftype() == "TEXT":
            p = Vec2(e.dxf.insert.x, e.dxf.insert.y)
            if distance(p, center) < weld_radius:
                overlap = True
                is_text = True
        elif e.dxftype() in ("POLYLINE", "LWPOLYLINE"):
            if e.dxftype() == "POLYLINE":
                pts = [Vec2(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]
            else:
                pts = [Vec2(x, y) for x, y, *_ in e.get_points()]
            for i in range(len(pts) - 1):
                if point_to_segment_distance(center, pts[i], pts[i+1]) < weld_radius:
                    overlap = True
                    break
    return overlap, is_text

def process_weldnoedit(doc):
    msp = doc.modelspace()
    tolerance_touch = 0.2
    min_sl1_length = 14
    target_distance = 5
    text_search_radius = 6
    weld_radius = 2.8
    min_seg_len = 4.5
    max_seg_len = 6.0
    cicle_len = 5.6
    offset_len = cicle_len / 2

    weld_blocks = []
    moved = 0
    weld_results = []
    sl1_to_delete = []

    for poly in msp.query("POLYLINE LWPOLYLINE"):
        if poly.dxftype() == "POLYLINE":
            if len(poly.vertices) != 3:
                continue
            has_curve = any(v.dxf.bulge != 0 for v in poly.vertices)
            pts = [Vec2(v.dxf.location.x, v.dxf.location.y) for v in poly.vertices]
        else:
            pts = [Vec2(x, y) for x, y, *_ in poly.get_points()]
            if len(pts) != 3:
                continue
            has_curve = any(b != 0 for (*_, b) in poly.get_points())
        if not has_curve:
            continue
        if not any(min_seg_len <= distance(pts[i], pts[i + 1]) <= max_seg_len for i in range(2)):
            continue
        center = Vec2(sum(p.x for p in pts)/3, sum(p.y for p in pts)/3)
        
        text_search_radius = 4
        closest_txt = None
        closest_dist = float('inf')
        for txt in msp.query("TEXT"):
            try:
                if not is_valid_wdno_entity(txt):
                    continue
                pos = Vec2(txt.dxf.insert.x, txt.dxf.insert.y)
                d = distance(pos, center)
                if d <= text_search_radius and d < closest_dist:
                    closest_txt = txt
                    closest_dist = d
            except:
                continue
        texts = []
        if closest_txt is not None:
            closest_txt.dxf.color = 1
            texts.append(closest_txt)
        poly.dxf.color = 1
        weld_blocks.append({"poly": poly, "texts": texts, "center": center})

    for weld in weld_blocks:
        weld_poly = weld["poly"]
        weld_center = weld["center"]
        weld_texts = weld["texts"]

        if weld_poly.dxftype() == "POLYLINE":
            weld_points = [Vec2(v.dxf.location.x, v.dxf.location.y) for v in weld_poly.vertices]
        else:
            weld_points = [Vec2(x, y) for x, y, *_ in weld_poly.get_points()]

        for sl1 in list(msp.query("POLYLINE LWPOLYLINE")):
            if sl1 is weld_poly:
                continue
            if sl1.dxftype() == "POLYLINE":
                sl1_pts = [Vec2(v.dxf.location.x, v.dxf.location.y) for v in sl1.vertices]
            else:
                sl1_pts = [Vec2(x, y) for x, y, *_ in sl1.get_points()]
            if len(sl1_pts) < 2:
                continue
            start, end = sl1_pts[0], sl1_pts[-1]
            sl1_len = distance(start, end)
            if any(distance(start, wp) <= tolerance_touch for wp in weld_points):
                sp1_idx, sp1, sp2 = 0, start, end
            elif any(distance(end, wp) <= tolerance_touch for wp in weld_points):
                sp1_idx, sp1, sp2 = -1, end, start
            else:
                continue

            final_sp2 = sp2
            if sl1_len < min_sl1_length:
                weld_results.append({"sp2": final_sp2, "center": weld_center, "weld_poly": weld_poly})
                sl1_to_delete.append(sl1)
                break

            direction_vec = sp2 - sp1
            direction_vec = direction_vec.normalize() if direction_vec.magnitude != 0 else None
            if direction_vec is None:
                continue

            found, move_vec = False, None
            for r in range(1, 10):
                test_point = sp2 + direction_vec * (-r)
                overlap, is_text = is_overlap_and_text(test_point, msp, [weld_poly, sl1] + weld_texts, weld_radius)
                if not overlap:
                    move_vec = test_point - sp1
                    found = True
                    break
            if not found:
                move_distance = distance(sp1, sp2) - target_distance
                if move_distance <= 0:
                    break
                move_vec = direction_vec * move_distance

            new_sp1 = sp1 + move_vec
            directions = [Vec2(dx, dy) for d in range(3, 11) for dx, dy in [(-d, 0), (d, 0), (0, -d), (0, d)]]
            final_offset = Vec2(0, 0)
            for offset in directions:
                test_center = weld_center + move_vec + offset
                overlap, is_text = is_overlap_and_text(test_center, msp, [weld_poly, sl1] + weld_texts, weld_radius)
                if not overlap:
                    final_offset = offset
                    break
            move_vec += final_offset
            new_sp1 = sp1 + move_vec

            if sl1.dxftype() == "POLYLINE":
                if sp1_idx == 0:
                    sl1.vertices[0].dxf.location = (new_sp1.x, new_sp1.y, 0)
                else:
                    sl1.vertices[-1].dxf.location = (new_sp1.x, new_sp1.y, 0)
            else:
                points = sl1.get_points()
                if sp1_idx == 0:
                    new_points = [(new_sp1.x, new_sp1.y)] + points[1:]
                else:
                    new_points = points[:-1] + [(new_sp1.x, new_sp1.y)]
                sl1.set_points(new_points)

            dx, dy = move_vec.x, move_vec.y
            if weld_poly.dxftype() == "POLYLINE":
                for v in weld_poly.vertices:
                    loc = v.dxf.location
                    v.dxf.location = (loc.x + dx, loc.y + dy, 0)
            else:
                weld_pts = [(x + dx, y + dy) for x, y, *_ in weld_poly.get_points()]
                weld_poly.set_points(weld_pts)
            for txt in weld_texts:
                pos = txt.dxf.insert
                txt.dxf.insert = (pos.x + dx, pos.y + dy, 0)

            sl1.dxf.color = 1
            weld_poly.dxf.color = 1
            for txt in weld_texts:
                txt.dxf.color = 1

            moved += 1
            weld_results.append({"sp2": final_sp2, "center": weld_center + move_vec + final_offset, "weld_poly": weld_poly})
            sl1_to_delete.append(sl1)
            break

    for sl1 in sl1_to_delete:
        try:
            msp.delete_entity(sl1)
        except Exception:
            pass

    for weld in weld_results:
        sp2 = weld["sp2"]
        poly = weld["weld_poly"]
        center = weld["center"]
        if poly.dxftype() == "POLYLINE":
            pts = [Vec2(v.dxf.location.x, v.dxf.location.y) for v in poly.vertices]
        else:
            pts = [Vec2(x, y) for x, y, *_ in poly.get_points()]
        if len(pts) == 3 and sp2 is not None:
            cp = (pts[0] + pts[1]) * 0.5
            vec = sp2 - cp
            if vec.magnitude != 0:
                cp = cp + vec.normalize() * (5.6 / 2)
            msp.add_line((cp.x, cp.y), (sp2.x, sp2.y), dxfattribs={'color': 1})

    for weld in weld_results:
        poly = weld["weld_poly"]
        if poly.dxftype() == "POLYLINE":
            pts = [Vec2(v.dxf.location.x, v.dxf.location.y) for v in poly.vertices]
        else:
            pts = [Vec2(x, y) for x, y, *_ in poly.get_points()]
        if len(pts) == 3:
            cp = (pts[0] + pts[1]) * 0.5
            msp.add_circle(center=cp, radius=(5.6 / 2), dxfattribs={"color": 2})
        try:
            msp.delete_entity(poly)
        except Exception:
            pass

### WELDSYMBOL 기능 ###
def process_weldsymbol(doc):
    msp = doc.modelspace()
    to_delete = []

    for weld in list(msp.query('LWPOLYLINE POLYLINE')):
        points = get_poly_points(weld)
        if len(points) != 7:
            continue
        if is_nearly_same_points(points):
            continue
        too_far = False
        for i in range(6):
            d = distance(points[i][:2], points[i+1][:2])
            if d > 2.0:
                too_far = True
                break
        if too_far:
            continue
        weld_center = midpoint([pt[:2] for pt in points])
        if not is_valid_center(weld_center):
            continue
        length = polyline_length(weld)
        if length < 1 or length > 100:
            continue

        short_plines = []
        for pl in msp.query('LWPOLYLINE POLYLINE LINE'):
            if pl == weld:
                continue
            pts = get_poly_points(pl)
            if len(pts) != 2:
                continue
            if any(distance(pt[:2], wp[:2]) <= 3.0 for pt in pts for wp in points):
                if polyline_length(pl) <= 2.8:
                    short_plines.append(pl)

        main_circle = msp.add_circle(center=weld_center, radius=1, dxfattribs={"color": 2})
        main_circle.dxf.lineweight = 20

        leader_line = None
        for ent in msp.query('LINE'):
            if hasattr(ent.dxf, 'color') and ent.dxf.color == 1:
                p_start = (ent.dxf.start[0], ent.dxf.start[1])
                p_end = (ent.dxf.end[0], ent.dxf.end[1])
                for pt in points:
                    if distance(pt[:2], p_start) <= 1 or distance(pt[:2], p_end) <= 1:
                        leader_line = ent
                        break
            if leader_line:
                break

        if hasattr(weld.dxf, 'linetype') and isinstance(weld.dxf.linetype, str):
            if weld.dxf.linetype.upper() == "GT100":
                weld.dxf.linetype = "DOT"

        if hasattr(weld.dxf, 'linetype') and weld.dxf.linetype.upper() == "BYLAYER":
            for r in [0.85, 0.7, 0.55, 0.4, 0.25]:
                inner = msp.add_circle(center=weld_center, radius=r, dxfattribs={"color": 2})
                inner.dxf.lineweight = 20

        # SW/OW 판정
        main_circle.dxf.layer = "SW" if len(short_plines) >= 5 else "OW"

        # 빨간선 당겨 붙이기
        red_lines = []
        for ent in msp.query('LINE'):
            if hasattr(ent.dxf, 'color') and ent.dxf.color == 1:
                p_start = (ent.dxf.start[0], ent.dxf.start[1])
                p_end = (ent.dxf.end[0], ent.dxf.end[1])
                for pt in points:
                    if distance(pt[:2], p_start) <= 1 or distance(pt[:2], p_end) <= 1:
                        red_lines.append((ent, p_start, p_end))
                        break
        for line, p1, p2 in red_lines:
            d1 = distance(p1, weld_center)
            d2 = distance(p2, weld_center)
            wp1 = p1 if d1 < d2 else p2
            wp2 = p2 if d1 < d2 else p1
            move_single_point_to(line, weld_center, fixed_point=wp2)
            break

        to_delete.append(weld)
        to_delete.extend(short_plines)

    for ent in to_delete:
        try:
            msp.delete_entity(ent)
        except Exception:
            pass

### NL1 생성 및 거리 제어 기능 ###
def find_all_circles_by_radius(msp, target_radius, radius_tolerance=0.1):
    circles = []
    for entity in msp.query('CIRCLE'):
        try:
            if (hasattr(entity.dxf, 'color') and entity.dxf.color == 2 and
                hasattr(entity.dxf, 'radius') and abs(entity.dxf.radius - target_radius) < radius_tolerance):
                center = Vec2(entity.dxf.center.x, entity.dxf.center.y)
                circles.append({'entity': entity, 'center': center, 'radius': entity.dxf.radius})
        except Exception:
            continue
    return circles

def adjust_weld_circle_distance(weld_circle, small_circle, min_distance=6.0, msp=None):
    weld_center = weld_circle['center']
    small_center = small_circle['center']
    weld_radius = weld_circle['radius']
    small_radius = small_circle['radius']
    current_distance = distance(weld_center, small_center)
    if current_distance >= min_distance:
        return True, weld_center, [], "no_adjustment"

    direction_vec = weld_center - small_center
    if direction_vec.magnitude == 0:
        return False, weld_center, [], "same_position"
    direction_normalized = direction_vec.normalize()
    new_weld_center = small_center + direction_normalized * min_distance

    weldno_texts = []
    weldno_text_search_radius = 3.0
    text_backups = []
    for txt in msp.query('TEXT'):
        try:
            txt_pos = Vec2(txt.dxf.insert.x, txt.dxf.insert.y)
            if distance(weld_center, txt_pos) <= weldno_text_search_radius:
                if is_valid_wdno_entity(txt):
                    weldno_texts.append(txt)
                    text_backups.append({'text': txt, 'original_pos': (txt.dxf.insert.x, txt.dxf.insert.y, getattr(txt.dxf.insert, 'z', 0))})
        except Exception:
            continue

    original_weld_center = Vec2(weld_center.x, weld_center.y)
    exclude_entities = [weld_circle['entity'], small_circle['entity']] + weldno_texts
    if check_interference_at_position(new_weld_center, msp, exclude_entities, weld_radius):
        if hasattr(small_circle['entity'], 'dxftype') and small_circle['entity'].dxftype() in ['POLYLINE', 'LWPOLYLINE']:
            min_7mm_center = small_center + direction_normalized * 7.0
            if not check_interference_at_position(min_7mm_center, msp, exclude_entities, weld_radius):
                new_weld_center = min_7mm_center
            else:
                return False, weld_center, [], "stretch_interference"
        else:
            return False, weld_center, [], "stretch_interference"

    all_circles = []
    for entity in msp.query('CIRCLE'):
        try:
            if (hasattr(entity.dxf, 'color') and entity.dxf.color == 2 and
                entity != weld_circle['entity']):
                circle_center = Vec2(entity.dxf.center.x, entity.dxf.center.y)
                all_circles.append({'entity': entity, 'center': circle_center, 'radius': entity.dxf.radius})
        except Exception:
            continue

    for other_circle in all_circles:
        other_center = other_circle['center']
        dist_between_centers = distance(new_weld_center, other_center)
        if dist_between_centers < 6.0:
            if hasattr(small_circle['entity'], 'dxftype') and small_circle['entity'].dxftype() in ['POLYLINE', 'LWPOLYLINE']:
                min_7mm_center = small_center + direction_normalized * 7.0
                dist_to_other_from_7mm = distance(min_7mm_center, other_center)
                if dist_to_other_from_7mm >= 6.0:
                    new_weld_center = min_7mm_center
                else:
                    return False, weld_center, [], "stretch_circle_collision"
            else:
                return False, weld_center, [], "stretch_circle_collision"

    try:
        move_vec = new_weld_center - weld_center
        weld_circle['entity'].dxf.center = (new_weld_center.x, new_weld_center.y, 0)
        for txt in weldno_texts:
            try:
                old_pos = txt.dxf.insert
                new_pos = (old_pos.x + move_vec.x, old_pos.y + move_vec.y, getattr(old_pos, 'z', 0))
                txt.dxf.insert = new_pos
            except Exception:
                pass
        _ = distance(new_weld_center, small_center)
        return True, new_weld_center, weldno_texts, "stretch"
    except Exception:
        try:
            weld_circle['entity'].dxf.center = (original_weld_center.x, original_weld_center.y, 0)
            weld_circle['center'] = original_weld_center
            for backup in text_backups:
                backup['text'].dxf.insert = backup['original_pos']
        except Exception:
            pass
        return False, weld_center, [], "stretch_error"

def ensure_minimum_distances_between_all_circles(msp, min_distance=6.0):
    all_circles = []
    for entity in msp.query('CIRCLE'):
        try:
            if hasattr(entity.dxf, 'color') and entity.dxf.color == 2:
                center = Vec2(entity.dxf.center.x, entity.dxf.center.y)
                all_circles.append({'entity': entity, 'center': center, 'radius': entity.dxf.radius})
        except Exception:
            continue

    for i in range(len(all_circles)):
        for j in range(i + 1, len(all_circles)):
            circle1 = all_circles[i]
            circle2 = all_circles[j]
            center1 = circle1['center']
            center2 = circle2['center']
            current_distance = distance(center1, center2)
            if current_distance < min_distance:
                moving_circle = None
                fixed_circle = None
                if abs(circle1['radius'] - 2.8) <= 0.3 and abs(circle2['radius'] - 2.8) > 0.3:
                    moving_circle = circle1
                    fixed_circle = circle2
                elif abs(circle2['radius'] - 2.8) <= 0.3 and abs(circle1['radius'] - 2.8) > 0.3:
                    moving_circle = circle2
                    fixed_circle = circle1
                elif abs(circle1['radius'] - 2.8) <= 0.3 and abs(circle2['radius'] - 2.8) <= 0.3:
                    moving_circle = circle1
                    fixed_circle = circle2
                else:
                    continue
                if moving_circle is None:
                    continue
                direction_vec = moving_circle['center'] - fixed_circle['center']
                if direction_vec.magnitude == 0:
                    continue
                direction_normalized = direction_vec.normalize()
                new_center = fixed_circle['center'] + direction_normalized * min_distance

                weldno_texts = []
                weldno_text_search_radius = 3.0
                for txt in msp.query('TEXT'):
                    try:
                        txt_pos = Vec2(txt.dxf.insert.x, txt.dxf.insert.y)
                        if distance(moving_circle['center'], txt_pos) <= weldno_text_search_radius:
                            if is_valid_wdno_entity(txt):
                                weldno_texts.append(txt)
                    except Exception:
                        continue

                exclude_entities = [circle1['entity'], circle2['entity']] + weldno_texts
                if not check_interference_at_position(new_center, msp, exclude_entities, moving_circle['radius']):
                    try:
                        move_vec = new_center - moving_circle['center']
                        moving_circle['entity'].dxf.center = (new_center.x, new_center.y, 0)
                        moving_circle['center'] = new_center
                        for txt in weldno_texts:
                            try:
                                old_pos = txt.dxf.insert
                                new_pos = (old_pos.x + move_vec.x, old_pos.y + move_vec.y, getattr(old_pos, 'z', 0))
                                txt.dxf.insert = new_pos
                            except Exception:
                                pass
                    except Exception:
                        pass

def find_closest_yellow_circles_to_weld_circles(msp, radius_tolerance=0.1):
    connections = []
    try:
        weld_circles = find_all_circles_by_radius(msp, 2.8, radius_tolerance)
        small_circles = find_all_circles_by_radius(msp, 1.0, radius_tolerance)

        sfw_polylines = []
        for poly in msp.query("POLYLINE LWPOLYLINE"):
            try:
                if hasattr(poly.dxf, 'layer') and poly.dxf.layer == "SFW":
                    if poly.dxftype() == "POLYLINE":
                        points = [Vec2(v.dxf.location.x, v.dxf.location.y) for v in poly.vertices]
                    else:
                        points = [Vec2(x, y) for x, y, *_ in poly.get_points()]
                    if len(points) == 6:
                        center_x = sum(p.x for p in points) / 6
                        center_y = sum(p.y for p in points) / 6
                        center = Vec2(center_x, center_y)
                        sfw_polylines.append({'entity': poly, 'center': center, 'points': points, 'type': 'SFW'})
            except Exception:
                continue

        all_sw_sfw = []
        for circle in small_circles:
            all_sw_sfw.append({'entity': circle['entity'], 'center': circle['center'], 'radius': circle['radius'], 'type': 'SW'})
        for sfw in sfw_polylines:
            all_sw_sfw.append({'entity': sfw['entity'], 'center': sfw['center'], 'radius': 1.0, 'type': 'SFW'})

        for weld_circle in weld_circles:
            weld_center = weld_circle['center']
            weld_group_radius = 4.0
            red_line_endpoints = []

            for entity in msp.query('LINE'):
                try:
                    if hasattr(entity.dxf, 'color') and entity.dxf.color == 1:
                        start_point = Vec2(entity.dxf.start.x, entity.dxf.start.y)
                        end_point = Vec2(entity.dxf.end.x, entity.dxf.end.y)
                        if (distance(weld_center, start_point) <= weld_group_radius or 
                            distance(weld_center, end_point) <= weld_group_radius):
                            red_line_endpoints.extend([start_point, end_point])
                except Exception:
                    continue

            for poly in msp.query("POLYLINE LWPOLYLINE"):
                try:
                    if hasattr(poly.dxf, 'color') and poly.dxf.color == 1:
                        if poly.dxftype() == "POLYLINE":
                            poly_points = [Vec2(v.dxf.location.x, v.dxf.location.y) for v in poly.vertices]
                        else:
                            poly_points = [Vec2(x, y) for x, y, *_ in poly.get_points()]
                        near_weld = any(distance(weld_center, point) <= weld_group_radius for point in poly_points)
                        if near_weld and len(poly_points) >= 2:
                            red_line_endpoints.extend([poly_points[0], poly_points[-1]])
                except Exception:
                    continue

            if not red_line_endpoints:
                continue

            valid_connections = []
            endpoint_search_radius = 1.5
            for endpoint in red_line_endpoints:
                for sw_sfw in all_sw_sfw:
                    try:
                        center = sw_sfw['center']
                        dist = distance(endpoint, center)
                        if dist <= endpoint_search_radius:
                            valid_connections.append({
                                'weld_circle': weld_circle,
                                'small_circle': sw_sfw,
                                'red_line_endpoint': endpoint,
                                'endpoint_to_small_distance': dist,
                                'weld_to_small_distance': distance(weld_center, center),
                                'sw_type': sw_sfw['type']
                            })
                    except Exception:
                        continue

            if not valid_connections:
                continue
            best_connection = min(valid_connections, key=lambda x: x['endpoint_to_small_distance'])
            connections.append(best_connection)
        return connections
    except Exception:
        return []

def process_nl1_distance_control(doc):
    msp = doc.modelspace()
    min_distance = 6.0
    try:
        connections = find_closest_yellow_circles_to_weld_circles(msp)
        if not connections:
            return
        for connection in connections:
            weld_circle = connection['weld_circle']
            small_circle = connection['small_circle']
            weld_center = weld_circle['center']
            small_center = small_circle['center']

            current_distance = connection['weld_to_small_distance']
            if current_distance <= min_distance:
                adjust_success, new_weld_center, moved_texts, action_type = adjust_weld_circle_distance(
                    weld_circle, small_circle, min_distance, msp
                )
                if adjust_success:
                    weld_center = new_weld_center

            nl1_line = msp.add_line(
                start=(weld_center.x, weld_center.y),
                end=(small_center.x, small_center.y),
                dxfattribs={'color': 4}
            )

            try:
                weld_entity = weld_circle['entity']
                weld_center_pos = Vec2(weld_entity.dxf.center.x, weld_entity.dxf.center.y)
                weld_radius_val = weld_entity.dxf.radius
                line_start = Vec2(nl1_line.dxf.start.x, nl1_line.dxf.start.y)
                line_end = Vec2(nl1_line.dxf.end.x, nl1_line.dxf.end.y)
                direction_to_small = line_end - line_start
                if direction_to_small.magnitude > 0:
                    direction_normalized = direction_to_small.normalize()
                    trim_start = weld_center_pos + direction_normalized * weld_radius_val
                    nl1_line.dxf.start = (trim_start.x, trim_start.y, 0)
            except Exception:
                pass

        # 그룹별 빨간 엔티티 정리
        red_lines_to_delete = []
        all_weld_circles = find_all_circles_by_radius(msp, 2.8, 0.3)
        for weld_circle in all_weld_circles:
            weld_center = weld_circle['center']
            weld_group_radius = 4.0
            for entity in msp.query('LINE'):
                try:
                    if hasattr(entity.dxf, 'color') and entity.dxf.color == 1:
                        start_point = Vec2(entity.dxf.start.x, entity.dxf.start.y)
                        end_point = Vec2(entity.dxf.end.x, entity.dxf.end.y)
                        if (distance(weld_center, start_point) <= weld_group_radius or 
                            distance(weld_center, end_point) <= weld_group_radius):
                            if entity not in red_lines_to_delete:
                                red_lines_to_delete.append(entity)
                except Exception:
                    continue
            for poly in msp.query("POLYLINE LWPOLYLINE"):
                try:
                    if hasattr(poly.dxf, 'color') and poly.dxf.color == 1:
                        if poly.dxftype() == "POLYLINE":
                            poly_points = [Vec2(v.dxf.location.x, v.dxf.location.y) for v in poly.vertices]
                        else:
                            poly_points = [Vec2(x, y) for x, y, *_ in poly.get_points()]
                        if any(distance(weld_center, point) <= weld_group_radius for point in poly_points):
                            if poly not in red_lines_to_delete:
                                red_lines_to_delete.append(poly)
                except Exception:
                    continue
        for red_entity in red_lines_to_delete:
            try:
                msp.delete_entity(red_entity)
            except Exception:
                pass

        ensure_minimum_distances_between_all_circles(msp, min_distance)
    except Exception:
        pass

### [4단계] NL1 길이 7mm 조정 ###
def find_nl1_lines_with_weld_circles(msp):
    nl1_weld_pairs = []
    nl1_lines = []
    for entity in msp.query('LINE'):
        try:
            if hasattr(entity.dxf, 'color') and entity.dxf.color == 4:
                nl1_lines.append(entity)
        except Exception:
            continue
    for nl1_line in nl1_lines:
        try:
            line_start = Vec2(nl1_line.dxf.start.x, nl1_line.dxf.start.y)
            line_end = Vec2(nl1_line.dxf.end.x, nl1_line.dxf.end.y)
            weld_circle = None
            small_circle = None
            sw_type = None
            for entity in msp.query('CIRCLE'):
                try:
                    if (hasattr(entity.dxf, 'color') and entity.dxf.color == 2 and
                        hasattr(entity.dxf, 'radius') and abs(entity.dxf.radius - 2.8) <= 0.3):
                        circle_center = Vec2(entity.dxf.center.x, entity.dxf.center.y)
                        dist_to_start = distance(circle_center, line_start)
                        if dist_to_start <= 3.5:
                            weld_circle = {'entity': entity, 'center': circle_center, 'radius': entity.dxf.radius}
                            break
                except Exception:
                    continue
            for entity in msp.query('CIRCLE'):
                try:
                    if (hasattr(entity.dxf, 'color') and entity.dxf.color == 2 and
                        hasattr(entity.dxf, 'radius') and abs(entity.dxf.radius - 1.0) <= 0.1):
                        circle_center = Vec2(entity.dxf.center.x, entity.dxf.center.y)
                        dist_to_end = distance(circle_center, line_end)
                        if dist_to_end <= 1.5:
                            small_circle = {'entity': entity, 'center': circle_center, 'radius': entity.dxf.radius}
                            sw_type = 'SW'
                            break
                except Exception:
                    continue
            if not small_circle:
                for poly in msp.query("POLYLINE LWPOLYLINE"):
                    try:
                        if hasattr(poly.dxf, 'layer') and poly.dxf.layer == "SFW":
                            if poly.dxftype() == "POLYLINE":
                                points = [Vec2(v.dxf.location.x, v.dxf.location.y) for v in poly.vertices]
                            else:
                                points = [Vec2(x, y) for x, y, *_ in poly.get_points()]
                            if len(points) == 6:
                                center_x = sum(p.x for p in points) / 6
                                center_y = sum(p.y for p in points) / 6
                                center = Vec2(center_x, center_y)
                                dist_to_end = distance(center, line_end)
                                if dist_to_end <= 2.0:
                                    small_circle = {'entity': poly, 'center': center, 'radius': 1.0}
                                    sw_type = 'SFW'
                                    break
                    except Exception:
                        continue
            if weld_circle and small_circle:
                nl1_length = distance(line_start, line_end)
                nl1_weld_pairs.append({
                    'nl1_line': nl1_line,
                    'weld_circle': weld_circle,
                    'small_circle': small_circle,
                    'current_length': nl1_length,
                    'sw_type': sw_type
                })
        except Exception:
            continue
    return nl1_weld_pairs

def adjust_nl1_to_7mm_length(nl1_weld_pair, target_length=7.0, msp=None):
    nl1_line = nl1_weld_pair['nl1_line']
    weld_circle = nl1_weld_pair['weld_circle']
    small_circle = nl1_weld_pair['small_circle']
    current_length = nl1_weld_pair['current_length']

    weld_center = weld_circle['center']
    small_center = small_circle['center']
    weld_radius = weld_circle['radius']

    if abs(current_length - target_length) < 0.1:
        return True, "no_adjustment"

    direction_vec = small_center - weld_center
    if direction_vec.magnitude == 0:
        return False, "same_position"

    direction_normalized = direction_vec.normalize()
    new_weld_center = small_center - direction_normalized * target_length

    weldno_texts = []
    weldno_text_search_radius = 3.0
    text_backups = []
    for txt in msp.query('TEXT'):
        try:
            txt_pos = Vec2(txt.dxf.insert.x, txt.dxf.insert.y)
            if distance(weld_center, txt_pos) <= weldno_text_search_radius:
                if is_valid_wdno_entity(txt):
                    weldno_texts.append(txt)
                    text_backups.append({
                        'text': txt,
                        'original_pos': (txt.dxf.insert.x, txt.dxf.insert.y, getattr(txt.dxf.insert, 'z', 0))
                    })
        except Exception:
            continue

    original_weld_center = Vec2(weld_center.x, weld_center.y)
    exclude_entities = [weld_circle['entity'], small_circle['entity'], nl1_line] + weldno_texts
    has_text_interference_at_new = check_text_interference_only(new_weld_center, msp, exclude_entities, weld_radius)
    has_text_interference_at_original = check_text_interference_only(original_weld_center, msp, exclude_entities, weld_radius)

    if not has_text_interference_at_new and not has_text_interference_at_original:
        target_center = new_weld_center
    elif not has_text_interference_at_new and has_text_interference_at_original:
        target_center = new_weld_center
    elif has_text_interference_at_new and not has_text_interference_at_original:
        target_center = original_weld_center
    else:
        target_center = new_weld_center

    if target_center == original_weld_center:
        return True, "keep_original_position"

    for entity in msp.query('CIRCLE'):
        try:
            if (hasattr(entity.dxf, 'color') and entity.dxf.color == 2 and
                entity != weld_circle['entity'] and entity != small_circle['entity']):
                other_center = Vec2(entity.dxf.center.x, entity.dxf.center.y)
                dist_to_other = distance(target_center, other_center)
                if dist_to_other < 6.0:
                    return False, "circle_collision"
        except Exception:
            continue

    try:
        move_vec = target_center - weld_center
        weld_circle['entity'].dxf.center = (target_center.x, target_center.y, 0)
        weld_circle['center'] = target_center
        for txt in weldno_texts:
            try:
                old_pos = txt.dxf.insert
                new_pos = (old_pos.x + move_vec.x, old_pos.y + move_vec.y, getattr(old_pos, 'z', 0))
                txt.dxf.insert = new_pos
            except Exception:
                pass

        direction_to_small = small_center - target_center
        if direction_to_small.magnitude > 0:
            direction_normalized_final = direction_to_small.normalize()
            new_trim_start = target_center + direction_normalized_final * weld_radius
            nl1_line.dxf.start = (new_trim_start.x, new_trim_start.y, 0)
        return True, "stretch_success"
    except Exception:
        try:
            weld_circle['entity'].dxf.center = (original_weld_center.x, original_weld_center.y, 0)
            weld_circle['center'] = original_weld_center
            for backup in text_backups:
                backup['text'].dxf.insert = backup['original_pos']
        except Exception:
            pass
        return False, "stretch_error"

def process_nl1_length_adjustment(doc):
    msp = doc.modelspace()
    target_length = 7.0
    try:
        nl1_weld_pairs = find_nl1_lines_with_weld_circles(msp)
        if not nl1_weld_pairs:
            return
        adjustment_needed_pairs = [p for p in nl1_weld_pairs if abs(p['current_length'] - target_length) > 0.1]
        if not adjustment_needed_pairs:
            return
        for pair in adjustment_needed_pairs:
            adjust_nl1_to_7mm_length(pair, target_length, msp)
    except Exception:
        pass

### [5단계] MWD 회전 및 최종 연결 ###
def get_text_bounding_box(text):
    try:
        insert = Vec2(text.dxf.insert.x, text.dxf.insert.y)
        height = text.dxf.height
        text_content = text.dxf.text
        width = len(text_content) * height * 0.7
        halign = text.dxf.halign if hasattr(text.dxf, 'halign') else 0
        valign = text.dxf.valign if hasattr(text.dxf, 'valign') else 0
        if halign == 0:
            min_x = insert.x; max_x = insert.x + width
        elif halign == 1:
            min_x = insert.x - width/2; max_x = insert.x + width/2
        elif halign == 2:
            min_x = insert.x - width; max_x = insert.x
        else:
            min_x = insert.x; max_x = insert.x + width
        if valign == 0:
            min_y = insert.y; max_y = insert.y + height
        elif valign == 1:
            min_y = insert.y; max_y = insert.y + height
        elif valign == 2:
            min_y = insert.y - height/2; max_y = insert.y + height/2
        elif valign == 3:
            min_y = insert.y - height; max_y = insert.y
        else:
            min_y = insert.y; max_y = insert.y + height
        center = Vec2((min_x + max_x)/2, (min_y + max_y)/2)
        return {'center': center, 'width': width, 'height': height,
                'min_x': min_x, 'max_x': max_x, 'min_y': min_y, 'max_y': max_y}
    except Exception:
        return None

def find_pipe_line_angle(sw_center, msp, search_radius=5.0):
    try:
        for entity in msp.query('LINE'):
            try:
                start = Vec2(entity.dxf.start.x, entity.dxf.start.y)
                end = Vec2(entity.dxf.end.x, entity.dxf.end.y)
                if (distance(sw_center, start) <= search_radius or 
                    distance(sw_center, end) <= search_radius):
                    dx = end.x - start.x
                    dy = end.y - start.y
                    angle = math.atan2(dy, dx)
                    return angle
            except Exception:
                continue
        for poly in msp.query("POLYLINE LWPOLYLINE"):
            try:
                if poly.dxftype() == "POLYLINE":
                    points = [Vec2(v.dxf.location.x, v.dxf.location.y) for v in poly.vertices]
                else:
                    points = [Vec2(x, y) for x, y, *_ in poly.get_points()]
                for i in range(len(points) - 1):
                    if (distance(sw_center, points[i]) <= search_radius or 
                        distance(sw_center, points[i+1]) <= search_radius):
                        dx = points[i+1].x - points[i].x
                        dy = points[i+1].y - points[i].y
                        angle = math.atan2(dy, dx)
                        return angle
            except Exception:
                continue
        return None
    except Exception:
        return None

def rotate_entity_around_point(entity, center, angle):
    try:
        cos_a = math.cos(angle); sin_a = math.sin(angle)
        if entity.dxftype() == 'CIRCLE':
            old_center = Vec2(entity.dxf.center.x, entity.dxf.center.y)
            dx = old_center.x - center.x; dy = old_center.y - center.y
            new_x = center.x + dx * cos_a - dy * sin_a
            new_y = center.y + dx * sin_a + dy * cos_a
            entity.dxf.center = (new_x, new_y, 0)
        elif entity.dxftype() == 'TEXT':
            old_pos = Vec2(entity.dxf.insert.x, entity.dxf.insert.y)
            dx = old_pos.x - center.x; dy = old_pos.y - center.y
            new_x = center.x + dx * cos_a - dy * sin_a
            new_y = center.y + dx * sin_a + dy * cos_a
            entity.dxf.insert = (new_x, new_y, 0)
        elif entity.dxftype() == 'LINE':
            start = Vec2(entity.dxf.start.x, entity.dxf.start.y)
            end = Vec2(entity.dxf.end.x, entity.dxf.end.y)
            dx = start.x - center.x; dy = start.y - center.y
            new_start_x = center.x + dx * cos_a - dy * sin_a
            new_start_y = center.y + dx * sin_a + dy * cos_a
            dx = end.x - center.x; dy = end.y - center.y
            new_end_x = center.x + dx * cos_a - dy * sin_a
            new_end_y = center.y + dx * sin_a + dy * cos_a
            entity.dxf.start = (new_start_x, new_start_y, 0)
            entity.dxf.end = (new_end_x, new_end_y, 0)
    except Exception:
        pass

def get_text_start_end_points(text):
    try:
        insert = Vec2(text.dxf.insert.x, text.dxf.insert.y)
        height = text.dxf.height
        text_content = text.dxf.text
        width = len(text_content) * height * 0.7
        rotation = text.dxf.rotation if hasattr(text.dxf, 'rotation') else 0
        rotation_rad = math.radians(rotation)
        halign = text.dxf.halign if hasattr(text.dxf, 'halign') else 0
        if halign == 0:
            start_x = 0; end_x = width
        elif halign == 1:
            start_x = -width/2; end_x = width/2
        elif halign == 2:
            start_x = -width; end_x = 0
        else:
            start_x = 0; end_x = width
        cos_r = math.cos(rotation_rad); sin_r = math.sin(rotation_rad)
        start_rotated_x = start_x * cos_r; start_rotated_y = start_x * sin_r
        start_point = Vec2(insert.x + start_rotated_x, insert.y + start_rotated_y)
        end_rotated_x = end_x * cos_r; end_rotated_y = end_x * sin_r
        end_point = Vec2(insert.x + end_rotated_x, insert.y + end_rotated_y)
        return start_point, end_point
    except Exception:
        return None, None

def check_text_endpoint_interference(text_entity, msp, exclude_entities, min_distance=5.0):
    try:
        start1, end1 = get_text_start_end_points(text_entity)
        if not start1 or not end1:
            return False
        for e in msp:
            if e in exclude_entities or not hasattr(e, "dxf") or e.dxf is None:
                continue
            if e.dxftype() == "TEXT":
                start2, end2 = get_text_start_end_points(e)
                if not start2 or not end2:
                    continue
                if (distance(start1, start2) < min_distance or
                    distance(start1, end2) < min_distance or
                    distance(end1, start2) < min_distance or
                    distance(end1, end2) < min_distance):
                    return True
        return False
    except Exception:
        return False

def check_pipe_layer_interference(mwd_entities, msp, exclude_entities):
    try:
        for mwd_entity in mwd_entities:
            if mwd_entity.dxftype() == 'CIRCLE':
                circle_center = Vec2(mwd_entity.dxf.center.x, mwd_entity.dxf.center.y)
                circle_radius = mwd_entity.dxf.radius
                for e in msp:
                    if e in exclude_entities or not hasattr(e, "dxf") or e.dxf is None:
                        continue
                    if hasattr(e.dxf, 'layer'):
                        layer_name = e.dxf.layer.upper()
                        if 'PIPE' in layer_name or 'ELBO' in layer_name:
                            if e.dxftype() in ("LINE", "POLYLINE", "LWPOLYLINE"):
                                if e.dxftype() == "LINE":
                                    start = Vec2(e.dxf.start.x, e.dxf.start.y)
                                    end = Vec2(e.dxf.end.x, e.dxf.end.y)
                                    dist = point_to_segment_distance(circle_center, start, end)
                                    if dist < circle_radius:
                                        return True
                                else:
                                    if e.dxftype() == "POLYLINE":
                                        pts = [Vec2(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]
                                    else:
                                        pts = [Vec2(x, y) for x, y, *_ in e.get_points()]
                                    for i in range(len(pts) - 1):
                                        dist = point_to_segment_distance(circle_center, pts[i], pts[i+1])
                                        if dist < circle_radius:
                                            return True
        return False
    except Exception:
        return False

def check_30degree_polyline_interference(mwd_entities, msp, exclude_entities):
    try:
        for mwd_entity in mwd_entities:
            if mwd_entity.dxftype() == 'CIRCLE':
                circle_center = Vec2(mwd_entity.dxf.center.x, mwd_entity.dxf.center.y)
                circle_radius = mwd_entity.dxf.radius
                for e in msp.query("POLYLINE LWPOLYLINE"):
                    if e in exclude_entities or not hasattr(e, "dxf") or e.dxf is None:
                        continue
                    if e.dxftype() == "POLYLINE":
                        pts = [Vec2(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]
                    else:
                        pts = [Vec2(x, y) for x, y, *_ in e.get_points()]
                    if len(pts) < 2:
                        continue
                    for i in range(len(pts) - 1):
                        p1, p2 = pts[i], pts[i+1]
                        angle_deg = (math.degrees(math.atan2(p2.y - p1.y, p2.x - p1.x)) % 360)
                        nearest_30 = round(angle_deg / 30) * 30
                        if abs(angle_deg - nearest_30) < 1.0:
                            dist = point_to_segment_distance(circle_center, p1, p2)
                            if dist < circle_radius:
                                return True
        return False
    except Exception:
        return False

def check_mwd_interference_with_priority(mwd_entities, sw_center, rotation_angle, msp, exclude_entities, pipe_lines=None):
    try:
        temp_positions = []
        for entity in mwd_entities:
            if entity.dxftype() == 'CIRCLE':
                temp_positions.append({'entity': entity, 'type': 'CIRCLE', 'original': (entity.dxf.center.x, entity.dxf.center.y, 0)})
            elif entity.dxftype() == 'TEXT':
                temp_positions.append({'entity': entity, 'type': 'TEXT', 'original': (entity.dxf.insert.x, entity.dxf.insert.y, 0)})
            elif entity.dxftype() == 'LINE':
                temp_positions.append({
                    'entity': entity, 'type': 'LINE',
                    'original_start': (entity.dxf.start.x, entity.dxf.start.y, 0),
                    'original_end': (entity.dxf.end.x, entity.dxf.end.y, 0)
                })
        for entity in mwd_entities:
            rotate_entity_around_point(entity, sw_center, rotation_angle)

        wdc_circle = None
        weldno_texts = []
        for entity in mwd_entities:
            if entity.dxftype() == 'CIRCLE' and abs(entity.dxf.radius - 2.8) <= 0.3:
                wdc_circle = entity
            elif entity.dxftype() == 'TEXT':
                if is_valid_wdno_entity(entity):
                    weldno_texts.append(entity)
        if wdc_circle and weldno_texts:
            wdc_center = Vec2(wdc_circle.dxf.center.x, wdc_circle.dxf.center.y)
            for txt in weldno_texts:
                bbox = get_text_bounding_box(txt)
                if bbox:
                    offset = wdc_center - bbox['center']
                    new_insert = Vec2(txt.dxf.insert.x + offset.x, txt.dxf.insert.y + offset.y)
                    txt.dxf.insert = (new_insert.x, new_insert.y, 0)

        has_text_interference = False
        for entity in mwd_entities:
            if entity.dxftype() == 'TEXT':
                if check_text_endpoint_interference(entity, msp, exclude_entities + mwd_entities, 5.0):
                    has_text_interference = True
                    break
        has_pipe_layer_interference = check_pipe_layer_interference(mwd_entities, msp, exclude_entities + mwd_entities)

        has_pc_circle_interference = False
        if pipe_lines:
            for entity in mwd_entities:
                if entity.dxftype() == 'CIRCLE' and abs(entity.dxf.radius - 2.8) <= 0.3:
                    center = Vec2(entity.dxf.center.x, entity.dxf.center.y)
                    for pc in pipe_lines:
                        if check_circle_to_segments_distance(center, entity.dxf.radius, pc['segments'], 2.0):
                            has_pc_circle_interference = True
                            break
                    if has_pc_circle_interference:
                        break

        has_30deg = check_30degree_polyline_interference(mwd_entities, msp, exclude_entities + mwd_entities)

        general_interference_score = 0
        for entity in mwd_entities:
            if entity.dxftype() == 'CIRCLE':
                center = Vec2(entity.dxf.center.x, entity.dxf.center.y)
                if check_interference_at_position(center, msp, exclude_entities + mwd_entities, entity.dxf.radius):
                    general_interference_score += 1

        for backup in temp_positions:
            if backup['type'] == 'CIRCLE':
                backup['entity'].dxf.center = backup['original']
            elif backup['type'] == 'TEXT':
                backup['entity'].dxf.insert = backup['original']
            elif backup['type'] == 'LINE':
                backup['entity'].dxf.start = backup['original_start']
                backup['entity'].dxf.end = backup['original_end']

        return {
            'text_interference': has_text_interference,
            'pipe_layer_interference': has_pipe_layer_interference,
            'pc_circle_interference': has_pc_circle_interference,
            '30degree_polyline_interference': has_30deg,
            'general_score': general_interference_score
        }
    except Exception:
        return {
            'text_interference': True,
            'pipe_layer_interference': True,
            'pc_circle_interference': True,
            '30degree_polyline_interference': True,
            'general_score': 999
        }

def find_sfw_polyline(msp, search_center, search_radius=20.0):
    sfw_polylines = []
    for poly in msp.query("POLYLINE LWPOLYLINE"):
        try:
            if hasattr(poly.dxf, 'layer') and poly.dxf.layer == "SFW":
                if poly.dxftype() == "POLYLINE":
                    points = [Vec2(v.dxf.location.x, v.dxf.location.y) for v in poly.vertices]
                else:
                    points = [Vec2(x, y) for x, y, *_ in poly.get_points()]
                if len(points) == 6:
                    center_x = sum(p.x for p in points) / 6
                    center_y = sum(p.y for p in points) / 6
                    center = Vec2(center_x, center_y)
                    dist = distance(search_center, center)
                    if dist <= search_radius:
                        sfw_polylines.append({'entity': poly, 'center': center, 'points': points, 'distance': dist})
        except Exception:
            continue
    return sfw_polylines

def adjust_wdc_for_sfw_7mm(wdc_circle, wdc_center, sfw_center, msp):
    current_distance = distance(wdc_center, sfw_center)
    if current_distance >= 7.0:
        return wdc_center, []
    direction_vec = wdc_center - sfw_center
    if direction_vec.magnitude == 0:
        return wdc_center, []
    direction_normalized = direction_vec.normalize()
    new_wdc_center = sfw_center + direction_normalized * 7.0

    weldno_texts = []
    weldno_text_search_radius = 3.0
    for txt in msp.query('TEXT'):
        try:
            txt_pos = Vec2(txt.dxf.insert.x, txt.dxf.insert.y)
            if distance(wdc_center, txt_pos) <= weldno_text_search_radius:
                if is_valid_wdno_entity(txt):
                    weldno_texts.append(txt)
        except Exception:
            continue
    try:
        move_vec = new_wdc_center - wdc_center
        wdc_circle.dxf.center = (new_wdc_center.x, new_wdc_center.y, 0)
        for txt in weldno_texts:
            try:
                old_pos = txt.dxf.insert
                new_pos = (old_pos.x + move_vec.x, old_pos.y + move_vec.y, getattr(old_pos, 'z', 0))
                txt.dxf.insert = new_pos
            except Exception:
                pass
        return new_wdc_center, weldno_texts
    except Exception:
        return wdc_center, []

def process_mwd_rotation_and_connection(doc):
    msp = doc.modelspace()
    used_sw_sfw = []
    try:
        wdc_circles = []
        for entity in msp.query('CIRCLE'):
            try:
                if (hasattr(entity.dxf, 'color') and entity.dxf.color == 2 and
                    hasattr(entity.dxf, 'radius') and abs(entity.dxf.radius - 2.8) <= 0.3):
                    entity.dxf.layer = "WDC"
                    entity.dxf.color = 2
                    wdc_circles.append(entity)
            except Exception:
                continue

        mwd_groups = []
        for wdc_circle in wdc_circles:
            try:
                wdc_center = Vec2(wdc_circle.dxf.center.x, wdc_circle.dxf.center.y)
                weldno_texts = []
                text_search_radius = 3.0
                for txt in msp.query('TEXT'):
                    try:
                        txt_pos = Vec2(txt.dxf.insert.x, txt.dxf.insert.y)
                        if distance(wdc_center, txt_pos) <= text_search_radius:
                            if is_valid_wdno_entity(txt):
                                txt.dxf.color = 4
                                txt.dxf.layer = "WDNO"
                                weldno_texts.append(txt)
                                bbox = get_text_bounding_box(txt)
                                if bbox:
                                    offset = wdc_center - bbox['center']
                                    new_insert = Vec2(txt.dxf.insert.x + offset.x, txt.dxf.insert.y + offset.y)
                                    txt.dxf.insert = (new_insert.x, new_insert.y, 0)
                    except Exception:
                        continue
                mwd_group = {'wdc_circle': wdc_circle, 'wdc_center': wdc_center,
                             'weldno_texts': weldno_texts, 'entities': [wdc_circle] + weldno_texts}
                mwd_groups.append(mwd_group)
            except Exception:
                continue

        def extract_wdno_number(mwd_group):
            try:
                for txt in mwd_group['weldno_texts']:
                    text_content = txt.dxf.text.strip()
                    numbers = re.findall(r'\d+', text_content)
                    if numbers:
                        return int(numbers[0])
                return 999999
            except:
                return 999999

        mwd_groups_sorted = sorted(mwd_groups, key=extract_wdno_number)

        for mwd_group in mwd_groups_sorted:
            try:
                wdc_circle = mwd_group['wdc_circle']
                wdc_center = mwd_group['wdc_center']
                sw_circle = None
                sw_center = None
                sw_layer = None
                sw_type = None
                nl1_exists = False

                for line in msp.query('LINE'):
                    try:
                        if hasattr(line.dxf, 'color') and line.dxf.color == 4:
                            line_start = Vec2(line.dxf.start.x, line.dxf.start.y)
                            line_end = Vec2(line.dxf.end.x, line.dxf.end.y)
                            if distance(wdc_center, line_start) <= 3.5:
                                nl1_exists = True
                                for circle in msp.query('CIRCLE'):
                                    if (hasattr(circle.dxf, 'color') and circle.dxf.color == 2 and
                                        abs(circle.dxf.radius - 1.0) <= 0.1):
                                        circle_center = Vec2(circle.dxf.center.x, circle.dxf.center.y)
                                        if distance(circle_center, line_end) <= 1.5:
                                            if circle not in used_sw_sfw:
                                                sw_circle = circle
                                                sw_center = circle_center
                                                sw_layer = circle.dxf.layer if hasattr(circle.dxf, 'layer') else "0"
                                                sw_type = 'CIRCLE'
                                            break
                                if sw_circle:
                                    break
                    except Exception:
                        continue

                if not sw_circle:
                    wg_search_radius = 3.5
                    found_wg = False
                    for line in msp.query('LINE'):
                        try:
                            if (hasattr(line.dxf, 'layer') and line.dxf.layer == 'WG' and
                                hasattr(line.dxf, 'color') and line.dxf.color == 7):
                                line_start = Vec2(line.dxf.start.x, line.dxf.start.y)
                                line_end = Vec2(line.dxf.end.x, line.dxf.end.y)
                                dist_to_start = distance(wdc_center, line_start)
                                dist_to_end = distance(wdc_center, line_end)
                                if dist_to_start <= wg_search_radius or dist_to_end <= wg_search_radius:
                                    far_point = line_end if dist_to_start < dist_to_end else line_start
                                    sw_search_radius = 2.0
                                    for circle in msp.query('CIRCLE'):
                                        try:
                                            if (hasattr(circle.dxf, 'color') and circle.dxf.color == 2 and
                                                abs(circle.dxf.radius - 1.0) <= 0.1):
                                                circle_layer = circle.dxf.layer if hasattr(circle.dxf, 'layer') else "0"
                                                circle_center = Vec2(circle.dxf.center.x, circle.dxf.center.y)
                                                if (circle_layer == "SW" and 
                                                    distance(far_point, circle_center) <= sw_search_radius and
                                                    circle not in used_sw_sfw):
                                                    sw_circle = circle
                                                    sw_center = circle_center
                                                    sw_layer = circle_layer
                                                    sw_type = 'CIRCLE'
                                                    found_wg = True
                                                    break
                                        except Exception:
                                            continue
                                    if found_wg:
                                        break
                                    sfw_polylines = find_sfw_polyline(msp, far_point, sw_search_radius)
                                    for sfw in sfw_polylines:
                                        if sfw['entity'] not in used_sw_sfw:
                                            sw_circle = sfw['entity']
                                            sw_center = sfw['center']
                                            sw_layer = "SFW"
                                            sw_type = 'POLYLINE'
                                            found_wg = True
                                            break
                                    if found_wg:
                                        break
                        except Exception:
                            continue

                if not sw_circle:
                    min_distance_val = float('inf')
                    closest_sw = None
                    closest_center = None
                    closest_layer = None
                    closest_type = None
                    for circle in msp.query('CIRCLE'):
                        try:
                            if (hasattr(circle.dxf, 'color') and circle.dxf.color == 2 and
                                abs(circle.dxf.radius - 1.0) <= 0.1):
                                circle_layer = circle.dxf.layer if hasattr(circle.dxf, 'layer') else "0"
                                if circle_layer == "SW" and circle not in used_sw_sfw:
                                    circle_center = Vec2(circle.dxf.center.x, circle.dxf.center.y)
                                    dist = distance(wdc_center, circle_center)
                                    if dist < min_distance_val:
                                        min_distance_val = dist
                                        closest_sw = circle
                                        closest_center = circle_center
                                        closest_layer = circle_layer
                                        closest_type = 'CIRCLE'
                        except Exception:
                            continue
                    sfw_polylines = find_sfw_polyline(msp, wdc_center, search_radius=50.0)
                    for sfw in sfw_polylines:
                        if sfw['entity'] not in used_sw_sfw and sfw['distance'] < min_distance_val:
                            min_distance_val = sfw['distance']
                            closest_sw = sfw['entity']
                            closest_center = sfw['center']
                            closest_layer = "SFW"
                            closest_type = 'POLYLINE'
                    if closest_sw:
                        sw_circle = closest_sw
                        sw_center = closest_center
                        sw_layer = closest_layer
                        sw_type = closest_type
                    else:
                        continue

                used_sw_sfw.append(sw_circle)

                if sw_layer in ["SW", "SFW"]:
                    if sw_type == 'POLYLINE' and sw_layer == "SFW":
                        original_wdc_center = Vec2(wdc_center.x, wdc_center.y)
                        wdc_center, _ = adjust_wdc_for_sfw_7mm(wdc_circle, wdc_center, sw_center, msp)
                        if wdc_center != original_wdc_center:
                            mwd_group['wdc_center'] = wdc_center

                    pipe_lines = find_pipe_lines_near_sw_improved(sw_circle, sw_center, sw_type, msp, 1.0)
                    exclude_entities = [sw_circle] + mwd_group['entities']

                    rotation_candidates = []
                    rotation_candidates.append({'angle': 0, 'degree': 0,
                        'interference': check_mwd_interference_with_priority(mwd_group['entities'], sw_center, 0, msp, exclude_entities, pipe_lines)})

                    for degree in range(30, 360, 30):
                        angle = math.radians(degree)
                        info = check_mwd_interference_with_priority(mwd_group['entities'], sw_center, angle, msp, exclude_entities, pipe_lines)
                        rotation_candidates.append({'angle': angle, 'degree': degree, 'interference': info})

                    best_candidate = None
                    text_free = [c for c in rotation_candidates if not c['interference']['text_interference']]
                    if text_free:
                        pipe_free = [c for c in text_free if not c['interference']['pipe_layer_interference']]
                        if pipe_free:
                            pc_free = [c for c in pipe_free if not c['interference']['pc_circle_interference']]
                            if pc_free:
                                poly_free = [c for c in pc_free if not c['interference']['30degree_polyline_interference']]
                                if poly_free:
                                    best_candidate = min(poly_free, key=lambda x: x['interference']['general_score'])
                                else:
                                    best_candidate = min(pc_free, key=lambda x: x['interference']['general_score'])
                            else:
                                poly_free = [c for c in pipe_free if not c['interference']['30degree_polyline_interference']]
                                if poly_free:
                                    best_candidate = min(poly_free, key=lambda x: x['interference']['general_score'])
                                else:
                                    best_candidate = min(pipe_free, key=lambda x: x['interference']['general_score'])
                        else:
                            pc_free = [c for c in text_free if not c['interference']['pc_circle_interference']]
                            if pc_free:
                                poly_free = [c for c in pc_free if not c['interference']['30degree_polyline_interference']]
                                if poly_free:
                                    best_candidate = min(poly_free, key=lambda x: x['interference']['general_score'])
                                else:
                                    best_candidate = min(pc_free, key=lambda x: x['interference']['general_score'])
                            else:
                                best_candidate = min(text_free, key=lambda x: x['interference']['general_score'])
                    else:
                        best_candidate = min(rotation_candidates, key=lambda x: x['interference']['general_score'])

                    if not best_candidate:
                        continue

                    final_angle = best_candidate['angle']
                    if final_angle != 0:
                        for entity in mwd_group['entities']:
                            rotate_entity_around_point(entity, sw_center, final_angle)
                        wdc_center_after = Vec2(wdc_circle.dxf.center.x, wdc_circle.dxf.center.y)
                        for txt in mwd_group['weldno_texts']:
                            bbox = get_text_bounding_box(txt)
                            if bbox:
                                offset = wdc_center_after - bbox['center']
                                new_insert = Vec2(txt.dxf.insert.x + offset.x, txt.dxf.insert.y + offset.y)
                                txt.dxf.insert = (new_insert.x, new_insert.y, 0)

                    rotated_wdc_center = Vec2(wdc_circle.dxf.center.x, wdc_circle.dxf.center.y)
                    if nl1_exists:
                        for line in list(msp.query('LINE')):
                            try:
                                if hasattr(line.dxf, 'color') and line.dxf.color == 4:
                                    line_start = Vec2(line.dxf.start.x, line.dxf.start.y)
                                    if (distance(wdc_center, line_start) <= 3.5 or
                                        distance(rotated_wdc_center, line_start) <= 3.5):
                                        msp.delete_entity(line)
                                        break
                            except Exception:
                                continue

                    wdc_wg_search_radius = 3.5
                    for line in list(msp.query('LINE')):
                        try:
                            if (hasattr(line.dxf, 'layer') and line.dxf.layer == 'WG' and
                                hasattr(line.dxf, 'color') and line.dxf.color == 7):
                                line_start = Vec2(line.dxf.start.x, line.dxf.start.y)
                                line_end = Vec2(line.dxf.end.x, line.dxf.end.y)
                                if (distance(rotated_wdc_center, line_start) <= wdc_wg_search_radius or
                                    distance(rotated_wdc_center, line_end) <= wdc_wg_search_radius):
                                    msp.delete_entity(line)
                        except Exception:
                            continue

                    wg_search_radius = 2.0
                    for line in list(msp.query('LINE')):
                        try:
                            if (hasattr(line.dxf, 'layer') and line.dxf.layer == 'WG' and
                                hasattr(line.dxf, 'color') and line.dxf.color == 7):
                                line_start = Vec2(line.dxf.start.x, line.dxf.start.y)
                                line_end = Vec2(line.dxf.end.x, line.dxf.end.y)
                                if (distance(sw_center, line_start) <= wg_search_radius or
                                    distance(sw_center, line_end) <= wg_search_radius):
                                    msp.delete_entity(line)
                        except Exception:
                            continue

                    wg_length = distance(sw_center, rotated_wdc_center)
                    if wg_length >= 40.0:
                        continue

                    new_line = msp.add_line(start=(sw_center.x, sw_center.y),
                                            end=(rotated_wdc_center.x, rotated_wdc_center.y),
                                            dxfattribs={'color': 7, 'layer': 'WG'})
                    try:
                        direction = rotated_wdc_center - sw_center
                        if direction.magnitude > 0:
                            direction_normalized = direction.normalize()
                            trim_end = rotated_wdc_center - direction_normalized * wdc_circle.dxf.radius
                            new_line.dxf.end = (trim_end.x, trim_end.y, 0)
                    except Exception:
                        pass
            except Exception:
                continue
    except Exception:
        pass

# ─────────────────────────────────────────────────────────
# In-memory 런너 연동용 엔트리
# ─────────────────────────────────────────────────────────
def process(doc):
    """
    In-memory DXF 문서 처리 파이프라인.
    - 입력: ezdxf.document.Drawing (DXF 문서 객체)
    - 반환: 처리 완료된 같은 문서 객체
    """
    # 단계별 파이프라인
    process_weldnoedit(doc)
    process_weldsymbol(doc)
    process_nl1_distance_control(doc)
    process_nl1_length_adjustment(doc)
    process_mwd_rotation_and_connection(doc)
    return doc

# 호환용 별칭들 (SAE3D_ON_RUNNER와의 함수명 호환)
def pipeline(doc): return process(doc)
def run(doc): return process(doc)
def main_process(doc): return process(doc)

# 파일 경로 처리용 헬퍼 (옵션)
def process_file(filepath):
    """
    파일 경로 기반 처리. 결과 경로를 반환.
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(filepath)
    doc = ezdxf.readfile(filepath)
    process(doc)
    basename = os.path.splitext(os.path.basename(filepath))[0]
    output_dir = os.path.dirname(filepath)
    output_path = os.path.join(output_dir, basename + "_WDSYM.dxf")
    try:
        doc.saveas(output_path)
        return output_path
    except PermissionError:
        alt_output_path = os.path.join(output_dir, basename + "_WDSYM_new.dxf")
        doc.saveas(alt_output_path)
        return alt_output_path

# ─────────────────────────────────────────────────────────
# CLI 실행부 (파일 다중 처리)
# ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python PLTONEWLINE.PY <dxf_file1> <dxf_file2> ...")
        sys.exit(1)

    filepaths = sys.argv[1:]
    for filepath in filepaths:
        try:
            if not os.path.exists(filepath):
                print(f"Error: File not found - {filepath}")
                continue
            doc = ezdxf.readfile(filepath)
            process(doc)
            basename = os.path.splitext(os.path.basename(filepath))[0]
            output_dir = os.path.dirname(filepath)
            output_path = os.path.join(output_dir, basename + "_WDSYM.dxf")
            try:
                doc.saveas(output_path)
                print(f"Processed: {filepath} -> {output_path}")
            except PermissionError:
                alt_output_path = os.path.join(output_dir, basename + "_WDSYM_new.dxf")
                try:
                    doc.saveas(alt_output_path)
                    print(f"Processed: {filepath} -> {alt_output_path} (alternative name due to permission)")
                except Exception as e:
                    print(f"Error saving {filepath}: {e}")
            except Exception as e:
                print(f"Error saving {filepath}: {e}")
        except Exception as e:
            print(f"Error processing {filepath}: {e}")
            continue
