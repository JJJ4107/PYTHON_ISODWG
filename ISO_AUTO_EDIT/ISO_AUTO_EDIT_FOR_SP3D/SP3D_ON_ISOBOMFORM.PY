# -*- coding: utf-8 -*-
"""
BOM FORM 자동화 (확장 버전)
- 기존 기능 + 추가 요구사항 반영
- H1/H2 Y값 차이(HL) 계산, FN 바로 아래 라인을 H3로 지정
- HB, FN, FIH 처리
- T2T: T1이 없거나 숫자가 아닌 행의 T2를 위 행 T2와 합치기 (FN까지만, 76.5mm 폭)
- V2~V5 생성: V2(V1+11mm), V3(V2+T2~T3거리), V4(V3+T3~T4거리), V5(V4+T4~T5거리)
- VV 라인 처리: MATLIST 15~25mm 수평선 처리
- 'CUT' 이후 텍스트는 공차 없이 개별 열로 처리
- T1~T5 거리에 비례하여 이동거리 조정 (기준: 170mm → 30mm)
- ERECTION MATERIALS 출력: FN의 T3, T3에 'ERECTION' 포함, 또는 FX 기준
"""
import os
import sys
import math
import traceback
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
    return exploded

# ─── 메인 처리 ───────────────────────────────────────────────────────────────
def process_file(path):
    doc = ezdxf.readfile(path)
    msp = doc.modelspace()

    # 0) BLOCK → explode (BLOCK 내부 TEXT/MTEXT 처리 가능)
    explode_block_inserts(msp)

    # 1) BOMTEXT 적용(스캔 범위)
    apply_arial_and_spacing(
        doc, msp,
        x_min=X_MIN, x_max=X_MAX,
        y_bottom=Y_BOTTOM, y_top=Y_TOP,
        width_factor=DEFAULT_WIDTH_FACTOR,
        style_name=DEFAULT_STYLE_NAME,
        font_file=DEFAULT_FONT_FILE
    )

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
        out = os.path.splitext(path)[0] + "_BOMFORM.DXF"
        doc.saveas(out); return

    # 3) 첫 행 판단 및 TTOL
    y_max = max(it["y"] for it in items)
    first_row = [it for it in items if abs(it["y"] - y_max) <= ROW_TOL]
    
    # 첫 행을 X 좌표로 정렬
    first_row_sorted = sorted(first_row, key=lambda t: t["x"])
    
    # 'CUT' 포함 텍스트 찾기
    cut_index = -1
    cut_x = None
    for i, item in enumerate(first_row_sorted):
        if "CUT" in item["s"].upper():
            cut_index = i
            cut_x = item["x"]
            break
    
    # TTOL 생성
    TTOL_raw = []
    
    if cut_index >= 0:
        # CUT 이전: 기존 방식 (공차로 그룹화)
        before_cut = [it["x"] for it in first_row_sorted[:cut_index+1]]
        before_cut_grouped = []
        if before_cut:
            before_cut_grouped = dedup_sorted_positions(before_cut, tol=COL_DEDUP_TOL)
            TTOL_raw.extend(before_cut_grouped)
        
        # CUT 이후: 공차 없이 각각을 개별 열로
        after_cut = [it["x"] for it in first_row_sorted[cut_index+1:]]
        after_cut_unique = []
        if after_cut:
            # 중복 제거만 하고 그룹화하지 않음
            for x in after_cut:
                if not after_cut_unique or abs(x - after_cut_unique[-1]) > CUT_AFTER_TOL:  # 0.1mm 이상 차이나면 별개 열
                    after_cut_unique.append(x)
            TTOL_raw.extend(after_cut_unique)
    else:
        # CUT가 없으면 기존 방식
        TTOL_raw = dedup_sorted_positions([it["x"] for it in first_row_sorted], tol=COL_DEDUP_TOL)

    if not TTOL_raw:
        sorted_all = sorted(items, key=lambda t: (-t["y"], t["x"]))
        TTOL_raw = dedup_sorted_positions([t["x"] for t in sorted_all[:5]], tol=COL_DEDUP_TOL)

    if not TTOL_raw:
        out = os.path.splitext(path)[0] + "_BOMFORM.DXF"
        doc.saveas(out); return

    # 4) 열 이동량(TN 고정) 계산
    X_TN = max(TTOL_raw)
    
    # T1 값 미리 확인 (첫 행의 T1)
    t1_value_preview = None
    first_row_preview = [it for it in items if abs(it["y"] - y_max) <= ROW_TOL]
    for it in first_row_preview:
        if len(TTOL_raw) > 0 and abs(it["x"] - TTOL_raw[0]) <= COL_DEDUP_TOL:
            t1_value_preview = get_text_value(it["e"])
            break
    
    # T1과 T5의 거리를 기준으로 SHIFT_MAX 조정 (T1이 '1'인 경우)
    SHIFT_BASE = 30.0  # 기본 이동거리 (170mm 기준)
    DIST_BASE = 170.0  # 기준 거리 (T1~T5)
    
    # T1 값 확인
    should_adjust = (t1_value_preview == "1")
    
    # T1과 T5 거리 계산 (T5가 있고 T1이 '1'인 경우)
    if should_adjust and len(TTOL_raw) >= 5:
        t1_x = TTOL_raw[0]
        t5_x = TTOL_raw[4]
        actual_dist = abs(t5_x - t1_x)
        # 비례하여 이동거리 조정
        SHIFT_MAX_ADJUSTED = SHIFT_BASE * (actual_dist / DIST_BASE)
    else:
        SHIFT_MAX_ADJUSTED = SHIFT_MAX  # 기본값 사용
    
    dists = [abs(x - X_TN) for x in TTOL_raw]
    d_max = max(dists) if dists else 0.0
    shifts = [(0.0 if d_max <= 1e-9 else SHIFT_MAX_ADJUSTED * (d / d_max)) for d in dists]
    TTOL_new = [x + dx for x, dx in zip(TTOL_raw, shifts)]

    # 5) 텍스트 배정/이동/레이어 + 'PT' 포함시 PTXT
    assigned = []
    
    # 각 텍스트의 실제 위치에 대한 이동량 계산
    # TTOL과 shifts를 이용해 보간 함수 생성
    def get_shift_for_x(x_pos):
        """주어진 X 위치에 대한 이동량을 계산 (선형 보간)"""
        if not TTOL_raw:
            return 0.0
        
        # X 위치가 TTOL 범위 밖인 경우
        if x_pos <= TTOL_raw[0]:
            return shifts[0]
        if x_pos >= TTOL_raw[-1]:
            return shifts[-1]
        
        # 선형 보간으로 이동량 계산
        for i in range(len(TTOL_raw) - 1):
            if TTOL_raw[i] <= x_pos <= TTOL_raw[i+1]:
                # 두 TTOL 사이의 비율 계산
                ratio = (x_pos - TTOL_raw[i]) / (TTOL_raw[i+1] - TTOL_raw[i])
                # 이동량 보간
                return shifts[i] + ratio * (shifts[i+1] - shifts[i])
        
        return 0.0
    
    for it in items:
        # 텍스트의 실제 위치에 대한 이동량 계산
        shift_amount = get_shift_for_x(it["x"])
        
        # 텍스트 이동
        move_text_entity(it["e"], shift_amount, 0.0)
        
        # 가장 가까운 열 찾기 (레이어 배정용)
        i_col = nearest_index(it["x"], TTOL_raw)
        if i_col is not None:
            # 레이어 배정
            try: 
                it["e"].dxf.layer = f"T{i_col+1}"
            except Exception: 
                pass
            
            # 'PT' 포함시 PTXT 레이어
            try:
                if "PT" in it["s"].upper():
                    it["e"].dxf.layer = "PTXT"
            except Exception:
                pass
        
        # 이동 후 위치
        xy_new = text_ref_xy(it["e"]) or (it["x"] + shift_amount, it["y"])
        
        assigned.append({
            "col": i_col + 1 if i_col is not None else 0,
            "x0": it["x"], 
            "y0": it["y"],
            "x1": xy_new[0], 
            "y1": xy_new[1],
            "s": it["s"], 
            "ent": it["e"],
            "shift": shift_amount
        })

    # ── 첫 행/TYPE1/머리글 좌표 계산 ────────────────────────────────────────
    first_row_assigned = [a for a in assigned if abs(a["y0"] - y_max) <= ROW_TOL]
    # T1 값
    t1_value = None
    t1_ent = None
    first_row_t1 = [a for a in first_row_assigned if a["col"] == 1]
    if first_row_t1:
        pick = sorted(first_row_t1, key=lambda r: r["x1"])[0]
        t1_value = pick["s"]; t1_ent = pick["ent"]

    # 스타일/높이
    style, height = get_text_style_and_height(t1_ent or assigned[0]["ent"], DEFAULT_STYLE_NAME, 2.5)

    IS_TYPE1 = (t1_value == "PT")
    need_headers = (t1_value == "1") or IS_TYPE1

    P_pos, C_pos = {}, {}
    if need_headers:
        y_hdr = y_max + HDR_DY
        headers = ["PT", "COMPONENT", "SIZE", "Q'TY", "WEIGHT"]
        for i, label in enumerate(headers, start=1):
            if i <= len(TTOL_new):
                x_hdr = TTOL_new[i-1]
                create_text(msp, label, x_hdr, y_hdr, height, style, color=OUT_TEXT_COLOR)
                P_pos[i] = (x_hdr, y_hdr)
        # FABRICATION MATERIALS
        if 1 <= len(TTOL_new):
            x_fab, y_fab = TTOL_new[0], y_max + FAB_DY
            create_text(msp, "FABRICATION MATERIALS", x_fab, y_fab, height, style, color=OUT_TEXT_COLOR)

    # C1..C5 : 첫 행 각 컬럼 좌표
    for i in range(1, min(5, len(TTOL_new)) + 1):
        cand = [a for a in first_row_assigned if a["col"] == i]
        if cand:
            a = sorted(cand, key=lambda r: r["x1"])[0]
            C_pos[i] = (a["x1"], a["y1"])

    # ── VA/HX 찾기 ──────────────────────────────────────────────────────────
    # VA → VY
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

    # HA → HX
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

    # ── V1/HN 그리기 ───────────────────────────────────────────────────────
    # V1 끝점 Y = "가장 아래쪽 T1 의 Y - 3"
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

    # ── ERECTION MATERIALS 처리 (모든 텍스트 처리 완료 후) ─────────────────
    # T3에 'ERECTION' 포함 확인 및 FABRICATION 포함된 T3 찾기
    erection_in_t3 = False
    fabrication_t3_y = None
    
    for a in assigned:
        if a["col"] == 3:
            if "ERECTION" in a["s"].upper():
                erection_in_t3 = True
            if "FABRICATION" in a["s"].upper():
                fabrication_t3_y = a["y1"]
    
    # ERECTION MATERIALS 출력 (T3에 ERECTION이 포함된 경우만)
    if erection_in_t3 and fabrication_t3_y and len(TTOL_new) >= 1:
        # FABRICATION이 포함된 T3의 Y값 - 5.5
        erection_y = fabrication_t3_y + EREC_DY  # FABRICATION T3의 Y - 5.5
        x_em = TTOL_new[0]  # T1의 X
        create_text(msp, "ERECTION MATERIALS", x_em, erection_y, height, style, color=OUT_TEXT_COLOR)

    # ══════════════════════════════════════════════════════════════════════════
    # 추가 기능 구현을 위한 준비
    # ══════════════════════════════════════════════════════════════════════════
    
    # FN 찾기 (H3 지정 및 추가 기능을 위해)
    fn_row = None
    fn_y_extra = None
    
    # 모든 행별로 정리 (ROW_TOL 사용하여 그룹화)
    rows_by_y = {}
    assigned_sorted_by_y = sorted(assigned, key=lambda a: a["y1"], reverse=True)
    
    for a in assigned_sorted_by_y:
        # 기존 행 중에서 ROW_TOL 내에 있는 행 찾기
        placed = False
        for y_key in sorted(rows_by_y.keys(), reverse=True):
            if abs(a["y1"] - y_key) <= ROW_TOL:
                rows_by_y[y_key].append(a)
                placed = True
                break
        
        # 적합한 행이 없으면 새 행 생성
        if not placed:
            rows_by_y[a["y1"]] = [a]
    
    # Y값 순으로 정렬하여 행 검사
    for y_key in sorted(rows_by_y.keys(), reverse=True):
        row = rows_by_y[y_key]
        # T1~T5 중 'TOTAL' 포함 확인
        for a in row:
            if a["col"] <= 5 and "TOTAL" in a["s"].upper():
                fn_row = row
                fn_y_extra = y_key
                break
        if fn_row:
            break
    
    # ── 대상 레이어 라인 처리 (MATLIST, MATLINE) ───────────────────────────
    # (1) 대상 레이어 LINE 색상=흰색
    for e in msp.query("LINE"):
        if is_target_layer(e):
            try: e.dxf.color = COLOR_WHITE
            except Exception: pass

    # (2) 수평 & 길이≥150mm → Y 큰 순으로 정렬, 레이어 H1,H2,...
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
    
    # FN 바로 아래 라인을 H3로 지정
    h3_line = None
    h3_index = -1
    
    if fn_y_extra and h_sorted:
        # FN Y값보다 작은 첫 번째 라인을 H3로 지정
        for idx, h in enumerate(h_sorted):
            (x1, y1), (x2, y2) = line_endpoints(h)
            h_y = (y1 + y2) / 2.0
            if h_y < fn_y_extra:
                h3_line = h
                h3_index = idx
                break
    
    # H1, H2, H3... 레이어 할당
    for idx, h in enumerate(h_sorted):
        if h == h3_line:
            # FN 아래 라인은 H3로 고정
            h.dxf.layer = "H3"
        elif idx < h3_index or h3_index == -1:
            # H3 이전 라인들은 순서대로 H1, H2...
            h.dxf.layer = f"H{idx+1}"
        else:
            # H3 이후 라인들은 H4, H5...
            h.dxf.layer = f"H{idx+2}"

    # (3) 27mm 이동: **위치조건 없음** + **수평/수직 모두 허용**, 길이 기준만
    moved_once = set()  # 엔티티 핸들로 중복 이동 방지
    def can_move(v):
        try: return v.dxf.handle not in moved_once
        except Exception: return True

    def pick_and_move_lines(max_count, rng):
        """대상 레이어 라인(수평/수직 포함) 중 길이가 rng 안인 것에서
           아직 이동 안 한 것 선택해 +X 27mm, 최대 max_count개."""
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

    # 이미 위에서 레이어가 할당되었으므로 27mm 이동만 처리
    for h in h_sorted:
        moved_1 = pick_and_move_lines(2, V_SHORT1)  # 40~50mm
        moved_2 = pick_and_move_lines(2, V_SHORT2)  # 8~10mm

    # (4) 모든 Hn 수평선의 시작X=V1.X, 끝X=HX 로 정규화
    for h in h_sorted:
        set_hline_endpoints(h, x_v1, HX)

    # ══════════════════════════════════════════════════════════════════════════
    # 추가 기능 구현
    # ══════════════════════════════════════════════════════════════════════════
    
    # H1, H2, H3 찾기 및 HL 계산
    h1_line = h_sorted[0] if len(h_sorted) >= 1 else None
    h2_line = h_sorted[1] if len(h_sorted) >= 2 else None
    # h3_line은 이미 위에서 FN 바로 아래로 지정됨
    
    HB_line = None
    HL = 0
    
    if h1_line and h2_line:
        (x1_h1, y1_h1), (x2_h1, y2_h1) = line_endpoints(h1_line)
        (x1_h2, y1_h2), (x2_h2, y2_h2) = line_endpoints(h2_line)
        h1_y = (y1_h1 + y2_h1) / 2.0
        h2_y = (y1_h2 + y2_h2) / 2.0
        HL = abs(h1_y - h2_y)
        
        # HB 생성 (H1을 +Y HL 방향으로 복사)
        HB_line = copy_line(msp, h1_line, dx=0, dy=HL, layer="HB", color=COLOR_WHITE)
    
    # FIH 계산 (H2를 -Y 방향으로 HL만큼 FN까지 복사)
    FIH_line = None
    if h2_line and fn_y_extra and HL > 0:
        (x1_h2, y1_h2), (x2_h2, y2_h2) = line_endpoints(h2_line)
        h2_y = (y1_h2 + y2_h2) / 2.0
        
        # 복사 횟수 계산
        num_copies = int((h2_y - fn_y_extra) / HL)
        
        # 복사 수행
        for i in range(1, num_copies + 1):
            copied_line = copy_line(msp, h2_line, dx=0, dy=-i*HL, layer=f"H{len(h_sorted)+i}", color=COLOR_WHITE)
            if i == num_copies:
                FIH_line = copied_line
    
    # T2T 처리 (T1이 없거나 숫자가 아닌 행의 T2를 위 행의 T2와 합치기, FN까지만)
    # rows_by_y는 이미 위에서 생성됨
    if len(rows_by_y) >= 2:
        # Y값 기준으로 정렬된 키 리스트 (위에서 아래로)
        sorted_y_keys = sorted(rows_by_y.keys(), reverse=True)
        
        # FN 찾기 (이미 위에서 찾았지만 확인)
        fn_y_limit = fn_y_extra if fn_y_extra else min(rows_by_y.keys())
        
        # 처리할 T2T 목록
        rows_to_delete = []
        t2t_created = []
        
        # 각 행을 순차적으로 검사 (FN까지만)
        for i in range(1, len(sorted_y_keys)):  # 두 번째 행부터 시작
            current_y = sorted_y_keys[i]
            
            # FN 이하는 처리하지 않음
            if current_y < fn_y_limit:
                break
                
            current_row = rows_by_y[current_y]
            upper_row = rows_by_y[sorted_y_keys[i - 1]]
            
            # 현재 행의 T1 확인
            current_t1 = None
            for a in current_row:
                if a["col"] == 1:
                    current_t1 = a
                    break
            
            # T1이 없거나 숫자가 아닌 경우만 처리
            should_merge = False
            if not current_t1:
                should_merge = True  # T1이 없음
            else:
                # T1이 숫자인지 확인
                try:
                    float(current_t1["s"])
                except ValueError:
                    should_merge = True  # T1이 숫자가 아님
            
            if should_merge:
                # 현재 행과 위 행의 T2 찾기
                current_t2 = None
                upper_t2 = None
                
                for a in current_row:
                    if a["col"] == 2:
                        current_t2 = a
                        break
                
                for a in upper_row:
                    if a["col"] == 2:
                        upper_t2 = a
                        break
                
                # 두 T2가 모두 있으면 합치기
                if current_t2 and upper_t2:
                    # T2T 생성 (위 행 T2 + 현재 행 T2)
                    combined_text = upper_t2["s"] + " " + current_t2["s"]
                    
                    # 위 행의 위치에 출력
                    t2_x = upper_t2["x1"]
                    t2_y = upper_t2["y1"]
                    
                    # 기존 upper_t2 삭제
                    rows_to_delete.append(upper_t2)
                    
                    # width_factor 계산 (78mm 목표)
                    # 참조 코드와 동일한 방식: 높이 * 0.7 * 문자수
                    estimated_width = height * 0.7 * len(combined_text)
                    required_width_factor = 78.0 / estimated_width
                    
                    # 텍스트 생성
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
                    
                    # width 속성 직접 설정 (참조 코드와 동일)
                    try:
                        if hasattr(t2t_entity.dxf, 'width'):
                            t2t_entity.dxf.width = required_width_factor
                    except Exception:
                        pass
                    
                    # 현재 행의 모든 텍스트 삭제 대상에 추가
                    rows_to_delete.extend(current_row)
                    t2t_created.append(combined_text)
        
        # 원본 텍스트 삭제
        deleted_entities = set()  # 중복 삭제 방지
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
    
    # V2~V5 생성 (TTOL 거리 기반)
    v2_line = None
    v3_line = None
    v4_line = None
    v5_line = None
    
    if HB_line and FIH_line:
        # HB와 FIH의 Y값 가져오기
        (x1_hb, y1_hb), (x2_hb, y2_hb) = line_endpoints(HB_line)
        (x1_fih, y1_fih), (x2_fih, y2_fih) = line_endpoints(FIH_line)
        hb_y = (y1_hb + y2_hb) / 2.0
        fih_y = (y1_fih + y2_fih) / 2.0
        
        # V2 생성 (V1을 +X 11mm 복사, 시작점 Y=HB, 끝점 Y=FIH)
        v2_x = x_v1 + 11.0
        v2_line = msp.add_line((v2_x, hb_y), (v2_x, fih_y), dxfattribs={"color": COLOR_WHITE, "layer": "V2"})
        
        # V3 생성 (V2에서 T2~T3 거리만큼 복사)
        if len(TTOL_new) >= 3:
            t2_t3_dist = TTOL_new[2] - TTOL_new[1]  # T3 - T2
            v3_x = v2_x + t2_t3_dist
            v3_line = msp.add_line((v3_x, hb_y), (v3_x, fih_y), dxfattribs={"color": COLOR_WHITE, "layer": "V3"})
        
        # V4 생성 (V3에서 T3~T4 거리만큼 복사)
        if v3_line and len(TTOL_new) >= 4:
            t3_t4_dist = TTOL_new[3] - TTOL_new[2]  # T4 - T3
            v4_x = v3_x + t3_t4_dist
            v4_line = msp.add_line((v4_x, hb_y), (v4_x, fih_y), dxfattribs={"color": COLOR_WHITE, "layer": "V4"})
        
        # V5 생성 (V4에서 T4~T5 거리만큼 복사)
        if v4_line and len(TTOL_new) >= 5:
            t4_t5_dist = TTOL_new[4] - TTOL_new[3]  # T5 - T4
            v5_x = v4_x + t4_t5_dist
            v5_line = msp.add_line((v5_x, hb_y), (v5_x, fih_y), dxfattribs={"color": COLOR_WHITE, "layer": "V5"})

    # ══════════════════════════════════════════════════════════════════════════
    # VV 라인 처리 (MATLIST 레이어의 15~25mm 수평선)
    # ══════════════════════════════════════════════════════════════════════════
    
    # MATLIST 레이어의 15~25mm 수평선 찾기
    vv_lines = []
    for e in msp.query("LINE"):
        if e.dxf.layer.upper() == "MATLIST" and is_horizontal(e):
            length = line_length(e)
            if 15.0 <= length <= 25.0:
                vv_lines.append(e)
    
    # Y값 기준으로 정렬 (위에서 아래로)
    vv_sorted = sorted(
        vv_lines,
        key=lambda ent: max(line_endpoints(ent)[0][1], line_endpoints(ent)[1][1]),
        reverse=True
    )
    
    # VV1, VV2, VV3... 할당
    vv1 = vv_sorted[0] if len(vv_sorted) >= 1 else None
    vv2 = vv_sorted[1] if len(vv_sorted) >= 2 else None
    vv3 = vv_sorted[2] if len(vv_sorted) >= 3 else None
    vv4 = vv_sorted[3] if len(vv_sorted) >= 4 else None
    vv5 = vv_sorted[4] if len(vv_sorted) >= 5 else None
    vv6 = vv_sorted[5] if len(vv_sorted) >= 6 else None
    
    # VV1~VV6 레이어 부여
    vv_lines_list = [
        (vv1, "VV1"),
        (vv2, "VV2"),
        (vv3, "VV3"),
        (vv4, "VV4"),
        (vv5, "VV5"),
        (vv6, "VV6")
    ]
    
    for vv_line, layer_name in vv_lines_list:
        if vv_line:
            try:
                vv_line.dxf.layer = layer_name
            except Exception:
                pass
    
    # VV1 삭제 (레이어 부여 후)
    if vv1:
        try:
            msp.delete_entity(vv1)
        except Exception:
            pass
    
    # VV3 수정 (시작점=V1.X, 끝점=HB 끝점)
    if vv3 and HB_line:
        (hb_x1, hb_y1), (hb_x2, hb_y2) = line_endpoints(HB_line)
        hb_end_x = max(hb_x1, hb_x2)  # HB의 끝점 X
        hb_y = (hb_y1 + hb_y2) / 2.0  # HB의 Y
        
        # VV3의 Y값 가져오기
        (vv3_x1, vv3_y1), (vv3_x2, vv3_y2) = line_endpoints(vv3)
        vv3_y = (vv3_y1 + vv3_y2) / 2.0
        
        # VV3 수정
        set_hline_endpoints(vv3, x_v1, hb_end_x, vv3_y)
    
    # H3는 이미 위에서 FN 바로 아래 라인으로 지정됨
    
    if h3_line and HB_line and vv3:
        # HB에서 H3까지의 Y 거리 계산
        (h3_x1, h3_y1), (h3_x2, h3_y2) = line_endpoints(h3_line)
        h3_y = (h3_y1 + h3_y2) / 2.0
        
        (hb_x1, hb_y1), (hb_x2, hb_y2) = line_endpoints(HB_line)
        hb_y = (hb_y1 + hb_y2) / 2.0
        
        copy_dy = h3_y - hb_y  # 복사할 Y 거리
        
        # V2~V5 복사
        v_lines = []
        if v2_line: v_lines.append(('V2', v2_line))
        if v3_line: v_lines.append(('V3', v3_line))
        if v4_line: v_lines.append(('V4', v4_line))
        if v5_line: v_lines.append(('V5', v5_line))
        
        # VV3의 Y값
        (vv3_x1, vv3_y1), (vv3_x2, vv3_y2) = line_endpoints(vv3)
        vv3_y = (vv3_y1 + vv3_y2) / 2.0
        
        for name, v_line in v_lines:
            # 복사
            copied_v = copy_line(msp, v_line, dx=0, dy=copy_dy, layer=f"{name}_COPY", color=COLOR_WHITE)
            
            if copied_v:
                # 끝점 Y를 VV3의 Y로 수정
                (cv_x1, cv_y1), (cv_x2, cv_y2) = line_endpoints(copied_v)
                # 시작점은 그대로, 끝점 Y만 VV3로
                copied_v.dxf.start = (cv_x1, cv_y1, 0.0)  # 시작점 유지
                copied_v.dxf.end = (cv_x2, vv3_y, 0.0)    # 끝점 Y를 VV3로
    
    # VV2, VV4, VV5를 +X 5mm 이동
    if vv2:
        move_line_x(vv2, 5.0)
    
    if vv4:
        move_line_x(vv4, 5.0)
    
    if vv5:
        move_line_x(vv5, 5.0)

    # ══════════════════════════════════════════════════════════════════════════
    # V5와 H1 간의 거리 계산 및 STRETCH 처리
    # ══════════════════════════════════════════════════════════════════════════
    
    if v5_line and h1_line and len(TTOL_new) >= 5:
        # V5의 X 좌표
        (v5_x1, v5_y1), (v5_x2, v5_y2) = line_endpoints(v5_line)
        v5_x = v5_x1  # V5는 수직선이므로 x1 = x2
        
        # H1의 끝점 X 좌표 (오른쪽 끝)
        (h1_x1, h1_y1), (h1_x2, h1_y2) = line_endpoints(h1_line)
        h1_end_x = max(h1_x1, h1_x2)
        
        # FX 계산 (절대값 - 25mm)
        FX = abs(h1_end_x - v5_x) - 25.0
        
        if FX > 0:  # FX가 양수일 때만 STRETCH
            stretch_amount = FX
            t5_x = TTOL_new[4]  # T5의 X 좌표 (이동 후)
            
            # V1의 Y 범위 (STRETCH 영역의 Y 범위)
            stretch_y_min = min(y_top_v1, y_bot_v1)
            stretch_y_max = max(y_top_v1, y_bot_v1)
            
            # STRETCH X 범위 (V1 X - 5 ~ T5 X + 5)
            stretch_x_min = x_v1 - 5.0
            stretch_x_max = t5_x + 5.0
            
            # TEXT STRETCH (머리글 포함을 위해 Y 범위 확장)
            stretch_count_text = 0
            for e in msp:
                if e.dxftype() in ("TEXT", "MTEXT"):
                    xy = text_ref_xy(e)
                    if xy:
                        x, y = xy
                        # Y 범위를 머리글까지 포함하도록 확장 (위로 30mm)
                        extended_y_max = stretch_y_max + 30.0
                        
                        # X 범위 내이고, Y가 확장된 범위 내에 있으면 이동
                        if (stretch_x_min <= x <= stretch_x_max) and (stretch_y_min <= y <= extended_y_max):
                            # 텍스트 내용 확인 (FABRICATION, ERECTION, PT, COMPONENT 등)
                            text_value = get_text_value(e).upper()
                            if any(keyword in text_value for keyword in ["FABRICATION", "ERECTION", "PT", "COMPONENT", "SIZE", "Q'TY", "WEIGHT"]):
                                move_text_entity(e, stretch_amount, 0.0)
                                stretch_count_text += 1
                            elif (stretch_y_min <= y <= stretch_y_max):  # 일반 텍스트는 원래 Y 범위 내에서만
                                move_text_entity(e, stretch_amount, 0.0)
                                stretch_count_text += 1
            
            # LINE STRETCH (H 라인 끝점 제외)
            stretch_count_line = 0
            h_line_layers = set()  # H 레이어 수집
            for e in msp.query("LINE"):
                layer = e.dxf.layer.upper()
                if layer.startswith("H") and (layer[1:].isdigit() or layer in ["HB", "HN"]):
                    h_line_layers.add(layer)
            
            for e in msp.query("LINE"):
                pts = line_endpoints(e)
                if pts:
                    (lx1, ly1), (lx2, ly2) = pts
                    layer = e.dxf.layer.upper()
                    
                    # H 계열 라인인지 확인
                    is_h_line = layer in h_line_layers
                    
                    if is_h_line:
                        # H 계열 라인은 시작점만 이동 (수평선이라고 가정)
                        if is_horizontal(e):
                            # 시작점(왼쪽 끝)이 STRETCH 범위에 있으면
                            left_x = min(lx1, lx2)
                            if (stretch_x_min <= left_x <= stretch_x_max):
                                # 시작점만 이동하도록 재설정
                                if lx1 < lx2:
                                    e.dxf.start = (lx1 + stretch_amount, ly1, 0.0)
                                else:
                                    e.dxf.end = (lx2 + stretch_amount, ly2, 0.0)
                                stretch_count_line += 1
                    else:
                        # 일반 라인은 전체 이동
                        x_in_range = ((stretch_x_min <= lx1 <= stretch_x_max) or (stretch_x_min <= lx2 <= stretch_x_max))
                        y_in_range = ((stretch_y_min <= ly1 <= stretch_y_max) or (stretch_y_min <= ly2 <= stretch_y_max))
                        
                        if x_in_range and y_in_range:
                            move_line_x(e, stretch_amount)
                            stretch_count_line += 1

    # ── TYPE1 추가 처리: C1..C5 → P1..P5 수평 이동 + 첫 행 삭제 ────────────
    if IS_TYPE1:
        # 이동량 계산
        deltas = {}
        for i in range(1, 6):
            if i in C_pos and i in P_pos:
                deltas[i] = P_pos[i][0] - C_pos[i][0]
        # 첫 행 헤더 엔티티 수집
        header_entities = []
        for a in first_row_assigned:
            if 1 <= a["col"] <= 5:
                header_entities.append(a["ent"])
        # 데이터 이동(첫 행 제외)
        for a in assigned:
            c = a["col"]
            if c in deltas:
                if abs(a["y0"] - y_max) <= ROW_TOL and (1 <= c <= 5):
                    continue  # 헤더는 나중에 삭제
                move_text_entity(a["ent"], deltas[c], 0.0)
        # 헤더 삭제
        for ent in set(header_entities):
            try:
                ent.destroy()
            except Exception:
                try: msp.delete_entity(ent)
                except Exception: pass

    # 9) 저장
    out = os.path.splitext(path)[0] + "_BOMFORM.DXF"
    doc.saveas(out)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(1)
    
    # 첫 번째 인자는 스크립트 이름이므로 제외
    input_files = sys.argv[1:]
    
    for input_file in input_files:
        if not input_file.lower().endswith('.dxf'):
            continue
            
        try:
            process_file(input_file)
        except Exception as ex:
            pass