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
                if line == "POLYLINE":
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
                    if width and width > 0 and len(points) >= 2:
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
        for entity in msp:
            if entity.dxftype() == "POLYLINE":
                pts = [(v.dxf.location.x, v.dxf.location.y) for v in entity.vertices]
                key = tuple((round(x,6), round(y,6)) for x,y in pts)
                for dl in direct_lines:
                    if len(dl.points) == len(pts) and self._points_match(pts, dl.points) and abs((dl.width or 0) - 0.6) < 1e-3:
                        entity.dxf.color = 3  # Green
                        entity.dxf.lineweight = 50
                        c_lines_key.add(key)
                        break
        return c_lines_key, direct_lines

    def _points_match(self, p1: List[Tuple[float,float]], p2: List[Tuple[float,float]], tol=1e-3) -> bool:
        if len(p1) != len(p2): return False
        for a,b in zip(p1,p2):
            if abs(a[0]-b[0])>tol or abs(a[1]-b[1])>tol:
                return False
        return True

# 보조 함수들

def draw_line(msp, p1, p2, color=7, layer=None):
    attrib = {"color": color}
    if layer:
        attrib["layer"] = layer
    msp.add_line(p1, p2, dxfattribs=attrib)


def draw_triangle(msp, pts, color=7, layer=None):
    draw_line(msp, pts[0], pts[1], color, layer)
    draw_line(msp, pts[1], pts[2], color, layer)
    draw_line(msp, pts[2], pts[0], color, layer)


def centroid(pts):
    x = sum(p[0] for p in pts)/len(pts)
    y = sum(p[1] for p in pts)/len(pts)
    return (x,y)


def scale_triangle(pts, center, scale):
    return [(center[0]+(x-center[0])*scale, center[1]+(y-center[1])*scale) for x,y in pts]


def distance(p1, p2):
    return math.dist(p1, p2)


def has_bulge(ent):
    if ent.dxftype() == 'LWPOLYLINE':
        for pt in ent:
            if hasattr(pt.dxf, 'bulge') and abs(pt.dxf.bulge)>1e-7:
                return True
        return False
    elif ent.dxftype()=='POLYLINE':
        for v in ent.vertices:
            if hasattr(v.dxf, 'bulge') and abs(v.dxf.bulge)>1e-7:
                return True
        return False
    return False


def get_bulge_radius(ent):
    pts = polypoints(ent)
    n = len(pts)
    if n<2: return None
    if ent.dxftype()=='LWPOLYLINE':
        for idx,pt in enumerate(ent):
            if hasattr(pt.dxf, 'bulge') and abs(pt.dxf.bulge)>1e-7 and idx<n-1:
                chord = distance(pts[idx], pts[idx+1])
                b = pt.dxf.bulge
                theta = 4*math.atan(abs(b))
                if theta==0: continue
                return abs(chord/(2*math.sin(theta/2)))
    else:
        verts = list(ent.vertices)
        for idx, v in enumerate(verts):
            if hasattr(v.dxf, 'bulge') and abs(v.dxf.bulge)>1e-7 and idx<n-1:
                chord = distance(pts[idx], pts[idx+1])
                b = v.dxf.bulge
                theta = 4*math.atan(abs(b))
                if theta==0: continue
                return abs(chord/(2*math.sin(theta/2)))
    return None


def polypoints(ent):
    if ent.dxftype()=='LWPOLYLINE':
        return list(ent.get_points('xy'))
    elif ent.dxftype()=='POLYLINE':
        return [(v.dxf.location.x, v.dxf.location.y) for v in ent.vertices]
    return []


def all_pair_distances(pts):
    return [distance(pts[i], pts[i+1]) for i in range(len(pts)-1)]

def process_dxf(filepath: str):
    print(f"\n📁 처리 중: {Path(filepath).name}")
    doc = ezdxf.readfile(filepath)
    modifier = DxfModifier(filepath)
    c_keys, direct_ls = modifier.find_and_modify_green_lines(doc)
    msp = doc.modelspace()
    to_delete = []

    # 1. C_LINES 분류: width 0.6 -> ELBO or PIPE
    for dl in direct_ls:
        if not dl.width or abs(dl.width-0.6)>1e-3: continue
        pts = dl.points; n=len(pts)
        for ent in msp.query('POLYLINE'):
            epts=[(v.dxf.location.x,v.dxf.location.y) for v in ent.vertices]
            if len(epts)==n and all(abs(epts[i][0]-pts[i][0])<1e-4 and abs(epts[i][1]-pts[i][1])<1e-4 for i in range(n)):
                if n==2:
                    ent.dxf.layer = 'ELBO' if has_bulge(ent) else 'PIPE'
                break

    # 2. PL 처리: PL3, PL5, PL7, etc.
    for ent in msp:
        if ent.dxftype() not in ['LWPOLYLINE','POLYLINE']: continue
        pts = polypoints(ent); n=len(pts)
        key=tuple((round(x,6),round(y,6)) for x,y in pts)
        if ent.dxftype()=='POLYLINE' and key in c_keys: continue
        if getattr(ent.dxf,'const_width',0)!=0: continue

        # 3점 polyline (PL3)
        if n==3:
           if has_bulge(ent):
            r = get_bulge_radius(ent)
            if r and 2 <= r <= 3:
                # weldno
                center1 = ((pts[0][0]+pts[1][0])/2, (pts[0][1]+pts[1][1])/2)
                center2 = ((pts[1][0]+pts[2][0])/2, (pts[1][1]+pts[2][1])/2)
                msp.add_circle(center=center1, radius=r, dxfattribs={'color':2, 'layer':'weldno'})
                msp.add_circle(center=center2, radius=r, dxfattribs={'color':2, 'layer':'weldno'})
                to_delete.append(ent)
            elif r and 5 <= r <= 8:
                # instno
                center1 = ((pts[0][0]+pts[1][0])/2, (pts[0][1]+pts[1][1])/2)
                center2 = ((pts[1][0]+pts[2][0])/2, (pts[1][1]+pts[2][1])/2)
                msp.add_circle(center=center1, radius=r, dxfattribs={'color':2, 'layer':'instno'})
                msp.add_circle(center=center2, radius=r, dxfattribs={'color':2, 'layer':'instno'})
                to_delete.append(ent)
            else:
            # 기본 선분 P1-P2, P2-P3
                draw_line(msp, pts[0], pts[1], color=7, layer='ARROW')
                draw_line(msp, pts[1], pts[2], color=7, layer='ARROW')
        
            # P1-P3 선: 거리 1.0 이하일 때만
            if distance(pts[0], pts[2]) <= 1.0:
                draw_line(msp, pts[0], pts[2], color=7, layer='ARROW')
            # Bulge 유무에 따른 레이어 지정 또는 삼각형 스케일 드로잉
            if has_bulge(ent):
                r = get_bulge_radius(ent)
                if r and 2 <= r <= 3:
                    ent.dxf.layer = 'weldno'
                elif r and 5 <= r <= 8:
                    ent.dxf.layer = 'instno'
            else:
                # 크기 조건 만족 시 내부 삼각형 드로잉
                if 1.9 <= distance(pts[0], pts[1]) <= 2.1:
                    ctr = centroid(pts)
                    for i in range(1, 5):
                        tri = scale_triangle(pts, ctr, 1 - 0.2 * i)
                        draw_triangle(msp, tri, color=7, layer='ARROW')
            ent.dxf.layer = 'ARROW'
            to_delete.append(ent)

        # 5점 polyline (PL5)
        elif n==5:
            dists=all_pair_distances(pts)
            if all(d<=4.5 for d in dists):
                for i in range(4): msp.add_line(pts[i],pts[i+1],dxfattribs={'layer':'itemno'})
                to_delete.append(ent)
                continue
            if any(d>=30 for d in dists):
                for i in range(4): msp.add_line(pts[i],pts[i+1],dxfattribs={'layer':'spoolno'})
                to_delete.append(ent)
                continue
            for i in range(4): draw_line(msp, pts[i], pts[i+1])
            to_delete.append(ent)
            
         # 6점 polyline (PL6)
        elif n == 6:
            dists = all_pair_distances(pts)
            if sum(1 for d in dists if 1.3 <= d <= 1.5) == 2:
                # FLOW
                for i in range(n-1):
                    msp.add_line(pts[i], pts[i+1], dxfattribs={'layer':'FLOW', 'color':2})
            elif all(2 <= d <= 8 for d in dists):
                # REDU
                for i in range(n-1):
                    msp.add_line(pts[i], pts[i+1], dxfattribs={'layer':'REDU', 'color':2})
            elif sum(1 for d in dists if 3 <= d <= 3.5) >= 3:
                # OLET
                for i in range(n-1):
                    msp.add_line(pts[i], pts[i+1], dxfattribs={'layer':'OLET', 'color':2})
            elif any(d <= 1.0 for d in dists):
                # FLAN
                for i in range(n-1):
                    msp.add_line(pts[i], pts[i+1], dxfattribs={'layer':'FLAN', 'color':2})
            elif sum(1 for d in dists if 6 <= d <= 15) >= 2:
                # VALV
                for i in range(n-1):
                    msp.add_line(pts[i], pts[i+1], dxfattribs={'layer':'VALV', 'color':2})
            else:
                # 기본 yellow
                for i in range(n-1):
                    msp.add_line(pts[i], pts[i+1], dxfattribs={'layer':'PL6', 'color':7})
            to_delete.append(ent)

        elif n == 7:
            dists = all_pair_distances(pts)
            mov_idx = [i for i, d in enumerate(dists) if 3 <= d <= 5]
            if len(mov_idx) >= 2:
                # 모든 점을 연결하는 6개의 선을 그리고, 모두 MOV 레이어와 YELLOW 색상!
                for i in range(n-1):
                    msp.add_line(pts[i], pts[i+1], dxfattribs={'layer': 'MOV', 'color': 2})
                to_delete.append(ent)
            elif all(d <= 2.2 for d in dists):
                ent.dxf.layer = 'weld'
                ent.dxf.color = 2  # YELLOW
                # 삭제하지 않음
            else:
                for i in range(n-1):
                    msp.add_line(pts[i], pts[i+1], dxfattribs={'color': 4})  # CYAN
                to_delete.append(ent)

        elif n == 8:
            dists = all_pair_distances(pts)
            count_wolet = sum(1 for d in dists if 1.5 <= d <= 4)
            if count_wolet >= 5:
                for i in range(n-1):
                    msp.add_line(pts[i], pts[i+1], dxfattribs={'layer':'WOLET', 'color':2})
            else:
                for i in range(n-1):
                    msp.add_line(pts[i], pts[i+1], dxfattribs={'layer':'PL8', 'color':7})
            to_delete.append(ent)


        elif n == 9:
            dists = all_pair_distances(pts)
            if all(d <= 5 for d in dists):
                for i in range(n-1):
                    msp.add_line(pts[i], pts[i+1], dxfattribs={'layer':'CV', 'color':2})
            else:
                for i in range(n-1):
                    msp.add_line(pts[i], pts[i+1], dxfattribs={'layer':'PL9', 'color':7})
            to_delete.append(ent)
 
        # 2점 polyline
        elif n==2:
            draw_line(msp, pts[0], pts[1], color=7)
            to_delete.append(ent)
        # 4점 polyline
        elif n==4:
            for i in range(3): draw_line(msp, pts[i], pts[i+1], color=7)
            to_delete.append(ent)

        # 3. TEXT 레이어 지정
        for ent in msp:
            if ent.dxftype()!='TEXT': continue
            txt = ent.dxf.text.upper() if hasattr(ent.dxf, 'text') else ''
            if '<' in txt and '>' in txt:
                ent.dxf.layer = 'itemno'
            elif any(tag in txt for tag in ['EL+','EL-','FL+','FL-']):
                ent.dxf.layer = 'ELEV'
            elif any(letter in txt for letter in ['F','G']):
                ent.dxf.layer = 'FLAN'
            elif 'FALL' in txt:
                ent.dxf.layer = 'FALL'

    # 4. SP3, SP7 처리
    for ent in msp:
        if ent.dxftype() not in ['LWPOLYLINE','POLYLINE']: continue
        pts=polypoints(ent); n=len(pts)
        if n==3:
            dists=all_pair_distances(pts)
            if all(1.5<=d<=2.3 for d in dists) and distance(pts[0], pts[2])<=1:
                draw_line(msp, pts[0], pts[1], layer='ARROW')
                draw_line(msp, pts[1], pts[2], layer='ARROW')
                draw_line(msp, pts[2], pts[0], layer='ARROW')
                ent.dxf.layer='ARROW'
        elif n==7:
            dists=all_pair_distances(pts)
            if any(d>30 for d in dists): ent.dxf.layer='SUPP'

    # 삭제 대상 엔티티 제거
    for ent in to_delete:
        try:
            msp.delete_entity(ent)
        except:
            pass

    # 5. PIPE 레이어 DP 처리
    for ent in list(msp):
        if ent.dxftype() in ['LWPOLYLINE','POLYLINE'] and ent.dxf.layer=='PIPE':
            pts=polypoints(ent)
            if len(pts)>=2:
                p1,p2=pts[0], pts[1]
                msp.add_line(p1, p2, dxfattribs={'layer':'PIPE','color':3})
            msp.delete_entity(ent)

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

    # 6. 파일 저장
    outname = Path(filepath).with_stem(Path(filepath).stem + "_PL")
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
