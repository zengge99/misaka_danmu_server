import collections
import logging
import logging.handlers
from pathlib import Path
from typing import List

# 这个双端队列将用于在内存中存储最新的日志，以供Web界面展示
_logs_deque = collections.deque(maxlen=200)

# 自定义一个日志处理器，它会将日志记录发送到我们的双端队列中
class DequeHandler(logging.Handler):
    def __init__(self, deque):
        super().__init__()
        self.deque = deque

    def emit(self, record):
        # 我们只存储格式化后的消息字符串
        self.deque.appendleft(self.format(record))

# 新增：一个过滤器，用于从UI日志中排除 httpx 的日志
class NoHttpxLogFilter(logging.Filter):
    def filter(self, record):
        # 不记录来自 'httpx' logger 的日志
        return not record.name.startswith('httpx')

# 新增：一个过滤器，用于从UI日志中排除B站特定的信息性日志
class BilibiliInfoFilter(logging.Filter):
    def filter(self, record):
        # 检查日志记录是否来自 BilibiliScraper 并且是 INFO 级别
        if record.name == 'BilibiliScraper' and record.levelno == logging.INFO:
            msg = record.getMessage()
            # 过滤掉“无结果”的通知
            if "returned no results." in msg:
                return False
            # 过滤掉 WBI key 获取过程的日志
            if "WBI mixin key" in msg:
                return False
        return True  # 其他所有日志都通过

def setup_logging():
    """
    配置根日志记录器，使其能够将日志输出到控制台、一个可轮转的文件，
    以及一个用于API的内存双端队列。
    此函数应在应用启动时被调用一次。
    """
    log_dir = Path(__file__).parent.parent / "config" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "app.log"

    # 为控制台和文件日志定义详细的格式
    verbose_formatter = logging.Formatter(
        '[%(asctime)s] [%(name)s:%(lineno)d] [%(levelname)s] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    # 为Web界面定义一个更简洁的格式
    ui_formatter = logging.Formatter('[%(asctime)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # 清理已存在的处理器，以避免在热重载时重复添加
    if logger.hasHandlers():
        logger.handlers.clear()

    logger.addHandler(logging.StreamHandler()) # 控制台处理器
    logger.addHandler(logging.handlers.RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=5, encoding='utf-8')) # 文件处理器

    # 创建并配置 DequeHandler，以过滤掉不希望在UI上显示的内容
    deque_handler = DequeHandler(_logs_deque)
    deque_handler.addFilter(NoHttpxLogFilter())
    deque_handler.addFilter(BilibiliInfoFilter()) # 添加新的过滤器
    logger.addHandler(deque_handler)

    # 为所有处理器设置格式
    for handler in logger.handlers:
        if isinstance(handler, DequeHandler):
            handler.setFormatter(ui_formatter)
        else:
            handler.setFormatter(verbose_formatter)
    
    logging.info("日志系统已初始化，日志将输出到控制台和 %s", log_file)

def get_logs() -> List[str]:
    """返回为API存储的所有日志条目列表。"""
    return list(_logs_deque)