# -*- coding: utf-8 -*-
"""
DXF DIMTRIM (R12/R14 호환)
- 파일 선택 창으로 1개/여러 개 DXF 선택
- 회전(기울기) != 0 이고 CYAN(ACI=4) TEXT를 모두 찾음
- 각 TEXT 중심에 (TEXT 높이 + 1mm) x (TEXT 전체 너비 + 1mm)의 회전 BOX 생성
- BOX 내부로 들어오는 PL2 레이어의 (직선) LWPOLYLINE/POLYLINE 구간을 잘라(TRIM)
- 결과를 <원본파일명>_DIMTRIM.dxf 로 저장

변경점:
- DXF 버전에 따라 LWPOLYLINE ↔ POLYLINE(2D) 자동 선택
"""

import math
import os
from dataclasses import dataclass
from typing import List, Tuple

import ezdxf
from ezdxf.math import Vec2

# ---------- 튜닝 가능한 상수 ----------
EPS = 1e-6
EPS_DEG = 1e-4
CHAR_WIDTH_RATIO = 0.60
EXPAND_MM_W = 1.0
EXPAND_MM_H = 1.0

TARGET_LAYER = "PL2"
TARGET_ACI = 4  # CYAN

# ---------- 유틸 ----------

def valid_ent(e) -> bool:
    return (e is not None) and hasattr(e, "dxf") and (e.dxf is not None)

def is_r2000_or_new(doc) -> bool:
    # R12=AC1009, R13=AC1012, R14=AC1014, R2000=AC1015
    return doc.dxfversion not in ("AC1009", "AC1012", "AC1014")

def aci_of_entity(e, doc) -> int:
    try:
        c = int(getattr(e.dxf, "color", 256) or 256)
    except Exception:
        c = 256
    if c not in (0, 256):
        return c
    try:
        layer_name = getattr(e.dxf, "layer", None)
        if layer_name and layer_name in doc.layers:
            return int(doc.layers.get(layer_name).dxf.color or 7)
    except Exception:
        pass
    return 7

def deg_norm(a: float) -> float:
    a = a % 360.0
    if a < 0:
        a += 360.0
    return a

def approx_text_width(txt: str, height: float, width_factor: float) -> float:
    if not txt:
        return 0.0
    return max(0.0, len(txt) * height * max(width_factor, 0.0) * CHAR_WIDTH_RATIO)

def text_center_approx(t, width: float, height: float) -> Vec2:
    insert = Vec2(t.dxf.insert[0], t.dxf.insert[1])
    rot = float(getattr(t.dxf, "rotation", 0.0) or 0.0)
    halign = int(getattr(t.dxf, "halign", 0) or 0)
    valign = int(getattr(t.dxf, "valign", 0) or 0)

    if (halign != 0 or valign != 0) and hasattr(t.dxf, "align_point"):
        ap = t.dxf.align_point
        return Vec2(ap[0], ap[1])

    ang = math.radians(rot)
    along = Vec2(math.cos(ang), math.sin(ang)) * (width * 0.5)
    perp = Vec2(-math.sin(ang), math.cos(ang)) * (height * 0.5)
    return insert + along + perp

@dataclass
class RotBox:
    center: Vec2
    angle_deg: float
    half_w: float
    half_h: float

def to_box_space(p: Vec2, box: RotBox) -> Vec2:
    v = p - box.center
    ang = math.radians(-box.angle_deg)
    return Vec2(v.x * math.cos(ang) - v.y * math.sin(ang),
                v.x * math.sin(ang) + v.y * math.cos(ang))

def liang_barsky_inside(p0: Vec2, p1: Vec2, xmin: float, ymin: float, xmax: float, ymax: float):
    dx = p1.x - p0.x
    dy = p1.y - p0.y
    p = [-dx, dx, -dy, dy]
    q = [p0.x - xmin, xmax - p0.x, p0.y - ymin, ymax - p0.y]
    u0, u1 = 0.0, 1.0
    for pi, qi in zip(p, q):
        if abs(pi) < EPS:
            if qi < 0:
                return (False, 0.0, 0.0)
            continue
        r = qi / pi
        if pi < 0:
            if r > u1: return (False, 0.0, 0.0)
            if r > u0: u0 = r
        else:
            if r < u0: return (False, 0.0, 0.0)
            if r < u1: u1 = r
    return (True, u0, u1)

def subtract_box_inside(p0: Vec2, p1: Vec2, box: RotBox):
    a = to_box_space(p0, box)
    b = to_box_space(p1, box)
    xmin, ymin = -box.half_w, -box.half_h
    xmax, ymax =  box.half_w,  box.half_h

    inside, u0, u1 = liang_barsky_inside(a, b, xmin, ymin, xmax, ymax)
    if not inside:
        return [(p0, p1)]
    if u0 <= 0.0 + EPS and u1 >= 1.0 - EPS:
        return []
    def lerp(pa, pb, t): return Vec2(pa.x + (pb.x - pa.x) * t, pa.y + (pb.y - pa.y) * t)
    pieces = []
    if u0 > 0.0 + EPS:
        pieces.append((lerp(p0, p1, 0.0), lerp(p0, p1, u0)))
    if u1 < 1.0 - EPS:
        pieces.append((lerp(p0, p1, u1), lerp(p0, p1, 1.0)))
    return pieces

def chain_segments_to_paths(segs: List[Tuple[Vec2, Vec2]], tol=1e-6) -> List[List[Vec2]]:
    paths, cur = [], []
    def close_segment():
        nonlocal cur, paths
        if len(cur) >= 2: paths.append(cur)
        cur = []
    for a, b in segs:
        if not cur:
            cur = [a, b]; continue
        if (cur[-1] - a).magnitude < tol:
            cur.append(b)
        else:
            close_segment()
            cur = [a, b]
    close_segment()
    return paths

# ---------- 폴리라인 핸들 ----------

@dataclass
class PolyPath:
    layer: str
    color: int
    linetype: str
    lineweight: int
    closed: bool
    points: List[Vec2]

def extract_pl2_paths(msp) -> Tuple[List[PolyPath], List[object]]:
    paths, originals = [], []

    for ent in list(msp.query("LWPOLYLINE[layer=='%s']" % TARGET_LAYER)):
        if not valid_ent(ent): continue
        try:
            pts_bulge = ent.get_points("xyb")
            if any(abs(b or 0.0) > EPS for _, _, b in pts_bulge):  # 곡선 제외
                continue
            pts = [Vec2(x, y) for x, y, _ in pts_bulge]
            paths.append(PolyPath(
                layer=ent.dxf.layer,
                color=int(getattr(ent.dxf, "color", 256) or 256),
                linetype=str(getattr(ent.dxf, "linetype", "BYLAYER") or "BYLAYER"),
                lineweight=int(getattr(ent.dxf, "lineweight", 0) or 0),
                closed=bool(ent.closed),
                points=pts
            ))
            originals.append(ent)
        except Exception:
            continue

    for ent in list(msp.query("POLYLINE[layer=='%s']" % TARGET_LAYER)):
        if not valid_ent(ent): continue
        try:
            if getattr(ent, "is_3d_polyline", False):
                continue
            pts, has_arc = [], False
            for v in ent.vertices:
                if not valid_ent(v): continue
                loc = v.dxf.location
                pts.append(Vec2(loc.x, loc.y))
                if abs(float(getattr(v.dxf, "bulge", 0.0) or 0.0)) > EPS:
                    has_arc = True
            if has_arc or len(pts) < 2:
                continue
            paths.append(PolyPath(
                layer=ent.dxf.layer,
                color=int(getattr(ent.dxf, "color", 256) or 256),
                linetype=str(getattr(ent.dxf, "linetype", "BYLAYER") or "BYLAYER"),
                lineweight=int(getattr(ent.dxf, "lineweight", 0) or 0),
                closed=bool(ent.is_closed),
                points=pts
            ))
            originals.append(ent)
        except Exception:
            continue

    return paths, originals

def apply_paths(doc, msp, paths: List[PolyPath]):
    """DXF 버전에 맞춰 안전하게 새 폴리라인 추가"""
    r2000p = is_r2000_or_new(doc)
    for p in paths:
        if len(p.points) < 2:
            continue
        coords = [(pt.x, pt.y) for pt in p.points]

        # 공통 속성 (R12에서도 안전)
        dxfattribs = {"layer": p.layer, "linetype": p.linetype}
        if p.color not in (0, 256):
            dxfattribs["color"] = p.color
        if r2000p:
            dxfattribs["lineweight"] = p.lineweight

        if r2000p:
            e = msp.add_lwpolyline(coords, dxfattribs=dxfattribs, format="xy")
            if p.closed and len(coords) >= 3:
                try: e.closed = True
                except Exception: pass
        else:
            # R12/R14: POLYLINE(2D)
            e = msp.add_polyline2d(coords, dxfattribs=dxfattribs)
            if p.closed and len(coords) >= 3:
                try: e.close(True)
                except Exception: pass

# ---------- 메인 처리 ----------

def collect_text_boxes(msp, doc) -> List[RotBox]:
    boxes: List[RotBox] = []
    for t in msp.query("TEXT"):
        if not valid_ent(t):
            continue
        try:
            rot = float(getattr(t.dxf, "rotation", 0.0) or 0.0)
            if abs(deg_norm(rot)) < EPS_DEG:
                continue
            if aci_of_entity(t, doc) != TARGET_ACI:
                continue
            height = float(getattr(t.dxf, "height", 0.0) or 0.0)
            if height <= 0:
                continue
            width_factor = float(getattr(t.dxf, "width", 1.0) or 1.0)
            text_str = str(getattr(t.dxf, "text", "") or "")
            w = approx_text_width(text_str, height, width_factor) + EXPAND_MM_W
            h = height + EXPAND_MM_H
            center = text_center_approx(t, w - EXPAND_MM_W, height)
            boxes.append(RotBox(center=center, angle_deg=rot, half_w=w * 0.5, half_h=h * 0.5))
        except Exception:
            continue
    return boxes

def trim_paths_by_boxes(paths: List[PolyPath], boxes: List[RotBox]) -> List[PolyPath]:
    cur_paths = paths
    for box in boxes:
        new_paths: List[PolyPath] = []
        for p in cur_paths:
            if len(p.points) < 2:
                continue
            segments: List[Tuple[Vec2, Vec2]] = []
            pts = p.points
            n = len(pts)
            rng = range(n - 1) if not p.closed else range(n)
            for i in rng:
                j = (i + 1) % n
                a, b = pts[i], pts[j]
                segments.extend(subtract_box_inside(a, b, box))
            for qpts in chain_segments_to_paths(segments):
                new_paths.append(PolyPath(
                    layer=p.layer, color=p.color, linetype=p.linetype,
                    lineweight=p.lineweight, closed=False, points=qpts
                ))
        cur_paths = new_paths
    return cur_paths

def process_file(path: str):
    print(f"[INFO] Processing: {os.path.basename(path)}")
    try:
        doc = ezdxf.readfile(path)
    except Exception as e:
        print(f"[ERROR] {os.path.basename(path)}: readfile failed: {e}")
        return

    msp = doc.modelspace()
    boxes = collect_text_boxes(msp, doc)

    paths, originals = extract_pl2_paths(msp)

    if not boxes or not paths:
        out_path = out_name(path)
        try:
            doc.saveas(out_path)
            print(f"  - Saved (no-op): {os.path.basename(out_path)}")
        except Exception as e:
            print(f"[ERROR] saveas failed: {e}")
        return

    trimmed = trim_paths_by_boxes(paths, boxes)

    for ent in originals:
        try: msp.delete_entity(ent)
        except Exception: pass

    apply_paths(doc, msp, trimmed)

    out_path = out_name(path)
    try:
        doc.saveas(out_path)
        print(f"  - Saved: {os.path.basename(out_path)} "
              f"(boxes={len(boxes)}, in_paths={len(paths)}, out_paths={len(trimmed)})")
    except Exception as e:
        print(f"[ERROR] saveas failed: {e}")

def out_name(path: str) -> str:
    base, _ = os.path.splitext(path)
    return f"{base}_DIMTRIM.dxf"

def ask_files() -> List[str]:
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk(); root.withdraw()
        paths = filedialog.askopenfilenames(
            title="DXF 파일 선택",
            filetypes=[("DXF files", "*.dxf"), ("All files", "*.*")]
        )
        root.update(); root.destroy()
        return list(paths)
    except Exception as e:
        print(f"[ERROR] 파일 선택 대화상자 오류: {e}")
        return []

def main():
    paths = ask_files()
    if not paths:
        print("선택된 DXF 파일이 없습니다."); return
    for p in paths:
        process_file(p)
    print("프로그램이 완료되었습니다.")

if __name__ == "__main__":
    main()
