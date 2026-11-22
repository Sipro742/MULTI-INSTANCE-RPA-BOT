from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import os

class AspxHandler(SimpleHTTPRequestHandler):
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".aspx": "text/html; charset=utf-8",
    }

if __name__ == "__main__":
    os.chdir(Path(__file__).resolve().parent)
    print("CLINSYS Mock activo en: http://127.0.0.1:8000/")
    HTTPServer(("127.0.0.1", 8000), AspxHandler).serve_forever()