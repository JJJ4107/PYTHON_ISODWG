import ezdxf
import math
import tkinter as tk
from tkinter import filedialog

def get_distance(p1, p2):
    """두 점 사이의 유클리드 거리 계산"""
    return math.hypot(p2[0] - p1[0], p2[1] - p1[1])

def select_dxf_file():
    """DXF 파일 선택 대화상자"""
    root = tk.Tk()
    root.withdraw()
    file_path = filedialog.askopenfilename(
        title="DXF 파일을 선택하세요",
        filetypes=[("DXF Files", "*.dxf"), ("All Files", "*.*")]
    )
    return file_path

def get_entity_center(entity):
    """엔티티의 중심점 또는 대표점 반환"""
    entity_type = entity.dxftype()
    
    try:
        if entity_type == 'LINE':
            start = (entity.dxf.start.x, entity.dxf.start.y)
            end = (entity.dxf.end.x, entity.dxf.end.y)
            return ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
        
        elif entity_type == 'CIRCLE':
            return (entity.dxf.center.x, entity.dxf.center.y)
        
        elif entity_type == 'ARC':
            return (entity.dxf.center.x, entity.dxf.center.y)
        
        elif entity_type in ['TEXT', 'MTEXT']:
            if hasattr(entity.dxf, 'insert'):
                return (entity.dxf.insert.x, entity.dxf.insert.y)
        
        elif entity_type == 'LWPOLYLINE':
            points = [(v[0], v[1]) for v in entity]
            if points:
                x = sum(p[0] for p in points) / len(points)
                y = sum(p[1] for p in points) / len(points)
                return (x, y)
        
        elif entity_type == 'POLYLINE':
            points = [(v.dxf.location.x, v.dxf.location.y) for v in entity.vertices()]
            if points:
                x = sum(p[0] for p in points) / len(points)
                y = sum(p[1] for p in points) / len(points)
                return (x, y)
        
        elif entity_type == 'POINT':
            return (entity.dxf.location.x, entity.dxf.location.y)
        
        elif entity_type == 'INSERT':
            return (entity.dxf.insert.x, entity.dxf.insert.y)
        
        elif entity_type == 'ELLIPSE':
            return (entity.dxf.center.x, entity.dxf.center.y)
            
    except:
        pass
    
    return None

def get_entity_properties(entity):
    """엔티티의 속성 정보 추출"""
    props = {
        'type': entity.dxftype(),
        'layer': getattr(entity.dxf, 'layer', '0'),
        'color': getattr(entity.dxf, 'color', 0),
        'handle': getattr(entity.dxf, 'handle', 'N/A')
    }
    
    entity_type = props['type']
    
    try:
        if entity_type == 'LINE':
            props['start'] = (entity.dxf.start.x, entity.dxf.start.y)
            props['end'] = (entity.dxf.end.x, entity.dxf.end.y)
            props['length'] = get_distance(props['start'], props['end'])
        
        elif entity_type == 'CIRCLE':
            props['center'] = (entity.dxf.center.x, entity.dxf.center.y)
            props['radius'] = entity.dxf.radius
        
        elif entity_type == 'ARC':
            props['center'] = (entity.dxf.center.x, entity.dxf.center.y)
            props['radius'] = entity.dxf.radius
            props['start_angle'] = entity.dxf.start_angle
            props['end_angle'] = entity.dxf.end_angle
        
        elif entity_type in ['TEXT', 'MTEXT']:
            props['text'] = getattr(entity.dxf, 'text', '')
            if hasattr(entity.dxf, 'insert'):
                props['position'] = (entity.dxf.insert.x, entity.dxf.insert.y)
            props['height'] = getattr(entity.dxf, 'height', 0)
        
        elif entity_type == 'LWPOLYLINE':
            points = [(v[0], v[1]) for v in entity]
            props['points'] = len(points)
            props['closed'] = getattr(entity.dxf, 'closed', False)
        
        elif entity_type == 'POLYLINE':
            points = [(v.dxf.location.x, v.dxf.location.y) for v in entity.vertices()]
            props['points'] = len(points)
            props['closed'] = getattr(entity.dxf, 'closed', False)
        
        elif entity_type == 'POINT':
            props['location'] = (entity.dxf.location.x, entity.dxf.location.y)
        
        elif entity_type == 'INSERT':
            props['block_name'] = getattr(entity.dxf, 'name', 'N/A')
            props['position'] = (entity.dxf.insert.x, entity.dxf.insert.y)
            props['rotation'] = getattr(entity.dxf, 'rotation', 0)
        
        elif entity_type == 'ELLIPSE':
            props['center'] = (entity.dxf.center.x, entity.dxf.center.y)
            props['ratio'] = entity.dxf.ratio
            
    except:
        pass
    
    return props

def main():
    print("\n=== DXF 전체 객체 분석 ===\n")
    
    # 파일 선택
    dxf_path = select_dxf_file()
    if not dxf_path:
        print("파일이 선택되지 않았습니다.")
        return

    try:
        # DXF 파일 읽기
        doc = ezdxf.readfile(dxf_path)
        msp = doc.modelspace()
        
        # 모든 엔티티 수집
        entities = []
        for entity in msp:
            center = get_entity_center(entity)
            if center:
                props = get_entity_properties(entity)
                entities.append({
                    'entity': entity,
                    'center': center,
                    'properties': props
                })
        
        print(f"총 {len(entities)}개의 객체를 발견했습니다.\n")
        
        # 1. 모든 객체 속성 표시
        print("【 객체 속성 정보 】")
        print("-" * 60)
        
        for i, item in enumerate(entities):
            props = item['properties']
            print(f"\n객체 #{i+1}")
            print(f"  타입: {props['type']}")
            print(f"  레이어: {props['layer']}")
            print(f"  색상: {props['color']}")
            print(f"  핸들: {props['handle']}")
            
            # 타입별 추가 정보
            entity_type = props['type']
            if entity_type == 'LINE':
                print(f"  시작점: ({props['start'][0]:.2f}, {props['start'][1]:.2f})")
                print(f"  끝점: ({props['end'][0]:.2f}, {props['end'][1]:.2f})")
                print(f"  길이: {props['length']:.2f}")
            elif entity_type == 'CIRCLE':
                print(f"  중심: ({props['center'][0]:.2f}, {props['center'][1]:.2f})")
                print(f"  반지름: {props['radius']:.2f}")
            elif entity_type == 'ARC':
                print(f"  중심: ({props['center'][0]:.2f}, {props['center'][1]:.2f})")
                print(f"  반지름: {props['radius']:.2f}")
                print(f"  시작각: {props['start_angle']:.2f}°")
                print(f"  끝각: {props['end_angle']:.2f}°")
            elif entity_type in ['TEXT', 'MTEXT']:
                print(f"  텍스트: '{props['text']}'")
                if 'position' in props:
                    print(f"  위치: ({props['position'][0]:.2f}, {props['position'][1]:.2f})")
                print(f"  높이: {props['height']:.2f}")
            elif entity_type in ['LWPOLYLINE', 'POLYLINE']:
                print(f"  점 개수: {props['points']}")
                print(f"  닫힘: {'예' if props['closed'] else '아니오'}")
            elif entity_type == 'POINT':
                print(f"  위치: ({props['location'][0]:.2f}, {props['location'][1]:.2f})")
            elif entity_type == 'INSERT':
                print(f"  블록명: {props['block_name']}")
                print(f"  위치: ({props['position'][0]:.2f}, {props['position'][1]:.2f})")
                print(f"  회전: {props['rotation']:.2f}°")
            elif entity_type == 'ELLIPSE':
                print(f"  중심: ({props['center'][0]:.2f}, {props['center'][1]:.2f})")
                print(f"  비율: {props['ratio']:.2f}")
        
        # 2. 모든 객체간 거리 표시
        print("\n\n【 객체간 거리 정보 】")
        print("-" * 60)
        
        if len(entities) > 1:
            for i in range(len(entities)):
                for j in range(i + 1, len(entities)):
                    dist = get_distance(entities[i]['center'], entities[j]['center'])
                    type1 = entities[i]['properties']['type']
                    type2 = entities[j]['properties']['type']
                    
                    # 추가 식별 정보
                    id1 = f"{type1}"
                    id2 = f"{type2}"
                    
                    if type1 in ['TEXT', 'MTEXT']:
                        id1 += f"('{entities[i]['properties']['text']}')"
                    if type2 in ['TEXT', 'MTEXT']:
                        id2 += f"('{entities[j]['properties']['text']}')"
                    
                    print(f"\n객체 #{i+1} [{id1}] ↔ 객체 #{j+1} [{id2}]")
                    print(f"  거리: {dist:.2f} mm")
                    print(f"  좌표: ({entities[i]['center'][0]:.2f}, {entities[i]['center'][1]:.2f}) ↔ ({entities[j]['center'][0]:.2f}, {entities[j]['center'][1]:.2f})")
        else:
            print("\n거리를 계산하기에 충분한 객체가 없습니다.")
        
        print("\n분석 완료!")
        
        # 3. 특정 텍스트 간 거리 표시
        print("\n\n【 특정 텍스트 간 거리 】")
        print("-" * 60)
        
        # 텍스트 엔티티만 필터링
        text_entities = []
        for item in entities:
            if item['properties']['type'] in ['TEXT', 'MTEXT']:
                text_content = item['properties'].get('text', '').strip()
                if text_content:
                    text_entities.append({
                        'text': text_content,
                        'center': item['center'],
                        'properties': item['properties']
                    })
        
        # 특정 텍스트 찾기
        text_2_bracket = None  # <2>
        text_1 = None         # 1
        text_2 = None         # 2
        
        for text_item in text_entities:
            if text_item['text'] == '<2>':
                text_2_bracket = text_item
            elif text_item['text'] == '1':
                text_1 = text_item
            elif text_item['text'] == '2':
                text_2 = text_item
        
        # 거리 계산 및 표시
        if text_2_bracket and text_1:
            dist = get_distance(text_2_bracket['center'], text_1['center'])
            print(f"\n'<2>' ↔ '1' 거리: {dist:.2f} mm")
            print(f"  '<2>' 위치: ({text_2_bracket['center'][0]:.2f}, {text_2_bracket['center'][1]:.2f})")
            print(f"  '1' 위치: ({text_1['center'][0]:.2f}, {text_1['center'][1]:.2f})")
        else:
            if not text_2_bracket:
                print("\n'<2>' 텍스트를 찾을 수 없습니다.")
            if not text_1:
                print("'1' 텍스트를 찾을 수 없습니다.")
        
        if text_2_bracket and text_2:
            dist = get_distance(text_2_bracket['center'], text_2['center'])
            print(f"\n'<2>' ↔ '2' 거리: {dist:.2f} mm")
            print(f"  '<2>' 위치: ({text_2_bracket['center'][0]:.2f}, {text_2_bracket['center'][1]:.2f})")
            print(f"  '2' 위치: ({text_2['center'][0]:.2f}, {text_2['center'][1]:.2f})")
        else:
            if not text_2_bracket:
                print("\n'<2>' 텍스트를 찾을 수 없습니다.")
            if not text_2:
                print("'2' 텍스트를 찾을 수 없습니다.")
        
        # 4. 흰색 라인과 DEL1 레이어 라인의 끝점 간 거리
        print("\n\n【 흰색 라인과 DEL1 레이어 라인 끝점 간 거리 】")
        print("-" * 60)
        
        # 흰색 라인 찾기 (색상 코드 7)
        white_lines = []
        del1_lines = []
        
        for item in entities:
            if item['properties']['type'] == 'LINE':
                # 흰색 체크 (DXF 색상 코드 7)
                if item['properties']['color'] == 7:
                    white_lines.append(item)
                # DEL1 레이어 체크
                if item['properties']['layer'].upper() == 'DEL1':
                    del1_lines.append(item)
        
        print(f"\n흰색 라인 개수: {len(white_lines)}")
        print(f"DEL1 레이어 라인 개수: {len(del1_lines)}")
        
        if white_lines:
            print("\n[흰색 라인 정보]")
            for i, line in enumerate(white_lines):
                props = line['properties']
                print(f"흰색 라인 #{i+1}:")
                print(f"  시작점: ({props['start'][0]:.2f}, {props['start'][1]:.2f})")
                print(f"  끝점: ({props['end'][0]:.2f}, {props['end'][1]:.2f})")
        
        if del1_lines:
            print("\n[DEL1 레이어 라인 정보]")
            for i, line in enumerate(del1_lines):
                props = line['properties']
                print(f"DEL1 라인 #{i+1}:")
                print(f"  시작점: ({props['start'][0]:.2f}, {props['start'][1]:.2f})")
                print(f"  끝점: ({props['end'][0]:.2f}, {props['end'][1]:.2f})")
        
        # 흰색과 DEL1 라인의 끝점 간 거리 계산
        if white_lines and del1_lines:
            print("\n[끝점 간 거리]")
            for i, white_line in enumerate(white_lines):
                white_end = white_line['properties']['end']
                for j, del1_line in enumerate(del1_lines):
                    del1_end = del1_line['properties']['end']
                    dist = get_distance(white_end, del1_end)
                    print(f"\n흰색 라인 #{i+1} 끝점 ↔ DEL1 라인 #{j+1} 끝점")
                    print(f"  거리: {dist:.2f} mm")
                    print(f"  흰색 끝점: ({white_end[0]:.2f}, {white_end[1]:.2f})")
                    print(f"  DEL1 끝점: ({del1_end[0]:.2f}, {del1_end[1]:.2f})")
                    
                    # 시작점과 끝점 간의 거리도 계산
                    white_start = white_line['properties']['start']
                    del1_start = del1_line['properties']['start']
                    
                    dist_start_to_end = get_distance(white_start, del1_end)
                    dist_end_to_start = get_distance(white_end, del1_start)
                    
                    print(f"  흰색 시작점 ↔ DEL1 끝점: {dist_start_to_end:.2f} mm")
                    print(f"  흰색 끝점 ↔ DEL1 시작점: {dist_end_to_start:.2f} mm")
        else:
            if not white_lines:
                print("\n흰색 라인을 찾을 수 없습니다.")
            if not del1_lines:
                print("DEL1 레이어의 라인을 찾을 수 없습니다.")
        
    except Exception as e:
        print(f"오류 발생: {e}")

if __name__ == "__main__":
    main()