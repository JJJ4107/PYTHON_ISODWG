import os
import re
import ezdxf
import tkinter as tk
from tkinter import filedialog
from datetime import datetime
from collections import defaultdict

try:
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
except ImportError:
    print("openpyxl 라이브러리가 필요합니다.")
    print("설치 명령: pip install openpyxl")
    exit()

def get_xy(e): 
    try:
        if hasattr(e, 'dxf') and hasattr(e.dxf, 'insert'):
            ins = e.dxf.insert
            if hasattr(ins, 'x') and hasattr(ins, 'y'):
                return float(ins.x), float(ins.y)
            elif isinstance(ins, (tuple, list)) and len(ins) >= 2:
                return float(ins[0]), float(ins[1])
        elif hasattr(e, 'insert'):
            ins = e.insert
            if isinstance(ins, (tuple, list)) and len(ins) >= 2:
                return float(ins[0]), float(ins[1])
    except Exception:
        pass
    return 0.0, 0.0

def get_text(e):
    try:
        if hasattr(e, 'dxf') and hasattr(e.dxf, 'text'):
            return e.dxf.text
        elif hasattr(e, 'text'):
            return e.text
    except Exception:
        pass
    return ''

def clean_str(s):
    return ''.join(s.split())

# 파일 선택 (tkinter 사용)
root = tk.Tk()
root.withdraw()
file_paths = filedialog.askopenfilenames(
    title="DXF 도면 선택", filetypes=[("DXF files", "*.dxf")]
)
root.destroy()
if not file_paths:
    print("DXF 파일이 선택되지 않았습니다.")
    exit()

# Excel 파일명 생성
today = datetime.now().strftime("%Y%m%d_%H%M%S")
excel_filename = f"TOTALBOM_{today}.xlsx"
excel_path = os.path.join(os.path.dirname(file_paths[0]), excel_filename)

# 전체 데이터를 저장할 리스트
all_data = []

# 시트별 데이터를 저장할 딕셔너리 추가
sheet_data = {
    'FAB MAT': [],
    'ELEC MAT': [],
    'PIPE': [],
    'BOLT/NUT': [],
    'INST': [],
    'FITTING': []
}

# 각 DXF 파일 처리
for file_path in file_paths:
    print(f"\n처리 중: {os.path.basename(file_path)}")
    file_data = []  # 현재 파일의 데이터를 임시 저장
    
    try:
        doc = ezdxf.readfile(file_path)
        msp = doc.modelspace()
    except Exception as e:
        continue
    
    # 1. LINENO 찾기 (기존 코드와 동일)
    lineno = None
    for e in msp.query('TEXT MTEXT'):
        txt = get_text(e).strip()
        x, y = get_xy(e)
        if 0 <= x <= 150 and 0 <= y <= 85 and '-' in txt and len(txt) >= 10:
            lineno = clean_str(txt)
            break
    
    if not lineno:
        lineno = '-'
    
    # 2. FABRICATION MATERIALS 섹션에서 ISODWGNO 찾기
    isodwgno = None
    iso_description = '-'  # ISO DESCRIPTION 초기값
    fab_mat_e = None
    fab_x, fab_y = None, None
    iso_x, iso_y = None, None  # ISO DWG NO의 위치 저장
    
    for e in msp.query('TEXT MTEXT'):
        txt = get_text(e)
        if "FABRICATION MATERIALS" in txt.upper():
            fab_mat_e = e
            fab_x, fab_y = get_xy(e)
            break
    
    if fab_mat_e:
        for e in msp.query('TEXT MTEXT'):
            txt = get_text(e).strip()
            x, y = get_xy(e)
            if fab_x is not None and fab_y is not None:
                if (x > fab_x) and (0 <= y <= 20) and ('-' in txt):
                    isodwgno = txt
                    iso_x, iso_y = x, y  # ISO DWG NO의 위치 저장
                    break
    
    if not isodwgno:
        isodwgno = '-'
    
    # 2.1. ISO DESCRIPTION 찾기 (변경된 범위: X-50 ~ X+50, Y+10 ~ Y+45)
    if iso_x is not None and iso_y is not None:
        # 지정된 범위에서 텍스트 찾기
        for e in msp.query('TEXT MTEXT'):
            txt = get_text(e).strip()
            x, y = get_xy(e)
            # X 좌표: iso_x-50부터 iso_x+50까지, Y 좌표: iso_y+25부터 iso_y+45까지
            if (iso_x - 50 <= x <= iso_x + 50) and (iso_y + 10 <= y <= iso_y + 45) and txt:
                iso_description = txt
                print(f"  - ISO DESCRIPTION 발견: {iso_description} at ({x:.1f}, {y:.1f})")
                break  # 첫 번째 텍스트만 사용
    
    # 2.5. INSU 값 찾기 (X: 185-200, Y: 60-70 영역)
    insu_value = '-'
    
    # 해당 영역의 모든 텍스트 확인
    area_texts = []
    for e in msp.query('TEXT MTEXT'):
        txt = get_text(e).strip()
        x, y = get_xy(e)
        if 185 <= x <= 200 and 60 <= y <= 70:
            area_texts.append((x, y, txt))
    
    # 숫자 텍스트 찾기
    for x, y, txt in area_texts:
        # 숫자인지 확인 (소수점 포함)
        try:
            float(txt)  # 숫자 변환 시도
            insu_value = txt
            break
        except ValueError:
            # 숫자가 아니면 계속 검색
            continue
    
    # 3. PT 헤더 찾기 (직접 검색)
    headers = ['PT', 'ITEM', 'MATERIAL', 'SIZE', 'DESCRIPTION', 'QTY', 'UNIT', 'TOTAL', 'REMARK']
    
    # 모든 PT 헤더 찾기
    pt_headers = []
    for e in msp.query('TEXT MTEXT'):
        txt = get_text(e).strip().upper()
        x, y = get_xy(e)
        # PT가 포함되고, 다른 긴 텍스트가 아닌 경우
        if txt == 'PT' or (txt.startswith('PT') and len(txt) <= 5):
            pt_headers.append((x, y, txt))
    
    if not pt_headers:
        continue
    
    # 각 PT 헤더에 대해 처리
    file_processed_pts = {}  # 파일 전체에서 처리된 PT 추적 - 각 파일마다 초기화
    
    for pt_idx, (pt_x, pt_y, pt_txt) in enumerate(pt_headers):
        
        # 현재 PT 헤더 주변의 다른 헤더들 찾기
        header_positions = {'PT': pt_x}
        
        # PT와 같은 Y 좌표 근처(±5)에서 다른 헤더 찾기
        for e in msp.query('TEXT MTEXT'):
            txt = get_text(e).strip().upper()
            x, y = get_xy(e)
            
            # PT와 비슷한 Y 좌표에 있는 헤더들 찾기
            if abs(y - pt_y) <= 5:
                for header in headers:
                    if header != 'PT':
                        # 헤더 텍스트 정확히 매칭 또는 포함 확인
                        if (header == txt) or (header in txt and len(txt) <= len(header) + 10):
                            header_positions[header] = x
                            break
        
        # DESCRIPTION 헤더 특별 처리 (다양한 변형 확인)
        if 'DESCRIPTION' not in header_positions:
            for e in msp.query('TEXT MTEXT'):
                txt = get_text(e).strip().upper()
                x, y = get_xy(e)
                if abs(y - pt_y) <= 5:
                    if 'DESC' in txt or 'DESCRIPT' in txt:
                        header_positions['DESCRIPTION'] = x
                        break
        
        # 4. PT 아래의 데이터 추출
        data_rows = []
        
        # 모든 텍스트를 Y좌표로 정렬
        all_texts = []
        for e in msp.query('TEXT MTEXT'):
            txt = get_text(e).strip()
            x, y = get_xy(e)
            if txt:  # 빈 텍스트는 제외
                all_texts.append((x, y, txt))
        
        all_texts.sort(key=lambda t: -t[1])  # Y좌표 내림차순 정렬
        
        # PT 숫자 찾기
        current_row = None
        last_pt_y = None
        pt_count = 0
        processed_pts = {}  # PT 번호별로 처리 여부 추적 {pt_number: row_data}
        
        for x, y, txt in all_texts:
            # PT 헤더 아래에서만 검색
            if y >= pt_y:
                continue
            
            # PT 열 위치 확인
            is_pt_column = abs(x - pt_x) <= 2
            
            # PT 열에서 숫자 찾기
            if is_pt_column and txt.isdigit():
                # 파일 전체에서 이미 처리된 PT인지 확인 (PT 번호만으로 체크)
                if txt in file_processed_pts:
                    print(f"    → PT {txt} 중복 발견, 건너뛰기")
                    continue
                
                print(f"  - PT {txt} 발견 at Y={y:.1f}")
                
                # 현재 테이블에서 중복 PT 처리
                if txt in processed_pts:
                    print(f"    → PT {txt} 중복 발견, 건너뛰기")
                    # 중복 PT가 발견되면 완전히 건너뛰기
                    continue
                
                # 이전 행 저장 (중복 체크)
                if current_row and current_row.get('ITEM NO') not in processed_pts:
                    processed_pts[current_row.get('ITEM NO')] = current_row
                    data_rows.append(current_row)
                
                pt_count += 1
                
                # 새로운 행 시작
                current_row = {'ITEM NO': txt, '_y_pos': y, '_pt_header_index': pt_idx}  # PT 헤더 인덱스 추가
                last_pt_y = y
                
                # 첫 번째 줄 데이터 수집
                for hdr, hdr_x in header_positions.items():
                    if hdr != 'PT':
                        for x2, y2, txt2 in all_texts:
                            if abs(x2 - hdr_x) <= 2 and abs(y2 - y) <= 2:
                                if txt2:  # 빈 텍스트가 아닌 경우만
                                    current_row[hdr] = txt2
                                break
                
                # 다음 줄 데이터 확인 (PT 열이 비어있는 경우에만)
                # 현재 PT 아래 2-6mm 범위에서 확인
                for next_y in range(int(y-6), int(y-2)):
                    next_y_float = float(next_y)
                    
                    # 먼저 이 Y 위치의 PT 열 확인
                    has_pt_at_next = False
                    for x2, y2, txt2 in all_texts:
                        if abs(x2 - pt_x) <= 2 and abs(y2 - next_y_float) <= 1:
                            if txt2 and txt2.strip():  # 공백이 아닌 텍스트가 있으면
                                if txt2.isdigit():  # PT 번호가 있으면
                                    has_pt_at_next = True
                                    break
                    
                    # PT 열에 숫자가 있으면 다음 PT이므로 중단
                    if has_pt_at_next:
                        break
                    
                    # PT 열이 비어있으면 다른 열의 데이터 확인
                    next_line_data = {}
                    has_data_at_next = False
                    
                    for hdr, hdr_x in header_positions.items():
                        if hdr != 'PT':
                            for x2, y2, txt2 in all_texts:
                                if abs(x2 - hdr_x) <= 2 and abs(y2 - next_y_float) <= 1 and txt2:
                                    next_line_data[hdr] = txt2
                                    has_data_at_next = True
                                    break
                    
                    # 데이터가 있으면 현재 행에 병합
                    if has_data_at_next:
                        for hdr, txt2 in next_line_data.items():
                            if current_row.get(hdr):
                                # 숫자 필드는 대체, 텍스트 필드는 공백 포함 연결
                                if hdr in ['UNIT', 'TOTAL', 'QTY']:
                                    current_row[hdr] = txt2  # 숫자는 대체
                                else:
                                    # 텍스트는 공백으로 연결
                                    current_row[hdr] = current_row[hdr] + ' ' + txt2
                            else:
                                current_row[hdr] = txt2
                        break  # 한 줄만 병합
            
            # PT 열이 비어있는 경우 - 추가 데이터 수집
            elif is_pt_column and current_row and abs(y - current_row['_y_pos']) < 10:
                # 현재 행의 PT 위치에서 10mm 이내인 경우만 처리
                # 다른 열에 데이터가 있는지 확인
                for hdr, hdr_x in header_positions.items():
                    if hdr != 'PT':
                        for x2, y2, txt2 in all_texts:
                            if abs(x2 - hdr_x) <= 2 and abs(y2 - y) <= 2 and txt2:
                                if current_row.get(hdr):
                                    # 숫자 필드는 대체, 텍스트 필드는 공백 포함 연결
                                    if hdr in ['UNIT', 'TOTAL', 'QTY']:
                                        current_row[hdr] = txt2
                                    else:
                                        current_row[hdr] = current_row[hdr] + ' ' + txt2
                                else:
                                    current_row[hdr] = txt2
                                break
            
            # 다른 PT 헤더 영역 도달 시 중단
            if y < pt_y - 100:  # PT 헤더에서 100mm 이상 떨어지면 중단
                break
            for other_idx, (other_pt_x, other_pt_y, _) in enumerate(pt_headers):
                if other_idx != pt_idx and other_pt_y < pt_y and abs(y - other_pt_y) <= 5:
                    break
        
        # 마지막 행 추가 (중복 체크)
        if current_row and current_row.get('ITEM NO') not in processed_pts:
            processed_pts[current_row.get('ITEM NO')] = current_row
            data_rows.append(current_row)
        
        # data_rows를 processed_pts 기준으로 재구성 (중복 제거)
        unique_data_rows = []
        seen_pts = set()
        for row in data_rows:
            pt_no = row.get('ITEM NO')
            if pt_no and pt_no not in seen_pts:
                seen_pts.add(pt_no)
                unique_data_rows.append(row)
        data_rows = unique_data_rows
        
        print(f"  - 테이블 {pt_idx+1}: 처리된 PT 개수 = {len(processed_pts)}, 고유 데이터 행 수 = {len(data_rows)}")
        
        # 5. UNIT 결정 및 Excel 데이터 생성
        table_data_count = 0
        
        for row in data_rows:
            # 같은 파일 내에서 이미 처리된 PT는 건너뛰기
            if row.get('ITEM NO') in file_processed_pts:
                print(f"    > PT {row.get('ITEM NO')}는 이미 처리됨 (건너뛰기)")
                continue
            
            # PT 헤더 인덱스 보존
            pt_header_index = row.get('_pt_header_index', -1)
            
            # _y_pos 제거 (내부 사용 필드)
            if '_y_pos' in row:
                del row['_y_pos']
                
            item = row.get('ITEM', '')
            mmea = 'MM' if 'PIPE' in item.upper() else 'EA'
            
            # UNIT와 TOTAL 값 반올림 처리
            unit_value = row.get('UNIT', '')
            total_value = row.get('TOTAL', '')
            
            # UNIT 반올림
            try:
                unit_float = float(unit_value)
                # 정수인지 확인
                if unit_float.is_integer():
                    unit_value = str(int(unit_float))
                else:
                    unit_value = str(round(unit_float, 1))
            except (ValueError, TypeError):
                unit_value = unit_value  # 숫자가 아니면 그대로 사용
            
            # TOTAL 반올림
            try:
                total_float = float(total_value)
                # 정수인지 확인
                if total_float.is_integer():
                    total_value = str(int(total_float))
                else:
                    total_value = str(round(total_float, 1))
            except (ValueError, TypeError):
                total_value = total_value  # 숫자가 아니면 그대로 사용
            
            csv_row = {
                'ISO DWG NO': isodwgno,
                'LINE NO': lineno,
                'ISO DESCRIPTION': iso_description,  # LINE NO 뒤로 이동
                'ITEM NO': row.get('ITEM NO', ''),  # PT를 ITEM NO로
                'ITEM': item,
                'MATERIAL': row.get('MATERIAL', ''),
                'SIZE': row.get('SIZE', ''),
                'DESCRIPTION': row.get('DESCRIPTION', ''),
                'Q\'TY': row.get('QTY', ''),
                '(mm/ea)': mmea,
                'U.WT': unit_value,  # 반올림된 UNIT 값
                'T.WT': total_value,  # 반올림된 TOTAL 값
                'INSU. T\'HK': insu_value,  # INSU 값 추가
                'REMARK': row.get('REMARK', ''),
                '_pt_header_index': pt_header_index  # PT 헤더 인덱스 추가
            }
            
            # 모든 'unset' 값을 '-'로 변경
            for key, value in csv_row.items():
                if isinstance(value, str) and value.lower() == 'unset':
                    csv_row[key] = '-'
            
            file_data.append(csv_row)  # 파일별 임시 리스트에 저장
            table_data_count += 1
            
            # 파일 전체 PT 추적에 추가 (PT 번호만으로 추적)
            file_processed_pts[row.get('ITEM NO')] = True
            
            # 디버깅: 생성된 행 확인
            desc_preview = csv_row['DESCRIPTION'][:30] + '...' if len(csv_row['DESCRIPTION']) > 30 else csv_row['DESCRIPTION']
            print(f"    > Excel 행 생성: PT={csv_row['ITEM NO']}, DESC={desc_preview}, T.WT={csv_row['T.WT']}")
        
        print(f"  - 테이블 {pt_idx+1}에서 추출된 행 수: {table_data_count}")
    
    # 현재 파일의 데이터를 PT 번호로 정렬
    if file_data:
        # PT를 숫자로 변환하여 정렬 (빈 값은 맨 뒤로)
        def sort_key(row):
            try:
                return int(row['ITEM NO'])
            except (ValueError, KeyError):
                return 9999  # ITEM NO가 없거나 숫자가 아닌 경우 맨 뒤로
        
        # 중복 제거
        unique_file_data = {}
        duplicate_count = 0
        for row in file_data:
            item_no = row.get('ITEM NO')
            if item_no:
                if item_no not in unique_file_data:
                    unique_file_data[item_no] = row
                else:
                    duplicate_count += 1
                    print(f"  - 중복 PT {item_no} 제거됨")
        
        if duplicate_count > 0:
            print(f"  - 총 {duplicate_count}개의 중복 데이터 제거됨")
        
        file_data_sorted = sorted(unique_file_data.values(), key=sort_key)
        
        # 정렬된 데이터를 전체 리스트에 추가
        all_data.extend(file_data_sorted)
        
        # 시트별로 데이터 분류
        for row in file_data_sorted:
            pt_header_idx = row.get('_pt_header_index', -1)
            item_upper = row.get('ITEM', '').upper()
            
            # _pt_header_index 제거 (시트별 데이터에는 필요 없음)
            row_copy = row.copy()
            if '_pt_header_index' in row_copy:
                del row_copy['_pt_header_index']
            
            # PT 헤더 인덱스에 따라 분류
            if pt_header_idx == 0:  # 첫 번째 PT 헤더
                sheet_data['FAB MAT'].append(row_copy)
            elif pt_header_idx == 1:  # 두 번째 PT 헤더
                sheet_data['ELEC MAT'].append(row_copy)
            
            # ITEM 내용에 따라 분류
            if 'PIPE' in item_upper and 'SUPPORT' not in item_upper:
                sheet_data['PIPE'].append(row_copy)
            elif 'BOLT' in item_upper or 'NUT' in item_upper or 'GASKET' in item_upper or 'GASK' in item_upper:
                sheet_data['BOLT/NUT'].append(row_copy)
            elif 'VALV' in item_upper or 'INST' in item_upper or 'V/V' in item_upper or 'MOV' in item_upper or 'PCV' in item_upper:
                sheet_data['INST'].append(row_copy)
            else:
                sheet_data['FITTING'].append(row_copy)
        
        print(f"\n  === 파일 처리 완료: {os.path.basename(file_path)} ===")
        print(f"  - 이 파일에서 추출된 데이터: {len(file_data_sorted)}행 (중복 제거 후)")
        print(f"  - 현재까지 총 데이터: {len(all_data)}행")
    else:
        print(f"\n  === 파일 처리 완료: {os.path.basename(file_path)} ===")
        print(f"  - 이 파일에서 추출된 데이터: 0행")

# 6. Excel 파일 저장
if all_data:
    # Excel 워크북 생성
    wb = Workbook()
    
    # 헤더 정의 (ISO DESCRIPTION을 LINE NO 뒤로 이동)
    headers = ['ISO DWG NO', 'LINE NO', 'ISO DESCRIPTION', 'ITEM NO', 'ITEM', 'SIZE', 'MATERIAL', 
               'DESCRIPTION', 'Q\'TY', '(mm/ea)', 'U.WT', 'T.WT', 'INSU. T\'HK', 'REMARK']
    
    # 헤더 스타일 (크기 12, 굵게, 중앙 정렬, 굵은 테두리)
    header_font = Font(size=12, bold=True)
    header_alignment = Alignment(horizontal='center', vertical='center')
    header_border = Border(
        left=Side(style='thick'),
        right=Side(style='thick'),
        top=Side(style='thick'),
        bottom=Side(style='thick')
    )
    
    # 데이터 스타일 (크기 11, 중앙 정렬, 일반 테두리)
    data_font = Font(size=11)
    data_alignment = Alignment(horizontal='center', vertical='center')
    data_border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )
    
    # 첫 번째 시트: 전체 데이터 (MTO Data)
    ws = wb.active
    ws.title = "MTO Data"
    
    # 헤더 작성
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.alignment = header_alignment
        cell.border = header_border
    
    # 데이터 작성 (_pt_header_index 제외)
    for row_idx, data in enumerate(all_data, 2):
        for col_idx, header in enumerate(headers, 1):
            value = data.get(header, '')
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.font = data_font
            cell.alignment = data_alignment
            cell.border = data_border
    
    # 컬럼 너비 자동 조정
    for column in ws.columns:
        max_length = 0
        column_letter = get_column_letter(column[0].column)
        
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        
        adjusted_width = (max_length + 2) * 1.2
        ws.column_dimensions[column_letter].width = adjusted_width
    
    # 추가 시트 생성 및 데이터 입력
    sheet_names = ['FAB MAT', 'ELEC MAT', 'PIPE', 'BOLT/NUT', 'FITTING', 'INST']  # INST를 마지막으로
    
    # TOTAL BOM 시트 생성을 위한 데이터 그룹화
    total_bom_data = defaultdict(lambda: {
        'Q\'TY': 0,
        '(mm/ea)': '',
        'U.WT': '',
        'count': 0
    })
    
    # 전체 데이터를 그룹화하여 합산
    for row in all_data:
        # 그룹화 키: ITEM + SIZE + MATERIAL + DESCRIPTION
        key = (
            row.get('ITEM', ''),
            row.get('SIZE', ''),
            row.get('MATERIAL', ''),
            row.get('DESCRIPTION', '')
        )
        
        # 수량 합산
        try:
            qty = float(row.get('Q\'TY', 0) or 0)
        except (ValueError, TypeError):
            qty = 0
        
        total_bom_data[key]['Q\'TY'] += qty
        total_bom_data[key]['(mm/ea)'] = row.get('(mm/ea)', '')
        total_bom_data[key]['U.WT'] = row.get('U.WT', '')
        total_bom_data[key]['count'] += 1
    
    # TOTAL BOM 시트 데이터 생성
    total_bom_rows = []
    for (item, size, material, description), data in total_bom_data.items():
        # T.WT 계산 (Q'TY × U.WT)
        try:
            unit_weight = float(data['U.WT'] or 0)
            total_qty = data['Q\'TY']
            total_weight = unit_weight * total_qty
            
            # (mm/ea) 값이 MM인 경우 1000으로 나누기
            if data['(mm/ea)'] == 'MM':
                total_weight = total_weight / 1000
            
            # 반올림 처리
            if total_weight.is_integer():
                total_weight_str = str(int(total_weight))
            else:
                total_weight_str = str(round(total_weight, 1))
        except (ValueError, TypeError):
            total_weight_str = ''
        
        # 수량 반올림 처리
        if isinstance(data['Q\'TY'], (int, float)):
            if float(data['Q\'TY']).is_integer():
                qty_str = str(int(data['Q\'TY']))
            else:
                qty_str = str(round(data['Q\'TY'], 1))
        else:
            qty_str = str(data['Q\'TY'])
        
        total_bom_rows.append({
            'ITEM': item,
            'SIZE': size,
            'MATERIAL': material,
            'DESCRIPTION': description,
            'Q\'TY': qty_str,
            '(mm/ea)': data['(mm/ea)'],
            'U.WT': data['U.WT'],
            'T.WT': total_weight_str
        })
    
    # TOTAL BOM 시트 생성
    ws_total_bom = wb.create_sheet(title="TOTAL BOM", index=1)  # MTO Data 다음에 위치
    
    # TOTAL BOM 헤더 정의 (LINE NO와 ISO DESCRIPTION 없음)
    total_bom_headers = ['ITEM', 'SIZE', 'MATERIAL', 'DESCRIPTION', 'Q\'TY', '(mm/ea)', 'U.WT', 'T.WT']
    
    # 헤더 작성
    for col, header in enumerate(total_bom_headers, 1):
        cell = ws_total_bom.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.alignment = header_alignment
        cell.border = header_border
    
    # 데이터 작성 (ITEM으로 정렬)
    total_bom_rows_sorted = sorted(total_bom_rows, key=lambda x: x['ITEM'])
    
    # T.WT 합계 계산
    total_weight_sum = 0
    
    for row_idx, data in enumerate(total_bom_rows_sorted, 2):
        for col_idx, header in enumerate(total_bom_headers, 1):
            value = data.get(header, '')
            cell = ws_total_bom.cell(row=row_idx, column=col_idx, value=value)
            cell.font = data_font
            cell.alignment = data_alignment
            cell.border = data_border
            
            # T.WT 값 합계 계산
            if header == 'T.WT' and value:
                try:
                    total_weight_sum += float(value)
                except (ValueError, TypeError):
                    pass
    
    # 합계 행 추가
    sum_row = len(total_bom_rows_sorted) + 2
    
    # "TOTAL" 텍스트를 DESCRIPTION 열에 표시
    desc_col = total_bom_headers.index('DESCRIPTION') + 1
    cell = ws_total_bom.cell(row=sum_row, column=desc_col, value='TOTAL')
    cell.font = Font(size=12, bold=True)
    cell.alignment = header_alignment
    cell.border = header_border
    
    # T.WT 합계 표시
    twt_col = total_bom_headers.index('T.WT') + 1
    if total_weight_sum.is_integer():
        sum_value = str(int(total_weight_sum))
    else:
        sum_value = str(round(total_weight_sum, 1))
    
    cell = ws_total_bom.cell(row=sum_row, column=twt_col, value=sum_value)
    cell.font = Font(size=12, bold=True)
    cell.alignment = header_alignment
    cell.border = header_border
    
    # 나머지 빈 셀에도 테두리 적용
    for col_idx in range(1, len(total_bom_headers) + 1):
        if col_idx != desc_col and col_idx != twt_col:
            cell = ws_total_bom.cell(row=sum_row, column=col_idx, value='')
            cell.border = header_border
    
    # 컬럼 너비 자동 조정
    for column in ws_total_bom.columns:
        max_length = 0
        column_letter = get_column_letter(column[0].column)
        
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        
        adjusted_width = (max_length + 2) * 1.2
        ws_total_bom.column_dimensions[column_letter].width = adjusted_width
    
    # 나머지 시트들 생성 (LINE NO가 있는 시트들)
    for sheet_name in sheet_names:
        if sheet_data[sheet_name]:  # 데이터가 있는 경우만 시트 생성
            ws = wb.create_sheet(title=sheet_name)
            
            # 헤더 작성 (LINE NO와 ISO DESCRIPTION 포함)
            for col, header in enumerate(headers, 1):
                cell = ws.cell(row=1, column=col, value=header)
                cell.font = header_font
                cell.alignment = header_alignment
                cell.border = header_border
            
            # 데이터 작성
            for row_idx, data in enumerate(sheet_data[sheet_name], 2):
                for col_idx, header in enumerate(headers, 1):
                    value = data.get(header, '')
                    cell = ws.cell(row=row_idx, column=col_idx, value=value)
                    cell.font = data_font
                    cell.alignment = data_alignment
                    cell.border = data_border
            
            # 컬럼 너비 자동 조정
            for column in ws.columns:
                max_length = 0
                column_letter = get_column_letter(column[0].column)
                
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                
                adjusted_width = (max_length + 2) * 1.2
                ws.column_dimensions[column_letter].width = adjusted_width
    
    # 파일 저장
    wb.save(excel_path)
    
    print(f"\n=== Excel 파일 저장 완료 ===")
    print(f"파일명: {excel_filename}")
    print(f"경로: {excel_path}")
    print(f"총 {len(all_data)}개의 데이터 저장됨")
    print(f"\n=== ISO DESCRIPTION 추가 ===")
    print(f"- ISO DWG NO 위치에서 X: iso_x-50 ~ iso_x+50, Y: iso_y+25 ~ iso_y+45 범위의 첫 번째 텍스트를 읽어 추가")
    print(f"- LINE NO 뒤에 'ISO DESCRIPTION' 헤더 추가")
    print(f"- LINE NO가 있는 모든 시트에만 ISO DESCRIPTION 포함")
    print(f"- TOTAL BOM 시트에는 LINE NO와 ISO DESCRIPTION 제외")
    print(f"\n=== 스타일 적용 ===")
    print(f"- 헤더: 크기 12, 굵게, 중앙 정렬, 굵은 테두리")
    print(f"- 데이터: 크기 11, 중앙 정렬, 일반 테두리")
    print(f"- 'unset' 값은 '-'로 변경됨")
    print(f"\n=== TOTAL BOM 시트 ===")
    print(f"- ITEM, SIZE, MATERIAL, DESCRIPTION이 같은 항목들의 수량(Q'TY) 합산")
    print(f"- T.WT = Q'TY × U.WT로 재계산")
    print(f"- (mm/ea)가 'MM'인 경우 T.WT = (Q'TY × U.WT) / 1000")
    print(f"- T.WT 합계가 맨 아래 행에 표시됨")
    print(f"- 컬럼 순서: ITEM → SIZE → MATERIAL → DESCRIPTION → Q'TY → (mm/ea) → U.WT → T.WT")
    print(f"\n=== 시트별 데이터 분류 기준 ===")
    print(f"1. PT 헤더 순서별:")
    print(f"   - 첫 번째 PT 헤더 → FAB MAT 시트")
    print(f"   - 두 번째 PT 헤더 → ELEC MAT 시트")
    print(f"2. ITEM 내용별:")
    print(f"   - 'PIPE' 포함 (단, 'SUPPORT' 포함 시 제외) → PIPE 시트")
    print(f"   - 'BOLT', 'NUT', 'GASKET', 'GASK' 포함 → BOLT/NUT 시트")
    print(f"   - 'VALV', 'INST', 'V/V', 'MOV', 'PCV' 포함 → INST 시트")
    print(f"   - 나머지 → FITTING 시트")
    print(f"\n=== 시트별 데이터 결과 ===")
    print(f"- MTO Data: 전체 데이터 ({len(all_data)}행)")
    print(f"- TOTAL BOM: 그룹화된 BOM ({len(total_bom_rows)}행) - ITEM/SIZE/MATERIAL/DESCRIPTION별 수량 합산")
    print(f"  → T.WT 합계: {sum_value}")
    for sheet_name in sheet_names:
        if sheet_data[sheet_name]:
            print(f"- {sheet_name}: {len(sheet_data[sheet_name])}행")