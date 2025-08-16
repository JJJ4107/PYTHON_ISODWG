import ezdxf
import tkinter as tk
from tkinter import filedialog
import math
import os
from typing import List, Tuple, Optional

def calculate_radius(polyline):
    """폴리라인의 반지름 계산 (원형 폴리라인 가정)"""
    try:
        # ezdxf의 explode 기능을 사용하여 폴리라인을 기본 도형으로 분해
        from ezdxf import path
        
        # 폴리라인을 Path 객체로 변환
        if hasattr(polyline, 'virtual_entities'):
            # 폴리라인을 분해하여 호(ARC)와 선분(LINE)으로 변환
            entities = list(polyline.virtual_entities())
            
            # 모든 엔티티가 호(ARC)인지 확인하고 반지름 수집
            radii = []
            centers = []
            
            for entity in entities:
                if entity.dxftype() == 'ARC':
                    radii.append(entity.dxf.radius)
                    centers.append((entity.dxf.center[0], entity.dxf.center[1]))
            
            # 모든 호가 같은 반지름과 중심을 가지는지 확인
            if radii and all(abs(r - radii[0]) < 0.1 for r in radii):
                # 모든 중심점이 같은지 확인
                if all(abs(c[0] - centers[0][0]) < 0.1 and abs(c[1] - centers[0][1]) < 0.1 for c in centers):
                    return radii[0]
        
        # 대체 방법: LWPOLYLINE의 경우 make_path 사용
        if hasattr(polyline, 'make_path'):
            p = polyline.make_path()
            if p.has_curves:
                # Path를 통해 반지름 계산 시도
                bbox = p.extents()
                if bbox:
                    width = bbox.extmax.x - bbox.extmin.x
                    height = bbox.extmax.y - bbox.extmin.y
                    # 원형인 경우 너비와 높이가 비슷해야 함
                    if abs(width - height) < 1.0:
                        # 대략적인 반지름 계산
                        radius = (width + height) / 4
                        return radius
    
    except Exception as e:
        # 예외 발생 시 기존 방법 사용
        pass
    
    # 기존 방법 (폴백)
    points = list(polyline.points())
    if len(points) < 2:
        return None
    
    # 폴리라인이 닫혀있고 점이 적은 경우 (호로 구성된 원일 가능성)
    if polyline.is_closed and len(points) <= 4:
        # 바운딩 박스로 반지름 추정
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        width = max(xs) - min(xs)
        height = max(ys) - min(ys)
        
        # 원형인지 확인 (너비와 높이가 비슷한지)
        if abs(width - height) < 1.0:
            radius = (width + height) / 4
            return radius
    
    # 많은 점으로 이루어진 경우 기존 방법 사용
    if len(points) >= 8:
        # 중심점 계산
        cx = sum(p[0] for p in points) / len(points)
        cy = sum(p[1] for p in points) / len(points)
        
        # 각 점에서 중심까지의 거리 계산
        distances = [math.sqrt((p[0] - cx)**2 + (p[1] - cy)**2) for p in points]
        avg_radius = sum(distances) / len(distances)
        
        # 모든 점이 비슷한 거리에 있는지 확인 (원형인지)
        std_dev = math.sqrt(sum((d - avg_radius)**2 for d in distances) / len(distances))
        if std_dev < 0.5:
            return avg_radius
    
    return None

def get_polyline_center(polyline):
    """폴리라인의 중심점 계산"""
    points = list(polyline.points())
    if not points:
        return None
    cx = sum(p[0] for p in points) / len(points)
    cy = sum(p[1] for p in points) / len(points)
    return (cx, cy)

def get_polyline_length(polyline):
    """폴리라인의 전체 길이 계산"""
    points = list(polyline.points())
    if len(points) < 2:
        return 0
    
    total_length = 0
    for i in range(len(points) - 1):
        dx = points[i+1][0] - points[i][0]
        dy = points[i+1][1] - points[i][1]
        total_length += math.sqrt(dx**2 + dy**2)
    
    # 폐곡선인 경우 마지막 점과 첫 점 연결
    if polyline.is_closed:
        dx = points[0][0] - points[-1][0]
        dy = points[0][1] - points[-1][1]
        total_length += math.sqrt(dx**2 + dy**2)
    
    return total_length

def distance_between_points(p1, p2):
    """두 점 사이의 거리 계산"""
    return math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)

def is_within_range(point, center, range_val):
    """점이 중심에서 특정 범위 내에 있는지 확인"""
    return distance_between_points(point, center) <= range_val

def get_line_length(line):
    """LINE 엔티티의 길이 계산"""
    start = line.dxf.start
    end = line.dxf.end
    return distance_between_points(start[:2], end[:2])

def find_closest_point_to_polyline(points, polyline):
    """폴리라인에 가장 가까운 점 찾기"""
    poly_points = list(polyline.points())
    min_dist = float('inf')
    closest_point = None
    
    for point in points:
        for poly_point in poly_points:
            dist = distance_between_points(point[:2], poly_point[:2])
            if dist < min_dist:
                min_dist = dist
                closest_point = point
    
    return closest_point

def find_farthest_point_from_polyline(points, polyline):
    """폴리라인에서 가장 먼 점 찾기"""
    poly_points = list(polyline.points())
    max_dist = 0
    farthest_point = None
    
    for point in points:
        min_dist_to_poly = float('inf')
        for poly_point in poly_points:
            dist = distance_between_points(point[:2], poly_point[:2])
            min_dist_to_poly = min(min_dist_to_poly, dist)
        
        if min_dist_to_poly > max_dist:
            max_dist = min_dist_to_poly
            farthest_point = point
    
    return farthest_point

def process_dxf_file(filepath):
    """DXF 파일 처리"""
    try:
        # DXF 파일 열기
        doc = ezdxf.readfile(filepath)
        msp = doc.modelspace()
        
        # 삭제할 엔티티들을 저장할 리스트
        entities_to_delete = []
        
        # 1. INST 찾기: 반지름 3~5mm, 레이어 GT_1인 폴리라인
        inst_entities = []
        for entity in msp:
            if entity.dxftype() in ['POLYLINE', 'LWPOLYLINE'] and entity.dxf.layer == 'GT_1':
                radius = calculate_radius(entity)
                if radius and 3 <= radius <= 5:
                    # 레이어를 INST로 변경하고 색상을 빨간색으로
                    entity.dxf.layer = 'INST'
                    entity.dxf.color = 1  # 빨간색
                    inst_entities.append(entity)
                    entities_to_delete.append(entity)
        
        print(f"INST 엔티티 찾음: {len(inst_entities)}개")
        
        # 2. AD1 찾기: INST 중심에서 5mm 범위 내, 3점, GT_1 레이어, 길이 5 이하
        ad1_entities = []
        for inst in inst_entities:
            inst_center = get_polyline_center(inst)
            if not inst_center:
                continue
            
            for entity in msp:
                if entity.dxftype() in ['POLYLINE', 'LWPOLYLINE'] and entity.dxf.layer == 'GT_1':
                    points = list(entity.points())
                    if len(points) == 3:
                        # 모든 점이 INST 중심에서 5mm 범위 내에 있는지 확인
                        if all(is_within_range(p[:2], inst_center, 5) for p in points):
                            length = get_polyline_length(entity)
                            if length <= 5:
                                entity.dxf.layer = 'AD1'
                                ad1_entities.append(entity)
                                entities_to_delete.append(entity)
        
        print(f"AD1 엔티티 찾음: {len(ad1_entities)}개")
        
        # 3. AD2 찾기: AD1 점에서 0.1mm 내, 길이 1mm 이하, 레이어 ARROW인 LINE
        ad2_entities = []
        for ad1 in ad1_entities:
            ad1_points = list(ad1.points())
            
            for entity in msp:
                if entity.dxftype() == 'LINE' and entity.dxf.layer == 'ARROW':
                    line_length = get_line_length(entity)
                    if line_length <= 1:
                        start_point = entity.dxf.start[:2]
                        end_point = entity.dxf.end[:2]
                        
                        # AD1의 점들과 비교
                        for ad1_point in ad1_points:
                            if (distance_between_points(start_point, ad1_point[:2]) <= 0.1 or
                                distance_between_points(end_point, ad1_point[:2]) <= 0.1):
                                entity.dxf.layer = 'AD2'
                                ad2_entities.append(entity)
                                entities_to_delete.append(entity)
                                break
        
        print(f"AD2 엔티티 찾음: {len(ad2_entities)}개")
        
        # 4. AD3 찾기: AD1 점에서 0.1mm 내, 레이어 PL2인 폴리라인 (최대 2개)
        ad3_entities = []
        for ad1 in ad1_entities:
            ad1_points = list(ad1.points())
            found_count = 0
            
            for entity in msp:
                if found_count >= 2:
                    break
                    
                if entity.dxftype() in ['POLYLINE', 'LWPOLYLINE'] and entity.dxf.layer == 'PL2':
                    entity_points = list(entity.points())
                    
                    # AD1의 점들과 비교
                    for ad1_point in ad1_points:
                        found = False
                        for ep in entity_points:
                            if distance_between_points(ep[:2], ad1_point[:2]) <= 0.1:
                                entity.dxf.layer = 'AD3'
                                ad3_entities.append(entity)
                                entities_to_delete.append(entity)
                                found_count += 1
                                found = True
                                break
                        if found:
                            break
        
        print(f"AD3 엔티티 찾음: {len(ad3_entities)}개")
        
        # 5. AP1, AP2 찾기 및 DEL1 찾기
        del1_entities = []
        if ad3_entities and ad1_entities:
            for ad3 in ad3_entities:
                ad3_points = list(ad3.points())
                
                # AD1에 가장 가까운 점(AP1)과 가장 먼 점(AP2) 찾기
                ap1 = find_closest_point_to_polyline(ad3_points, ad1_entities[0])
                ap2 = find_farthest_point_from_polyline(ad3_points, ad1_entities[0])
                
                if ap2:
                    # AP2에서 범위 내 TEXT 찾기
                    for entity in msp:
                        if entity.dxftype() == 'TEXT':
                            text_pos = entity.dxf.insert[:2]
                            
                            # 위치 조건 확인
                            x_ok = ap2[0] - 60 <= text_pos[0] <= ap2[0] + 15
                            y_ok = ap2[1] - 7 <= text_pos[1] <= ap2[1] + 7
                            
                            if x_ok and y_ok:
                                # 기울기가 0인지 확인 (rotation이 0)
                                if abs(entity.dxf.rotation) < 0.01:
                                    # 텍스트 내용 확인
                                    text_content = entity.dxf.text.upper()
                                    keywords = ['TT', 'TI', 'TE', 'TP', 'PI', 'PP', 'PE', 'PT']
                                    if any(kw in text_content for kw in keywords):
                                        del1_entities.append(entity)
                                        entities_to_delete.append(entity)
        
        print(f"DEL1 엔티티 찾음: {len(del1_entities)}개")
        
        # 6. 엔티티 삭제
        for entity in entities_to_delete:
            try:
                msp.delete_entity(entity)
            except:
                pass
        
        # 7. 파일 저장
        base_name = os.path.splitext(os.path.basename(filepath))[0]
        dir_name = os.path.dirname(filepath)
        new_filename = os.path.join(dir_name, f"{base_name}_INDEL.dxf")
        
        doc.saveas(new_filename)
        print(f"파일 저장 완료: {new_filename}")
        
        return True
        
    except Exception as e:
        print(f"오류 발생: {str(e)}")
        return False

def main():
    """메인 함수"""
    # 파일 선택 대화상자
    root = tk.Tk()
    root.withdraw()
    
    filepaths = filedialog.askopenfilenames(
        title="DXF 파일 선택",
        filetypes=[("DXF files", "*.dxf"), ("All files", "*.*")]
    )
    
    if not filepaths:
        print("파일이 선택되지 않았습니다.")
        return
    
    # 선택된 파일들 처리
    for filepath in filepaths:
        print(f"\n처리 중: {filepath}")
        success = process_dxf_file(filepath)
        if success:
            print(f"성공적으로 처리됨: {filepath}")
        else:
            print(f"처리 실패: {filepath}")

if __name__ == "__main__":
    main()