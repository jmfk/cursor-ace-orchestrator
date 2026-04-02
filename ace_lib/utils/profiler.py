"""
Performance profiling utilities for ACE.
"""
import time
import functools
import json
from pathlib import Path
from typing import Any, Callable
from datetime import datetime


class Profiler:
    """
    Profiler class to track function execution time and log it to a JSONL file.
    """
    def __init__(self, log_file: Path = Path(".ace/profiling.jsonl")):
        self.log_file = log_file
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

    def profile(self, func: Callable) -> Callable:
        """
        Decorator to profile a function.
        """
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            start_time = time.perf_counter()
            result = func(*args, **kwargs)
            end_time = time.perf_counter()
            duration = end_time - start_time

            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "function": func.__name__,
                "duration_seconds": duration,
                "args_count": len(args),
                "kwargs_keys": list(kwargs.keys()),
            }

            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry) + "\n")

            return result

        return wrapper


profiler = Profiler()
