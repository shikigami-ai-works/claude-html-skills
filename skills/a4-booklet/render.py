#!/usr/bin/env python3
"""a4-booklet の撮影、分割、PDF 化、ZIP 作りを1本にした script。

使い方（どこからでも回せる）:
  python render.py book/book.html --make-noise
  python render.py book/book.html --screenshot --page-count 14
  python render.py book/book.html --screenshot --page-count 14 --scale 2
  python render.py book/book.html --pdf
  python render.py book/book.html --zip

  --make-noise   HTML の隣の img/noise.png に 96x96 の灰色の粒のタイルを作る（seed 42）
  --screenshot   全ページを縦長の PNG 1枚（preview.png）に撮り、pages/<名前>-pNN.png へページごとに分ける
  --pdf          ヘッドレス Chrome で <名前>.pdf に印刷し、大きさとページ数を出す
  --zip          pages/*.png と JPEG（品質 88）の写しを <名前>-pages.zip と <名前>-pages-jpg.zip にまとめる
  --scale        1 は見た目の確認用、2 は渡す用のページ画像
  --page-h       A4 1ページぶんの CSS px。296mm を 96dpi で 1118.74。
                 後半のページほど上端が欠けて写るなら、ここを測り直す

Chrome は --chrome、環境変数 CHROME_PATH、各 OS の既定の場所、PATH の順に探す。
--make-noise、--screenshot、--zip は Pillow を使う（pip install pillow）。--pdf は標準ライブラリだけで動く。
"""
from __future__ import annotations

import argparse
import math
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

A4_WIDTH_PX = 794  # 210mm を 96dpi で


def find_chrome() -> str:
    """Chrome（無ければ Chromium 系）の実行ファイルを探す。環境変数 CHROME_PATH が最優先。"""
    env = os.environ.get("CHROME_PATH")
    if env:
        return env
    cands: list[str] = []
    if os.name == "nt":
        for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"), os.environ.get("LOCALAPPDATA")):
            if base:
                cands.append(os.path.join(base, "Google", "Chrome", "Application", "chrome.exe"))
        for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles")):
            if base:
                cands.append(os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe"))
    elif sys.platform == "darwin":
        cands += ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                  "/Applications/Chromium.app/Contents/MacOS/Chromium"]
    for c in cands:
        if os.path.isfile(c):
            return c
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome"):
        found = shutil.which(name)
        if found:
            return found
    return cands[0] if cands else "google-chrome"


def need_pillow():
    try:
        from PIL import Image
    except ImportError:
        sys.exit("Pillow が要る。pip install pillow で入れてから回す")
    Image.MAX_IMAGE_PIXELS = None  # 冊子の縦長の1枚は既定の上限を超えることがある
    return Image


def run_chrome(chrome: str, profile: Path, args: list[str], url: str) -> None:
    # 別の --user-data-dir を渡す。普段使いの Chrome が起動していると、ヘッドレスが何も書かずに終わることがある
    cmd = [chrome, "--headless=new", "--disable-gpu", "--no-first-run", "--hide-scrollbars",
           f"--user-data-dir={profile}", "--virtual-time-budget=25000", *args, url]
    proc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=180)
    if proc.returncode != 0:
        sys.exit(f"Chrome が exit {proc.returncode} で終わった")


def make_noise(html: Path) -> None:
    Image = need_pillow()
    rnd = random.Random(42)
    img = Image.new("L", (96, 96))
    img.putdata([rnd.randrange(256) for _ in range(96 * 96)])
    out = html.parent / "img" / "noise.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    print(f"noise: {out} ({out.stat().st_size} bytes)")


def screenshot(html: Path, chrome: str, profile: Path, pages: int, scale: int, page_h: float) -> None:
    Image = need_pillow()
    height = math.ceil(pages * page_h)
    shot = html.parent / "preview.png"
    run_chrome(chrome, profile, [f"--force-device-scale-factor={scale}", f"--window-size={A4_WIDTH_PX},{height}",
                                 f"--screenshot={shot}"], html.as_uri())
    if not shot.is_file():
        sys.exit("スクリーンショットが書かれなかった")
    pages_dir = html.parent / "pages"
    pages_dir.mkdir(exist_ok=True)
    with Image.open(shot) as img:
        print(f"shot: {img.width}x{img.height}")
        ph = img.height / pages
        for i in range(pages):
            # 境目には隣のページの帯が 1px 混ざるので、上下 2px を削る
            top = math.ceil(i * ph) + 2
            bot = math.floor((i + 1) * ph) - 2
            img.crop((0, top, img.width, bot)).save(pages_dir / f"{html.stem}-p{i + 1:02d}.png")
    print(f"pages: {pages} sliced into {pages_dir}")


def count_pdf_pages(pdf: Path) -> int:
    return len(re.findall(rb"/Type\s*/Page[^s]", pdf.read_bytes()))


def to_pdf(html: Path, chrome: str, profile: Path) -> None:
    pdf = html.with_suffix(".pdf")
    before = pdf.stat().st_mtime if pdf.exists() else -1.0
    run_chrome(chrome, profile, ["--no-pdf-header-footer", f"--print-to-pdf={pdf}"], html.as_uri())
    if not pdf.exists() or pdf.stat().st_mtime <= before:
        sys.exit(f"PDF が書かれなかった: {pdf}")
    print(f"pdf: {pdf} ({pdf.stat().st_size} bytes)")
    print(f"pdf pages: {count_pdf_pages(pdf)}")


def make_zip(html: Path) -> None:
    Image = need_pillow()
    pages_dir = html.parent / "pages"
    pngs = sorted(pages_dir.glob("*.png")) if pages_dir.is_dir() else []
    if not pngs:
        sys.exit("--zip には pages/ の PNG が要る（先に --screenshot を回す）")
    jpg_dir = html.parent / "pages-jpg"
    jpg_dir.mkdir(exist_ok=True)
    jpgs = []
    for p in pngs:
        out = jpg_dir / (p.stem + ".jpg")
        with Image.open(p) as img:
            img.convert("RGB").save(out, quality=88)
        jpgs.append(out)
    for files, name in ((pngs, f"{html.stem}-pages.zip"), (jpgs, f"{html.stem}-pages-jpg.zip")):
        out = html.parent / name
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            for f in files:
                z.write(f, f.name)
        print(f"zip: {out} ({out.stat().st_size} bytes)")


def main() -> int:
    ap = argparse.ArgumentParser(description="a4-booklet の撮影、分割、PDF 化、ZIP 作り")
    ap.add_argument("html", help="冊子の正本の HTML")
    ap.add_argument("--make-noise", action="store_true")
    ap.add_argument("--screenshot", action="store_true")
    ap.add_argument("--pdf", action="store_true")
    ap.add_argument("--zip", action="store_true")
    ap.add_argument("--page-count", type=int, default=0)
    ap.add_argument("--scale", type=int, default=1)
    ap.add_argument("--page-h", type=float, default=1118.74)
    ap.add_argument("--chrome", default="")
    a = ap.parse_args()

    html = Path(a.html).resolve()
    if not html.is_file():
        sys.exit(f"HTML が見つからない: {html}")
    if not (a.make_noise or a.screenshot or a.pdf or a.zip):
        ap.error("--make-noise、--screenshot、--pdf、--zip のどれかを付ける")
    if a.screenshot and a.page_count < 1:
        ap.error("--screenshot には --page-count が要る")
    chrome = a.chrome or find_chrome()
    if (a.screenshot or a.pdf) and not (os.path.isfile(chrome) or shutil.which(chrome)):
        sys.exit(f"Chrome が見つからない: {chrome}（--chrome か環境変数 CHROME_PATH で場所を指定できる）")

    # Chrome が終わった直後はプロファイルのファイルを掴んでいることがあるので、消せなくても止めない
    with tempfile.TemporaryDirectory(prefix="a4-booklet-", ignore_cleanup_errors=True) as tmp:
        profile = Path(tmp) / "profile"
        if a.make_noise:
            make_noise(html)
        if a.screenshot:
            screenshot(html, chrome, profile, a.page_count, a.scale, a.page_h)
        if a.pdf:
            to_pdf(html, chrome, profile)
        if a.zip:
            make_zip(html)
    return 0


if __name__ == "__main__":
    sys.exit(main())
