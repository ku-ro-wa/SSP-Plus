# managers/webapp_thread.py
import threading
import uvicorn
from webapp.main import app

class WebAppThreadManager:
    def __init__(self, host="0.0.0.0", port=8000, ssl_certfile=None, ssl_keyfile=None):
        config = uvicorn.Config(app, host=host, port=port, ssl_certfile=ssl_certfile, ssl_keyfile=ssl_keyfile, log_level="info")
        self.server = uvicorn.Server(config)
        self.thread = None

    def start(self):
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.thread.start()

    def stop(self):
        self.server.should_exit = True
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)