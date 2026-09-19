"""路線へ色を当てる案を出す。入力の JSON は書き換えない。

使い方: python assign_colors.py 入力.json
入力は build_rosenzu.py の入力の JSON か、同じ形の lines（id、group、color、stations）を持つ JSON。
条件1: 同じ駅を通る路線どうしは、通常の差 15 以上かつ色覚の型の差 8 以上（build_rosenzu.py の警告と同じ線）。
条件2: 同じ区分の路線どうし（記号の一覧で隣に並ぶ）は、通常の差 15 以上。
色は PALETTE（Skill rosenzu の SKILL.md の表と同じ16色）から、1路線1色で重ならないように選ぶ。
今の色がある路線は今の色に近い候補を優先し、無い路線は PALETTE の前の方を優先する。
探索は枝刈りつきの深さ優先で、節の数に上限を置く。上限に当たったら、そこまでの一番良い案を出す。
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_rosenzu as core  # noqa: E402

PALETTE = ["#E74635", "#165CD6", "#189B89", "#AC2A96", "#9970FB", "#25880F", "#D659C5", "#1790D1",
           "#CA2661", "#0E6999", "#107B5E", "#EE4E86", "#6664EC", "#8C3BBF", "#179E56", "#845C0C"]
LIMIT = 5_000_000


def main():
    if len(sys.argv) != 2:
        print("使い方: python assign_colors.py 入力.json")
        sys.exit(2)
    d = core.load(sys.argv[1])
    lines = d.get("lines", [])
    if not lines or len(lines) > len(PALETTE):
        print("!! 路線が %d 本。1本以上、候補の %d 色以下にする" % (len(lines), len(PALETTE)))
        sys.exit(1)
    ids = [ln["id"] for ln in lines]
    old = {ln["id"]: ln.get("color", "") for ln in lines}
    grp = {ln["id"]: ln.get("group") for ln in lines}
    conf = {i: set() for i in ids}
    for s in core.lines_by_station(d).values():
        for a in s:
            for b in s:
                if a != b:
                    conf[a].add(b)
    sib = {i: {j for j in ids if j != i and grp[j] == grp[i] and j not in conf[i]} for i in ids}
    okp = {(x, y): core.delta_e(x, y) >= 15 and min(core.delta_e(x, y, k) for k in core.MACHADO) >= 8
           for x in PALETTE for y in PALETTE if x != y}
    okn = {(x, y): core.delta_e(x, y) >= 15 for x in PALETTE for y in PALETTE if x != y}
    cost = {(i, c): (core.delta_e(old[i], c) if core.COLOR_RE.fullmatch(old[i]) else PALETTE.index(c))
            for i in ids for c in PALETTE}
    order = sorted(ids, key=lambda i: (-len(conf[i]) - len(sib[i]), ids.index(i)))
    best = [float("inf"), None]
    nodes = [0]

    def dfs(k, assign, used, total):
        nodes[0] += 1
        if nodes[0] > LIMIT or total >= best[0]:
            return
        if k == len(order):
            best[0], best[1] = total, dict(assign)
            return
        free = [c for c in PALETTE if c not in used]
        if total + sum(min(cost[(j, c)] for c in free) for j in order[k:]) >= best[0]:
            return
        i = order[k]
        for c in sorted(free, key=lambda c: cost[(i, c)]):
            if all(okp[(c, assign[j])] for j in conf[i] if j in assign) and \
                    all(okn[(c, assign[j])] for j in sib[i] if j in assign):
                assign[i] = c
                used.add(c)
                dfs(k + 1, assign, used, total + cost[(i, c)])
                del assign[i]
                used.discard(c)

    dfs(0, {}, set(), 0.0)
    if best[1] is None:
        print("!! 条件を満たす当て方が見つからない（探索した節 %d）。路線を区分し直すか、同じ駅を通る路線を減らす" % nodes[0])
        sys.exit(1)
    print("探索した節 %d%s" % (nodes[0], "（上限で打ち切り。一番良い案とは限らない）" if nodes[0] > LIMIT else "（全部見た）"))
    for i in ids:
        c = best[1][i]
        print("%-3s %-7s → %s（文字 %s）" % (i, old[i] or "-", c, "白" if core.text_on(c) == core.WHITE else "墨"))


if __name__ == "__main__":
    main()
