"""設計図の HTML を裏の Chrome で開き、3つの図と追いかけの1枚を撮って、描けた四角と線の数を数える。

使い方: python shots.py 入力.json 出力.html 撮影先フォルダ
見る数: 各図の四角の数と線の札の数が、入力の数と一致すること（一致しなければ exit 1）。
撮る物: 画面、概念図、ER図の3枚と、ER図で最初の新規の物を選んだ1枚（幅 1600、高さ 900）。
Chrome の場所は自動で探す。見つからないときは環境変数 CHROME_PATH で指定する。
"""
import io
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")


def find_chrome():
    """Chrome（無ければ Chromium 系）の実行ファイルを探す。環境変数 CHROME_PATH が最優先。"""
    env = os.environ.get("CHROME_PATH")
    if env:
        return env
    cands = []
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


CHROME = find_chrome()


def run(args, timeout=90):
    return subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--window-size=1600,900",
                           "--virtual-time-budget=3000"] + args, capture_output=True, timeout=timeout)


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(2)
    src, html_path, out_dir = sys.argv[1:4]
    d = json.load(io.open(src, encoding="utf-8"))
    os.makedirs(out_dir, exist_ok=True)
    url = Path(html_path).resolve().as_uri()
    stem = os.path.splitext(os.path.basename(html_path))[0]
    want = {"screens": (len(d["screens"]), len(d["screen_edges"])), "concept": (len(d["concepts"]), len(d["concept_edges"])),
            "er": (len(d["tables"]), len(d["er_edges"]))}
    first_new = next((k for k, o in d["objects"].items() if o.get("kind") == "new"), next(iter(d["objects"])))
    ok = True
    for view, (n_nodes, n_edges) in want.items():
        dom = run(["--dump-dom", f"{url}#view={view}"]).stdout.decode("utf-8", "replace")
        got_nodes = len(re.findall(r'class="node ', dom))
        got_edges = len(re.findall(r'class="elabel', dom))
        ready = 'data-ready="1"' in dom
        same = ready and got_nodes == n_nodes and got_edges == n_edges
        ok &= same
        print(f"{'合った' if same else 'NG'} {view}: 四角 {got_nodes}/{n_nodes}、線の札 {got_edges}/{n_edges}、描き終わり {ready}")
    shots = [("screens", ""), ("concept", ""), ("er", ""), ("er", first_new)]
    for view, sel in shots:
        name = f"{stem}_{view}" + (f"_{sel}" if sel else "") + ".png"
        path = os.path.join(out_dir, name)
        run([f"--screenshot={path}", f"{url}#view={view}" + (f"&sel={sel}" if sel else "")])
        size = os.path.getsize(path) if os.path.exists(path) else 0
        ok &= size > 20000
        print(f"撮った {path}（{size} バイト）")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
