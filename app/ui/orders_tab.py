"""发货记录页。"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QMessageBox,
)

from .. import database

HEADERS = ["时间", "状态", "商品", "买家/会话", "详情"]
STATUS_STYLE = {
    "success": "成功",
    "failed": "失败",
    "unmatched": "未匹配",
    "skipped": "跳过",
}


class OrdersTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)

        bar = QHBoxLayout()
        self.btn_refresh = QPushButton("刷新")
        self.btn_clear = QPushButton("清空记录")
        bar.addWidget(self.btn_refresh)
        bar.addWidget(self.btn_clear)
        bar.addStretch()
        lay.addLayout(bar)

        self.table = QTableWidget(0, len(HEADERS))
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 150)
        self.table.setColumnWidth(1, 70)
        self.table.setColumnWidth(2, 160)
        self.table.setColumnWidth(3, 160)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        lay.addWidget(self.table)

        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_clear.clicked.connect(self._clear)
        self.refresh()

    def refresh(self):
        rows = database.list_shipments(500)
        self.table.setRowCount(len(rows))
        for r, s in enumerate(rows):
            self.table.setItem(r, 0, QTableWidgetItem(s["shipped_at"] or ""))
            self.table.setItem(r, 1, QTableWidgetItem(STATUS_STYLE.get(s["status"], s["status"])))
            self.table.setItem(r, 2, QTableWidgetItem(s["goods_name"] or ""))
            self.table.setItem(r, 3, QTableWidgetItem(s["buyer"] or s["session_key"] or ""))
            detail = QTableWidgetItem(s["detail"] or "")
            detail.setToolTip(s["detail"] or "")
            self.table.setItem(r, 4, detail)
        self.table.resizeRowsToContents()

    def _clear(self):
        if QMessageBox.question(self, "确认", "确定清空全部发货记录？") == QMessageBox.Yes:
            database.clear_shipments()
            self.refresh()
