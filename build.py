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
        f'<div class="issue-mast"><a class="brand-sm" href="{root}index.html">日知</a>'
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
<body><nav class="top"><a href="{root}index.html" class="brand">日知 · Lyn每日三次知识分享</a>
<div class="nav-right">{links_html}
<button type="button" onclick="var d=document.documentElement;d.dataset.theme=d.dataset.theme=='dark'?'light':'dark';localStorage.theme=d.dataset.theme" aria-label="切换主题">◐</button></div></nav>
{inner}<footer>日知 · Lyn每日三次知识分享</footer></body></html>"""


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


def load_xz():
    items = [parse_xz(p) for p in sorted(XZ_SRC.glob("*.md"))]
    items.sort(key=lambda x: (x[0]["日期"], ORDER.get(x[0]["时段"], 9), x[0]["slug"]))
    return items


# 历史人物按「人」整合（专区页先人后日）
# 例程约定：历史连载仅午间 14:54 更新一天（见 HISTORY.md）
PERSON_BIOS = {
    "jiaxu": (
        "三国魏谋士，字文和，武威姑臧人。"
        "本传见《三国志·魏书》卷十；本站连载按其一生事迹分日。"
    ),
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


def group_history_persons(xz_items):
    """List of person dicts, most recently updated first."""
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
        p["published"] = len(ch)
        p["latest"] = max(c["meta"]["日期"] for c in ch)
        persons.append(p)
    persons.sort(key=lambda p: p["latest"], reverse=True)
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
        lis.append(
            f'<li class="person-chapter">'
            f'<a href="{href}">'
            f'<div class="meta">{dlabel(m["日期"])} · {m["时段"]} · {day_label}</div>'
            f'<div class="zg-title">{html.escape(m["标题"])}</div>'
            f'<span class="go-mini">阅读 →</span></a></li>'
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
        f'<p class="person-bio">{html.escape(bio)}</p>'
        f'<p class="person-progress">{html.escape(prog)}</p>'
        f"</header>"
        f'<div class="archive-block"><h2>连载章节</h2>'
        f'<ul class="zg-list person-chapters">{"".join(lis)}</ul></div></div>'
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
<div class="vol">VOL. 01 · {today}</div><h1 class="rack-title">日知</h1></div>
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
<div class="archive-strip"><div class="copy"><strong>日知主页</strong>今日刊 · 近日四则 · 往期</div>
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
<div class="archive-strip archive-strip-xz"><div class="copy"><strong>小灶主页</strong>四专区 · 按日浏览</div>
<a class="go" href="xiaozao.html">进入小灶 →</a></div>
</section>
</div>"""


def rizhi_rack_html(issues, days):
    today, today_map, cards, status, t, vol_date = _today_status(issues)
    recent = []
    for d in sorted((d for d in days if d < today), reverse=True)[:4]:
        items = sorted(days[d], key=lambda x: (ORDER.get(x[0]["slot"], 9), x[0]["slug"]))
        li = "".join(
            f'<li><a href="issues/{m["slug"]}.html"><span class="s">{m["slot"]}</span>'
            f'<span class="t">{html.escape(_clip(_short_title(f), 40))}</span></a></li>'
            for m, f in items
        )
        td = datetime.date.fromisoformat(d)
        recent.append(
            f'<article class="day-card"><h3 class="day-date">{td.month}月{td.day}日'
            f'<span class="dow">周{WD[td.weekday()]}</span></h3><ul>{li}</ul></article>'
        )
    return f"""<div class="home page-wide"><header class="rack-mast"><div>
<div class="vol">VOL. 01 · {today}</div><h1 class="rack-title">日知</h1></div>
<div class="rack-sub"><strong>{vol_date}</strong>周{WD[t.weekday()]} · 日知主页<br>{status}</div></header>
<section class="rack-section" aria-labelledby="today-h"><div class="rack-section-head">
<h2 id="today-h">今日刊</h2><span class="hint">{dlabel(today)}</span></div>
<div class="today-grid">{cards}</div></section>
<section class="rack-section" aria-labelledby="recent-h"><div class="rack-section-head">
<h2 id="recent-h">近日四则</h2><a class="hint" href="archive.html">日知往期 →</a></div>
<div class="recent-grid">{"".join(recent)}</div></section>
<div class="archive-strip"><div class="copy"><strong>日知往期</strong>共 {len(issues)} 期 · 按日编排</div>
<a class="go" href="archive.html">打开往期 →</a></div></div>"""


def archive_html(issues, days):
    rows = []
    for d in sorted(days, reverse=True):
        items = sorted(days[d], key=lambda x: (ORDER.get(x[0]["slot"], 9), x[0]["slug"]))
        li = "".join(
            f'<li><a href="issues/{m["slug"]}.html"><span class="slot">{m["slot"]}</span>'
            f'<span class="entry"><span class="meta"><span class="who who-{m["署名"]}">{m["署名"]}</span> '
            f'{m.get("期次","日知连载")}</span><span class="teaser">{html.escape(f[:60])}</span></span></a></li>'
            for m, f in items
        )
        rows.append(
            f'<section class="day" id="d{d}"><h2 class="date">{dlabel(d)}</h2><ul class="list">{li}</ul></section>'
        )
    jump = (
        '<nav class="jump">'
        + "".join(f'<a href="#d{d}">{dlabel(d).split(" ")[0]}</a>' for d in sorted(days, reverse=True))
        + "</nav>"
    )
    return (
        '<div class="archive-page"><a class="back" href="rizhi.html">← 回日知主页</a>'
        f'<div class="archive-block"><h2>日知往期</h2>'
        f'<p class="count">共 {len(issues)} 期 · 按日编排</p>'
        f"{jump}{''.join(rows)}</div></div>"
    )


def xiaozao_home_html(xz_items):
    latest = _latest_by_zone(xz_items)
    # recent 4 across all zones
    recent = list(reversed(xz_items))[:4]
    cards = []
    for key, name, desc in ZONES:
        page = ZONE_PAGE[key]
        if key in latest:
            m, b = latest[key]
            hook = _xz_hook_line(b, 64) or m["标题"]
            extra = ""
            if key == "history":
                page = f'xiaozao/person-{person_slug_from_meta(m)}.html'
                extra = f'<a class="zone-hist" href="{page}">进入人物志 →</a>'
                page = ZONE_PAGE[key]  # zone list page for 进入专区
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
    recent_html = "".join(
        f'<a class="xz-day-card" href="{ZONE_PAGE[m["zkey"]]}">'
        f'<div class="xz-day-meta">{m["日期"][5:].replace("-","/")} · {m["时段"]} · {next(n for k,n,_ in ZONES if k==m["zkey"])}</div>'
        f'<div class="xz-day-hook">{html.escape(_clip(m["标题"], 36))}</div>'
        f'<span class="xz-day-go">打开 →</span></a>'
        for m, b in recent
    )
    today = xz_items[-1][0]["日期"] if xz_items else ""
    t = datetime.date.fromisoformat(today) if today else datetime.date.today()
    vol_date = f"{t.year} · {t.month} · {t.day}"
    return f"""<div class="home home-xz-page page-wide"><header class="rack-mast"><div>
<div class="vol">VOL. 01 · {today}</div><h1 class="rack-title">小灶</h1></div>
<div class="rack-sub"><strong>{vol_date}</strong>周{WD[t.weekday()]} · 小灶主页<br>四专区独立连载</div></header>
<section class="rack-section" aria-labelledby="zones-h"><div class="rack-section-head">
<h2 id="zones-h">四专区</h2><a class="hint" href="xiaozao-dates.html">按日浏览 →</a></div>
<div class="zone-grid">{"".join(cards)}</div></section>
<section class="rack-section" aria-labelledby="xz-recent-h"><div class="rack-section-head">
<h2 id="xz-recent-h">近日更新</h2><span class="hint">跨专区</span></div>
<div class="xz-recent-grid">{recent_html}</div></section>
<div class="archive-strip archive-strip-xz"><div class="copy"><strong>小灶日期页</strong>共 {len(xz_items)} 则 · 可按专区筛选</div>
<a class="go" href="xiaozao-dates.html">打开日期页 →</a></div></div>"""


def xiaozao_zone_html(zkey, xz_items):
    name = next(n for k, n, _ in ZONES if k == zkey)
    desc = next(d for k, _, d in ZONES if k == zkey)
    items = [(m, b) for m, b in xz_items if m["zkey"] == zkey]
    items = list(reversed(items))
    tabs = "".join(
        f'<a class="ztab{" active" if k==zkey else ""}" href="{ZONE_PAGE[k]}">{n}</a>'
        for k, n, _ in ZONES
    )
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
                f'<p class="person-bio">{html.escape(p["bio"])}</p>'
                f'<div class="person-progress">{html.escape(prog)}</div>'
                f'<span class="go-mini">进入人物志 →</span></a></li>'
            )
        return (
            f'<div class="archive-page zone-page"><a class="back" href="xiaozao.html">← 回小灶主页</a>'
            f'<nav class="zone-tabs" aria-label="专区">{tabs}</nav>'
            f'<div class="archive-block"><h2>{name}</h2>'
            f'<p class="count">{desc} · 共 {len(persons)} 人 · 先按人浏览再进日章</p>'
            f'<ul class="person-grid">{"".join(cards)}</ul></div></div>'
        )
    lis = []
    for m, b in items:
        hook = _xz_hook_line(b, 72)
        href = f'xiaozao/entry-{m["slug"]}.html'
        lis.append(
            f'<li class="xz-entry">'
            f'<a href="{href}">'
            f'<div class="meta">{dlabel(m["日期"])} · {m["时段"]}</div>'
            f'<div class="zg-title">{html.escape(m["标题"])}</div>'
            f'<div class="teaser">{html.escape(hook)}</div>'
            f'<span class="go-mini">阅读 →</span></a></li>'
        )
    return (
        f'<div class="archive-page zone-page"><a class="back" href="xiaozao.html">← 回小灶主页</a>'
        f'<nav class="zone-tabs" aria-label="专区">{tabs}</nav>'
        f'<div class="archive-block"><h2>{name}</h2>'
        f'<p class="count">{desc} · 共 {len(items)} 则</p>'
        f'<ul class="zg-list">{"".join(lis)}</ul></div></div>'
    )


def xiaozao_dates_html(xz_items, filter_key=None):
    by = {}
    for m, b in xz_items:
        if filter_key and m["zkey"] != filter_key:
            continue
        by.setdefault(m["日期"], []).append((m, b))
    tabs = ['<a class="ztab%s" href="xiaozao-dates.html">全部</a>' % (" active" if not filter_key else "")]
    for k, n, _ in ZONES:
        tabs.append(
            f'<a class="ztab{" active" if filter_key==k else ""}" href="xiaozao-dates.html?zone={k}">{n}</a>'
        )
    # static filter pages instead of querystring for file:// compatibility
    # rebuild tabs to use xiaozao-dates-{key}.html
    tabs = [
        f'<a class="ztab{" active" if not filter_key else ""}" href="xiaozao-dates.html">全部</a>'
    ]
    for k, n, _ in ZONES:
        href = "xiaozao-dates.html" if False else f"xiaozao-dates-{k}.html"
        if k == "zhiguai":
            pass
        tabs.append(
            f'<a class="ztab{" active" if filter_key==k else ""}" href="xiaozao-dates-{k}.html">{n}</a>'
        )

    rows = []
    for d in sorted(by, reverse=True):
        items = sorted(by[d], key=lambda x: (ORDER.get(x[0]["时段"], 9), x[0]["slug"]))
        lis = []
        for m, b in items:
            name = next(n for k, n, _ in ZONES if k == m["zkey"])
            hook = _xz_hook_line(b, 48)
            if m["zkey"] == "history":
                href = f'xiaozao/history-{m["slug"]}.html'
            else:
                href = f'xiaozao/entry-{m["slug"]}.html'
            lis.append(
                f'<li><a href="{href}">'
                f'<span class="slot xz-slot xz-{m["zkey"]}">{name[:2]}</span>'
                f'<span class="entry"><span class="meta">{m["时段"]} · {html.escape(m["标题"])}</span>'
                f'<span class="teaser">{html.escape(hook)}</span></span></a></li>'
            )
        rows.append(
            f'<section class="day" id="xz{d}"><h2 class="date">{dlabel(d)}</h2>'
            f'<ul class="list">{"".join(lis)}</ul></section>'
        )
    title = "小灶日期页" if not filter_key else f'小灶日期页 · {next(n for k,n,_ in ZONES if k==filter_key)}'
    return (
        f'<div class="archive-page"><a class="back" href="xiaozao.html">← 回小灶主页</a>'
        f'<nav class="zone-tabs" aria-label="专区筛选">{"".join(tabs)}</nav>'
        f'<div class="archive-block"><h2>{title}</h2>'
        f'<p class="count">共 {sum(len(v) for v in by.values())} 则 · 按日编排</p>'
        f'{"".join(rows)}</div></div>'
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
        nav += '<a href="../archive.html">目录</a>'
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
            f'<div class="issue-mast"><a class="brand-sm" href="../index.html">日知</a>'
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
        article += (
            f'<footer class="folio"><a href="../archive.html">← 目录</a>'
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
        days.setdefault(m["日期"], []).append((m, first_piece_teaser(body)))

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
        page("Lyn每日三次知识分享", home_html(issues, days, xz_items), "", active="home"),
        encoding="utf-8",
    )
    (OUT / "rizhi.html").write_text(
        page("日知主页", rizhi_rack_html(issues, days), "", active="rizhi"),
        encoding="utf-8",
    )
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
        page("小灶日期页", xiaozao_dates_html(xz_items), "", active="xiaozao"),
        encoding="utf-8",
    )
    for key, name, _ in ZONES:
        (OUT / f"xiaozao-dates-{key}.html").write_text(
            page(f"小灶日期页 · {name}", xiaozao_dates_html(xz_items, filter_key=key), "", active="xiaozao"),
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
