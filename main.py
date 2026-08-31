"""闲鱼自动发货工具 - 程序入口"""
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from app.database import init_db


def main():
    try:
        init_db()
    except Exception as e:
        QMessageBox.critical(None, "启动失败", f"初始化数据库失败：\n{e}")
        return 1

    from app import logger

    # 启动标记：方便确认运行的是最新版本
    logger.info("=" * 46)
    logger.info("闲鱼自动发货工具 启动 (build 20260822-01)")
    logger.info("=" * 46)

    app = QApplication(sys.argv)
    app.setApplicationName("闲鱼自动发货")

    try:
        # 延迟导入，确保数据库就绪
        from app.ui.main_window import MainWindow

        win = MainWindow()
    except Exception as e:
        logger.error(f"程序初始化失败: {e}")
        QMessageBox.critical(
            None, "启动失败",
            f"程序初始化失败：\n{e}\n\n详细信息已写入 data/logs/ 下的日志文件。\n可将日志内容反馈给开发者排查。",
        )
        return 1

    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
