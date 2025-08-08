import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PyPDF2 import PdfMerger, PdfReader
from datetime import datetime
import threading

class PDFMergerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("PDF 병합 도구")
        self.root.geometry("800x600")
        
        # 우선순위 이름
        self.priority_names = ["김진상", "이봉수", "신기복", "하동주", "이상욱", "심현영"]
        
        # UI 구성
        self.setup_ui()
        
    def setup_ui(self):
        # 상단 프레임
        top_frame = ttk.Frame(self.root, padding="10")
        top_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 디렉토리 선택 버튼
        self.select_btn = ttk.Button(
            top_frame, 
            text="📁 디렉토리 선택", 
            command=self.select_directory,
            width=20
        )
        self.select_btn.grid(row=0, column=0, padx=5, pady=5)
        
        # 선택된 경로 표시
        self.path_label = ttk.Label(top_frame, text="선택된 디렉토리: 없음")
        self.path_label.grid(row=0, column=1, padx=5, pady=5, sticky=tk.W)
        
        # 중간 프레임 - 파일 목록
        middle_frame = ttk.LabelFrame(self.root, text="PDF 파일 목록", padding="10")
        middle_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=10, pady=5)
        
        # 스크롤바가 있는 텍스트 위젯
        self.file_text = tk.Text(middle_frame, height=15, width=70)
        scrollbar = ttk.Scrollbar(middle_frame, command=self.file_text.yview)
        self.file_text.configure(yscrollcommand=scrollbar.set)
        
        self.file_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        # 하단 프레임
        bottom_frame = ttk.Frame(self.root, padding="10")
        bottom_frame.grid(row=2, column=0, sticky=(tk.W, tk.E))
        
        # 병합 버튼
        self.merge_btn = ttk.Button(
            bottom_frame,
            text="🔗 PDF 병합 시작",
            command=self.merge_pdfs,
            width=20,
            state=tk.DISABLED
        )
        self.merge_btn.grid(row=0, column=0, padx=5, pady=5)
        
        # 진행 상태 표시
        self.status_label = ttk.Label(bottom_frame, text="대기 중...")
        self.status_label.grid(row=0, column=1, padx=5, pady=5)
        
        # 진행률 바
        self.progress = ttk.Progressbar(
            bottom_frame,
            length=200,
            mode='indeterminate'
        )
        self.progress.grid(row=1, column=0, columnspan=2, padx=5, pady=5)
        
        # 우선순위 설명
        priority_frame = ttk.LabelFrame(self.root, text="병합 우선순위", padding="10")
        priority_frame.grid(row=3, column=0, sticky=(tk.W, tk.E), padx=10, pady=5)
        
        priority_text = "우선순위: " + " → ".join(self.priority_names)
        priority_text += "\n※ 이봉수님 파일은 -1, -3, -2 순서로 정렬됩니다."
        ttk.Label(priority_frame, text=priority_text).pack()
        
        # 그리드 가중치 설정
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)
        middle_frame.columnconfigure(0, weight=1)
        middle_frame.rowconfigure(0, weight=1)
        
    def select_directory(self):
        """디렉토리 선택 다이얼로그"""
        directory = filedialog.askdirectory(title="PDF 파일이 있는 폴더를 선택하세요")
        
        if directory:
            self.selected_directory = directory
            self.path_label.config(text=f"선택된 디렉토리: {directory}")
            self.scan_directory()
            
    def scan_directory(self):
        """선택된 디렉토리의 PDF 파일 스캔"""
        self.file_text.delete(1.0, tk.END)
        
        pdf_files = [f for f in os.listdir(self.selected_directory) 
                    if f.lower().endswith('.pdf')]
        
        if not pdf_files:
            self.file_text.insert(tk.END, "❌ PDF 파일이 없습니다.")
            self.merge_btn.config(state=tk.DISABLED)
            return
            
        # 필수 파일 확인
        has_kim = any("김진상" in f for f in pdf_files)
        has_lee = any("이봉수" in f for f in pdf_files)
        
        if not (has_kim and has_lee):
            self.file_text.insert(tk.END, "⚠️ 경고: 김진상 또는 이봉수 파일이 없습니다.\n")
            self.file_text.insert(tk.END, "계속 진행하시겠습니까?\n\n")
            
        # 병합될 순서대로 파일 표시
        sorted_files = self.get_sorted_files(pdf_files)
        
        self.file_text.insert(tk.END, f"📋 총 {len(pdf_files)}개의 PDF 파일 발견\n")
        self.file_text.insert(tk.END, "="*50 + "\n")
        self.file_text.insert(tk.END, "병합 순서:\n\n")
        
        for i, file in enumerate(sorted_files, 1):
            # 파일 크기 확인
            file_path = os.path.join(self.selected_directory, file)
            file_size = os.path.getsize(file_path) / 1024 / 1024  # MB
            
            # 우선순위 표시
            priority_mark = ""
            for idx, name in enumerate(self.priority_names):
                if name in file:
                    priority_mark = f" [우선순위 {idx+1}]"
                    break
                    
            self.file_text.insert(tk.END, f"{i:3d}. {file} ({file_size:.1f}MB){priority_mark}\n")
            
        # 병합 버튼 활성화
        self.merge_btn.config(state=tk.NORMAL)
        self.pdf_files = sorted_files
        
    def get_sorted_files(self, pdf_files):
        """우선순위에 따라 파일 정렬"""
        # 이봉수 파일 특별 처리
        lee_bongsu_files = sorted(
            [f for f in pdf_files if "이봉수" in f],
            key=lambda f: 0 if "-1" in f else 1 if "-3" in f else 2 if "-2" in f else 3
        )
        
        # 정렬 키 함수
        def sort_key(filename):
            for i, name in enumerate(self.priority_names):
                if name in filename:
                    return (i, filename)
            return (len(self.priority_names), filename)
        
        # 이봉수 제외한 파일들
        other_files = [f for f in pdf_files if "이봉수" not in f]
        sorted_others = sorted(other_files, key=sort_key)
        
        # 최종 리스트 구성
        final_list = []
        for name in self.priority_names:
            if name == "이봉수":
                final_list.extend(lee_bongsu_files)
            else:
                final_list.extend([f for f in sorted_others if name in f])
                
        # 우선순위에 없는 파일들 추가
        final_list.extend([f for f in sorted_others 
                          if not any(name in f for name in self.priority_names)])
        
        return final_list
        
    def merge_pdfs(self):
        """PDF 병합 실행"""
        # 결과 파일명
        folder_name = os.path.basename(self.selected_directory)
        result_name = f"주간통합_{folder_name}.pdf"
        output_path = os.path.join(self.selected_directory, result_name)
        
        # 이미 존재하는지 확인
        if os.path.exists(output_path):
            response = messagebox.askyesno(
                "파일 존재",
                f"{result_name} 파일이 이미 존재합니다.\n덮어쓰시겠습니까?"
            )
            if not response:
                return
                
        # 병합 작업을 별도 스레드에서 실행
        self.merge_btn.config(state=tk.DISABLED)
        self.progress.start()
        self.status_label.config(text="병합 중...")
        
        thread = threading.Thread(
            target=self._merge_worker,
            args=(output_path,)
        )
        thread.start()
        
    def _merge_worker(self, output_path):
        """병합 작업 수행 (워커 스레드)"""
        try:
            merger = PdfMerger()
            total_files = len(self.pdf_files)
            
            for i, pdf in enumerate(self.pdf_files):
                pdf_path = os.path.join(self.selected_directory, pdf)
                
                # UI 업데이트
                self.root.after(0, self.update_status, 
                              f"처리 중... ({i+1}/{total_files}): {pdf}")
                
                # PDF 유효성 검사
                try:
                    with open(pdf_path, 'rb') as f:
                        PdfReader(f)
                    merger.append(pdf_path)
                except Exception as e:
                    print(f"⚠️ {pdf} 추가 실패: {e}")
                    continue
                    
            # 병합 파일 저장
            merger.write(output_path)
            merger.close()
            
            # 완료 메시지
            self.root.after(0, self.merge_complete, output_path)
            
        except Exception as e:
            self.root.after(0, self.merge_error, str(e))
            
    def update_status(self, message):
        """상태 업데이트"""
        self.status_label.config(text=message)
        
    def merge_complete(self, output_path):
        """병합 완료 처리"""
        self.progress.stop()
        self.merge_btn.config(state=tk.NORMAL)
        self.status_label.config(text="병합 완료!")
        
        file_size = os.path.getsize(output_path) / 1024 / 1024  # MB
        
        messagebox.showinfo(
            "병합 완료",
            f"PDF 병합이 완료되었습니다!\n\n"
            f"파일명: {os.path.basename(output_path)}\n"
            f"크기: {file_size:.1f}MB\n"
            f"위치: {output_path}"
        )
        
        # 파일 목록 새로고침
        self.scan_directory()
        
    def merge_error(self, error_msg):
        """병합 오류 처리"""
        self.progress.stop()
        self.merge_btn.config(state=tk.NORMAL)
        self.status_label.config(text="병합 실패")
        
        messagebox.showerror("오류", f"PDF 병합 중 오류가 발생했습니다:\n{error_msg}")

def main():
    root = tk.Tk()
    app = PDFMergerGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()