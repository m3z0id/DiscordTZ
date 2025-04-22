import datetime

class Logger:
    @staticmethod
    def log(message: str) -> None:
        timenow: str = datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        print(f"[{timenow}] [LOG] {message}")
    @staticmethod
    def error(message: str) -> None:
        timenow: str = datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        print(f"[{timenow}] [ERROR] {message}")
    @staticmethod
    def success(message: str) -> None:
        timenow: str = datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        print(f"[{timenow}] [SUCCESS] {message}")