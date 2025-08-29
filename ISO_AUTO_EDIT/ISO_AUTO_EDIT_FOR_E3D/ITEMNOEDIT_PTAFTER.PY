import ezdxf
import os
import math
from ezdxf.math import Vec2
from tkinter import Tk, filedialog

def select_files():
    Tk().withdraw()
    return filedialog.askopenfilenames(
        title="DXF 파일 선택 (여러 개 가능)",
        filetypes=[("DXF files", "*.dxf")])

def distance(p1, p2):
    return math.hypot(p2.x - p1.x, p2.y - p1.y)

def set_entity_color(entity, color=1):
    try:
        if entity and hasattr(entity, "dxf") and hasattr(entity.dxf, "color"):
            entity.dxf.color = color
    except:
        pass

def get_text_position(text):
    try:
        ins = getattr(text.dxf, "insert", None)
        if ins:
            return Vec2(ins.x, ins.y)
        loc = getattr(text.dxf, "location", None)
        if loc:
            return Vec2(loc[0], loc[1])
    except:
        pass
    return Vec2(0, 0)

def get_line_midpoint(line):
    try:
        start = line.dxf.start
        end = line.dxf.end
        return Vec2((start.x + end.x) / 2, (start.y + end.y) / 2)
    except:
        return Vec2(0, 0)

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
            entity.dxf.rotation = (orig_angle + angle_deg) % 360
        elif t == "LINE":
            a = Vec2(entity.dxf.start.x, entity.dxf.start.y)
            b = Vec2(entity.dxf.end.x, entity.dxf.end.y)
            ra = rotate_point(a, center, angle_deg)
            rb = rotate_point(b, center, angle_deg)
            entity.dxf.start = (ra.x, ra.y, 0)
            entity.dxf.end = (rb.x, rb.y, 0)
        elif t in ("LWPOLYLINE", "POLYLINE"):
            if t == "LWPOLYLINE":
                points = [Vec2(pt[0], pt[1]) for pt in entity.get_points()]
                new_points = [rotate_point(pt, center, angle_deg) for pt in points]
                entity.clear()
                for pt in new_points:
                    entity.append_points([(pt.x, pt.y)])
            else:  # POLYLINE
                for v in entity.vertices:
                    pt = Vec2(v.dxf.location.x, v.dxf.location.y)
                    rpt = rotate_point(pt, center, angle_deg)
                    v.dxf.location = (rpt.x, rpt.y, 0)
    except Exception as e:
        print(f"▶ 회전 오류: {entity} / {e}")

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
        elif t in ("LWPOLYLINE", "POLYLINE"):
            if t == "LWPOLYLINE":
                points = [Vec2(pt[0], pt[1]) for pt in entity.get_points()]
                new_points = [move_point(pt, offset) for pt in points]
                entity.clear()
                for pt in new_points:
                    entity.append_points([(pt.x, pt.y)])
            else:
                for v in entity.vertices:
                    pt = Vec2(v.dxf.location.x, v.dxf.location.y)
                    npt = move_point(pt, offset)
                    v.dxf.location = (npt.x, npt.y, 0)
    except Exception as e:
        print(f"▶ 이동 오류: {entity} / {e}")

def calc_angle_deg(pt1, pt2):
    dx = pt2.x - pt1.x
    dy = pt2.y - pt1.y
    return math.degrees(math.atan2(dy, dx))

def get_perpendicular_offset(angle_deg, length):
    angle_rad = math.radians(angle_deg + 90)
    return Vec2(math.cos(angle_rad) * length, math.sin(angle_rad) * length)

def set_mirrtext_zero(doc):
    try:
        doc.header['$MIRRTEXT'] = 0
        print("   [MIRRTEXT=0] 설정 완료")
    except Exception as e:
        print(f"▶ MIRRTEXT=0 설정 오류: {e}")

def process_dxf(file_path):
    try:
        doc = ezdxf.readfile(file_path)
    except Exception as e:
        print(f"파일 열기 실패: {file_path} / {e}")
        return

    msp = doc.modelspace()
    modified = False

    for st1 in msp.query('TEXT'):
        if '<' not in st1.dxf.text or '>' not in st1.dxf.text:
            continue
        st1_pos = get_text_position(st1)

        candidate_st2 = []
        for e in msp.query('TEXT LINE'):
            if e is st1:
                continue
            pos = get_text_position(e) if e.dxftype() == 'TEXT' else get_line_midpoint(e)
            dx = pos.x - st1_pos.x
            dy = abs(pos.y - st1_pos.y)
            if 0 < dx <= 15 and dy <= 5:
                candidate_st2.append(e)

        text_st2s = [e for e in candidate_st2 if e.dxftype() == 'TEXT' and abs(get_text_position(e).y - st1_pos.y) <= 0.5]
        line_st2s = []
        for e in candidate_st2:
            if e.dxftype() == 'LINE':
                start = e.dxf.start
                end = e.dxf.end
                length = distance(Vec2(start.x, start.y), Vec2(end.x, end.y))
                if 2.8 <= length <= 4.2:
                   line_st2s.append(e)

        # ITNO 조건: 셋 다 있을 때만!
        if text_st2s and line_st2s:
            st1.dxf.layer = "ITNO"
            text_st2s[0].dxf.layer = "ITNO"
            for l in line_st2s:
                l.dxf.layer = "ITNO"
            set_entity_color(st1, 1)
            set_entity_color(text_st2s[0], 1)
            for l in line_st2s:
                set_entity_color(l, 1)
            modified = True
            print(f"[ITNO 처리] ITEM: {st1.dxf.text}, 우측: {text_st2s[0].dxf.text}, 선: {len(line_st2s)}개")

            # ---- 1. A1 라인 찾기 ----
            found_A1 = None
            AP1, AP2 = None, None
            for l in line_st2s:
                pts = [Vec2(l.dxf.start.x, l.dxf.start.y), Vec2(l.dxf.end.x, l.dxf.end.y)]
                for pt in pts:
                    for testline in msp.query('LINE'):
                        if testline in line_st2s:
                            continue
                        ta = Vec2(testline.dxf.start.x, testline.dxf.start.y)
                        tb = Vec2(testline.dxf.end.x, testline.dxf.end.y)
                        if distance(pt, ta) <= 0.5 or distance(pt, tb) <= 0.5:
                            testline.dxf.layer = "A1"
                            set_entity_color(testline, 1)
                            found_A1 = testline
                            AP1 = ta if distance(pt, ta) <= 0.5 else tb
                            AP2 = tb if distance(pt, ta) <= 0.5 else ta
                            break
                    if found_A1:
                        break
                if found_A1:
                    break
            if not found_A1:
                min_dist = float("inf")
                nearest_line = None
                nearest_ap = None
                opposite_ap = None
                for e in msp.query('LINE'):
                    if e in line_st2s:
                        continue
                    a = Vec2(e.dxf.start.x, e.dxf.start.y)
                    b = Vec2(e.dxf.end.x, e.dxf.end.y)
                    d_to_a = distance(st1_pos, a)
                    d_to_b = distance(st1_pos, b)
                    if d_to_a < min_dist:
                        min_dist = d_to_a
                        nearest_line = e
                        nearest_ap = a
                        opposite_ap = b
                    if d_to_b < min_dist:
                        min_dist = d_to_b
                        nearest_line = e
                        nearest_ap = b
                        opposite_ap = a
                if nearest_line is not None:
                    nearest_line.dxf.layer = "A1"
                    set_entity_color(nearest_line, 1)
                    found_A1 = nearest_line
                    AP1 = nearest_ap
                    AP2 = opposite_ap
                    print(f"   [A1] <...>에서 가장 가까운 LINE {nearest_line.dxf.handle}")
                else:
                    continue  # A1이 없으면 아래를 실행하지 않음

            # === [여기] ITNO-DN 포함 텍스트 탐색 및 설정 ===
            st1_pos = get_text_position(st1)
            itno_dn_text = None
            for e in msp.query('TEXT'):
                if e is st1 or e is text_st2s[0]:
                    continue
                pos = get_text_position(e)
                dx = abs(pos.x - st1_pos.x)
                dy = st1_pos.y - pos.y  # -y 방향(아래)
                if dx <= 2.0 and 0 < dy <= 4.0 and "DN" in e.dxf.text.upper():
                    itno_dn_text = e
                    break
            if itno_dn_text:
                itno_dn_text.dxf.layer = "ITNODN"
                set_entity_color(itno_dn_text, 1)
                print(f"   [ITNODN 추가] DN 포함 TEXT: '{itno_dn_text.dxf.text}' 포함")

            # ---- 2. AP2에서 가장 가까운 PIPE 객체 찾기 ----
            pipe_candidates = []
            for e in msp.query('LWPOLYLINE POLYLINE'):
                if e.dxf.layer.upper() == "PIPE":
                    try:
                        pts = [Vec2(p[0], p[1]) for p in e.get_points()]
                    except:
                        pts = [Vec2(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]
                    for pt in pts:
                        pipe_candidates.append((distance(AP2, pt), e, pt))
            for e in msp.query('LINE'):
                if e.dxf.layer.upper() == "PIPE":
                    a = Vec2(e.dxf.start.x, e.dxf.start.y)
                    b = Vec2(e.dxf.end.x, e.dxf.end.y)
                    pipe_candidates.append((distance(AP2, a), e, a))
                    pipe_candidates.append((distance(AP2, b), e, b))
            if pipe_candidates:
                pipe_candidates.sort(key=lambda x: x[0])
                min_dist, nearest_pipe, nearest_pipe_pt = pipe_candidates[0]
                set_entity_color(nearest_pipe, 1)
                print(f"   [PIPE] AP2와 가장 가까운 PIPE 객체 {nearest_pipe.dxf.handle}, 거리={min_dist:.3f}mm")

                # --- PIPE 방향각 계산 ---
                angle = 0
                if nearest_pipe.dxftype() == "LINE":
                    pa = Vec2(nearest_pipe.dxf.start.x, nearest_pipe.dxf.start.y)
                    pb = Vec2(nearest_pipe.dxf.end.x, nearest_pipe.dxf.end.y)
                    angle = calc_angle_deg(pa, pb)
                    axis1, axis2 = pa, pb
                else:
                    pts = []
                    try:
                        pts = [Vec2(p[0], p[1]) for p in nearest_pipe.get_points()]
                    except:
                        pts = [Vec2(v.dxf.location.x, v.dxf.location.y) for v in nearest_pipe.vertices]
                    idx = min(range(len(pts)), key=lambda i: distance(pts[i], nearest_pipe_pt))
                    if 0 < idx < len(pts)-1:
                        angle = (calc_angle_deg(pts[idx-1], pts[idx]) + calc_angle_deg(pts[idx], pts[idx+1])) / 2
                        axis1, axis2 = pts[idx-1], pts[idx+1]
                    elif idx == 0 and len(pts) > 1:
                        angle = calc_angle_deg(pts[0], pts[1])
                        axis1, axis2 = pts[0], pts[1]
                    elif idx == len(pts)-1 and len(pts) > 1:
                        angle = calc_angle_deg(pts[-2], pts[-1])
                        axis1, axis2 = pts[-2], pts[-1]
                    else:
                        axis1, axis2 = pts[0], pts[-1]

                # === [중요] ITNO 그룹 완성(ITNODN 포함)
                itno_entities = [st1, text_st2s[0]] + line_st2s
                if itno_dn_text:
                    itno_entities.append(itno_dn_text)

                # --- ITNO 회전 및 이동 ---
                for ent in itno_entities:
                    rotate_entity_around(ent, AP1, angle)
                offset = Vec2(AP2.x - AP1.x, AP2.y - AP1.y)
                for ent in itno_entities:
                    move_entity(ent, offset)
                print(f"   [회전+이동] ITNO 전체를 PIPE 방향({angle:.2f}°)으로 AP1→AP2로 이동 완료")

                # --- 직교 1mm 이동 ---
                perp_offset = get_perpendicular_offset(angle, 1)
                for ent in itno_entities:
                    move_entity(ent, perp_offset)
                print(f"   [직교 1mm 이동] PIPE(각:{angle:.2f}°) 직교 방향으로 1mm 평행이동 완료")

                # --- DN 직교 -Y 2 mm 이동 ---
                if itno_dn_text:
                    perp_offset = get_perpendicular_offset(angle, -2)
                    move_entity(itno_dn_text, perp_offset)
                    print("   [ITNODN] DN 포함 TEXT를 PIPE 직교 방향(2mm)으로 이동 완료")

                # --- PIPE 축(P1→P2) 기준 ±6mm 추가 이동 ---
                x_sum = 0; y_sum = 0; n = 0
                for ent in itno_entities:
                    if ent.dxftype() == "TEXT":
                        pos = get_text_position(ent)
                        x_sum += pos.x; y_sum += pos.y; n += 1
                    elif ent.dxftype() == "LINE":
                        a = Vec2(ent.dxf.start.x, ent.dxf.start.y)
                        b = Vec2(ent.dxf.end.x, ent.dxf.end.y)
                        x_sum += (a.x + b.x); y_sum += (a.y + b.y); n += 2
                    elif ent.dxftype() == "LWPOLYLINE":
                        for pt in ent.get_points():
                            x_sum += pt[0]; y_sum += pt[1]; n += 1
                    elif ent.dxftype() == "POLYLINE":
                        for v in ent.vertices:
                            x_sum += v.dxf.location.x; y_sum += v.dxf.location.y; n += 1
                centroid = Vec2(x_sum/n, y_sum/n) if n else Vec2(0,0)
                pipe_vec = axis2 - axis1
                pipe_vec_len = pipe_vec.magnitude
                if pipe_vec_len > 0:
                    pipe_dir = pipe_vec / pipe_vec_len
                    ap2_to_centroid = centroid - AP2
                    proj = ap2_to_centroid.dot(pipe_dir)
                    offset_len = -6 if proj >= 0 else 6
                    offset_vec = pipe_dir * offset_len
                    for ent in itno_entities:
                        move_entity(ent, offset_vec)
                    print(f"   [PIPE 벡터] ITNO 중심이 AP2 기준 {'우측(앞,+6mm)' if proj >= 0 else '좌측(뒤,-6mm)'}로 {offset_len:+}mm PIPE 방향으로 이동")

                # --- 180도 회전 조건 ---
                if angle < -145:
                    set_mirrtext_zero(doc)
                    print("   [180도 회전] ITNO 그룹을 AP2 기준으로 180도 회전 수행")
                    for ent in itno_entities:
                        rotate_entity_around(ent, AP2, 180)

                # --- 꺼꾸로 된 text ITNO 그룹 선정 후 ---
                # --- ITNO 그룹 선정 후 ---
                itno_entities = [st1, text_st2s[0]] + line_st2s
                if itno_dn_text:
                    itno_entities.append(itno_dn_text)

                # (1) <를 포함하는 text(ST1)의 x값 > ST2의 x값인 경우 검사
                itno_entities = [st1, text_st2s[0]] + line_st2s
                if itno_dn_text:
                    itno_entities.append(itno_dn_text)

                st1_x = get_text_position(st1).x
                st2_x = get_text_position(text_st2s[0]).x

                # (1) ITNODN 포함 여부 판단
                include_dn = bool(itno_dn_text)

                # (2) 중심점(점들의 평균) 구하기
                x_sum = 0; y_sum = 0; n = 0
                for ent in itno_entities if include_dn else [st1, text_st2s[0]] + line_st2s:
                    if ent.dxftype() == "TEXT":
                        pos = get_text_position(ent)
                        x_sum += pos.x; y_sum += pos.y; n += 1
                    elif ent.dxftype() == "LINE":
                        a = Vec2(ent.dxf.start.x, ent.dxf.start.y)
                        b = Vec2(ent.dxf.end.x, ent.dxf.end.y)
                        x_sum += (a.x + b.x); y_sum += (a.y + b.y); n += 2
                    elif ent.dxftype() == "LWPOLYLINE":
                        for pt in ent.get_points():
                            x_sum += pt[0]; y_sum += pt[1]; n += 1
                    elif ent.dxftype() == "POLYLINE":
                        for v in ent.vertices:
                            x_sum += v.dxf.location.x; y_sum += v.dxf.location.y; n += 1
                center = Vec2(x_sum/n, y_sum/n) if n else Vec2(0,0)

                # (3) 만약 ITNODN 포함이면, PIPE 직교방향(90도)으로 2mm 평행이동
                if include_dn:
                    # PIPE angle, axis1, axis2는 ITNO 처리에서 이미 계산되어 있어야 함
                    if 'angle' in locals():
                        perp_offset = get_perpendicular_offset(angle, -2)
                        center = center + perp_offset

                # (4) < 포함 text(ST1)의 x > ST2의 x이면, 위 중심을 기준으로 180도 회전
                if st1_x > st2_x:
                    for ent in itno_entities:
                        rotate_entity_around(ent, center, 180)
                    print(f"   [ITNO{'(+ITNODN)' if include_dn else ''} 반전] 회전 중심: ({center.x:.2f},{center.y:.2f}) 기준 180도 회전")

                    print("---- 중심좌표 계산 대상 ----")
                    for ent in itno_entities:
                        if ent.dxftype() == "TEXT":
                            print(f"TEXT: {ent.dxf.text} / {get_text_position(ent)}")
                        elif ent.dxftype() == "LINE":
                            print(f"LINE: {ent.dxf.layer} / {ent.dxf.start}, {ent.dxf.end}")

                # --- AP2 선 및 AP2 3mm 내, 길이2.3mm 이하(PIPE제외) 선 삭제 ---
                to_remove = []
                if found_A1:
                    to_remove.append(found_A1)
                for e in msp:
                    if not hasattr(e, 'dxf') or not hasattr(e.dxf, 'layer'):
                        continue
                    layer_name = str(e.dxf.layer).upper()
                    # 여기를 수정!
                    if layer_name != "ARROW":
                        continue
                    if e.dxftype() not in ("LINE", "LWPOLYLINE", "POLYLINE"):
                        continue
                    pts = []
                    if e.dxftype() == "LINE":
                        pts = [Vec2(e.dxf.start.x, e.dxf.start.y), Vec2(e.dxf.end.x, e.dxf.end.y)]
                    elif e.dxftype() == "LWPOLYLINE":
                        pts = [Vec2(pt[0], pt[1]) for pt in e.get_points()]
                    elif e.dxftype() == "POLYLINE":
                        pts = [Vec2(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]
                    near_ap2 = any(distance(AP2, pt) <= 2.2 for pt in pts)  # 2.2mm로 변경
                    total_len = 0
                    if len(pts) >= 2:
                        for i in range(len(pts)-1):
                            total_len += distance(pts[i], pts[i+1])
                    if near_ap2 and total_len <= 2.3:
                        to_remove.append(e)
                for e in set(to_remove):
                    try:
                        msp.delete_entity(e)
                    except Exception as ex:
                        print(f"   [삭제오류] {e} / {ex}")

                print(f"   [삭제] AP2 2.2mm내, 길이2.3mm 이하(ARROW만) 선 {len(to_remove)}개 삭제 완료")
   # if modified:
   #     save_path = os.path.splitext(file_path)[0] + "_ITNO.dxf"
   #     doc.saveas(save_path)
   #     print(f"[✔] 저장 완료: {os.path.basename(save_path)}")
   # else:
   #     print(f"[ ] 조건 일치 없음: {os.path.basename(file_path)}")
    save_path = os.path.splitext(file_path)[0] + "_ITNO.dxf"
    try:
        doc.saveas(save_path)
        print(f"[✔] 저장 완료: {os.path.basename(save_path)}")
    except Exception as e:
        print(f"[!] 저장 오류: {e}")
        
if __name__ == "__main__":
    files = select_files()
    for f in files:
        process_dxf(f)
    print("▶ 모든 파일 처리 완료.")
