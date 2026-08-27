# pyShare

Share a folder over your local network with a small, installable **PWA file
browser** built on FastAPI. Point it at any directory, open the printed URL
(or scan the QR code), and browse, preview, and download its contents from
your phone or laptop.

## Features

- **Subdirectory browsing** — navigate the whole tree, not just the top level.
- **Installable PWA** — add to home screen / install as an app; a service
  worker caches the app shell so the UI loads fast and the toolbar works
  offline (shared content is never cached).
- **Grid & list views** with breadcrumbs, instant folder filtering, and
  sorting by name, size, or modified date. Preferences persist per device.
- **Inline previews** for images, video, audio, and text/code — plus
  "Open in tab" and "Download" (forces a save, not a navigation).
- **Share dialog** with a scannable QR code and one-tap copy of the LAN link.
- **Deep links** — each folder has a stable `/?p=folder` URL; browser
  back/forward works.
- **Type-safe file serving** — all routes resolve paths against the shared
  root and reject any traversal (`../`) with a `400`.

## Requirements

- Python 3.10+
- [FastAPI](https://fastapi.tiangolo.com/), [Uvicorn](https://www.uvicorn.org/),
  and [`qrcode`](https://pypi.org/project/qrcode/)

> No Pillow needed — QR codes are rendered as SVG via `qrcode.image.svg`.

```bash
pip install fastapi uvicorn qrcode
```

## Usage

```bash
python pyshare.py /path/to/folder [--port 8000]
```

On startup it prints the LAN URL and an ASCII QR code:

```
Sharing folder: C:\Users\me\photos
Access it at:   http://192.168.1.218:8000
(UI is a PWA - installable on phones, works via QR scan)

  [QR code]
```

Open that URL on any device on the same network, or scan the QR.

| Argument | Default | Description |
|----------|---------|-------------|
| `dir`    | *(required)* | Directory to share |
| `--port` | `8000`    | Port to listen on (binds to `0.0.0.0`) |

### `pysh.bat` (Windows helper)

Share the folder you're standing in, in one command:

```bat
pysh.bat
```

It runs `pyshare.py` against `%cd%`. Edit the path inside if you move the
project.

## HTTP API

| Endpoint | Description |
|----------|-------------|
| `GET /` | The PWA app shell (single embedded HTML file). |
| `GET /api/browse?p=<rel>` | JSON listing for a subdirectory: `{ path, parent, root, share_url, items:[{name,type,size,mtime}] }`. `p=""` = root. |
| `GET /files/<rel>` | Serve a file (nested paths supported). |
| `GET /download/<rel>` | Same as `/files` but sets `Content-Disposition: attachment`. |
| `GET /manifest.json` | PWA web app manifest. |
| `GET /sw.js` | Service worker (caches the app shell only). |
| `GET /icon.svg` | App icon. |
| `GET /qr.svg` | SVG QR code of the current share URL. |

All file/path routes are sandboxed to the shared directory; anything that
escapes it returns `400`.

## Project layout

```
pyshare.py    FastAPI app + embedded PWA (single file, no build step)
pysh.bat      Windows shortcut to share the current directory
.gitignore    excludes __pycache__ / *.pyc
```

## Security notes

- The server binds to `0.0.0.0`, so **anyone on your network can read the
  shared folder** — only share directories you're comfortable exposing.
- There is no authentication; treat the LAN URL as the credential.
- Path traversal is blocked, and the service worker deliberately never caches
  `/files/` or `/api/` responses, so stale or private content isn't retained
  on the device.
