#!/usr/bin/env python3
"""
本地管理面板 + 网站预览，一个命令同时提供：
    网站      http://localhost:8765/
    管理面板  http://localhost:8765/admin

用法：  python3 scripts/admin.py
只监听本机，不会暴露到网络。不需要安装任何东西。
"""
import io, json, shutil, sys, urllib.parse
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_photos as bp

ROOT = bp.ROOT
PORT = 8765
REMOVED = bp.ORIG / "_已移除"
ADMIN_HTML = Path(__file__).resolve().parent / "admin.html"

def safe_name(name):
    name = (name or "").strip()
    if not name or name in (".", "..") or "/" in name or "\\" in name or name.startswith("_"):
        raise ValueError(f"名字不合法：{name!r}")
    return name

def unique(path: Path):
    """目标已存在时加 -2、-3 后缀。"""
    if not path.exists():
        return path
    i = 2
    while True:
        cand = path.with_name(f"{path.stem}-{i}{path.suffix}")
        if not cand.exists():
            return cand
        i += 1

def state():
    entries = bp.load_entries()
    places = {}
    for a in bp.subdirs(bp.ORIG):
        if a.name.startswith("_"):
            continue
        places[a.name] = [p.name for p in bp.subdirs(a)]
    for e in entries:
        places.setdefault(e["author"], [])
        if e["place"] not in places[e["author"]]:
            places[e["author"]].append(e["place"])
    return {"photos": entries, "places": places}

def move_entry(e, new_place):
    """把一张照片的原图、大图、缩略图挪到另一个地点文件夹，并更新条目。"""
    author = e["author"]
    orig = bp.ORIG / author / e["place"] / e.get("file", "")
    if not e.get("file") or not orig.exists():
        # 老条目没有 file 字段：按 slug 反查
        cands = [p for p in (bp.ORIG / author / e["place"]).iterdir()
                 if bp.is_image(p) and bp.slug(p.name) == Path(e["src"]).stem]
        if not cands:
            raise FileNotFoundError(f"找不到原图：{e['src']}")
        orig = cands[0]
    new_orig = unique(bp.ORIG / author / new_place / orig.name)
    new_orig.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(orig), str(new_orig))

    rel = Path(author) / new_place / f"{bp.slug(new_orig.name)}.jpg"
    for base, key in ((bp.PHOTOS, "src"), (bp.THUMBS, "thumb")):
        old = ROOT / e[key]
        new = base / rel
        new.parent.mkdir(parents=True, exist_ok=True)
        if old.exists():
            shutil.move(str(old), str(new))
    e.update(place=new_place, file=new_orig.name,
             src=f"photos/{rel.as_posix()}", thumb=f"thumbs/{rel.as_posix()}")

def apply_layout(author, layout):
    """layout = {地点: [src, ...]}，整体决定该作者的地点归属和顺序。"""
    entries = bp.load_entries()
    by_src = {e["src"]: e for e in entries}
    mine = [e for e in entries if e["author"] == author]
    others = [e for e in entries if e["author"] != author]
    placed = []
    seen = set()          # 已处理的条目（按对象）
    for place, srcs in layout.items():
        place = safe_name(place)
        (bp.ORIG / author / place).mkdir(parents=True, exist_ok=True)
        for src in srcs:
            e = by_src.get(src)
            if not e or e["author"] != author or id(e) in seen:
                continue
            seen.add(id(e))
            if e["place"] != place:
                move_entry(e, place)
            placed.append(e)
    # 没出现在 layout 里的（比如页面没加载到）保持原样放在后面
    placed += [e for e in mine if id(e) not in seen]
    out, inserted = [], False
    for e in entries:
        if e["author"] == author:
            if not inserted:
                out.extend(placed)
                inserted = True
        else:
            out.append(e)
    if not inserted:
        out.extend(placed)
    out.sort(key=lambda e: bp.AUTHOR_ORDER.get(e["author"], 9))   # 稳定排序，作者内部顺序不变
    bp.save_entries(out)

def remove_entry(src):
    entries = bp.load_entries()
    e = next((x for x in entries if x["src"] == src), None)
    if not e:
        raise FileNotFoundError(src)
    orig = bp.ORIG / e["author"] / e["place"] / e.get("file", "")
    if orig.exists():
        dst = unique(REMOVED / e["author"] / e["place"] / orig.name)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(orig), str(dst))
    for key in ("src", "thumb"):
        p = ROOT / e[key]
        if p.exists():
            p.unlink()
    bp.save_entries([x for x in entries if x["src"] != src])

def update_entry(data):
    entries = bp.load_entries()
    for e in entries:
        if e["src"] == data.get("src"):
            for k in ("title", "date", "note"):
                if k in data:
                    e[k] = str(data[k])
            break
    bp.save_entries(entries)

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT), **kw)

    def log_message(self, fmt, *args):
        line = fmt % args if args else fmt
        if "/api/" in line or "code 4" in line or "code 5" in line:
            super().log_message(fmt, *args)

    def send_json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path in ("/admin", "/admin/"):
            body = ADMIN_HTML.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/api/state":
            return self.send_json(state())
        if path.startswith("/originals/"):
            return self.send_error(403)
        return super().do_GET()

    def do_POST(self):
        url = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(url.query)
        try:
            if url.path == "/api/layout":
                d = self.read_json()
                apply_layout(safe_name(d["author"]), d["layout"])
                return self.send_json(state())
            if url.path == "/api/place":
                d = self.read_json()
                (bp.ORIG / safe_name(d["author"]) / safe_name(d["name"])).mkdir(parents=True, exist_ok=True)
                return self.send_json(state())
            if url.path == "/api/update":
                update_entry(self.read_json())
                return self.send_json({"ok": True})
            if url.path == "/api/remove":
                remove_entry(self.read_json()["src"])
                return self.send_json(state())
            if url.path == "/api/upload":
                author, place = safe_name(q["author"][0]), safe_name(q["place"][0])
                name = Path(urllib.parse.unquote(q["name"][0])).name
                if Path(name).suffix.lower() not in bp.EXTS:
                    raise ValueError(f"不支持的文件类型：{name}")
                n = int(self.headers.get("Content-Length") or 0)
                dst = unique(bp.ORIG / author / place / name)
                dst.parent.mkdir(parents=True, exist_ok=True)
                with open(dst, "wb") as f:
                    left = n
                    while left > 0:
                        chunk = self.rfile.read(min(left, 1 << 20))
                        if not chunk:
                            break
                        f.write(chunk)
                        left -= len(chunk)
                return self.send_json({"ok": True, "file": dst.name})
            if url.path == "/api/rebuild":
                log = []
                bp.build(log=log.append)
                return self.send_json({"log": log, **state()})
            self.send_error(404)
        except Exception as e:
            self.send_json({"error": f"{type(e).__name__}: {e}"}, 400)

if __name__ == "__main__":
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError as e:
        if e.errno == 48:
            sys.exit(f"端口 {PORT} 已被占用，可能已经有一个 admin.py 在跑。\n"
                     f"先在那个终端按 Ctrl+C 停掉，或运行：  pkill -f scripts/admin.py")
        raise
    print(f"网站      http://localhost:{PORT}/\n管理面板  http://localhost:{PORT}/admin\n按 Ctrl+C 停止")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
