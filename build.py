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
                kind = "zhiguai" if "志怪" in domain or "志怪" in title else "piece"
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
            zg = next((b for b in blocks if b[0] == "zhiguai"), None)
            return preamble, headlines, pieces, zg, signoff
        if not blocks:
            if line.strip():
                preamble.append(line)
        i += 1

    headlines = [b for b in blocks if b[0] == "headline"]
    pieces = [b for b in blocks if b[0] == "piece"]
    zg = next((b for b in blocks if b[0] == "zhiguai"), None)
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


def render_zhiguai(zg, column_href):
    if not zg:
        return ""
    kind, domain, title, body_lines = zg
    # title may still contain long 附｜志怪小灶：…
    display = title
    for sep in ("：", ":"):
        if "志怪" in display and sep in display:
            # keep after last useful sep if very long label
            pass
    return (
        f'<aside class="zg-spread" id="zhiguai">'
        f'<div class="tag-row"><span class="zg-tag">志怪小灶</span>'
        f'<a class="col-link" href="{column_href}">查看专栏</a></div>'
        f'<h3 class="zg-title">{html.escape(display)}</h3>'
        f'<div class="zg-body">{body_to_paras(body_lines)}</div>'
        f"</aside>"
    )


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
    _, _, _, zg, _ = split_sections(body)
    if not zg:
        return None
    _, domain, title, body_lines = zg
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
        ("index.html", "刊架", "home"),
        ("archive.html", "往期", "archive"),
        ("zhiguai.html", "志怪专栏", "zhiguai"),
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


def rack_html(issues, days):
    latest_m = issues[-1][0]
    today = latest_m["日期"]
    today_map = {m["slot"]: (m, b) for m, b in issues if m["日期"] == today}
    # 强调卡：今日最新且带双头条的一场，否则今日最新一场
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

    return f"""<div class="home"><header class="rack-mast"><div>
<div class="vol">VOL. 01 · {today}</div><h1 class="rack-title">日知</h1></div>
<div class="rack-sub"><strong>{vol_date}</strong>周{WD[t.weekday()]} · 知识分享<br>{status}</div></header>
<section class="rack-section" aria-labelledby="today-h"><div class="rack-section-head">
<h2 id="today-h">今日刊</h2><span class="hint">{dlabel(today)}</span></div>
<div class="today-grid">{cards}</div></section>
<section class="rack-section" aria-labelledby="recent-h"><div class="rack-section-head">
<h2 id="recent-h">近日</h2><a class="hint" href="archive.html">全部目录 →</a></div>
<div class="recent-grid">{"".join(recent)}</div></section>
<div class="archive-strip"><div class="copy"><strong>往期</strong>共 {len(issues)} 期 · 按日编排</div>
<a class="go" href="archive.html">全部目录 →</a></div>
<div class="zg-blurb"><span>志怪小灶：每期附一篇聊斋／子不语等志怪短篇。</span>
<a href="zhiguai.html">志怪专栏 →</a></div></div>"""


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
        '<div class="archive-page"><a class="back" href="index.html">← 回刊架</a>'
        f'<div class="archive-block"><h2>全部目录</h2>'
        f'<p class="count">共 {len(issues)} 期 · 按日编排 · 亦可 <a href="zhiguai.html">志怪专栏</a></p>'
        f"{jump}{''.join(rows)}</div></div>"
    )


def main():
    issues = [parse(p) for p in sorted(SRC.glob("2*.md"))]
    (OUT / "issues").mkdir(exist_ok=True)
    for f in (OUT / "issues").glob("*.html"):
        f.unlink()
    issues.sort(key=lambda x: x[0]["slug"])

    zhiguai_entries = []

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
            + render_zhiguai(zg, "../zhiguai.html")
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
                active="home",
            ),
            encoding="utf-8",
        )
        zg_info = extract_zhiguai(body)
        if zg_info:
            title, excerpt = zg_info
            zhiguai_entries.append((m, title, excerpt))

    days = {}
    for m, body in issues:
        days.setdefault(m["日期"], []).append((m, first_piece_teaser(body)))

    (OUT / "index.html").write_text(
        page(
            "Lyn每日三次知识分享",
            rack_html(issues, days),
            "",
            active="home",
        ),
        encoding="utf-8",
    )
    (OUT / "archive.html").write_text(
        page("往期目录 · 日知", archive_html(issues, days), "", active="archive"),
        encoding="utf-8",
    )

    zg_items = []
    for m, title, excerpt in reversed(zhiguai_entries):
        zg_items.append(
            f'<li class="zg-entry">'
            f'<a href="issues/{m["slug"]}.html#zhiguai">'
            f'<div class="meta"><span class="who who-{m["署名"]}">{m["署名"]}</span> '
            f'{dlabel(m["日期"])} · {m["slot"]}</div>'
            f'<div class="zg-title">{html.escape(title)}</div>'
            f'<div class="teaser">{html.escape(excerpt)}</div>'
            f"</a></li>"
        )
    zg_body = (
        '<header class="issue-head"><div class="kicker">专栏</div>'
        '<h1 class="issue-title">志怪小灶</h1>'
        '<p class="intro" style="margin:0">每期知识分享末尾的志怪／民俗短篇，按时间倒序汇于此。'
        "点开可跳到该期全文对应段落。</p></header>"
        f'<p class="count">共 {len(zhiguai_entries)} 则</p>'
        f'<ul class="zg-list">{"".join(zg_items)}</ul>'
    )
    (OUT / "zhiguai.html").write_text(
        page("志怪小灶 · 专栏", zg_body, "", active="zhiguai"), encoding="utf-8"
    )

    print(f"built {len(issues)} issues, {len(zhiguai_entries)} zhiguai -> {OUT}")


if __name__ == "__main__":
    main()
