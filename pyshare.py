"""pyShare — share a directory over LAN with a file browser.

Run:  python pyshare.py <dir> [--port 8000]
"""

import argparse
import io
import os
import socket
import sys

import qrcode
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response
from qrcode.image.svg import SvgPathImage

app = FastAPI(title="pyShare")

shared_dir = ""
share_url = ""


# ---------------------------------------------------------------------------
# path safety
# ---------------------------------------------------------------------------

def resolve(rel: str) -> str:
    """Resolve *rel* (forward slashes, "" = root) against the shared root.

    Raises 400 on any attempt to escape the shared directory.
    """
    base = os.path.abspath(shared_dir)
    rel = (rel or "").replace("\\", "/").strip("/")
    target = os.path.normpath(os.path.join(base, rel))
    if rel and target != base and not target.startswith(base + os.sep):
        raise HTTPException(status_code=400, detail="Invalid path")
    return target


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@app.get("/api/browse")
async def api_browse(p: str = ""):
    target = resolve(p)
    if not os.path.isdir(target):
        raise HTTPException(status_code=404, detail="Folder not found")
    try:
        names = sorted(os.listdir(target), key=str.lower)
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied")

    items = []
    for name in names:
        fp = os.path.join(target, name)
        is_dir = os.path.isdir(fp)
        try:
            st = os.stat(fp)
        except OSError:
            continue  # skip broken symlinks / racing deletes
        items.append({
            "name": name,
            "type": "dir" if is_dir else "file",
            "size": 0 if is_dir else st.st_size,
            "mtime": st.st_mtime,
        })

    base = os.path.abspath(shared_dir)
    return {
        "path": p,
        "parent": "/".join(p.split("/")[:-1]),
        "root": os.path.basename(base) or base,
        "share_url": share_url,
        "items": items,
    }


@app.get("/files/{file_path:path}")
async def serve_file(file_path: str):
    target = resolve(file_path)
    if not os.path.isfile(target):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(target)


@app.get("/download/{file_path:path}")
async def download_file(file_path: str):
    target = resolve(file_path)
    if not os.path.isfile(target):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(target, filename=os.path.basename(target))


# ---------------------------------------------------------------------------
# Assets
# ---------------------------------------------------------------------------

ICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
<rect width="128" height="128" rx="30" fill="#0b0e14"/>
<path d="M26 46a10 10 0 0 1 10-10h18l10 10h28a10 10 0 0 1 10 10v34a10 10 0 0 1-10 10H36a10 10 0 0 1-10-10V46z" fill="#3776ab"/>
<circle cx="44" cy="88" r="9" fill="#ffd43b"/>
<circle cx="86" cy="64" r="9" fill="#ffd43b"/>
<circle cx="86" cy="102" r="9" fill="#ffd43b"/>
<line x1="52" y1="84" x2="78" y2="69" stroke="#ffd43b" stroke-width="6" stroke-linecap="round"/>
<line x1="52" y1="92" x2="78" y2="100" stroke="#ffd43b" stroke-width="6" stroke-linecap="round"/>
</svg>"""


@app.get("/icon.svg", response_class=Response)
async def icon():
    return Response(ICON_SVG, media_type="image/svg+xml",
                    headers={"Cache-Control": "max-age=3600"})


@app.get("/qr.svg", response_class=Response)
async def qr_svg():
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M,
                       box_size=8, border=2)
    qr.add_data(share_url or location_fallback())
    qr.make(fit=True)
    img = qr.make_image(image_factory=SvgPathImage)
    buf = io.BytesIO()
    img.save(buf)
    return Response(buf.getvalue(), media_type="image/svg+xml",
                    headers={"Cache-Control": "max-age=300"})


def location_fallback():
    return "http://127.0.0.1"


# ---------------------------------------------------------------------------
# index
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index():
    return INDEX_HTML


# ---------------------------------------------------------------------------
# entrypoint
# ---------------------------------------------------------------------------

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


def main():
    global shared_dir, share_url
    parser = argparse.ArgumentParser(description="Share a directory over FastAPI with a file browser.")
    parser.add_argument("dir", help="The directory to share", type=str)
    parser.add_argument("--port", help="Port to use", type=int, default=8000)
    args = parser.parse_args()

    shared_dir = os.path.abspath(args.dir)
    if not os.path.isdir(shared_dir):
        print(f"Directory not found: {shared_dir}")
        return

    share_url = f"http://{get_lan_ip()}:{args.port}"
    print(f"Sharing folder: {shared_dir}")
    print(f"Access it at:   {share_url}")
    print(f"Ensure both devices are on the same network")

    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L,
                       box_size=10, border=4)
    qr.add_data(share_url)
    qr.make(fit=True)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        qr.print_ascii(invert=True)
    except Exception:
        try:
            qr.print_ascii()
        except Exception:
            print("(could not print QR code to this console)")

    uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="critical", access_log=False)


INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#0b0e14">
<title>pyShare</title>
<link rel="icon" href="/icon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/icon.svg">
<style>
:root{
  --bg:#0b0e14; --panel:#121826; --panel-2:#182238; --line:#223047;
  --text:#e9eef8; --muted:#8b98b1; --accent:#ffd43b; --blue:#3776ab;
  --radius:14px;
}
*{box-sizing:border-box}
html,body{margin:0;min-height:100%}
body{
  background:
    radial-gradient(900px 480px at 85% -10%, rgba(55,118,171,.28), transparent 60%),
    radial-gradient(700px 400px at -10% 110%, rgba(255,212,59,.06), transparent 60%),
    var(--bg);
  color:var(--text);
  font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Inter,Arial,sans-serif;
  -webkit-font-smoothing:antialiased;
  touch-action:manipulation;
}
button{font:inherit;color:inherit}

/* ---------- top bar ---------- */
.top{position:sticky;top:0;z-index:20;display:flex;align-items:center;gap:12px;flex-wrap:wrap;
  padding:12px 16px;padding-top:calc(12px + env(safe-area-inset-top));
  background:rgba(11,14,20,.85);backdrop-filter:blur(10px);border-bottom:1px solid var(--line)}
.brand{display:flex;align-items:center;gap:10px;min-width:0}
.brand img{width:34px;height:34px;border-radius:9px;flex:none}
.brand h1{margin:0;font-size:17px;letter-spacing:.2px}
.brand .sub{font-size:12px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:40vw}
.tools{margin-left:auto;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
#search{background:var(--panel);border:1px solid var(--line);color:var(--text);border-radius:10px;
  padding:8px 12px;width:200px;outline:none;transition:border-color .15s}
#search:focus{border-color:var(--blue)}
#search::placeholder{color:var(--muted)}
.seg{display:flex;background:var(--panel);border:1px solid var(--line);border-radius:10px;overflow:hidden}
.seg button{display:flex;align-items:center;background:none;border:0;color:var(--muted);padding:8px 11px;cursor:pointer}
.seg button.on{color:var(--text);background:var(--panel-2)}
#sort{background:var(--panel);color:var(--text);border:1px solid var(--line);border-radius:10px;padding:8px 10px;outline:none}
.icon-btn{display:flex;align-items:center;background:var(--panel);border:1px solid var(--line);border-radius:10px;
  padding:8px 11px;cursor:pointer;color:var(--muted)}
.icon-btn:hover{color:var(--text);border-color:var(--blue)}
.seg svg,.icon-btn svg{width:16px;height:16px}

/* ---------- breadcrumbs ---------- */
.crumbs{display:flex;align-items:center;flex-wrap:wrap;gap:2px;padding:14px 18px 2px;font-size:13px}
.crumbs button{background:none;border:0;color:var(--muted);padding:4px 8px;border-radius:8px;cursor:pointer}
.crumbs button:hover{background:var(--panel);color:var(--text)}
.crumbs .cur{color:var(--text);font-weight:600;padding:4px 8px}
.crumbs .sep{color:var(--muted);opacity:.55}

/* ---------- content ---------- */
main{padding:8px 16px 40px;max-width:1400px;margin:0 auto;padding-bottom:calc(40px + env(safe-area-inset-bottom))}
.count{color:var(--muted);font-size:12px;padding:6px 6px 12px}
.grid{display:grid;gap:12px;grid-template-columns:repeat(auto-fill,minmax(170px,1fr))}
.card{position:relative;background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);
  padding:14px;cursor:pointer;transition:transform .12s ease,border-color .12s,background .12s;
  animation:pop .3s ease backwards;overflow:hidden}
.card:hover{transform:translateY(-2px);border-color:#31415f;background:var(--panel-2)}
.thumb{height:56px;border-radius:10px;display:flex;align-items:center;justify-content:center;margin-bottom:12px;
  overflow:hidden}
.thumb svg{width:28px;height:28px}
.thumb img{width:100%;height:100%;object-fit:cover}
.name{font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.meta{color:var(--muted);font-size:12px;margin-top:2px}
.hint{position:absolute;top:12px;right:12px;width:28px;height:28px;border-radius:8px;display:flex;align-items:center;
  justify-content:center;color:var(--muted);background:var(--panel-2);opacity:0;transition:opacity .15s}
.card:hover .hint{opacity:1}
.hint svg{width:15px;height:15px}

.rows .row{display:grid;grid-template-columns:40px minmax(0,1fr) 80px 140px 30px;gap:12px;align-items:center;
  padding:8px 12px;border-radius:12px;cursor:pointer;animation:pop .25s ease backwards}
.rows .row:hover{background:var(--panel)}
.rows .thumb{width:38px;height:38px;margin:0;border-radius:9px}
.rows .thumb svg{width:20px;height:20px}
.rows .thumb img{width:100%;height:100%;object-fit:cover}
.cell{color:var(--muted);font-size:13px;text-align:right}

/* ---------- states ---------- */
.state{display:flex;flex-direction:column;align-items:center;gap:14px;padding:70px 20px;color:var(--muted)}
.state .big{width:56px;height:56px;opacity:.45}
.state .big svg{width:100%;height:100%}
.spin{width:22px;height:22px;border-radius:50%;border:3px solid var(--line);border-top-color:var(--accent);
  animation:rot .8s linear infinite}
.state button{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:8px 14px;cursor:pointer}

/* ---------- dialogs ---------- */
dialog{border:1px solid var(--line);border-radius:16px;background:var(--panel);color:var(--text);
  padding:0;box-shadow:0 24px 60px rgba(0,0,0,.5);max-width:92vw}
dialog::backdrop{background:rgba(4,6,10,.6)}
.dlg-body{padding:18px;max-width:min(560px,90vw);max-height:80vh;overflow:auto}
.dlg-body h2{margin:0 0 12px;font-size:16px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.dlg-actions{display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end;margin-top:14px}
.dlg-actions button{border-radius:10px;padding:8px 14px;cursor:pointer;border:1px solid var(--line);background:var(--panel-2)}
.dlg-actions .primary{background:var(--accent);border-color:var(--accent);color:#1a1c22;font-weight:600}
.prev-img{max-width:100%;max-height:62vh;border-radius:10px;display:block;margin:0 auto}
.prev-media{width:100%;max-height:62vh;border-radius:10px;display:block}
.prev-pre{background:var(--bg);border:1px solid var(--line);border-radius:10px;padding:12px;overflow:auto;
  max-height:62vh;font:13px/1.55 ui-monospace,Consolas,monospace;white-space:pre;margin:0}
.info-body{padding:22px;text-align:center}
.info-body img.qr{width:180px;height:180px;background:#fff;border-radius:12px;padding:10px}
.info-url{font-family:ui-monospace,Consolas,monospace;font-size:13px;background:var(--bg);border:1px solid var(--line);
  border-radius:10px;padding:10px;margin:14px 0;word-break:break-all}
.info-hint{font-size:12px;color:var(--muted);margin-bottom:14px}
.info-actions{display:flex;gap:8px;justify-content:center;flex-wrap:wrap}
.info-actions button{border-radius:10px;padding:8px 14px;cursor:pointer;border:1px solid var(--line);background:var(--panel-2)}
.info-actions .primary{background:var(--accent);border-color:var(--accent);color:#1a1c22;font-weight:600}

@keyframes pop{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
@keyframes rot{to{transform:rotate(1turn)}}

@media(max-width:640px){
  .tools{width:100%;order:3}
  #search{flex:1;width:auto}
  .rows .row{grid-template-columns:38px minmax(0,1fr) 70px 28px}
  .cell.date,.rows .hint{display:none}
  .grid{grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:10px}
}
</style>
</head>
<body>
<header class="top">
  <div class="brand">
    <img src="/icon.svg" alt="">
    <div style="min-width:0">
      <h1>pyShare</h1>
      <div class="sub" id="rootName">shared folder</div>
    </div>
  </div>
  <div class="tools">
    <input id="search" type="search" placeholder="Filter this folder…  ( / )" autocomplete="off">
    <div class="seg" id="viewSeg">
      <button data-view="grid" title="Grid view"></button>
      <button data-view="list" title="List view"></button>
    </div>
    <select id="sort" title="Sort by">
      <option value="name">Name</option>
      <option value="size">Size</option>
      <option value="mtime">Modified</option>
    </select>
    <button class="icon-btn" id="infoBtn" title="Share link &amp; QR code"></button>
  </div>
</header>

<nav class="crumbs" id="crumbs"></nav>
<main>
  <div id="status"></div>
  <div id="items"></div>
</main>

<!-- file preview -->
<dialog id="prevDlg">
  <div class="dlg-body">
    <h2 id="prevTitle"></h2>
    <div id="prevBody"></div>
    <div class="dlg-actions">
      <button id="openTab">Open in tab</button>
      <button class="primary" id="dlBtn">Download</button>
      <button id="prevClose">Close</button>
    </div>
  </div>
</dialog>

<!-- share / QR -->
<dialog id="infoDlg">
  <div class="info-body">
    <img class="qr" src="/qr.svg" alt="QR code">
    <div class="info-url" id="infoUrl"></div>
    <div class="info-hint">Scan with a phone camera, or send the link.</div>
    <div class="info-actions">
      <button class="primary" id="copyBtn">Copy link</button>
      <button id="infoClose">Close</button>
    </div>
  </div>
</dialog>

<script>
"use strict";
const $ = s => document.querySelector(s);
const itemsEl = $("#items"), statusEl = $("#status"), crumbsEl = $("#crumbs");
const esc = s => String(s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"\u0022","'":"&#39;"}[c]));

/* ---------- icons ---------- */
const stroke = p => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${p}</svg>`;
const ICONS = {
  folder: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M3.5 6.8c0-1.3 1.1-2.4 2.4-2.4h4.1c.6 0 1.2.3 1.6.7l1 1.2h7.4c1.4 0 2.5 1.1 2.5 2.4v8.6c0 1.3-1.1 2.4-2.5 2.4H5.9c-1.4 0-2.4-1.1-2.4-2.4V6.8z"/></svg>',
  image: stroke('<rect x="3.5" y="4.5" width="17" height="15" rx="2.5"/><circle cx="9" cy="9.5" r="1.6"/><path d="m5.5 17.5 4.2-4.2c.5-.5 1.3-.5 1.8 0l3.5 3.5 1.8-1.8c.5-.5 1.3-.5 1.8 0l3.4 3.4"/>'),
  video: stroke('<rect x="3.5" y="5" width="17" height="14" rx="2.5"/><path d="m10.5 9 5 3-5 3V9z"/>'),
  audio: stroke('<path d="M9.5 18.5V6l9-2v12.5"/><circle cx="7.5" cy="18.5" r="2.2"/><circle cx="16.5" cy="16.5" r="2.2"/>'),
  code: stroke('<path d="m8.5 8-4.5 4 4.5 4"/><path d="m15.5 8 4.5 4-4.5 4"/><path d="m13.2 5.5-2.4 13"/>'),
  archive: stroke('<rect x="4" y="4" width="16" height="4" rx="1"/><path d="M5.5 8v10a2 2 0 0 0 2 2h9a2 2 0 0 0 2-2V8"/><path d="M10 12h4"/>'),
  pdf: stroke('<path d="M6.5 3.5h7l4 4v13h-11v-17z"/><path d="M13.5 3.5V8h4"/><path d="M9 15.5h6"/>'),
  text: stroke('<path d="M6.5 3.5h7l4 4v13h-11v-17z"/><path d="M13.5 3.5V8h4"/><path d="M9 13h6M9 16h4"/>'),
  file: stroke('<path d="M6.5 3.5h7l4 4v13h-11v-17z"/><path d="M13.5 3.5V8h4"/>')
};
const EXT_MAP = {
  image: "png jpg jpeg gif webp svg bmp ico tif tiff heic avif".split(" "),
  video: "mp4 mkv webm mov avi m4v ts wmv".split(" "),
  audio: "mp3 wav flac ogg m4a aac opus wma".split(" "),
  code:  "py js ts jsx tsx html css scss json yml yaml toml sh bat ps1 rs go java c cpp h hpp cs rb php kt swift sql".split(" "),
  archive: "zip rar 7z tar gz bz2 xz zst".split(" "),
  pdf: ["pdf"],
  text:  "txt md log csv ini conf xml env lua".split(" ")
};
const EXT_CAT = {};
for (const [cat, exts] of Object.entries(EXT_MAP)) exts.forEach(e => EXT_CAT[e] = cat);
const CAT_COLOR = { image:"#4ade80", video:"#fb923c", audio:"#f472b6", code:"#ffd43b",
                    archive:"#a78bfa", pdf:"#ff8787", text:"#9fb0cc", file:"#9fb0cc" };
function catOf(name){
  const i = name.lastIndexOf(".");
  return (i < 0) ? "file" : (EXT_CAT[name.slice(i + 1).toLowerCase()] || "file");
}
function iconFor(it){
  if (it.type === "dir") return { svg: ICONS.folder, color: "#7fb3ff" };
  const c = catOf(it.name);
  return { svg: ICONS[c] || ICONS.file, color: CAT_COLOR[c] || CAT_COLOR.file };
}

/* static toolbar icons */
$("#infoBtn").innerHTML = stroke('<rect x="4" y="4" width="6.5" height="6.5" rx="1.4"/><rect x="13.5" y="4" width="6.5" height="6.5" rx="1.4"/><rect x="4" y="13.5" width="6.5" height="6.5" rx="1.4"/><path d="M14 14h3v3h-3z" fill="currentColor" stroke="none"/><path d="M19.5 14v2.5"/><path d="M14 19.5h2.5"/><path d="M19.5 19.5v.5"/>');
$('#viewSeg [data-view="grid"]').innerHTML = stroke('<rect x="4" y="4" width="7" height="7" rx="1.5"/><rect x="13" y="4" width="7" height="7" rx="1.5"/><rect x="4" y="13" width="7" height="7" rx="1.5"/><rect x="13" y="13" width="7" height="7" rx="1.5"/>');
$('#viewSeg [data-view="list"]').innerHTML = stroke('<path d="M9 6h11M9 12h11M9 18h11"/><path d="M4.5 6h.5M4.5 12h.5M4.5 18h.5"/>');

/* ---------- state ---------- */
let view = localStorage.getItem("pyshare.view") || "grid";
let sort = localStorage.getItem("pyshare.sort") || "name";
let query = "";
let state = { path:"", parent:"", root:"", share_url:"", items:[], busy:true, error:null };

const fmtSize = n => {
  if (n < 1024) return n + " B";
  const u = ["KB","MB","GB","TB"];
  let i = -1;
  do { n /= 1024; i++; } while (n >= 1024 && i < u.length - 1);
  return n.toFixed(n >= 100 ? 0 : 1) + " " + u[i];
};
const fmtDate = t => {
  const d = new Date(t * 1000);
  return d.toLocaleDateString() + " " + d.toLocaleTimeString([], { hour:"2-digit", minute:"2-digit" });
};
const encPath = p => p.split("/").map(encodeURIComponent).join("/");
const filesHref = p => "/files/" + encPath(p);
const dlHref = p => "/download/" + encPath(p);

/* ---------- data ---------- */
function dirFromUrl(){
  const p = new URLSearchParams(location.search).get("p");
  return p ? p.replace(/\/+$/, "") : "";
}

async function load(){
  const p = dirFromUrl();
  state = { path:p, parent:"", root:"", share_url:"", items:[], busy:true, error:null };
  render();
  try {
    const r = await fetch("/api/browse?p=" + encodeURIComponent(p));
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.detail || (r.status + " " + r.statusText));
    Object.assign(state, data, { busy:false });
  } catch (e) {
    state.error = e.message || "Failed to load";
    state.busy = false;
  }
  render();
}

function navigate(path){
  query = ""; $("#search").value = "";
  const url = path ? "/?p=" + encodeURIComponent(path) : "/";
  history.pushState(null, "", url);
  load();
}

/* ---------- rendering ---------- */
function visibleItems(){
  const q = query.trim().toLowerCase();
  let arr = state.items.filter(i => !q || i.name.toLowerCase().includes(q));
  const byName = (a,b) => a.name.localeCompare(b.name, undefined, { numeric:true, sensitivity:"base" });
  return arr.sort((a,b) => {
    if (a.type !== b.type) return a.type === "dir" ? -1 : 1;
    if (sort === "size")  return b.size - a.size || byName(a,b);
    if (sort === "mtime") return b.mtime - a.mtime || byName(a,b);
    return byName(a,b);
  });
}

function renderCrumbs(){
  const segs = state.path ? state.path.split("/") : [];
  let h = `<button data-nav="">${esc(state.root || "Home")}</button>`;
  segs.forEach((s, i) => {
    h += `<span class="sep">/</span>` + (i === segs.length - 1
      ? `<span class="cur">${esc(s)}</span>`
      : `<button data-nav="${esc(segs.slice(0, i + 1).join("/"))}">${esc(s)}</button>`);
  });
  crumbsEl.innerHTML = h;
}

const thumbHtml = (it, color) => {
  const isImg = it.type === "file" && catOf(it.name) === "image";
  const inner = isImg
    ? `<img loading="lazy" src="${filesHref(state.path ? state.path + "/" + it.name : it.name)}" alt="">`
    : iconFor(it).svg;
  return `<div class="thumb" style="color:${color};background:${color}1f">${inner}</div>`;
};

function cardHtml(it, i, delay){
  const { svg, color } = iconFor(it);
  const name = it.name;
  const full = state.path ? state.path + "/" + name : name;
  const isImg = it.type === "file" && catOf(name) === "image";
  const thumb = isImg
    ? `<div class="thumb"><img loading="lazy" src="${filesHref(full)}" alt=""></div>`
    : `<div class="thumb" style="color:${color};background:${color}1f">${svg}</div>`;
  const meta = it.type === "dir" ? "Folder" : `${fmtSize(it.size)} · ${fmtDate(it.mtime)}`;
  const hint = it.type === "file"
    ? `<span class="hint" title="Open">${stroke('<path d="M7 17 17 7"/><path d="M9.5 7H17v7.5"/>')}</span>` : "";
  return `<div class="card" data-type="${it.type}" data-name="${esc(name)}"
    style="animation-delay:${delay}ms" title="${esc(name)}">
    ${thumb}<div class="name">${esc(name)}</div><div class="meta">${meta}</div>${hint}</div>`;
}

function rowHtml(it, i, delay){
  const { svg, color } = iconFor(it);
  const name = it.name;
  const full = state.path ? state.path + "/" + name : name;
  const isImg = it.type === "file" && catOf(name) === "image";
  const thumb = isImg
    ? `<div class="thumb"><img loading="lazy" src="${filesHref(full)}" alt=""></div>`
    : `<div class="thumb" style="color:${color};background:${color}1f">${svg}</div>`;
  const open = it.type === "file"
    ? `<span class="hint" title="Open">${stroke('<path d="M7 17 17 7"/><path d="M9.5 7H17v7.5"/>')}</span>`
    : `<span class="hint"></span>`;
  return `<div class="row" data-type="${it.type}" data-name="${esc(name)}"
    style="animation-delay:${delay}ms" title="${esc(name)}">
    ${thumb}
    <div class="name">${esc(name)}</div>
    <div class="cell">${it.type === "dir" ? "—" : fmtSize(it.size)}</div>
    <div class="cell date">${it.type === "dir" ? "—" : fmtDate(it.mtime)}</div>
    ${open}</div>`;
}

function render(){
  document.title = (state.path ? state.path + " · " : "") + "pyShare";
  $("#rootName").textContent = state.root || "shared folder";
  renderCrumbs();

  if (state.busy){
    statusEl.innerHTML = `<div class="state"><div class="spin"></div>Loading…</div>`;
    itemsEl.innerHTML = ""; itemsEl.className = "";
    return;
  }
  if (state.error){
    statusEl.innerHTML = `<div class="state"><div class="big">${ICONS.folder}</div>
      <div>${esc(state.error)}</div><button id="homeBtn">Go to top folder</button></div>`;
    itemsEl.innerHTML = ""; itemsEl.className = "";
    const b = $("#homeBtn"); if (b) b.addEventListener("click", () => navigate(""));
    return;
  }

  const arr = visibleItems();
  const dirs = state.items.filter(i => i.type === "dir").length;
  const files = state.items.length - dirs;
  if (!arr.length){
    statusEl.innerHTML = `<div class="state"><div class="big">${ICONS.folder}</div>
      <div>${query ? `No matches for “${esc(query)}”` : "This folder is empty"}</div></div>`;
    itemsEl.innerHTML = ""; itemsEl.className = "";
    return;
  }

  const n = state.items.length;
  statusEl.innerHTML = `<div class="count">${n} item${n === 1 ? "" : "s"} · ${dirs} folder${dirs === 1 ? "" : "s"} · ${files} file${files === 1 ? "" : "s"}${query ? ` (filtered from ${n})` : ""}</div>`;
  const make = view === "grid" ? cardHtml : rowHtml;
  itemsEl.className = view === "grid" ? "grid" : "rows";
  itemsEl.innerHTML = arr.map((it, i) => make(it, i, Math.min(i * 22, 330))).join("");
}

/* ---------- preview ---------- */
const prevDlg = $("#prevDlg");
function openPreview(name){
  const full = state.path ? state.path + "/" + name : name;
  const c = catOf(name);
  $("#prevTitle").textContent = name;
  const body = $("#prevBody");
  if (c === "image"){
    body.innerHTML = `<img class="prev-img" src="${filesHref(full)}" alt="">`;
  } else if (c === "video"){
    body.innerHTML = `<video class="prev-media" controls src="${filesHref(full)}"></video>`;
  } else if (c === "audio"){
    body.innerHTML = `<audio class="prev-media" controls src="${filesHref(full)}"></audio>`;
  } else if (c === "text" || c === "code" || c === "pdf" || c === "file"){
    body.innerHTML = `<pre class="prev-pre">Loading…</pre>`;
    fetch(filesHref(full)).then(r => {
      if (!r.ok) throw new Error(r.status + " " + r.statusText);
      return r.text();
    }).then(t => {
      if (t.length > 400000) t = t.slice(0, 400000) + "\n\n… (truncated, file is large)";
      if (document.querySelector("#prevBody .prev-pre"))
        document.querySelector("#prevBody .prev-pre").textContent = t;
    }).catch(e => {
      const p = document.querySelector("#prevBody .prev-pre");
      if (p) p.textContent = "Preview unavailable (" + e.message + "). Use Download instead.";
    });
  } else {
    body.innerHTML = `<div class="meta" style="padding:10px 0">No inline preview for this type — use Download.</div>`;
  }
  $("#openTab").onclick = () => window.open(filesHref(full), "_blank");
  $("#dlBtn").onclick = () => window.location.href = dlHref(full);
  prevDlg.showModal();
}

/* ---------- share ---------- */
const infoDlg = $("#infoDlg");
$("#infoBtn").addEventListener("click", () => {
  $("#infoUrl").textContent = state.share_url || location.origin;
  infoDlg.showModal();
});
$("#copyBtn").addEventListener("click", async () => {
  const url = state.share_url || location.origin;
  try {
    await navigator.clipboard.writeText(url);
    $("#copyBtn").textContent = "Copied ✓";
  } catch {
    const el = $("#infoUrl");
    const range = document.createRange(); range.selectNodeContents(el);
    const sel = getSelection(); sel.removeAllRanges(); sel.addRange(range);
    document.execCommand("copy");
    $("#copyBtn").textContent = "Copied ✓";
  }
  setTimeout(() => $("#copyBtn").textContent = "Copy link", 1600);
});
$("#infoClose").addEventListener("click", () => infoDlg.close());
$("#prevClose").addEventListener("click", () => prevDlg.close());

/* ---------- events ---------- */
itemsEl.addEventListener("click", e => {
  const el = e.target.closest("[data-name]");
  if (!el) return;
  const name = el.dataset.name;
  const full = state.path ? state.path + "/" + name : name;
  if (el.dataset.type === "dir") navigate(full);
  else openPreview(name);
});

crumbsEl.addEventListener("click", e => {
  const b = e.target.closest("button[data-nav]");
  if (b) navigate(b.dataset.nav);
});

$("#search").addEventListener("input", e => { query = e.target.value; if (!state.busy && !state.error) render(); });
$("#search").addEventListener("keydown", e => {
  if (e.key === "Escape"){ e.target.value = ""; query = ""; render(); e.target.blur(); }
});

$("#viewSeg").addEventListener("click", e => {
  const b = e.target.closest("button[data-view]");
  if (!b) return;
  view = b.dataset.view;
  localStorage.setItem("pyshare.view", view);
  syncView(); render();
});
function syncView(){
  document.querySelectorAll("#viewSeg button").forEach(b =>
    b.classList.toggle("on", b.dataset.view === view));
}

$("#sort").addEventListener("change", e => {
  sort = e.target.value;
  localStorage.setItem("pyshare.sort", sort);
  render();
});

document.addEventListener("keydown", e => {
  if (e.key === "/" && document.activeElement.tagName !== "INPUT"){
    e.preventDefault(); $("#search").focus();
  }
});
window.addEventListener("popstate", load);

/* close dialogs on backdrop click */
for (const d of [prevDlg, infoDlg])
  d.addEventListener("click", e => { if (e.target === d) d.close(); });

/* ---------- init ---------- */
$("#sort").value = sort;
syncView();
load();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
