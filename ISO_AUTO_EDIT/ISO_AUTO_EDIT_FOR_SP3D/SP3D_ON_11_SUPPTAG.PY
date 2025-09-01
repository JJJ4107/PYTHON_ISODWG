import ezdxf
import math
import os
import sys
import traceback
from collections import defaultdict

CYAN = 4
RED = 1
YELLOW = 2
SL1_LENGTH = 4.4
CIRCLE_RADIUS = 1.75
HALF_SL1 = CIRCLE_RADIUS

def calc_distance(p1, p2):
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])

def extract_points(ent):
    try:
        if not ent or not hasattr(ent, 'dxf') or ent.dxf is None:
            return []
        t = ent.dxftype()
        if t == 'LINE':
            return [(ent.dxf.start.x, ent.dxf.start.y), (ent.dxf.end.x, ent.dxf.end.y)]
        if t == 'LWPOLYLINE':
            return [tuple(pt[:2]) for pt in ent.get_points()]
        if t == 'POLYLINE':
            return [(v.dxf.location.x, v.dxf.location.y) for v in ent.vertices]
    except:
        pass
    return []

def has_curve(ent):
    t = ent.dxftype()
    if t == 'LWPOLYLINE':
        for pt in ent.get_points():
            if len(pt) > 4 and abs(pt[4]) > 1e-3:
                return True
    if t == 'POLYLINE':
        for v in ent.vertices:
            if hasattr(v.dxf, 'bulge') and abs(v.dxf.bulge) > 1e-3:
                return True
    return False

def polyline_length(pts):
    return sum(calc_distance(pts[i], pts[i+1]) for i in range(len(pts)-1))

def midpoint(pts):
    n = len(pts)
    return (sum(p[0] for p in pts)/n, sum(p[1] for p in pts)/n)

def calc_slope(p1, p2):
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    if abs(dx) < 1e-9:
        return float('inf') if dy > 0 else float('-inf')
    return dy / dx

def are_collinear(p1, p2, p3, p4, tolerance=0.1):
    v1 = (p2[0] - p1[0], p2[1] - p1[1])
    v2 = (p3[0] - p1[0], p3[1] - p1[1])
    cross1 = abs(v1[0] * v2[1] - v1[1] * v2[0])
    
    v3 = (p4[0] - p1[0], p4[1] - p1[1])
    cross2 = abs(v1[0] * v3[1] - v1[1] * v3[0])
    
    return cross1 < tolerance and cross2 < tolerance

def slopes_equal(slope1, slope2, tolerance=0.01):
    if slope1 == float('inf') or slope1 == float('-inf'):
        return slope2 == float('inf') or slope2 == float('-inf')
    if slope2 == float('inf') or slope2 == float('-inf'):
        return False
    return abs(slope1 - slope2) < tolerance

def point_to_line_distance(point, line_start, line_end):
    x0, y0 = point
    x1, y1 = line_start
    x2, y2 = line_end
    
    line_length = calc_distance(line_start, line_end)
    if line_length == 0:
        return calc_distance(point, line_start)
    
    t = max(0, min(1, ((x0 - x1) * (x2 - x1) + (y0 - y1) * (y2 - y1)) / (line_length ** 2)))
    projection = (x1 + t * (x2 - x1), y1 + t * (y2 - y1))
    
    return calc_distance(point, projection)

def has_pipe_between_s1_s2(s1_pts, s2_pts, pipe_entities):
    s1_center = midpoint(s1_pts)
    s2_center = midpoint(s2_pts)
    middle_point = midpoint([s1_center, s2_center])
    
    s1_slope = calc_slope(s1_pts[0], s1_pts[1])
    
    for e, pts in pipe_entities:
        if len(pts) < 2:
            continue
        
        for i in range(len(pts) - 1):
            pipe_slope = calc_slope(pts[i], pts[i+1])
            
            if not slopes_equal(s1_slope, pipe_slope, tolerance=0.05):
                continue
            
            dist = point_to_line_distance(middle_point, pts[i], pts[i+1])
            if dist <= 1.0:
                return True
    
    return False

def is_valid_s1(ent):
    if has_curve(ent): return False
    pts = extract_points(ent)
    if len(pts) != 2: return False
    
    if not hasattr(ent.dxf, 'layer') or ent.dxf.layer not in ['WELDS', 'NOZZLES']:
        return False
    
    if abs(pts[0][1] - pts[1][1]) < 1e-6:
        return False
    
    L = polyline_length(pts)
    return 2.8 <= L <= 4.0

def is_ps_candidate(pts):
    return len(pts) == 7 and any(calc_distance(pts[i], pts[i+1]) >= 3.0 for i in range(6))

def point_at_distance(origin, target, dist):
    dx, dy = target[0] - origin[0], target[1] - origin[1]
    length = math.hypot(dx, dy)
    if length == 0:
        return origin
    ux, uy = dx / length, dy / length
    return (origin[0] + ux * dist, origin[1] + uy * dist)

def find_arrow_lines(arrow_entities, a1_points):
    arrow_lines = []
    for e, pts in arrow_entities:
        if len(pts) == 2:
            line_length = calc_distance(pts[0], pts[1])
            if line_length <= 1.0:
                for a1_pt in [a1_points[0], a1_points[-1]]:
                    for line_pt in pts:
                        if calc_distance(a1_pt, line_pt) <= 0.1:
                            arrow_lines.append(e)
                            break
    return arrow_lines

def process_doc(doc):
    """Process a single DXF document (in-memory runner entry point)"""
    msp = doc.modelspace()
    
    # Pre-cache entities by layer for optimization
    entities_by_layer = defaultdict(list)
    all_entities = []
    
    for e in msp:
        all_entities.append(e)
        if hasattr(e.dxf, 'layer'):
            entities_by_layer[e.dxf.layer].append((e, extract_points(e)))
    
    # Process S1 entities
    s1_list = []
    for e in all_entities:
        if is_valid_s1(e):
            pts = extract_points(e)
            if pts and len(pts) == 2:
                s1_list.append({'ent': e, 'pts': pts})
    
    # Cache PIPE entities for reuse
    pipe_entities = entities_by_layer.get('PIPE', [])
    arrow_entities = entities_by_layer.get('ARROW', [])
    
    croschk = []
    for i, rec1 in enumerate(s1_list):
        for j, rec2 in enumerate(s1_list):
            if i >= j:
                continue
            
            if not hasattr(rec1['ent'], 'dxf') or not hasattr(rec2['ent'], 'dxf'):
                continue
            
            len1 = polyline_length(rec1['pts'])
            len2 = polyline_length(rec2['pts'])
            if abs(len1 - len2) > 0.2:
                continue
            
            slope1 = calc_slope(rec1['pts'][0], rec1['pts'][1])
            slope2 = calc_slope(rec2['pts'][0], rec2['pts'][1])
            if not slopes_equal(slope1, slope2):
                continue
            
            if are_collinear(rec1['pts'][0], rec1['pts'][1], 
                           rec2['pts'][0], rec2['pts'][1]):
                continue
            
            all_distances = [calc_distance(a, b) for a in rec1['pts'] for b in rec2['pts']]
            dmin = min(all_distances)
            dmax = max(all_distances)
            
            if not (3.0 <= dmin <= 7.0 and 3.0 <= dmax <= 7.0):
                continue
            
            if any(calc_distance(p1, p2) <= 0.2 for p1 in rec1['pts'] for p2 in rec2['pts']):
                continue
            
            if not has_pipe_between_s1_s2(rec1['pts'], rec2['pts'], pipe_entities):
                continue

            rec1['ent'].dxf.color = CYAN
            rec2['ent'].dxf.color = CYAN
            center1 = midpoint(rec1['pts'])

            A1 = next(({'ent':e,'pts':extract_points(e)} for e in all_entities 
                      if len(extract_points(e))==3 and 
                      any(calc_distance(p,center1)<=1 for p in extract_points(e))), None)
            if not A1: continue
            
            mid_p2 = A1['pts'][1]
            A2 = next(({'ent':e,'pts':extract_points(e)} for e in all_entities 
                      if e is not A1['ent'] and len(extract_points(e)) in (2,3) and 
                      any(calc_distance(p,mid_p2)<=0.3 for p in extract_points(e))), None)
            if not A2: continue
            
            A2['ent'].dxf.color = RED
            farpt = max(A2['pts'], key=lambda p: calc_distance(p, center1))
            PS = next(({'ent':e,'pts':extract_points(e)} for e in all_entities 
                      if is_ps_candidate(extract_points(e)) and 
                      any(calc_distance(p,farpt)<=7 for p in extract_points(e))), None)
            if not PS: continue
            
            PS['ent'].dxf.color = CYAN
            ps_point = min(PS['pts'], key=lambda p: calc_distance(p, center1))
            line = msp.add_line(center1, ps_point, dxfattribs={'color': CYAN, 'layer': 'SUPP'})
            croschk.append({'s1': rec1['ent'], 's2': rec2['ent'], 'line': line, 'ps': ps_point})
            
            arrow_lines = find_arrow_lines(arrow_entities, A1['pts'])
            for arrow_line in arrow_lines:
                msp.delete_entity(arrow_line)
            
            msp.delete_entity(A1['ent'])
            msp.delete_entity(A2['ent'])
            break

    supptag = []
    for i, rec1 in enumerate(s1_list):
        for j, rec2 in enumerate(s1_list):
            if i >= j: continue
            
            if not hasattr(rec1['ent'], 'dxf') or not hasattr(rec2['ent'], 'dxf'):
                continue
            
            len1 = polyline_length(rec1['pts'])
            len2 = polyline_length(rec2['pts'])
            if abs(len1 - len2) > 0.2:
                continue
            
            slope1 = calc_slope(rec1['pts'][0], rec1['pts'][1])
            slope2 = calc_slope(rec2['pts'][0], rec2['pts'][1])
            if not slopes_equal(slope1, slope2):
                continue
            
            if are_collinear(rec1['pts'][0], rec1['pts'][1], 
                           rec2['pts'][0], rec2['pts'][1]):
                continue
            
            all_distances = [calc_distance(a, b) for a in rec1['pts'] for b in rec2['pts']]
            dmin = min(all_distances)
            dmax = max(all_distances)
            
            if not (3.0 <= dmin <= 7.0 and 3.0 <= dmax <= 7.0):
                continue
            
            if any(calc_distance(p1, p2) <= 0.2 for p1 in rec1['pts'] for p2 in rec2['pts']):
                continue
            
            if not has_pipe_between_s1_s2(rec1['pts'], rec2['pts'], pipe_entities):
                continue
            
            pts1, pts2 = rec1['pts'], rec2['pts']
            center_sl1 = midpoint([midpoint(pts1), midpoint(pts2)])
            msp.add_circle(center=center_sl1, radius=CIRCLE_RADIUS, dxfattribs={'color': CYAN, 'layer': 'SUPP'})
            
            pt1_sel = max(pts1, key=lambda p1: max(calc_distance(p1, p2) for p2 in pts2))
            pt2_sel = max(pts2, key=lambda p2: calc_distance(pt1_sel, p2))
            
            def trim_and_extend(p_start, p_end):
                t_start = p_start if calc_distance(p_start, center_sl1) <= CIRCLE_RADIUS else point_at_distance(center_sl1, p_start, CIRCLE_RADIUS)
                t_end = p_end if calc_distance(p_end, center_sl1) <= CIRCLE_RADIUS else point_at_distance(center_sl1, p_end, CIRCLE_RADIUS)
                
                dx = t_end[0] - t_start[0]
                dy = t_end[1] - t_start[1]
                current_length = math.hypot(dx, dy)
                
                if current_length == 0: 
                    return None, None
                
                ux, uy = dx / current_length, dy / current_length
                
                mid_x = (t_start[0] + t_end[0]) / 2.0
                mid_y = (t_start[1] + t_end[1]) / 2.0
                half_length = 1.75
                
                new_start = (mid_x - ux * half_length, mid_y - uy * half_length)
                new_end = (mid_x + ux * half_length, mid_y + uy * half_length)
                
                if calc_distance(new_start, center_sl1) <= CIRCLE_RADIUS and calc_distance(new_end, center_sl1) <= CIRCLE_RADIUS:
                    return new_start, new_end
                else:
                    return t_start, t_end
            
            for start, end in [(pt1_sel, pt2_sel), (next(p for p in pts1 if p!=pt1_sel), next(p for p in pts2 if p!=pt2_sel))]:
                ts, te = trim_and_extend(start, end)
                if ts and te:
                    msp.add_line(ts, te, dxfattribs={'color': CYAN, 'layer': 'SUPP'})
            
            msp.delete_entity(rec1['ent'])
            msp.delete_entity(rec2['ent'])
            supptag.append({'s1': rec1['ent'], 's2': rec2['ent'], 'center': center_sl1})
            break

    for rec in croschk:
        match = next((x for x in supptag if x['s1']==rec['s1'] and x['s2']==rec['s2']), None)
        if not match: continue
        
        ln = rec['line']
        ps_to_center_dist = calc_distance(rec['ps'], match['center'])
        if ps_to_center_dist > CIRCLE_RADIUS:
            boundary_point = point_at_distance(rec['ps'], match['center'], ps_to_center_dist - CIRCLE_RADIUS)
            ln.dxf.start = rec['ps']
            ln.dxf.end = (*boundary_point, 0)
        else:
            ln.dxf.start = rec['ps']
            ln.dxf.end = (*match['center'], 0)
        
        msp.delete_entity(rec['s1'])
        msp.delete_entity(rec['s2'])

    # Final adjustment of PS-circle connections
    circles = []
    for e in msp:
        if e.dxftype() == 'CIRCLE' and abs(e.dxf.radius - CIRCLE_RADIUS) < 0.01 and e.dxf.layer == 'SUPP':
            circles.append({'ent': e, 'center': (e.dxf.center.x, e.dxf.center.y)})
    
    ps_entities = []
    for e in msp:
        pts = extract_points(e)
        if is_ps_candidate(pts):
            ps_entities.append({'ent': e, 'pts': pts})
    
    for e in msp:
        if e.dxftype() == 'LINE' and hasattr(e.dxf, 'layer') and e.dxf.layer == 'SUPP' and hasattr(e.dxf, 'color') and e.dxf.color == CYAN:
            line_start = (e.dxf.start.x, e.dxf.start.y)
            line_end = (e.dxf.end.x, e.dxf.end.y)
            
            connected_to_ps = False
            for ps in ps_entities:
                for pt in ps['pts']:
                    if calc_distance(line_start, pt) < 0.1 or calc_distance(line_end, pt) < 0.1:
                        connected_to_ps = True
                        break
                if connected_to_ps:
                    break
            
            if connected_to_ps:
                closest_circle = None
                min_dist = float('inf')
                
                for circle in circles:
                    dist_start = calc_distance(line_start, circle['center'])
                    dist_end = calc_distance(line_end, circle['center'])
                    
                    if dist_start < min_dist:
                        min_dist = dist_start
                        closest_circle = circle
                        is_start_closer = True
                    if dist_end < min_dist:
                        min_dist = dist_end
                        closest_circle = circle
                        is_start_closer = False
                
                if closest_circle and min_dist < 5.0:
                    if is_start_closer:
                        if calc_distance(line_end, closest_circle['center']) > CIRCLE_RADIUS:
                            new_start = point_at_distance(line_end, closest_circle['center'], 
                                                        calc_distance(line_end, closest_circle['center']) - CIRCLE_RADIUS)
                            e.dxf.start = (*new_start, 0)
                        else:
                            e.dxf.start = (*closest_circle['center'], 0)
                    else:
                        if calc_distance(line_start, closest_circle['center']) > CIRCLE_RADIUS:
                            new_end = point_at_distance(line_start, closest_circle['center'], 
                                                      calc_distance(line_start, closest_circle['center']) - CIRCLE_RADIUS)
                            e.dxf.end = (*new_end, 0)
                        else:
                            e.dxf.end = (*closest_circle['center'], 0)
    
    return doc

def main():
    if len(sys.argv) < 2:
        print("Usage: python PLTONEWLINE.py file1.dxf file2.dxf ...")
        sys.exit(1)
    
    files = sys.argv[1:]
    
    for filepath in files:
        try:
            doc = ezdxf.readfile(filepath)
            
            # Process the document
            doc = process_doc(doc)
            
            # Save the processed document
            out_path = os.path.splitext(filepath)[0] + '_SUPP.dxf'
            doc.saveas(out_path)
            
        except Exception as e:
            traceback.print_exc(file=sys.stdout)
            continue

if __name__ == '__main__':
    main()

"""
Time Complexity Analysis:
- Entity iteration: O(n) where n is number of entities
- S1 pair validation: O(m²) where m is number of S1 entities
- Distance calculations: O(1) per calculation
- PIPE checking: O(p) where p is number of PIPE entities
- Overall: O(n + m² × p) in worst case

Optimizations implemented:
1. Pre-caching entities by layer using defaultdict
2. Using indexed loops to avoid redundant pair checking
3. Early termination with continue statements
4. Minimized redundant calculations
5. Efficient data structures for lookups
"""