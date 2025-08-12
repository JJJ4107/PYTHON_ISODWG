import ezdxf
from ezdxf.entities import Line, Polyline, LWPolyline, Text
import tkinter as tk
from tkinter import filedialog
import math
import numpy as np
from typing import List, Tuple, Optional

class DXFAnalyzer:
    def __init__(self):
        self.docs = []
        self.instno_circles = []
        
    def select_files(self):
        """DXF 파일 선택 대화상자"""
        root = tk.Tk()
        root.withdraw()
        file_paths = filedialog.askopenfilenames(
            title="DXF 파일 선택",
            filetypes=[("DXF files", "*.dxf"), ("All files", "*.*")]
        )
        return file_paths
    
    def load_dxf_files(self, file_paths):
        """선택된 DXF 파일들을 로드"""
        for path in file_paths:
            try:
                doc = ezdxf.readfile(path)
                self.docs.append(doc)
                print(f"파일 로드 완료: {path}")
            except Exception as e:
                print(f"파일 로드 실패 {path}: {e}")
    
    def find_instno_polylines(self):
        """INSTNO 레이어의 3점 폴리라인 찾기"""
        for doc in self.docs:
            msp = doc.modelspace()
            for entity in msp:
                if entity.dxf.layer == "INSTNO":
                    if isinstance(entity, (Polyline, LWPolyline)):
                        points = list(entity.points())
                        if len(points) == 3:
                            # 3점 폴리라인에서 원의 중심과 반지름 계산
                            center, radius = self.calculate_circle_from_3points(points)
                            if center and radius:
                                self.instno_circles.append({
                                    'entity': entity,
                                    'center': center,
                                    'radius': radius,
                                    'points': points
                                })
    
    def calculate_circle_from_3points(self, points):
        """3점으로부터 원의 중심과 반지름 계산"""
        if len(points) < 3:
            return None, None
        
        p1, p2, p3 = points[:3]
        
        # 2D 좌표만 사용
        x1, y1 = p1[0], p1[1]
        x2, y2 = p2[0], p2[1]
        x3, y3 = p3[0], p3[1]
        
        # 원의 중심 계산
        d = 2 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
        if abs(d) < 1e-10:
            return None, None
        
        ux = ((x1**2 + y1**2) * (y2 - y3) + (x2**2 + y2**2) * (y3 - y1) + (x3**2 + y3**2) * (y1 - y2)) / d
        uy = ((x1**2 + y1**2) * (x3 - x2) + (x2**2 + y2**2) * (x1 - x3) + (x3**2 + y3**2) * (x2 - x1)) / d
        
        # 반지름 계산
        radius = math.sqrt((x1 - ux)**2 + (y1 - uy)**2)
        
        return (ux, uy), radius
    
    def distance_2d(self, p1, p2):
        """2D 거리 계산"""
        return math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)
    
    def line_length(self, line):
        """라인의 길이 계산"""
        start = line.dxf.start
        end = line.dxf.end
        return self.distance_2d(start, end)
    
    def find_near_circle(self, center, radius, entity, tolerance=5.0):
        """원 둘레 근처에 있는지 확인"""
        if isinstance(entity, Line):
            start = entity.dxf.start
            end = entity.dxf.end
            # 라인의 중점
            mid = ((start[0] + end[0])/2, (start[1] + end[1])/2)
            dist_from_center = self.distance_2d(center, mid)
            dist_from_circle = abs(dist_from_center - radius)
            return dist_from_circle <= tolerance
        return False
    
    def lines_intersect(self, line1, line2):
        """두 라인이 교차하는지 확인"""
        # 간단한 교차 검사 (2D)
        x1, y1 = line1.dxf.start[0], line1.dxf.start[1]
        x2, y2 = line1.dxf.end[0], line1.dxf.end[1]
        x3, y3 = line2.dxf.start[0], line2.dxf.start[1]
        x4, y4 = line2.dxf.end[0], line2.dxf.end[1]
        
        denom = (x1-x2)*(y3-y4) - (y1-y2)*(x3-x4)
        if abs(denom) < 1e-10:
            return False
        
        t = ((x1-x3)*(y3-y4) - (y1-y3)*(x3-x4)) / denom
        u = -((x1-x2)*(y1-y3) - (y1-y2)*(x1-x3)) / denom
        
        return 0 <= t <= 1 and 0 <= u <= 1
    
    def polyline_length(self, entity):
        """폴리라인의 총 길이 계산"""
        points = list(entity.points())
        total_length = 0
        for i in range(len(points)-1):
            total_length += self.distance_2d(points[i], points[i+1])
        return total_length
    
    def process_instno_circle(self, circle_data):
        """각 INSTNO 원에 대한 처리"""
        doc = None
        for d in self.docs:
            if circle_data['entity'] in d.modelspace():
                doc = d
                break
        
        if not doc:
            return
        
        msp = doc.modelspace()
        center = circle_data['center']
        radius = circle_data['radius']
        
        # A1 찾기: 원 둘레 5mm 이내, 길이 1mm 이하 LINE
        A1 = None
        for entity in msp:
            if isinstance(entity, Line):
                if self.line_length(entity) <= 1.0:
                    if self.find_near_circle(center, radius, entity, 5.0):
                        A1 = entity
                        break
        
        if not A1:
            print("A1을 찾을 수 없습니다.")
            return
        
        # A2 찾기: A1과 교차하는 2점 폴리라인
        A2 = None
        for entity in msp:
            if isinstance(entity, (Polyline, LWPolyline)):
                points = list(entity.points())
                if len(points) == 2:
                    # 폴리라인을 라인으로 변환하여 교차 검사
                    temp_line = Line()
                    temp_line.dxf.start = points[0]
                    temp_line.dxf.end = points[1]
                    if self.lines_intersect(A1, temp_line):
                        A2 = entity
                        break
        
        if not A2:
            print("A2를 찾을 수 없습니다.")
            return
        
        # A3 찾기: A1에 접하고 3점, 길이 합 5mm 이하
        A3 = None
        for entity in msp:
            if isinstance(entity, (Polyline, LWPolyline)):
                points = list(entity.points())
                if len(points) == 3:
                    total_length = self.polyline_length(entity)
                    if total_length <= 5.0:
                        # A1과의 접촉 확인 (간단히 거리로 확인)
                        a1_mid = ((A1.dxf.start[0] + A1.dxf.end[0])/2, 
                                 (A1.dxf.start[1] + A1.dxf.end[1])/2)
                        min_dist = min([self.distance_2d(a1_mid, p) for p in points])
                        if min_dist <= 1.0:  # 접촉 판정
                            A3 = entity
                            break
        
        if not A3:
            print("A3를 찾을 수 없습니다.")
            return
        
        # ALL 그룹
        ALL = [A1, A2, A3]
        
        # TBOX 찾기: A2의 먼 점에서 5mm 이내, 5점, 거리합 13.5-14.5mm
        a2_points = list(A2.points())
        a1_mid = ((A1.dxf.start[0] + A1.dxf.end[0])/2, 
                  (A1.dxf.start[1] + A1.dxf.end[1])/2)
        
        # A2의 두 점 중 A1에서 더 먼 점 찾기
        far_point = a2_points[0] if self.distance_2d(a1_mid, a2_points[0]) > self.distance_2d(a1_mid, a2_points[1]) else a2_points[1]
        
        TBOX = None
        for entity in msp:
            if isinstance(entity, (Polyline, LWPolyline)):
                points = list(entity.points())
                if len(points) == 5:
                    total_length = self.polyline_length(entity)
                    if 13.5 <= total_length <= 14.5:
                        # far_point에서 5mm 이내인지 확인
                        min_dist = min([self.distance_2d(far_point, p) for p in points])
                        if min_dist <= 5.0:
                            TBOX = entity
                            break
        
        # ITAG 찾기: ALL 그룹 점에서 3mm 이내, 기울기 0, 숫자 11 이하
        ITAG = None
        all_points = []
        for e in ALL:
            if isinstance(e, Line):
                all_points.extend([e.dxf.start, e.dxf.end])
            else:
                all_points.extend(list(e.points()))
        
        for entity in msp:
            if isinstance(entity, Text):
                try:
                    text_value = float(entity.dxf.text)
                    if text_value <= 11:
                        # 기울기 0 확인 (rotation이 0인지)
                        if abs(entity.dxf.rotation) < 0.1:
                            # ALL 그룹 점들과의 거리 확인
                            text_pos = entity.dxf.insert
                            min_dist = min([self.distance_2d(text_pos, p) for p in all_points])
                            if min_dist <= 3.0:
                                ITAG = entity
                                break
                except:
                    continue
        
        # TPOINT 찾기: INSTNO를 접하는 다른 2점 폴리라인
        TPOINT = None
        for entity in msp:
            if isinstance(entity, (Polyline, LWPolyline)) and entity != A2:
                points = list(entity.points())
                if len(points) == 2:
                    # 원과의 접촉 확인
                    min_dist = min([abs(self.distance_2d(center, p) - radius) for p in points])
                    if min_dist <= 1.0:
                        TPOINT = entity
                        break
        
        if not TPOINT:
            print("TPOINT를 찾을 수 없습니다.")
            return
        
        # FTP 계산: TPOINT의 180도 반대편 점
        tpoint_points = list(TPOINT.points())
        tpoint_mid = ((tpoint_points[0][0] + tpoint_points[1][0])/2,
                      (tpoint_points[0][1] + tpoint_points[1][1])/2)
        
        # 중심에서 tpoint_mid로의 벡터의 반대 방향
        vec_x = tpoint_mid[0] - center[0]
        vec_y = tpoint_mid[1] - center[1]
        
        # 180도 반대편 점 (원 위의 점)
        FTP = (center[0] - vec_x, center[1] - vec_y)
        
        # ITAG 이동
        if ITAG:
            # ITAG의 현재 위치
            current_pos = ITAG.dxf.insert
            
            # FTP로 이동
            offset_x = FTP[0] - current_pos[0]
            offset_y = FTP[1] - current_pos[1]
            
            ITAG.dxf.insert = (FTP[0], FTP[1], current_pos[2] if len(current_pos) > 2 else 0)
        
        # 색상 변경: CYAN (색상 인덱스 4)
        for entity in ALL:
            entity.dxf.color = 4
        
        if TPOINT:
            TPOINT.dxf.color = 4
        
        if ITAG:
            ITAG.dxf.color = 4
        
        print("처리 완료")
    
    def run(self):
        """메인 실행 함수"""
        # 파일 선택
        file_paths = self.select_files()
        if not file_paths:
            print("파일이 선택되지 않았습니다.")
            return
        
        # DXF 파일 로드
        self.load_dxf_files(file_paths)
        
        # INSTNO 폴리라인 찾기
        self.find_instno_polylines()
        print(f"찾은 INSTNO 원: {len(self.instno_circles)}개")
        
        # 각 INSTNO 원에 대해 처리
        for i, circle_data in enumerate(self.instno_circles):
            print(f"\n원 {i+1} 처리 중...")
            self.process_instno_circle(circle_data)
        
        # 수정된 파일 저장
        for i, doc in enumerate(self.docs):
            output_path = f"modified_{i}.dxf"
            doc.saveas(output_path)
            print(f"저장 완료: {output_path}")

if __name__ == "__main__":
    analyzer = DXFAnalyzer()
    analyzer.run()