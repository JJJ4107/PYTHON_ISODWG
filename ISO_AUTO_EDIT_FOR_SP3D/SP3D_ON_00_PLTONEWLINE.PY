import ezdxf
import os
import math
import re
import sys

# -------------------- 공용 기하 유틸 --------------------
def calculate_polyline_area(points):
    if len(points) < 3:
        return 0
    area = 0
    n = len(points)
    for i in range(n):
        j = (i + 1) % n
        area += points[i][0] * points[j][1]
        area -= points[j][0] * points[i][1]
    return abs(area) / 2

def calculate_hatch_area(hatch):
    try:
        total_area = 0
        for path in hatch.paths:
            if path.path_type_flags & 2:  # Polyline path
                points = [(v[0], v[1]) for v in path.vertices]
                if len(points) >= 3:
                    total_area += calculate_polyline_area(points)
            else:  # Edge path
                points = []
                for edge in path.edges:
                    if edge.EDGE_TYPE == "LineEdge":
                        points.append((edge.start[0], edge.start[1]))
                    elif edge.EDGE_TYPE == "ArcEdge":
                        center = edge.center
                        radius = edge.radius
                        start_angle = math.radians(edge.start_angle)
                        points.append((
                            center[0] + radius * math.cos(start_angle),
                            center[1] + radius * math.sin(start_angle)
                        ))
                    elif edge.EDGE_TYPE == "EllipseEdge":
                        points.append((edge.center[0], edge.center[1]))
                    elif edge.EDGE_TYPE == "SplineEdge":
                        if hasattr(edge, 'control_points'):
                            points.extend([(p[0], p[1]) for p in edge.control_points])
                if path.edges and hasattr(path.edges[-1], 'end'):
                    last_edge = path.edges[-1]
                    if last_edge.EDGE_TYPE == "LineEdge":
                        points.append((last_edge.end[0], last_edge.end[1]))
                if len(points) >= 3:
                    total_area += calculate_polyline_area(points)
        return total_area
    except Exception:
        return 0

def calculate_line_length(line):
    start = line.dxf.start
    end = line.dxf.end
    dx = end.x - start.x
    dy = end.y - start.y
    dz = end.z - start.z
    return math.sqrt(dx*dx + dy*dy + dz*dz)

def get_arc_endpoints(arc):
    center = arc.dxf.center
    radius = arc.dxf.radius
    start_angle = math.radians(arc.dxf.start_angle)
    end_angle = math.radians(arc.dxf.end_angle)
    start_point = (center.x + radius * math.cos(start_angle),
                   center.y + radius * math.sin(start_angle),
                   center.z)
    end_point = (center.x + radius * math.cos(end_angle),
                 center.y + radius * math.sin(end_angle),
                 center.z)
    return start_point, end_point

def point_distance(p1, p2):
    return math.sqrt((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2 + (p1[2]-p2[2])**2)

def point_distance_2d(p1, p2):
    return math.sqrt((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2)

def point_to_line_distance(point, line_start, line_end):
    x0, y0, z0 = point
    x1, y1, z1 = line_start
    x2, y2, z2 = line_end
    dx, dy, dz = x2-x1, y2-y1, z2-z1
    line_length_sq = dx*dx + dy*dy + dz*dz
    if line_length_sq == 0:
        return point_distance(point, line_start), line_start
    t = ((x0-x1)*dx + (y0-y1)*dy + (z0-z1)*dz) / line_length_sq
    t = max(0, min(1, t))
    closest_point = (x1 + t*dx, y1 + t*dy, z1 + t*dz)
    return point_distance(point, closest_point), closest_point

def find_closest_pipe_point(ap1, pipe_lines):
    min_distance = float('inf')
    closest_point = None
    for line in pipe_lines:
        start = (line.dxf.start.x, line.dxf.start.y, line.dxf.start.z)
        end   = (line.dxf.end.x,   line.dxf.end.y,   line.dxf.end.z)
        distance, pt = point_to_line_distance(ap1, start, end)
        if distance < min_distance:
            min_distance = distance
            closest_point = pt
    return closest_point

def endpoints(line):
    s = line.dxf.start
    e = line.dxf.end
    return (s.x, s.y, s.z), (e.x, e.y, e.z)

def line_angle_deg(line):
    (x1, y1, _), (x2, y2, _) = endpoints(line)
    ang = math.degrees(math.atan2(y2 - y1, x2 - x1))
    ang = ang % 180.0  # 방향성 제거
    return ang

def angle_close(a, b, tol=5.0):
    d = abs(a - b)
    d = min(d, 180 - d)
    return d <= tol

def ensure_layer(doc, name):
    try:
        if name not in doc.layers:
            doc.layers.add(name)
    except Exception:
        pass

# -------------------- TEE 탐지/레이어 지정 --------------------
def process_tee_groups(doc, msp, counters):
    """
    - PIPE 레이어, 길이 6~8mm LINE을 후보로 삼아
      끝점 클러스터(반경 0.2mm)에 모인 3개를 T1,T2,T3로 인식.
    - T1,T2: 각도 유사(≤5°)한 2개, T3: 나머지 1개
    - TP(클러스터 평균) → A1(AP1/AP2) → (연장 A2) → AP2 기준 50mm 내 TSIZE
    - TSIZE에서 (\d+)[xX](\d+) 추출 → T1,T2 레이어=TEE{T1SIZE}, T3=TEE{T2SIZE}
    """
    # 1) 후보 수집
    candidates = []
    for e in msp:
        try:
            if e.dxftype() == "LINE" and e.dxf.layer.upper() == "PIPE":
                L = calculate_line_length(e)
                if 6.0 <= L <= 8.0:
                    candidates.append(e)
        except Exception:
            continue

    if not candidates:
        return

    # 2) 끝점 클러스터링 (반경 0.2mm)
    endpoints_list = []  # (point, line, end_idx)
    for ln in candidates:
        s, e = endpoints(ln)
        endpoints_list.append((s, ln, 0))
        endpoints_list.append((e, ln, 1))

    used_line_handles = set()
    visited = [False] * len(endpoints_list)
    CLUSTER_R = 0.2

    def cluster_center(points):
        # 단순 평균
        x = sum(p[0] for p in points) / len(points)
        y = sum(p[1] for p in points) / len(points)
        z = sum(p[2] for p in points) / len(points)
        return (x, y, z)

    # 모든 LINE 목록 (A1/A2 탐색용)
    all_lines = [e for e in msp if hasattr(e, "dxftype") and e.dxftype() == "LINE"]

    # TEXT/MTEXT 목록 (TSIZE 탐색용)
    texts = []
    for e in msp:
        try:
            if e.dxftype() == "TEXT":
                ip = e.dxf.insert
                texts.append(("TEXT", e, (ip.x, ip.y)))
            elif e.dxftype() == "MTEXT":
                ip = e.dxf.insert
                texts.append(("MTEXT", e, (ip.x, ip.y)))
        except Exception:
            continue

    for i in range(len(endpoints_list)):
        if visited[i]:
            continue
        p0, l0, _ = endpoints_list[i]
        # 이 포인트를 중심으로 반경 내 모으기
        cluster_idxs = []
        for j, (pt, ln, _) in enumerate(endpoints_list):
            if visited[j]:
                continue
            if point_distance(p0, pt) <= CLUSTER_R:
                cluster_idxs.append(j)

        # 클러스터에 속한 서로 다른 라인 3개인지 확인
        lines_in_cluster = {}
        cluster_points = []
        for idx in cluster_idxs:
            pt, ln, endi = endpoints_list[idx]
            lines_in_cluster.setdefault(ln, []).append(pt)
            cluster_points.append(pt)

        if len(lines_in_cluster) != 3:
            # 방문 표시만 하고 패스
            for idx in cluster_idxs:
                visited[idx] = True
            continue

        # 이미 처리한 라인인지 체크
        unique_handles = {ln.dxf.handle for ln in lines_in_cluster.keys() if hasattr(ln.dxf, "handle")}
        if any(h in used_line_handles for h in unique_handles):
            for idx in cluster_idxs:
                visited[idx] = True
            continue

        # TP = 클러스터 평균점
        TP = cluster_center(cluster_points)

        # 3) 각도 비교 → 평행한 2개 = T1,T2, 나머지 = T3
        three_lines = list(lines_in_cluster.keys())
        ang = [line_angle_deg(ln) for ln in three_lines]

        # 가장 가까운 각도 쌍 찾기
        pair_idx = None
        min_gap = 999
        for a in range(3):
            for b in range(a+1, 3):
                gap = min(abs(ang[a]-ang[b]), 180-abs(ang[a]-ang[b]))
                if gap < min_gap:
                    min_gap = gap
                    pair_idx = (a, b)

        if pair_idx is None or min_gap > 5.0:
            # 평행한 두 개를 못 찾으면 스킵
            for idx in cluster_idxs:
                visited[idx] = True
            continue

        i1, i2 = pair_idx
        i3 = [0,1,2]
        i3.remove(i1); i3.remove(i2)
        i3 = i3[0]

        T1 = three_lines[i1]
        T2 = three_lines[i2]
        T3 = three_lines[i3]

        # 4) TP에서 0.5mm 내 끝점이 닿는 LINE → A1 선택
        A1 = None
        AP1 = None
        AP2 = None
        best_d = 1e9
        for ln in all_lines:
            if ln is T1 or ln is T2 or ln is T3:
                continue
            try:
                s, e = endpoints(ln)
                ds = point_distance(TP, s)
                de = point_distance(TP, e)
                dmin = min(ds, de)
                if dmin <= 0.5 and dmin < best_d:
                    best_d = dmin
                    A1 = ln
                    if ds <= de:
                        AP1, AP2 = s, e
                    else:
                        AP1, AP2 = e, s
            except Exception:
                continue

        if A1 is None:
            # A1 못 찾으면 이 클러스터 패스
            counters['tee_skipped_no_A1'] += 1
            for idx in cluster_idxs:
                visited[idx] = True
            continue

        # 5) AP2에서 0.1mm 내 끝점이 닿는 다른 LINE → A2 로 보고 AP2를 그 라인의 "먼 끝"으로 재설정
        A2 = None
        best_d2 = 1e9
        for ln in all_lines:
            if ln is A1 or ln is T1 or ln is T2 or ln is T3:
                continue
            try:
                s, e = endpoints(ln)
                ds = point_distance(AP2, s)
                de = point_distance(AP2, e)
                dmin = min(ds, de)
                if dmin <= 0.1 and dmin < best_d2:
                    best_d2 = dmin
                    A2 = ln
                    if ds <= de:
                        near, far = s, e
                    else:
                        near, far = e, s
                    new_AP2 = far
            except Exception:
                continue

        if A2 is not None:
            AP2 = new_AP2  # 연장

        # 6) AP2 기준 50mm 내 TSIZE 텍스트 찾기
        TSIZE = None
        best_td = 1e9
        for kind, t, ins in texts:
            try:
                txt = t.dxf.text if kind == "TEXT" else t.text
                if not isinstance(txt, str):
                    continue
                s_txt = txt.strip()
                if ('x' in s_txt.lower()) or ('DN' in s_txt.upper()):
                    d = point_distance_2d((AP2[0], AP2[1]), ins)
                    if d <= 50.0 and d < best_td:
                        best_td = d
                        TSIZE = s_txt
            except Exception:
                continue

        if TSIZE is None:
            counters['tee_skipped_no_TSIZE'] += 1
            for idx in cluster_idxs:
                visited[idx] = True
            continue

        # 7) TSIZE 파싱: (\d+)\s*[xX]\s*(\d+)
        m = re.search(r'(\d+)\s*[xX]\s*(\d+)', TSIZE)
        if not m:
            counters['tee_skipped_parse_fail'] += 1
            for idx in cluster_idxs:
                visited[idx] = True
            continue

        T1SIZE = m.group(1)
        T2SIZE = m.group(2)

        # 8) 레이어 지정
        layer_T12 = f"TEE{T1SIZE}"
        layer_T3  = f"TEE{T2SIZE}"
        ensure_layer(doc, layer_T12)
        ensure_layer(doc, layer_T3)

        try:
            T1.dxf.layer = layer_T12
            T2.dxf.layer = layer_T12
            T3.dxf.layer = layer_T3
            counters['tee_labeled'] += 1
        except Exception:
            counters['tee_layer_errors'] += 1

        # 처리된 라인으로 표시
        used_line_handles.update(unique_handles)
        for idx in cluster_idxs:
            visited[idx] = True

# -------------------- 기존 파이프/엘보/치수 처리 --------------------
def process_dxf_file(filepath):
    try:
        doc = ezdxf.readfile(filepath)
        msp = doc.modelspace()

        entities_to_delete = []
        pipe_lines = []

        counters = {
            'pipe_line_color': 0,
            'pipe_line_yellow': 0,
            'pipe_arc': 0,
            'dimlines_line': 0,
            'fittings_line': 0,
            'isotext_line': 0,
            'dimlines_polyline': 0,
            'isotext_polyline': 0,
            'elbo_arc_moved': 0,
            'hatch_deleted': 0,
            # TEE 관련
            'tee_labeled': 0,
            'tee_skipped_no_A1': 0,
            'tee_skipped_no_TSIZE': 0,
            'tee_skipped_parse_fail': 0,
            'tee_layer_errors': 0,
        }

        for entity in msp:
            try:
                # HATCH: 면적 <= 0.9 삭제
                if entity.dxftype() == 'HATCH':
                    area = calculate_hatch_area(entity)
                    if area <= 0.9:
                        entities_to_delete.append(entity)
                        counters['hatch_deleted'] += 1
                        continue

                layer = entity.dxf.layer.upper()

                # PIPE 레이어의 LINE 목록 축적
                if entity.dxftype() == 'LINE' and layer == 'PIPE':
                    pipe_lines.append(entity)

                # 1) PIPE LINE 색상
                if entity.dxftype() == 'LINE' and layer == 'PIPE':
                    length = calculate_line_length(entity)
                    if 0.2 <= length <= 1.1:
                        entity.dxf.color = 2  # YELLOW
                        counters['pipe_line_yellow'] += 1
                    elif hasattr(entity.dxf, 'color') and entity.dxf.color == 7:
                        entity.dxf.color = 3  # GREEN
                        counters['pipe_line_color'] += 1

                # 2) PIPE ARC -> 색상 GREEN, 레이어 ELBO
                elif entity.dxftype() == 'ARC' and layer == 'PIPE':
                    entity.dxf.color = 3
                    entity.dxf.layer = 'ELBO'
                    counters['pipe_arc'] += 1

                # 3) DIMLINES LINE -> 흰색
                elif entity.dxftype() == 'LINE' and layer == 'DIMLINES':
                    entity.dxf.color = 7
                    counters['dimlines_line'] += 1

                # 4) FITTINGS LINE -> YELLOW
                elif entity.dxftype() == 'LINE' and layer == 'FITTINGS':
                    entity.dxf.color = 2
                    counters['fittings_line'] += 1

                # 5) ISOTEXT LINE -> 흰색
                elif entity.dxftype() == 'LINE' and layer == 'ISOTEXT':
                    entity.dxf.color = 7
                    counters['isotext_line'] += 1

                # 6) DIMLINES 폴리라인(닫힘, 면적 0.1~0.9) 삭제
                elif entity.dxftype() in ['LWPOLYLINE', 'POLYLINE'] and layer == 'DIMLINES':
                    points = []
                    if entity.dxftype() == 'LWPOLYLINE':
                        points = list(entity.get_points())
                        is_closed = getattr(entity, 'closed', False)
                    else:
                        points = [(v.dxf.location.x, v.dxf.location.y) for v in entity.vertices]
                        is_closed = getattr(entity, 'is_closed', False)

                    if points and is_closed:
                        area = calculate_polyline_area(points)
                        if 0.1 <= area <= 0.9:
                            entities_to_delete.append(entity)
                            counters['dimlines_polyline'] += 1

                # 7) ISOTEXT 폴리라인(닫힘, 면적 0.1~0.9) 삭제
                elif entity.dxftype() in ['LWPOLYLINE', 'POLYLINE'] and layer == 'ISOTEXT':
                    points = []
                    if entity.dxftype() == 'LWPOLYLINE':
                        points = list(entity.get_points())
                        is_closed = getattr(entity, 'closed', False)
                    else:
                        points = [(v.dxf.location.x, v.dxf.location.y) for v in entity.vertices]
                        is_closed = getattr(entity, 'is_closed', False)

                    if points and is_closed:
                        area = calculate_polyline_area(points)
                        if 0.1 <= area <= 0.9:
                            entities_to_delete.append(entity)
                            counters['isotext_polyline'] += 1

            except AttributeError:
                continue
            except Exception:
                continue

        # 삭제 실행
        for entity in entities_to_delete:
            try:
                msp.delete_entity(entity)
            except Exception:
                pass

        # ELBO ARC 이동
        if pipe_lines:
            for entity in msp:
                try:
                    if entity.dxftype() == 'ARC' and entity.dxf.layer.upper() == 'ELBO':
                        start_point, end_point = get_arc_endpoints(entity)
                        ap1 = start_point
                        ap2 = find_closest_pipe_point(ap1, pipe_lines)
                        if ap2:
                            dx = ap2[0] - ap1[0]
                            dy = ap2[1] - ap1[1]
                            dz = ap2[2] - ap1[2]
                            old_center = entity.dxf.center
                            entity.dxf.center = (old_center.x + dx,
                                                 old_center.y + dy,
                                                 old_center.z + dz)
                            counters['elbo_arc_moved'] += 1
                except Exception:
                    continue

        # ---------- ▼ 추가: TEE 탐지/레이어 지정 ----------
        process_tee_groups(doc, msp, counters)
        # ---------- ▲ 추가 끝 ----------

        # 저장
        base_name = os.path.splitext(os.path.basename(filepath))[0]
        dir_name = os.path.dirname(filepath)
        new_filepath = os.path.join(dir_name, f"{base_name}_PL.DXF")
        doc.saveas(new_filepath)

        # 결과 리포트
        result_info = f"\n처리 통계:\n"
        result_info += f"  - PIPE 라인 (0.2~1.1mm) → YELLOW: {counters['pipe_line_yellow']}개\n"
        result_info += f"  - PIPE 흰색 LINE → GREEN: {counters['pipe_line_color']}개\n"
        result_info += f"  - PIPE ARC → GREEN/ELBO: {counters['pipe_arc']}개\n"
        result_info += f"  - DIMLINES LINE → 흰색: {counters['dimlines_line']}개\n"
        result_info += f"  - FITTINGS LINE → YELLOW: {counters['fittings_line']}개\n"
        result_info += f"  - ISOTEXT LINE → 흰색: {counters['isotext_line']}개\n"
        result_info += f"  - DIMLINES 폴리라인 삭제: {counters['dimlines_polyline']}개\n"
        result_info += f"  - ISOTEXT 폴리라인 삭제: {counters['isotext_polyline']}개\n"
        result_info += f"  - HATCH 삭제 (면적 ≤ 0.9): {counters['hatch_deleted']}개\n"
        result_info += f"  - ELBO ARC 이동: {counters['elbo_arc_moved']}개\n"
        result_info += f"  - TEE 레이어 지정 완료: {counters['tee_labeled']}건\n"
        result_info += f"    · A1 미발견 스킵: {counters['tee_skipped_no_A1']}건\n"
        result_info += f"    · TSIZE 미발견 스킵: {counters['tee_skipped_no_TSIZE']}건\n"
        result_info += f"    · TSIZE 파싱 실패: {counters['tee_skipped_parse_fail']}건\n"
        result_info += f"    · 레이어 지정 오류: {counters['tee_layer_errors']}건"

        return True, new_filepath + result_info

    except IOError as e:
        return False, f"파일 읽기/쓰기 오류: {e}"
    except ezdxf.DXFStructureError as e:
        return False, f"DXF 구조 오류: {e}"
    except Exception as e:
        return False, f"처리 중 오류 발생: {e}"

# -------------------- 실행부 --------------------
if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(1)
    
    file_paths = sys.argv[1:]
    
    success_count = 0
    error_files = []
    
    for filepath in file_paths:
        success, result = process_dxf_file(filepath)
        if success:
            success_count += 1
        else:
            error_files.append((filepath, result))