"""闲鱼自动化客户端：基于 Playwright 操作 goofish.com 网页版。

流程（经社区验证的可行路径）：
1. 打开 https://www.goofish.com/im 聊天列表页
2. 扫描消息列表，识别包含「我已付款，等待你发货 / 等待卖家发货」的会话卡片
   （排除「待付款」等不可发货状态）
3. 点击进入会话 → 提取聊天窗口文本 → 由外部解析器匹配商品
4. 在输入框填写发货内容 → 回车发送
5. 返回消息列表，继续下一个会话

注意：本工具在「聊天中发送内容」完成发货，不点击「去发货」按钮，
避免触发移动端/物流核验等复杂流程。页面结构如遇改版，调整 config.py 中
的 PAYMENT_MARKERS 等关键文本即可。
"""
import re
import time

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

from . import config, logger

# 一次性扫描消息列表：对每个付款标记元素向上找会话卡片容器，
# 同一卡片只保留一条；生成稳定 uid（买家昵称+商品图URL）用于防重复发货。
_JS_SCAN_PAID = """
() => {
    const markers = ['我已付款，等待你发货', '我已付款,等待你发货', '等待卖家发货', '等待你发货'];
    const seenCards = new Set();
    const seenUids = new Set();
    const results = [];
    const all = document.querySelectorAll('div, li, section, span');
    for (const n of all) {
        const t = (n.innerText || '').trim();
        if (!t || t.length > 150) continue;
        if (!markers.some(m => t.includes(m))) continue;
        // 向上找会话卡片容器
        let node = n;
        let card = null;
        for (let i = 0; i < 6 && node && node !== document.body; i++) {
            const r = node.getBoundingClientRect();
            const inner = (node.innerText || '').replace(/\\s+/g, ' ').trim();
            if (r.width > 200 && r.height > 30 && inner.length > 5) { card = {node, inner}; break; }
            node = node.parentElement;
        }
        if (!card) continue;
        const cardKey = card.inner.slice(0, 80);
        if (seenCards.has(cardKey)) continue;
        seenCards.add(cardKey);
        // 排除「待付款」等不可发货状态
        if (['待付款', '等待买家付款'].some(m => card.inner.includes(m))) continue;
        // 买家昵称（卡片首词）+ 商品缩略图 URL = 稳定标识
        const firstLine = (card.inner.split(' ')[0] || '').trim();
        let imgSrc = '';
        for (const img of card.node.querySelectorAll('img')) {
            const s = (img.src || img.getAttribute('src') || '');
            if (s.includes('alicdn') && (s.includes('xy_item') || s.includes('bao/uploaded'))) {
                imgSrc = s.split('?')[0];
                break;
            }
        }
        const uid = (firstLine + '|' + imgSrc).slice(0, 150);
        if (!uid || seenUids.has(uid)) continue;
        seenUids.add(uid);
        results.push({
            key: cardKey,
            text: card.inner.slice(0, 300),
            uid: uid,
            marker: markers.find(m => card.inner.includes(m)) || markers[0],
        });
    }
    return results;
}
"""

_JS_INPUT_VALUE = """
(el) => {
  if (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT') return el.value || '';
  return el.innerText || el.textContent || '';
}
"""


class XianyuClient:
    def __init__(self, headless: bool = False):
        self.headless = headless
        self._playwright = None
        self._context = None
        self._page = None

    # ---------- 生命周期 ----------
    def start(self) -> None:
        """启动浏览器（含重试）。失败抛出最后一次异常。"""
        if self._playwright is not None:
            return
        last_err = None
        for attempt in range(1, 4):
            try:
                self._start_once()
                return
            except Exception as e:
                last_err = e
                import traceback
                logger.warn(f"浏览器启动失败（第{attempt}次/共3次）: {e}")
                logger.error(traceback.format_exc())
                self._cleanup_after_failed_start()
                time.sleep(2)
        raise last_err

    def _start_once(self) -> None:
        self._playwright = sync_playwright().start()

        launch_kwargs = dict(
            user_data_dir=str(config.BROWSER_DIR),
            headless=self.headless,
            args=["--start-maximized", "--disable-blink-features=AutomationControlled"],
            no_viewport=True,
        )
        channel = self._pick_system_browser()
        if channel:
            launch_kwargs["channel"] = channel
            logger.info(f"使用系统浏览器: {channel}（无需下载浏览器内核）")

        try:
            self._context = self._playwright.chromium.launch_persistent_context(**launch_kwargs)
        except Exception as e:
            # 系统浏览器启动失败时回退到内置 Chromium
            if channel:
                logger.warn(f"系统浏览器启动失败({e})，回退到内置 Chromium")
                launch_kwargs.pop("channel", None)
                self._context = self._playwright.chromium.launch_persistent_context(**launch_kwargs)
            else:
                raise

        self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
        self._page.set_default_timeout(10000)
        logger.info("浏览器已启动（登录态目录: data/browser_profile）")

    def _cleanup_after_failed_start(self) -> None:
        """启动失败后清理半初始化的资源。"""
        try:
            if self._context is not None:
                self._context.close()
        except Exception:
            pass
        try:
            if self._playwright is not None:
                self._playwright.stop()
        except Exception:
            pass
        self._context = None
        self._playwright = None
        self._page = None

    @staticmethod
    def _pick_system_browser() -> str | None:
        """优先使用系统已安装的 Edge/Chrome，避免下载浏览器内核。"""
        import os
        candidates = {
            "msedge": [
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            ],
            "chrome": [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            ],
        }
        for ch, paths in candidates.items():
            if any(os.path.exists(p) for p in paths):
                return ch
        return None

    def stop(self) -> None:
        for name in ("_context", "_playwright"):
            try:
                obj = getattr(self, name)
                if obj is not None:
                    obj.close() if hasattr(obj, "close") else None
            except Exception:
                pass
        self._context = None
        self._playwright = None
        self._page = None
        logger.info("浏览器已关闭")

    def _current_page(self):
        """点击可能打开新标签页，始终使用最后激活的页面。"""
        if self._context and len(self._context.pages) > 0:
            return self._context.pages[-1]
        return self._page

    # ---------- 页面操作 ----------
    def _safe_goto(self, page, url, timeout=30000) -> bool:
        """导航到 URL，处理页面自身重定向导致的导航中断。"""
        for attempt in range(2):
            try:
                # 先等待上一轮导航结束，避免 "interrupted by another navigation"
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=5000)
                except Exception:
                    pass
                page.goto(url, wait_until="domcontentloaded", timeout=timeout)
                return True
            except Exception as e:
                logger.warn(f"导航失败(第{attempt + 1}次): {e}")
                page.wait_for_timeout(1500)
        return False

    def open_im(self) -> bool:
        """打开聊天列表页；返回 True 表示已登录可用，False 表示需要扫码登录。

        网络/导航故障通过抛异常表达（上层会冷却后重试），不会误判为登录失效。
        """
        page = self._current_page()
        if page.url.rstrip("/") == config.IM_URL.rstrip("/"):
            # 已在列表页，等待页面稳定即可，避免重复导航
            try:
                page.wait_for_load_state("domcontentloaded", timeout=5000)
            except Exception:
                pass
        else:
            if not self._safe_goto(page, config.IM_URL):
                raise RuntimeError(f"打开聊天页失败: {config.IM_URL}")
        page.wait_for_timeout(1500)

        url = page.url
        if any(m in url.lower() for m in config.LOGIN_URL_MARKERS):
            logger.warn("检测到登录跳转，需要重新登录")
            return False

        # 轻量登录态检测：取 body 前 800 字符
        try:
            body = page.locator("body").inner_text(timeout=8000)[:800]
        except PWTimeout:
            raise RuntimeError("页面加载异常（body 不可读）")
        if any(m in body for m in config.LOGIN_PAGE_MARKERS):
            logger.warn("页面出现登录二维码/登录提示，需要重新登录")
            return False
        return True

    def find_paid_sessions(self) -> list[dict]:
        """扫描消息列表，返回付款待发货的会话列表（同一会话只返回一条）。

        每项: {key, card_text, marker, uid}
        uid = 买家昵称 + 商品图URL，稳定标识，用于防重复发货。
        """
        page = self._current_page()
        try:
            results = page.evaluate(_JS_SCAN_PAID) or []
        except Exception as e:
            logger.warn(f"扫描付款会话失败: {e}")
            return []
        # 兜底：确保字段齐全
        sessions = []
        for r in results:
            if isinstance(r, dict) and r.get("text") and r.get("uid"):
                sessions.append({
                    "key": (r.get("key") or r["text"][:80]),
                    "card_text": r["text"],
                    "marker": r.get("marker") or config.PAYMENT_MARKERS[0],
                    "uid": r["uid"],
                })
        return sessions

    def enter_session(self, session: dict) -> dict | None:
        """点击进入会话；成功返回 {session_key, body_text, card_text}，失败返回 None。"""
        page = self._current_page()
        url_before = page.url
        try:
            page.get_by_text(session["marker"], exact=False).first.click(timeout=6000)
        except Exception:
            logger.warn(f"点击会话失败: {session['key'][:40]}")
            return None
        page.wait_for_timeout(1800)

        # 新标签页保护
        if len(self._context.pages) > 1:
            page = self._context.pages[-1]

        in_chat = False
        if page.url != url_before and "im" in page.url:
            in_chat = True
        elif self._find_input(page) is not None:
            in_chat = True
        if not in_chat:
            logger.warn(f"未能进入聊天窗口: {session['key'][:40]}")
            return None

        try:
            body_text = page.locator("body").inner_text(timeout=8000)
        except Exception:
            body_text = session["card_text"]

        # 订单卡片信息：商品标题通常不显示为普通文本（图片卡片），
        # 尝试从卡片内 img 的 alt / title 属性中提取（闲鱼缩略图常带标题）
        card_info = self._extract_order_card_info(page)

        # 会话唯一标识：优先稳定 uid（买家昵称+商品图），其次 URL/卡片文本
        uid = session.get("uid") or ""
        if uid:
            session_key = f"uid:{uid}"
        else:
            session_key = page.url
            if not session_key or session_key == url_before:
                session_key = f"text:{session['key']}"
        return {
            "session_key": session_key,
            "body_text": body_text,
            "card_text": session["card_text"],
            "card_info": card_info,
        }

    def _extract_order_card_info(self, page) -> str:
        """从聊天窗口的订单卡片中提取商品标题（图片 alt / title 属性）。"""
        js = """
        (el) => {
            let node = el;
            const found = [];
            for (let i = 0; i < 6 && node && node !== document.body; i++) {
                node.querySelectorAll('img').forEach(img => {
                    const a = (img.alt || '').trim();
                    if (a && a.length > 1) found.push('IMG_ALT: ' + a);
                });
                node.querySelectorAll('[title]').forEach(x => {
                    const v = (x.title || '').trim();
                    if (v && v.length > 1) found.push('TITLE: ' + v);
                });
                if (found.length > 8) break;
                node = node.parentElement;
            }
            return [...new Set(found)].slice(0, 12).join('\\n');
        }
        """
        for marker in config.PAYMENT_MARKERS:
            try:
                loc = page.get_by_text(marker, exact=False).first
                if loc.count() > 0 and loc.is_visible():
                    info = loc.evaluate(js)
                    if info and info.strip():
                        return info.strip()[:800]
            except Exception:
                continue
        return ""

    def _find_input(self, page):
        """在聊天窗口内定位输入框（textarea / contenteditable / input）。"""
        try:
            for tag in ("textarea", "div[contenteditable='true']", "input[type='text']", "input"):
                loc = page.locator(tag)
                for j in range(loc.count()):
                    el = loc.nth(j)
                    try:
                        if el.is_visible() and (el.is_editable() if tag != "div[contenteditable='true']" else True):
                            return el
                    except Exception:
                        continue
        except Exception:
            pass
        # 按 placeholder 兜底
        for ph in config.INPUT_PLACEHOLDERS:
            try:
                loc = page.get_by_placeholder(ph)
                if loc.count() and loc.first.is_visible():
                    return loc.first
            except Exception:
                continue
        return None

    def send_text(self, text: str) -> bool:
        """向当前聊天窗口发送文本；返回是否发送成功。"""
        page = self._current_page()
        inp = self._find_input(page)
        if inp is None:
            logger.error("未找到聊天输入框，发送失败")
            return False

        # 多行内容压成一行，避免误发多条消息
        one_line = re.sub(r"\s*\n\s*", " ", text).strip()
        if not one_line:
            logger.error("发货内容为空")
            return False

        try:
            inp.click(timeout=3000)
            page.wait_for_timeout(300)
            tag = inp.evaluate("el => el.tagName")
            if tag == "TEXTAREA":
                inp.fill(one_line)
            else:
                inp.press_sequentially(one_line, delay=8)
            page.wait_for_timeout(200)
            page.keyboard.press("Enter")
            page.wait_for_timeout(1500)
            # 校验：输入框应已被清空
            try:
                left = inp.evaluate(_JS_INPUT_VALUE).strip()
            except Exception:
                left = ""
            return len(left) == 0
        except Exception as e:
            logger.error(f"发送文本异常: {e}")
            return False

    def back_to_list(self) -> None:
        try:
            page = self._current_page()
            if page.url.rstrip("/") != config.IM_URL.rstrip("/"):
                self._safe_goto(page, config.IM_URL)
            page.wait_for_timeout(1000)
        except Exception:
            pass


# ---------- 便捷入口（供登录按钮使用） ----------
def open_login_window() -> bool:
    """打开一个有头浏览器窗口供用户扫码登录；浏览器关闭后返回。

    返回 True 表示流程正常（含用户扫码完成或用户主动关闭）；
    返回 False 表示浏览器启动失败（详细原因已写入日志）。
    """
    client = XianyuClient(headless=False)
    try:
        client.start()
        page = client._current_page()
        page.goto(config.IM_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2000)
        logger.info("请在浏览器中扫码登录闲鱼，登录完成后关闭浏览器窗口")
        # 等待用户手动关闭浏览器（每 3 秒检查一次）
        while True:
            try:
                client._context.pages[0].title()
                time.sleep(3)
            except Exception:
                break
        return True
    except Exception as e:
        import traceback
        logger.error(f"登录窗口异常: {e}\n{traceback.format_exc()}")
        return False
    finally:
        client.stop()
