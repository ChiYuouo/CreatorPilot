import sys
from pathlib import Path
from loguru import logger

from conf import BASE_DIR


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def log_formatter(record: dict) -> str:
    """
    格式化日志记录。
    参数：record 为包含日志元数据与消息的字典。
    返回值：格式化后的字符串。
    """
    colors = {
        "TRACE": "#cfe2f3",
        "INFO": "#9cbfdd",
        "DEBUG": "#8598ea",
        "WARNING": "#dcad5a",
        "SUCCESS": "#3dd08d",
        "ERROR": "#ae2c2c"
    }
    color = colors.get(record["level"].name, "#b3cfe7")
    return f"<fg #70acde>{{time:YYYY-MM-DD HH:mm:ss}}</fg #70acde> | <fg {color}>{{level}}</fg {color}>: <light-white>{{message}}</light-white>\n"


def create_logger(log_name: str, file_path: str):
    """
    为不同业务模块创建自定义日志记录器。
    参数：log_name 为日志名称，file_path 为日志文件路径。
    返回值：配置完成的日志记录器。
    """
    def filter_record(record):
        return record["extra"].get("business_name") == log_name

    Path(BASE_DIR / file_path).parent.mkdir(exist_ok=True)
    logger.add(Path(BASE_DIR / file_path), filter=filter_record, level="INFO", rotation="10 MB", retention="10 days", backtrace=True, diagnose=True)
    return logger.bind(business_name=log_name)


# 移除已有的所有日志处理器
logger.remove()
# 添加标准控制台日志处理器
logger.add(sys.stdout, colorize=True, format=log_formatter)

douyin_logger = create_logger('douyin', 'logs/douyin.log')
tencent_logger = create_logger('tencent', 'logs/tencent.log')
xhs_logger = create_logger('xhs', 'logs/xhs.log')
tiktok_logger = create_logger('tiktok', 'logs/tiktok.log')
bilibili_logger = create_logger('bilibili', 'logs/bilibili.log')
kuaishou_logger = create_logger('kuaishou', 'logs/kuaishou.log')
baijiahao_logger = create_logger('baijiahao', 'logs/baijiahao.log')
xiaohongshu_logger = create_logger('xiaohongshu', 'logs/xiaohongshu.log')
youtube_logger = create_logger('youtube', 'logs/youtube.log')
alipay_logger = create_logger('alipay', 'logs/alipay.log')
weibo_logger = create_logger('weibo', 'logs/weibo.log')
hupu_logger = create_logger('hupu', 'logs/hupu.log')
