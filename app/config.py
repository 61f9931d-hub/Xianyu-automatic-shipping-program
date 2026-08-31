"""全局配置：路径、默认值、闲鱼页面关键文本。"""
from pathlib import Path

# ---------- 路径 ----------
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "app.db"
BROWSER_DIR = DATA_DIR / "browser_profile"   # Playwright 持久化登录态
LOG_DIR = DATA_DIR / "logs"

for _d in (DATA_DIR, BROWSER_DIR, LOG_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ---------- 默认设置 ----------
DEFAULT_SETTINGS = {
    "monitor_interval": 60,        # 监控间隔（秒）
    "auto_start": 0,               # 启动时自动开始监控
    "headless": 0,                 # 0=有头浏览器(可观察), 1=无头
    "send_delay": 1.5,             # 发货操作间的基础延时（秒）
    "default_message": "",         # 商品未匹配时的兜底发货内容（留空则只记录不发）
}

# ---------- 闲鱼页面关键信息（闲鱼改版后如失效，改这里即可） ----------
IM_URL = "https://www.goofish.com/im"           # 消息/聊天列表页

# 判定「买家已付款、等待发货」的文本特征（系统消息卡片中的文字）
PAYMENT_MARKERS = [
    "我已付款，等待你发货",
    "我已付款,等待你发货",
    "等待卖家发货",
    "等待你发货",
]

# 表示「不能发货」的文本特征（如待付款状态）
UNPAID_MARKERS = ["待付款", "等待买家付款"]

# 登录失效特征（URL 或页面文本）
LOGIN_URL_MARKERS = ["passport", "login", "login.taobao.com", "sso"]
LOGIN_PAGE_MARKERS = ["扫码登录", "二维码登录", "请登录"]

# 聊天输入框的候选定位方式（placeholder / 属性）
INPUT_PLACEHOLDERS = ["说点什么", "请输入消息", "发消息", "输入", "message"]
