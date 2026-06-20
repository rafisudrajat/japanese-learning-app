import sys
import threading
import time
import urllib.request
import webbrowser

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
    url = f"http://{HOST}:{PORT}/"

    if "--browser" in sys.argv:
        print(f"Opening {url} in your default browser...")
        webbrowser.open(url)
        print("Press Ctrl+C to stop the server.")
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
    else:
        import webview

        webview.create_window("Japanese Reader", url)
        webview.start()


if __name__ == "__main__":
    main()
