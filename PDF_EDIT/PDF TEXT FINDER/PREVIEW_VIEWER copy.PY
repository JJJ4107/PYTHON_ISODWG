import sys
import fitz
import os
from PyQt5.QtWidgets import QApplication, QLabel, QScrollArea, QWidget, QVBoxLayout
from PyQt5.QtGui import QPixmap, QImage
from PyQt5.QtCore import Qt

class PDFPreview(QWidget):
    def __init__(self, pdf_path, page_num):
        super().__init__()
        self.setWindowTitle("PDF 미리보기 (확대/축소+이동)")
        self.pdf_path = pdf_path  # 삭제를 위해 보관
        doc = fitz.open(pdf_path)
        page = doc.load_page(page_num)
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(img)

        self._base_pixmap = pixmap
        self._zoom = 1.0
        self.label = QLabel(self)
        self.label.setPixmap(self._base_pixmap)
        self.label.setAlignment(Qt.AlignCenter)
        self.scroll = QScrollArea(self)
        self.scroll.setWidget(self.label)
        self.scroll.setWidgetResizable(True)
        layout = QVBoxLayout(self)
        layout.addWidget(self.scroll)
        self.setLayout(layout)
        self.resize(2000, 1600)
        self._drag_pos = None

    def closeEvent(self, event):
        try:
            os.remove(self.pdf_path)
        except Exception:
            pass
        event.accept()

    def wheelEvent(self, event):
        angle = event.angleDelta().y()
        if angle > 0:
            self.zoom_in()
        else:
            self.zoom_out()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Plus, Qt.Key_Equal):
            self.zoom_in()
        elif event.key() == Qt.Key_Minus:
            self.zoom_out()

    def zoom_in(self):
        self._zoom *= 1.2
        self.update_zoom()

    def zoom_out(self):
        self._zoom /= 1.2
        self.update_zoom()

    def update_zoom(self):
        pixmap = self._base_pixmap.scaled(
            self._base_pixmap.size() * self._zoom, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.label.setPixmap(pixmap)
        self.label.resize(pixmap.size())

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.pos()

    def mouseMoveEvent(self, event):
        if self._drag_pos:
            delta = event.pos() - self._drag_pos
            self._drag_pos = event.pos()
            h_scroll = self.scroll.horizontalScrollBar()
            v_scroll = self.scroll.verticalScrollBar()
            h_scroll.setValue(h_scroll.value() - delta.x())
            v_scroll.setValue(v_scroll.value() - delta.y())

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf_path", help="PDF 파일 경로")
    parser.add_argument("page_num", type=int, help="페이지 번호 (0-base)")
    args = parser.parse_args()
    app = QApplication(sys.argv)
    preview = PDFPreview(args.pdf_path, args.page_num)
    preview.show()
    app.exec_()

if __name__ == "__main__":
    main()
