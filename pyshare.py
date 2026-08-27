import os
import socket
import argparse
import qrcode
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
import uvicorn

def get_lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip

app = FastAPI()
shared_dir = ""

@app.get("/", response_class=HTMLResponse)
async def list_files():
    try:
        files = os.listdir(shared_dir)
        items = "".join(f'<li><a href="/files/{f}">{f}</a></li>' for f in files if os.path.isfile(os.path.join(shared_dir, f)))
        html = f"<h1>Shared Files</h1><ul>{items}</ul>"
        return html
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/files/{filename}")
async def serve_file(filename: str):
    filepath = os.path.join(shared_dir, filename)
    if not os.path.isfile(filepath):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(filepath)

def main():
    global shared_dir
    parser = argparse.ArgumentParser(description="Share a directory over FastAPI.")
    parser.add_argument("dir", help="The directory to share", type=str)
    parser.add_argument("--port", help="Port to use", type=int, default=8000)
    args = parser.parse_args()

    shared_dir = os.path.abspath(args.dir)
    if not os.path.isdir(shared_dir):
        print(f"Directory not found: {shared_dir}")
        return

    ip = get_lan_ip()
    url = f"http://{ip}:{args.port}"
    print(f"Sharing folder: {shared_dir}")
    print(f"Access it at: {url}")

    # Generate and display QR code
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    qr.print_ascii()

    uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="critical", access_log=False)

if __name__ == "__main__":
    main()
