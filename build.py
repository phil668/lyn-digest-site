#!/usr/bin/env python3
"""Rebuild Lyn digest site (magazine layout) from /workspace/lyn-digests/*.md.

头条标记约定（可选，旧期无则不显示双头条条带）::

    **头条｜游戏｜标题**
    正文…
    来源：…

    **头条｜AI视频｜标题**
    …

领域正文::

    **经济｜标题**
    …

志怪仍用含「志怪」的 **…｜…** 或标题行；签名行 ——日知／——拓 不进网格。
"""
import html
import re
import sys
import datetime
from pathlib import Path

WD = "一二三四五六日"
ORDER = {"上午": 0, "午间": 1, "晚间": 2}
SLOT = {"下午": "午间"}
SRC = Path(sys.argv[1] if len(sys.argv) > 1 else "/workspace/lyn-digests")
OUT = Path(__file__).resolve().parent
XZ_SRC = Path("/workspace/lyn-xiaozao")
ZONES = [
    ("zhiguai", "灵异志怪", "鬼故事、搜神与志异"),
    ("minsu", "传统民俗", "节令、礼俗与民间规矩"),
    ("shenhua", "神话传说", "山海经与古史传说"),
    ("history", "历史人物", "人物志与专名大事"),
]
ZONE_KEY = {name: key for key, name, _ in ZONES}
ZONE_PAGE = {key: f"xiaozao-{key}.html" for key, _, _ in ZONES}

# **头条｜领域｜标题** 或 **领域｜标题**
HEADLINE_RE = re.compile(r"^\*\*头条｜([^｜*]+)｜(.+?)\*\*\s*$")
PIECE_RE = re.compile(r"^\*\*([^｜*\n]+)｜(.+?)\*\*\s*$")
SIG_RE = re.compile(r"^——")


def dlabel(d):
    t = datetime.date.fromisoformat(d)
    return f"{t.month}月{t.day}日 · 周{WD[t.weekday()]}"


def inline(t):
    t = html.escape(t, quote=False)
    links = []

    def lk(m):
        links.append(
            f'<a href="{html.escape(m.group(2))}" target="_blank" rel="noopener">{m.group(1)}</a>'
        )
        return f"\x00{len(links)-1}\x00"

    t = re.sub(r"\[([^\]]+)\]\((\S+?)\)", lk, t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<![\*\w])\*([^*\n]+?)\*(?!\*)", r"<em>\1</em>", t)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    return re.sub(r"\x00(\d+)\x00", lambda m: links[int(m.group(1))], t)


def strip_md(s):
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
    s = re.sub(r"[*#`_>]+", "", s)
    return s.strip()


def parse(p):
    meta, lines = {}, p.read_text(encoding="utf-8").split("\n")
    while lines and re.match(r"#\s*[^\s:：]+[:：]", lines[0]):
        k, v = re.split(r"[:：]", lines.pop(0)[1:], maxsplit=1)
        meta[k.strip()] = v.strip()
    meta.setdefault("署名", "拓" if "期次" in meta else "日知")
    meta["slot"] = SLOT.get(meta.get("时段", ""), meta.get("时段", ""))
    meta["slug"] = p.stem
    return meta, "\n".join(lines).strip()


def split_sections(body):
    """Split body into preamble, headlines[], pieces[], zhiguai_md, signoff."""
    lines = body.split("\n")
    blocks = []  # list of (kind, domain, title, body_lines)
    i = 0
    preamble = []
    while i < len(lines):
        line = lines[i]
        hm = HEADLINE_RE.match(line.strip())
        pm = PIECE_RE.match(line.strip()) if not hm else None
        # 期头大标题不算条目
        if pm and (
            pm.group(1).strip().startswith("日知知识分享")
            or pm.group(1).strip().startswith("拓的知识分享")
            or pm.group(1).strip() in ("日知知识分享", "拓的知识分享")
        ):
            if not blocks:
                preamble.append(line)
            i += 1
            continue
        if hm or pm:
            if hm:
                kind, domain, title = "headline", hm.group(1).strip(), hm.group(2).strip()
            else:
                domain, title = pm.group(1).strip(), pm.group(2).strip()
                kind = "zhiguai" if any(k in domain or k in title for k in ("志怪", "小灶", "民俗", "神话", "传说", "历史")) else "piece"
            i += 1
            body_lines = []
            while i < len(lines):
                nxt = lines[i]
                if HEADLINE_RE.match(nxt.strip()) or PIECE_RE.match(nxt.strip()):
                    break
                if SIG_RE.match(nxt.strip()):
                    break
                body_lines.append(nxt)
                i += 1
            # trim blank edges
            while body_lines and not body_lines[0].strip():
                body_lines.pop(0)
            while body_lines and not body_lines[-1].strip():
                body_lines.pop()
            blocks.append((kind, domain, title, body_lines))
            continue
        if SIG_RE.match(line.strip()):
            signoff = line.strip()
            i += 1
            # rest ignored after signature
            while i < len(lines) and not lines[i].strip():
                i += 1
            headlines = [b for b in blocks if b[0] == "headline"]
            pieces = [b for b in blocks if b[0] == "piece"]
            zg = [b for b in blocks if b[0] == "zhiguai"]
            return preamble, headlines, pieces, zg, signoff
        if not blocks:
            if line.strip():
                preamble.append(line)
        i += 1

    headlines = [b for b in blocks if b[0] == "headline"]
    pieces = [b for b in blocks if b[0] == "piece"]
    zg = [b for b in blocks if b[0] == "zhiguai"]
    return preamble, headlines, pieces, zg, ""


def body_to_paras(body_lines):
    """Turn piece body lines into HTML paragraphs; 来源 lines -> .sources."""
    if not body_lines:
        return ""
    paras, cur = [], []
    for line in body_lines:
        if not line.strip():
            if cur:
                paras.append("\n".join(cur))
                cur = []
            continue
        cur.append(line)
    if cur:
        paras.append("\n".join(cur))
    out = []
    for block in paras:
        raw = block.strip()
        lines = raw.split("\n")
        body_ls, src_ls = [], []
        for x in lines:
            if (not src_ls) and x.strip().startswith("来源"):
                src_ls.append(x.strip())
            elif src_ls:
                src_ls.append(x.strip())
            else:
                body_ls.append(x)
        if body_ls:
            out.append("<p>" + "<br>\n".join(inline(x) for x in body_ls) + "</p>")
        if src_ls:
            out.append(f'<p class="sources">{inline(" ".join(src_ls))}</p>')
    return "\n".join(out)



def render_double_lead(headlines):
    if not headlines:
        return ""
    # order: prefer 游戏 then AI视频, else keep file order
    def rank(h):
        d = h[1].replace(" ", "")
        if "游戏" in d:
            return 0
        if "AI视频" in d or "AI影像" in d:
            return 1
        return 2

    ordered = sorted(headlines, key=rank)
    cards = []
    for kind, domain, title, body_lines in ordered:
        cards.append(
            f'<section class="lead-card">'
            f'<div class="lead-eyebrow">'
            f'<span class="section-label lead-label">{html.escape(domain)}</span>'
            f'<span class="lead-mark">头条</span></div>'
            f"<h2>{html.escape(title)}</h2>"
            f'<div class="piece-body">{body_to_paras(body_lines)}</div>'
            f"</section>"
        )
    # if only one headline, still show band
    return (
        f'<div class="double-lead" aria-label="本期头条">'
        f'<div class="double-lead-band">本期头条</div>'
        f'<div class="double-lead-grid">{"".join(cards)}</div></div>'
    )


def render_piece_grid(pieces):
    if not pieces:
        return ""
    cells = []
    for kind, domain, title, body_lines in pieces:
        cells.append(
            f'<section class="piece">'
            f'<span class="section-label">{html.escape(domain)}</span>'
            f"<h2>{html.escape(title)}</h2>"
            f'<div class="piece-body">{body_to_paras(body_lines)}</div>'
            f"</section>"
        )
    return f'<div class="piece-grid">{"".join(cells)}</div>'



def format_hist_body(body_lines):
    """Like body_to_paras, but pair 原文／白话 into quote cards when consecutive."""
    if not body_lines:
        return ""
    html_parts, i = [], 0
    lines = list(body_lines)
    while i < len(lines):
        s = lines[i].strip()
        if s.startswith("原文") and i + 1 < len(lines) and lines[i+1].strip().startswith("白话"):
            src = s
            bai = lines[i+1].strip()
            # optional following blank skip
            html_parts.append(
                f'<div class="hist-quote"><span class="q-src">正史摘录</span>'
                f'<div>{inline(src)}</div>'
                f'<div class="hist-baihua">{inline(bai)}</div></div>'
            )
            i += 2
            continue
        if not s:
            i += 1
            continue
        # gather paragraph until blank
        chunk = [lines[i]]
        i += 1
        while i < len(lines) and lines[i].strip():
            # break if next is 原文 start of pair
            if lines[i].strip().startswith("原文") and i + 1 < len(lines) and lines[i+1].strip().startswith("白话"):
                break
            chunk.append(lines[i])
            i += 1
        html_parts.append("<p>" + "<br>\n".join(inline(x) for x in chunk) + "</p>")
    return "".join(html_parts)


def classify_xiaozao(domain, title):
    blob = domain + title
    if "历史" in blob:
        return "历史", "hist"
    if "神话" in blob or "传说" in blob:
        return "神话", "myth"
    if "民俗" in blob:
        return "民俗", "folk"
    return "志怪", "ghost"


def render_zhiguai(zg, column_href, hist_href=None):
    """zg: list of blocks. History goes to separate page; others in 小灶 grid."""
    if not zg:
        return ""
    cards, hist = [], None
    for kind, domain, title, body_lines in zg:
        sub, cls = classify_xiaozao(domain, title)
        if sub == "历史":
            hist = (domain, title, body_lines)
            continue
        disp = title
        for pre in ("志怪｜", "民俗｜", "神话｜", "传说｜", "历史｜", "志怪小灶：", "附｜志怪小灶："):
            if disp.startswith(pre):
                disp = disp[len(pre):]
        cards.append(
            f'<div class="xz-card xz-{cls}">'
            f'<div class="xz-sub">{sub}</div>'
            f'<h3 class="zg-title">{html.escape(disp)}</h3>'
            f'<div class="zg-body">{body_to_paras(body_lines)}</div></div>'
        )
    parts = []
    if cards:
        n = len(cards)
        gcls = "xz-grid three" if n >= 3 else ("xz-grid two" if n == 2 else "xz-grid")
        parts.append(
            f'<aside class="zg-spread" id="zhiguai">'
            f'<div class="tag-row"><span class="zg-tag">小灶 · 志怪＋民俗＋神话</span>'
            f'<a class="col-link" href="{column_href}">查看小灶</a></div>'
            f'<div class="{gcls}">{"".join(cards)}</div></aside>'
        )
    if hist and hist_href:
        _, title, _ = hist
        disp = title
        for pre in ("历史｜",):
            if disp.startswith(pre):
                disp = disp[len(pre):]
        parts.append(
            f'<a class="hist-teaser" href="{hist_href}">'
            f'<span class="ht-kicker">小灶 · 历史专页</span>'
            f'<span class="ht-title">{html.escape(disp)}</span>'
            f'<span class="ht-go">读完整人物志 →</span></a>'
        )
    return "".join(parts)


def render_history_page(m, hist, root="../"):
    domain, title, body_lines = hist
    disp = title
    for pre in ("历史｜",):
        if disp.startswith(pre):
            disp = disp[len(pre):]
    serial = ""
    if "第" in disp and "天" in disp:
        serial = '<div class="hist-serial">人物志 · 可按篇幅分日连载</div>'
    body = (
        f'<div class="issue-page hist-page">'
        f'<div class="issue-mast"><a class="brand-sm" href="{root}index.html">Justknow</a>'
        f'<span class="meta-sm">{m["日期"].replace("-", " · ")} · {html.escape(m["slot"])} · 历史</span></div>'
        f'<header class="issue-head"><div class="issue-kicker">小灶 · 历史专页</div>'
        f'<h1 class="issue-title">{html.escape(disp)}</h1>'
        f'<div class="byline">文 · <span class="who who-{m["署名"]}">{m["署名"]}</span></div></header>'
        f'{serial}'
        f'<div class="hist-body">{format_hist_body(body_lines)}</div>'
        f'<footer class="folio"><a href="{m["slug"]}.html">← 回本期</a>'
        f'<span class="center">{html.escape(dlabel(m["日期"]).split(" · ")[0])} · 历史</span>'
        f'<a href="{root}xiaozao.html">小灶</a></footer></div>'
    )
    return page(f'历史 · {disp}', body, root, active="xiaozao")


def render_preamble(preamble):
    if not preamble:
        return ""
    # skip the big **日知知识分享｜…** title line if present
    lines = []
    for l in preamble:
        s = l.strip()
        if s.startswith("**日知知识分享") or s.startswith("**拓的知识分享"):
            continue
        if s:
            lines.append(l)
    if not lines:
        return ""
    return '<p class="greeting">' + "<br>\n".join(inline(x) for x in lines) + "</p>"


def extract_zhiguai(body):
    """Return (title, excerpt_plain) or None — for column index."""
    _, _, _, zgs, _ = split_sections(body)
    if not zgs:
        return None
    out = []
    for _, domain, title, body_lines in zgs:
        out.append(_zg_one(domain, title, body_lines))
    return out


def _zg_one(domain, title, body_lines):
    excerpt = ""
    for l in body_lines:
        s = strip_md(l)
        if not s or s.startswith("来源"):
            continue
        excerpt = s
        break
    if len(excerpt) > 120:
        excerpt = excerpt[:120] + "…"
    return title, excerpt


def page(title, body, root, active=None, wrap_main=True):
    nav_links = [
        ("index.html", "首页", "home"),
        ("rizhi.html", "日知", "rizhi"),
        ("xiaozao.html", "小灶", "xiaozao"),
    ]
    links_html = "".join(
        f'<a href="{root}{href}" class="nav-link{" active" if active == key else ""}">{label}</a>'
        for href, label, key in nav_links
    )
    inner = body if not wrap_main else f"<main>{body}</main>"
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>
<link rel="stylesheet" href="{root}styles.css"><script>if(localStorage.theme)document.documentElement.dataset.theme=localStorage.theme</script></head>
<body><nav class="top"><a href="{root}index.html" class="brand">Justknow</a>
<div class="nav-right">{links_html}
<button type="button" onclick="var d=document.documentElement;d.dataset.theme=d.dataset.theme=='dark'?'light':'dark';localStorage.theme=d.dataset.theme" aria-label="切换主题">◐</button></div></nav>
{inner}<footer>Justknow · Lyn每日三次知识分享</footer></body></html>"""


def first_piece_teaser(body):
    _, headlines, pieces, zg, _ = split_sections(body)
    if headlines:
        return f"{headlines[0][1]}｜{headlines[0][2]}"
    if pieces:
        return f"{pieces[0][1]}｜{pieces[0][2]}"
    first = next(
        (
            re.sub(r"[*#\[\]]|\(http\S+\)", "", l).strip()
            for l in body.split("\n")
            if l.strip() and not l.startswith("Lyn")
        ),
        "",
    )
    return first


def _clip(t, n):
    t = strip_md(t)
    return t if len(t) <= n else t[:n] + "…"


def _short_title(teaser):
    """'领域｜标题' -> '标题'；去掉 '1. ' 序号。"""
    t = re.sub(r"^\d+\.\s*", "", strip_md(teaser))
    return t.split("｜", 1)[1] if "｜" in t else t


def _first_body_line(body_lines):
    for l in body_lines:
        x = strip_md(l)
        if x and not x.startswith("来源"):
            return x
    return ""


def slot_card(slot, m, body, featured=False):
    if m is None:
        return (
            f'<div class="slot-card pending" aria-disabled="true">'
            f'<div class="slot-label"><span>{slot}</span><span class="time">待刊</span></div>'
            f'<div class="who-line"><span class="who">日知</span> · 日知连载</div>'
            f'<h3>{slot}场尚未付印</h3>'
            f'<p class="tease">刊出后会出现在这里，并同步进近日小卡。</p>'
            f'<span class="open">待刊 · 请稍候</span></div>'
        )
    _, headlines, pieces, _, _ = split_sections(body)
    href = f'issues/{m["slug"]}.html'
    who = html.escape(m["署名"])
    label = html.escape(m.get("期次") or "日知连载")
    when = html.escape(m.get("计划时间", ""))
    if headlines:
        doms = " × ".join(h[1] for h in headlines[:2])
        h3 = f"双头条 · {doms}"
        rows = "".join(
            f'<div class="row"><span class="tag">{html.escape(h[1])}</span>'
            f'<span>{html.escape(_clip(h[2], 46))}</span></div>'
            for h in headlines[:2]
        )
        inner = f'<div class="dual-tease">{rows}</div>'
    elif pieces:
        h3 = _clip(pieces[0][2], 30)
        inner = f'<p class="tease">{html.escape(_clip(_first_body_line(pieces[0][3]), 72))}</p>'
    else:
        h3 = _clip(_short_title(first_piece_teaser(body)), 30) or "本期"
        inner = '<p class="tease"></p>'
    cls = "slot-card featured" if featured else "slot-card"
    return (
        f'<a class="{cls}" href="{href}">'
        f'<div class="slot-label"><span>{slot}</span><span class="time">{when}</span></div>'
        f'<div class="who-line"><span class="who">{who}</span> · {label}</div>'
        f"<h3>{html.escape(h3)}</h3>{inner}"
        f'<span class="open">打开本期 →</span></a>'
    )


def parse_xz(p):
    """Parse a 小灶 source md: #日期/#时段/#专区/#标题 + body."""
    lines = p.read_text(encoding="utf-8").split("\n")
    meta = {}
    while lines and re.match(r"#\s*[^\s:：]+[:：]", lines[0]):
        k, v = re.split(r"[:：]", lines.pop(0)[1:], maxsplit=1)
        meta[k.strip()] = v.strip()
    zone_name = meta.get("专区", "灵异志怪")
    zkey = ZONE_KEY.get(zone_name)
    if not zkey:
        # fuzzy
        for key, name, _ in ZONES:
            if key in zone_name or name in zone_name or zone_name in name:
                zkey = key
                zone_name = name
                break
        zkey = zkey or "zhiguai"
        zone_name = next(n for k, n, _ in ZONES if k == zkey)
    meta["专区"] = zone_name
    meta["zkey"] = zkey
    meta["标题"] = meta.get("标题") or p.stem
    meta["日期"] = meta.get("日期") or p.stem[:10]
    meta["时段"] = SLOT.get(meta.get("时段", ""), meta.get("时段", "")) or "午间"
    meta["slug"] = p.stem
    body = "\n".join(lines).strip()
    return meta, body


SLOT_TIME = {"上午": (9, 54), "午间": (14, 54), "晚间": (20, 54)}
CST = datetime.timezone(datetime.timedelta(hours=8))


def build_now():
    """Asia/Shanghai now; override with XZ_NOW='YYYY-MM-DD HH:MM' or XZ_PREVIEW_ALL=1."""
    import os
    if os.environ.get("XZ_PREVIEW_ALL") == "1":
        return None
    ov = os.environ.get("XZ_NOW")
    if ov:
        return datetime.datetime.strptime(ov, "%Y-%m-%d %H:%M").replace(tzinfo=CST)
    return datetime.datetime.now(CST)


def xz_release_time(m):
    try:
        d = datetime.date.fromisoformat(m["日期"])
    except ValueError:
        return None
    h, mi = SLOT_TIME.get(m["时段"], (14, 54))
    return datetime.datetime(d.year, d.month, d.day, h, mi, tzinfo=CST)


def load_xz():
    now = build_now()
    items = [parse_xz(p) for p in sorted(XZ_SRC.glob("*.md"))]
    if now is not None:
        kept = []
        for m, b in items:
            rt = xz_release_time(m)
            if rt and rt > now:
                print(f"[xz] skip future {m['slug']} ({m['日期']} {m['时段']})", file=sys.stderr)
                continue
            kept.append((m, b))
        items = kept
    items.sort(key=lambda x: (x[0]["日期"], ORDER.get(x[0]["时段"], 9), x[0]["slug"]))
    return items


# 历史人物按「人」整合（专区页先人后日）
# 例程约定：历史连载仅午间 14:54 更新一天（见 HISTORY.md）
PERSON_BIOS = {
    "jiaxu": (
        "后人常称「三国第一谋士」／「毒士」；"
        "本传见《三国志·魏书》卷十。"
    ),
}
PERSON_INFO = {
    "jiaxu": {
        "epithet": "后人常称「三国第一谋士」／「毒士」（后人称呼，非本传原文）",
        "events": [
            "李郭之乱：劝李傕、郭汜收兵西攻长安（初平三年）",
            "宛城／淯水：先言追必败、再言追必胜（建安初）",
            "官渡：「四胜」劝曹操决机，破袁绍",
            "渭南：「离之而已」，伪许割地离间韩遂、马超",
            "立嗣：「思袁本初、刘景升父子」，太子遂定",
        ],
        "verdict": "荀攸、贾诩，庶乎算无遗策，经达权变，其良、平之亚与！",
        "verdict_src": "陈寿《三国志·魏书·荀彧荀攸贾诩传》卷十 评（原文作「筭」）",
    },
}
PERSON_SLUG_RE = re.compile(r"history-([a-z0-9]+)(?:-\d+)?$", re.I)
DAY_RE = re.compile(r"第\s*(\d+)\s*天")
TOTAL_RE = re.compile(r"预计\s*(\d+)\s*天")


def person_name_from_title(title):
    for sep in ("——", "—", "–"):
        if sep in title:
            return title.split(sep, 1)[0].strip()
    return (title or "").strip()


def person_slug_from_meta(m):
    mm = PERSON_SLUG_RE.search(m.get("slug", ""))
    if mm:
        return mm.group(1).lower()
    name = person_name_from_title(m.get("标题", ""))
    return re.sub(r"[^a-z0-9]+", "", name.lower()) or "person"


def parse_day_progress(title):
    d = DAY_RE.search(title or "")
    t = TOTAL_RE.search(title or "")
    return (int(d.group(1)) if d else None, int(t.group(1)) if t else None)


def _bio_from_body(body):
    """Prefer a 字／籍贯句；else first usable paragraph."""
    paras = []
    for l in body.split("\n"):
        s = strip_md(l)
        if not s or s.startswith("来源") or s.startswith("史料凡例"):
            continue
        if s.startswith("开篇") or re.match(r"^第?\d+", s):
            continue
        paras.append(s)
        if len(paras) >= 4:
            break
    for p in paras:
        if "字" in p and ("人" in p or "州" in p or "郡" in p):
            parts = re.split(r"(?<=[。！？])", p)
            out = "".join(parts[:2]).strip()
            return _clip(out or p, 120)
    if paras:
        return _clip(paras[0], 120)
    return ""


def chapter_summary(body, n=4):
    """Key events from ## headings (skip 开篇/收束/预告)."""
    out = []
    for l in body.split("\n"):
        mm = re.match(r"^##\s+(.*)", l)
        if not mm:
            continue
        h = strip_md(mm.group(1)).strip()
        if re.match(r"^[（(]", h) or h.startswith("开篇") or re.match(r"^\d+\.\d+", h) or "收束" in h:
            continue
        h = re.sub(r"^[一二三四五六七八九十]+、", "", h)
        h = h.replace("【专名大事】", "")
        out.append(_clip(h, 34))
    return out[:n]


def render_person_info(info, cls="person-info"):
    if not info:
        return ""
    ev = "".join(f"<li>{html.escape(e)}</li>" for e in info.get("events", []))
    return (
        f'<div class="{cls}">'
        f'<p class="person-epithet">{html.escape(info.get("epithet",""))}</p>'
        f'<div class="person-sec">经典大事</div><ul class="person-events">{ev}</ul>'
        f'<div class="person-sec">历史评价</div>'
        f'<p class="person-verdict">「{html.escape(info.get("verdict",""))}」'
        f'<span class="verdict-src">——{html.escape(info.get("verdict_src",""))}</span></p></div>'
    )


def group_history_persons(xz_items):
    """List of person dicts, earliest first-published first."""
    buckets = {}
    order = []
    for m, b in xz_items:
        if m["zkey"] != "history":
            continue
        slug = person_slug_from_meta(m)
        if slug not in buckets:
            buckets[slug] = {
                "slug": slug,
                "name": person_name_from_title(m["标题"]),
                "chapters": [],
                "total_days": None,
            }
            order.append(slug)
        day, total = parse_day_progress(m["标题"])
        buckets[slug]["chapters"].append(
            {"meta": m, "body": b, "day": day, "href": f'xiaozao/history-{m["slug"]}.html'}
        )
        if total:
            buckets[slug]["total_days"] = total
        nm = person_name_from_title(m["标题"])
        if nm and (not buckets[slug]["name"] or (day == 1)):
            buckets[slug]["name"] = nm
    persons = []
    for slug in order:
        p = buckets[slug]
        ch = p["chapters"]
        ch.sort(
            key=lambda c: (
                c["day"] if c["day"] is not None else 999,
                c["meta"]["日期"],
                ORDER.get(c["meta"]["时段"], 9),
            )
        )
        p["bio"] = PERSON_BIOS.get(slug) or _bio_from_body(ch[0]["body"])
        p["info"] = PERSON_INFO.get(slug, {})
        for c in ch:
            c["summary"] = chapter_summary(c["body"])
        p["published"] = len(ch)
        p["latest"] = max(c["meta"]["日期"] for c in ch)
        persons.append(p)
    # Order by first-published (earliest chapter date) ascending
    for p in persons:
        p["earliest"] = min(c["meta"]["日期"] for c in p["chapters"])
    persons.sort(key=lambda p: (p["earliest"], p["slug"]))
    return persons


def render_person_hub(person, root="../"):
    name = person["name"]
    bio = person["bio"]
    total = person["total_days"]
    pub = person["published"]
    prog = f"已刊 {pub} 天" + (f"／预计 {total} 天" if total else "")
    lis = []
    for c in person["chapters"]:
        m = c["meta"]
        day_label = f"第{c['day']}天" if c["day"] else m["时段"]
        href = f'history-{m["slug"]}.html'
        # Subtitle: part after ——, else clipped full title
        title = m["标题"] or ""
        sub = title
        for sep in ("——", "—", "–"):
            if sep in title:
                sub = title.split(sep, 1)[1].strip()
                break
        lis.append(
            f'<li class="person-chapter">'
            f'<a href="{href}">'
            f'<div class="ch-day">{html.escape(day_label)}</div>'
            f'<div class="meta">{dlabel(m["日期"])} · {m["时段"]}</div>'
            f'<div class="ch-title">{html.escape(sub)}</div>'
            + (
                '<ul class="ch-sum">'
                + "".join(f"<li>{html.escape(x)}</li>" for x in c.get("summary", []))
                + "</ul>"
            )
            + f'<span class="go-mini">阅读 →</span></a></li>'
        )
    tabs = "".join(
        f'<a class="ztab{" active" if k == "history" else ""}" href="{root}{ZONE_PAGE[k]}">{n}</a>'
        for k, n, _ in ZONES
    )
    inner = (
        f'<div class="archive-page zone-page person-hub">'
        f'<a class="back" href="{root}xiaozao-history.html">← 回历史人物</a>'
        f'<nav class="zone-tabs" aria-label="专区">{tabs}</nav>'
        f'<header class="person-head">'
        f'<div class="person-kicker">人物志</div>'
        f'<h1 class="person-name">{html.escape(name)}</h1>'
        + (render_person_info(person.get("info"), "person-info person-info-hub")
           or f'<p class="person-bio">{html.escape(bio)}</p>')
        + f'<p class="person-progress">{html.escape(prog)}</p>'
        f"</header>"
        f'<div class="archive-block"><h2>连载章节</h2>'
        f'<ul class="person-chapters">{"".join(lis)}</ul></div></div>'
    )
    return page(f"人物 · {name}", inner, root, active="xiaozao")




def _xz_hook_line(body, n=52):
    for l in body.split("\n"):
        s = strip_md(l)
        if s and not s.startswith("来源") and not s.startswith("##"):
            return _clip(s, n)
    return ""


def _today_status(issues):
    latest_m = issues[-1][0]
    today = latest_m["日期"]
    today_map = {m["slot"]: (m, b) for m, b in issues if m["日期"] == today}
    feat = None
    for slot in ("晚间", "午间", "上午"):
        if slot in today_map and split_sections(today_map[slot][1])[1]:
            feat = slot
            break
    if feat is None:
        feat = latest_m["slot"]
    cards = "".join(
        slot_card(s, *(today_map.get(s) or (None, "")), featured=(s == feat))
        for s in ("上午", "午间", "晚间")
    )
    published = len(today_map)
    pend = [s for s in ("上午", "午间", "晚间") if s not in today_map]
    status = f"今日{'三' if published == 3 else '两' if published == 2 else '一'}场已刊"
    if pend:
        status += " · " + "／".join(pend) + "待刊"
    t = datetime.date.fromisoformat(today)
    vol_date = f"{t.year} · {t.month} · {t.day}"
    return today, today_map, cards, status, t, vol_date


def _latest_by_zone(xz_items):
    """zkey -> latest (meta, body)."""
    out = {}
    for m, b in reversed(xz_items):
        out.setdefault(m["zkey"], (m, b))
    return out


def home_html(issues, days, xz_items):
    today, today_map, cards, status, t, vol_date = _today_status(issues)
    latest = _latest_by_zone(xz_items)
    zone_rows = []
    for key, name, desc in ZONES:
        if key in latest:
            m, b = latest[key]
            hook = _xz_hook_line(b) or m["标题"]
            href = ZONE_PAGE[key]
            if key == "history":
                href = f'xiaozao/person-{person_slug_from_meta(m)}.html'
            zone_rows.append(
                f'<a class="xz-hook xz-{key}" href="{href}">'
                f'<span class="xz-k">{name[:2]}</span>'
                f'<span class="xz-t">{html.escape(m["标题"])}</span>'
                f'<span class="xz-h">{html.escape(_clip(hook, 56))}</span></a>'
            )
        else:
            zone_rows.append(
                f'<div class="xz-hook xz-{key} pending">'
                f'<span class="xz-k">{name[:2]}</span>'
                f'<span class="xz-t">{name}</span>'
                f'<span class="xz-h">待刊</span></div>'
            )

    return f"""<div class="home">
<header class="rack-mast"><div>
<div class="vol">VOL. 01 · {today}</div><h1 class="rack-title rack-title-en">Justknow</h1></div>
<div class="rack-sub"><strong>{vol_date}</strong>周{WD[t.weekday()]} · 知识分享<br>{status}</div></header>

<section class="home-col" id="rizhi" aria-labelledby="rizhi-h">
<header class="col-mast col-rizhi">
<div class="col-kicker">栏目一</div>
<h2 id="rizhi-h" class="col-title">日知</h2>
<p class="col-desc">每日三次知识分享 · 头条与领域速览</p>
</header>
<section class="rack-section" aria-labelledby="rz-today-h"><div class="rack-section-head">
<h3 id="rz-today-h">今日刊节选</h3><span class="hint">{dlabel(today)}</span></div>
<div class="today-grid">{cards}</div></section>
<div class="archive-strip"><div class="copy"><strong>日知主页</strong><span class="col-tagline">求日知于微，求日新于恒。</span></div>
<a class="go" href="rizhi.html">进入日知 →</a></div>
</section>

<section class="home-col home-col-xz" id="xiaozao" aria-labelledby="xiaozao-h">
<header class="col-mast col-xiaozao">
<div class="col-kicker">栏目二</div>
<h2 id="xiaozao-h" class="col-title">小灶</h2>
<p class="col-desc">灵异志怪 · 传统民俗 · 神话传说 · 历史人物</p>
</header>
<section class="rack-section" aria-labelledby="xz-today-h"><div class="rack-section-head">
<h3 id="xz-today-h">四专区最新</h3><span class="hint">{dlabel(today)}</span></div>
<div class="xz-today-grid">{"".join(zone_rows)}</div></section>
<div class="archive-strip archive-strip-xz"><div class="copy"><strong>小灶主页</strong><span class="col-tagline">兴致未尽，此处继续。</span></div>
<a class="go" href="xiaozao.html">进入小灶 →</a></div>
</section>
</div>"""


def _paper_item_sum(body_lines, n=78):
    """First non-source body line, clipped — for newspaper digest."""
    return _clip(_first_body_line(body_lines), n)


def paper_slot_col(slot, m, body):
    """One newspaper partition: published = digest; missing = 待刊."""
    slot_time = {"上午": "9:54", "午间": "14:54", "晚间": "20:54"}.get(slot, "")
    if m is None:
        return (
            f'<section class="paper-col pending" aria-label="{slot}·待刊">'
            f'<header class="paper-col-head">'
            f'<span class="paper-slot">{slot}</span>'
            f'<span class="paper-when">待刊</span></header>'
            f'<div class="paper-empty">'
            f'<p class="paper-empty-mark">待刊</p>'
            f'<p class="paper-empty-hint">{slot}场尚未付印<br>刊出后本栏自动成文</p>'
            f'</div></section>'
        )
    _, headlines, pieces, _, _ = split_sections(body)
    href = f'issues/{m["slug"]}.html'
    when = html.escape(m.get("计划时间") or slot_time)
    # lead block: up to 2 headlines with short digests
    leads = []
    for h in headlines[:2]:
        _kind, dom, title, blines = h
        leads.append(
            f'<article class="paper-lead">'
            f'<div class="paper-kicker"><span class="pk-tag">头条</span>'
            f'<span class="pk-dom">{html.escape(dom)}</span></div>'
            f'<h3 class="paper-lead-title">{html.escape(title)}</h3>'
            f'<p class="paper-sum">{html.escape(_paper_item_sum(blines, 90))}</p>'
            f"</article>"
        )
    # remaining pieces as compact digest rows (skip if already in headlines)
    digests = []
    for p in pieces[:8]:
        _kind, dom, title, blines = p
        digests.append(
            f'<li class="paper-item">'
            f'<span class="pi-dom">{html.escape(dom)}</span>'
            f'<span class="pi-title">{html.escape(_clip(title, 36))}</span>'
            f'<span class="pi-sum">{html.escape(_paper_item_sum(blines, 56))}</span>'
            f"</li>"
        )
    # if no headlines but pieces exist, promote first as lead
    if not leads and pieces:
        _kind, dom, title, blines = pieces[0]
        leads.append(
            f'<article class="paper-lead">'
            f'<div class="paper-kicker"><span class="pk-dom">{html.escape(dom)}</span></div>'
            f'<h3 class="paper-lead-title">{html.escape(title)}</h3>'
            f'<p class="paper-sum">{html.escape(_paper_item_sum(blines, 90))}</p>'
            f"</article>"
        )
        digests = digests[1:]  # first already promoted
    leads_html = "".join(leads) or '<p class="paper-sum mute">本期暂无摘要</p>'
    list_html = (
        f'<ul class="paper-digest">{"".join(digests)}</ul>' if digests else ""
    )
    n_items = len(headlines) + len(pieces)
    return (
        f'<section class="paper-col" aria-label="{slot}·已刊">'
        f'<header class="paper-col-head">'
        f'<span class="paper-slot">{slot}</span>'
        f'<span class="paper-when">{when}</span></header>'
        f'{leads_html}{list_html}'
        f'<a class="paper-more" href="{href}">读全文 · 共 {n_items} 则 →</a>'
        f"</section>"
    )


def _day_status_label(day, day_map, *, is_today=False):
    published = len(day_map)
    pend = [s for s in ("上午", "午间", "晚间") if s not in day_map]
    nword = "三" if published == 3 else "两" if published == 2 else "一" if published == 1 else "零"
    head = "今日" if is_today else "本日"
    status = f"{head}{nword}场已刊" if published else f"{head}尚未付印"
    if pend and published:
        status += " · " + "／".join(pend) + ("待刊" if is_today else "未刊")
    elif pend and not published:
        status += " · " + "／".join(pend) + ("待刊" if is_today else "未刊")
    return status, published


def rizhi_day_paper_html(day, day_map, *, is_today=False):
    """单日报纸总页：三栏分区；已刊写概括，缺场标待刊／未刊。"""
    t = datetime.date.fromisoformat(day)
    vol_date = f"{t.year} · {t.month} · {t.day}"
    status, published = _day_status_label(day, day_map, is_today=is_today)
    cols = "".join(
        paper_slot_col(s, *(day_map.get(s) or (None, "")))
        for s in ("上午", "午间", "晚间")
    )
    paper_name = "今日刊" if is_today else f"{t.month}月{t.day}日刊"
    back_href = "rizhi.html" if is_today else "archive.html"
    back_label = "← 回日知主页" if is_today else "← 回日知往期"
    folio = f"第 {published}/3 场已刊"
    return f"""<div class="home page-wide paper-page">
<a class="back" href="{back_href}">{back_label}</a>
<div class="paper-sheet">
<header class="paper-mast">
<div class="paper-mast-top">
<span class="paper-brand">Justknow · 日知</span>
<span class="paper-folio">{folio}</span>
</div>
<h1 class="paper-name">{paper_name}</h1>
<div class="paper-dateline">
<strong>{vol_date}</strong>
<span>{dlabel(day)}</span>
<span class="paper-status">{status}</span>
</div>
<div class="paper-rule" aria-hidden="true"></div>
</header>
<div class="paper-cols" role="group" aria-label="本日三场">{cols}</div>
<p class="paper-foot">上午 9:54 · 午间 14:54 · 晚间 20:54　·　摘要节选自本期头条与领域条目，点「读全文」看完整期。</p>
</div>
</div>"""


def rizhi_today_html(issues):
    """今日刊主页（今日日期的报纸总页）。"""
    today, today_map, _cards, status, t, vol_date = _today_status(issues)
    return rizhi_day_paper_html(today, today_map, is_today=True)


def day_hub_path(day, today=None):
    """Consistent day-overview URL. Today keeps branded today.html; past days use day-YYYY-MM-DD.html."""
    if today is not None and day == today:
        return "today.html"
    return f"day-{day}.html"



def rizhi_rack_html(issues, days):
    today, today_map, cards, status, t, vol_date = _today_status(issues)
    recent = []
    for d in sorted((d for d in days if d < today), reverse=True)[:4]:
        items = sorted(days[d], key=lambda x: (ORDER.get(x[0]["slot"], 9), x[0]["slug"]))
        li = "".join(
            f'<li><a href="issues/{m["slug"]}.html"><span class="s">{m["slot"]}</span>'
            f'<span class="t">{html.escape(_clip(_short_title(first_piece_teaser(body)), 40))}</span></a></li>'
            for m, body in items
        )
        td = datetime.date.fromisoformat(d)
        hub = day_hub_path(d, today)
        recent.append(
            f'<article class="day-card"><h3 class="day-date">'
            f'<a class="day-date-link" href="{hub}">{td.month}月{td.day}日'
            f'<span class="dow">周{WD[td.weekday()]}</span></a></h3>'
            f'<ul>{li}</ul>'
            f'<a class="day-go" href="{hub}">打开当日刊 →</a></article>'
        )
    return f"""<div class="home page-wide"><header class="rack-mast"><div>
<div class="vol">VOL. 01 · {today}</div><h1 class="rack-title">日知</h1></div>
<div class="rack-sub"><strong>{vol_date}</strong>周{WD[t.weekday()]} · 日知主页<br>{status}</div></header>
<section class="rack-section" aria-labelledby="today-h"><div class="rack-section-head">
<h2 id="today-h">今日刊</h2><span class="hint">{dlabel(today)} · <a href="today.html">今日刊主页 →</a></span></div>
<div class="today-grid">{cards}</div></section>
<section class="rack-section" aria-labelledby="recent-h"><div class="rack-section-head">
<h2 id="recent-h">近日四则</h2><a class="hint" href="archive.html">日知往期 →</a></div>
<div class="recent-grid">{"".join(recent)}</div></section>
<div class="archive-strip"><div class="copy"><strong>日知往期</strong>共 {len(issues)} 期 · 按日编排</div>
<a class="go" href="archive.html">打开往期 →</a></div></div>"""


def archive_html(issues, days):
    """日知往期：一行四张日卡（近日四则样式），点进当日报纸总页。"""
    today = issues[-1][0]["日期"] if issues else None
    cards = []
    for d in sorted(days):  # 正序：从上到下、从左到右
        items = sorted(days[d], key=lambda x: (ORDER.get(x[0]["slot"], 9), x[0]["slug"]))
        by_slot = {m["slot"]: (m, body) for m, body in items}
        rows = []
        for slot in ("上午", "午间", "晚间"):
            if slot not in by_slot:
                continue
            m, body = by_slot[slot]
            title = _clip(_short_title(first_piece_teaser(body)), 40)
            rows.append(
                f'<li><span class="s">{slot}</span>'
                f'<span class="t">{html.escape(title)}</span></li>'
            )
        td = datetime.date.fromisoformat(d)
        hub = day_hub_path(d, today)
        n = len(items)
        cards.append(
            f'<a class="day-card day-card-hub" href="{hub}" id="d{d}">'
            f'<h3 class="day-date">{td.month}月{td.day}日'
            f'<span class="dow">周{WD[td.weekday()]}</span></h3>'
            f'<ul>{"".join(rows)}</ul>'
            f'<span class="day-go">打开当日刊 · {n} 场 →</span></a>'
        )
    n_days = len(days)
    return (
        '<div class="archive-page page-wide"><a class="back" href="rizhi.html">← 回日知主页</a>'
        f'<div class="archive-block"><h2>日知往期</h2>'
        f'<p class="count">共 {n_days} 日 · {len(issues)} 期 · 按日正序</p>'
        f'<div class="recent-grid archive-day-grid">{"".join(cards)}</div></div></div>'
    )


ZONE_SHORT = {
    "zhiguai": "志怪",
    "minsu": "民俗",
    "shenhua": "神话",
    "history": "历史",
}


def _xz_recent_past_days(xz_items, n=4):
    """Up to n past calendar days before today (Asia/Shanghai), newest first.

    Prefer days that have any 小灶 entries; if fewer than n, pad with empty
    calendar days walking back from yesterday (shown as 待刊).
    """
    today = datetime.datetime.now(CST).date()
    by = {}
    for m, b in xz_items:
        d = m["日期"]
        try:
            dd = datetime.date.fromisoformat(d)
        except ValueError:
            continue
        if dd < today:
            by.setdefault(d, []).append((m, b))
    content_days = sorted(by.keys(), reverse=True)[:n]
    days = list(content_days)
    if len(days) < n:
        have = set(days)
        cursor = today - datetime.timedelta(days=1)
        # walk back far enough to fill n slots
        for _ in range(366):
            if len(days) >= n:
                break
            ds = cursor.isoformat()
            if ds not in have:
                days.append(ds)
                have.add(ds)
            cursor -= datetime.timedelta(days=1)
        days = sorted(days, reverse=True)
    return [(d, by.get(d, [])) for d in days]


def _xz_day_hook(m, b, n=42):
    """Short 概括 for a day-card zone line: prefer body hook, skip 凡例."""
    if m.get("zkey") == "history":
        return _clip(m.get("标题") or "", n)
    hook = _xz_hook_line(b, n)
    if hook and (hook.startswith("史料") or hook.startswith("凡例") or hook.startswith("开篇")):
        hook = ""
    return hook or _clip(m.get("标题") or "", n)


def _xz_day_summary_lines(items):
    """One hook line per zone present that day (latest entry in zone)."""
    by_zone = {}
    for m, b in sorted(items, key=lambda x: (ORDER.get(x[0]["时段"], 9), x[0]["slug"])):
        by_zone[m["zkey"]] = (m, b)
    lines = []
    for key, name, _ in ZONES:
        if key not in by_zone:
            continue
        m, b = by_zone[key]
        hook = _xz_day_hook(m, b, 42)
        short = ZONE_SHORT.get(key, name[:2])
        n = sum(1 for mm, _ in items if mm["zkey"] == key)
        count = f"·{n}" if n > 1 else ""
        lines.append(
            f'<li class="xz-dz xz-{key}">'
            f'<span class="zn">{short}{count}</span>'
            f'<span class="zh">{html.escape(hook)}</span></li>'
        )
    return lines


def xiaozao_home_html(xz_items):
    latest = _latest_by_zone(xz_items)
    cards = []
    for key, name, desc in ZONES:
        if key in latest:
            m, b = latest[key]
            hook = _xz_hook_line(b, 64) or m["标题"]
            cards.append(
                f'<a class="zone-card zone-{key}" href="{ZONE_PAGE[key]}">'
                f'<div class="zone-kicker">专区</div>'
                f'<h3 class="zone-title">{name}</h3>'
                f'<p class="zone-desc">{desc}</p>'
                f'<div class="zone-latest"><span class="zl-label">最新</span>'
                f'<span class="zl-title">{html.escape(m["标题"])}</span>'
                f'<span class="zl-hook">{html.escape(hook)}</span></div>'
                f'<span class="zone-go">进入专区 →</span></a>'
            )
        else:
            cards.append(
                f'<div class="zone-card zone-{key} pending">'
                f'<div class="zone-kicker">专区</div>'
                f'<h3 class="zone-title">{name}</h3>'
                f'<p class="zone-desc">{desc}</p>'
                f'<div class="zone-latest"><span class="zl-label">最新</span><span class="zl-hook">待刊</span></div>'
                f'<span class="zone-go">待刊</span></div>'
            )
    recent_cards = []
    for d, items in _xz_recent_past_days(xz_items, 4):
        td = datetime.date.fromisoformat(d)
        meta = (
            f'{td.month}月{td.day}日'
            f'<span class="dow">周{WD[td.weekday()]}</span>'
        )
        if items:
            lines = _xz_day_summary_lines(items)
            body = f'<ul class="xz-day-zones">{"".join(lines)}</ul>'
            recent_cards.append(
                f'<a class="xz-day-card" href="xiaozao-day-{d}.html">'
                f'<div class="xz-day-meta">{meta}</div>'
                f'{body}'
                f'<span class="xz-day-go">打开当日 →</span></a>'
            )
        else:
            recent_cards.append(
                f'<div class="xz-day-card pending">'
                f'<div class="xz-day-meta">{meta}</div>'
                f'<div class="xz-day-hook pending-mark">待刊</div>'
                f'<span class="xz-day-go">尚无更新</span></div>'
            )
    recent_html = "".join(recent_cards)
    # 共 N 则 = len(xz_items)：已刊全量（四专区含历史日章；未来档已由 load_xz 剔除）
    today_d = datetime.datetime.now(CST).date()
    today = today_d.isoformat()
    vol_date = f"{today_d.year} · {today_d.month} · {today_d.day}"
    return f"""<div class="home home-xz-page page-wide"><header class="rack-mast"><div>
<div class="vol">VOL. 01 · {today}</div><h1 class="rack-title">小灶</h1></div>
<div class="rack-sub"><strong>{vol_date}</strong>周{WD[today_d.weekday()]} · 小灶主页<br>专区独立连载</div></header>
<section class="rack-section" aria-labelledby="zones-h"><div class="rack-section-head">
<h2 id="zones-h">专区</h2><a class="hint" href="xiaozao-dates.html">按日浏览 →</a></div>
<div class="zone-grid">{"".join(cards)}</div></section>
<section class="rack-section" aria-labelledby="xz-recent-h"><div class="rack-section-head">
<h2 id="xz-recent-h">近日更新</h2><span class="hint">今日以前 · 四日</span></div>
<div class="xz-recent-grid">{recent_html}</div></section>
<div class="archive-strip archive-strip-xz"><div class="copy"><strong>小灶完整页</strong>共 {len(xz_items)} 则 · 点专区或日期进单独页</div>
<a class="go" href="xiaozao-dates.html">了解更多 →</a></div></div>"""


def xiaozao_zone_html(zkey, xz_items):
    name = next(n for k, n, _ in ZONES if k == zkey)
    desc = next(d for k, _, d in ZONES if k == zkey)
    items = [(m, b) for m, b in xz_items if m["zkey"] == zkey]
    # ascending chronological (xz_items already date/slot ascending)
    zone_bar = _xz_step2_zone_bar(zkey)
    hint = '<p class="xz-filter-hint">第二步：全部回完整页，或切换四个专区。</p>'
    if zkey == "history":
        persons = group_history_persons(xz_items)
        cards = []
        for p in persons:
            total = p["total_days"]
            prog = f"已刊 {p['published']}" + (f"／预计 {total} 天" if total else " 天")
            cards.append(
                f'<li class="person-card">'
                f'<a href="xiaozao/person-{p["slug"]}.html">'
                f'<div class="person-kicker">人物志</div>'
                f'<h3 class="person-name">{html.escape(p["name"])}</h3>'
                + (render_person_info(p.get("info")) or f'<p class="person-bio">{html.escape(p["bio"])}</p>')
                + f'<div class="person-progress">{html.escape(prog)}</div>'
                f'<span class="go-mini">进入人物志 →</span></a></li>'
            )
        return (
            f'<div class="archive-page zone-page"><a class="back" href="xiaozao.html">← 回小灶主页</a>'
            f'<div class="archive-block"><h2>{name}</h2>'
            f'{zone_bar}{hint}'
            f'<p class="count">{desc} · 共 {len(persons)} 人 · 先按人浏览再进日章</p>'
            f'<ul class="person-grid">{"".join(cards)}</ul></div></div>'
        )
    lis = []
    for m, b in items:
        hook = _xz_hook_line(b, 72)
        href = f'xiaozao/entry-{m["slug"]}.html'
        lis.append(
            f'<li class="xz-entry xz-entry-row">'
            f'<a href="{href}">'
            f'<div class="meta">{dlabel(m["日期"])} · {m["时段"]}</div>'
            f'<div class="zg-title">{html.escape(m["标题"])}</div>'
            f'<div class="teaser">{html.escape(hook)}</div>'
            f'<span class="go-mini">阅读 →</span></a></li>'
        )
    base = f"{name} · 共 {len(items)} 则"
    return (
        f'<div class="archive-page zone-page">'
        f'<a class="back" href="xiaozao.html">← 回小灶主页</a>'
        f'<div class="archive-block"><h2>{name}</h2><p class="zone-desc-line">{desc}</p>'
        f'{zone_bar}{hint}'
        f'<p class="count">{base}</p>'
        f'<ul class="zg-list">{"".join(lis)}</ul></div></div>'
    )


def _zone_name(k):
    return next(n for kk, n, _ in ZONES if kk == k)


def _xz_href(m, prefix=""):
    if m["zkey"] == "history":
        return f'{prefix}xiaozao/history-{m["slug"]}.html'
    return f'{prefix}xiaozao/entry-{m["slug"]}.html'


def _xz_link_tabs(items):
    """items: list of (href, label, is_active)."""
    return "".join(
        f'<a class="ztab{" active" if act else ""}" href="{href}">{lab}</a>'
        for href, lab, act in items
    )


def _xz_filter_bar(zone_links=None, date_links=None, aria="筛选", unlabeled=False):
    """zone_links / date_links: list of (href, label, active).
    unlabeled=True：不显示「专区／日期」行标签（一级三钮用）。"""
    rows = []
    if zone_links:
        label = "" if unlabeled else '<span class="xz-filter-label">专区</span>'
        rows.append(
            f'<div class="xz-filter-row">{label}'
            f'<div class="zone-tabs xz-filter-tabs" role="navigation" aria-label="专区">'
            f'{_xz_link_tabs(zone_links)}</div></div>'
        )
    if date_links:
        label = "" if unlabeled else '<span class="xz-filter-label">日期</span>'
        rows.append(
            f'<div class="xz-filter-row">{label}'
            f'<div class="zone-tabs xz-filter-tabs" role="navigation" aria-label="日期">'
            f'{_xz_link_tabs(date_links)}</div></div>'
        )
    return f'<div class="xz-filters" aria-label="{aria}">{"".join(rows)}</div>'


def _date_nav_links(dates, active="all", all_href="xiaozao-dates.html"):
    out = [(all_href, "全部", active == "all")]
    for d in dates:
        td = datetime.date.fromisoformat(d)
        out.append((f"xiaozao-day-{d}.html", f"{td.month}月{td.day}日", active == d))
    return out


def _zone_nav_links(active="all", all_href="xiaozao-dates.html"):
    out = [(all_href, "全部", active == "all")]
    for k, n, _ in ZONES:
        out.append((ZONE_PAGE[k], n, active == k))
    return out


def _xz_step1_bar(active="all", latest_date=None):
    """完整页一级筛栏：全部｜专区｜日期。"""
    zone_href = ZONE_PAGE[ZONES[0][0]]  # 默认进第一个专区页
    date_href = (
        f"xiaozao-day-{latest_date}.html" if latest_date else "xiaozao-dates.html"
    )
    items = [
        ("xiaozao-dates.html", "全部", active == "all"),
        (zone_href, "专区", active == "zone"),
        (date_href, "日期", active == "date"),
    ]
    return _xz_filter_bar(zone_links=items, unlabeled=True, aria="筛选")


def _xz_step2_zone_bar(active="all"):
    """专区路径第二步：全部（回完整页）＋四专区。"""
    return _xz_filter_bar(_zone_nav_links(active), None, aria="专区筛选")


def _xz_step2_date_bar(dates, active="all"):
    """日期路径第二步：全部（回完整页）＋各日期。"""
    return _xz_filter_bar(None, _date_nav_links(dates, active=active), aria="日期筛选")


def _xz_day_rows(by, dates):
    rows = []
    for d in dates:
        items = sorted(by[d], key=lambda x: (ORDER.get(x[0]["时段"], 9), x[0]["slug"]))
        lis = []
        for m, b in items:
            name = _zone_name(m["zkey"])
            hook = _xz_hook_line(b, 48)
            lis.append(
                f'<li class="xz-entry-row">'
                f'<a href="{_xz_href(m)}">'
                f'<span class="slot xz-slot xz-{m["zkey"]}">{name[:2]}</span>'
                f'<span class="entry"><span class="meta">{m["时段"]} · {html.escape(m["标题"])}</span>'
                f'<span class="teaser">{html.escape(hook)}</span></span></a></li>'
            )
        rows.append(
            f'<section class="day xz-day" id="xz{d}" data-date="{d}">'
            f'<h2 class="date"><a href="xiaozao-day-{d}.html">{dlabel(d)}</a></h2>'
            f'<ul class="list">{"".join(lis)}</ul></section>'
        )
    return rows


def _xz_book_hrefs(xz_items):
    """全部小灶条目 href 列表（新→旧），供随手翻开随机跳转。"""
    by = {}
    for m, b in xz_items:
        by.setdefault(m["日期"], []).append((m, b))
    hrefs = []
    for d in sorted(by, reverse=True):
        day_items = sorted(
            by[d], key=lambda x: (ORDER.get(x[0]["时段"], 9), x[0]["slug"])
        )
        hrefs.extend(_xz_href(m) for m, _ in day_items)
    return hrefs


def _xz_ancient_book(xz_items):
    """完整页「全部」：线装古书摊开；点书页／随手翻开 → 随机进一条条目。"""
    import json

    hrefs = _xz_book_hrefs(xz_items)
    if not hrefs:
        return '<p class="xz-filter-empty">暂无条目</p>'
    hrefs_json = html.escape(json.dumps(hrefs, ensure_ascii=False), quote=True)
    n = len(hrefs)
    by = {}
    for m, b in xz_items:
        by.setdefault(m["日期"], []).append((m, b))
    metas = []
    for d in sorted(by, reverse=True):
        day_items = sorted(
            by[d], key=lambda x: (ORDER.get(x[0]["时段"], 9), x[0]["slug"])
        )
        metas.extend(day_items)
    left_bits, right_bits = [], []
    for i, (m, _) in enumerate(metas[:8]):
        short = ZONE_SHORT.get(m["zkey"], _zone_name(m["zkey"])[:2])
        raw = re.sub(r"[——（）()《》·、，,。：:]", "", m["标题"])
        title = _clip(raw, 8)
        bit = (
            f'<span class="xz-book-col xz-{m["zkey"]}" aria-hidden="true">'
            f'<em class="xz-book-col-z">{html.escape(short)}</em>'
            f'<b class="xz-book-col-t">{html.escape(title)}</b>'
            f"</span>"
        )
        (left_bits if i < 4 else right_bits).append(bit)
    left_html = "".join(left_bits)
    right_html = "".join(right_bits)
    # script: 翻页动画约 0.5s，再随机跳转
    script = (
        "<script>(function(){"
        'var root=document.getElementById("xz-book");'
        "if(!root)return;"
        "var hrefs=[],busy=0;"
        'try{hrefs=JSON.parse(root.getAttribute("data-hrefs")||"[]");}catch(e){hrefs=[];}'
        "function go(){if(!hrefs.length)return;"
        "var i=Math.floor(Math.random()*hrefs.length);location.href=hrefs[i];}"
        "function flip(){if(busy||!hrefs.length)return;busy=1;"
        'root.classList.add("is-flipping");'
        "var ms=500;"
        'try{if(window.matchMedia&&matchMedia("(prefers-reduced-motion: reduce)").matches)ms=40;}'
        "catch(e){}"
        "setTimeout(go,ms);}"
        'root.addEventListener("click",flip);'
        'root.addEventListener("keydown",function(e){'
        'if(e.key==="Enter"||e.key===" "){e.preventDefault();flip();}});'
        'var btn=document.getElementById("xz-book-open");'
        'if(btn)btn.addEventListener("click",function(e){e.stopPropagation();flip();});'
        "})();</script>"
    )
    return (
        f'<div class="xz-book" id="xz-book" data-hrefs="{hrefs_json}" '
        f'role="button" tabindex="0" aria-label="随手翻开一卷小灶，随机阅读一则">'
        f'<div class="xz-book-board">'
        f'<div class="xz-book-binding" aria-hidden="true">'
        f"<span></span><span></span><span></span><span></span></div>"
        f'<div class="xz-book-spread">'
        f'<div class="xz-book-page xz-book-left">'
        f'<div class="xz-book-page-inner">'
        f'<span class="xz-book-seal" aria-hidden="true">小灶</span>'
        f'<div class="xz-book-cols">{left_html}</div>'
        f"</div></div>"
        f'<div class="xz-book-gutter" aria-hidden="true"></div>'
        f'<div class="xz-book-page xz-book-right">'
        f'<div class="xz-book-page-inner">'
        f'<div class="xz-book-cols">{right_html}</div>'
        f'<p class="xz-book-verso" aria-hidden="true">凡{n}则 · 随手一翻</p>'
        f"</div></div>"
        f"</div>"
        f'<span class="xz-book-ribbon" aria-hidden="true"></span>'
        f"</div>"
        f'<button type="button" class="xz-book-open" id="xz-book-open">随手翻开</button>'
        f'<p class="xz-book-tip">点书页或按钮，随机跳进一则小灶正文</p>'
        f"</div>"
        f"{script}"
    )


def _xz_day_piece_card(m, b):
    """日期页日刊架条目卡：专区色脊 + 刊讯感；点进详情。"""
    zkey = m["zkey"]
    short = ZONE_SHORT.get(zkey, _zone_name(zkey)[:2])
    name = _zone_name(zkey)
    hook = _xz_hook_line(b, 72)
    slot = m["时段"]
    return (
        f'<a class="xz-issue-card xz-piece xz-{zkey}" href="{_xz_href(m)}">'
        f'<aside class="xz-issue-spine xz-spine-{zkey}" aria-hidden="true">'
        f'<span class="xz-issue-mon">{html.escape(slot)}</span>'
        f'<span class="xz-issue-num xz-piece-zn">{html.escape(short)}</span>'
        f'<span class="xz-issue-wd">{html.escape(name)}</span>'
        f'</aside>'
        f'<div class="xz-issue-main">'
        f'<div class="xz-issue-mast">'
        f'<span class="xz-issue-kicker">刊讯 · {html.escape(short)}</span>'
        f'<span class="xz-issue-count">{html.escape(slot)}</span>'
        f'</div>'
        f'<div class="xz-issue-strips">'
        f'<span class="xz-issue-strip xz-{zkey}" style="flex:1"></span>'
        f'</div>'
        f'<p class="xz-issue-lead">'
        f'<span class="xz-issue-lead-t">{html.escape(m["标题"])}</span></p>'
        f'<p class="xz-piece-teaser">{html.escape(hook)}</p>'
        f'<span class="xz-issue-open">阅读 →</span>'
        f'</div></a>'
    )


def _xz_day_piece_rack(items):
    """日期第二步主体：该日条目的日刊架卡片墙。"""
    sorted_items = sorted(
        items, key=lambda x: (ORDER.get(x[0]["时段"], 9), x[0]["slug"])
    )
    cards = [_xz_day_piece_card(m, b) for m, b in sorted_items]
    return f'<div class="xz-issue-rack xz-day-pieces">{"".join(cards)}</div>'


def xiaozao_dates_html(xz_items, filter_key=None):
    """小灶完整页：一级仅「全部｜专区｜日期」；filter_key 页用专区第二步。"""
    items = xz_items
    if filter_key:
        items = [(m, b) for m, b in xz_items if m["zkey"] == filter_key]
    by = {}
    for m, b in items:
        by.setdefault(m["日期"], []).append((m, b))
    dates = sorted(by)
    all_dates = sorted({m["日期"] for m, _ in xz_items})
    total = sum(len(v) for v in by.values())
    latest = all_dates[-1] if all_dates else None
    if filter_key:
        bar = _xz_step2_zone_bar(filter_key)
        hint = '<p class="xz-filter-hint">第二步：全部回完整页，或切换四个专区。</p>'
        base = f"{_zone_name(filter_key)} · 共 {total} 则 · 按日编排"
        rows = _xz_day_rows(by, dates)
        title = f"小灶完整页 · {_zone_name(filter_key)}"
        return (
            f'<div class="archive-page">'
            f'<a class="back" href="xiaozao.html">← 回小灶主页</a>'
            f'<div class="archive-block"><h2>{title}</h2>{bar}{hint}'
            f'<p class="count">{base}</p>'
            f'{"".join(rows)}</div></div>'
        )
    # 「全部」＝线装古书；点书页／随手翻开 → 随机进一条条目
    bar = _xz_step1_bar(active="all", latest_date=latest)
    hint = (
        '<p class="xz-filter-hint">'
        "点专区／日期进入第二步；下面是一卷小灶——随手翻开，随机读一则。"
        "</p>"
    )
    book = _xz_ancient_book(items)
    return (
        f'<div class="archive-page page-wide xz-overview">'
        f'<a class="back" href="xiaozao.html">← 回小灶主页</a>'
        f'<div class="archive-block">'
        f'<h2 class="xz-ov-title">小灶完整页</h2>'
        f'<p class="xz-ov-sub">共 {total} 则 · 线装一卷 · 随手翻开</p>'
        f'{bar}{hint}{book}</div></div>'
    )


def xiaozao_day_html(d, xz_items):
    """小灶日期页：第二步＝全部＋各日期；主体＝该日日刊架条目卡。"""
    items = [(m, b) for m, b in xz_items if m["日期"] == d]
    td = datetime.date.fromisoformat(d)
    all_dates = sorted({m["日期"] for m, _ in xz_items})
    i = all_dates.index(d)
    nav = []
    if i > 0:
        p = all_dates[i - 1]
        nav.append(f'<a href="xiaozao-day-{p}.html">← {dlabel(p)}</a>')
    if i < len(all_dates) - 1:
        n = all_dates[i + 1]
        nav.append(f'<a href="xiaozao-day-{n}.html">{dlabel(n)} →</a>')
    base = f"{td.month}月{td.day}日 · 共 {len(items)} 则 · 日刊架"
    rack = _xz_day_piece_rack(items) if items else (
        '<p class="xz-filter-empty">当日暂无条目</p>'
    )
    bar = _xz_step2_date_bar(all_dates, active=d)
    return (
        f'<div class="archive-page page-wide xz-day-page">'
        f'<a class="back" href="xiaozao.html">← 回小灶主页</a>'
        f'<div class="archive-block"><h2>小灶 · {td.month}月{td.day}日 周{WD[td.weekday()]}</h2>'
        f'{bar}'
        f'<p class="xz-filter-hint">第二步：全部回完整页，或切换日期；'
        f'<a href="xiaozao-dates.html">回完整页看全部 →</a></p>'
        f'<p class="count">{base}</p>'
        f'{rack}'
        f'<nav class="xz-day-nav">{"".join(nav)}</nav></div></div>'
    )


def render_xz_entry_page(m, body, root="../"):
    name = next(n for k, n, _ in ZONES if k == m["zkey"])
    # body: ## headings + paras
    html_parts = []
    for block in re.split(r"\n(?=## )", body):
        block = block.strip()
        if not block:
            continue
        if block.startswith("## "):
            first, *rest = block.split("\n", 1)
            html_parts.append(f"<h2>{html.escape(first[3:].strip())}</h2>")
            if rest:
                html_parts.append(body_to_paras(rest[0].split("\n")))
        else:
            html_parts.append(body_to_paras(block.split("\n")))
    inner = (
        f'<div class="issue-page">'
        f'<div class="issue-mast"><a class="brand-sm" href="{root}xiaozao.html">小灶</a>'
        f'<span class="meta-sm">{m["日期"].replace("-", " · ")} · {html.escape(m["时段"])} · {name}</span></div>'
        f'<header class="issue-head"><div class="issue-kicker">小灶 · {name}</div>'
        f'<h1 class="issue-title">{html.escape(m["标题"])}</h1></header>'
        f'<div class="piece-body">{"".join(html_parts)}</div>'
        f'<footer class="folio"><a href="{root}{ZONE_PAGE[m["zkey"]]}">← {name}</a>'
        f'<span class="center">{html.escape(dlabel(m["日期"]).split(" · ")[0])}</span>'
        f'<a href="{root}xiaozao.html">小灶主页</a></footer></div>'
    )
    return page(f'{name} · {m["标题"]}', inner, root, active="xiaozao")


def render_xz_history_page(m, body, root="../"):
    # reuse format_hist_body on lines
    lines = []
    for l in body.split("\n"):
        if l.startswith("## "):
            lines.append(l[3:])
        else:
            lines.append(l)
    hist_body = format_hist_body(lines)
    pslug = person_slug_from_meta(m)
    pname = person_name_from_title(m["标题"]) or "人物志"
    day, total = parse_day_progress(m["标题"])
    serial_bits = ["人物志 · 可按篇幅分日连载"]
    if day:
        serial_bits.append(f"第{day}天" + (f"／预计{total}天" if total else ""))
    serial = " · ".join(serial_bits)
    inner = (
        f'<div class="issue-page hist-page">'
        f'<div class="issue-mast"><a class="brand-sm" href="{root}xiaozao.html">小灶</a>'
        f'<span class="meta-sm">{m["日期"].replace("-", " · ")} · 历史人物</span></div>'
        f'<header class="issue-head"><div class="issue-kicker">小灶 · 历史人物 · {html.escape(pname)}</div>'
        f'<h1 class="issue-title">{html.escape(m["标题"])}</h1></header>'
        f'<div class="hist-serial">{html.escape(serial)}'
        f' · <a href="{root}xiaozao/person-{pslug}.html">本人物目录</a></div>'
        f'<div class="hist-body">{hist_body}</div>'
        f'<footer class="folio"><a href="{root}xiaozao/person-{pslug}.html">← {html.escape(pname)}</a>'
        f'<span class="center">{html.escape(dlabel(m["日期"]).split(" · ")[0])} · '
        f'<a href="{root}xiaozao-history.html">历史人物</a></span>'
        f'<a href="{root}xiaozao.html">小灶主页</a></footer></div>'
    )
    return page(f'历史 · {m["标题"]}', inner, root, active="xiaozao")



def main():
    issues = [parse(p) for p in sorted(SRC.glob("2*.md"))]
    (OUT / "issues").mkdir(exist_ok=True)
    xz_dir = OUT / "xiaozao"
    xz_dir.mkdir(exist_ok=True)
    for f in (OUT / "issues").glob("*.html"):
        f.unlink()
    for f in xz_dir.glob("*.html"):
        f.unlink()
    issues.sort(key=lambda x: x[0]["slug"])
    xz_items = load_xz()

    for idx, (m, body) in enumerate(issues):
        label = m.get("期次") or "日知连载"
        nav = '<div class="pager">'
        nav += (
            f'<a href="{issues[idx-1][0]["slug"]}.html">← 上一期</a>'
            if idx
            else "<span></span>"
        )
        nav += f'<a href="../day-{m["日期"]}.html">当日刊</a>'
        nav += (
            f'<a href="{issues[idx+1][0]["slug"]}.html">下一期 →</a>'
            if idx < len(issues) - 1
            else "<span></span>"
        )
        nav += "</div>"

        preamble, headlines, pieces, zg, signoff = split_sections(body)
        # 预览：小灶已独立，内页不渲染志怪／历史 teaser
        date_parts = m["日期"].split("-")
        vol_date = f"{date_parts[0]} · {int(date_parts[1])} · {int(date_parts[2])}"
        mast = (
            f'<div class="issue-mast"><a class="brand-sm" href="../index.html">Justknow</a>'
            f'<span class="meta-sm">{vol_date} · {html.escape(m["slot"])}</span></div>'
        )
        head = (
            f'<header class="issue-head"><div class="issue-kicker">{dlabel(m["日期"])} '
            f'<span class="sep">/</span> {m["slot"]}</div>'
            f'<h1 class="issue-title">{html.escape(label)}</h1>'
            f'<div class="byline">文 · <span class="who who-{m["署名"]}">{m["署名"]}</span></div></header>'
        )
        article = (
            mast
            + head
            + render_preamble(preamble)
            + render_double_lead(headlines)
            + render_piece_grid(pieces)
        )
        if signoff:
            article += f'<p class="signoff">{html.escape(signoff)}</p>'
        day_href = f'../day-{m["日期"]}.html'
        article += (
            f'<footer class="folio"><a href="{day_href}">← 当日刊</a>'
            f'<span class="center">{html.escape(dlabel(m["日期"]).split(" · ")[0])} · {html.escape(m["slot"])}</span>'
            f"<span>日知</span></footer>"
        )
        (OUT / "issues" / f'{m["slug"]}.html').write_text(
            page(
                f'{m.get("日期")} {m["slot"]} · {m["署名"]}',
                f'<div class="issue-page">{article}</div>' + nav,
                "../",
                active="rizhi",
            ),
            encoding="utf-8",
        )

    days = {}
    for m, body in issues:
        days.setdefault(m["日期"], []).append((m, body))

    # 小灶独立条目页／历史日章／人物枢纽页
    for m, body in xz_items:
        if m["zkey"] == "history":
            (xz_dir / f'history-{m["slug"]}.html').write_text(
                render_xz_history_page(m, body, root="../"), encoding="utf-8"
            )
        else:
            (xz_dir / f'entry-{m["slug"]}.html').write_text(
                render_xz_entry_page(m, body, root="../"), encoding="utf-8"
            )
    for person in group_history_persons(xz_items):
        (xz_dir / f'person-{person["slug"]}.html').write_text(
            render_person_hub(person, root="../"), encoding="utf-8"
        )

    (OUT / "index.html").write_text(
        page("Justknow · Lyn每日三次知识分享", home_html(issues, days, xz_items), "", active="home"),
        encoding="utf-8",
    )
    (OUT / "rizhi.html").write_text(
        page("日知主页", rizhi_rack_html(issues, days), "", active="rizhi"),
        encoding="utf-8",
    )
    (OUT / "today.html").write_text(
        page("今日刊", rizhi_today_html(issues), "", active="rizhi"),
        encoding="utf-8",
    )
    # 每日报纸总页（含今日 day-YYYY-MM-DD.html；今日另保留 today.html 品牌入口）
    for d, items in days.items():
        day_map = {m["slot"]: (m, body) for m, body in items}
        is_today = d == issues[-1][0]["日期"]
        td = datetime.date.fromisoformat(d)
        title = "今日刊" if is_today else f"{td.month}月{td.day}日刊"
        (OUT / f"day-{d}.html").write_text(
            page(title, rizhi_day_paper_html(d, day_map, is_today=is_today), "", active="rizhi"),
            encoding="utf-8",
        )
    # drop stale day-*.html no longer in source
    keep_days = {f"day-{d}.html" for d in days}
    for f in OUT.glob("day-*.html"):
        if f.name not in keep_days:
            f.unlink()
    (OUT / "archive.html").write_text(
        page("日知往期", archive_html(issues, days), "", active="rizhi"),
        encoding="utf-8",
    )
    (OUT / "xiaozao.html").write_text(
        page("小灶主页", xiaozao_home_html(xz_items), "", active="xiaozao"),
        encoding="utf-8",
    )
    for key, name, _ in ZONES:
        (OUT / ZONE_PAGE[key]).write_text(
            page(f"小灶 · {name}", xiaozao_zone_html(key, xz_items), "", active="xiaozao"),
            encoding="utf-8",
        )
    (OUT / "xiaozao-dates.html").write_text(
        page("小灶完整页", xiaozao_dates_html(xz_items), "", active="xiaozao"),
        encoding="utf-8",
    )
    xz_dates = sorted({m["日期"] for m, _ in xz_items})
    for d in xz_dates:
        td = datetime.date.fromisoformat(d)
        (OUT / f"xiaozao-day-{d}.html").write_text(
            page(f"小灶 · {td.month}月{td.day}日", xiaozao_day_html(d, xz_items), "", active="xiaozao"),
            encoding="utf-8",
        )
    keep_xd = {f"xiaozao-day-{d}.html" for d in xz_dates}
    for f in OUT.glob("xiaozao-day-*.html"):
        if f.name not in keep_xd:
            f.unlink()
    for key, name, _ in ZONES:
        (OUT / f"xiaozao-dates-{key}.html").write_text(
            page(f"小灶完整页 · {name}", xiaozao_dates_html(xz_items, filter_key=key), "", active="xiaozao"),
            encoding="utf-8",
        )
    (OUT / "zhiguai.html").write_text(
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta http-equiv="refresh" content="0;url=xiaozao.html">'
        '<title>小灶</title></head><body><p><a href="xiaozao.html">前往小灶主页 →</a></p></body></html>',
        encoding="utf-8",
    )

    n_persons = len(group_history_persons(xz_items))
    print(
        f"built {len(issues)} issues (no inline 小灶), {len(xz_items)} xiaozao entries, "
        f"{n_persons} history persons -> {OUT}"
    )



if __name__ == "__main__":
    main()
