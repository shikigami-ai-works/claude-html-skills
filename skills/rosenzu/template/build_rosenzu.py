"""路線図の雛形。長い流れを路線、流れの節目を駅として、鉄道の路線図の形の HTML に書き出す。

使い方:
  python build_rosenzu.py 入力.json [--out 出力.html]   入力の JSON から書き出す（出力先の既定は入力の "out"）
  python build_rosenzu.py 入力.json --selftest          陰性対照と色の式の対照だけを回す。何も書かない
台帳から入力を組み立てる案件では、この file を rosenzu_core.py の名で案件へ複製し、
組み立てた dict を normalize() に通してから selftest() か build() を呼ぶ。

入力の形は同じフォルダの sample.json を見る。守る決まりは3つ。
- 路線の記号（V1 など。大文字1字と数字1〜2桁）は一度振ったら変えない。消した路線の記号は "retired" へ移して欠番にする。
- 路線の区間は "edges"（実在するつながりの一覧。向きつき）にある組だけを通る。
- 駅の鍵は元の台帳の番号をそのまま使う。

区間が edges に無い、駅に名前が無い、記号の形の誤りや重複、欠番の使い回しがあれば、書かずに exit 1 で止まる。
色の検査（記号札の文字、紙との差、彩度、同じ駅を通る路線どうしの差）は警告だけで、書き出しは続ける。
色の式は WCAG の比、OKLab の差 ×100、Machado 2009 の色覚の型。
見た目の正本はこの雛形。
"""
import argparse
import copy
import html
import io
import json
import math
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

WHITE, INK = "#FFFFFF", "#14181A"
PAPER = {"明": "#EEF0EC", "暗": "#131718"}
MACHADO = {
    "protan": [[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216], [-0.003882, -0.048116, 1.051998]],
    "deutan": [[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413], [-0.011820, 0.042940, 0.968881]],
}
ID_RE = re.compile(r"[A-Z][0-9]{1,2}")
COLOR_RE = re.compile(r"#[0-9A-Fa-f]{6}")
DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
REQUIRED = ("title", "groups", "stations", "edges", "lines")


# ---- 色の計算 ----
def _lin(hx):
    out = []
    for i in (1, 3, 5):
        c = int(hx[i:i + 2], 16) / 255
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return out


def _lum(hx):
    r, g, b = _lin(hx)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    hi, lo = sorted((_lum(a), _lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _cbrt(x):
    return math.copysign(abs(x) ** (1 / 3), x)


def _oklab(rgb):
    r, g, b = rgb
    l = _cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b)
    m = _cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b)
    s = _cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b)
    return (0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
            1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s)


def _sim(rgb, kind):
    M = MACHADO[kind]
    return [min(1.0, max(0.0, M[i][0] * rgb[0] + M[i][1] * rgb[1] + M[i][2] * rgb[2])) for i in range(3)]


def delta_e(a, b, kind=None):
    """OKLab の差 ×100。kind に protan か deutan を渡すと、その色覚の型での見え方どうしで比べる。"""
    x, y = _lin(a), _lin(b)
    if kind:
        x, y = _sim(x, kind), _sim(y, kind)
    return 100 * math.dist(_oklab(x), _oklab(y))


def chroma(hx):
    _, a, b = _oklab(_lin(hx))
    return math.hypot(a, b)


def text_on(hx):
    """記号札の文字色。白と墨のうち、コントラスト比が高いほう。"""
    return WHITE if contrast(hx, WHITE) >= contrast(hx, INK) else INK


# ---- 入力と検査 ----
def normalize(d):
    """入力の dict を検査と書き出しの形に揃える。駅の鍵、路線の駅、辺の両端を文字列にする。"""
    d["stations"] = {str(k): ({"name": v} if isinstance(v, str) else dict(v))
                     for k, v in d.get("stations", {}).items()}
    for ln in d.get("lines", []):
        ln["stations"] = [str(n) for n in ln.get("stations", [])]
    for e in d.get("edges", []):
        e["a"], e["b"] = str(e["a"]), str(e["b"])
    return d


def load(path):
    return normalize(json.load(io.open(path, encoding="utf-8")))


def check(d):
    """書き出しを止める誤りの一覧。空なら書き出してよい。"""
    errs = ["入力に %s が無い" % k for k in REQUIRED if k not in d]
    if errs:
        return errs
    if not d["lines"]:
        return ["lines が空"]
    groups = {g["key"] for g in d["groups"]}
    edges = {(e["a"], e["b"]) for e in d["edges"]}
    retired = set(d.get("retired", []))
    for e in d["edges"]:
        if e.get("new") and not DATE_RE.fullmatch(str(e["new"])):
            errs.append("edges %s→%s: new の日付の形が違う %r" % (e["a"], e["b"], e["new"]))
    seen = set()
    for ln in d["lines"]:
        lid = ln.get("id", "")
        if not ID_RE.fullmatch(lid):
            errs.append("路線の記号の形が違う: %r" % lid)
        if lid in seen:
            errs.append("路線の記号が重複: %s" % lid)
        if lid in retired:
            errs.append("欠番の記号を使い回している: %s" % lid)
        seen.add(lid)
        if ln.get("group") not in groups:
            errs.append("%s: groups に無い区分 %r" % (lid, ln.get("group")))
        if not COLOR_RE.fullmatch(ln.get("color", "")):
            errs.append("%s: 色の形が違う %r" % (lid, ln.get("color")))
        for k in ("name", "title"):
            if not ln.get(k):
                errs.append("%s: %s が空" % (lid, k))
        st = ln["stations"]
        if len(st) < 2:
            errs.append("%s: 駅が2つ未満" % lid)
        if len(set(st)) != len(st):
            errs.append("%s: 同じ駅を2回通る" % lid)
        for n in st:
            if not d["stations"].get(n, {}).get("name"):
                errs.append("%s: 名前の無い駅 %s" % (lid, n))
        for a, b in zip(st, st[1:]):
            if (a, b) not in edges:
                errs.append("%s: 区間 %s→%s が edges に無い" % (lid, a, b))
    return errs


def lines_by_station(d):
    by = {}
    for ln in d["lines"]:
        for n in ln["stations"]:
            by.setdefault(n, [])
            if ln["id"] not in by[n]:
                by[n].append(ln["id"])
    return by


def color_warnings(d, by_station):
    col = {ln["id"]: ln["color"] for ln in d["lines"]}
    warns = []
    for lid, c in col.items():
        best = max(contrast(c, WHITE), contrast(c, INK))
        if best < 4.5:
            warns.append("%s %s: 記号札の文字が読みにくい（白でも墨でもコントラスト比 %.2f、4.5 未満）" % (lid, c, best))
        for mode, p in PAPER.items():
            r = contrast(c, p)
            if r < 3:
                warns.append("%s %s: %sの紙との差が %.2f（3 未満）で線が沈む" % (lid, c, mode, r))
        if chroma(c) < 0.10:
            warns.append("%s %s: 彩度 %.3f（0.10 未満）で灰色に見える" % (lid, c, chroma(c)))
    pairs = sorted({tuple(sorted((a, b))) for ids in by_station.values() for a in ids for b in ids if a != b})
    for a, b in pairs:
        n = delta_e(col[a], col[b])
        cvd = min(delta_e(col[a], col[b], k) for k in MACHADO)
        if n < 15:
            warns.append("%s と %s: 同じ駅を通るのに色の差 %.1f（15 未満）" % (a, b, n))
        elif cvd < 8:
            warns.append("%s と %s: 色覚の型によっては差 %.1f（8 未満）" % (a, b, cvd))
    return warns


def selftest(d):
    """誤りを1つずつ仕込んだ写しが止まり、元の入力が通り、色の式が既知の値を返すことを確かめる。"""
    missing = [k for k in REQUIRED if k not in d]
    if missing or not d.get("lines"):
        print("!! 入力の形が足りず、陰性対照を組めない:", missing or "lines が空")
        return False
    ok = True
    first = d["lines"][0]
    a, b, last = first["stations"][0], first["stations"][1], first["stations"][-1]

    def drop_edge(x):
        x["edges"] = [e for e in x["edges"] if (e["a"], e["b"]) != (a, b)]

    def unnamed(x):
        x["lines"][0]["stations"].append("__名前なし__")
        x["edges"].append({"a": last, "b": "__名前なし__"})

    def dup_id(x):
        x["lines"].append(copy.deepcopy(x["lines"][0]))

    def reuse_retired(x):
        x["retired"] = list(x.get("retired", [])) + [x["lines"][0]["id"]]

    for label, fn, needle in [("区間が edges に無い", drop_edge, "edges に無い"),
                              ("名前の無い駅", unnamed, "名前の無い駅"),
                              ("記号の重複", dup_id, "重複"),
                              ("欠番の使い回し", reuse_retired, "欠番")]:
        x = copy.deepcopy(d)
        fn(x)
        errs = check(x)
        hit = any(needle in m for m in errs)
        ok = ok and hit
        print("%s %s: %s" % ("止まった" if hit else "!! 止まらない", label, errs[0] if errs else "誤り無し"))
    base = check(d)
    ok = ok and not base
    print("%s 元の入力: %s" % ("通った" if not base else "!! 通らない", base[0] if base else "誤り無し"))
    # 色の式の対照。値は別の実装（JavaScript の色検査）が同じ組に出した数字
    for x, y, kind, want in [("#00897B", "#11917A", None, 2.6), ("#00897B", "#6F7C7D", "deutan", 1.3)]:
        got = delta_e(x, y, kind)
        hit = abs(got - want) < 0.1
        ok = ok and hit
        print("%s 色の式 %s と %s（%s）: %.2f、既知の値 %.1f" % ("合った" if hit else "!! ずれた", x, y, kind or "通常", got, want))
    return ok


# ---- 書き出し ----
CSS = """:root{--paper:#EEF0EC;--surface:#FAFBF9;--ink:#14181A;--ink2:#5A625F;--ink3:#8A928E;
  --rule:#D5DAD5;--rule2:#C2C8C2;--hot:#A6522B;--cold:#2F5A6E;--dotbg:#FFFFFF;--xring:#14181A}
@media (prefers-color-scheme: dark){
  :root{--paper:#131718;--surface:#1A1F20;--ink:#E7EBE7;--ink2:#9AA49F;--ink3:#6E7873;
        --rule:#2A3132;--rule2:#3A4243;--hot:#DA8B52;--cold:#71A5BE;--dotbg:#E7EBE7;--xring:#0B0D0E}
}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);
  font-family:"Zen Kaku Gothic New","Yu Gothic","Hiragino Kaku Gothic ProN",Meiryo,sans-serif;
  font-size:15px;line-height:1.7;font-variant-numeric:tabular-nums}
a{color:inherit}
.wrap{max-width:1180px;margin:0 auto;padding:52px 28px 96px}
header{border-bottom:1px solid var(--rule2);padding-bottom:22px}
h1{font-family:"Zen Old Mincho","Yu Mincho",serif;font-weight:900;font-size:40px;letter-spacing:.14em;margin:0 0 6px;line-height:1.2}
.sub{color:var(--ink2);font-size:14px;margin:0 0 4px;max-width:76ch}
.sub a{color:var(--cold);margin-right:10px}
.mc{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin:22px 0 14px}
.mc div{background:var(--surface);border:1px solid var(--rule);border-radius:3px;padding:10px 14px}
.mc p{margin:0;font-size:12.5px;color:var(--ink2)}
.mc b{font-family:"Zen Old Mincho","Yu Mincho",serif;font-size:26px;font-weight:700;font-variant-numeric:proportional-nums}
h2{font-family:"Zen Old Mincho","Yu Mincho",serif;font-size:18px;font-weight:700;letter-spacing:.08em;
  margin:34px 0 4px;padding-bottom:6px;border-bottom:1px solid var(--rule2)}
.lgs{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:8px 26px;margin-top:10px}
.lgh{font-size:12.5px;color:var(--ink2);margin:6px 0 2px}
.lgr{display:flex;align-items:center;gap:1px 9px;margin:5px 0;font-size:14px;flex-wrap:wrap}
.lge{flex-basis:100%;padding-left:43px;font-size:12px;color:var(--ink3)}
.lp{display:inline-block;background:var(--c);color:var(--on,#fff);font-weight:700;font-size:11.5px;line-height:1;
  padding:4px 6px;border-radius:4px;text-decoration:none;letter-spacing:.03em}
.lp.big{font-size:13px;padding:5px 7px;min-width:34px;text-align:center}
.lp.s{font-size:10px;padding:2px 4px;margin:0 2px}
.key{display:flex;flex-wrap:wrap;gap:8px 20px;font-size:12.5px;color:var(--ink2);margin:14px 0 0}
.key>span{display:inline-flex;align-items:center;gap:6px}
.kd{width:16px;height:16px;border-radius:50%;border:4px solid var(--ink2);background:var(--dotbg);display:inline-block}
.kd.x{width:20px;height:20px;border:4px solid var(--xring);box-shadow:0 0 0 2px var(--ink2)}
.kd.u{border-style:dashed}
.ln{border-bottom:1px solid var(--rule);padding:16px 0 14px;scroll-margin-top:12px}
.ln:target{background:color-mix(in srgb,var(--c) 8%,transparent)}
.lh{display:flex;align-items:flex-start;gap:12px;margin-bottom:12px}
.id{flex:none;background:var(--c);color:var(--on,#fff);font-weight:700;font-size:18px;line-height:1;
  padding:9px 0;width:52px;text-align:center;border-radius:8px;letter-spacing:.03em}
.nm{display:flex;flex-wrap:wrap;align-items:center;gap:8px;font-size:16px;font-weight:700;margin:0}
.ti{margin:0;font-size:13px;color:var(--ink2)}
.tg{font-size:11px;font-weight:400;padding:0 8px;border-radius:2px;border:1px solid var(--cold);color:var(--cold);white-space:nowrap}
.tg.h{border-color:var(--hot);color:var(--hot)}
.tr{display:flex;align-items:flex-start;padding:0 4px}
.st{flex:0 0 120px;position:relative;text-align:center}
.st::before,.st::after{content:"";position:absolute;top:9px;height:8px;background:var(--c)}
.st::before{left:0;right:50%}
.st::after{left:50%;right:0}
.st.first::before,.st.last::after{display:none}
.dot{position:relative;z-index:1;display:block;width:26px;height:26px;margin:0 auto;border-radius:50%;
  background:var(--dotbg);border:5px solid var(--c)}
.st.x .dot{width:30px;height:30px;margin-top:-2px;border:5px solid var(--xring);box-shadow:0 0 0 3px var(--c)}
.st.u .dot{border-style:dashed}
.tx{display:block;margin-top:6px}
.sn{display:block;font-size:10.5px;color:var(--ink3);letter-spacing:.02em}
.sl{display:block;font-size:13.5px;font-weight:500;line-height:1.4;padding:0 4px}
.xf{display:block;margin-top:3px}
.sg{flex:1 1 auto;min-width:26px;height:8px;margin-top:9px;background:var(--c);position:relative}
.sg.w{background:repeating-linear-gradient(90deg,var(--c) 0 14px,color-mix(in srgb,var(--c) 45%,var(--paper)) 14px 18px)}
.wd{position:absolute;left:50%;bottom:12px;transform:translateX(-50%);font-size:10.5px;color:var(--cold);
  border:1px solid var(--cold);border-radius:2px;padding:0 4px;white-space:nowrap;background:var(--paper);line-height:1.5}
.nt{font-size:12.5px;color:var(--ink2);margin:12px 0 0;max-width:90ch}
.xt{overflow-x:auto;margin-top:8px}
table{border-collapse:collapse;font-size:13.5px;min-width:520px}
th,td{text-align:left;padding:6px 12px 6px 0;border-bottom:1px solid var(--rule);vertical-align:middle}
th{font-size:12px;color:var(--ink2);font-weight:500}
td .lp{margin-right:4px}
.xn{font-family:"Zen Old Mincho","Yu Mincho",serif;font-weight:700;color:var(--ink2)}
.foot{margin-top:40px;padding-top:18px;border-top:1px solid var(--rule2);font-size:12.5px;color:var(--ink3);max-width:84ch}
.foot p{margin:0 0 6px}
.sub,.ti,.sl,.nt,.foot,td{overflow-wrap:anywhere}
@media (max-width:720px){
  .wrap{padding:32px 15px 64px}h1{font-size:30px}
  .lgs{grid-template-columns:1fr}
  .tr{flex-direction:column;padding:0}
  .st{flex:none;display:flex;align-items:center;gap:12px;text-align:left;min-height:44px;padding-left:2px}
  .st::before,.st::after{top:auto;height:auto;width:8px;left:11px;right:auto}
  .st::before{top:0;bottom:50%}
  .st::after{top:50%;bottom:0}
  .dot{margin:0;flex:none}
  .st.x .dot{margin:0 0 0 -2px}
  .tx{margin:0}
  .sg{flex:none;width:8px;min-width:0;height:26px;margin:0 0 0 11px}
  .sg.w{background:repeating-linear-gradient(180deg,var(--c) 0 10px,color-mix(in srgb,var(--c) 45%,var(--paper)) 10px 14px)}
  .wd{left:20px;bottom:auto;top:50%;transform:translateY(-50%)}
}"""

PAGE = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Zen+Old+Mincho:wght@400;700;900&family=Zen+Kaku+Gothic+New:wght@400;500;700&display=swap" rel="stylesheet">
<style>
__CSS__
</style>
</head>
<body>
<div class="wrap">
<header>
<h1>__TITLE__</h1>
__LEAD__
</header>
<div class="mc">__CARDS__</div>
<h2>路線の記号</h2>
<div class="lgs">__LEGEND__</div>
<div class="key">__KEY__</div>
__ROWS__
__XFER__
<div class="foot">__FOOT__</div>
</div>
</body>
</html>
"""


def render(d, source_label, regen):
    """HTML の本文、数（路線、駅、乗換駅、札）、色の警告を返す。source_label と regen は作り方の欄に出す。"""
    esc = html.escape
    S = d["stations"]
    E = {(e["a"], e["b"]): e for e in d["edges"]}
    LINES = d["lines"]
    new_label = d.get("new_label", "開通")
    by_station = lines_by_station(d)
    COLOR = {ln["id"]: ln["color"] for ln in LINES}

    def style(lid):
        return "--c:%s;--on:%s" % (COLOR[lid], text_on(COLOR[lid]))

    def pill(lid, cls="lp"):
        return '<a class="%s" href="#%s" style="%s">%s</a>' % (cls, lid, style(lid), lid)

    def code(n):
        return "#" + n if n.isdigit() else n

    def station(ln, i, n):
        s = S[n]
        cls = ["st"]
        if i == 0:
            cls.append("first")
        if i == len(ln["stations"]) - 1:
            cls.append("last")
        others = [x for x in by_station[n] if x != ln["id"]]
        if others:
            cls.append("x")
        if s.get("unverified"):
            cls.append("u")
        tip = "%s %s" % (code(n), s["name"])
        if s.get("tip"):
            tip += "\n" + s["tip"]
        xf = '<span class="xf">%s</span>' % "".join(pill(x, "lp s") for x in others) if others else ""
        return ('<div class="%s" title="%s"><span class="dot"></span><span class="tx">'
                '<span class="sn">%s-%d　%s</span><span class="sl">%s</span>%s</span></div>') % (
            " ".join(cls), esc(tip, quote=True), ln["id"], i + 1, esc(code(n)), esc(s["name"]), xf)

    def segment(a, b):
        e = E[(a, b)]
        tip = "%s→%s" % (code(a), code(b))
        if e.get("tip"):
            tip += " " + e["tip"]
        tip = esc(tip[:400], quote=True)
        if e.get("new"):
            return '<div class="sg w" title="%s"><span class="wd">%d/%d %s</span></div>' % (
                tip, int(e["new"][5:7]), int(e["new"][8:10]), esc(new_label))
        return '<div class="sg" title="%s"></div>' % tip

    used = [(a, b) for ln in LINES for a, b in zip(ln["stations"], ln["stations"][1:])]
    used_new = sorted({p for p in used if E[p].get("new")}, key=lambda p: E[p]["new"])
    legend, rows = [], []
    for g in d["groups"]:
        mine = [ln for ln in LINES if ln["group"] == g["key"]]
        if not mine:
            continue
        legend.append('<div class="lgg"><p class="lgh">%s</p>%s</div>' % (esc(g["name"]), "".join(
            '<p class="lgr">%s<span>%s</span><span class="lge">%s %s → %s %s</span></p>' % (
                pill(ln["id"], "lp big"), esc(ln["name"]),
                esc(code(ln["stations"][0])), esc(S[ln["stations"][0]]["name"]),
                esc(code(ln["stations"][-1])), esc(S[ln["stations"][-1]]["name"])) for ln in mine)))
        rows.append('<h2 class="grp">%s</h2>' % esc(g["name"]))
        for ln in mine:
            ch = ln["stations"]
            nnew = sum(1 for a, b in zip(ch, ch[1:]) if E[(a, b)].get("new"))
            tags = '<span class="tg">新しい区間 %d</span>' % nnew if nnew else ""
            tags += "".join('<span class="tg h">%s</span>' % esc(f) for f in ln.get("flags", []))
            parts = [station(ln, 0, ch[0])]
            for i, (a, b) in enumerate(zip(ch, ch[1:]), start=1):
                parts += [segment(a, b), station(ln, i, b)]
            note = '<p class="nt">%s</p>' % esc(ln["note"]) if ln.get("note") else ""
            rows.append('<section class="ln" id="%s" style="%s"><div class="lh"><span class="id">%s</span>'
                        '<div><p class="nm">%s%s</p><p class="ti">%s</p></div></div>'
                        '<div class="tr">%s</div>%s</section>' % (
                            ln["id"], style(ln["id"]), ln["id"], esc(ln["name"]), tags, esc(ln["title"]),
                            "".join(parts), note))

    def order(n):
        return (-len(by_station[n]), (0, int(n), "") if n.isdigit() else (1, 0, n))

    xs = sorted((n for n, ids in by_station.items() if len(ids) >= 2), key=order)
    xfer = ""
    if xs:
        xfer = ('<h2>乗換駅</h2><div class="xt"><table><thead><tr><th>番号</th><th>駅</th><th>路線数</th>'
                '<th>通る路線</th></tr></thead><tbody>%s</tbody></table></div>') % "".join(
            '<tr><td class="xn">%s</td><td>%s</td><td>%d</td><td>%s</td></tr>' % (
                esc(code(n)), esc(S[n]["name"]), len(by_station[n]), "".join(pill(x) for x in by_station[n]))
            for n in xs)

    key = ['<span><span class="kd"></span>駅</span>',
           '<span><span class="kd x"></span>乗換駅（名札の下に乗り換えられる路線）</span>']
    if any(S[n].get("unverified") for n in by_station):
        key.append('<span><span class="kd u"></span>%s</span>' % esc(d.get("unverified_label", "節目そのものの動作が未確認")))
    if used_new:
        last = E[used_new[-1]]["new"]
        key.append('<span><span class="tg" style="font-size:10.5px">%d/%d %s</span>その日に%sした区間（線は破線）</span>' % (
            int(last[5:7]), int(last[8:10]), esc(new_label), esc(new_label)))
    flags = []
    for ln in LINES:
        for f in ln.get("flags", []):
            if f not in flags:
                flags.append(f)
    for f in flags:
        key.append('<span><span class="tg h">%s</span>%s</span>' % (esc(f), esc(d.get("flag_notes", {}).get(f, ""))))

    cards = [("路線", "%d本" % len(LINES)), ("駅", "%d駅" % len(by_station)),
             ("乗換駅（2路線以上が通る）", "%d駅" % len(xs))]
    if used_new:
        cards.append(("新しい区間", "%dか所" % len(used_new)))

    ex_line = max(LINES, key=lambda ln: len(ln["stations"]))
    k = min(3, len(ex_line["stations"]))
    ex_code = code(ex_line["stations"][k - 1])
    lead = '<p class="sub">%s</p>' % esc(d.get("lead", ""))
    lead += ('<p class="sub">路線の記号は今後も変えない。駅の名札の「%s-%d　%s」は、%s 線の%dつ目の駅で、元の番号が %s という意味。</p>' % (
        ex_line["id"], k, esc(ex_code), ex_line["id"], k, esc(ex_code)))
    if d.get("links"):
        lead += '<p class="sub">%s</p>' % "".join(
            '<a href="%s">%s</a>' % (esc(x["href"], quote=True), esc(x["label"])) for x in d["links"])

    foot = ('<p>作り方: %s（実在するつながり %d 本）と照合して書き出した。区間が1つでも一覧に無ければ、書き出さずに止まる。</p>'
            '<p>各路線のメモは %s 時点。駅と区間に指を置くと説明が出る。路線の記号を押すと、その路線へ飛ぶ。</p>'
            '<p>路線を足すときは、次の空き記号で書き足す（retired の記号は使い回さない）。作り直し: %s</p>') % (
        esc(source_label), len(d["edges"]), esc(d.get("as_of", "-")), esc(regen))

    parts = {
        "TITLE": esc(d["title"]), "CSS": CSS, "LEAD": lead,
        "CARDS": "".join('<div><p>%s</p><b>%s</b></div>' % (esc(a), esc(b)) for a, b in cards),
        "LEGEND": "".join(legend), "KEY": "\n".join(key), "ROWS": "\n".join(rows), "XFER": xfer, "FOOT": foot,
    }
    page = re.sub(r"__([A-Z]+)__", lambda m: parts[m.group(1)], PAGE)
    stats = {"lines": len(LINES), "stations": len(by_station), "xfer": len(xs),
             "labels": sum(len(ln["stations"]) for ln in LINES),
             "xlabels": sum(1 for ln in LINES for n in ln["stations"] if len(by_station[n]) >= 2)}
    return page, stats, color_warnings(d, by_station)


def build(d, out, source_label, regen):
    """検査して書き出す。戻り値は exit の値（0 は書き出した、1 は止まった）。"""
    errs = check(d)
    if errs:
        for m in errs:
            print("!!", m)
        return 1
    if not out:
        print('!! 出力先が無い（入力の "out" か --out で渡す）')
        return 1
    page, stats, warns = render(d, source_label, regen)
    for w in warns:
        print("!! 色:", w)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    io.open(out, "w", encoding="utf-8", newline="\n").write(page)
    print("書き出し: %s ／ 路線 %d 本、駅 %d、乗換駅 %d ／ 駅の札 %d（うち乗換 %d）／ 色の警告 %d" % (
        out, stats["lines"], stats["stations"], stats["xfer"], stats["labels"], stats["xlabels"], len(warns)))
    return 0


def main():
    ap = argparse.ArgumentParser(description="路線図の雛形")
    ap.add_argument("src", help="入力の JSON")
    ap.add_argument("--out", help="出力の HTML（既定は入力の out）")
    ap.add_argument("--selftest", action="store_true", help="陰性対照と色の式の対照だけを回す")
    args = ap.parse_args()
    src = os.path.abspath(args.src)
    d = load(src)
    if args.selftest:
        sys.exit(0 if selftest(d) else 1)
    sys.exit(build(d, args.out or d.get("out"), "%s の lines（路線）を edges" % src,
                   "python %s %s" % (os.path.abspath(__file__), src)))


if __name__ == "__main__":
    main()
