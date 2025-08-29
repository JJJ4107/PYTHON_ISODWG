import ezdxf
import os
import sys
import math

def process_dxf_files():
    """DXF 파일 선택 및 처리 메인 함수"""
    # Command line arguments로 파일 경로 받기
    if len(sys.argv) < 2:
        sys.exit(1)
    
    file_paths = sys.argv[1:]
    
    # 선택된 각 파일 처리
    for file_path in file_paths:
        try:
            process_single_dxf(file_path)
        except Exception as e:
            pass

def process_single_dxf(file_path):
    """단일 DXF 파일 처리"""
    # DXF 파일 읽기
    doc = ezdxf.readfile(file_path)
    msp = doc.modelspace()
    
    # DXF 버전 확인
    dxf_version = doc.dxfversion
    
    # 파일의 모든 레이어 확인
    all_layers = set()
    for entity in msp:
        if hasattr(entity.dxf, 'layer'):
            all_layers.add(entity.dxf.layer)
    
    # PIPE, TEE, ELBO가 포함된 레이어 이름 찾기
    pipe_tee_elbo_layers = set()
    for entity in msp:
        if hasattr(entity.dxf, 'layer'):
            layer_upper = entity.dxf.layer.upper()
            if 'PIPE' in layer_upper or 'TEE' in layer_upper or 'ELBO' in layer_upper:
                pipe_tee_elbo_layers.add(entity.dxf.layer)
    
    # 삭제할 엔티티를 저장할 리스트
    entities_to_delete = []
    
    # SUPP 레이어의 LINE을 변환할 리스트
    supp_lines_to_convert = []
    
    # 모든 엔티티 검토
    for entity in msp:
        # SUPP 레이어의 LINE 찾기 (SUPP가 포함된 모든 레이어)
        if entity.dxftype() == 'LINE' and hasattr(entity.dxf, 'layer'):
            layer_upper = entity.dxf.layer.upper()
            if 'SUPP' in layer_upper:  # 정확한 일치가 아닌 포함 여부 확인
                supp_lines_to_convert.append(entity)
                continue
        
        # 엔티티의 위치 확인
        if hasattr(entity, 'dxf'):
            # 점 위치 가져오기
            x, y = None, None
            
            # 엔티티 타입에 따라 좌표 가져오기
            if entity.dxftype() == 'TEXT' or entity.dxftype() == 'MTEXT':
                if hasattr(entity.dxf, 'insert'):
                    x, y = entity.dxf.insert[0], entity.dxf.insert[1]
            elif hasattr(entity.dxf, 'location'):
                x, y = entity.dxf.location[0], entity.dxf.location[1]
            elif hasattr(entity.dxf, 'center'):
                x, y = entity.dxf.center[0], entity.dxf.center[1]
            elif entity.dxftype() == 'LINE':
                # LINE의 경우 시작점 사용
                if hasattr(entity.dxf, 'start'):
                    x, y = entity.dxf.start[0], entity.dxf.start[1]
            elif entity.dxftype() == 'POLYLINE' or entity.dxftype() == 'LWPOLYLINE':
                # POLYLINE의 경우 첫 번째 정점 사용
                try:
                    if entity.dxftype() == 'LWPOLYLINE':
                        points = list(entity.get_points())
                        if points:
                            x, y = points[0][0], points[0][1]
                    else:
                        vertices = list(entity.vertices)
                        if vertices:
                            x, y = vertices[0].dxf.location[0], vertices[0].dxf.location[1]
                except:
                    pass
            
            # 조건 1: X 0~50, Y 550~590 범위에서 PL16, PL8 레이어 및 TEXT 'N' 삭제
            if x is not None and y is not None:
                if 0 <= x <= 50 and 550 <= y <= 590:
                    # PL16 또는 PL8 레이어 확인
                    if hasattr(entity.dxf, 'layer'):
                        if entity.dxf.layer in ['PL16', 'PL8']:
                            entities_to_delete.append(entity)
                            continue
                    
                    # TEXT 'N' 확인
                    if entity.dxftype() in ['TEXT', 'MTEXT']:
                        if hasattr(entity.dxf, 'text') and entity.dxf.text.strip() == 'N':
                            entities_to_delete.append(entity)
                            continue
                
                # 조건 2: X 820~860, Y 0~20 범위에서 PL4 레이어 삭제
                if 820 <= x <= 860 and 0 <= y <= 20:
                    if hasattr(entity.dxf, 'layer'):
                        if entity.dxf.layer == 'PL4':
                            entities_to_delete.append(entity)
    
    # 엔티티 삭제
    for entity in entities_to_delete:
        try:
            msp.delete_entity(entity)
        except:
            pass
    
    # SUPP 레이어의 LINE을 POLYLINE으로 변환
    converted_count = 0
    for line in supp_lines_to_convert:
        try:
            # LINE의 시작점과 끝점 가져오기
            start = line.dxf.start
            end = line.dxf.end
            
            # DXF 버전에 따라 적절한 폴리라인 생성
            try:
                # R2000 이상에서는 LWPOLYLINE 사용
                polyline = msp.add_lwpolyline([(start[0], start[1]), (end[0], end[1])])
                polyline.dxf.const_width = 0.3
            except:
                # R2000 미만에서는 POLYLINE 사용
                polyline = msp.add_polyline2d([(start[0], start[1]), (end[0], end[1])])
                # POLYLINE의 경우 각 정점에 폭 설정
                for vertex in polyline.vertices:
                    vertex.dxf.start_width = 0.3
                    vertex.dxf.end_width = 0.3
            
            # 속성 복사
            polyline.dxf.layer = line.dxf.layer
            if hasattr(line.dxf, 'color'):
                polyline.dxf.color = line.dxf.color
            
            # 기존 LINE 삭제
            msp.delete_entity(line)
            converted_count += 1
            
        except Exception as e:
            pass
    
    # 변환 후 SUPP 레이어의 폴리라인 확인
    supp_polylines = 0
    for entity in msp:
        if entity.dxftype() in ['POLYLINE', 'LWPOLYLINE'] and hasattr(entity.dxf, 'layer'):
            if 'SUPP' in entity.dxf.layer.upper():
                supp_polylines += 1
    
    # 색상 변경 작업 (ACE01 레이어 변경 전에 수행)
    # AutoCAD 색상 인덱스: RED=1, YELLOW=2, GREEN=3, CYAN=4, BLUE=5, MAGENTA=6, WHITE=7
    for entity in msp:
        try:
            if hasattr(entity.dxf, 'color'):
                current_color = entity.dxf.color
                current_layer = entity.dxf.layer if hasattr(entity.dxf, 'layer') else ''
                
                # ELBO 레이어의 모든 객체를 BLUE로 변경 (최우선)
                if current_layer == 'ELBO':
                    entity.dxf.color = 5  # BLUE
                
                # ARROW 레이어의 모든 객체를 흰색으로 변경
                elif current_layer == 'ARROW':
                    entity.dxf.color = 7  # WHITE
                
                # PIPE, TEE, ELBO가 레이어 이름에 포함된 폴리라인을 BLUE로 변경
                elif current_layer in pipe_tee_elbo_layers:
                    if entity.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
                        entity.dxf.color = 5  # BLUE
                
                # AD1, G1 레이어의 CYAN이나 GREEN 폴리라인을 흰색으로
                elif current_layer in ['AD1', 'G1']:
                    if entity.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
                        if current_color == 4 or current_color == 3:  # CYAN(4) or GREEN(3)
                            entity.dxf.color = 7  # WHITE
                
                # 1. 모든 CYAN TEXT를 YELLOW로 변경
                if entity.dxftype() in ['TEXT', 'MTEXT'] and current_color == 4:
                    entity.dxf.color = 2  # CYAN(4) -> YELLOW(2)
                
                # 2. GT-1 또는 GT_1 레이어의 YELLOW 폴리라인 중 길이가 5 이하인 것은 흰색으로
                elif (current_layer == 'GT-1' or current_layer == 'GT_1') and current_color == 2:
                    if entity.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
                        # 폴리라인 길이 계산
                        length = 0
                        points_count = 0
                        try:
                            if entity.dxftype() == 'LWPOLYLINE':
                                points = list(entity.get_points())
                                points_count = len(points)
                                for i in range(len(points) - 1):
                                    dx = points[i+1][0] - points[i][0]
                                    dy = points[i+1][1] - points[i][1]
                                    length += math.sqrt(dx**2 + dy**2)
                            else:
                                vertices = list(entity.vertices)
                                points_count = len(vertices)
                                for i in range(len(vertices) - 1):
                                    dx = vertices[i+1].dxf.location[0] - vertices[i].dxf.location[0]
                                    dy = vertices[i+1].dxf.location[1] - vertices[i].dxf.location[1]
                                    length += math.sqrt(dx**2 + dy**2)
                            
                            # 길이가 5 이하이거나 3점 폴리라인인 경우 흰색으로 변경
                            if length <= 5 or points_count == 3:
                                entity.dxf.color = 7  # WHITE
                        except:
                            pass
                
                # 2-1. GT-1 또는 GT_1 레이어의 모든 3점 폴리라인을 흰색으로 (색상 무관)
                elif current_layer == 'GT-1' or current_layer == 'GT_1':
                    if entity.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
                        points_count = 0
                        try:
                            if entity.dxftype() == 'LWPOLYLINE':
                                points = list(entity.get_points())
                                points_count = len(points)
                            else:
                                vertices = list(entity.vertices)
                                points_count = len(vertices)
                            
                            # 3점 폴리라인인 경우 흰색으로 변경
                            if points_count == 3:
                                entity.dxf.color = 7  # WHITE
                        except:
                            pass
                
                # 3. PL2 레이어이고 색상이 CYAN 또는 GREEN인 폴리라인은 흰색으로
                elif current_layer == 'PL2' and (current_color == 4 or current_color == 3):
                    if entity.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
                        entity.dxf.color = 7  # WHITE
                
                # 4. PL2 레이어의 모든 GREEN 색상을 흰색으로 (폴리라인뿐만 아니라 모든 객체)
                elif current_layer == 'PL2' and current_color == 3:
                    entity.dxf.color = 7  # WHITE
                    
        except Exception as e:
            pass
    
    # SFW 레이어 관련 복잡한 작업
    sfw_points = []  # SFW 레이어의 점들
    pl18_to_delete = []  # SFW 점 주변 10mm 내의 PL18 레이어 (삭제 대상)
    del2_entities = []  # DEL2: 7mm 이하의 2점 PL2 폴리라인
    del3_entities = []  # DEL3: 3점 폴리라인과 LINE
    ad1_entities = []   # AD1: 7mm 이상 폴리라인
    del4_entities = []  # DEL4: AD1 끝점 50mm 내의 'CON' 포함 문자
    del5_entities = []  # DEL5: DEL4 아래 8mm 내의 문자
    sfw_entities = []   # SFW 레이어의 모든 엔티티 (유지됨)
    
    # 1단계: SFW 레이어의 점 수집 및 SFW 엔티티 수집
    for entity in msp:
        if hasattr(entity.dxf, 'layer'):
            layer_name = entity.dxf.layer.upper()  # 대소문자 구분 없이 비교
            if layer_name == 'SFW':
                sfw_entities.append(entity)
                # 점의 좌표 수집
                if entity.dxftype() == 'POINT':
                    if hasattr(entity.dxf, 'location'):
                        sfw_points.append((entity.dxf.location[0], entity.dxf.location[1]))
                elif entity.dxftype() in ['TEXT', 'MTEXT']:
                    if hasattr(entity.dxf, 'insert'):
                        sfw_points.append((entity.dxf.insert[0], entity.dxf.insert[1]))
                elif entity.dxftype() in ['CIRCLE', 'ARC']:
                    if hasattr(entity.dxf, 'center'):
                        sfw_points.append((entity.dxf.center[0], entity.dxf.center[1]))
                elif entity.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
                    # 폴리라인의 모든 점을 SFW 점으로 추가
                    if entity.dxftype() == 'LWPOLYLINE':
                        points = list(entity.get_points())
                        for p in points:
                            sfw_points.append((p[0], p[1]))
    
    # 2단계: 각 SFW 점 주변 10mm 범위에서 엔티티 검색 (2mm에서 10mm로 변경)
    for sfw_x, sfw_y in sfw_points:
        for entity in msp:
            try:
                # 엔티티의 위치 확인
                x, y = None, None
                
                if entity.dxftype() in ['TEXT', 'MTEXT']:
                    if hasattr(entity.dxf, 'insert'):
                        x, y = entity.dxf.insert[0], entity.dxf.insert[1]
                elif entity.dxftype() == 'LINE':
                    if hasattr(entity.dxf, 'start'):
                        x, y = entity.dxf.start[0], entity.dxf.start[1]
                elif entity.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
                    # 폴리라인의 첫 점 사용
                    if entity.dxftype() == 'LWPOLYLINE':
                        points = list(entity.get_points())
                        if points:
                            x, y = points[0][0], points[0][1]
                    else:
                        vertices = list(entity.vertices)
                        if vertices:
                            x, y = vertices[0].dxf.location[0], vertices[0].dxf.location[1]
                
                if x is not None and y is not None:
                    # SFW 점으로부터 10mm 범위 내인지 확인 (2mm에서 10mm로 변경)
                    if abs(x - sfw_x) <= 100 and abs(y - sfw_y) <= 100:
                        current_layer = entity.dxf.layer if hasattr(entity.dxf, 'layer') else ''
                        
                        # PL18 레이어는 삭제 대상으로 추가
                        if current_layer.upper() == 'PL18':
                            pl18_to_delete.append(entity)
                        
                        # 2mm 범위 내인 경우에만 다른 처리
                        if abs(x - sfw_x) <= 2 and abs(y - sfw_y) <= 2:
                            # 폴리라인 처리
                            if entity.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
                                points_list = []
                                length = 0
                                
                                if entity.dxftype() == 'LWPOLYLINE':
                                    points_list = list(entity.get_points())
                                else:
                                    vertices = list(entity.vertices)
                                    points_list = [(v.dxf.location[0], v.dxf.location[1]) for v in vertices]
                                
                                # 폴리라인 길이 계산
                                for i in range(len(points_list) - 1):
                                    dx = points_list[i+1][0] - points_list[i][0]
                                    dy = points_list[i+1][1] - points_list[i][1]
                                    length += math.sqrt(dx**2 + dy**2)
                                
                                # DEL2: 7mm 이하의 2점 PL2 폴리라인
                                if len(points_list) == 2 and length <= 7 and current_layer.upper() == 'PL2':
                                    del2_entities.append(entity)
                                
                                # DEL3: 3점 폴리라인
                                elif len(points_list) == 3:
                                    del3_entities.append(entity)
                                
                                # AD1: 7mm 이상 폴리라인
                                elif length >= 7:
                                    ad1_entities.append(entity)
                            
                            # DEL3: LINE
                            elif entity.dxftype() == 'LINE':
                                del3_entities.append(entity)
                            
            except:
                pass
    
    # 3단계: AD1 끝점에서 50mm 범위의 'CON' 포함 문자 찾기
    for ad1_entity in ad1_entities:
        try:
            # AD1 폴리라인의 끝점 찾기
            end_point = None
            if ad1_entity.dxftype() == 'LWPOLYLINE':
                points = list(ad1_entity.get_points())
                if points:
                    end_point = (points[-1][0], points[-1][1])
            else:
                vertices = list(ad1_entity.vertices)
                if vertices:
                    end_point = (vertices[-1].dxf.location[0], vertices[-1].dxf.location[1])
            
            if end_point:
                # 끝점에서 50mm 범위의 텍스트 검색
                for entity in msp:
                    if entity.dxftype() in ['TEXT', 'MTEXT']:
                        if hasattr(entity.dxf, 'insert'):
                            tx, ty = entity.dxf.insert[0], entity.dxf.insert[1]
                            distance = math.sqrt((tx - end_point[0])**2 + (ty - end_point[1])**2)
                            
                            if distance <= 50:
                                if hasattr(entity.dxf, 'text'):
                                    if 'CON' in entity.dxf.text.upper():
                                        del4_entities.append(entity)
        except:
            pass
    
    # 4단계: DEL4 아래 8mm 내의 문자 찾기
    for del4_entity in del4_entities:
        try:
            if hasattr(del4_entity.dxf, 'insert'):
                del4_x, del4_y = del4_entity.dxf.insert[0], del4_entity.dxf.insert[1]
                
                for entity in msp:
                    if entity.dxftype() in ['TEXT', 'MTEXT'] and entity not in del4_entities:
                        if hasattr(entity.dxf, 'insert'):
                            tx, ty = entity.dxf.insert[0], entity.dxf.insert[1]
                            
                            # DEL4 아래 8mm 이내 (Y값이 더 작고, 차이가 8mm 이내)
                            if ty < del4_y and (del4_y - ty) <= 8 and abs(tx - del4_x) <= 50:
                                del5_entities.append(entity)
        except:
            pass
    
    # 5단계: PL18 엔티티 삭제
    for entity in pl18_to_delete:
        try:
            msp.delete_entity(entity)
        except:
            pass
    
    # 6단계: 나머지 관련 엔티티를 RED 색상으로 변경
    entities_to_change_red = set()
    entities_to_change_red.update(del2_entities)
    entities_to_change_red.update(del3_entities)
    entities_to_change_red.update(ad1_entities)
    entities_to_change_red.update(del4_entities)
    entities_to_change_red.update(del5_entities)
    
    # RED 색상(인덱스 1)으로 변경
    for entity in entities_to_change_red:
        try:
            if hasattr(entity.dxf, 'color'):
                entity.dxf.color = 1  # RED
        except:
            pass
    
    # 모든 객체의 레이어를 ACE01로 변경
    for entity in msp:
        try:
            if hasattr(entity.dxf, 'layer'):
                entity.dxf.layer = 'ACE01'  # 레이어를 ACE01로 변경
        except:
            pass
    
    # 새 파일명 생성
    dir_name = os.path.dirname(file_path)
    base_name = os.path.basename(file_path)
    
    # 파일명에서 *PL 이전 부분 추출
    if 'PL' in base_name:
        new_name = base_name.split('PL')[0] + 'SA.DXF'
    else:
        # PL이 없는 경우 확장자 제거 후 SA.DXF 추가
        name_without_ext = os.path.splitext(base_name)[0]
        new_name = name_without_ext + 'SA.DXF'
    
    new_file_path = os.path.join(dir_name, new_name)
    
    # TEXT 속성 설정
    for txt in msp.query('TEXT'):
        if not txt.dxf.text:
            continue
        
        txt.dxf.width = 0.85      # 원하는 폭으로 설정
        txt.dxf.style = "ARIAL"  # 폰트 스타일
        txt.dxf.color = 2        # 색상 (2 = 노란색)

    if "ARIAL" not in doc.styles:
        doc.styles.new("ARIAL", dxfattribs={"font": "arial.ttf"})
    
    # 파일 저장 (원본과 동일한 DXF 버전으로)
    try:
        doc.saveas(new_file_path)
    except:
        # 버전 문제가 있으면 R2000으로 저장
        doc.saveas(new_file_path, fmt='R2000')

def main():
    """프로그램 실행"""
    # 필요한 라이브러리 확인
    try:
        import ezdxf
    except ImportError:
        sys.exit(1)
    
    process_dxf_files()

if __name__ == "__main__":
    main()

