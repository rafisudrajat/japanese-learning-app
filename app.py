import threading
import time
import urllib.request

import uvicorn

from server.main import HOST, app

PORT = 8764


def start_server(host: str = HOST, port: int = PORT) -> threading.Thread:
    thread = threading.Thread(
        target=uvicorn.run, args=(app,), kwargs={"host": host, "port": port}, daemon=True
    )
    thread.start()
    for _ in range(50):
        try:
            urllib.request.urlopen(f"http://{host}:{port}/")
            break
        except OSError:
            time.sleep(0.1)
    return thread


def main() -> None:
    start_server()
    import webview

    webview.create_window("Japanese Reader", f"http://{HOST}:{PORT}/")
    webview.start()


if __name__ == "__main__":
    main()
