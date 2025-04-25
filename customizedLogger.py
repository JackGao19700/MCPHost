import logging

# 配置日志记录器
class FileLogger:
    def __init__(self,logFilePath,delay=False):
        # delay为False, 立即写入.否则有缓冲.
        self.delay=delay

        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)

        # 创建 FileHandler 并设置 delay 为 False
        self.file_handler = logging.FileHandler('../mcpClient/log/mcphost.txt', delay=delay)
        self.file_handler.setLevel(logging.INFO)

        log_format = '%(asctime)s - %(levelname)s - %(message)s'
        formatter = logging.Formatter(log_format)
        self.file_handler.setFormatter(formatter)

        self.logger.addHandler(self.file_handler)
    def __call__(self,*args):
        self.logger.info(*args)
        if not self.delay:
            self.file_handler.flush()

