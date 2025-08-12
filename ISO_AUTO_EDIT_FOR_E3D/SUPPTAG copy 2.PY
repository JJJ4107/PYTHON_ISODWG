import ezdxf
import tkinter as tk
from tkinter import filedialog
import math
import os
import traceback
import sys

CYAN = 4
RED = 1
YELLOW = 2

def calc_distance(p1, p2):
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])

def extract_points(ent):
    """LINE, LWPOLYLINE, POLYLINE 에서 2D 점 리스트 추출"""
    try:
        if ent.dxftype() == 'LINE':
            return [(ent.dxf.start.x, ent.dxf.start.y), (ent.dxf.end.x, ent.dxf.end.y)]
        elif ent.dxftype() == 'LWPOLYLINE':
            return [tuple(pt[:2]) for pt in ent.get_points()]
        elif ent.dxftype() == 'POLYLINE':
            return [(v.dxf.location.x, v.dxf.location.y) for v in ent.vertices]
    except Exception:
        pass
    return []

def has_curve(ent):
    """곡선(버지, bulge) 포함 여부 검사"""
    if ent.dxftype() == 'LWPOLYLINE':
        for pt in ent.get_points():
            if len(pt) > 4 and abs(pt[4]) > 1e-3:
                return True
    elif ent.dxftype() == 'POLYLINE':
        for v in ent.vertices:
            if hasattr(v.dxf, 'bulge') and abs(v.dxf.bulge) > 1e-3:
                return True
    return False

def polyline_length(pts):
    return sum(calc_distance(pts[i], pts[i+1]) for i in range(len(pts)-1))

def midpoint(pts):
    return (sum(p[0] for p in pts)/len(pts), sum(p[1] for p in pts)/len(pts))

def is_valid_s1(ent):
    """
    CROSCHK.PY 기준 2점, 길이 3~4mm인 폴리라인/S1 판정 :contentReference[oaicite:0]{index=0}
    """
    if has_curve(ent):
        return False
    pts = extract_points(ent)
    if len(pts) != 2:
        return False
    length = polyline_length(pts)
    return 3.0 <= length <= 4.0

def is_ps_candidate(pts):
    """7점, 인접 점 간 최소 거리 3mm 이상이면 PS 후보"""
    return len(pts) == 7 and any(calc_distance(pts[i], pts[i+1]) >= 3.0 for i in range(6))

def main():
    root = tk.Tk()
    root.withdraw()
    files = filedialog.askopenfilenames(
        title="DXF 파일 선택",
        filetypes=[("DXF Files", "*.dxf")],
    )
    if not files:
        print("선택된 파일 없음")
        return

    for filepath in files:
        print(f"\n🔧 처리중: {filepath}")
        try:
            doc = ezdxf.readfile(filepath)
            msp = doc.modelspace()

            # --- 1) CROSCHK.PY 로직 (S1/S2 탐색, A1/A2/PS 탐색, PS–S1 선 추가) :contentReference[oaicite:1]{index=1}
            croschk_records = []
            s1_candidates = [
                {'entity': e, 'points': extract_points(e)}
                for e in msp if is_valid_s1(e)
            ]
            processed_s1 = set()
            for s1 in s1_candidates:
                if id(s1['entity']) in processed_s1:
                    continue
                for s2 in s1_candidates:
                    if s1 is s2 or id(s2['entity']) in processed_s1:
                        continue
                    # 거리 판별
                    min_d = min(calc_distance(p1, p2) for p1 in s1['points'] for p2 in s2['points'])
                    if not (2.5 <= min_d <= 20.0):
                        continue

                    # 색상 변경
                    s1['entity'].dxf.color = CYAN
                    s2['entity'].dxf.color = CYAN
                    processed_s1.update({id(s1['entity']), id(s2['entity'])})

                    # A1 (3점 이내 1mm) / A2 (0.3mm 기준) / PS (7점 7mm 범위) 탐색
                    def find_a1(center):
                        for ent in msp:
                            pts = extract_points(ent)
                            if len(pts) == 3 and any(calc_distance(p, center) <= 1.0 for p in pts):
                                return {'entity': ent, 'points': pts}
                        return None

                    s1_mid = midpoint(s1['points'])
                    A1 = find_a1(s1_mid) or find_a1(midpoint(s2['points']))
                    if not A1:
                        break
                    p2 = A1['points'][1]
                    A2 = None
                    for ent in msp:
                        if ent == A1['entity']:
                            continue
                        pts = extract_points(ent)
                        if len(pts) in (2,3) and any(calc_distance(p, p2) <= 0.3 for p in pts):
                            A2 = {'entity': ent, 'points': pts}
                            A2['entity'].dxf.color = RED
                            break
                    if not A2:
                        break
                    far_pt = max(A2['points'], key=lambda p: calc_distance(p, s1_mid))
                    PS = None
                    for ent in msp:
                        pts = extract_points(ent)
                        if is_ps_candidate(pts) and any(calc_distance(p, far_pt) <= 7.0 for p in pts):
                            PS = {'entity': ent, 'points': pts}
                            break
                    if not PS:
                        break
                    PS['entity'].dxf.color = CYAN

                    # PS–S1 선 추가 및 기록
                    ps_closest = min(PS['points'], key=lambda p: calc_distance(p, s1_mid))
                    line = msp.add_line(s1_mid, ps_closest, dxfattribs={'color': CYAN})
                    croschk_records.append({
                        's1_entity': s1['entity'],
                        's2_entity': s2['entity'],
                        'ps_point': ps_closest,
                        'line_entity': line
                    })

                    # A1/A2 삭제
                    try:
                        msp.delete_entity(A1['entity'])
                        msp.delete_entity(A2['entity'])
                    except:
                        pass
                    break  # 이 S1 처리 후 다음으로

            # --- 2) SUPPTAG.PY 로직 (SL1 생성, A1/A2/PS 재탐색, 연결선 및 삭제) :contentReference[oaicite:2]{index=2}
            supptag_records = []
            for s1 in s1_candidates:
                for s2 in s1_candidates:
                    if s1 is s2:
                        continue
                    # S1–S2 10mm 이내
                    if min(calc_distance(p1,p2) for p1 in s1['points'] for p2 in s2['points']) > 10.0:
                        continue

                    # SP/EP 정의
                    sp1, ep1 = s1['points']
                    sp2, ep2 = s2['points']
                    # SL1 중심 계산
                    mid1 = ((sp1[0]+sp2[0])/2, (sp1[1]+sp2[1])/2)
                    mid2 = ((ep1[0]+ep2[0])/2, (ep1[1]+ep2[1])/2)
                    sl1_center = ((mid1[0]+mid2[0])/2, (mid1[1]+mid2[1])/2)

                    # SL1 선 2개와 원
                    msp.add_line((sl1_center[0]+(mid1[0]-sl1_center[0])*2.2, sl1_center[1]+(mid1[1]-sl1_center[1])*2.2),
                                 (sl1_center[0]-(mid1[0]-sl1_center[0])*2.2, sl1_center[1]-(mid1[1]-sl1_center[1])*2.2),
                                 dxfattribs={'color': CYAN})
                    msp.add_line((sl1_center[0]+(mid2[0]-sl1_center[0])*2.2, sl1_center[1]+(mid2[1]-sl1_center[1])*2.2),
                                 (sl1_center[0]-(mid2[0]-sl1_center[0])*2.2, sl1_center[1]-(mid2[1]-sl1_center[1])*2.2),
                                 dxfattribs={'color': CYAN})
                    msp.add_circle(center=sl1_center, radius=2.2, dxfattribs={'color': CYAN})

                    # A1 (1mm) / A2 (0.2mm) / PS (7mm, 7점) 재탐색
                    def find_a1_sup(center):
                        for ent in msp:
                            pts = extract_points(ent)
                            if len(pts) == 3 and any(calc_distance(p, center) <= 1.0 for p in pts):
                                return {'entity': ent, 'points': pts}
                        return None

                    A1 = find_a1_sup(sl1_center)
                    if not A1:
                        break
                    p2 = A1['points'][1]
                    A2 = None
                    for ent in msp:
                        if ent == A1['entity']:
                            continue
                        pts = extract_points(ent)
                        if len(pts) in (2,3) and any(calc_distance(p, p2) <= 0.2 for p in pts):
                            A2 = {'entity': ent, 'points': pts}
                            break
                    if not A2:
                        break
                    far_pt = max(A2['points'], key=lambda p: calc_distance(p, sl1_center))
                    PS = None
                    for ent in msp:
                        pts = extract_points(ent)
                        if is_ps_candidate(pts) and any(calc_distance(p, far_pt) <= 7.0 for p in pts):
                            PS = {'entity': ent, 'points': pts}
                            break
                    if not PS:
                        break
                    # PS 색상 및 연결
                    PS['entity'].dxf.color = CYAN
                    close_pspt = min(PS['points'], key=lambda p: calc_distance(p, sl1_center))
                    # SUPP 연결선
                    msp.add_line(sl1_center, close_pspt, dxfattribs={'color': CYAN})

                    supptag_records.append({
                        's1_entity': s1['entity'],
                        's2_entity': s2['entity'],
                        'sl1_center': sl1_center,
                        'ps_point': close_pspt
                    })

                    # A1/A2 삭제
                    try:
                        msp.delete_entity(A1['entity'])
                        msp.delete_entity(A2['entity'])
                    except:
                        pass
                    break

            # --- 3) Stretch: CROSCHK에서 그린 PS–S1 선을 SL1 중심으로 수정 & S1/S2 삭제
            for rec in croschk_records:
                # 매칭되는 SL1 center 찾기
                match = next((s for s in supptag_records
                              if id(s['s1_entity']) == id(rec['s1_entity']) and
                                 rec['ps_point'] == s['ps_point']), None)
                if not match:
                    continue
                line = rec['line_entity']
                # start: PS, end: SL1 center
                line.dxf.start = match['ps_point']
                line.dxf.end   = (*match['sl1_center'], 0)

                # S1, S2 삭제
                try:
                    msp.delete_entity(rec['s1_entity'])
                    msp.delete_entity(rec['s2_entity'])
                except:
                    pass

            # 저장
            save_path = os.path.splitext(filepath)[0] + '_SUPP.dxf'
            doc.saveas(save_path)
            print(f"✅ 저장됨: {save_path}")

        except Exception:
            print(f"❌ 오류 발생 - {filepath}")
            traceback.print_exc(file=sys.stdout)

    print("🎉 전체 작업 완료")

if __name__ == "__main__":
    main()
