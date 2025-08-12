import ezdxf
import tkinter as tk
from tkinter import filedialog

def select_dxf_file():
    root = tk.Tk()
    root.withdraw()  # GUI창 숨기기
    file_path = filedialog.askopenfilename(
        filetypes=[("DXF Files", "*.dxf")],
        title="DXF 파일을 선택하세요"
    )
    return file_path

def main():
    dxf_path = select_dxf_file()
    if not dxf_path:
        print("DXF 파일을 선택하지 않았습니다.")
        return

    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()

    layer_set = set()
    entity_types = set()
    text_samples = []
    entity_count = {}

    for e in msp:
        layer_set.add(e.dxf.layer)
        etype = e.dxftype()
        entity_types.add(etype)
        entity_count[etype] = entity_count.get(etype, 0) + 1
        # 텍스트 샘플 10개까지 추출
        if etype in ("TEXT", "MTEXT") and len(text_samples) < 10:
            text_samples.append(e.dxf.text if etype == "TEXT" else e.text)

    print("레이어 목록:", sorted(list(layer_set)))
    print("엔티티 타입:", sorted(list(entity_types)))
    print("엔티티별 개수:", entity_count)
    print("텍스트 샘플:", text_samples)

if __name__ == "__main__":
    main()
