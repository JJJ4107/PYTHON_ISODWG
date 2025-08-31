import os
import subprocess
import shutil

def convert_dwg_to_dxf_2013_with_suffix(oda_path):
    current_dir = os.getcwd()
    temp_dir = os.path.join(current_dir, "__temp_convert__")
    output_dir = os.path.join(current_dir, "2013DXF")

    # 출력 폴더 준비
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # 임시 폴더 생성 (ODA는 폴더 전체를 변환하므로 별도 사용)
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)

    # 변환 대상 DWG만 복사 (예: -A.DWG 제외)
    dwg_files = [
        f for f in os.listdir(current_dir)
        if f.lower().endswith(".dwg") and not f.endswith("-A.DWG")
    ]

    if not dwg_files:
        print("변환할 DWG 파일이 없습니다.")
        return

    for dwg in dwg_files:
        shutil.copy2(os.path.join(current_dir, dwg), os.path.join(temp_dir, dwg))

    # ODA 변환 실행 (temp → output)
    print("\n[DXF 변환 시작]")
    subprocess.run([
        oda_path,
        temp_dir,      # 입력 폴더
        output_dir,    # 출력 폴더
        "ACAD2013",    # DXF 버전
        "DXF",         # 출력 포맷
        "0",           # Binary
        "0"            # 하위 폴더 포함 안 함
    ], check=True)

    # 변환된 파일 이름 바꾸기: 파일명.dxf → 파일명-A.dxf
    print("\n[파일명 변경 중]")
    for dwg in dwg_files:
        base = os.path.splitext(dwg)[0]
        src_dxf = os.path.join(output_dir, base + ".dxf")
        dst_dxf = os.path.join(output_dir, base + "-A.dxf")
        if os.path.exists(src_dxf):
            os.rename(src_dxf, dst_dxf)
            print(f"{base}.dxf → {base}-A.dxf")

    # 임시 폴더 삭제
    shutil.rmtree(temp_dir)
    print("\n✅ 변환 완료: 2013DXF 폴더에 -A.dxf 파일로 저장되었습니다.")

if __name__ == "__main__":
    oda_converter_path = r"C:\Program Files\ODA\ODAFileConverter 26.4.0\ODAFileConverter.exe"

    if os.path.exists(oda_converter_path):
        convert_dwg_to_dxf_2013_with_suffix(oda_converter_path)
    else:
        print("❌ ODAFileConverter.exe 경로가 올바르지 않습니다. 다시 확인해주세요.")
