# -*- coding: utf-8 -*-
"""
BOM FORM 자동화 (최종 수정 버전)
- T1-T2: 11mm, T2-T3: 91mm, T3-T4: 19mm, T4-T5: 19mm 간격 고정
- T2T width_factor 최대 0.87 제한
- 가장 위쪽 데이터 Y 좌표 기준 (헤더 제외)
- MATLIST와 새로 생성된 요소만 이동/STRETCH
- MATLIST 텍스트 스타일 ARIAL 적용
- 기존 헤더 이동시 재생성 금지
- FN 없을 때 HB/HN Y값으로 V 라인 생성
- STRETCH 단계에서 헤더(PT/COMPONENT/SIZE/Q'TY/WEIGHT)도 이동
- 최종 후처리: ERECTION MATERIALS 미출력 & (T1=='1') & (SIZE≤51) → FABRICATION MATERIALS를 ERECTION MATERIALS로 변경/출력
"""
import os
import math
import traceback
import tkinter as tk
from tkinter import filedialog
import ezdxf

# ─── BOMTEXT 유틸 ────────────────────────────────────────────────────────────
try:
    from BOMTEXT import (
        apply_arial_and_spacing,
        DEFAULT_STYLE_NAME,
        DEFAULT_FONT_FILE,
        DEFAULT_WIDTH_FACTOR,
    )
    HAVE_BOMTEXT = True
except Exception:
    HAVE_BOMTEXT = False
    DEFAULT_STYLE_NAME = "ARIAL"
    DEFAULT_FONT_FILE = "arial.ttf"
    DEFAULT_WIDTH_FACTOR = 0.87
    def apply_arial_and_spacing(*args, **kwargs):
        return 0

# X열 판별 오차(READBOM 없으면 9mm)
try:
    from READBOM import DEFAULT_X_TOL
except Exception:
    DEFAULT_X_TOL = 9.0

# ─── 상수 ────────────────────────────────────────────────────────────────────
# 스캔 범위
X_MIN, X_MAX = 600.0, 841.0
Y_TOP, Y_BOTTOM = 560.0, 250.0

# 행/열 판단
ROW_TOL = 4.0
COL_DEDUP_TOL = 6.0  # CUT 이전 텍스트의 열 그룹화 공차
CUT_AFTER_TOL = 0.1  # CUT 이후 텍스트의 열 구분 공차
CUT_MATCH_TOL = 1.0  # CUT 이후 텍스트 배정 시 허용 공차
ASSIGN_X_TOL = DEFAULT_X_TOL
SHIFT_MAX = 30.0  # 기본 최대 이동거리 (T1~T5 170mm 기준)

# 머리글/재료명 배치
HDR_DY = 10.0
FAB_DY = 21.0
EREC_DY = -5.5  # FX.y - 5.5

# 색상
COLOR_WHITE = 7
COLOR_YELLOW = 2
OUT_TEXT_COLOR = COLOR_YELLOW  # 모든 새 출력 텍스트: 노랑

# VA/HX 검색 영역/기본값
VA_RECT = (600.0, 650.0, 550.0, 590.0)  # x1,x2,y1,y2
HA_RECT = (810.0, 840.0, 250.0, 550.0)
VA_MAX_LEN = 10.0
HA_MAX_LEN = 10.0
VY_DEFAULT = 577.2
HX_DEFAULT = 816.5
V1_X_OFFSET_FROM_T1 = -4.0

# 라인 판정/이동
VERT_DX_TOL = 0.75
HORZ_DY_TOL = 0.75
MOVE_SHORT_X = 27.0
HLINE_MIN_LEN = 150.0
V_SHORT1 = (40.0, 50.0)  # 최대 2개
V_SHORT2 = (8.0, 10.0)   # 최대 2개
TARGET_LINE_LAYERS = {"MATLIST", "MATLINE"}  # 두 레이어 모두 대상

# 추가 상수
T2T_TARGET_WIDTH = 76.5  # T2T 텍스트 목표 폭 (mm)
MAX_WIDTH_FACTOR = 0.87  # 최대 width_factor

# === 고정 간격 상수 ===
T1_T2_SPACING = 11.0   # T1 → T2: 11mm
T2_T3_SPACING = 91.0   # T2 → T3: 91mm  
T3_T4_SPACING = 19.0   # T3 → T4: 19mm (Q'TY)
T4_T5_SPACING = 19.0   # T4 → T5: 19mm (WEIGHT)

# ─── 유틸 ───────────────────────────────────────────────────────────────────
def is_target_layer(ent):
    try:
        return (ent.dxftype() == "LINE") and (ent.dxf.layer.upper() in TARGET_LINE_LAYERS)
    except Exception:
        return False

def text_ref_xy(e):
    try:
        if e.dxftype() == "TEXT":
            if e.dxf.hasattr("align_point"):
                ap = e.dxf.align_point
                if ap is not None:
                    ax, ay = float(ap[0]), float(ap[1])
                    if ax != 0.0 or ay != 0.0:
                        return ax, ay
            ins = getattr(e.dxf, "insert", None)
            if ins is not None:
                return float(ins[0]), float(ins[1])
        elif e.dxftype() == "MTEXT":
            ins = getattr(e.dxf, "insert", None)
            if ins is not None:
                return float(ins[0]), float(ins[1])
    except Exception:
        pass
    return None

def in_band(xy, x_min, x_max, y_bottom, y_top):
    if xy is None: return False
    x, y = xy
    return (x_min <= x <= x_max) and (min(y_bottom, y_top) <= y <= max(y_bottom, y_top))

def get_text_value(e):
    try:
        if e.dxftype() == "TEXT":
            return (e.dxf.text or "").strip()
        elif e.dxftype() == "MTEXT":
            return (e.text or "").strip()
    except Exception:
        return ""
    return ""

def get_text_style_and_height(e, fallback_style=DEFAULT_STYLE_NAME, fallback_height=2.5):
    style = fallback_style
    height = fallback_height
    try:
        if e.dxftype() == "TEXT":
            if e.dxf.hasattr("style"): style = e.dxf.style
            if e.dxf.hasattr("height"): height = float(e.dxf.height)
        elif e.dxftype() == "MTEXT":
            if e.dxf.hasattr("style"): style = e.dxf.style
            if e.dxf.hasattr("char_height"): height = float(e.dxf.char_height)
    except Exception:
        pass
    return style, height

def move_text_entity(e, dx, dy=0.0):
    try:
        if e.dxftype() == "TEXT":
            if e.dxf.hasattr("insert"):
                ins = e.dxf.insert
                e.dxf.insert = (float(ins[0]) + dx, float(ins[1]) + dy)
            if e.dxf.hasattr("align_point"):
                ap = e.dxf.align_point
                if ap is not None:
                    e.dxf.align_point = (float(ap[0]) + dx, float(ap[1]) + dy, float(ap[2]) if len(ap) > 2 else 0.0)
        elif e.dxftype() == "MTEXT":
            if e.dxf.hasattr("insert"):
                ins = e.dxf.insert
                e.dxf.insert = (float(ins[0]) + dx, float(ins[1]) + dy, float(ins[2]) if len(ins) > 2 else 0.0)
    except Exception:
        pass

def create_text(msp, text, x, y, height, style, layer=None, color=OUT_TEXT_COLOR):
    try:
        t = msp.add_text(text, dxfattribs={"height": height, "style": style})
        t.dxf.insert = (x, y)
        if layer: t.dxf.layer = layer
        if color is not None: t.dxf.color = int(color)
        return t
    except Exception:
        return None

def dedup_sorted_positions(xs, tol=COL_DEDUP_TOL):
    if not xs: return []
    xs = sorted(xs)
    groups, cur = [], [xs[0]]
    for v in xs[1:]:
        if abs(v - cur[-1]) <= tol: cur.append(v)
        else: groups.append(cur); cur = [v]
    groups.append(cur)
    return [sum(g)/len(g) for g in groups]

def nearest_index(value, xs):
    if not xs: return None
    best_i, best_d = 0, abs(value - xs[0])
    for i in range(1, len(xs)):
        d = abs(value - xs[i])
        if d < best_d: best_d, best_i = d, i
    return best_i

# LINE 유틸
def line_endpoints(ent):
    try:
        if ent.dxftype() != "LINE": return None
        s = ent.dxf.start; e = ent.dxf.end
        return (float(s[0]), float(s[1])), (float(e[0]), float(e[1]))
    except Exception:
        return None

def line_length(ent):
    pts = line_endpoints(ent)
    if not pts: return 0.0
    (x1,y1),(x2,y2) = pts
    return math.hypot(x2-x1, y2-y1)

def is_horizontal(ent, dy_tol=HORZ_DY_TOL):
    pts = line_endpoints(ent)
    if not pts: return False
    (x1,y1),(x2,y2) = pts
    return abs(y2-y1) <= dy_tol and abs(x2-x1) > 1e-6

def is_vertical(ent, dx_tol=VERT_DX_TOL):
    pts = line_endpoints(ent)
    if not pts: return False
    (x1,y1),(x2,y2) = pts
    return abs(x2-x1) <= dx_tol and abs(y2-y1) > 1e-6

def move_line_x(ent, dx):
    try:
        (x1,y1),(x2,y2) = line_endpoints(ent)
        ent.dxf.start = (x1 + dx, y1, 0.0)
        ent.dxf.end   = (x2 + dx, y2, 0.0)
        return True
    except Exception:
        return False

def set_hline_endpoints(ent, x_left, x_right, y_keep=None):
    try:
        (xa,ya),(xb,yb) = line_endpoints(ent)
        y = (ya + yb)/2.0 if y_keep is None else y_keep
        xl, xr = (x_left, x_right) if x_left <= x_right else (x_right, x_left)
        ent.dxf.start = (xl, y, 0.0)
        ent.dxf.end   = (xr, y, 0.0)
        return True
    except Exception:
        return False

def is_in_rect_both_end(ent, x1, x2, y1, y2):
    pts = line_endpoints(ent)
    if not pts: return False
    (ax,ay),(bx,by) = pts
    return (x1 <= ax <= x2 and y1 <= ay <= y2) and (x1 <= bx <= x2 and y1 <= by <= y2)

def copy_line(msp, line_ent, dx=0, dy=0, layer=None, color=None):
    """LINE 엔티티를 복사하여 이동"""
    pts = line_endpoints(line_ent)
    if not pts: return None
    (x1,y1),(x2,y2) = pts
    new_line = msp.add_line(
        (x1 + dx, y1 + dy),
        (x2 + dx, y2 + dy),
        dxfattribs={}
    )
    if layer:
        new_line.dxf.layer = layer
    if color is not None:
        new_line.dxf.color = int(color)
    return new_line

# ─── BLOCK → explode ─────────────────────────────────────────────────────────
def explode_block_inserts(msp):
    inserts = list(msp.query("INSERT"))
    if not inserts:
        return 0
    exploded = 0
    for ins in inserts:
        try:
            ins.explode(msp)  # ezdxf 0.18+: explode to target layout
            msp.delete_entity(ins)
            exploded += 1
        except Exception:
            try:
                ins.explode()
                msp.delete_entity(ins)
                exploded += 1
            except Exception:
                pass
    if exploded:
        print(f" - BLOCK INSERT exploded: {exploded}개")
    return exploded

# ─── SIZE 값 추출 함수 ───────────────────────────────────────────────────────
def extract_size_value(text):
    """텍스트에서 SIZE 숫자값 추출"""
    import re
    m = re.search(r"(\d+(\.\d+)?)", text)
    if m:
        try:
            return float(m.group(1))
        except Exception:
            pass
    return None

# ─── 메인 처리 ───────────────────────────────────────────────────────────────
def process_file(path):
    print(f"\n[INFO] Processing: {path}")
    doc = ezdxf.readfile(path)
    msp = doc.modelspace()

    # 새로 생성된 요소 추적
    new_entities = set()
    
    # 0) BLOCK → explode (BLOCK 내부 TEXT/MTEXT 처리 가능)
    explode_block_inserts(msp)

    # 1) BOMTEXT 적용(스캔 범위) - MATLIST 레이어만
    apply_arial_and_spacing(
        doc, msp,
        x_min=X_MIN, x_max=X_MAX,
        y_bottom=Y_BOTTOM, y_top=Y_TOP,
        width_factor=DEFAULT_WIDTH_FACTOR,
        style_name=DEFAULT_STYLE_NAME,
        font_file=DEFAULT_FONT_FILE
    )

    # MATLIST 레이어의 TEXT 스타일을 ARIAL로 변경 + width_factor 제한
    for e in msp:
        if e.dxftype() in ("TEXT", "MTEXT"):
            try:
                if e.dxf.layer.upper() == "MATLIST":
                    e.dxf.style = DEFAULT_STYLE_NAME
                    if e.dxftype() == "TEXT" and hasattr(e.dxf, 'width'):
                        if e.dxf.width > MAX_WIDTH_FACTOR:
                            e.dxf.width = MAX_WIDTH_FACTOR
            except Exception:
                pass

    # 2) TEXT 수집(모델공간 내, BLOCK explode 후 포함)
    items = []
    for e in msp:
        if e.dxftype() not in ("TEXT", "MTEXT"): continue
        xy = text_ref_xy(e)
        if not in_band(xy, X_MIN, X_MAX, Y_BOTTOM, Y_TOP): continue
        s = get_text_value(e)
        if s == "": continue
        items.append({"e": e, "x": xy[0], "y": xy[1], "s": s})

    if not items:
        print(" - 지정 구간 내 텍스트 없음 → 저장만 수행.")
        out = os.path.splitext(path)[0] + "_BOMFORM.DXF"
        doc.saveas(out); print(f" - 저장: {out}"); return

    # 3) 첫 행 판단 및 TTOL
    y_max = max(it["y"] for it in items)
    first_row = [it for it in items if abs(it["y"] - y_max) <= ROW_TOL]
    first_row_sorted = sorted(first_row, key=lambda t: t["x"])
    
    # 'CUT' 포함 텍스트 찾기
    cut_index = -1
    cut_x = None
    for i, item in enumerate(first_row_sorted):
        if "CUT" in item["s"].upper():
            cut_index = i
            cut_x = item["x"]
            print(f" - 'CUT' 발견: 위치 {i}, X={cut_x:.3f}, 텍스트='{item['s']}'")
            break
    
    # TTOL 생성
    TTOL_raw = []
    if cut_index >= 0:
        before_cut = [it["x"] for it in first_row_sorted[:cut_index+1]]
        before_cut_grouped = []
        if before_cut:
            before_cut_grouped = dedup_sorted_positions(before_cut, tol=COL_DEDUP_TOL)
            TTOL_raw.extend(before_cut_grouped)
        after_cut = [it["x"] for it in first_row_sorted[cut_index+1:]]
        after_cut_unique = []
        if after_cut:
            for x in after_cut:
                if not after_cut_unique or abs(x - after_cut_unique[-1]) > CUT_AFTER_TOL:
                    after_cut_unique.append(x)
            TTOL_raw.extend(after_cut_unique)
        print(f" - CUT 이전 열: {len(before_cut_grouped)}개 (공차 {COL_DEDUP_TOL}mm)")
        print(f" - CUT 이후 열: {len(after_cut_unique)}개 (공차 {CUT_AFTER_TOL}mm)")
    else:
        TTOL_raw = dedup_sorted_positions([it["x"] for it in first_row_sorted], tol=COL_DEDUP_TOL)
    
    print(" - TTOL (첫 행 X열, 좌→우):")
    for i, x in enumerate(TTOL_raw, start=1):
        print(f"    T{i}: X={x:.3f}")

    if not TTOL_raw:
        sorted_all = sorted(items, key=lambda t: (-t["y"], t["x"]))
        TTOL_raw = dedup_sorted_positions([t["x"] for t in sorted_all[:5]], tol=COL_DEDUP_TOL)
        print(" - 임시 TTOL:")
        for i, x in enumerate(TTOL_raw, start=1):
            print(f"    T{i}: X={x:.3f}")

    if not TTOL_raw:
        print(" - 유효한 열 없음 → 저장만 수행.")
        out = os.path.splitext(path)[0] + "_BOMFORM.DXF"
        doc.saveas(out); print(f" - 저장: {out}"); return

    # 4) 열 이동량(TN 고정) 계산
    X_TN = max(TTOL_raw)
    t1_value_preview = None
    first_row_preview = [it for it in first_row if abs(it["y"] - y_max) <= ROW_TOL]
    for it in first_row_preview:
        if len(TTOL_raw) > 0 and abs(it["x"] - TTOL_raw[0]) <= COL_DEDUP_TOL:
            t1_value_preview = get_text_value(it["e"])
            break
    
    SHIFT_BASE = 30.0
    DIST_BASE = 170.0
    should_adjust = (t1_value_preview == "1")
    if should_adjust and len(TTOL_raw) >= 5:
        t1_x = TTOL_raw[0]; t5_x = TTOL_raw[4]
        actual_dist = abs(t5_x - t1_x)
        SHIFT_MAX_ADJUSTED = SHIFT_BASE * (actual_dist / DIST_BASE)
        print(f" - T1='1': T1~T5 거리 {actual_dist:.1f}mm (기준 {DIST_BASE}mm)")
        print(f" - 최대 이동거리 조정: {SHIFT_MAX_ADJUSTED:.1f}mm (기준 {SHIFT_BASE}mm)")
    else:
        SHIFT_MAX_ADJUSTED = SHIFT_MAX
        if not should_adjust:
            print(f" - T1≠'1': 기본 이동거리 사용 {SHIFT_MAX_ADJUSTED:.1f}mm")
        else:
            print(f" - T5 없음: 기본 이동거리 사용 {SHIFT_MAX_ADJUSTED:.1f}mm")
    
    dists = [abs(x - X_TN) for x in TTOL_raw]
    d_max = max(dists) if dists else 0.0
    shifts = [(0.0 if d_max <= 1e-9 else SHIFT_MAX_ADJUSTED * (d / d_max)) for d in dists]
    TTOL_new = [x + dx for x, dx in zip(TTOL_raw, shifts)]
    print(" - 열 이동(좌→우):")
    for i, (x0, dx, x1) in enumerate(zip(TTOL_raw, shifts, TTOL_new), start=1):
        pin = " (TN 고정)" if abs(x0 - X_TN) < 1e-6 else ""
        print(f"    T{i}: {x0:.3f} → {x1:.3f} (dx=+{dx:.3f}){pin}")

    # === 고정 간격 적용 ===
    # T1부터 시작하여 고정 간격으로 T2, T3, T4, T5 위치 재계산
    if len(TTOL_new) >= 1:
        t1_x = TTOL_new[0]
        if len(TTOL_new) >= 2:
            TTOL_new[1] = t1_x + T1_T2_SPACING  # T2 = T1 + 11mm
        if len(TTOL_new) >= 3:
            TTOL_new[2] = t1_x + T1_T2_SPACING + T2_T3_SPACING  # T3 = T1 + 11 + 91 = T1 + 102mm
        if len(TTOL_new) >= 4:
            TTOL_new[3] = t1_x + T1_T2_SPACING + T2_T3_SPACING + T3_T4_SPACING  # T4 = T1 + 102 + 19 = T1 + 121mm
        if len(TTOL_new) >= 5:
            TTOL_new[4] = t1_x + T1_T2_SPACING + T2_T3_SPACING + T3_T4_SPACING + T4_T5_SPACING  # T5 = T1 + 121 + 19 = T1 + 140mm
        
        print(" - 고정 간격 적용 후 열 위치:")
        for i, x in enumerate(TTOL_new[:5], start=1):
            print(f"    T{i}: X={x:.3f}")

    # 5) 텍스트 배정/이동/레이어 + 'PT' 포함시 PTXT
    assigned = []
    original_layers = {}
    header_keywords = ["PT", "COMPONENT", "SIZE", "Q'TY", "WEIGHT"]
    
    # TOTAL WEIGHT가 있는 Y 위치 찾기
    total_weight_y = None
    for it in items:
        if "TOTAL WEIGHT" in it["s"].upper():
            total_weight_y = it["y"]
            print(f" - 'TOTAL WEIGHT' 발견: Y={total_weight_y:.2f}")
            break
    
    # CUT이 포함된 텍스트의 Y 위치 찾기 (첫 행 제외)
    cut_text_y = None
    for it in items:
        # 첫 행이 아닌 텍스트 중에서 CUT 찾기
        if abs(it["y"] - y_max) > ROW_TOL and "CUT" in it["s"].upper():
            if cut_text_y is None or it["y"] > cut_text_y:  # 가장 위쪽 CUT 찾기
                cut_text_y = it["y"]
                print(f" - 'CUT' 포함 텍스트 발견 (첫 행 제외): Y={cut_text_y:.2f}, 텍스트='{it['s']}'")
    
    for it in items:
        original_layer = it["e"].dxf.layer.upper()
        original_layers[it["e"]] = original_layer
        is_header = any(keyword in it["s"].upper() for keyword in header_keywords)
        
        # TOTAL이 포함된 텍스트인지 확인
        has_total = "TOTAL" in it["s"].upper()
        
        # CUT이 포함된 텍스트인지 확인 (첫 행 제외)
        has_cut = False
        if abs(it["y"] - y_max) > ROW_TOL:  # 첫 행이 아닌 경우만
            has_cut = "CUT" in it["s"].upper()
        
        # CUT 텍스트 이후(아래)의 텍스트인지 확인
        is_after_cut = False
        if cut_text_y is not None:
            is_after_cut = it["y"] < (cut_text_y - ROW_TOL)
        
        # TOTAL WEIGHT 이후(아래)의 텍스트인지 확인
        is_after_total_weight = False
        if total_weight_y is not None:
            is_after_total_weight = it["y"] < (total_weight_y - ROW_TOL)
        
        # 어느 열(T1~T5)에 속하는지 판단
        i_col = nearest_index(it["x"], TTOL_raw)
        
        if original_layer == "MATLIST" or is_header:
            # TOTAL, CUT이 포함되거나 TOTAL WEIGHT/CUT 이후면 고정 간격 적용하지 않음
            if has_total or has_cut or is_after_total_weight or is_after_cut:
                # 원래 이동량만 적용 (고정 간격 적용 안함)
                if i_col is not None and i_col < len(shifts):
                    shift_amount = shifts[i_col]
                else:
                    shift_amount = 0.0
                if has_total:
                    print(f"   - TOTAL 포함 텍스트 제외: '{it['s']}' (원래 이동량만 적용: {shift_amount:.2f}mm)")
                elif has_cut:
                    print(f"   - CUT 포함 텍스트 제외: '{it['s']}' (원래 이동량만 적용: {shift_amount:.2f}mm)")
                elif is_after_cut:
                    print(f"   - CUT 이후 텍스트 제외: '{it['s']}' (Y={it['y']:.2f})")
                elif is_after_total_weight:
                    print(f"   - TOTAL WEIGHT 이후 텍스트 제외: '{it['s']}' (Y={it['y']:.2f})")
            else:
                # 각 열을 고정 간격 위치로 직접 이동
                if i_col is not None and i_col < len(TTOL_new):
                    new_x = TTOL_new[i_col]
                    shift_amount = new_x - it["x"]
                else:
                    shift_amount = 0.0
            
            move_text_entity(it["e"], shift_amount, 0.0)
            
            if i_col is not None and original_layer == "MATLIST":
                try: 
                    it["e"].dxf.layer = f"T{i_col+1}"
                except Exception: 
                    pass
                try:
                    if "PT" in it["s"].upper():
                        it["e"].dxf.layer = "PTXT"
                except Exception:
                    pass
        else:
            shift_amount = 0.0
            i_col = None
        
        xy_new = text_ref_xy(it["e"]) or (it["x"] + shift_amount, it["y"])
        
        assigned.append({
            "col": i_col + 1 if i_col is not None else 0,
            "x0": it["x"], 
            "y0": it["y"],
            "x1": xy_new[0], 
            "y1": xy_new[1],
            "s": it["s"], 
            "ent": it["e"],
            "shift": shift_amount,
            "original_layer": original_layer,
            "has_total": has_total,
            "has_cut": has_cut,
            "after_total_weight": is_after_total_weight,
            "after_cut": is_after_cut
        })

    print(" - TEXT 배정/이동 결과:")
    for a in sorted(assigned, key=lambda r: (-r["y0"], r["x0"])):
        print(f"    [T{a['col']}] '{a['s']}' @({a['x0']:.2f},{a['y0']:.2f}) → ({a['x1']:.2f},{a['y1']:.2f})")

    # ── 첫 행/TYPE1/머리글 좌표 계산 ────────────────────────────────────────
    first_row_assigned = [a for a in assigned if abs(a["y0"] - y_max) <= ROW_TOL]
    
    # 헤더 제외 실제 데이터 최상단 Y
    data_y_max = None
    header_keywords_all = ["PT", "COMPONENT", "SIZE", "Q'TY", "WEIGHT", "FABRICATION", "ERECTION"]
    for a in assigned:
        text_upper = a["s"].upper()
        is_header2 = any(keyword in text_upper for keyword in header_keywords_all)
        if not is_header2:
            if data_y_max is None or a["y0"] > data_y_max:
                data_y_max = a["y0"]
    if data_y_max is None:
        data_y_max = y_max
    print(f" - 데이터 최상단 Y값: {data_y_max:.2f} (헤더 제외)")
    
    # T1, 스타일
    t1_value = None
    t1_ent = None
    first_row_t1 = [a for a in first_row_assigned if a["col"] == 1]
    if first_row_t1:
        pick = sorted(first_row_t1, key=lambda r: r["x1"])[0]
        t1_value = pick["s"]; t1_ent = pick["ent"]

    style, height = get_text_style_and_height(t1_ent or assigned[0]["ent"], DEFAULT_STYLE_NAME, 2.5)

    IS_TYPE1 = (t1_value == "PT")
    need_headers = (t1_value == "1") or IS_TYPE1

    existing_headers_moved = False
    P_pos, C_pos = {}, {}
    
    # 헤더 고정 X 좌표 (고정 간격 적용)
    header_x_positions = {}
    if len(TTOL_new) >= 3:
        pt_x   = TTOL_new[0]
        comp_x = TTOL_new[1]
        size_x = TTOL_new[2]
        qty_x  = TTOL_new[3] if len(TTOL_new) >= 4 else size_x + T3_T4_SPACING
        weight_x = TTOL_new[4] if len(TTOL_new) >= 5 else qty_x + T4_T5_SPACING
        
        header_x_positions = {
            1: pt_x,           # PT
            2: comp_x,         # COMPONENT  
            3: size_x,         # SIZE
            4: qty_x,          # Q'TY
            5: weight_x        # WEIGHT
        }
        print(f" - 헤더 X 좌표: PT={pt_x:.1f}, COMP={comp_x:.1f}, SIZE={size_x:.1f}, Q'TY={qty_x:.1f}, WEIGHT={weight_x:.1f}")
    
    if need_headers:
        for a in assigned:
            if any(keyword == a["s"].upper() for keyword in ["PT", "COMPONENT", "SIZE", "Q'TY", "WEIGHT"]):
                if a["shift"] > 0:
                    existing_headers_moved = True
                    break
        if not existing_headers_moved:
            y_hdr = data_y_max + HDR_DY
            headers = ["PT", "COMPONENT", "SIZE", "Q'TY", "WEIGHT"]
            print(f" - 머리글 출력(Y={y_hdr:.2f})")
            for i, label in enumerate(headers, start=1):
                if i in header_x_positions:
                    x_hdr = header_x_positions[i]
                    new_text = create_text(msp, label, x_hdr, y_hdr, height, style, color=OUT_TEXT_COLOR)
                    if new_text:
                        new_entities.add(new_text)
                    P_pos[i] = (x_hdr, y_hdr)
                    print(f"    - {label}: X={x_hdr:.2f}")
        else:
            print(" - 기존 헤더가 이동됨: 재생성 금지")
            
        # FABRICATION MATERIALS (없는 경우만 생성)
        if 1 <= len(TTOL_new):
            fab_exists = False
            for a in assigned:
                if "FABRICATION MATERIALS" in a["s"].upper():
                    fab_exists = True
                    break
            if not fab_exists:
                x_fab, y_fab = TTOL_new[0], data_y_max + FAB_DY
                new_text = create_text(msp, "FABRICATION MATERIALS", x_fab, y_fab, height, style, color=OUT_TEXT_COLOR)
                if new_text:
                    new_entities.add(new_text)

    # C1..C5 : 첫 행 각 컬럼 좌표
    for i in range(1, min(5, len(TTOL_new)) + 1):
        cand = [a for a in first_row_assigned if a["col"] == i]
        if cand:
            a = sorted(cand, key=lambda r: r["x1"])[0]
            C_pos[i] = (a["x1"], a["y1"])

    # ── VA/HX 찾기 + VB 추가 ──────────────────────────────────────────────
    vx1, vx2, vy1, vy2 = VA_RECT
    va_candidates = []
    for e in msp.query("LINE"):
        if is_in_rect_both_end(e, vx1, vx2, vy1, vy2) and line_length(e) <= VA_MAX_LEN:
            va_candidates.append(e)
    VY = VY_DEFAULT
    if va_candidates:
        def upper_y(ent):
            (x1,y1),(x2,y2) = line_endpoints(ent); return max(y1,y2)
        best = sorted(va_candidates, key=lambda ent: upper_y(ent), reverse=True)[0]
        (x1,y1),(x2,y2) = line_endpoints(best)
        VY = min(y1, y2)

    # VB 라인 찾기: X 810~820mm 사이, 길이 500mm 이상 수직선
    VB_line = None
    VB_X = None
    vb_search_x_min, vb_search_x_max = 810.0, 820.0  # 변경된 범위
    vb_min_length = 500.0
    
    for e in msp.query("LINE"):
        if is_vertical(e):
            pts = line_endpoints(e)
            if pts:
                (x1, y1), (x2, y2) = pts
                x_avg = (x1 + x2) / 2.0
                length = line_length(e)
                if vb_search_x_min <= x_avg <= vb_search_x_max and length >= vb_min_length:
                    if VB_line is None or length > line_length(VB_line):
                        VB_line = e
                        VB_X = x_avg
    
    if VB_line:
        try:
            VB_line.dxf.layer = "VB"
            print(f" - VB 라인 발견: X={VB_X:.2f}, 길이={line_length(VB_line):.2f}mm")
        except Exception:
            pass

    hx1, hx2, hy1, hy2 = HA_RECT
    ha_candidates = []
    for e in msp.query("LINE"):
        if is_in_rect_both_end(e, hx1, hx2, hy1, hy2) and line_length(e) <= HA_MAX_LEN:
            ha_candidates.append(e)
    HX = HX_DEFAULT
    if ha_candidates:
        def small_x(ent):
            (x1,y1),(x2,y2) = line_endpoints(ent); return min(x1,x2)
        pick = sorted(ha_candidates, key=lambda ent: small_x(ent))[0]
        (x1,y1),(x2,y2) = line_endpoints(pick); HX = min(x1,x2)
    
    # VB가 존재하면 HX를 VB_X로 대체
    if VB_X is not None:
        print(f" - VB 존재: H 라인 끝점을 {HX:.2f} → {VB_X:.2f}로 변경")
        HX = VB_X

    # ── V1/HN 그리기 ───────────────────────────────────────────────────────
    t1_all = [a for a in assigned if a["col"] == 1]
    if t1_all:
        y_last_t1 = min(a["y1"] for a in t1_all) - 3.0
    else:
        y_last_t1 = min(a["y1"] for a in assigned) - 3.0

    x_t1 = TTOL_new[0]
    x_v1 = x_t1 + V1_X_OFFSET_FROM_T1
    y_top_v1 = VY
    y_bot_v1 = y_last_t1
    if y_bot_v1 > y_top_v1:
        y_bot_v1, y_top_v1 = y_top_v1, y_bot_v1

    v1_line = msp.add_line((x_v1, y_top_v1), (x_v1, y_bot_v1), dxfattribs={"color": COLOR_WHITE, "layer": "V1"})
    hn_line = msp.add_line((x_v1, y_bot_v1), (HX, y_bot_v1), dxfattribs={"color": COLOR_WHITE, "layer": "HN"})
    new_entities.add(v1_line)
    new_entities.add(hn_line)

    # ── ERECTION MATERIALS (1차 규칙: T3에 'ERECTION' 포함) ────────────────
    erection_in_t3 = False
    fabrication_t3_y = None
    for a in assigned:
        if a["col"] == 3:
            if "ERECTION" in a["s"].upper():
                erection_in_t3 = True
                print(f" - T3에 'ERECTION' 발견: '{a['s']}'")
            if "FABRICATION" in a["s"].upper():
                fabrication_t3_y = a["y1"]
                print(f" - T3에 'FABRICATION' 발견: '{a['s']}', Y={fabrication_t3_y:.2f}")
    if erection_in_t3 and fabrication_t3_y and len(TTOL_new) >= 1:
        erec_exists = any("ERECTION MATERIALS" in a["s"].upper() for a in assigned)
        if not erec_exists:
            erection_y = fabrication_t3_y + EREC_DY
            x_em = TTOL_new[0]
            new_text = create_text(msp, "ERECTION MATERIALS", x_em, erection_y, height, style, color=OUT_TEXT_COLOR)
            if new_text:
                new_entities.add(new_text)
            print(f" - ERECTION MATERIALS 출력: X={x_em:.2f}, Y={erection_y:.2f}")

    # ══════════════════════════════════════════════════════════════════════════
    # 추가 기능 준비: FN/H 라인 등
    # ══════════════════════════════════════════════════════════════════════════
    fn_row = None
    fn_y_extra = None
    rows_by_y = {}
    assigned_sorted_by_y = sorted(assigned, key=lambda a: a["y1"], reverse=True)
    for a in assigned_sorted_by_y:
        placed = False
        for y_key in sorted(rows_by_y.keys(), reverse=True):
            if abs(a["y1"] - y_key) <= ROW_TOL:
                rows_by_y[y_key].append(a)
                placed = True
                break
        if not placed:
            rows_by_y[a["y1"]] = [a]
    for y_key in sorted(rows_by_y.keys(), reverse=True):
        row = rows_by_y[y_key]
        for a in row:
            if a["col"] <= 5 and "TOTAL" in a["s"].upper():
                fn_row = row
                fn_y_extra = y_key
                print(f" - FN 발견: Y={fn_y_extra:.2f}, 텍스트: '{a['s']}'")
                break
        if fn_row:
            break
    
    # 대상 레이어 라인 색상
    for e in msp.query("LINE"):
        if is_target_layer(e):
            try: e.dxf.color = COLOR_WHITE
            except Exception: pass

    # 수평 라인 수집/정렬
    hlines = []
    for e in msp.query("LINE"):
        if not is_target_layer(e): continue
        if is_horizontal(e) and line_length(e) >= HLINE_MIN_LEN:
            hlines.append(e)
    h_sorted = sorted(
        hlines,
        key=lambda ent: max(line_endpoints(ent)[0][1], line_endpoints(ent)[1][1]),
        reverse=True
    )
    
    # H3 지정(FN 아래 첫 라인)
    h3_line = None
    h3_index = -1
    if fn_y_extra and h_sorted:
        for idx, h in enumerate(h_sorted):
            (x1, y1), (x2, y2) = line_endpoints(h)
            h_y = (y1 + y2) / 2.0
            if h_y < fn_y_extra:
                h3_line = h
                h3_index = idx
                print(f" - FN({fn_y_extra:.2f}) 바로 아래 라인을 H3로 지정: Y={h_y:.2f}")
                break
    
    # Hn 레이어명 할당
    for idx, h in enumerate(h_sorted):
        if h == h3_line:
            h.dxf.layer = "H3"
        elif idx < h3_index or h3_index == -1:
            h.dxf.layer = f"H{idx+1}"
        else:
            h.dxf.layer = f"H{idx+2}"

    # 짧은 라인 이동(27mm)
    moved_once = set()
    def can_move(v):
        try: return v.dxf.handle not in moved_once
        except Exception: return True
    def pick_and_move_lines(max_count, rng):
        picked = 0
        for v in msp.query("LINE"):
            if picked >= max_count: break
            if not is_target_layer(v): continue
            if not (is_vertical(v) or is_horizontal(v)): continue
            L = line_length(v)
            if rng[0] <= L <= rng[1]:
                if can_move(v) and move_line_x(v, MOVE_SHORT_X):
                    try: moved_once.add(v.dxf.handle)
                    except Exception: pass
                    picked += 1
        return picked
    for h in h_sorted:
        moved_1 = pick_and_move_lines(2, V_SHORT1)
        moved_2 = pick_and_move_lines(2, V_SHORT2)
        layer_name = h.dxf.layer if hasattr(h.dxf, 'layer') else "?"
        print(f"  · {layer_name}: 27mm 이동(위치조건 없음) 40~50mm {moved_1}개, 8~10mm {moved_2}개")

    # Hn 수평선 좌우 정규화
    for h in h_sorted:
        set_hline_endpoints(h, x_v1, HX)
    if h_sorted:
        print(f" - Hn 수평선 정규화 완료: 시작X={x_v1:.2f}, 끝X={HX:.2f}")

    # H1/H2/HB/FIH
    h1_line = h_sorted[0] if len(h_sorted) >= 1 else None
    h2_line = h_sorted[1] if len(h_sorted) >= 2 else None
    HB_line = None
    HL = 0
    if h1_line and h2_line:
        (x1_h1, y1_h1), (x2_h1, y2_h1) = line_endpoints(h1_line)
        (x1_h2, y1_h2), (x2_h2, y2_h2) = line_endpoints(h2_line)
        h1_y = (y1_h1 + y2_h1) / 2.0
        h2_y = (y1_h2 + y2_h2) / 2.0
        HL = abs(h1_y - h2_y)
        if HL >= 15.0:
            print(f" - HL이 15mm 이상 ({HL:.2f}mm): 절반으로 조정")
            HL = HL / 2.0
        print(f" - H1 Y값: {h1_y:.2f}, H2 Y값: {h2_y:.2f}, HL: {HL:.2f}")
        HB_line = copy_line(msp, h1_line, dx=0, dy=HL, layer="HB", color=COLOR_WHITE)
        if HB_line:
            new_entities.add(HB_line)
        print(f" - HB 생성: H1을 +Y {HL:.2f} 복사")
    FIH_line = None
    if h2_line and fn_y_extra and HL > 0:
        (x1_h2, y1_h2), (x2_h2, y2_h2) = line_endpoints(h2_line)
        h2_y = (y1_h2 + y2_h2) / 2.0
        num_copies = int((h2_y - fn_y_extra) / HL)
        print(f" - H2를 FN까지 {num_copies}번 복사 (간격: {HL:.2f})")
        for i in range(1, num_copies + 1):
            copied_line = copy_line(msp, h2_line, dx=0, dy=-i*HL, layer=f"H{len(h_sorted)+i}", color=COLOR_WHITE)
            if copied_line:
                new_entities.add(copied_line)
            if i == num_copies:
                FIH_line = copied_line
                print(f" - FIH 생성: 마지막 복사된 라인")

    # T2T 처리(FN까지만)
    if len(rows_by_y) >= 2:
        sorted_y_keys = sorted(rows_by_y.keys(), reverse=True)
        fn_y_limit = fn_y_extra if fn_y_extra else min(rows_by_y.keys())
        rows_to_delete = []
        t2t_created = []
        for i in range(1, len(sorted_y_keys)):
            current_y = sorted_y_keys[i]
            if current_y < fn_y_limit:
                break
            current_row = rows_by_y[current_y]
            upper_row = rows_by_y[sorted_y_keys[i - 1]]
            current_t1 = None
            for a in current_row:
                if a["col"] == 1:
                    current_t1 = a; break
            should_merge = False
            if not current_t1:
                should_merge = True
            else:
                try:
                    float(current_t1["s"])
                except ValueError:
                    should_merge = True
            if should_merge:
                current_t2 = None
                upper_t2 = None
                for a in current_row:
                    if a["col"] == 2:
                        current_t2 = a; break
                for a in upper_row:
                    if a["col"] == 2:
                        upper_t2 = a; break
                if current_t2 and upper_t2:
                    combined_text = upper_t2["s"] + " " + current_t2["s"]
                    t2_x = upper_t2["x1"]; t2_y = upper_t2["y1"]
                    rows_to_delete.append(upper_t2)
                    estimated_width = height * 0.7 * len(combined_text)
                    required_width_factor = min(T2T_TARGET_WIDTH / estimated_width, MAX_WIDTH_FACTOR)
                    t2t_entity = msp.add_text(
                        combined_text,
                        dxfattribs={
                            "height": height,
                            "style": style,
                            "layer": "T2T",
                            "color": OUT_TEXT_COLOR
                        }
                    )
                    t2t_entity.dxf.insert = (t2_x, t2_y)
                    try:
                        if hasattr(t2t_entity.dxf, 'width'):
                            t2t_entity.dxf.width = required_width_factor
                    except Exception:
                        pass
                    if t2t_entity:
                        new_entities.add(t2t_entity)
                    print(f" - T2T 생성: '{combined_text}' @ ({t2_x:.2f}, {t2_y:.2f}), 폭={T2T_TARGET_WIDTH}mm, width_factor={required_width_factor:.3f} (최대 {MAX_WIDTH_FACTOR})")
                    rows_to_delete.extend(current_row)
                    t2t_created.append(combined_text)
        deleted_entities = set()
        for item in rows_to_delete:
            if item["ent"] not in deleted_entities:
                try:
                    item["ent"].destroy()
                    deleted_entities.add(item["ent"])
                except Exception:
                    try:
                        msp.delete_entity(item["ent"])
                        deleted_entities.add(item["ent"])
                    except Exception:
                        pass
        print(f" - T2T 처리 완료: {len(t2t_created)}개 생성 (FN까지만 처리)")
    
    # V2~V5 생성 (고정 간격 적용)
    v2_line = None; v3_line = None; v4_line = None; v5_line = None
    v_top_y = None; v_bot_y = None
    if HB_line:
        (x1_hb, y1_hb), (x2_hb, y2_hb) = line_endpoints(HB_line)
        v_top_y = (y1_hb + y2_hb) / 2.0
    if FIH_line:
        (x1_fih, y1_fih), (x2_fih, y2_fih) = line_endpoints(FIH_line)
        v_bot_y = (y1_fih + y2_fih) / 2.0
    elif hn_line:
        (x1_hn, y1_hn), (x2_hn, y2_hn) = line_endpoints(hn_line)
        v_bot_y = (y1_hn + y2_hn) / 2.0
    if v_top_y and v_bot_y:
        v2_x = x_v1 + T1_T2_SPACING
        v2_line = msp.add_line((v2_x, v_top_y), (v2_x, v_bot_y), dxfattribs={"color": COLOR_WHITE, "layer": "V2"})
        if v2_line: new_entities.add(v2_line)
        print(f" - V2 생성: X={v2_x:.2f}, Y={v_top_y:.2f}~{v_bot_y:.2f} (V1 + {T1_T2_SPACING}mm)")
        
        v3_x = v2_x + T2_T3_SPACING
        v3_line = msp.add_line((v3_x, v_top_y), (v3_x, v_bot_y), dxfattribs={"color": COLOR_WHITE, "layer": "V3"})
        if v3_line: new_entities.add(v3_line)
        print(f" - V3 생성: X={v3_x:.2f} (V2 + {T2_T3_SPACING}mm)")
        
        if v3_line:
            v4_x = v3_x + T3_T4_SPACING
            v4_line = msp.add_line((v4_x, v_top_y), (v4_x, v_bot_y), dxfattribs={"color": COLOR_WHITE, "layer": "V4"})
            if v4_line: new_entities.add(v4_line)
            print(f" - V4 생성: X={v4_x:.2f} (V3 + {T3_T4_SPACING}mm)")
        
        if v4_line:
            v5_x = v4_x + T4_T5_SPACING
            v5_line = msp.add_line((v5_x, v_top_y), (v5_x, v_bot_y), dxfattribs={"color": COLOR_WHITE, "layer": "V5"})
            if v5_line: new_entities.add(v5_line)
            print(f" - V5 생성: X={v5_x:.2f} (V4 + {T4_T5_SPACING}mm)")

    # ═════════════════════════════════════════════════════════════════════════=
    # VV 라인 처리 (HB 라인 MIN X 적용)
    # ═════════════════════════════════════════════════════════════════════════=
    # HB 라인의 MIN X 값 찾기
    hb_min_x = None
    if HB_line:
        (hb_x1, hb_y1), (hb_x2, hb_y2) = line_endpoints(HB_line)
        hb_min_x = min(hb_x1, hb_x2)
        print(f" - HB 라인 MIN X: {hb_min_x:.2f}")
    
    vv_lines = []
    for e in msp.query("LINE"):
        if e.dxf.layer.upper() == "MATLIST" and is_horizontal(e):
            length = line_length(e)
            if 15.0 <= length <= 25.0:
                vv_lines.append(e)
    vv_sorted = sorted(
        vv_lines,
        key=lambda ent: max(line_endpoints(ent)[0][1], line_endpoints(ent)[1][1]),
        reverse=True
    )
    vv1 = vv_sorted[0] if len(vv_sorted) >= 1 else None
    vv2 = vv_sorted[1] if len(vv_sorted) >= 2 else None
    vv3 = vv_sorted[2] if len(vv_sorted) >= 3 else None
    vv4 = vv_sorted[3] if len(vv_sorted) >= 4 else None
    vv5 = vv_sorted[4] if len(vv_sorted) >= 5 else None
    vv6 = vv_sorted[5] if len(vv_sorted) >= 6 else None
    print(f" - VV 라인 발견: {len(vv_sorted)}개 (15~25mm 수평선)")
    
    # VV 라인 레이어 부여
    for vv_line, layer_name in [(vv1,"VV1"),(vv2,"VV2"),(vv3,"VV3"),(vv4,"VV4"),(vv5,"VV5"),(vv6,"VV6")]:
        if vv_line:
            try:
                vv_line.dxf.layer = layer_name
                print(f" - {layer_name} 레이어 부여")
            except Exception:
                pass
    
    if vv1:
        try:
            msp.delete_entity(vv1)
            print(" - VV1 삭제 완료")
        except Exception:
            pass
    if vv3 and HB_line:
        (hb_x1, hb_y1), (hb_x2, hb_y2) = line_endpoints(HB_line)
        hb_end_x = max(hb_x1, hb_x2)
        (vv3_x1, vv3_y1), (vv3_x2, vv3_y2) = line_endpoints(vv3)
        vv3_y = (vv3_y1 + vv3_y2) / 2.0
        set_hline_endpoints(vv3, x_v1, hb_end_x, vv3_y)
        print(f" - VV3 수정: 시작X={x_v1:.2f}, 끝X={hb_end_x:.2f}")
    
    # VV 레이어 라인들 중 100mm 이상인 경우 MIN X 조정
    if hb_min_x is not None:
        for e in msp.query("LINE"):
            layer = e.dxf.layer.upper()
            if layer.startswith("VV") and is_horizontal(e):
                vv_length = line_length(e)
                if vv_length > 100.0:
                    (vv_x1, vv_y1), (vv_x2, vv_y2) = line_endpoints(e)
                    vv_y = (vv_y1 + vv_y2) / 2.0
                    vv_max_x = max(vv_x1, vv_x2)
                    set_hline_endpoints(e, hb_min_x, vv_max_x, vv_y)
                    print(f"   - {layer} 길이 {vv_length:.1f}mm > 100mm: MIN X를 HB와 동일하게 {hb_min_x:.2f}로 조정")
    if h3_line and HB_line and vv3:
        (h3_x1, h3_y1), (h3_x2, h3_y2) = line_endpoints(h3_line)
        h3_y = (h3_y1 + h3_y2) / 2.0
        (hb_x1, hb_y1), (hb_x2, hb_y2) = line_endpoints(HB_line)
        hb_y = (hb_y1 + hb_y2) / 2.0
        copy_dy = h3_y - hb_y
        print(f" - HB Y={hb_y:.2f}, H3 Y={h3_y:.2f}, 복사 거리={copy_dy:.2f}")
        v_lines = []
        if v2_line: v_lines.append(('V2', v2_line))
        if v3_line: v_lines.append(('V3', v3_line))
        if v4_line: v_lines.append(('V4', v4_line))
        if v5_line: v_lines.append(('V5', v5_line))
        (vv3_x1, vv3_y1), (vv3_x2, vv3_y2) = line_endpoints(vv3)
        vv3_y = (vv3_y1 + vv3_y2) / 2.0
        for name, v_line in v_lines:
            copied_v = copy_line(msp, v_line, dx=0, dy=copy_dy, layer=f"{name}_COPY", color=COLOR_WHITE)
            if copied_v:
                new_entities.add(copied_v)
                (cv_x1, cv_y1), (cv_x2, cv_y2) = line_endpoints(copied_v)
                copied_v.dxf.start = (cv_x1, cv_y1, 0.0)
                copied_v.dxf.end = (cv_x2, vv3_y, 0.0)
                print(f" - {name} 복사 및 끝점 수정: Y={vv3_y:.2f}")
    if vv2:
        move_line_x(vv2, 5.0); print(" - VV2를 +X 5mm 이동")
    if vv4:
        move_line_x(vv4, 5.0); print(" - VV4를 +X 5mm 이동")
    if vv5:
        move_line_x(vv5, 5.0); print(" - VV5를 +X 5mm 이동")

    # ═════════════════════════════════════════════════════════════════════════=
    # V5-H1 거리 기반 STRETCH (헤더 포함)
    # ═════════════════════════════════════════════════════════════════════════=
    if v5_line and h1_line and len(TTOL_new) >= 5:
        (v5_x1, v5_y1), (v5_x2, v5_y2) = line_endpoints(v5_line)
        v5_x = v5_x1
        (h1_x1, h1_y1), (h1_x2, h1_y2) = line_endpoints(h1_line)
        h1_end_x = max(h1_x1, h1_x2)
        FX = abs(h1_end_x - v5_x) - 25.0
        print(f" - V5 X={v5_x:.2f}, H1 끝점 X={h1_end_x:.2f}")
        print(f" - |H1 끝점 - V5| = {abs(h1_end_x - v5_x):.2f}mm")
        print(f" - FX = {FX:.2f}mm (이동량)")
        if FX > 0:
            stretch_amount = FX
            t5_x = TTOL_new[4]
            stretch_y_min = min(y_top_v1, y_bot_v1)
            stretch_y_max = max(y_top_v1, y_bot_v1)
            stretch_x_min = x_v1 - 5.0
            stretch_x_max = t5_x + 5.0
            print(f" - FX > 0: STRETCH 수행 (이동량={stretch_amount:.2f}mm)")
            print(f" - STRETCH X 범위: {stretch_x_min:.2f} ~ {stretch_x_max:.2f}")
            print(f" - STRETCH Y 범위: {stretch_y_min:.2f} ~ {stretch_y_max:.2f}")

            stretch_count_text = 0
            header_keywords3 = ["PT", "COMPONENT", "SIZE", "Q'TY", "WEIGHT"]

            for e in msp:
                if e.dxftype() in ("TEXT", "MTEXT"):
                    current_layer = e.dxf.layer.upper()
                    orig_layer = original_layers.get(e, current_layer)
                    text_value_raw = get_text_value(e)
                    text_value = text_value_raw.upper()
                    is_existing_header = False
                    header_type = None
                    for keyword in header_keywords3:
                        if keyword in text_value:
                            is_existing_header = True
                            header_type = keyword
                            break
                    xy = text_ref_xy(e)
                    if not xy:
                        continue
                    x, y = xy
                    if is_existing_header:
                        if (stretch_x_min <= x <= stretch_x_max) and (stretch_y_min <= y <= (stretch_y_max + 30.0)):
                            move_text_entity(e, stretch_amount, 0.0)
                            stretch_count_text += 1
                            print(f"   - 헤더 STRETCH: '{text_value_raw}'")
                        continue
                    is_matlist_origin = (orig_layer == "MATLIST")
                    is_t_layer = (current_layer.startswith("T") and 
                                  (current_layer[1:].isdigit() or 
                                   current_layer == "T2T" or 
                                   current_layer == "PTXT"))
                    is_new = (e in new_entities)
                    is_fab_erec = ("FABRICATION" in text_value or "ERECTION" in text_value)
                    if is_matlist_origin or (is_t_layer and is_matlist_origin) or is_new or is_fab_erec:
                        if (stretch_x_min <= x <= stretch_x_max) and (stretch_y_min <= y <= (stretch_y_max + 30.0)):
                            move_text_entity(e, stretch_amount, 0.0)
                            stretch_count_text += 1

            # LINE STRETCH
            stretch_count_line = 0
            h_line_layers = set()
            v_line_layers = set()
            vv_line_layers = set()
            for e in msp.query("LINE"):
                layer = e.dxf.layer.upper()
                if layer.startswith("H") and (layer[1:].isdigit() or layer in ["HB", "HN"]):
                    h_line_layers.add(layer)
                elif layer.startswith("V") and (layer[1:].isdigit() or layer.endswith("_COPY")):
                    v_line_layers.add(layer)
                elif layer.startswith("VV") and layer[2:].isdigit():
                    vv_line_layers.add(layer)
            for e in msp.query("LINE"):
                layer = e.dxf.layer.upper()
                is_matlist = (layer == "MATLIST")
                is_h_line = layer in h_line_layers
                is_v_line = layer in v_line_layers
                is_vv_line = layer in vv_line_layers
                is_new = (e in new_entities)
                
                # VV 라인은 VV3만 제외하고 나머지는 이동에서 제외
                if is_vv_line and layer != "VV3":
                    continue
                    
                if is_matlist or is_h_line or is_v_line or is_vv_line or is_new:
                    pts = line_endpoints(e)
                    if not pts: 
                        continue
                    (lx1, ly1), (lx2, ly2) = pts
                    if is_h_line or layer == "VV3":  # VV3도 H 라인처럼 처리
                        if is_horizontal(e):
                            left_x = min(lx1, lx2)
                            if (stretch_x_min <= left_x <= stretch_x_max):
                                if lx1 < lx2:
                                    e.dxf.start = (lx1 + stretch_amount, ly1, 0.0)
                                else:
                                    e.dxf.end = (lx2 + stretch_amount, ly2, 0.0)
                                stretch_count_line += 1
                                print(f"   - {layer} 시작점만 이동")
                    else:
                        x_in_range = ((stretch_x_min <= lx1 <= stretch_x_max) or (stretch_x_min <= lx2 <= stretch_x_max))
                        y_in_range = ((stretch_y_min <= ly1 <= stretch_y_max) or (stretch_y_min <= ly2 <= stretch_y_max))
                        if x_in_range and y_in_range:
                            move_line_x(e, stretch_amount)
                            stretch_count_line += 1
            print(f" - STRETCH 완료: TEXT {stretch_count_text}개, LINE {stretch_count_line}개 (VV3 제외한 VV 라인 이동 제외)")
        else:
            print(f" - FX <= 0: STRETCH 수행하지 않음")

    # TYPE1: C→P 이동 (삭제 없음)
    if IS_TYPE1:
        print(" - TYPE1: T1='PT' → C→P 이동")
        deltas = {}
        for i in range(1, 6):
            if i in C_pos and i in header_x_positions:
                deltas[i] = header_x_positions[i] - C_pos[i][0]
        for a in assigned:
            c = a["col"]
            if c in deltas:
                move_text_entity(a["ent"], deltas[c], 0.0)
        print(f"   · 이동된 컬럼: {list(deltas.keys())}")

    # ══════════════════════════════════════════════════════════════════════════
    # 최종 후처리: ERECTION MATERIALS 처리
    # T1이 '1'인 경우에만 T3(SIZE) ≤ 51 조건 체크
    # ══════════════════════════════════════════════════════════════════════════
    def _has_erection_materials():
        """ERECTION MATERIALS 텍스트가 존재하는지 확인"""
        for e in msp:
            if e.dxftype() in ("TEXT", "MTEXT"):
                val = get_text_value(e).upper()
                if "ERECTION MATERIALS" in val:
                    return True
        return False

    def _get_first_row_size_value():
        """첫 행 T3(SIZE) 열에서 숫자값 추출"""
        t3_candidates = [a for a in first_row_assigned if a["col"] == 3]
        if not t3_candidates:
            return None
        t3_pick = sorted(t3_candidates, key=lambda r: r["x1"])[0]
        return extract_size_value(t3_pick["s"])

    # 조건 확인
    erection_exists_final = _has_erection_materials()
    size_numeric = _get_first_row_size_value()
    
    print(f"\n[최종 후처리 체크]")
    print(f" - ERECTION MATERIALS 존재: {erection_exists_final}")
    print(f" - T1 값: '{t1_value}'")
    print(f" - T3(SIZE) 숫자값: {size_numeric}")
    
    # 수정된 조건: T1이 '1'인 경우만 SIZE 체크
    should_replace = False
    if not erection_exists_final:
        if t1_value == "1":
            # T1이 1인 경우: SIZE ≤ 51 체크
            if size_numeric is not None and size_numeric <= 51.0:
                should_replace = True
                print(f" - 조건 충족: ERECTION 없음 & T1='1' & SIZE≤51")
        else:
            # T1이 1이 아닌 경우: 무조건 변경
            should_replace = True
            print(f" - 조건 충족: ERECTION 없음 & T1≠'1' (SIZE 체크 불필요)")
    
    if should_replace:
        print(f"   → FABRICATION MATERIALS를 ERECTION MATERIALS로 변경")
        
        changed = 0
        for e in msp:
            if e.dxftype() in ("TEXT", "MTEXT"):
                txt = get_text_value(e)
                up = txt.upper()
                if "FABRICATION MATERIALS" in up:
                    new_text = up.replace("FABRICATION MATERIALS", "ERECTION MATERIALS")
                    if e.dxftype() == "TEXT":
                        try:
                            e.dxf.text = new_text
                            changed += 1
                            print(f"   · TEXT 변경: '{txt}' → '{new_text}'")
                        except Exception as ex:
                            print(f"   · TEXT 변경 실패: {ex}")
                    elif e.dxftype() == "MTEXT":
                        try:
                            e.text = new_text
                            changed += 1
                            print(f"   · MTEXT 변경: '{txt}' → '{new_text}'")
                        except Exception as ex:
                            print(f"   · MTEXT 변경 실패: {ex}")
        
        if changed == 0:
            # FABRICATION MATERIALS가 없는 경우 새로 생성
            print("   · FABRICATION MATERIALS 텍스트 없음 → ERECTION MATERIALS 신규 생성")
            if len(TTOL_new) >= 1:
                x_em = TTOL_new[0]
                y_em = data_y_max + FAB_DY
                new_text = create_text(msp, "ERECTION MATERIALS", x_em, y_em, height, style, color=OUT_TEXT_COLOR)
                if new_text:
                    new_entities.add(new_text)
                    print(f"   · ERECTION MATERIALS 생성: X={x_em:.2f}, Y={y_em:.2f}")
        else:
            print(f"   · 총 {changed}개 텍스트를 ERECTION MATERIALS로 변경")
    else:
        print(f" - 조건 미충족: 변경 없음")
        if erection_exists_final:
            print("   (이미 ERECTION MATERIALS 존재)")
        elif t1_value == "1" and size_numeric and size_numeric > 51.0:
            print(f"   (T1='1'이지만 SIZE > 51, 현재값: {size_numeric})")

    # 저장
    out = os.path.splitext(path)[0] + "_BOMFORM.DXF"
    doc.saveas(out)
    print(f"\n[완료] 저장: {out}")

def main():
    root = tk.Tk(); root.withdraw()
    paths = filedialog.askopenfilenames(
        title="DXF 파일을 선택하세요(복수 선택 가능)",
        filetypes=[("DXF files", "*.dxf"), ("All files", "*.*")]
    )
    root.update(); root.destroy()
    if not paths:
        print("선택된 파일이 없습니다."); return

    for p in paths:
        try:
            process_file(p)
        except Exception as ex:
            print(f"[ERROR] {p}: {ex}")
            traceback.print_exc()

if __name__ == "__main__":
    main()