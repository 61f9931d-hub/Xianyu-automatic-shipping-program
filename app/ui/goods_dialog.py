"""商品编辑对话框。"""
from PySide6.QtWidgets import (
    QDialog, QFormLayout, QLineEdit, QPlainTextEdit, QCheckBox,
    QDialogButtonBox, QVBoxLayout, QLabel,
)


class GoodsDialog(QDialog):
    def __init__(self, parent=None, goods: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("编辑商品" if goods else "新增商品")
        self.setMinimumWidth(480)

        self._goods = goods or {}
        lay = QVBoxLayout(self)

        tip = QLabel(
            "商品价格：填闲鱼售价（如 0.30），系统按订单价格自动匹配该商品，"
            "多个商品请设置不同价格以确保匹配准确。\n"
            "匹配关键词：价格匹配不到时按关键词兜底（PC 版聊天窗口不显示商品标题，"
            "关键词可能无效，建议优先用价格匹配）。\n"
            "发货内容：发送给买家的文本（网盘链接 + 提取码）。"
        )
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#666; font-size:12px;")
        lay.addWidget(tip)

        form = QFormLayout()
        self.name_edit = QLineEdit()
        self.price_edit = QLineEdit()
        self.price_edit.setPlaceholderText("如 0.30，留空则不用价格匹配")
        self.keywords_edit = QLineEdit()
        self.content_edit = QPlainTextEdit()
        self.content_edit.setFixedHeight(90)
        self.enabled_check = QCheckBox("启用该商品（启用后才会自动发货）")
        self.enabled_check.setChecked(True)

        form.addRow("商品名称 *", self.name_edit)
        form.addRow("商品价格", self.price_edit)
        form.addRow("匹配关键词", self.keywords_edit)
        form.addRow("发货内容 *", self.content_edit)
        form.addRow("", self.enabled_check)
        lay.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText("保存")
        btns.button(QDialogButtonBox.Cancel).setText("取消")
        btns.accepted.connect(self._on_ok)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

        if goods:
            self.name_edit.setText(goods.get("name", ""))
            self.price_edit.setText(goods.get("price", ""))
            self.keywords_edit.setText(goods.get("keywords", ""))
            self.content_edit.setPlainText(goods.get("content", ""))
            self.enabled_check.setChecked(bool(goods.get("enabled", 1)))

    def _on_ok(self):
        if not self.name_edit.text().strip():
            self.name_edit.setFocus()
            return
        if not self.content_edit.toPlainText().strip():
            self.content_edit.setFocus()
            return
        self.accept()

    def values(self) -> dict:
        return {
            "name": self.name_edit.text().strip(),
            "price": self.price_edit.text().strip(),
            "keywords": self.keywords_edit.text().strip(),
            "content": self.content_edit.toPlainText().strip(),
            "enabled": self.enabled_check.isChecked(),
        }
