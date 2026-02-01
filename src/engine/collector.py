import time
import os
import queue
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from core.db_helper import DBHelper
from infra.logger import get_logger
from core.config_manager import ConfigManager
from infra.graceful_exit import should_exit, register_cleanup
from engine.collector_worker import CollectorWorker

log = get_logger("Collector")

class ReceiptHandler(FileSystemEventHandler):
    def __init__(self, task_queue):
        self.task_queue = task_queue
    def on_created(self, event):
        if not event.is_directory:
            self.task_queue.put(event.src_path)

def scan_input_dir(input_dir, task_queue):
    for root, _, files in os.walk(input_dir):
        for file in files:
            task_queue.put(os.path.join(root, file))

def start_watching():
    input_dir = ConfigManager.get("path.input")
    os.makedirs(input_dir, exist_ok=True)
    task_queue = queue.Queue()
    db = DBHelper()

    if ConfigManager.get("collector.initial_scan_enabled", True):
        scan_input_dir(input_dir, task_queue)

    workers = []
    for i in range(ConfigManager.get_int("collector.worker_threads", 2)):
        w = CollectorWorker(task_queue, i)
        w.start()
        workers.append(w)

    event_handler = ReceiptHandler(task_queue)
    observer = Observer()
    observer.schedule(event_handler, input_dir, recursive=True)
    observer.start()
    register_cleanup(observer.stop)
    register_cleanup(observer.join)

    try:
        while not should_exit():
            db.update_heartbeat("Collector-Master", "ACTIVE")
            time.sleep(ConfigManager.get("intervals.collector_scan", 60))
            if should_exit(): break
            scan_input_dir(input_dir, task_queue)
    except Exception as e:
        log.error(f"Collector Master exception: {e}")
    finally:
        log.info("Collector exiting...")

if __name__ == "__main__":
    start_watching()
