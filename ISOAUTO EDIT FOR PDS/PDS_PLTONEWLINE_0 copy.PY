import ezdxf
from pathlib import Path
import tkinter as tk
from tkinter import filedialog
from typing import List, Tuple, Optional
import math
from dataclasses import dataclass

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

def calculate_polyline_area(points):
    """폴리라인의 면적을 계산 (Shoelace formula)"""
    n = len(points)
    if n < 3:
        return 0
    
    area = 0
    for i in range(n):
        j = (i + 1) % n
        area += points[i][0] * points[j][1]
        area -= points[j][0] * points[i][1]
    
    return abs(area) / 2.0

def stretch_entities_in_range(msp, header_x, header_y, stretch_x=39):
    """
    헤더 위치를 기준으로 특정 범위 내의 YELLOW TEXT와 라인들을 STRETCH
    범위: X: header_x-5 ~ header_x+170, Y: header_y ~ header_y-250
    STRETCH: 범위 내의 점들만 이동, 범위를 가로지르는 객체는 늘어남
    """
    # 범위 정의
    x_min = header_x - 5
    x_max = header_x + 170
    y_min = header_y - 250
    y_max = header_y
    
    print(f"\n📐 STRETCH 범위:")
    print(f"  X 범위: {x_min:.3f} ~ {x_max:.3f}")
    print(f"  Y 범위: {y_min:.3f} ~ {y_max:.3f}")
    print(f"  STRETCH 거리: X축 +{stretch_x}mm")
    
    stretched_count = 0
    
    # 점이 범위 내에 있는지 확인하는 함수
    def point_in_range(x, y):
        return x_min <= x <= x_max and y_min <= y <= y_max
    
    # 1. YELLOW TEXT (color=2) - 완전히 범위 내에 있으면 이동
    for text in msp.query('TEXT'):
        if text.dxf.color == 2:  # YELLOW
            x, y = text.dxf.insert[0], text.dxf.insert[1]
            if point_in_range(x, y):
                text.dxf.insert = (x + stretch_x, y, text.dxf.insert[2] if len(text.dxf.insert) > 2 else 0)
                stretched_count += 1
    
    # 2. LINE STRETCH
    for line in msp.query('LINE'):
        start_x, start_y = line.dxf.start.x, line.dxf.start.y
        end_x, end_y = line.dxf.end.x, line.dxf.end.y
        
        start_in_range = point_in_range(start_x, start_y)
        end_in_range = point_in_range(end_x, end_y)
        
        # 시작점만 범위 내에 있으면 시작점만 이동 (STRETCH)
        if start_in_range and not end_in_range:
            line.dxf.start = (start_x + stretch_x, start_y, line.dxf.start.z)
            stretched_count += 1
        # 끝점만 범위 내에 있으면 끝점만 이동 (STRETCH)
        elif not start_in_range and end_in_range:
            line.dxf.end = (end_x + stretch_x, end_y, line.dxf.end.z)
            stretched_count += 1
        # 양쪽 모두 범위 내에 있으면 전체 이동
        elif start_in_range and end_in_range:
            line.dxf.start = (start_x + stretch_x, start_y, line.dxf.start.z)
            line.dxf.end = (end_x + stretch_x, end_y, line.dxf.end.z)
            stretched_count += 1
    
    # 3. POLYLINE, LWPOLYLINE STRETCH
    for ent in msp:
        if ent.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
            modified = False
            
            if ent.dxftype() == 'LWPOLYLINE':
                # LWPOLYLINE의 경우
                new_points = []
                for x, y, *rest in ent.get_points('xyb'):
                    if point_in_range(x, y):
                        new_points.append((x + stretch_x, y) + tuple(rest))
                        modified = True
                    else:
                        new_points.append((x, y) + tuple(rest))
                if modified:
                    ent.set_points(new_points)
                    stretched_count += 1
            else:
                # POLYLINE의 경우
                for vertex in ent.vertices:
                    loc = vertex.dxf.location
                    if point_in_range(loc.x, loc.y):
                        vertex.dxf.location = (loc.x + stretch_x, loc.y, loc.z)
                        modified = True
                if modified:
                    stretched_count += 1
    
    # 4. ARC STRETCH - 중심점이 범위 내에 있으면 이동
    for arc in msp.query('ARC'):
        center_x, center_y = arc.dxf.center.x, arc.dxf.center.y
        if point_in_range(center_x, center_y):
            arc.dxf.center = (center_x + stretch_x, center_y, arc.dxf.center.z)
            stretched_count += 1
    
    # 5. CIRCLE STRETCH - 중심점이 범위 내에 있으면 이동
    for circle in msp.query('CIRCLE'):
        center_x, center_y = circle.dxf.center.x, circle.dxf.center.y
        if point_in_range(center_x, center_y):
            circle.dxf.center = (center_x + stretch_x, center_y, circle.dxf.center.z)
            stretched_count += 1
    
    print(f"✅ 총 {stretched_count}개의 엔티티를 STRETCH했습니다.")

def find_and_process_weld_header(msp):
    """
    WELD SHOP WELD WELD 헤더를 찾아서 관련 라인들을 처리
    """
    print("\n🔍 WELD 헤더 처리 시작...")
    
    # 디버깅을 위해 모든 텍스트 출력
    print("\n📝 도면 내 모든 텍스트 확인:")
    all_texts = []
    for text in msp.query('TEXT'):
        if text.dxf.text:
            all_texts.append(text)
            # WELD 또는 SHOP이 포함된 텍스트만 출력
            if 'WELD' in text.dxf.text.upper() or 'SHOP' in text.dxf.text.upper():
                print(f"   텍스트: '{text.dxf.text}' at X={text.dxf.insert[0]:.1f}, Y={text.dxf.insert[1]:.1f}")
    
    # 1. 다양한 방법으로 WELD 패턴 찾기
    first_weld = None
    pattern_found = False
    
    # 방법 1: 한 줄에 전체 패턴이 있는 경우
    for text in all_texts:
        text_upper = text.dxf.text.upper()
        # 공백을 제거하거나 축소하여 비교
        text_compressed = ' '.join(text_upper.split())
        
        if 'WELD' in text_compressed and 'SHOP' in text_compressed:
            # WELD SHOP WELD WELD 순서 확인
            if text_compressed.count('WELD') >= 3 and 'WELD SHOP' in text_compressed:
                first_weld = text
                pattern_found = True
                print(f"✅ 한 줄에서 WELD 패턴 발견: '{text.dxf.text}'")
                break
    
    # 방법 2: 개별 텍스트로 나뉘어 있는 경우
    if not pattern_found:
        # Y 좌표로 그룹화 (같은 줄에 있는 텍스트들)
        y_groups = {}
        for text in all_texts:
            y = round(text.dxf.insert[1], 1)  # 0.1 단위로 반올림
            if y not in y_groups:
                y_groups[y] = []
            y_groups[y].append(text)
        
        # 각 그룹에서 WELD SHOP WELD WELD 패턴 찾기
        for y, texts in y_groups.items():
            # X 좌표로 정렬
            texts.sort(key=lambda t: t.dxf.insert[0])
            
            # 텍스트 내용 연결
            combined = ' '.join([t.dxf.text.upper().strip() for t in texts])
            
            # 패턴 확인
            if 'WELD' in combined and 'SHOP' in combined:
                words = combined.split()
                # WELD SHOP WELD WELD 순서 찾기
                for i in range(len(words) - 3):
                    if (words[i] == 'WELD' and 
                        words[i+1] == 'SHOP' and 
                        words[i+2] == 'WELD' and 
                        i+3 < len(words) and words[i+3] == 'WELD'):
                        # 첫 번째 WELD 찾기
                        for t in texts:
                            if 'WELD' in t.dxf.text.upper():
                                first_weld = t
                                pattern_found = True
                                print(f"✅ 개별 텍스트에서 WELD 패턴 발견!")
                                print(f"   Y={y}에서 발견: {combined}")
                                break
                        break
                if pattern_found:
                    break
    
    # 방법 3: 더 유연한 검색 (WELD가 3개 이상, SHOP이 1개 이상)
    if not pattern_found:
        print("\n💡 유연한 검색 시도...")
        for y, texts in y_groups.items():
            combined = ' '.join([t.dxf.text.upper().strip() for t in texts])
            weld_count = combined.count('WELD')
            shop_count = combined.count('SHOP')
            
            if weld_count >= 3 and shop_count >= 1:
                # 첫 번째 WELD 텍스트 찾기
                for t in texts:
                    if 'WELD' in t.dxf.text.upper():
                        first_weld = t
                        pattern_found = True
                        print(f"✅ 유연한 검색으로 패턴 발견!")
                        print(f"   Y={y}에서 WELD {weld_count}개, SHOP {shop_count}개")
                        break
                if pattern_found:
                    break
    
    if not first_weld:
        print("⚠️ WELD 패턴을 찾을 수 없습니다.")
        print("   가능한 원인:")
        print("   - 텍스트가 다른 레이어에 있음")
        print("   - 대소문자나 공백 문제")
        print("   - WELD/SHOP 텍스트가 도면에 없음")
        return
    
    # 2. 첫 번째 WELD 위로 숫자 텍스트 찾기
    weld_y = first_weld.dxf.insert[1]
    weld_x = first_weld.dxf.insert[0]
    
    print(f"\n📍 첫 번째 WELD 위치: X={weld_x:.3f}, Y={weld_y:.3f}")
    
    numeric_texts = []
    for text in msp.query('TEXT'):
        if text.dxf.text:
            # 숫자 판별을 더 유연하게
            text_content = text.dxf.text.strip()
            # 숫자, 점, 대시, 공백 제거 후 숫자인지 확인
            cleaned = text_content.replace('.', '').replace('-', '').replace(' ', '')
            
            if cleaned and (cleaned.isdigit() or 
                           (cleaned.replace(',', '').isdigit()) or  # 쉼표 포함
                           (text_content.count('.') <= 1 and cleaned.replace('.', '').isdigit())):  # 소수점
                
                text_x = text.dxf.insert[0]
                text_y = text.dxf.insert[1]
                
                # WELD 위쪽, X축 근처
                if (text_y > weld_y and 
                    abs(text_x - weld_x) < 10 and  # X 범위 ±10mm로 축소
                    text_y - weld_y < 200):  # Y 범위 확대
                    numeric_texts.append((text_y, text))
                    print(f"   숫자 텍스트 발견: '{text_content}' at Y={text_y:.3f}")
    
    if not numeric_texts:
        print("⚠️ WELD 위에 숫자 텍스트를 찾을 수 없습니다.")
        print("   하지만 작업을 계속 진행합니다...")
        # 숫자 텍스트가 없어도 WELD Y 위치를 기준으로 계속 진행
        top_text_y = weld_y + 10  # WELD 위 10mm를 기준으로 설정
    else:
        # Y값으로 정렬
        numeric_texts.sort(key=lambda x: x[0])
        print(f"\n✅ 숫자 텍스트 {len(numeric_texts)}개 발견")
        top_text_y = numeric_texts[-1][0]
    
    # 3. 가장 위 숫자 텍스트 + Y 방향으로 60mm 이하의 첫 번째 수평선 찾기
    bline = None
    horizontal_lines = []
    
    # 모든 수평선 검색 (다른 객체가 있어도 계속)
    print("\n🔍 수평선 검색 중...")
    for line in msp.query('LINE'):
        try:
            start_x, start_y = line.dxf.start.x, line.dxf.start.y
            end_x, end_y = line.dxf.end.x, line.dxf.end.y
            
            # 수평선인지 확인 (Y 좌표가 거의 같음)
            if abs(start_y - end_y) < 0.1:
                line_length = abs(end_x - start_x)
                # 60mm 이하이고 기준점 위에 있는 라인
                if line_length <= 60 and start_y > top_text_y:
                    horizontal_lines.append((start_y, line, line_length))
                    print(f"   수평선 발견: Y={start_y:.3f}, 길이={line_length:.3f}mm")
        except Exception as e:
            print(f"   라인 처리 중 오류 (무시하고 계속): {e}")
            continue
    
    if horizontal_lines:
        # Y값이 가장 작은 (가장 아래) 수평선을 BLINE으로
        horizontal_lines.sort(key=lambda x: x[0])
        bline = horizontal_lines[0][1]
        bline_y = horizontal_lines[0][0]
        bline_length = horizontal_lines[0][2]
        
        # BLINE의 레이어를 'BLINE'으로 변경
        try:
            bline.dxf.layer = 'BLINE'
            print(f"✅ BLINE 발견 및 레이어 변경: Y={bline_y:.3f}, 길이={bline_length:.3f}mm")
        except Exception as e:
            print(f"⚠️ BLINE 레이어 변경 실패: {e}")
    else:
        print("⚠️ 조건에 맞는 BLINE을 찾을 수 없습니다.")
        print("   BLINE 관련 작업을 건너뜁니다.")
        return
    
    # 4. BLINE에 수직으로 교차하는 라인 찾기 (좌측부터 4개)
    bline_start_x = min(bline.dxf.start.x, bline.dxf.end.x)
    bline_end_x = max(bline.dxf.start.x, bline.dxf.end.x)
    bline_y = bline.dxf.start.y
    
    print(f"\n📐 BLINE 범위: X={bline_start_x:.3f} ~ {bline_end_x:.3f}, Y={bline_y:.3f}")
    
    vertical_lines = []
    all_vertical_count = 0
    
    print("\n🔍 수직선 검색 중...")
    for line in msp.query('LINE'):
        try:
            start_x, start_y = line.dxf.start.x, line.dxf.start.y
            end_x, end_y = line.dxf.end.x, line.dxf.end.y
            
            # 수직선인지 확인 (X 좌표가 거의 같음)
            if abs(start_x - end_x) < 0.1:
                all_vertical_count += 1
                x_pos = start_x
                
                # 디버깅을 위한 상세 정보
                if bline_start_x - 10 <= x_pos <= bline_end_x + 10:  # 범위를 약간 확대하여 확인
                    print(f"   후보 수직선: X={x_pos:.3f}, Y={min(start_y, end_y):.3f}~{max(start_y, end_y):.3f}")
                
                # BLINE과 교차하는지 확인 (허용 오차 추가)
                tolerance = 0.5  # 교차 판단 허용 오차
                if (bline_start_x - tolerance <= x_pos <= bline_end_x + tolerance and 
                    min(start_y, end_y) <= bline_y <= max(start_y, end_y)):
                    vertical_lines.append((x_pos, line))
                    print(f"   ✅ 교차하는 수직선 발견: X={x_pos:.3f}")
        except Exception as e:
            print(f"   수직선 처리 중 오류 (무시하고 계속): {e}")
            continue
    
    print(f"   전체 수직선 수: {all_vertical_count}개")
    
    # X 좌표로 정렬 (좌측부터)
    vertical_lines.sort(key=lambda x: x[0])
    
    # 처음 4개만 선택
    selected_verticals = vertical_lines[:4]
    print(f"✅ 수직선 {len(selected_verticals)}개 선택")
    
    if len(selected_verticals) == 0:
        print("   ⚠️ BLINE과 교차하는 수직선을 찾지 못했습니다.")
        print("   가능한 원인:")
        print("   - BLINE이 너무 짧음 (7.225mm)")
        print("   - 수직선이 BLINE 높이에 도달하지 않음")
        print("   - 수직선이 BLINE의 X 범위를 벗어남")
    
    # 5. 선택된 4개 수직선의 BLINE 아래 부분만 남기도록 TRIM (반대로 수정)
    trim_count = 0
    for x_pos, line in selected_verticals:
        try:
            start_y = line.dxf.start.y
            end_y = line.dxf.end.y
            
            # BLINE 아래쪽 부분만 남기도록 수정
            if start_y < bline_y < end_y:
                # 위쪽 끝점을 BLINE 위치로 수정 (아래 부분만 남김)
                line.dxf.end = (line.dxf.end.x, bline_y, line.dxf.end.z)
                trim_count += 1
                print(f"   수직선 TRIM 성공: X={x_pos:.3f} (아래 부분 유지)")
            elif end_y < bline_y < start_y:
                # 아래쪽 끝점을 BLINE 위치로 수정 (아래 부분만 남김)
                line.dxf.start = (line.dxf.start.x, bline_y, line.dxf.start.z)
                trim_count += 1
                print(f"   수직선 TRIM 성공: X={x_pos:.3f} (아래 부분 유지)")
        except Exception as e:
            print(f"   수직선 TRIM 실패 (무시하고 계속): {e}")
            continue
    
    print(f"✅ {trim_count}개의 수직선 TRIM 완료")
    
    # 6. BLINE과 유사한 위치의 라인들 찾아서 삭제 (범위 확대)
    lines_to_delete = []
    line_info = []  # 삭제할 라인의 정보를 미리 저장
    
    print("\n🔍 삭제할 수평선 검색 중...")
    print(f"   BLINE 정보: Y={bline_y:.3f}, X={bline_start_x:.3f}~{bline_end_x:.3f}, 길이={bline_length:.3f}mm")
    
    # 먼저 BLINE과 동일한 X 범위를 가진 모든 수평선 찾기
    for line in msp.query('LINE'):
        try:
            if line == bline:  # BLINE은 제외
                continue
                
            start_x, start_y = line.dxf.start.x, line.dxf.start.y
            end_x, end_y = line.dxf.end.x, line.dxf.end.y
            
            # 수평선이고 BLINE 위쪽에 있는지 확인
            if (abs(start_y - end_y) < 0.1 and  # 수평선
                start_y > bline_y):  # BLINE 위쪽 (거리 제한 없음)
                
                # BLINE과 X 범위가 비슷한지 확인
                line_start_x = min(start_x, end_x)
                line_end_x = max(start_x, end_x)
                line_length = abs(end_x - start_x)
                
                # BLINE과 길이가 비슷하고 X 범위가 겹치는지 확인
                if (abs(line_length - bline_length) < 5 and  # 길이 차이 5mm 이내
                    line_start_x <= bline_end_x and line_end_x >= bline_start_x):  # X 범위 겹침
                    
                    # Y 간격 확인 (6-7mm 간격의 배수인지)
                    y_gap = start_y - bline_y
                    
                    # 6-7mm 간격으로 반복되는 모든 라인 찾기
                    gap_interval = 6.5  # 평균 간격
                    tolerance = 1.5  # 허용 오차
                    
                    # gap이 6.5의 배수에 가까운지 확인
                    if y_gap > 0:
                        multiple = round(y_gap / gap_interval)
                        expected_y = bline_y + (multiple * gap_interval)
                        
                        if abs(start_y - expected_y) < tolerance:
                            lines_to_delete.append(line)
                            line_info.append({'y': start_y, 'gap': y_gap})
                            print(f"   삭제 대상 라인 발견: Y={start_y:.3f} (BLINE+{y_gap:.1f}mm)")
        except Exception as e:
            print(f"   라인 검색 중 오류 (무시하고 계속): {e}")
            continue
    
    # 추가로 BLINE과 정확히 같은 길이와 X 위치를 가진 라인 찾기
    for line in msp.query('LINE'):
        try:
            if line == bline or line in lines_to_delete:  # 이미 처리된 라인 제외
                continue
                
            start_x, start_y = line.dxf.start.x, line.dxf.start.y
            end_x, end_y = line.dxf.end.x, line.dxf.end.y
            
            # 수평선이고 BLINE과 정확히 같은 X 좌표를 가진 경우
            if (abs(start_y - end_y) < 0.1 and  # 수평선
                abs(start_x - bline.dxf.start.x) < 0.1 and  # 시작 X 동일
                abs(end_x - bline.dxf.end.x) < 0.1 and  # 끝 X 동일
                start_y > bline_y):  # BLINE 위쪽
                
                # 이미 리스트에 없는 경우만 추가
                already_exists = False
                for existing_line in lines_to_delete:
                    if existing_line == line:
                        already_exists = True
                        break
                
                if not already_exists:
                    lines_to_delete.append(line)
                    y_gap = start_y - bline_y
                    line_info.append({'y': start_y, 'gap': y_gap})
                    print(f"   정확히 일치하는 라인 발견: Y={start_y:.3f} (BLINE+{y_gap:.1f}mm)")
        except Exception as e:
            print(f"   라인 검색 중 오류 (무시하고 계속): {e}")
            continue
    
    # 라인 삭제
    print(f"\n🗑️ 총 {len(lines_to_delete)}개의 라인 삭제 예정")
    deleted_count = 0
    for i, line in enumerate(lines_to_delete):
        try:
            # 삭제하기 전에 정보 가져오기
            info = line_info[i] if i < len(line_info) else {'y': 0, 'gap': 0}
            msp.delete_entity(line)
            deleted_count += 1
            print(f"   라인 삭제 완료: Y={info['y']:.3f} (BLINE+{info['gap']:.1f}mm)")
        except Exception as e:
            print(f"   라인 삭제 실패 (무시하고 계속): {e}")
    
    print(f"✅ {deleted_count}개의 라인 실제 삭제 완료")
    print(f"\n✅ WELD 헤더 처리 완료!")

def process_pl97_and_pl31(msp):
    """
    PL97 레이어 처리 및 PL31 면적 기반 삭제
    """
    print("\n🔍 PL97 및 PL31 레이어 처리 시작...")
    
    # 1. PL97 레이어 찾기
    pl97_entities = []
    for ent in msp:
        if ent.dxftype() in ['LWPOLYLINE', 'POLYLINE'] and ent.dxf.layer == 'PL97':
            pl97_entities.append(ent)
    
    if not pl97_entities:
        print("⚠️ PL97 레이어를 찾을 수 없습니다.")
    else:
        print(f"✅ PL97 레이어 {len(pl97_entities)}개 발견")
        
        # 각 PL97 엔티티 처리
        for idx, ent in enumerate(pl97_entities):
            pts = polypoints(ent)
            if pts:
                # 중심점 계산
                center = centroid(pts)
                print(f"\n   PL97 #{idx+1} 중심: ({center[0]:.3f}, {center[1]:.3f})")
                
                # 다양한 지름의 원 그리기
                diameters = [2.5, 2.0, 1.5, 1.0, 0.5]
                for diameter in diameters:
                    radius = diameter / 2.0
                    try:
                        circle = msp.add_circle(
                            center=center,
                            radius=radius,
                            dxfattribs={'layer': 'WELD', 'color': 2}  # YELLOW
                        )
                        print(f"   ✅ 지름 {diameter}mm 원 추가 (반지름 {radius}mm)")
                    except Exception as e:
                        print(f"   ❌ 지름 {diameter}mm 원 추가 실패: {e}")
                
                # PL97 삭제
                try:
                    msp.delete_entity(ent)
                    print(f"   ✅ PL97 엔티티 삭제 완료")
                except Exception as e:
                    print(f"   ❌ PL97 삭제 실패: {e}")
    
    # 2. PL31 레이어에서 면적 3.9 이하인 엔티티 찾아 삭제
    print("\n🔍 PL31 레이어 면적 기반 삭제...")
    pl31_to_delete = []
    
    for ent in msp:
        if ent.dxftype() in ['LWPOLYLINE', 'POLYLINE'] and ent.dxf.layer == 'PL31':
            pts = polypoints(ent)
            if len(pts) >= 3:  # 면적 계산이 가능한 경우
                area = calculate_polyline_area(pts)
                print(f"   PL31 발견: 점 {len(pts)}개, 면적 {area:.3f}")
                
                if area <= 3.9:
                    pl31_to_delete.append(ent)
                    print(f"   ✅ 삭제 대상 (면적 {area:.3f} ≤ 3.9)")
    
    # PL31 삭제
    if pl31_to_delete:
        print(f"\n🗑️ 면적 3.9 이하인 PL31 {len(pl31_to_delete)}개 삭제")
        for ent in pl31_to_delete:
            try:
                msp.delete_entity(ent)
                print(f"   ✅ PL31 삭제 완료")
            except Exception as e:
                print(f"   ❌ PL31 삭제 실패: {e}")
    else:
        print("   면적 3.9 이하인 PL31을 찾을 수 없습니다.")

def calculate_line_angle(start, end):
    """라인의 기울기를 계산 (0~360도)"""
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    
    if abs(dx) < 1e-10 and abs(dy) < 1e-10:  # 시작점과 끝점이 같은 경우
        return None
    
    # atan2는 -π ~ π 범위를 반환, 이를 0~360도로 변환
    angle_rad = math.atan2(dy, dx)
    angle_deg = math.degrees(angle_rad)
    
    # 0~360도 범위로 정규화
    if angle_deg < 0:
        angle_deg += 360
    
    return angle_deg

def process_layer3_lines_and_texts(msp):
    """레이어 3인 LINE과 TEXT 처리"""
    print("\n🔍 레이어 3 LINE 및 TEXT 처리 시작...")
    
    # ISO 도면 표준 각도들 (30도 간격)
    iso_angles = [0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330]
    angle_tolerance = 1.0  # 각도 허용 오차 (±1도)
    
    # 1. 레이어 3인 LINE 처리
    dim_count = 0
    g1_count = 0
    
    for line in msp.query('LINE'):
        if line.dxf.layer == '3':
            start = (line.dxf.start.x, line.dxf.start.y)
            end = (line.dxf.end.x, line.dxf.end.y)
            
            angle = calculate_line_angle(start, end)
            if angle is not None:
                # ISO 각도인지 확인
                is_iso_angle = False
                for iso_angle in iso_angles:
                    # 각도 차이 계산 (0도와 360도 근처 처리)
                    angle_diff = abs(angle - iso_angle)
                    if angle_diff > 180:
                        angle_diff = 360 - angle_diff
                    
                    if angle_diff <= angle_tolerance:
                        is_iso_angle = True
                        break
                
                if is_iso_angle:
                    line.dxf.layer = 'DIM'
                    dim_count += 1
                    print(f"   LINE 각도 {angle:.1f}° → DIM 레이어")
                else:
                    line.dxf.layer = 'G1'
                    g1_count += 1
                    print(f"   LINE 각도 {angle:.1f}° → G1 레이어")
    
    print(f"✅ DIM 레이어로 변경: {dim_count}개")
    print(f"✅ G1 레이어로 변경: {g1_count}개")
    
    # 2. 레이어 3이고 기울기 0인 숫자 TEXT 처리
    cp_count = 0
    
    for text in msp.query('TEXT'):
        if text.dxf.layer == '3':
            # 텍스트 내용이 숫자인지 확인
            text_content = text.dxf.text.strip()
            cleaned = text_content.replace('.', '').replace('-', '').replace(' ', '').replace(',', '')
            
            is_numeric = False
            if cleaned and (cleaned.isdigit() or 
                           (text_content.count('.') <= 1 and cleaned.isdigit())):
                is_numeric = True
            
            if is_numeric:
                # 텍스트 회전 각도 확인 (기본값 0)
                rotation = text.dxf.rotation if hasattr(text.dxf, 'rotation') else 0
                
                # 0도 또는 360도 근처인지 확인 (허용 오차 ±1도)
                if abs(rotation) <= 1.0 or abs(rotation - 360) <= 1.0:
                    text.dxf.layer = 'CP'
                    cp_count += 1
                    print(f"   숫자 TEXT '{text_content}' 기울기 {rotation:.1f}° → CP 레이어")
    
    print(f"✅ CP 레이어로 변경: {cp_count}개")

def process_red_dim_lines(msp, doc):
    """색상이 RED이고 레이어가 DIM인 LINE 처리"""
    print("\n🔍 RED 색상 DIM 레이어 LINE 처리...")
    
    # 라인타입이 없으면 생성
    if 'HIDDEN' not in doc.linetypes:
        try:
            # HIDDEN 라인타입 생성 (숨은선 패턴)
            doc.linetypes.new('HIDDEN', dxfattribs={
                'description': '- - - - - -',
                'pattern': [6.35, -3.175]  # 실선 6.35mm, 공백 3.175mm 반복
            })
            print("   HIDDEN 라인타입 생성")
        except:
            print("   ⚠️ HIDDEN 라인타입이 이미 존재하거나 생성 실패")
    
    modified_count = 0
    
    for line in msp.query('LINE'):
        if line.dxf.layer == 'DIM' and line.dxf.color == 1:  # RED = 1
            try:
                # 색상을 YELLOW로 변경
                line.dxf.color = 2  # YELLOW = 2
                
                # 레이어를 CONT로 변경
                line.dxf.layer = 'CONT'
                
                # 라인타입을 HIDDEN으로 변경
                line.dxf.linetype = 'HIDDEN'
                
                # LTSCALE을 5로 설정
                line.dxf.ltscale = 5.0
                
                modified_count += 1
                print(f"   LINE 수정: 색상 RED→YELLOW, 레이어 DIM→CONT, 라인타입→HIDDEN, LTSCALE→5")
                
            except Exception as e:
                print(f"   ❌ LINE 수정 실패: {e}")
    
    print(f"✅ 총 {modified_count}개의 LINE 수정 완료")

def process_dxf(filepath: str):
    print(f"\n📁 처리 중: {Path(filepath).name}")
    doc = ezdxf.readfile(filepath)
    msp = doc.modelspace()

    # 처리된 엔티티를 추적하기 위한 세트
    processed_entities = set()

    # 1. 레이어 1이고 색상이 RED인 LINE을 PIPE 레이어로 변경
    for line in msp.query('LINE'):
        if line.dxf.layer == '1' and line.dxf.color == 1:  # RED = 1
            line.dxf.layer = 'PIPE'
            print(f"LINE을 PIPE 레이어로 변경")

    # 2. 레이어 1이고 RED 색상의 ARC를 ELBO 레이어로 변경
    for arc in msp.query('ARC'):
        if arc.dxf.layer == '1' and arc.dxf.color == 1:  # RED = 1
            arc.dxf.layer = 'ELBO'
            print(f"ARC를 ELBO 레이어로 변경")

    # 3. PL 처리: 다양한 점 개수별 레이어 변경
    entities_to_delete = []  # 삭제할 엔티티 리스트
    
    for ent in list(msp):
        if ent.dxftype() not in ['LWPOLYLINE','POLYLINE']: 
            continue
        
        pts = polypoints(ent)
        n = len(pts)
        
        # 처리된 엔티티 추적
        processed_entities.add(id(ent))
        
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
                else:
                    ent.dxf.layer = 'PL3'
            else:
                ent.dxf.layer = 'PL3'

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

        # 6점 polyline (PL6)
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
            
        # 위에서 정의되지 않은 점 개수의 폴리라인 처리
        else:
            ent.dxf.layer = f'PL{n}'
            ent.dxf.color = 7
            print(f"정의되지 않은 {n}점 폴리라인 -> {ent.dxf.layer} 레이어")
    
    # 삭제 예정인 엔티티들을 실제로 삭제
    print(f"\n삭제 대상 엔티티 수: {len(entities_to_delete)}개")
    for idx, ent in enumerate(entities_to_delete):
        try:
            msp.delete_entity(ent)
            print(f"  [{idx+1}] INSTNO 폴리라인 삭제 완료")
        except Exception as e:
            print(f"  [{idx+1}] 삭제 실패: {e}")
    
    # 4. TEXT 레이어 지정 및 색상 설정
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
        
        # 모든 텍스트를 노란색으로 설정
        ent.dxf.color = 2

    # 5. SP3, SP7 처리 (레이어만 지정)
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

    # 6. FALL 레이어의 2점 폴리라인 색상을 흰색으로 변경
    for ent in list(msp):
        if ent.dxftype() in ['LWPOLYLINE','POLYLINE'] and ent.dxf.layer=='FALL':
            pts = polypoints(ent)
            if len(pts) == 2:
                ent.dxf.color = 7  # 흰색

    # 7. 'PT            COMPONENT              SIZE' 헤더 찾아서 STRETCH 처리
    # X값이 620보다 작은 경우에만 실행
    header_found = False
    for text in msp.query('TEXT'):
        if text.dxf.text and 'PT' in text.dxf.text and 'COMPONENT' in text.dxf.text and 'SIZE' in text.dxf.text:
            header_x = text.dxf.insert[0]
            header_y = text.dxf.insert[1]
            print(f"\n📍 HEADER 찾음: '{text.dxf.text.strip()}'")
            print(f"   위치: X={header_x:.3f}, Y={header_y:.3f}")
            
            # X값이 620보다 작은지 확인
            if header_x < 620:
                print(f"   ✅ X값({header_x:.3f})이 620보다 작으므로 STRETCH 실행")
                # 해당 범위의 엔티티들을 STRETCH (X축으로 +39mm)
                stretch_entities_in_range(msp, header_x, header_y, stretch_x=39)
            else:
                print(f"   ⚠️ X값({header_x:.3f})이 620 이상이므로 STRETCH 건너뜀")
            
            header_found = True
            break
    
    if not header_found:
        print("\n⚠️ 'PT            COMPONENT              SIZE' 헤더를 찾을 수 없습니다.")

    # 8. WELD 헤더 관련 처리
    find_and_process_weld_header(msp)

    # 9. PL97 및 PL31 처리
    process_pl97_and_pl31(msp)

    # 10. 레이어 3 LINE 및 TEXT 처리
    process_layer3_lines_and_texts(msp)

    # 11. RED 색상 DIM 레이어 LINE 처리
    process_red_dim_lines(msp, doc)

    # 12. 파일 저장
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