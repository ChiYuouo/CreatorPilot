from datetime import timedelta

from datetime import datetime
from pathlib import Path

from conf import BASE_DIR


def get_absolute_path(relative_path: str, base_dir: str = None) -> str:
    # 将相对路径转换为绝对路径
    absolute_path = Path(BASE_DIR) / base_dir / relative_path
    return str(absolute_path)


def get_title_and_hashtags(filename):
    """
  获取视频标题和话题标签

  参数：
    filename: 视频文件名

  返回值：
    视频标题和话题标签列表
  """

    # 获取保存视频标题和话题标签的文本文件名
    txt_filename = filename.replace(".mp4", ".txt")

    # 读取 txt 文件
    with open(txt_filename, "r", encoding="utf-8") as f:
        content = f.read()

    # 获取标题和话题标签
    splite_str = content.strip().split("\n")
    title = splite_str[0]
    hashtags = splite_str[1].replace("#", "").split(" ")

    return title, hashtags


def generate_schedule_time_next_day(total_videos, videos_per_day = 1, daily_times=None, timestamps=False, start_days=0):
    """
    生成视频上传计划，默认从次日开始。

    参数：
    - total_videos：待上传的视频总数。
    - videos_per_day：每天上传的视频数量。
    - daily_times：可选的每日发布小时列表。
    - timestamps：是否返回时间戳；否则返回 datetime 对象。
    - start_days：在次日的基础上额外推迟的天数。

    返回值：
    - 视频发布时间列表，元素为时间戳或 datetime 对象。
    """
    if videos_per_day <= 0:
        raise ValueError("videos_per_day should be a positive integer")

    if daily_times is None:
        # 未指定发布时间时使用默认时段
        daily_times = [6, 11, 14, 16, 22]

    if videos_per_day > len(daily_times):
        raise ValueError("videos_per_day should not exceed the length of daily_times")

    # 生成发布时间列表
    schedule = []
    current_time = datetime.now()

    for video in range(total_videos):
        day = video // videos_per_day + start_days + 1  # 加 1，表示从次日开始安排
        daily_video_index = video % videos_per_day

        # 计算当前视频的发布时间
        hour = daily_times[daily_video_index]
        time_offset = timedelta(days=day, hours=hour - current_time.hour, minutes=-current_time.minute,
                                seconds=-current_time.second, microseconds=-current_time.microsecond)
        timestamp = current_time + time_offset

        schedule.append(timestamp)

    if timestamps:
        schedule = [int(time.timestamp()) for time in schedule]
    return schedule
