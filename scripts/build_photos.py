#!/usr/bin/env python3
"""
把 originals/<作者>/<地点>/ 里的照片压缩成网页用的大图和缩略图，
并更新 js/photos.js。已有条目的 title / date / note 和排列顺序会保留。

用法：  python3 scripts/build_photos.py
依赖：  只用 macOS 自带的 sips，不需要安装任何东西。
"""
import json, re, subprocess, sys, unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ORIG, PHOTOS, THUMBS = ROOT / "originals", ROOT / "photos", ROOT / "thumbs"
DATA = ROOT / "js" / "photos.js"
LARGE_MAX, THUMB_MAX = 2000, 900          # 长边像素
EXTS = {".jpg", ".jpeg", ".png", ".heic", ".tif", ".tiff", ".webp"}
AUTHOR_ORDER = {"越越": 0, "Sherry": 1}

def sips(args):
    return subprocess.run(["sips", *args], capture_output=True, text=True, check=True).stdout

def size(path):
    out = sips(["-g", "pixelWidth", "-g", "pixelHeight", str(path)])
    w = int(re.search(r"pixelWidth:\s*(\d+)", out).group(1))
    h = int(re.search(r"pixelHeight:\s*(\d+)", out).group(1))
    return w, h

def resize(src, dst, max_side):
    dst.parent.mkdir(parents=True, exist_ok=True)
    sips(["-s", "format", "jpeg", "-s", "formatOptions", "82", "-Z", str(max_side), str(src), "--out", str(dst)])

def slug(name):
    n = unicodedata.normalize("NFKC", Path(name).stem)
    return re.sub(r"[^\w\-]+", "-", n).strip("-") or "photo"

def is_image(p):
    return p.is_file() and p.suffix.lower() in EXTS and not p.name.startswith(".")

def subdirs(p):
    return sorted(d for d in p.iterdir() if d.is_dir() and not d.name.startswith("."))

# ---------- photos.js 读写 ----------
def load_entries():
    if not DATA.exists():
        return []
    text = DATA.read_text(encoding="utf-8")
    m = re.search(r"window\.PHOTOS\s*=\s*(\[.*\]);", text, re.S)
    if not m:
        return []
    body = re.sub(r"//[^\n]*", "", m.group(1))
    body = re.sub(r"(\{|,)\s*([A-Za-z_]\w*)\s*:", r'\1 "\2":', body)
    body = re.sub(r",\s*([\]}])", r"\1", body)
    try:
        return json.loads(body)
    except json.JSONDecodeError as e:
        sys.exit(f"读取现有 photos.js 失败：{e}\n请检查语法，或先备份后删除该文件再运行。")

def save_entries(entries):
    lines = ["// 由 scripts/build_photos.py / admin.py 生成。title / date / note 可以手改，重新运行会保留。",
             "// 这里的先后顺序就是网页上的展示顺序。",
             "window.PHOTOS = ["]
    cur = None
    for e in entries:
        key = (e["author"], e["place"])
        if key != cur:
            lines.append(f"\n  // ---- {e['author']} · {e['place']} ----")
            cur = key
        lines.append("  " + json.dumps(e, ensure_ascii=False) + ",")
    lines.append("];\n")
    DATA.write_text("\n".join(lines), encoding="utf-8")

# ---------- 主流程 ----------
def build(log=print):
    if not ORIG.exists():
        raise SystemExit("没有找到 originals/ 文件夹。")
    existing = load_entries()
    old_by_src = {e["src"]: e for e in existing}
    old_index = {e["src"]: i for i, e in enumerate(existing)}
    place_rank = {}
    for i, e in enumerate(existing):
        place_rank.setdefault((e["author"], e["place"]), i)

    entries, found = [], set()
    for author_dir in subdirs(ORIG):
        if author_dir.name.startswith("_"):      # _已移除 等文件夹跳过
            continue
        for place_dir in subdirs(author_dir):
            for f in sorted(p for p in place_dir.iterdir() if is_image(p)):
                rel = Path(author_dir.name) / place_dir.name / f"{slug(f.name)}.jpg"
                large, thumb = PHOTOS / rel, THUMBS / rel
                src_key = f"photos/{rel.as_posix()}"
                found.add(src_key)
                if not large.exists() or large.stat().st_mtime < f.stat().st_mtime:
                    log(f"压缩  {author_dir.name}/{place_dir.name}/{f.name}")
                    resize(f, large, LARGE_MAX)
                    resize(f, thumb, THUMB_MAX)
                w, h = size(large)
                old = old_by_src.get(src_key, {})
                entries.append({
                    "author": author_dir.name, "place": place_dir.name, "file": f.name,
                    "src": src_key, "thumb": f"thumbs/{rel.as_posix()}", "w": w, "h": h,
                    "title": old.get("title", ""), "date": old.get("date", ""), "note": old.get("note", ""),
                })

    for src in old_by_src:
        if src not in found:
            log(f"移除（原图已不在）{src}")
            for p in (ROOT / src, ROOT / src.replace("photos/", "thumbs/", 1)):
                if p.exists():
                    p.unlink()

    big = 10**9
    entries.sort(key=lambda e: (
        AUTHOR_ORDER.get(e["author"], 9), e["author"],
        place_rank.get((e["author"], e["place"]), big), e["place"],
        old_index.get(e["src"], big), e["file"],
    ))
    save_entries(entries)
    log(f"完成：{len(entries)} 张照片，已写入 js/photos.js")
    return entries

if __name__ == "__main__":
    build()
