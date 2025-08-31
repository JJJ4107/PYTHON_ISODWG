import ezdxf
from pathlib import Path
import sys
import math
from dataclasses import dataclass
from typing import List, Tuple, Optional, Set, Dict
from collections import defaultdict

def has_bulge(ent):
    if ent.dxftype() == 'LWPOLYLINE':
        for x, y, bulge in ent.get_points('xyb'):
            if abs(bulge) > 1e-7:
                return True
        return False
    elif ent.dxftype() == 'POLYLINE':
        for v in ent.vertices:
            if hasattr(v.dxf, 'bulge') and abs(v.dxf.bulge) > 1e-7:
                return True
        return False
    return False

def get_bulge_radius(ent):
    pts = polypoints(ent)
    n = len(pts)
    if n < 2:
        return None

    if ent.dxftype() == 'LWPOLYLINE':
        points = list(ent.get_points('xyb'))
        for idx, (x, y, bulge) in enumerate(points[:-1]):
            if abs(bulge) > 1e-7:
                chord = distance(pts[idx], pts[idx+1])
                theta = 4 * math.atan(abs(bulge))
                if theta == 0:
                    continue
                return abs(chord / (2 * math.sin(theta/2)))
    else:
        verts = list(ent.vertices)
        for idx, v in enumerate(verts[:-1]):
            if hasattr(v.dxf, 'bulge') and abs(v.dxf.bulge) > 1e-7:
                chord = distance(pts[idx], pts[idx+1])
                theta = 4 * math.atan(abs(v.dxf.bulge))
                if theta == 0:
                    continue
                return abs(chord / (2 * math.sin(theta/2)))
    return None

def get_arc_center_from_bulge(p1, p2, bulge):
    if abs(bulge) < 1e-7:
        return None
    
    mid_x = (p1[0] + p2[0]) / 2
    mid_y = (p1[1] + p2[1]) / 2
    
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    chord_length = math.sqrt(dx*dx + dy*dy)
    
    if chord_length < 1e-7:
        return None
    
    theta = 4 * math.atan(abs(bulge))
    radius = chord_length / (2 * math.sin(theta/2))
    
    sagitta = radius * (1 - math.cos(theta/2))
    if bulge < 0:
        sagitta = -sagitta
    
    perp_x = -dy / chord_length
    perp_y = dx / chord_length
    
    h = radius - sagitta
    
    center_x = mid_x + h * perp_x
    center_y = mid_y + h * perp_y
    
    return (center_x, center_y)

def get_polyline_arc_center_and_radius_with_bulge(ent):
    pts = polypoints(ent)
    
    if ent.dxftype() == 'LWPOLYLINE':
        points = list(ent.get_points('xyb'))
        for idx in range(len(points)):
            x1, y1, bulge = points[idx]
            next_idx = (idx + 1) % len(points)
            x2, y2, _ = points[next_idx]
            
            if abs(bulge) > 1e-7:
                center = get_arc_center_from_bulge((x1, y1), (x2, y2), bulge)
                if center:
                    radius = distance(center, (x1, y1))
                    return center, radius
    else:
        verts = list(ent.vertices)
        for idx in range(len(verts)):
            v1 = verts[idx]
            next_idx = (idx + 1) % len(verts)
            v2 = verts[next_idx]
            
            if hasattr(v1.dxf, 'bulge') and abs(v1.dxf.bulge) > 1e-7:
                p1 = (v1.dxf.location.x, v1.dxf.location.y)
                p2 = (v2.dxf.location.x, v2.dxf.location.y)
                center = get_arc_center_from_bulge(p1, p2, v1.dxf.bulge)
                if center:
                    radius = distance(center, p1)
                    return center, radius
    
    return None, None

def circle_exists_at_position(circles_cache, center, radius, tolerance=0.1):
    for existing_center, existing_radius in circles_cache:
        center_distance = distance(existing_center, center)
        if (center_distance < tolerance and 
            abs(existing_radius - radius) < tolerance):
            return True
    return False

def centroid(pts):
    return (sum(p[0] for p in pts)/len(pts), sum(p[1] for p in pts)/len(pts))

def scale_triangle(pts, center, scale):
    return [(center[0]+(x-center[0])*scale, center[1]+(y-center[1])*scale) for x,y in pts]

def distance(p1, p2):
    return math.dist(p1, p2)
          
def draw_line(msp, p1, p2, color=7, layer=None):
    attrib = {"color": color}
    if layer:
        attrib["layer"] = layer
    msp.add_line(p1, p2, dxfattribs=attrib)

def polypoints(ent):
    if ent.dxftype()=='LWPOLYLINE':
        return [(pt[0], pt[1]) for pt in ent.get_points('xy')]
    elif ent.dxftype()=='POLYLINE':
        return [(v.dxf.location.x, v.dxf.location.y) for v in ent.vertices]
    return []

def all_pair_distances(pts):
    return [distance(pts[i], pts[i+1]) for i in range(len(pts)-1)]

def line_exists_between_points(lines_cache, p1, p2, tolerance=1e-6):
    for start, end in lines_cache:
        if ((abs(start[0] - p1[0]) < tolerance and 
             abs(start[1] - p1[1]) < tolerance and
             abs(end[0] - p2[0]) < tolerance and 
             abs(end[1] - p2[1]) < tolerance) or
            (abs(start[0] - p2[0]) < tolerance and 
             abs(start[1] - p2[1]) < tolerance and
             abs(end[0] - p1[0]) < tolerance and 
             abs(end[1] - p1[1]) < tolerance)):
            return True
    return False

def calculate_polyline_area(points):
    n = len(points)
    if n < 3:
        return 0
    
    area = 0
    for i in range(n):
        j = (i + 1) % n
        area += points[i][0] * points[j][1]
        area -= points[j][0] * points[i][1]
    
    return abs(area) / 2.0

def stretch_entities_in_range(msp, header_x, header_y, stretch_x=39):
    x_min = header_x - 5
    x_max = header_x + 170
    y_min = header_y - 250
    y_max = header_y
    
    def point_in_range(x, y):
        return x_min <= x <= x_max and y_min <= y <= y_max
    
    # Cache entities by type for better performance
    texts = list(msp.query('TEXT'))
    lines = list(msp.query('LINE'))
    polylines = [ent for ent in msp if ent.dxftype() in ['POLYLINE', 'LWPOLYLINE']]
    arcs = list(msp.query('ARC'))
    circles = list(msp.query('CIRCLE'))
    
    # Process YELLOW TEXT
    for text in texts:
        if text.dxf.color == 2:
            x, y = text.dxf.insert[0], text.dxf.insert[1]
            if point_in_range(x, y):
                text.dxf.insert = (x + stretch_x, y, text.dxf.insert[2] if len(text.dxf.insert) > 2 else 0)
    
    # Process LINES
    for line in lines:
        start_x, start_y = line.dxf.start.x, line.dxf.start.y
        end_x, end_y = line.dxf.end.x, line.dxf.end.y
        
        start_in_range = point_in_range(start_x, start_y)
        end_in_range = point_in_range(end_x, end_y)
        
        if start_in_range and not end_in_range:
            line.dxf.start = (start_x + stretch_x, start_y, line.dxf.start.z)
        elif not start_in_range and end_in_range:
            line.dxf.end = (end_x + stretch_x, end_y, line.dxf.end.z)
        elif start_in_range and end_in_range:
            line.dxf.start = (start_x + stretch_x, start_y, line.dxf.start.z)
            line.dxf.end = (end_x + stretch_x, end_y, line.dxf.end.z)
    
    # Process POLYLINES
    for ent in polylines:
        modified = False
        
        if ent.dxftype() == 'LWPOLYLINE':
            new_points = []
            for x, y, *rest in ent.get_points('xyb'):
                if point_in_range(x, y):
                    new_points.append((x + stretch_x, y) + tuple(rest))
                    modified = True
                else:
                    new_points.append((x, y) + tuple(rest))
            if modified:
                ent.set_points(new_points)
        else:
            for vertex in ent.vertices:
                loc = vertex.dxf.location
                if point_in_range(loc.x, loc.y):
                    vertex.dxf.location = (loc.x + stretch_x, loc.y, loc.z)
                    modified = True
    
    # Process ARCS
    for arc in arcs:
        center_x, center_y = arc.dxf.center.x, arc.dxf.center.y
        if point_in_range(center_x, center_y):
            arc.dxf.center = (center_x + stretch_x, center_y, arc.dxf.center.z)
    
    # Process CIRCLES
    for circle in circles:
        center_x, center_y = circle.dxf.center.x, circle.dxf.center.y
        if point_in_range(center_x, center_y):
            circle.dxf.center = (center_x + stretch_x, center_y, circle.dxf.center.z)

def find_and_process_weld_header(msp):
    # Cache all texts once
    all_texts = list(msp.query('TEXT'))
    
    first_weld = None
    pattern_found = False
    
    # Method 1: Single line pattern
    for text in all_texts:
        if not text.dxf.text:
            continue
        text_upper = text.dxf.text.upper()
        text_compressed = ' '.join(text_upper.split())
        
        if 'WELD' in text_compressed and 'SHOP' in text_compressed:
            if text_compressed.count('WELD') >= 3 and 'WELD SHOP' in text_compressed:
                first_weld = text
                pattern_found = True
                break
    
    # Method 2: Separate texts grouped by Y coordinate
    if not pattern_found:
        y_groups = defaultdict(list)
        for text in all_texts:
            if text.dxf.text:
                y = round(text.dxf.insert[1], 1)
                y_groups[y].append(text)
        
        for y, texts in y_groups.items():
            texts.sort(key=lambda t: t.dxf.insert[0])
            combined = ' '.join([t.dxf.text.upper().strip() for t in texts if t.dxf.text])
            
            if 'WELD' in combined and 'SHOP' in combined:
                words = combined.split()
                for i in range(len(words) - 3):
                    if (words[i] == 'WELD' and words[i+1] == 'SHOP' and 
                        words[i+2] == 'WELD' and i+3 < len(words) and words[i+3] == 'WELD'):
                        for t in texts:
                            if t.dxf.text and 'WELD' in t.dxf.text.upper():
                                first_weld = t
                                pattern_found = True
                                break
                        break
                if pattern_found:
                    break
    
    # Method 3: Flexible search
    if not pattern_found:
        y_groups = defaultdict(list)
        for text in all_texts:
            if text.dxf.text:
                y = round(text.dxf.insert[1], 1)
                y_groups[y].append(text)
        
        for y, texts in y_groups.items():
            combined = ' '.join([t.dxf.text.upper().strip() for t in texts if t.dxf.text])
            weld_count = combined.count('WELD')
            shop_count = combined.count('SHOP')
            
            if weld_count >= 3 and shop_count >= 1:
                for t in texts:
                    if t.dxf.text and 'WELD' in t.dxf.text.upper():
                        first_weld = t
                        pattern_found = True
                        break
                if pattern_found:
                    break
    
    if not first_weld:
        return
    
    weld_y = first_weld.dxf.insert[1]
    weld_x = first_weld.dxf.insert[0]
    
    # Find numeric texts above WELD
    numeric_texts = []
    for text in all_texts:
        if not text.dxf.text:
            continue
        text_content = text.dxf.text.strip()
        cleaned = text_content.replace('.', '').replace('-', '').replace(' ', '').replace(',', '')
        
        if cleaned and (cleaned.isdigit() or 
                       (text_content.count('.') <= 1 and cleaned.replace('.', '').isdigit())):
            text_x = text.dxf.insert[0]
            text_y = text.dxf.insert[1]
            
            if (text_y > weld_y and abs(text_x - weld_x) < 10 and text_y - weld_y < 200):
                numeric_texts.append((text_y, text))
    
    top_text_y = numeric_texts[-1][0] if numeric_texts else weld_y + 10
    
    # Find horizontal lines
    lines = list(msp.query('LINE'))
    horizontal_lines = []
    
    for line in lines:
        try:
            start_x, start_y = line.dxf.start.x, line.dxf.start.y
            end_x, end_y = line.dxf.end.x, line.dxf.end.y
            
            if abs(start_y - end_y) < 0.1:
                line_length = abs(end_x - start_x)
                if line_length <= 60 and start_y > top_text_y:
                    horizontal_lines.append((start_y, line, line_length))
        except:
            continue
    
    if not horizontal_lines:
        return
    
    horizontal_lines.sort(key=lambda x: x[0])
    bline = horizontal_lines[0][1]
    bline_y = horizontal_lines[0][0]
    
    try:
        bline.dxf.layer = 'BLINE'
    except:
        pass
    
    # Find vertical lines intersecting with BLINE
    bline_start_x = min(bline.dxf.start.x, bline.dxf.end.x)
    bline_end_x = max(bline.dxf.start.x, bline.dxf.end.x)
    
    vertical_lines = []
    for line in lines:
        try:
            start_x, start_y = line.dxf.start.x, line.dxf.start.y
            end_x, end_y = line.dxf.end.x, line.dxf.end.y
            
            if abs(start_x - end_x) < 0.1:
                x_pos = start_x
                tolerance = 0.5
                
                if (bline_start_x - tolerance <= x_pos <= bline_end_x + tolerance and 
                    min(start_y, end_y) <= bline_y <= max(start_y, end_y)):
                    vertical_lines.append((x_pos, line))
        except:
            continue
    
    vertical_lines.sort(key=lambda x: x[0])
    selected_verticals = vertical_lines[:4]
    
    # TRIM vertical lines
    for x_pos, line in selected_verticals:
        try:
            start_y = line.dxf.start.y
            end_y = line.dxf.end.y
            
            if start_y < bline_y < end_y:
                line.dxf.end = (line.dxf.end.x, bline_y, line.dxf.end.z)
            elif end_y < bline_y < start_y:
                line.dxf.start = (line.dxf.start.x, bline_y, line.dxf.start.z)
        except:
            continue
    
    # Delete similar horizontal lines
    bline_start_x = min(bline.dxf.start.x, bline.dxf.end.x)
    bline_end_x = max(bline.dxf.start.x, bline.dxf.end.x)
    bline_length = abs(bline.dxf.end.x - bline.dxf.start.x)
    
    lines_to_delete = []
    
    for line in lines:
        if line == bline:
            continue
        try:
            start_x, start_y = line.dxf.start.x, line.dxf.start.y
            end_x, end_y = line.dxf.end.x, line.dxf.end.y
            
            if abs(start_y - end_y) < 0.1 and start_y > bline_y:
                line_start_x = min(start_x, end_x)
                line_end_x = max(start_x, end_x)
                line_length = abs(end_x - start_x)
                
                if (abs(line_length - bline_length) < 5 and
                    line_start_x <= bline_end_x and line_end_x >= bline_start_x):
                    
                    y_gap = start_y - bline_y
                    gap_interval = 6.5
                    tolerance = 1.5
                    
                    if y_gap > 0:
                        multiple = round(y_gap / gap_interval)
                        expected_y = bline_y + (multiple * gap_interval)
                        
                        if abs(start_y - expected_y) < tolerance:
                            lines_to_delete.append(line)
        except:
            continue
    
    # Additional check for exactly matching lines
    for line in lines:
        if line == bline or line in lines_to_delete:
            continue
        try:
            start_x, start_y = line.dxf.start.x, line.dxf.start.y
            end_x, end_y = line.dxf.end.x, line.dxf.end.y
            
            if (abs(start_y - end_y) < 0.1 and
                abs(start_x - bline.dxf.start.x) < 0.1 and
                abs(end_x - bline.dxf.end.x) < 0.1 and
                start_y > bline_y):
                lines_to_delete.append(line)
        except:
            continue
    
    # Delete lines
    for line in lines_to_delete:
        try:
            msp.delete_entity(line)
        except:
            continue

def process_pl97_and_pl31(msp):
    # Cache polylines by layer
    polylines = [ent for ent in msp if ent.dxftype() in ['LWPOLYLINE', 'POLYLINE']]
    pl97_entities = [ent for ent in polylines if ent.dxf.layer == 'PL97']
    pl31_entities = [ent for ent in polylines if ent.dxf.layer == 'PL31']
    
    # Process PL97
    for ent in pl97_entities:
        pts = polypoints(ent)
        if pts:
            center = centroid(pts)
            diameters = [2.5, 2.0, 1.5, 1.0, 0.5]
            for diameter in diameters:
                radius = diameter / 2.0
                try:
                    msp.add_circle(
                        center=center,
                        radius=radius,
                        dxfattribs={'layer': 'WELD', 'color': 2}
                    )
                except:
                    pass
            
            try:
                msp.delete_entity(ent)
            except:
                pass
    
    # Process PL31
    pl31_to_delete = []
    for ent in pl31_entities:
        pts = polypoints(ent)
        if len(pts) >= 3:
            area = calculate_polyline_area(pts)
            if area <= 3.9:
                pl31_to_delete.append(ent)
    
    for ent in pl31_to_delete:
        try:
            msp.delete_entity(ent)
        except:
            pass

def calculate_line_angle(start, end):
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    
    if abs(dx) < 1e-10 and abs(dy) < 1e-10:
        return None
    
    angle_rad = math.atan2(dy, dx)
    angle_deg = math.degrees(angle_rad)
    
    if angle_deg < 0:
        angle_deg += 360
    
    return angle_deg

def process_layer3_lines_and_texts(msp):
    iso_angles = [0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330]
    angle_tolerance = 1.0
    
    # Cache entities by type
    lines = [line for line in msp.query('LINE') if line.dxf.layer == '3']
    texts = [text for text in msp.query('TEXT') if text.dxf.layer == '3']
    
    # Process lines
    for line in lines:
        start = (line.dxf.start.x, line.dxf.start.y)
        end = (line.dxf.end.x, line.dxf.end.y)
        
        angle = calculate_line_angle(start, end)
        if angle is not None:
            is_iso_angle = False
            for iso_angle in iso_angles:
                angle_diff = abs(angle - iso_angle)
                if angle_diff > 180:
                    angle_diff = 360 - angle_diff
                
                if angle_diff <= angle_tolerance:
                    is_iso_angle = True
                    break
            
            if is_iso_angle:
                line.dxf.layer = 'DIM'
            else:
                line.dxf.layer = 'G1'
    
    # Process texts
    for text in texts:
        if not text.dxf.text:
            continue
        text_content = text.dxf.text.strip()
        cleaned = text_content.replace('.', '').replace('-', '').replace(' ', '').replace(',', '')
        
        is_numeric = False
        if cleaned and (cleaned.isdigit() or 
                       (text_content.count('.') <= 1 and cleaned.isdigit())):
            is_numeric = True
        
        if is_numeric:
            rotation = text.dxf.rotation if hasattr(text.dxf, 'rotation') else 0
            if abs(rotation) <= 1.0 or abs(rotation - 360) <= 1.0:
                text.dxf.layer = 'CP'

def process_red_dim_lines(msp, doc):
    if 'HIDDEN' not in doc.linetypes:
        try:
            doc.linetypes.new('HIDDEN', dxfattribs={
                'description': '- - - - - -',
                'pattern': [6.35, -3.175]
            })
        except:
            pass
    
    lines = [line for line in msp.query('LINE') if line.dxf.layer == 'DIM' and line.dxf.color == 1]
    
    for line in lines:
        try:
            line.dxf.color = 2
            line.dxf.layer = 'CONT'
            line.dxf.linetype = 'HIDDEN'
            line.dxf.ltscale = 5.0
        except:
            pass

def process(doc):
    """In-memory processing entry point"""
    msp = doc.modelspace()
    
    # Pre-cache entities by type for better performance
    lines = list(msp.query('LINE'))
    arcs = list(msp.query('ARC'))
    texts = list(msp.query('TEXT'))
    circles = list(msp.query('CIRCLE'))
    polylines = [ent for ent in msp if ent.dxftype() in ['LWPOLYLINE', 'POLYLINE']]
    
    # Create performance caches
    circles_cache = [(circle.dxf.center, circle.dxf.radius) for circle in circles]
    lines_cache = [(line.dxf.start, line.dxf.end) for line in lines]
    
    processed_entities = set()
    
    # 1. Layer 1 RED LINE to PIPE
    for line in lines:
        if line.dxf.layer == '1' and line.dxf.color == 1:
            line.dxf.layer = 'PIPE'
    
    # 2. Layer 1 RED ARC to ELBO
    for arc in arcs:
        if arc.dxf.layer == '1' and arc.dxf.color == 1:
            arc.dxf.layer = 'ELBO'
    
    # 3. Polyline processing
    entities_to_delete = []
    
    for ent in polylines:
        pts = polypoints(ent)
        n = len(pts)
        
        processed_entities.add(id(ent))
        
        if n == 3:
            if has_bulge(ent):
                r = get_bulge_radius(ent)
                if r and 2 <= r <= 3:
                    ent.dxf.layer = 'WELDNO'
                    ent.dxf.color = 2
                elif r and 5 <= r <= 8:
                    center, calculated_radius = get_polyline_arc_center_and_radius_with_bulge(ent)
                    
                    if center and calculated_radius:
                        if not circle_exists_at_position(circles_cache, center, calculated_radius):
                            circle = msp.add_circle(
                                center=center,
                                radius=calculated_radius,
                                dxfattribs={'layer': 'INSTNO', 'color': 4}
                            )
                            circles_cache.append((center, calculated_radius))
                            entities_to_delete.append(ent)
                        else:
                            ent.dxf.layer = 'INSTNO'
                            ent.dxf.color = 2
                else:
                    ent.dxf.layer = 'PL3'
            else:
                ent.dxf.layer = 'PL3'

        elif n == 4:
            dists = all_pair_distances(pts)
            last_to_first = distance(pts[3], pts[0])
            
            tolerance = 0.1
            if (len(dists) >= 3 and
                abs(dists[0] - 7.445) <= tolerance and
                abs(dists[1] - 1.612) <= tolerance and
                abs(dists[2] - 7.592) <= tolerance and
                abs(last_to_first - 0) <= tolerance):
                ent.dxf.layer = 'FALL'
                ent.dxf.color = 2
            else:
                ent.dxf.layer = 'PL4'
                ent.dxf.color = 7

        elif n == 5:
            dists = all_pair_distances(pts)
            if all(d <= 4.5 for d in dists):
                ent.dxf.layer = 'itemno'
            elif any(d >= 30 for d in dists):
                ent.dxf.layer = 'spoolno'
            else:
                ent.dxf.layer = 'PL5'
            ent.dxf.color = 7

        elif n == 6:
            dists = all_pair_distances(pts)
            total_dist = sum(dists)
            
            if 10 <= total_dist <= 11:
                ent.dxf.layer = 'SFW'
                ent.dxf.color = 2
            elif 17.5 <= total_dist <= 22:
                ent.dxf.layer = 'REDU'
                ent.dxf.color = 2
            elif 16 <= total_dist <= 16.5:
                ent.dxf.layer = 'REDU'
                ent.dxf.color = 2
            elif 17 <= total_dist <= 17.3:
                ent.dxf.layer = 'FLOW'
                ent.dxf.color = 2
            elif 12 <= total_dist <= 13.3:
                ent.dxf.layer = 'OLET'
                ent.dxf.color = 2
            elif any(d <= 1.0 for d in dists):
                ent.dxf.layer = 'FLAN'
                ent.dxf.color = 2
            elif sum(1 for d in dists if 6 <= d <= 15) >= 2:
                ent.dxf.layer = 'VALV'
                ent.dxf.color = 2
            else:
                ent.dxf.layer = 'PL6'
                ent.dxf.color = 7

        elif n == 7:
            dists = all_pair_distances(pts)
            mov_idx = [i for i, d in enumerate(dists) if 3 <= d <= 5]
            if len(mov_idx) >= 2:
                ent.dxf.layer = 'MOV'
                ent.dxf.color = 2
            elif all(d <= 2.2 for d in dists):
                ent.dxf.layer = 'weld'
                ent.dxf.color = 2
            else:
                ent.dxf.layer = 'PL7'
                ent.dxf.color = 4

        elif n == 8:
            dists = all_pair_distances(pts)
            if sum(1 for d in dists if 1.5 <= d <= 4) >= 5:
                ent.dxf.layer = 'WOLET'
                ent.dxf.color = 2
            else:
                ent.dxf.layer = 'PL8'
                ent.dxf.color = 7

        elif n == 9:
            dists = all_pair_distances(pts)
            if all(d <= 5 for d in dists):
                ent.dxf.layer = 'CV'
                ent.dxf.color = 2
            else:
                ent.dxf.layer = 'PL9'
                ent.dxf.color = 7

        elif n == 10:
            dists = all_pair_distances(pts)
            total_dist = sum(dists)
            
            if 13.5 <= total_dist <= 14.5:
                ent.dxf.layer = 'CAP'
                ent.dxf.color = 2
            else:
                ent.dxf.layer = 'PL10'
                ent.dxf.color = 7

        elif n == 12:
            dists = all_pair_distances(pts)
            total_dist = sum(dists)
            
            if 34 <= total_dist <= 35:
                ent.dxf.layer = 'SFW'
                ent.dxf.color = 2
            else:
                ent.dxf.layer = 'PL12'
                ent.dxf.color = 7

        elif n == 2:
            ent.dxf.layer = 'PL2'
            ent.dxf.color = 7
            
        else:
            ent.dxf.layer = f'PL{n}'
            ent.dxf.color = 7
    
    # Delete entities
    for ent in entities_to_delete:
        try:
            msp.delete_entity(ent)
        except:
            pass
    
    # 4. Text processing
    for text in texts:
        if not text.dxf.text:
            continue
        txt = text.dxf.text.upper()
        if '<' in txt and '>' in txt:
            text.dxf.layer = 'itemno'
        elif any(tag in txt for tag in ['EL+', 'EL-', 'FL+', 'FL-']):
            text.dxf.layer = 'ELEV'
        elif any(letter in txt for letter in ['F', 'G']):
            text.dxf.layer = 'FLAN'
        elif 'FALL' in txt:
            text.dxf.layer = 'FALL'
        
        text.dxf.color = 2
    
    # 5. SP3, SP7 processing
    for ent in polylines:
        if id(ent) in processed_entities:
            continue
        pts = polypoints(ent)
        n = len(pts)
        
        if n == 3:
            dists = all_pair_distances(pts)
            total_dist = sum(dists)
            
            if total_dist <= 5:
                if not line_exists_between_points(lines_cache, pts[2], pts[0]):
                    msp.add_line(pts[2], pts[0], dxfattribs={'color': 7, 'layer': 'ARROW'})
                    lines_cache.append((pts[2], pts[0]))
        elif n == 7:
            dists = all_pair_distances(pts)
            if any(d > 30 for d in dists):
                ent.dxf.layer = 'SUPP'
    
    # 6. FALL layer 2-point polylines
    fall_polylines = [ent for ent in polylines if ent.dxf.layer == 'FALL']
    for ent in fall_polylines:
        pts = polypoints(ent)
        if len(pts) == 2:
            ent.dxf.color = 7
    
    # 7. Header processing
    header_found = False
    for text in texts:
        if (text.dxf.text and 'PT' in text.dxf.text and 
            'COMPONENT' in text.dxf.text and 'SIZE' in text.dxf.text):
            header_x = text.dxf.insert[0]
            header_y = text.dxf.insert[1]
            
            if header_x < 620:
                stretch_entities_in_range(msp, header_x, header_y, stretch_x=39)
            
            header_found = True
            break
    
    # 8. WELD header processing
    find_and_process_weld_header(msp)
    
    # 9. PL97 and PL31 processing
    process_pl97_and_pl31(msp)
    
    # 10. Layer 3 processing
    process_layer3_lines_and_texts(msp)
    
    # 11. RED DIM lines processing
    process_red_dim_lines(msp, doc)

def process_dxf_file(filepath: str):
    """Process a single DXF file"""
    try:
        doc = ezdxf.readfile(filepath)
        process(doc)
        
        outname = Path(filepath).with_stem(Path(filepath).stem + '_PL')
        doc.saveas(str(outname))
        return str(outname)
    except Exception as e:
        return f"Error processing {filepath}: {str(e)}"

def main():
    """Main entry point for command line usage"""
    if len(sys.argv) < 2:
        sys.exit(1)
    
    results = []
    for filepath in sys.argv[1:]:
        if not filepath.lower().endswith('.dxf'):
            continue
        
        if not Path(filepath).exists():
            continue
        
        try:
            result = process_dxf_file(filepath)
            results.append(f"Processed: {result}")
        except Exception as e:
            results.append(f"Error: {filepath} - {str(e)}")
    
    return results

if __name__ == '__main__':
    main()