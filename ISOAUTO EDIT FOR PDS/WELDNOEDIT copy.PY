import ezdxf
import os
import math
from ezdxf.math import Vec2
from tkinter import Tk, filedialog

def distance(p1, p2):
    return math.hypot(p2.x - p1.x, p2.y - p1.y)

def point_to_segment_distance(p: Vec2, a: Vec2, b: Vec2) -> float:
    ap = p - a
    ab = b - a
    ab_len_squared = ab.dot(ab)
    if ab_len_squared == 0:
        return distance(p, a)
    t = max(0, min(1, ap.dot(ab) / ab_len_squared))
    projection = a + ab * t
    return distance(p, projection)

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

Tk().withdraw()
filepaths = filedialog.askopenfilenames(
    title="DXF 파일들을 선택하세요",
    filetypes=[("DXF Files", "*.dxf")]
)
if not filepaths:
    print("❌ 선택된 파일이 없습니다.")
    exit()

for filepath in filepaths:
    print(f"\n📂 처리 중: {os.path.basename(filepath)}")
    doc = ezdxf.readfile(filepath)
    msp = doc.modelspace()

    tolerance_touch = 0.4
    min_sl1_length = 6.0
    target_distance = 6.0
    text_search_radius = 4.0
    weld_radius = 3.0
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
        texts = []
        for txt in msp.query("TEXT"):
            pos = Vec2(txt.dxf.insert.x, txt.dxf.insert.y)
            if distance(pos, center) <= text_search_radius:
                txt.dxf.color = 1
                texts.append(txt)
        poly.dxf.color = 1
        weld_blocks.append({"poly": poly, "texts": texts, "center": center})

    print(f"✅ WELD 블록 수: {len(weld_blocks)}")

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
                cp = cp + vec.normalize() * offset_len
            msp.add_line((cp.x, cp.y), (sp2.x, sp2.y), dxfattribs={'color': 1})

    for sl1 in sl1_to_delete:
        try:
            msp.delete_entity(sl1)
        except Exception as ex:
            print(f"SL1 삭제 오류: {ex}")

    for weld in weld_results:
        poly = weld["weld_poly"]
        if poly.dxftype() == "POLYLINE":
            pts = [Vec2(v.dxf.location.x, v.dxf.location.y) for v in poly.vertices]
        else:
            pts = [Vec2(x, y) for x, y, *_ in poly.get_points()]
        if len(pts) == 3:
            cp = (pts[0] + pts[1]) * 0.5
            msp.add_circle(center=cp, radius=cicle_len / 2, dxfattribs={"color": 2})
        try:
            msp.delete_entity(poly)
        except Exception as ex:
            print(f"❗ WELD 삭제 오류: {ex}")

    for txt in msp.query('TEXT'):
        txt.dxf.color = 2
        txt.dxf.style = "ARIAL"
        txt.dxf.width = 0.86

    if "ARIAL" not in doc.styles:
        doc.styles.new("ARIAL", dxfattribs={"font": "arial.ttf"})

    output_path = os.path.splitext(filepath)[0] + "_wno.dxf"
    doc.saveas(output_path)
    print(f"🎯 최종 이동된 WELD 수: {moved}")
    print(f"📁 저장된 파일: {output_path}")
