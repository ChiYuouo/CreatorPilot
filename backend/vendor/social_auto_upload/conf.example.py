from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()
XHS_SERVER = "http://127.0.0.1:11901"  # 仅用于小红书相关流程
LOCAL_CHROME_PATH = ""  # 可选，例如 C:/Program Files/Google/Chrome/Application/chrome.exe
LOCAL_CHROME_HEADLESS = True  # 上传器及示例默认使用的无头浏览器设置
DEBUG_MODE = True  # 默认调试设置
# YouTube 上传器的可选代理；无法访问 youtube.com 时，直接连接
# 会超时，且 Patchright 启动的 Chromium 不会使用系统代理。
# 填写本机代理地址，例如 "http://127.0.0.1:7890"；None 表示不使用代理。
YT_PROXY = None
