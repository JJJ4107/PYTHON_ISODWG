import clr
import csv
import sys
import os
import tkinter as tk
from tkinter import filedialog

# --------- [1] Autodesk API 경로 추가 ---------
api_path = r"C:\Program Files\Autodesk\Navisworks Manage 2024\api"
sys.path.append(api_path)

# --------- [2] .NET 어셈블리 참조 ---------
try:
    clr.AddReference("Autodesk.Navisworks.Api")
    clr.AddReference("Autodesk.Navisworks.Timeliner")
    clr.AddReference("Autodesk.Navisworks.Api.Interop.ComApi")
except Exception as e:
    print("❌ DLL 로딩 실패: Autodesk API DLL을 찾을 수 없습니다.")
    print("📌 DLL 경로 확인: ", api_path)
    print("🔧 예외 메시지:", e)
    sys.exit(1)

# --------- [3] 네임스페이스 가져오기 ---------
from Autodesk.Navisworks.Api import *
from Autodesk.Navisworks.Api.DocumentParts import *
from Autodesk.Navisworks.Api.Interop.ComApi import InwOpState10, ComApiBridge

# --------- [4] 파일 선택 함수 ---------
def select_file(title, filetypes):
    root = tk.Tk()
    root.withdraw()
    return filedialog.askopenfilename(title=title, filetypes=filetypes)

# --------- [5] CSV에서 이름 목록 읽기 ---------
def read_csv_item_names(csv_path):
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        return [row['Name'].strip() for row in reader]

# --------- [6] 색상 덮어쓰기 함수 ---------
def override_color(doc, model_item, color):
    overrides = doc.Models.OverrideAppearance
    appearance = overrides.GetAppearanceOverride(model_item) or Appearance()
    appearance.Color = color
    overrides.SetAppearanceOverride(model_item, appearance)

# --------- [7] 모델 전체 항목 탐색 ---------
def search_all_items(models):
    def recurse(item):
        result = []
        for child in item.Children:
            result.extend(recurse(child))
        result.append(item)
        return result

    all_items = []
    for model in models:
        all_items.extend(recurse(model.RootItem))
    return all_items

# --------- [8] 메인 실행 ---------
def main():
    print("📂 Navisworks NWD 파일과 CSV를 선택하세요.")
    nwd_path = select_file("NWD 파일을 선택하세요", [("Navisworks files", "*.nwd")])
    if not nwd_path:
        print("⚠️ NWD 파일이 선택되지 않았습니다.")
        return

    csv_path = select_file("CSV 파일을 선택하세요", [("CSV files", "*.csv")])
    if not csv_path:
        print("⚠️ CSV 파일이 선택되지 않았습니다.")
        return

    item_names = read_csv_item_names(csv_path)
    print(f"✅ CSV에서 {len(item_names)}개의 항목을 읽음.")

    # -------- Navisworks API 실행 --------
    print("🧩 Navisworks 파일 열기 중...")
    state = ComApiBridge.State
    state10 = clr.Convert(state, InwOpState10)
    state10.OpenFile(nwd_path)

    doc = Application.ActiveDocument
    if doc is None:
        print("❌ Navisworks 문서를 열 수 없습니다. Navisworks가 실행 중인지 확인하세요.")
        return

    all_items = search_all_items(doc.Models)
    matched_count = 0

    for item in all_items:
        name = item.DisplayName.strip()
        if name in item_names:
            override_color(doc, item, Color.Red)
            matched_count += 1

    print(f"🎨 {matched_count}개의 항목을 빨간색으로 설정 완료.")

if __name__ == "__main__":
    main()
