class Logger:
    """A simple, static logging utility."""
    
    @staticmethod
    def plain(message: str):
        print(message)

    @staticmethod
    def info(message: str):
        print(f"[INFO] {message}")
    
    @staticmethod
    def success(message: str):
        print(f"[SUCCESS] {message}")

    @staticmethod
    def debug(message: str):
        print(f"[DEBUG] {message}")
    
    @staticmethod
    def warning(message: str):
        print(f"[WARNING] {message}")
    
    @staticmethod
    def error(message: str):
        print(f"[ERROR] {message}")