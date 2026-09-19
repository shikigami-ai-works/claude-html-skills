"""設計図の雛形。1つの JSON から、画面（モックと業務フロー）、概念図、ER図の3つを切り替える HTML を書き出す。

使い方:
  python build_sekkeizu.py 入力.json [--out 出力.html]   書き出す（出力先の既定は入力の "out"）
  python build_sekkeizu.py 入力.json --selftest          陰性対照を回すだけ。何も書かない

入力の形は同じフォルダの sample.json を見る。
見た目の正本は同じフォルダの template.html。案件の HTML は手で直さず、入力を直して書き出し直す。

止まる（書かずに exit 1）: 項目の欠け、線の端が無い、画面や表が知らない物を指す、id の重複、
  画面が同じ段と列に重なる、列の鍵が PK/FK/空 以外、物の kind が new/old/ext 以外、チップの色が g/r/b/空 以外。
警告だけ（書き出しは続ける）: どの画面にも出てこない物、FK を持つのに ER の線が1本も無い表。
"""
import argparse
import copy
import html
import io
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "template.html")
REQUIRED = ("title", "doc", "objects", "lanes", "screens", "screen_edges", "concepts", "concept_edges", "tables", "er_edges")
KINDS = {"new", "old", "ext"}
KEYS = {"", "PK", "FK"}
TONES = {"", "g", "r", "b"}


class Invalid(Exception):
    pass


def _dups(ids, what, errs):
    seen = set()
    for i in ids:
        if i in seen:
            errs.append(f"{what}の id {i} が重複")
        seen.add(i)


def validate(d):
    """止まる誤りがあれば Invalid を投げる。警告の一覧を返す。"""
    errs, warns = [], []
    for k in REQUIRED:
        if k not in d:
            errs.append(f"項目 {k} が無い")
    if errs:
        raise Invalid(errs)
    objs = d["objects"]
    for k, o in objs.items():
        if not o.get("name"):
            errs.append(f"物 {k} に name が無い")
        if o.get("kind") not in KINDS:
            errs.append(f"物 {k} の kind は new / old / ext のどれか（今は {o.get('kind')!r}）")
    lane_ids = [l.get("id") for l in d["lanes"]]
    _dups(lane_ids, "段", errs)
    sids = [s.get("id") for s in d["screens"]]
    _dups(sids, "画面", errs)
    cells = {}
    for s in d["screens"]:
        sid = s.get("id")
        if s.get("lane") not in lane_ids:
            errs.append(f"画面 {sid} の lane {s.get('lane')!r} が段に無い")
        col = s.get("col")
        if not isinstance(col, int) or col < 0:
            errs.append(f"画面 {sid} の col は 0 以上の整数")
        cell = (s.get("lane"), col)
        if cell in cells:
            errs.append(f"画面 {sid} が画面 {cells[cell]} と同じ段と列に重なる")
        cells[cell] = sid
        if not s.get("objs"):
            errs.append(f"画面 {sid} に objs が無い")
        for o in s.get("objs") or []:
            if o not in objs:
                errs.append(f"画面 {sid} が知らない物 {o} を指す")
        for r in s.get("rows") or []:
            if len(r) < 2:
                errs.append(f"画面 {sid} の行は [左, 本文, 印] の形")
            elif len(r) > 2 and isinstance(r[2], dict) and "chip" in r[2] and r[2].get("tone", "") not in TONES:
                errs.append(f"画面 {sid} のチップの tone は g / r / b / 空のどれか")
    cids = [c.get("id") for c in d["concepts"]]
    _dups(cids, "概念", errs)
    for c in cids:
        if c not in objs:
            errs.append(f"概念 {c} が物に無い")
    tids = [t.get("id") for t in d["tables"]]
    _dups(tids, "表", errs)
    for t in d["tables"]:
        if t.get("id") not in objs:
            errs.append(f"表 {t.get('id')} が物に無い")
        if not t.get("fields"):
            errs.append(f"表 {t.get('id')} に列が無い")
        for f in t.get("fields") or []:
            if len(f) < 4:
                errs.append(f"表 {t.get('id')} の列は [日本語名, 英名, 型, 鍵, 注] の形")
            elif f[3] not in KEYS:
                errs.append(f"表 {t.get('id')} の列 {f[1]} の鍵は PK / FK / 空のどれか（今は {f[3]!r}）")
    for name, edges, ids in (("画面の線", d["screen_edges"], set(sids)), ("概念図の線", d["concept_edges"], set(cids)),
                             ("ER図の線", d["er_edges"], set(tids))):
        for e in edges:
            if len(e) < 3:
                errs.append(f"{name} は [元, 先, 札] の形（{e}）")
                continue
            if e[0] not in ids or e[1] not in ids:
                errs.append(f"{name} {e[0]} → {e[1]} の端が無い")
            if len(e) > 3 and e[3] not in ("", "dash"):
                errs.append(f"{name} {e[0]} → {e[1]} の線の種類は dash か空")
    if errs:
        raise Invalid(errs)
    used = {o for s in d["screens"] for o in s["objs"]}
    for k in objs:
        if k not in used:
            warns.append(f"物 {k} がどの画面にも出てこない")
    for t in d["tables"]:
        if any(f[3] == "FK" for f in t["fields"]) and not any(t["id"] in (e[0], e[1]) for e in d["er_edges"]):
            warns.append(f"表 {t['id']} は FK を持つのに ER の線が1本も無い")
    return warns


def render(d):
    tpl = io.open(TEMPLATE, encoding="utf-8").read()
    data = json.dumps({k: v for k, v in d.items() if not k.startswith("_")}, ensure_ascii=False)
    data = data.replace("</", "<\\/")  # 中身に </script> があっても script を閉じさせない
    assert tpl.count("__SEKKEIZU_DATA__") == 1
    return tpl.replace("__SEKKEIZU_DATA__", data).replace("__SEKKEIZU_TITLE__", html.escape(d["title"]))


def build(d, out):
    warns = validate(d)
    for w in warns:
        print("!! 警告:", w)
    text = render(d)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    io.open(out, "w", encoding="utf-8", newline="\n").write(text)
    print(f"書いた: {out}（画面 {len(d['screens'])}、線 {len(d['screen_edges'])}、概念 {len(d['concepts'])}、"
          f"表 {len(d['tables'])}、ER の線 {len(d['er_edges'])}、警告 {len(warns)}）")


def selftest(d):
    """元の入力が通り、わざと壊した入力が全部止まることを確かめる。"""
    ok = True
    try:
        validate(d)
        print("通った: 元の入力")
    except Invalid as e:
        print("NG: 元の入力が止まった", e.args[0])
        ok = False
    first = next(iter(d["objects"]))
    cases = [
        ("画面の線の端が無い", lambda x: x["screen_edges"].append([x["screens"][0]["id"], "zz_missing", "x"])),
        ("画面が知らない物を指す", lambda x: x["screens"][0]["objs"].append("zz_missing")),
        ("画面の id が重複", lambda x: x["screens"][1].__setitem__("id", x["screens"][0]["id"])),
        ("画面が同じ段と列に重なる", lambda x: x["screens"][1].update(lane=x["screens"][0]["lane"], col=x["screens"][0]["col"])),
        ("列の鍵の誤り", lambda x: x["tables"][0]["fields"][0].__setitem__(3, "XX")),
        ("物の kind の誤り", lambda x: x["objects"][first].__setitem__("kind", "zz")),
        ("ER図の線の端が無い", lambda x: x["er_edges"].append([x["tables"][0]["id"], "zz_missing", "x"])),
        ("項目の欠け", lambda x: x.pop("tables")),
    ]
    for label, fn in cases:
        x = copy.deepcopy(d)
        fn(x)
        try:
            validate(x)
            print("NG: 止まらなかった:", label)
            ok = False
        except Invalid:
            print("止まった:", label)
    x = copy.deepcopy(d)
    x["objects"][first]["desc"] = "閉じ札 </script> を含む説明"
    text = render(x)
    body = text[text.index("const DATA = "):]
    if "</script> を含む" in body.split("</script>")[0] or body.count("</script>") != text.count("</script>") - text[:text.index("const DATA = ")].count("</script>"):
        print("NG: 中身の </script> が script を閉じる")
        ok = False
    elif "<\\/script> を含む" in text:
        print("通った: 中身の </script> は埋め込みで無害になる")
    else:
        print("NG: 埋め込みの確かめができん")
        ok = False
    return ok


def main():
    ap = argparse.ArgumentParser(description="設計図の HTML を書き出す")
    ap.add_argument("input")
    ap.add_argument("--out")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    d = json.load(io.open(a.input, encoding="utf-8"))
    if a.selftest:
        sys.exit(0 if selftest(d) else 1)
    out = a.out or d.get("out")
    if not out:
        print("出力先が無い（--out か入力の \"out\"）")
        sys.exit(2)
    try:
        build(d, out)
    except Invalid as e:
        print("止まった。書いていない:")
        for m in e.args[0]:
            print(" -", m)
        sys.exit(1)


if __name__ == "__main__":
    main()
