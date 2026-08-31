"""商品管理页。"""
import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QMessageBox, QFileDialog,
)

from .. import database
from .goods_dialog import GoodsDialog

HEADERS = ["ID", "商品名称", "价格", "匹配关键词", "发货内容", "状态", "创建时间"]


class GoodsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)

        bar = QHBoxLayout()
        self.btn_add = QPushButton("新增")
        self.btn_edit = QPushButton("编辑")
        self.btn_del = QPushButton("删除")
        self.btn_export = QPushButton("导出")
        self.btn_import = QPushButton("导入")
        for b in (self.btn_add, self.btn_edit, self.btn_del, self.btn_export, self.btn_import):
            bar.addWidget(b)
        bar.addStretch()
        lay.addLayout(bar)

        self.table = QTableWidget(0, len(HEADERS))
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 50)
        self.table.setColumnWidth(1, 150)
        self.table.setColumnWidth(2, 70)
        self.table.setColumnWidth(3, 160)
        self.table.setColumnWidth(4, 230)
        self.table.setColumnWidth(5, 60)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.doubleClicked.connect(lambda _: self._edit_selected())
        lay.addWidget(self.table)

        self.btn_add.clicked.connect(self._add)
        self.btn_edit.clicked.connect(self._edit_selected)
        self.btn_del.clicked.connect(self._delete_selected)
        self.btn_export.clicked.connect(self._export)
        self.btn_import.clicked.connect(self._import)

        self.refresh()

    # ---------- 数据 ----------
    def refresh(self):
        rows = database.list_goods()
        self.table.setRowCount(len(rows))
        for r, g in enumerate(rows):
            self.table.setItem(r, 0, QTableWidgetItem(str(g["id"])))
            self.table.setItem(r, 1, QTableWidgetItem(g["name"]))
            price = QTableWidgetItem(("¥" + g["price"]) if (g.get("price") or "").strip() else "")
            price.setToolTip("商品价格，用于订单价格匹配")
            self.table.setItem(r, 2, price)
            self.table.setItem(r, 3, QTableWidgetItem(g["keywords"]))
            content_item = QTableWidgetItem(g["content"].replace("\n", " "))
            content_item.setToolTip(g["content"])
            self.table.setItem(r, 4, content_item)
            self.table.setItem(r, 5, QTableWidgetItem("启用" if g["enabled"] else "停用"))
            self.table.setItem(r, 6, QTableWidgetItem(g["created_at"] or ""))
            self.table.item(r, 0).setTextAlignment(Qt.AlignCenter)
        self.table.resizeRowsToContents()

    def _selected_row(self) -> int:
        rows = self.table.selectionModel().selectedRows()
        return rows[0].row() if rows else -1

    def _selected_goods(self) -> dict | None:
        row = self._selected_row()
        if row < 0:
            return None
        gid = int(self.table.item(row, 0).text())
        for g in database.list_goods():
            if g["id"] == gid:
                return g
        return None

    # ---------- 操作 ----------
    def _add(self):
        dlg = GoodsDialog(self)
        if dlg.exec() == GoodsDialog.Accepted:
            v = dlg.values()
            database.add_goods(v["name"], v["keywords"], v["content"], v.get("price", ""))
            self.refresh()

    def _edit_selected(self):
        g = self._selected_goods()
        if not g:
            QMessageBox.information(self, "提示", "请先选择一行商品")
            return
        dlg = GoodsDialog(self, g)
        if dlg.exec() == GoodsDialog.Accepted:
            v = dlg.values()
            database.update_goods(g["id"], v["name"], v["keywords"], v["content"], v["enabled"], v.get("price", ""))
            self.refresh()

    def _delete_selected(self):
        g = self._selected_goods()
        if not g:
            QMessageBox.information(self, "提示", "请先选择一行商品")
            return
        if QMessageBox.question(self, "确认删除", f"确定删除商品「{g['name']}」？") == QMessageBox.Yes:
            database.delete_goods(g["id"])
            self.refresh()

    def _export(self):
        path, _ = QFileDialog.getSaveFileName(self, "导出商品", "goods_backup.json", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(database.export_goods())
            QMessageBox.information(self, "导出成功", f"已导出到:\n{path}")
        except Exception as e:
            QMessageBox.warning(self, "导出失败", str(e))

    def _import(self):
        path, _ = QFileDialog.getOpenFileName(self, "导入商品", "", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                count = database.import_goods(f.read())
            self.refresh()
            QMessageBox.information(self, "导入成功", f"已导入 {count} 个商品")
        except json.JSONDecodeError:
            QMessageBox.warning(self, "导入失败", "文件不是有效的 JSON 格式")
        except Exception as e:
            QMessageBox.warning(self, "导入失败", str(e))
