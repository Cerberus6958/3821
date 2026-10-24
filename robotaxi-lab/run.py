"""Start the Robotaxi dispatch lab: python run.py  (then open http://127.0.0.1:8000)."""

import argparse
import threading
import webbrowser

import uvicorn


def main():
    parser = argparse.ArgumentParser(description="Robotaxi dispatch lab")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true", help="Do not open a browser tab")
    args = parser.parse_args()
    url = f"http://{args.host}:{args.port}"
    if not args.no_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    print(f"Robotaxi dispatch lab running at {url}  (Ctrl+C to stop)")
    uvicorn.run("backend.api:app", host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
