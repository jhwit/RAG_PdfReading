"""
日志配置模块。

什么是日志？
就像飞机的"黑匣子"，记录系统运行中发生的一切重要事件：
- 什么时候启动了？
- 谁上传了什么文件？
- 哪里出错了？错误信息是什么？

为什么不用 print？
print 只能输出到屏幕，程序关闭后信息就没了。
日志可以：
1. 同时输出到屏幕和文件
2. 分级别（DEBUG < INFO < WARNING < ERROR），方便过滤
3. 带时间戳，方便排查问题发生的时间点
"""
import logging          # Python 标准库自带的日志模块
import sys              # 系统相关，这里用来获取标准输出流
from datetime import datetime  # 获取当前日期，用于生成日志文件名


def setup_logger(name: str = "rag_kb") -> logging.Logger:
    """
    创建并配置一个日志记录器。

    参数:
        name: 日志器名称。一个项目可以有多个日志器（如 "rag_kb.document"、"rag_kb.rag"），
              它们会继承根配置，但可以在日志中区分来源。

    返回:
        logging.Logger: 配置好的日志器对象
    """
    # 获取（或创建）一个名为 name 的日志器
    logger = logging.getLogger(name)
    # 设置日志级别：INFO 表示只记录 INFO 及以上级别的日志（DEBUG 会被忽略）
    logger.setLevel(logging.INFO)

    # 如果已经配置过（有 handlers），直接返回，避免重复添加处理器
    # 为什么？因为每次调用 setup_logger 如果没有这个判断，
    # 同一个日志会输出 2 次、3 次……越来越多
    if not logger.handlers:
        # 定义日志格式
        # %(asctime)s    = 时间，如 2026-06-28 14:30:00
        # %(levelname)-8s = 日志级别，左对齐占 8 位（INFO    / ERROR   ）
        # %(name)s       = 日志器名称
        # %(message)s    = 真正的日志内容
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

        # === 处理器 1：输出到屏幕 ===
        # StreamHandler 把日志写到某个流（stream），sys.stdout 就是屏幕
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(formatter)  # 应用上面定义的格式
        logger.addHandler(console)

        # === 处理器 2：输出到文件 ===
        # FileHandler 把日志写到磁盘文件
        # 文件名按日期生成：logs/app_20260628.log，每天一个文件，方便归档
        file_handler = logging.FileHandler(
            f"logs/app_{datetime.now().strftime('%Y%m%d')}.log",
            encoding="utf-8"  # 使用 UTF-8 编码，避免中文乱码
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger
