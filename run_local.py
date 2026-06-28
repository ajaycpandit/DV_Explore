"""
Run the DeltaV Strategy Workbench LOCALLY, bound to localhost only.

Nothing is exposed to your network and no data leaves this machine — the file you
open is parsed in memory on your own computer. Uploaded text is held in a temp
folder only for the life of the run and is gone when you stop the server.

    python run_local.py

Then your browser opens http://127.0.0.1:5000  (press Ctrl+C in the terminal to stop).
"""
import threading
import time
import webbrowser

import server  # the Flask app


def _open_browser():
    time.sleep(1.3)
    try:
        webbrowser.open('http://127.0.0.1:5000')
    except Exception:
        pass


if __name__ == '__main__':
    threading.Thread(target=_open_browser, daemon=True).start()
    print("\n  DeltaV Strategy Workbench  —  LOCAL ONLY (not on your network)")
    print("  Open:  http://127.0.0.1:5000")
    print("  Stop:  press Ctrl+C in this window\n")
    # 127.0.0.1 = this machine only. Do NOT change to 0.0.0.0 for sensitive data.
    server.app.run(host='127.0.0.1', port=5000, debug=False)
