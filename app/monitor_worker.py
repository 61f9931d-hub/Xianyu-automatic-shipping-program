"""后台监控线程：定时扫描闲鱼聊天页，识别付款订单并自动发货。"""
import time

from PySide6.QtCore import QThread, Signal

from . import config, database, logger
from .xianyu_client import XianyuClient

# 会话处理结果状态
ST_SUCCESS = "success"
ST_UNMATCHED = "unmatched"
ST_FAILED = "failed"
ST_SKIPPED = "skipped"

# 已退款/已关闭订单的强特征系统消息文案
_REFUND_PHRASES = ("你关闭了订单", "钱款已原路退返", "订单已关闭", "已退款成功", "退款成功", "订单已取消")


def _is_current_order_refunded(body_text: str) -> bool:
    """判断「当前订单」是否已退款。

    同一会话可能有多笔交易的历史消息，退款记录可能属于更早的订单。
    因此只检测「最近一次付款消息之后」的文本，避免历史退款误伤当前订单。
    """
    if not body_text:
        return False
    last_pos = -1
    for marker in config.PAYMENT_MARKERS:
        idx = body_text.rfind(marker)
        if idx > last_pos:
            last_pos = idx
    tail = body_text[last_pos:] if last_pos >= 0 else body_text
    return any(p in tail for p in _REFUND_PHRASES)


class MonitorWorker(QThread):
    # 信号：日志行 / 状态文本 / 订单事件 / 需要登录
    log = Signal(str)
    status = Signal(str)
    order_event = Signal(dict)
    login_needed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False
        self._client = None

    # ---------- 控制 ----------
    def start_monitor(self):
        if self.isRunning():
            return
        self._running = True
        self.start()

    def stop_monitor(self):
        self._running = False
        # 线程阻塞在 sleep 时也能较快退出
        self.wait(5000)

    # ---------- 主循环 ----------
    def run(self):
        logger.info("监控线程启动")
        self.status.emit("正在启动浏览器…")
        # 注意：闲鱼会拦截无头浏览器（页面显示"非法访问"），必须使用有头模式
        self._client = XianyuClient(headless=False)
        try:
            self._client.start()
        except Exception as e:
            logger.error(f"浏览器启动失败: {e}")
            self.status.emit("浏览器启动失败")
            self._running = False
            return

        while self._running:
            try:
                self._tick()
            except Exception as e:
                logger.error(f"监控循环异常: {e}")
                # 异常后冷却几秒再重试，避免热循环（导航中断等问题通常可自愈）
                for _ in range(5):
                    if not self._running:
                        break
                    time.sleep(1)
            if self._running:
                self._sleep_interval()

        try:
            self._client.stop()
        except Exception:
            pass
        self.status.emit("已停止")
        logger.info("监控线程已退出")

    def _sleep_interval(self):
        try:
            interval = int(database.get_setting("monitor_interval", "60"))
        except ValueError:
            interval = 60
        # 分小段 sleep，便于快速响应停止指令
        for _ in range(max(1, interval // 1)):
            if not self._running:
                return
            time.sleep(1)

    def _tick(self):
        client = self._client
        self.status.emit("正在检查新订单…")

        if not client.open_im():
            self.status.emit("需要重新登录")
            self.login_needed.emit()
            self._running = False
            return

        sessions = client.find_paid_sessions()
        if not sessions:
            logger.info("未发现新的付款订单")
            self.status.emit("运行中（暂无新订单）")
            return

        logger.info(f"发现 {len(sessions)} 个付款待发货会话")
        self.status.emit(f"发现 {len(sessions)} 个待发货订单，正在处理…")

        for s in sessions:
            if not self._running:
                return
            self._handle_session(client, s)
            # 回到消息列表，刷新会话视图
            client.back_to_list()

        self.status.emit("本轮处理完成")

    def _handle_session(self, client, session):
        entry = client.enter_session(session)
        if entry is None:
            return

        session_key = entry["session_key"]
        if database.shipment_exists(session_key):
            logger.info(f"会话已处理过，跳过: {session['key'][:40]}")
            self.order_event.emit({"status": ST_SKIPPED, "detail": "重复会话，跳过"})
            return

        # 匹配商品：优先按价格匹配（PC 版聊天窗口不显示商品标题，价格是最可靠信号）
        body_text = entry.get("body_text", "") or ""
        card_text = entry.get("card_text", "") or ""
        card_info = entry.get("card_info", "") or ""
        search_text = (card_text + "\n" + body_text + "\n" + card_info)[:4000]
        order_price = database.extract_price(search_text)
        goods = database.match_goods(search_text)
        buyer = _guess_buyer(card_text)
        body_preview = " ".join(body_text.split())[:150] or "(空)"
        card_preview = " ".join(card_info.split())[:150] or "(无)"
        price_desc = f"¥{order_price}" if order_price is not None else "(未提取到价格)"

        # 已退款/已关闭订单不发货（只检测最近付款消息之后，避免历史退款误伤当前订单）
        if _is_current_order_refunded(body_text):
            logger.warn(f"订单已退款/关闭，跳过发货: {session['key'][:40]}")
            database.add_shipment(session_key, buyer, "(已退款)", ST_SKIPPED, "订单已退款/关闭")
            self.order_event.emit({"status": ST_SKIPPED, "buyer": buyer, "goods": "(已退款)", "session": session_key})
            return

        if goods is None:
            default_msg = database.get_setting("default_message", "").strip()
            if default_msg:
                logger.warn(f"未匹配到商品，使用兜底内容发货: {session['key'][:40]}")
                ok = client.send_text(default_msg)
                status = ST_SUCCESS if ok else ST_FAILED
                database.add_shipment(session_key, buyer, "(兜底内容)", status,
                                      "未匹配商品，发送默认内容" if ok else "未匹配商品，发送默认内容失败")
                self.order_event.emit({"status": status, "buyer": buyer,
                                       "goods": "(兜底内容)", "session": session_key})
            else:
                logger.warn(
                    f"未匹配到商品，跳过发货（订单价格 {price_desc}）\n"
                    f"  [会话文本] {body_preview}\n"
                    f"  [卡片信息] {card_preview}\n"
                    f"  [提示] 若订单价格为 ¥{order_price}，请在商品管理中为对应商品设置相同价格"
                )
                database.add_shipment(session_key, buyer, "(未匹配)", ST_UNMATCHED,
                                      f"会话文本: {body_preview[:100]} | 卡片: {card_preview[:100]}")
                self.order_event.emit({"status": ST_UNMATCHED, "buyer": buyer,
                                       "goods": "(未匹配)", "session": session_key})
            return

        # 发送发货内容
        logger.info(f"匹配商品「{goods['name']}」，开始发货…")
        delay = float(database.get_setting("send_delay", "1.5"))
        time.sleep(min(delay, 3))
        ok = client.send_text(goods["content"])
        if ok:
            logger.success(f"发货成功: 「{goods['name']}」 → {buyer or session['key'][:24]}")
            logger.info("提示: 内容已自动发送。请到闲鱼APP手动点击「去发货」完成状态更新，买家才能确认收货")
            database.add_shipment(session_key, buyer, goods["name"], ST_SUCCESS,
                                  f"内容: {goods['content'][:60]}")
        else:
            logger.error(f"发货失败: 「{goods['name']}」 → {session['key'][:40]}")
            database.add_shipment(session_key, buyer, goods["name"], ST_FAILED,
                                  "发送失败，请检查浏览器状态")
        self.order_event.emit({"status": ST_SUCCESS if ok else ST_FAILED,
                               "buyer": buyer, "goods": goods["name"], "session": session_key})


def _guess_buyer(card_text: str) -> str:
    """从会话卡片文本粗略提取买家昵称（第一行开头部分）。"""
    line = (card_text or "").split("\n")[0].strip()
    if not line:
        return ""
    # 卡片首行通常是「昵称」或「昵称 商品名」，截取前 12 个字符作为参考
    return line[:12]
