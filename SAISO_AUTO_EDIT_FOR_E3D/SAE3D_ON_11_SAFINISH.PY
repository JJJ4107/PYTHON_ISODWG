import ezdxf
import os
import sys
import math

def process_single_dxf(file_path):
    """단일 DXF 파일 처리 (기존 로직 유지, 출력 제거)"""
    doc = ezdxf.readfile(file_path)
    msp = doc.modelspace()

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
            if 'SUPP' in layer_upper:
                supp_lines_to_convert.append(entity)
                continue

        # 엔티티의 위치 확인
        if hasattr(entity, 'dxf'):
            x, y = None, None

            if entity.dxftype() in ('TEXT', 'MTEXT'):
                if hasattr(entity.dxf, 'insert'):
                    x, y = entity.dxf.insert[0], entity.dxf.insert[1]
            elif hasattr(entity.dxf, 'location'):
                x, y = entity.dxf.location[0], entity.dxf.location[1]
            elif hasattr(entity.dxf, 'center'):
                x, y = entity.dxf.center[0], entity.dxf.center[1]
            elif entity.dxftype() == 'LINE':
                if hasattr(entity.dxf, 'start'):
                    x, y = entity.dxf.start[0], entity.dxf.start[1]
            elif entity.dxftype() in ('POLYLINE', 'LWPOLYLINE'):
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
                    if hasattr(entity.dxf, 'layer'):
                        if entity.dxf.layer in ['PL16', 'PL8']:
                            entities_to_delete.append(entity)
                            continue

                    if entity.dxftype() in ['TEXT', 'MTEXT']:
                        if hasattr(entity.dxf, 'text') and str(entity.dxf.text).strip() == 'N':
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
    for line in supp_lines_to_convert:
        try:
            start = line.dxf.start
            end = line.dxf.end

            try:
                polyline = msp.add_lwpolyline([(start[0], start[1]), (end[0], end[1])])
                polyline.dxf.const_width = 0.3
            except:
                polyline = msp.add_polyline2d([(start[0], start[1]), (end[0], end[1])])
                for vertex in polyline.vertices:
                    vertex.dxf.start_width = 0.3
                    vertex.dxf.end_width = 0.3

            polyline.dxf.layer = line.dxf.layer
            if hasattr(line.dxf, 'color'):
                polyline.dxf.color = line.dxf.color

            msp.delete_entity(line)
        except:
            import traceback
            traceback.print_exc(file=sys.stderr)

    # 색상 변경 작업
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

                # PIPE/TEE/ELBO가 레이어 이름에 포함된 폴리라인을 BLUE로 변경
                elif current_layer in pipe_tee_elbo_layers:
                    if entity.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
                        entity.dxf.color = 5  # BLUE

                # AD1, G1 레이어의 CYAN이나 GREEN 폴리라인을 흰색으로
                elif current_layer in ['AD1', 'G1']:
                    if entity.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
                        if current_color in (4, 3):  # CYAN(4) or GREEN(3)
                            entity.dxf.color = 7  # WHITE

                # 1. 모든 CYAN TEXT를 YELLOW로 변경
                if entity.dxftype() in ['TEXT', 'MTEXT'] and current_color == 4:
                    entity.dxf.color = 2  # YELLOW

                # 2. GT-1 레이어의 YELLOW 폴리라인 중 길이 ≤ 5 → WHITE
                elif current_layer == 'GT-1' and current_color == 2:
                    if entity.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
                        length = 0
                        try:
                            if entity.dxftype() == 'LWPOLYLINE':
                                points = list(entity.get_points())
                                for i in range(len(points) - 1):
                                    dx = points[i+1][0] - points[i][0]
                                    dy = points[i+1][1] - points[i][1]
                                    length += math.sqrt(dx**2 + dy**2)
                            else:
                                vertices = list(entity.vertices)
                                for i in range(len(vertices) - 1):
                                    dx = vertices[i+1].dxf.location[0] - vertices[i].dxf.location[0]
                                    dy = vertices[i+1].dxf.location[1] - vertices[i].dxf.location[1]
                                    length += math.sqrt(dx**2 + dy**2)

                            if length <= 5:
                                entity.dxf.color = 7  # WHITE
                        except:
                            pass

                # 3. PL2 레이어이고 색상이 CYAN인 폴리라인은 WHITE로
                elif current_layer == 'PL2' and current_color == 4:
                    if entity.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
                        entity.dxf.color = 7  # WHITE

        except:
            pass

    # SFW 레이어 관련 작업
    sfw_points = []
    pl18_to_delete = []
    del2_entities = []
    del3_entities = []
    ad1_entities = []
    del4_entities = []
    del5_entities = []
    sfw_entities = []

    # 1단계: SFW 레이어의 점 수집 및 SFW 엔티티 수집
    for entity in msp:
        if hasattr(entity.dxf, 'layer'):
            layer_name = entity.dxf.layer.upper()
            if layer_name == 'SFW':
                sfw_entities.append(entity)
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
                    if entity.dxftype() == 'LWPOLYLINE':
                        points = list(entity.get_points())
                        for p in points:
                            sfw_points.append((p[0], p[1]))

    # 2단계: 각 SFW 점 주변 범위 검색 (주석의 수치 유지)
    for sfw_x, sfw_y in sfw_points:
        for entity in msp:
            try:
                x, y = None, None

                if entity.dxftype() in ['TEXT', 'MTEXT']:
                    if hasattr(entity.dxf, 'insert'):
                        x, y = entity.dxf.insert[0], entity.dxf.insert[1]
                elif entity.dxftype() == 'LINE':
                    if hasattr(entity.dxf, 'start'):
                        x, y = entity.dxf.start[0], entity.dxf.start[1]
                elif entity.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
                    if entity.dxftype() == 'LWPOLYLINE':
                        points = list(entity.get_points())
                        if points:
                            x, y = points[0][0], points[0][1]
                    else:
                        vertices = list(entity.vertices)
                        if vertices:
                            x, y = vertices[0].dxf.location[0], vertices[0].dxf.location[1]

                if x is not None and y is not None:
                    # 바깥 범위 100 (기존 코드 유지)
                    if abs(x - sfw_x) <= 100 and abs(y - sfw_y) <= 100:
                        current_layer = entity.dxf.layer if hasattr(entity.dxf, 'layer') else ''

                        if current_layer.upper() == 'PL18':
                            pl18_to_delete.append(entity)

                        # 내부 범위 2 (기존 코드 유지)
                        if abs(x - sfw_x) <= 2 and abs(y - sfw_y) <= 2:
                            if entity.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
                                points_list = []
                                length = 0

                                if entity.dxftype() == 'LWPOLYLINE':
                                    points_list = list(entity.get_points())
                                else:
                                    vertices = list(entity.vertices)
                                    points_list = [(v.dxf.location[0], v.dxf.location[1]) for v in vertices]

                                for i in range(len(points_list) - 1):
                                    dx = points_list[i+1][0] - points_list[i][0]
                                    dy = points_list[i+1][1] - points_list[i][1]
                                    length += math.sqrt(dx**2 + dy**2)

                                if len(points_list) == 2 and length <= 7 and current_layer.upper() == 'PL2':
                                    del2_entities.append(entity)
                                elif len(points_list) == 3:
                                    del3_entities.append(entity)
                                elif length >= 7:
                                    ad1_entities.append(entity)

                            elif entity.dxftype() == 'LINE':
                                del3_entities.append(entity)

            except:
                pass

    # 3단계: AD1 끝점에서 50mm 범위의 'CON' 포함 문자 찾기
    for ad1_entity in ad1_entities:
        try:
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
                for entity in msp:
                    if entity.dxftype() in ['TEXT', 'MTEXT']:
                        if hasattr(entity.dxf, 'insert'):
                            tx, ty = entity.dxf.insert[0], entity.dxf.insert[1]
                            distance = math.sqrt((tx - end_point[0])**2 + (ty - end_point[1])**2)
                            if distance <= 50:
                                if hasattr(entity.dxf, 'text'):
                                    if 'CON' in str(entity.dxf.text).upper():
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
                entity.dxf.layer = 'ACE01'
        except:
            pass

    # 새 파일명 생성
    dir_name = os.path.dirname(file_path)
    base_name = os.path.basename(file_path)

    if 'PL' in base_name:
        new_name = base_name.split('PL')[0] + 'SA.DXF'
    else:
        name_without_ext = os.path.splitext(base_name)[0]
        new_name = name_without_ext + 'SA.DXF'

    new_file_path = os.path.join(dir_name, new_name)

    # TEXT 속성 설정
    for txt in msp.query('TEXT'):
        try:
            if not txt.dxf.text:
                continue
            txt.dxf.width = 0.85
            txt.dxf.style = "ARIAL"
            txt.dxf.color = 2
        except:
            pass

    if "ARIAL" not in doc.styles:
        try:
            doc.styles.new("ARIAL", dxfattribs={"font": "arial.ttf"})
        except:
            pass

    # 저장 (가능하면 원본 버전, 실패 시 R2000)
    try:
        doc.saveas(new_file_path)
    except:
        doc.saveas(new_file_path, fmt='R2000')

def main():
    # tkinter 제거, 명령줄 인자로 DXF 목록을 받음
    if len(sys.argv) <= 1:
        # 인자가 없으면 조용히 종료 (print 금지 요청)
        return

    # ezdxf 임포트 확인은 상단에서 이미 수행됨
    # 전달된 모든 경로 처리
    for file_path in sys.argv[1:]:
        try:
            if os.path.isfile(file_path) and file_path.lower().endswith('.dxf'):
                process_single_dxf(file_path)
        except:
            # 출력 금지 요구에 따라 조용히 무시
            pass

if __name__ == "__main__":
    main()
