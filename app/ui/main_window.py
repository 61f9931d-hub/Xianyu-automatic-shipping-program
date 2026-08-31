"""主窗口：组装各页签、监控线程、登录线程。"""
import os

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QPushButton, QLabel, QPlainTextEdit, QMessageBox, QSplitter,
    QApplication,
)

from .. import config, database, logger
from ..monitor_worker import MonitorWorker
from ..xianyu_client import open_login_window
from .goods_tab import GoodsTab
from .orders_tab import OrdersTab
from .settings_tab import SettingsTab


class LoginThread(QThread):
    done = Signal(bool)

    def run(self):
        ok = open_login_window()
        self.done.emit(ok)


class MainWindow(QMainWindow):
    log_signal = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("闲鱼自动发货工具")
        self.resize(980, 720)
        self.worker = MonitorWorker(self)
        self.login_thread = None

        self._build_ui()
        self._connect()

        # 日志回调（监控线程会调用，跨线程经信号转发）
        logger.set_ui_callback(lambda line: self.log_signal.emit(line))
        self.log_signal.connect(self._append_log)

        if int(database.get_setting("auto_start", "0")) == 1:
            self._start_monitor()

    # ---------- UI ----------
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)

        # 顶栏
        top = QHBoxLayout()
        self.status_dot = QLabel("●")
        self.status_dot.setStyleSheet("color:#999; font-size:16px;")
        self.status_label = QLabel("未启动")
        self.status_label.setStyleSheet("font-size:13px;")
        self.btn_start = QPushButton("启动监控")
        self.btn_stop = QPushButton("停止监控")
        self.btn_stop.setEnabled(False)
        self.btn_login = QPushButton("登录闲鱼")
        self.btn_open_data = QPushButton("数据目录")
        top.addWidget(self.status_dot)
        top.addWidget(self.status_label)
        top.addStretch()
        top.addWidget(self.btn_start)
        top.addWidget(self.btn_stop)
        top.addWidget(self.btn_login)
        top.addWidget(self.btn_open_data)
        root.addLayout(top)

        # 页签 + 日志
        splitter = QSplitter(Qt.Vertical)
        self.tabs = QTabWidget()
        self.goods_tab = GoodsTab()
        self.orders_tab = OrdersTab()
        self.settings_tab = SettingsTab()
        self.tabs.addTab(self.goods_tab, "商品管理")
        self.tabs.addTab(self.orders_tab, "发货记录")
        self.tabs.addTab(self.settings_tab, "设置")

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(2000)
        self.log_view.setPlaceholderText("运行日志…")

        splitter.addWidget(self.tabs)
        splitter.addWidget(self.log_view)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([520, 160])
        root.addWidget(splitter, 1)

    def _connect(self):
        self.btn_start.clicked.connect(self._start_monitor)
        self.btn_stop.clicked.connect(self._stop_monitor)
        self.btn_login.clicked.connect(self._login)
        self.btn_open_data.clicked.connect(self._open_data_dir)
        self.worker.log.connect(self._append_log)
        self.worker.status.connect(self._set_status)
        self.worker.order_event.connect(self._on_order_event)
        self.worker.login_needed.connect(self._on_login_needed)

    # ---------- 日志 ----------
    def _append_log(self, line: str):
        self.log_view.appendPlainText(line)
        sb = self.log_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    # ---------- 状态 ----------
    def _set_status(self, text: str, color: str | None = None):
        self.status_label.setText(text)
        if color is None:
            color = {"需要重新登录": "#e67e22", "已停止": "#999", "浏览器启动失败": "#e74c3c"}.get(text, "#2ecc71")
        self.status_dot.setStyleSheet(f"color:{color}; font-size:16px;")

    def _on_order_event(self, ev: dict):
        self.orders_tab.refresh()
        status = ev.get("status", "")
        if status == "success":
            self._append_log(f"【自动发货】{ev.get('goods','')} → {ev.get('buyer','')}")
            QApplication.alert(self, 3000)
        elif status == "failed":
            self._append_log(f"【发货失败】{ev.get('goods','')} → {ev.get('buyer','')}")
        elif status == "unmatched":
            self._append_log("【未匹配】出现无法匹配商品的付款订单，请补充商品关键词")

    # ---------- 按钮行为 ----------
    def _start_monitor(self):
        if self.worker.isRunning():
            return
        self.worker.start_monitor()
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)

    def _stop_monitor(self):
        self.worker.stop_monitor()
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self._set_status("已停止", "#999")

    def _login(self):
        if self.login_thread and self.login_thread.isRunning():
            QMessageBox.information(self, "提示", "登录窗口已打开，请先完成扫码")
            return
        self._set_status("等待扫码登录…", "#e67e22")
        self.login_thread = LoginThread(self)
        self.login_thread.done.connect(self._on_login_done)
        self.login_thread.start()

    def _on_login_done(self, ok: bool):
        if ok:
            self._set_status("登录窗口已关闭", "#2ecc71")
            self._append_log("登录流程结束。若已扫码登录，可点击「启动监控」开始自动发货")
        else:
            self._set_status("登录异常", "#e74c3c")
            QMessageBox.warning(
                self, "登录窗口启动失败",
                "无法打开浏览器登录窗口。\n\n"
                "常见原因与处理：\n"
                "1. 安全软件（360 / 电脑管家 / 杀毒）拦截了浏览器驱动\n"
                "   → 请将整个项目目录加入安全软件白名单后重试\n"
                "2. 系统浏览器异常或未安装 Edge / Chrome\n"
                "   → 请安装 Microsoft Edge 后重试\n"
                "3. 其他原因\n"
                "   → 详细错误已记录在 data/logs/ 日志中，可发给开发者排查",
            )

    def _on_login_needed(self):
        QMessageBox.warning(
            self, "需要登录",
            "闲鱼登录已失效或尚未登录。\n请点击「登录闲鱼」，在打开的浏览器中扫码登录，\n登录后关闭浏览器窗口，再点击「启动监控」。",
        )
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)

    def _open_data_dir(self):
        if os.path.isdir(str(config.DATA_DIR)):
            os.startfile(str(config.DATA_DIR))

    # ---------- 退出 ----------
    def closeEvent(self, event):
        if self.worker.isRunning():
            self.worker.stop_monitor()
        event.accept()
