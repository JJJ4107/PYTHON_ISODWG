import ezdxf
from pathlib import Path
import tkinter as tk
from tkinter import filedialog
from typing import List, Tuple, Optional
import math
from dataclasses import dataclass

@dataclass
class LineInfo:
    entity_type: str
    layer: str
    points: List[Tuple[float, float]]
    width: Optional[float]
    source: str

class DxfModifier:
    def __init__(self, input_file: str):
        self.input_file = Path(input_file)

    def _direct_parse_dxf(self) -> List[LineInfo]:
        lines: List[LineInfo] = []
        try:
            with open(self.input_file, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.readlines()
            i = 0
            while i < len(content):
                line = content[i].strip()
                
                # LWPOLYLINE 처리 추가
                if line == "LWPOLYLINE":
                    layer = "0"
                    const_width = None
                    points = []
                    i += 1
                    
                    # LWPOLYLINE 헤더 정보 파싱
                    while i < len(content):
                        code = content[i].strip()
                        if code == "10":  # 첫 번째 X 좌표를 만나면 좌표 수집 시작
                            break
                        if code == "8":  # Layer
                            i += 1
                            if i < len(content):
                                layer = content[i].strip()
                        elif code == "43":  # Constant width
                            i += 1
                            if i < len(content):
                                const_width = float(content[i].strip())
                        i += 1
                    
                    # 좌표 수집
                    while i < len(content):
                        code = content[i].strip()
                        if code == "10":  # X coordinate
                            x = None
                            y = None
                            i += 1
                            if i < len(content):
                                x = float(content[i].strip())
                            i += 1
                            # 다음은 20 (Y coordinate)이어야 함
                            if i < len(content) and content[i].strip() == "20":
                                i += 1
                                if i < len(content):
                                    y = float(content[i].strip())
                                if x is not None and y is not None:
                                    points.append((x, y))
                        elif code == "0":  # 다음 엔티티 시작
                            break
                        else:
                            i += 1
                    
                    # width가 0.6인 경우만 저장
                    if const_width and const_width == 0.6 and len(points) >= 2:
                        lines.append(LineInfo(
                            entity_type="LWPOLYLINE",
                            layer=layer,
                            points=points,
                            width=const_width,
                            source="direct_parsing"
                        ))
                    i += 1
                    
                elif line == "POLYLINE":
                    layer = "0"
                    start_width: Optional[float] = None
                    end_width: Optional[float] = None
                    i += 1
                    # 헤더 파싱
                    while i < len(content):
                        code = content[i].strip()
                        if code == "VERTEX":
                            break
                        if code == "8":
                            i += 1
                            if i < len(content):
                                layer = content[i].strip()
                        elif code == "40":
                            i += 1
                            if i < len(content):
                                try:
                                    start_width = float(content[i].strip())
                                except ValueError:
                                    start_width = None
                        elif code == "41":
                            i += 1
                            if i < len(content):
                                try:
                                    end_width = float(content[i].strip())
                                except ValueError:
                                    end_width = None
                        i += 1
                    # 꼭지점 파싱
                    points: List[Tuple[float,float]] = []
                    while i < len(content):
                        token = content[i].strip()
                        if token == "VERTEX":
                            x = None; y = None
                            i += 1
                            while i < len(content) and content[i].strip() not in ["VERTEX", "SEQEND"]:
                                code = content[i].strip()
                                if code == "10":
                                    i += 1
                                    if i < len(content):
                                        try:
                                            x = float(content[i].strip())
                                        except ValueError:
                                            x = None
                                elif code == "20":
                                    i += 1
                                    if i < len(content):
                                        try:
                                            y = float(content[i].strip())
                                        except ValueError:
                                            y = None
                                i += 1
                            if x is not None and y is not None:
                                points.append((x,y))
                        elif token == "SEQEND":
                            break
                        else:
                            i += 1
                    width = start_width if start_width and start_width > 0 else end_width
                    # width가 0.6인 경우만 저장
                    if width and width == 0.6 and len(points) >= 2:
                        lines.append(LineInfo(
                            entity_type="POLYLINE",
                            layer=layer,
                            points=points,
                            width=width,
                            source="direct_parsing"
                        ))
                    i += 1
                else:
                    i += 1
        except Exception as e:
            print(f"직접 파싱 중 오류: {e}")
        return lines

    def find_and_modify_green_lines(self, doc):
        direct_lines = self._direct_parse_dxf()
        c_lines_key = set()
        msp = doc.modelspace()
        modified_count = 0
        
        # width가 0.6인 라인들만 필터링
        width_06_lines = [line for line in direct_lines if line.width and line.width == 0.6]
        
        for entity in msp:
            entity_type = entity.dxftype()
            # POLYLINE과 LWPOLYLINE 모두 처리
            if entity_type in ["POLYLINE", "LWPOLYLINE"]:
                if entity_type == "POLYLINE":
                    pts = [(v.dxf.location.x, v.dxf.location.y) for v in entity.vertices]
                elif entity_type == "LWPOLYLINE":
                    pts = [(pt[0], pt[1]) for pt in entity.get_points('xy')]
                else:
                    continue
                    
                key = tuple((round(x,6), round(y,6)) for x,y in pts)
                
                for dl in width_06_lines:
                    # 동일한 엔티티 타입인지도 확인
                    if (dl.entity_type == entity_type and
                        len(dl.points) == len(pts) and 
                        self._points_match(pts, dl.points)):
                        try:
                            entity.dxf.color = 3  # Green
                            entity.dxf.lineweight = 50
                            c_lines_key.add(key)
                            modified_count += 1
                            break
                        except Exception as e:
                            print(f"엔티티 수정 실패 ({entity_type}): {e}")
        
        print(f"width = 0.6인 라인으로 수정된 개수: {modified_count}개")
        return c_lines_key, direct_lines

    def _points_match(self, p1: List[Tuple[float,float]], p2: List[Tuple[float,float]], tol=1e-3) -> bool:
        if len(p1) != len(p2): return False
        for a,b in zip(p1,p2):
            if abs(a[0]-b[0])>tol or abs(a[1]-b[1])>tol:
                return False
        return True

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
    """두 점과 bulge 값으로부터 호의 중심점을 계산"""
    if abs(bulge) < 1e-7:
        return None
    
    # 현의 중점
    mid_x = (p1[0] + p2[0]) / 2
    mid_y = (p1[1] + p2[1]) / 2
    
    # 현의 길이와 방향
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    chord_length = math.sqrt(dx*dx + dy*dy)
    
    if chord_length < 1e-7:
        return None
    
    # bulge로부터 중심까지의 거리 계산
    # bulge = tan(theta/4), 여기서 theta는 호의 중심각
    theta = 4 * math.atan(abs(bulge))
    radius = chord_length / (2 * math.sin(theta/2))
    
    # sagitta (호의 높이) 계산
    sagitta = radius * (1 - math.cos(theta/2))
    if bulge < 0:
        sagitta = -sagitta
    
    # 현에 수직인 방향 벡터 (왼쪽으로 90도 회전)
    perp_x = -dy / chord_length
    perp_y = dx / chord_length
    
    # 호의 높이를 고려한 오프셋
    h = radius - sagitta
    
    # 중심점 계산
    center_x = mid_x + h * perp_x
    center_y = mid_y + h * perp_y
    
    return (center_x, center_y)

def get_polyline_arc_center_and_radius_with_bulge(ent):
    """bulge가 있는 폴리라인의 중심점과 반지름 계산"""
    pts = polypoints(ent)
    
    if ent.dxftype() == 'LWPOLYLINE':
        points = list(ent.get_points('xyb'))
        print(f"  LWPOLYLINE bulge 정보:")
        for idx, (x, y, bulge) in enumerate(points):
            print(f"    점{idx+1}: ({x:.3f}, {y:.3f}), bulge={bulge:.6f}")
        
        # 모든 세그먼트 확인 (닫힌 폴리라인 포함)
        for idx in range(len(points)):
            x1, y1, bulge = points[idx]
            # 다음 점 (마지막 점의 경우 첫 번째 점으로)
            next_idx = (idx + 1) % len(points)
            x2, y2, _ = points[next_idx]
            
            if abs(bulge) > 1e-7:
                print(f"  bulge 발견: 점{idx+1}→점{next_idx+1}, bulge={bulge:.6f}")
                center = get_arc_center_from_bulge((x1, y1), (x2, y2), bulge)
                if center:
                    radius = distance(center, (x1, y1))
                    print(f"  계산된 중심: ({center[0]:.3f}, {center[1]:.3f}), 반지름: {radius:.3f}")
                    return center, radius
    else:  # POLYLINE
        verts = list(ent.vertices)
        print(f"  POLYLINE bulge 정보:")
        for idx, v in enumerate(verts):
            bulge = v.dxf.bulge if hasattr(v.dxf, 'bulge') else 0
            print(f"    점{idx+1}: ({v.dxf.location.x:.3f}, {v.dxf.location.y:.3f}), bulge={bulge:.6f}")
        
        # 모든 세그먼트 확인 (닫힌 폴리라인 포함)
        for idx in range(len(verts)):
            v1 = verts[idx]
            # 다음 점 (마지막 점의 경우 첫 번째 점으로)
            next_idx = (idx + 1) % len(verts)
            v2 = verts[next_idx]
            
            if hasattr(v1.dxf, 'bulge') and abs(v1.dxf.bulge) > 1e-7:
                p1 = (v1.dxf.location.x, v1.dxf.location.y)
                p2 = (v2.dxf.location.x, v2.dxf.location.y)
                print(f"  bulge 발견: 점{idx+1}→점{next_idx+1}, bulge={v1.dxf.bulge:.6f}")
                center = get_arc_center_from_bulge(p1, p2, v1.dxf.bulge)
                if center:
                    radius = distance(center, p1)
                    print(f"  계산된 중심: ({center[0]:.3f}, {center[1]:.3f}), 반지름: {radius:.3f}")
                    return center, radius
    
    print(f"  ⚠️ bulge가 있는 세그먼트를 찾을 수 없습니다.")
    return None, None

def circle_exists_at_position(msp, center, radius, tolerance=0.1):
    """특정 위치에 동일한 반지름의 원이 존재하는지 확인"""
    for circle in msp.query('CIRCLE'):
        existing_center = (circle.dxf.center.x, circle.dxf.center.y)
        existing_radius = circle.dxf.radius
        
        # 중심점과 반지름이 모두 허용 오차 내에 있는지 확인
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
    
def scale_triangle(pts, center, scale):
    # pts: [(x1, y1), (x2, y2), (x3, y3)]
    # center: (cx, cy)
    return [
        (center[0] + (x - center[0]) * scale, center[1] + (y - center[1]) * scale)
        for x, y in pts
    ]

def polypoints(ent):
    if ent.dxftype()=='LWPOLYLINE':
        return [(pt[0], pt[1]) for pt in ent.get_points('xy')]
    elif ent.dxftype()=='POLYLINE':
        return [(v.dxf.location.x, v.dxf.location.y) for v in ent.vertices]
    return []

def all_pair_distances(pts):
    return [distance(pts[i], pts[i+1]) for i in range(len(pts)-1)]

def line_exists_between_points(msp, p1, p2, tolerance=1e-6):
    """두 점 사이에 이미 LINE이 존재하는지 확인"""
    for line in msp.query('LINE'):
        start = (line.dxf.start.x, line.dxf.start.y)
        end = (line.dxf.end.x, line.dxf.end.y)
        
        # 양방향 모두 체크
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

def process_dxf(filepath: str):
    print(f"\n📁 처리 중: {Path(filepath).name}")
    doc = ezdxf.readfile(filepath)
    modifier = DxfModifier(filepath)
    c_keys, direct_ls = modifier.find_and_modify_green_lines(doc)
    msp = doc.modelspace()

    # 1. C_LINES 분류: width 0.6 -> ELBO or PIPE (수정됨)
    for dl in direct_ls:
        if not dl.width or abs(dl.width-0.6)>1e-3: continue
        pts = dl.points
        n = len(pts)
        
        # POLYLINE과 LWPOLYLINE 모두 처리하도록 수정
        for ent in msp:
            if ent.dxftype() not in ['POLYLINE', 'LWPOLYLINE']:
                continue
                
            # 각 타입에 맞게 좌표 추출
            if ent.dxftype() == 'POLYLINE':
                epts = [(v.dxf.location.x, v.dxf.location.y) for v in ent.vertices]
            else:  # LWPOLYLINE
                epts = [(pt[0], pt[1]) for pt in ent.get_points('xy')]
                
            # 좌표가 일치하는 엔티티를 찾아서 레이어 설정
            if len(epts)==n and all(abs(epts[i][0]-pts[i][0])<1e-4 and abs(epts[i][1]-pts[i][1])<1e-4 for i in range(n)):
                # bulge가 있으면 ELBO, 없으면 PIPE 레이어로 설정
                ent.dxf.layer = 'ELBO' if has_bulge(ent) else 'PIPE'
                break

    # 2. PL 처리: 다양한 점 개수별 레이어 변경
    entities_to_delete = []  # 삭제할 엔티티 리스트
    
    for ent in list(msp):
        if ent.dxftype() not in ['LWPOLYLINE','POLYLINE']: continue
        pts = polypoints(ent)
        n = len(pts)
        key = tuple((round(x,6),round(y,6)) for x,y in pts)
        if ent.dxftype()=='POLYLINE' and key in c_keys: continue
        if getattr(ent.dxf,'const_width',0)!=0: continue

        # 3점 polyline (PL3)
        if n==3:
            if has_bulge(ent):
                r = get_bulge_radius(ent)
                if r and 2 <= r <= 3:
                    ent.dxf.layer = 'WELDNO'
                    ent.dxf.color = 2
                elif r and 5 <= r <= 8:
                    # INSTNO 처리 - 원으로 대체
                    print(f"\nINSTNO 폴리라인 발견: bulge 반지름 = {r:.3f}")
                    
                    # bulge를 사용하여 정확한 원의 중심점과 반지름 계산
                    center, calculated_radius = get_polyline_arc_center_and_radius_with_bulge(ent)
                    
                    if center and calculated_radius:
                        print(f"폴리라인 타입: {ent.dxftype()}")
                        print(f"3점 좌표: {pts}")
                        print(f"계산된 중심: ({center[0]:.3f}, {center[1]:.3f}), 반지름: {calculated_radius:.3f}")
                        
                        # 동일한 위치에 동일한 원이 있는지 확인
                        if not circle_exists_at_position(msp, center, calculated_radius):
                            # 원 그리기 - CYAN 색상(4)
                            circle = msp.add_circle(
                                center=center,
                                radius=calculated_radius,
                                dxfattribs={'layer': 'INSTNO', 'color': 4}  # CYAN
                            )
                            print(f"✅ CYAN 원 추가 완료: 중심 ({center[0]:.3f}, {center[1]:.3f}), 반지름 {calculated_radius:.3f}")
                            
                            # 원본 폴리라인을 삭제 목록에 추가
                            entities_to_delete.append(ent)
                            print(f"폴리라인을 삭제 목록에 추가")
                        else:
                            print(f"⚠️ 원이 이미 존재 (SKIP)")
                    else:
                        print(f"❌ 원의 중심점 계산 실패")
                        # 계산 실패시에도 레이어는 설정
                        ent.dxf.layer = 'INSTNO'
                        ent.dxf.color = 2

        # 4점 polyline (PL4) - FALL 조건 추가
        elif n==4:
            # 점간 거리 계산 (마지막 점에서 첫 점으로의 거리 포함)
            dists = all_pair_distances(pts)
            last_to_first = distance(pts[3], pts[0])
            
            # FALL 패턴 확인 (허용 오차 0.1mm)
            tolerance = 0.1
            if (len(dists) >= 3 and
                abs(dists[0] - 7.445) <= tolerance and  # 점1→점2
                abs(dists[1] - 1.612) <= tolerance and  # 점2→점3
                abs(dists[2] - 7.592) <= tolerance and  # 점3→점4
                abs(last_to_first - 0) <= tolerance):   # 점4→점1
                ent.dxf.layer = 'FALL'
                ent.dxf.color = 2
            else:
                ent.dxf.layer = 'PL4'
                ent.dxf.color = 7

        # 5점 polyline (PL5)
        elif n==5:
            dists = all_pair_distances(pts)
            if all(d<=4.5 for d in dists):
                ent.dxf.layer = 'itemno'
            elif any(d>=30 for d in dists):
                ent.dxf.layer = 'spoolno'
            else:
                ent.dxf.layer = 'PL5'
            ent.dxf.color = 7

        # 6점 polyline (PL6) - 수정된 부분
        elif n==6:
            dists = all_pair_distances(pts)
            total_dist = sum(dists)  # 모든 점간 거리의 합
            
            # 길이값 합계 기준으로 레이어 지정
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
            elif any(d<=1.0 for d in dists):
                ent.dxf.layer = 'FLAN'
                ent.dxf.color = 2
            elif sum(1 for d in dists if 6<=d<=15)>=2:
                ent.dxf.layer = 'VALV'
                ent.dxf.color = 2
            else:
                ent.dxf.layer = 'PL6'
                ent.dxf.color = 7

        elif n==7:
            dists = all_pair_distances(pts)
            mov_idx = [i for i,d in enumerate(dists) if 3<=d<=5]
            if len(mov_idx)>=2:
                ent.dxf.layer = 'MOV'
                ent.dxf.color = 2
            elif all(d<=2.2 for d in dists):
                ent.dxf.layer='weld'
                ent.dxf.color=2
            else:
                ent.dxf.layer = 'PL7'
                ent.dxf.color = 4

        elif n==8:
            dists = all_pair_distances(pts)
            if sum(1 for d in dists if 1.5<=d<=4)>=5:
                ent.dxf.layer = 'WOLET'
                ent.dxf.color = 2
            else:
                ent.dxf.layer = 'PL8'
                ent.dxf.color = 7

        elif n==9:
            dists = all_pair_distances(pts)
            if all(d<=5 for d in dists):
                ent.dxf.layer = 'CV'
                ent.dxf.color = 2
            else:
                ent.dxf.layer = 'PL9'
                ent.dxf.color = 7

        elif n==10:
            dists = all_pair_distances(pts)
            total_dist = sum(dists)  # 모든 점간 거리의 합
            
            if 13.5 <= total_dist <= 14.5:
                ent.dxf.layer = 'CAP'
                ent.dxf.color = 2  # Yellow
            else:
                ent.dxf.layer = 'PL10'
                ent.dxf.color = 7

        elif n==12:
            dists = all_pair_distances(pts)
            total_dist = sum(dists)  # 모든 점간 거리의 합
            
            if 34 <= total_dist <= 35:
                ent.dxf.layer = 'SFW'
                ent.dxf.color = 2  # Yellow
            else:
                ent.dxf.layer = 'PL12'
                ent.dxf.color = 7

        elif n==2:
            ent.dxf.layer = 'PL2'
            ent.dxf.color = 7
    
    # 삭제 예정인 엔티티들을 실제로 삭제
    print(f"\n삭제 대상 엔티티 수: {len(entities_to_delete)}개")
    for idx, ent in enumerate(entities_to_delete):
        try:
            msp.delete_entity(ent)
            print(f"  [{idx+1}] INSTNO 폴리라인 삭제 완료")
        except Exception as e:
            print(f"  [{idx+1}] 삭제 실패: {e}")
    
    # 3. TEXT 레이어 지정
    for ent in msp.query('TEXT'):
        txt = ent.dxf.text.upper()
        if '<' in txt and '>' in txt:
            ent.dxf.layer = 'itemno'
        elif any(tag in txt for tag in ['EL+','EL-','FL+','FL-']):
            ent.dxf.layer = 'ELEV'
        elif any(letter in txt for letter in ['F','G']):
            ent.dxf.layer = 'FLAN'
        elif 'FALL' in txt:
            ent.dxf.layer = 'FALL'

    # 4. SP3, SP7 처리 (레이어만 지정)
    # 4. SP3, SP7 처리 (레이어만 지정)
    for ent in msp:
        if ent.dxftype() not in ['LWPOLYLINE','POLYLINE']: continue
        pts = polypoints(ent)
        n = len(pts)
        # ARROW 선긋기 - 중복 체크 추가
        if n==3:
            dists = all_pair_distances(pts)
            total_dist = sum(dists)  # 점간 거리의 합 계산
            
            if total_dist <= 5:  # 새로운 조건: 점간 거리 합이 5 이하
                # LINE이 이미 존재하는지 확인
                if not line_exists_between_points(msp, pts[2], pts[0]):
                    # 원래 삼각형 세 변
                    line20 = msp.add_line(pts[2], pts[0], dxfattribs={'color': 7, 'layer': 'ARROW'})
                    print(f"새 LINE 추가: {pts[2]} -> {pts[0]}")
                else:
                    print(f"LINE 이미 존재: {pts[2]} -> {pts[0]} (SKIP)")
        elif n==7:
            dists = all_pair_distances(pts)
            if any(d>30 for d in dists):
                ent.dxf.layer = 'SUPP'

    # 5. PIPE 레이어 처리 (삭제 X, color 만 처리)
    for ent in list(msp):
        if ent.dxftype() in ['LWPOLYLINE','POLYLINE'] and ent.dxf.layer=='PIPE':
            ent.dxf.color = 3

    # FALL 레이어의 2점 폴리라인 색상을 흰색으로 변경
    for ent in list(msp):
        if ent.dxftype() in ['LWPOLYLINE','POLYLINE'] and ent.dxf.layer=='FALL':
            pts = polypoints(ent)
            if len(pts) == 2:
                ent.dxf.color = 7  # 흰색

    for txt in msp.query('TEXT'):
        txt.dxf.color = 2
        txt.dxf.style = "ARIAL"
       # txt.dxf.width = 0.86 

    def set_width_by_f_x(msp):
        # 1. FABRICATION MATERIALS 텍스트의 'F' 문자 위치(X좌표) 찾기
        f_x = None
        for txt in msp.query('TEXT'):
            if txt.dxf.text and txt.dxf.text.strip().upper().startswith('F'):
                f_x = txt.dxf.insert[0]
                break  # 첫 'F'만 찾으면 됨

        if f_x is None:
            print("FABRICATION MATERIALS의 F 위치를 찾지 못했습니다.")
            return

        # 2. 전체 TEXT를 돌면서 F 기준 왼쪽/오른쪽에 width 적용
        for txt in msp.query('TEXT'):
            if not txt.dxf.text:
                continue
            x = txt.dxf.insert[0]
            # 폭은 모두 float으로 비교
            if x < f_x - 1e-4:  # F의 X보다 왼쪽
                txt.dxf.width = 0.87
            else:  # F 포함 오른쪽(포함)
                txt.dxf.width = 0.8
            txt.dxf.style = "ARIAL"
            txt.dxf.color = 2


        if "ARIAL" not in doc.styles:
            doc.styles.new("ARIAL", dxfattribs={"font": "arial.ttf"})
    set_width_by_f_x(msp)

    # 7. 파일 저장
    outname = Path(filepath).with_stem(Path(filepath).stem + '_PL')
    doc.saveas(str(outname))
    print(f"✅ 저장 완료: {outname}")

def select_files_and_process():
    root = tk.Tk()
    root.withdraw()
    files = filedialog.askopenfilenames(filetypes=[('DXF files','*.dxf')])
    for f in files:
        process_dxf(f)

if __name__ == '__main__':
    select_files_and_process()