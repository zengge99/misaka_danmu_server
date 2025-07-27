import collections
from datetime import datetime

class LogManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LogManager, cls).__new__(cls)
            # Store up to 200 recent log entries
            cls._instance.logs = collections.deque(maxlen=200)
        return cls._instance

    def add_log(self, message: str):
        """Adds a new log entry with a timestamp."""
        log_entry = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}"
        # Prepend to the deque so newest logs are first
        self.logs.appendleft(log_entry)
        # Also print to the console for live debugging
        print(log_entry)

    def get_all_logs(self) -> list[str]:
        """Returns a list of all stored log entries."""
        return list(self.logs)

# A single, globally accessible instance of the log manager
log_manager = LogManager()