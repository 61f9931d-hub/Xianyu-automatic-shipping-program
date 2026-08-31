"""设置页。"""
import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QSpinBox, QLabel,
    QCheckBox, QLineEdit, QPushButton, QMessageBox, QGroupBox, QFileDialog,
)

from .. import config, database


class SettingsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)

        g1 = QGroupBox("监控设置")
        f1 = QFormLayout(g1)
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(10, 3600)
        self.interval_spin.setSuffix(" 秒")
        self.interval_spin.setToolTip("每隔多久扫描一次聊天页")
        self.auto_start_check = QCheckBox("启动程序时自动开始监控")
        self.default_msg_edit = QLineEdit()
        self.default_msg_edit.setPlaceholderText("留空则未匹配到商品时不发货，仅记录")
        f1.addRow("监控间隔", self.interval_spin)
        f1.addRow("", self.auto_start_check)
        f1.addRow("未匹配兜底内容", self.default_msg_edit)
        f1.addRow("浏览器模式", QLabel("有头模式（闲鱼会拦截无头浏览器，固定使用）"))
        lay.addWidget(g1)

        g2 = QGroupBox("数据")
        f2 = QFormLayout(g2)
        self.dir_label = QLineEdit(str(config.DATA_DIR))
        self.dir_label.setReadOnly(True)
        btn_open = QPushButton("打开数据目录")
        btn_open.clicked.connect(self._open_dir)
        f2.addRow("数据目录", self.dir_label)
        f2.addRow("", btn_open)
        lay.addWidget(g2)

        self.btn_save = QPushButton("保存设置")
        self.btn_save.clicked.connect(self._save)
        lay.addWidget(self.btn_save)
        lay.addStretch()

        self._load()

    def _load(self):
        self.interval_spin.setValue(int(database.get_setting("monitor_interval", "60")))
        self.auto_start_check.setChecked(int(database.get_setting("auto_start", "0")) == 1)
        self.default_msg_edit.setText(database.get_setting("default_message", ""))

    def _save(self):
        database.set_setting("monitor_interval", self.interval_spin.value())
        database.set_setting("headless", 0)  # 闲鱼拦截无头浏览器，固定有头模式
        database.set_setting("auto_start", 1 if self.auto_start_check.isChecked() else 0)
        database.set_setting("default_message", self.default_msg_edit.text().strip())
        QMessageBox.information(self, "已保存", "设置已保存，下次监控轮询生效")

    def _open_dir(self):
        path = str(config.DATA_DIR)
        if os.path.isdir(path):
            os.startfile(path)
        else:
            QMessageBox.warning(self, "提示", f"目录不存在: {path}")
