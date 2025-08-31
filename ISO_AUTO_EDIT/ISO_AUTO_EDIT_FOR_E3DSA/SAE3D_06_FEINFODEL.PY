import ezdxf
import tkinter as tk
from tkinter import filedialog
import math
import os
from typing import List, Tuple, Optional
import numpy as np

class DXFProcessor:
    def __init__(self):
        self.doc = None
        self.msp = None
    
    def vec3_to_tuple(self, vec) -> Tuple[float, float, float]:
        """Vec3 객체를 튜플로 안전하게 변환"""
        try:
            # Vec3 객체인 경우
            if hasattr(vec, 'x') and hasattr(vec, 'y') and hasattr(vec, 'z'):
                return (vec.x, vec.y, vec.z)
            # 이미 튜플이거나 리스트인 경우
            elif hasattr(vec, '__getitem__'):
                return (float(vec[0]), float(vec[1]), float(vec[2]) if len(vec) > 2 else 0.0)
            else:
                return (0.0, 0.0, 0.0)
        except Exception as e:
            print(f"Vec3 변환 오류: {e}")
            return (0.0, 0.0, 0.0)
        
    def select_files(self) -> List[str]:
        """파일 선택 다이얼로그를 열어 DXF 파일 선택"""
        root = tk.Tk()
        root.withdraw()
        
        file_paths = filedialog.askopenfilenames(
            title="DXF 파일 선택",
            filetypes=[("DXF files", "*.dxf"), ("All files", "*.*")]
        )
        
        return list(file_paths)
    
    def get_polyline_points(self, entity) -> List[Tuple[float, float, float]]:
        """폴리라인의 점들을 가져오기"""
        points = []
        
        if entity.dxftype() == 'LWPOLYLINE':
            points = [(p[0], p[1], 0) for p in entity.get_points('xy')]
        elif entity.dxftype() == 'POLYLINE':
            points = []
            for v in entity.vertices:
                if hasattr(v.dxf.location, 'x'):
                    # Vec3 객체인 경우
                    loc = v.dxf.location
                    points.append((loc.x, loc.y, loc.z))
                else:
                    # 튜플인 경우
                    points.append(tuple(v.dxf.location))
        
        return points
    
    def get_line_points(self, entity) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
        """라인의 시작점과 끝점 가져오기"""
        if entity.dxftype() == 'LINE':
            start = entity.dxf.start
            end = entity.dxf.end
            return ((start.x, start.y, start.z), (end.x, end.y, end.z))
        return None
    
    def distance_point_to_segment(self, point: Tuple[float, float], 
                                seg_start: Tuple[float, float], 
                                seg_end: Tuple[float, float]) -> float:
        """점과 선분 사이의 최단 거리 계산"""
        x, y = point
        x1, y1 = seg_start[:2]
        x2, y2 = seg_end[:2]
        
        # 선분의 길이 제곱
        seg_length_sq = (x2 - x1)**2 + (y2 - y1)**2
        
        if seg_length_sq == 0:
            # 선분이 점인 경우
            return math.sqrt((x - x1)**2 + (y - y1)**2)
        
        # 점을 선분에 투영
        t = ((x - x1) * (x2 - x1) + (y - y1) * (y2 - y1)) / seg_length_sq
        
        # t를 0과 1 사이로 제한 (선분의 범위 내)
        t = max(0, min(1, t))
        
        # 투영점
        proj_x = x1 + t * (x2 - x1)
        proj_y = y1 + t * (y2 - y1)
        
        # 점과 투영점 사이의 거리
        distance = math.sqrt((x - proj_x)**2 + (y - proj_y)**2)
        
        return distance
    
    def is_near_polyline(self, test_points: List[Tuple[float, float, float]], 
                        target_polyline, tolerance: float = 0.5) -> bool:
        """테스트 폴리라인이 타겟 폴리라인에 가까운지 확인"""
        target_points = self.get_polyline_points(target_polyline)
        
        if len(target_points) < 2:
            return False
        
        # 각 테스트 점이 타겟 폴리라인의 어떤 선분에 가까운지 확인
        for test_point in test_points:
            min_dist = float('inf')
            
            # 모든 연속된 점들 사이의 선분 확인
            for i in range(len(target_points) - 1):
                dist = self.distance_point_to_segment(
                    test_point[:2], 
                    target_points[i][:2], 
                    target_points[i+1][:2]
                )
                min_dist = min(min_dist, dist)
            
            # 폴리라인이 닫혀있는 경우 마지막 점과 첫 점 사이도 확인
            try:
                if hasattr(target_polyline, 'is_closed') and target_polyline.is_closed:
                    dist = self.distance_point_to_segment(
                        test_point[:2], 
                        target_points[-1][:2], 
                        target_points[0][:2]
                    )
                    min_dist = min(min_dist, dist)
            except:
                pass  # 닫힌 폴리라인 확인 실패 시 무시
            
            # 하나의 점이라도 tolerance 이내에 있으면 True
            if min_dist <= tolerance:
                return True
        
        return False
    
    def get_entity_length(self, entity) -> float:
        """엔티티의 길이 계산"""
        if entity.dxftype() == 'LINE':
            start = entity.dxf.start
            end = entity.dxf.end
            return math.sqrt((end.x-start.x)**2 + (end.y-start.y)**2 + (end.z-start.z)**2)
        
        elif entity.dxftype() in ['LWPOLYLINE', 'POLYLINE']:
            points = self.get_polyline_points(entity)
            length = 0
            for i in range(len(points) - 1):
                length += math.sqrt(
                    (points[i+1][0]-points[i][0])**2 + 
                    (points[i+1][1]-points[i][1])**2 + 
                    (points[i+1][2]-points[i][2])**2
                )
            return length
        
        return 0
    
    def is_near_point(self, point1: Tuple[float, float], 
                     point2: Tuple[float, float], 
                     tolerance: float = 0.1) -> bool:
        """두 점이 가까운지 확인"""
        dist = math.sqrt((point1[0]-point2[0])**2 + (point1[1]-point2[1])**2)
        return dist <= tolerance
    
    def get_all_points_from_entity(self, entity) -> List[Tuple[float, float, float]]:
        """엔티티에서 모든 점 가져오기"""
        if entity.dxftype() == 'LINE':
            # Vec3 객체를 튜플로 변환
            start = entity.dxf.start
            end = entity.dxf.end
            return [(start.x, start.y, start.z), (end.x, end.y, end.z)]
        elif entity.dxftype() in ['LWPOLYLINE', 'POLYLINE']:
            return self.get_polyline_points(entity)
        return []
    
    def find_text_in_area(self, center: Tuple[float, float], 
                         x_range: Tuple[float, float], 
                         y_range: Tuple[float, float],
                         text_contains: str,
                         slope_zero: bool = False) -> List:
        """특정 영역 내에서 텍스트 찾기"""
        found_texts = []
        
        for entity in self.msp:
            if entity.dxftype() in ['TEXT', 'MTEXT']:
                if hasattr(entity.dxf, 'insert'):
                    text_pos = self.vec3_to_tuple(entity.dxf.insert)
                elif hasattr(entity.dxf, 'location'):
                    text_pos = self.vec3_to_tuple(entity.dxf.location)
                else:
                    continue
                
                # 영역 확인
                if (center[0] + x_range[0] <= text_pos[0] <= center[0] + x_range[1] and
                    center[1] - y_range <= text_pos[1] <= center[1] + y_range):
                    
                    text_content = entity.dxf.text if hasattr(entity.dxf, 'text') else str(entity.text)
                    
                    # 빈 문자열이면 모든 텍스트 찾기
                    if text_contains == '' or text_contains in text_content:
                        if slope_zero:
                            # 기울기 확인 (회전각이 0인지)
                            rotation = entity.dxf.rotation if hasattr(entity.dxf, 'rotation') else 0
                            if abs(rotation) < 0.01:  # 거의 0도
                                found_texts.append(entity)
                        else:
                            found_texts.append(entity)
        
        return found_texts
    
    def extract_number_from_dn_text(self, text_entity) -> Optional[float]:
        """DN 텍스트에서 숫자 추출"""
        text_content = text_entity.dxf.text if hasattr(text_entity.dxf, 'text') else str(text_entity.text)
        
        # DN 뒤의 숫자 추출
        import re
        match = re.search(r'DN\s*(\d+)', text_content, re.IGNORECASE)
        if match:
            return float(match.group(1))
        
        # DN 앞의 숫자 추출
        match = re.search(r'(\d+)\s*DN', text_content, re.IGNORECASE)
        if match:
            return float(match.group(1))
        
        return None
    
    def process_file(self, filepath: str):
        """단일 DXF 파일 처리"""
        print(f"\n처리 중: {filepath}")
        
        # DXF 파일 열기
        self.doc = ezdxf.readfile(filepath)
        self.msp = self.doc.modelspace()
        
        # 1. VALV 레이어의 폴리라인 찾기
        valv_polylines = []
        for entity in self.msp:
            if entity.dxftype() in ['LWPOLYLINE', 'POLYLINE'] and entity.dxf.layer == 'VALV':
                # VALV 레이어를 흰색으로 변경
                entity.dxf.color = 7  # WHITE
                valv_polylines.append(entity)
        
        print(f"VALV 폴리라인 개수: {len(valv_polylines)}")
        
        # 처리할 항목들을 저장할 리스트
        ad1_entities = []
        ad2_entities = []
        ad3_entities = []
        del1_entities = []
        del2_entities = []
        del3_entities = []
        
        # 삭제할 엔티티 그룹
        entities_to_delete = []
        
        # 2. 각 VALV 폴리라인에 대해 처리
        for idx, valv_poly in enumerate(valv_polylines):
            print(f"\nVALV 폴리라인 {idx+1} 처리 중...")
            
            # GT_1 또는 ARROW 레이어의 2-3점 폴리라인 찾기
            found_arrows = []
            checked_count = 0
            
            for entity in self.msp:
                if entity.dxftype() in ['LWPOLYLINE', 'POLYLINE']:
                    if entity.dxf.layer in ['GT_1', 'ARROW']:
                        points = self.get_polyline_points(entity)
                        checked_count += 1
                        
                        # 2점 또는 3점 폴리라인인지 확인
                        if 2 <= len(points) <= 3:
                            # VALV 폴리라인에 0.5mm 내에 접하는지 확인
                            if self.is_near_polyline(points, valv_poly, 0.5):
                                found_arrows.append(entity)
                                
                                if len(found_arrows) >= 10:
                                    break
            
            print(f"  검사한 GT_1/ARROW 엔티티: {checked_count}개")
            
            print(f"찾은 화살표 개수: {len(found_arrows)}")
            
            # 디버깅: 찾은 화살표 정보 출력
            for i, arrow in enumerate(found_arrows):
                points = self.get_polyline_points(arrow)
                print(f"  화살표 {i+1}: {len(points)}점, 원래 레이어: {arrow.dxf.layer}")
            
            # 3. 찾은 화살표들을 AD1으로 변경
            for arrow in found_arrows:
                arrow.dxf.layer = 'AD1'
                arrow.dxf.color = 1  # RED
                ad1_entities.append(arrow)
                
                # 4. AD1 점에 0.1mm 내에 접하는 선분들 찾기
                arrow_points = self.get_polyline_points(arrow)
                
                for entity in self.msp:
                    if entity.dxftype() in ['LINE', 'LWPOLYLINE', 'POLYLINE']:
                        if entity in found_arrows:
                            continue
                        
                        # 엔티티의 모든 점 가져오기
                        entity_points = self.get_all_points_from_entity(entity)
                        
                        # LINE이거나 2-3점 폴리라인만 처리
                        if entity.dxftype() == 'LINE' or (2 <= len(entity_points) <= 3):
                            # AD1의 점들과 가까운지 확인
                            is_near = False
                            for arrow_point in arrow_points:
                                for entity_point in entity_points:
                                    # Vec3 객체를 튜플로 변환
                                    arrow_pt = self.vec3_to_tuple(arrow_point) if hasattr(arrow_point, 'x') else arrow_point
                                    entity_pt = self.vec3_to_tuple(entity_point) if hasattr(entity_point, 'x') else entity_point
                                    
                                    if self.is_near_point(arrow_pt[:2], entity_pt[:2], 0.1):
                                        is_near = True
                                        break
                                if is_near:
                                    break
                            
                            if is_near:
                                length = self.get_entity_length(entity)
                                
                                # 길이에 따라 분류
                                if 0.6 <= length <= 0.8:
                                    entity.dxf.layer = 'AD2'
                                    entity.dxf.color = 1  # RED
                                    ad2_entities.append(entity)
                                elif length >= 3:
                                    entity.dxf.layer = 'AD3'
                                    entity.dxf.color = 1  # RED
                                    ad3_entities.append(entity)
                
                # 5. AD3 처리
                for ad3 in [e for e in ad3_entities if e in self.msp]:
                    ad3_points = self.get_all_points_from_entity(ad3)
                    
                    if len(ad3_points) >= 2:
                        # AD1과의 거리 계산하여 AP1, AP2 결정
                        min_dist = float('inf')
                        max_dist = 0
                        ap1 = None
                        ap2 = None
                        
                        for ad3_point in ad3_points:
                            for arrow_point in arrow_points:
                                # Vec3 객체를 튜플로 변환
                                ad3_pt = self.vec3_to_tuple(ad3_point) if hasattr(ad3_point, 'x') else ad3_point
                                arrow_pt = self.vec3_to_tuple(arrow_point) if hasattr(arrow_point, 'x') else arrow_point
                                
                                dist = math.sqrt(
                                    (ad3_pt[0]-arrow_pt[0])**2 + 
                                    (ad3_pt[1]-arrow_pt[1])**2
                                )
                                if dist < min_dist:
                                    min_dist = dist
                                    ap1 = ad3_pt
                                if dist > max_dist:
                                    max_dist = dist
                                    ap2 = ad3_pt
                        
                        if ap2:
                            # AP2 근처에서 DN 텍스트 찾기
                            dn_texts = self.find_text_in_area(
                                ap2[:2], (-50, 15), 7, 'DN', slope_zero=True
                            )
                            
                            for dn_text in dn_texts:
                                del1_entities.append(dn_text)
                                
                                # DN 숫자값 확인
                                dn_value = self.extract_number_from_dn_text(dn_text)
                                if dn_value and dn_value <= 80:
                                    # 관련 엔티티들을 삭제 목록에 추가
                                    entities_to_delete.extend([arrow, ad3, dn_text])
                                    entities_to_delete.extend([e for e in ad2_entities if e in self.msp])
                            
                            # AP2 근처에서 CON 텍스트 찾기 (DN과 동일한 조건)
                            con_texts = self.find_text_in_area(
                                ap2[:2], (-50, 15), 7, 'CON', slope_zero=True
                            )
                            
                            for con_text in con_texts:
                                del2_entities.append(con_text)
                                
                                # CON 텍스트 아래 Y-10mm까지에서 문자열 찾기
                                con_pos = self.vec3_to_tuple(con_text.dxf.insert) if hasattr(con_text.dxf, 'insert') else self.vec3_to_tuple(con_text.dxf.location)
                                
                                # Y-10mm까지 범위에서 텍스트 찾기 (기울기 0)
                                below_texts = self.find_text_in_area(
                                    (con_pos[0], con_pos[1] - 5), (-5, 5), 5, '', slope_zero=True
                                )
                                
                                for below_text in below_texts:
                                    if below_text != con_text:  # CON 텍스트 자신은 제외
                                        del3_entities.append(below_text)
                                
                                # 관련 AD1, AD2, AD3, DEL2, DEL3 삭제
                                entities_to_delete.append(con_text)
                                entities_to_delete.extend(del3_entities)
                                entities_to_delete.append(arrow)
                                entities_to_delete.append(ad3)
                                entities_to_delete.extend([e for e in ad2_entities if e in self.msp])
        
        # 7. 중복 제거 후 엔티티 삭제
        entities_to_delete = list(set(entities_to_delete))
        for entity in entities_to_delete:
            try:
                self.msp.delete_entity(entity)
            except:
                pass
        
        # 8. 파일 저장
        base_name = os.path.splitext(os.path.basename(filepath))[0]
        output_path = os.path.join(os.path.dirname(filepath), f"{base_name}_FEDEL.DXF")
        
        self.doc.saveas(output_path)
        print(f"저장 완료: {output_path}")
        
        # 통계 출력
        print(f"VALV 엔티티 (흰색으로 변경): {len(valv_polylines)}")
        print(f"AD1 엔티티: {len(ad1_entities)}")
        print(f"AD2 엔티티: {len(ad2_entities)}")
        print(f"AD3 엔티티: {len(ad3_entities)}")
        print(f"삭제된 엔티티: {len(entities_to_delete)}")

def main():
    processor = DXFProcessor()
    
    # 파일 선택
    files = processor.select_files()
    
    if not files:
        print("파일이 선택되지 않았습니다.")
        return
    
    # 각 파일 처리
    for filepath in files:
        try:
            processor.process_file(filepath)
        except Exception as e:
            print(f"오류 발생 ({filepath}): {str(e)}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    main()