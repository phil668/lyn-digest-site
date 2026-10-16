#!/usr/bin/env python3
"""Rebuild Lyn digest site from /workspace/lyn-digests/*.md. Usage: python3 build.py"""
import html, re, sys, datetime
from pathlib import Path

WD = "一二三四五六日"
ORDER = {"上午": 0, "午间": 1, "晚间": 2}
SLOT = {"下午": "午间"}
SRC = Path(sys.argv[1] if len(sys.argv) > 1 else "/workspace/lyn-digests")
OUT = Path(__file__).resolve().parent


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


def render(md):
    blocks, cur = [], []
    for line in md.split("\n"):
        if line.strip() == "":
            if cur:
                blocks.append(cur)
                cur = []
        else:
            cur.append(line)
    if cur:
        blocks.append(cur)
    out = []
    for b in blocks:
        i, para = 0, []

        def flush():
            if para:
                out.append("<p>" + "<br>\n".join(inline(x) for x in para) + "</p>")
                para.clear()

        while i < len(b):
            l = b[i]
            if re.fullmatch(r"\s*(-{3,}|\*{3,})\s*", l):
                flush()
                out.append("<hr>")
                i += 1
                continue
            m = re.match(r"(#{1,6})\s+(.*)", l)
            if m:
                flush()
                n = len(m.group(1))
                out.append(f"<h{n}>{inline(m.group(2))}</h{n}>")
                i += 1
                continue
            if l.startswith(">"):
                flush()
                q = []
                while i < len(b) and b[i].startswith(">"):
                    q.append(b[i].lstrip("> "))
                    i += 1
                out.append("<blockquote>" + "<br>".join(map(inline, q)) + "</blockquote>")
                continue
            for pat, tag in ((r"\s*[-*+]\s+(.*)", "ul"), (r"\s*\d+[.)]\s+(.*)", "ol")):
                if re.fullmatch(pat, l) and not re.match(r"\s*\*\*", l):
                    flush()
                    items = []
                    while (
                        i < len(b)
                        and re.fullmatch(pat, b[i])
                        and not re.match(r"\s*\*\*", b[i])
                    ):
                        items.append(re.fullmatch(pat, b[i]).group(1))
                        i += 1
                    out.append(
                        f"<{tag}>"
                        + "".join(f"<li>{inline(x)}</li>" for x in items)
                        + f"</{tag}>"
                    )
                    break
            else:
                para.append(l)
                i += 1
        flush()
    return out


def wrap_zhiguai(out_parts, column_href):
    """Wrap 志怪 section; return (html, start_index or None)."""
    for k, h in enumerate(out_parts):
        if "志怪" in h and (h.startswith("<p><strong>") or h.startswith("<h")) and k > 0:
            start = k - 1 if k > 0 and out_parts[k - 1] == "<hr>" else k
            body = "\n".join(out_parts[start:])
            section = (
                f'\n<section class="zhiguai" id="zhiguai">'
                f'<div class="tag-row"><span class="tag">志怪小灶</span>'
                f'<a class="col-link" href="{column_href}">查看专栏</a></div>\n'
                f"{body}\n</section>"
            )
            return "\n".join(out_parts[:start]) + section, start
    return "\n".join(out_parts), None


def strip_md(s):
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
    s = re.sub(r"[*#`_>]+", "", s)
    return s.strip()


def extract_zhiguai(body):
    """Return (title, excerpt_plain, section_md) or None."""
    lines = body.split("\n")
    start = None
    for i, l in enumerate(lines):
        if "志怪" in l and (("**" in l) or l.startswith("#")) and i > 0:
            start = i
            # include preceding --- if present
            if i > 0 and re.fullmatch(r"\s*(-{3,}|\*{3,})\s*", lines[i - 1] or ""):
                start = i  # keep heading as start for title
            break
    if start is None:
        return None
    # trim trailing signature like ——拓 / ——日知
    end = len(lines)
    while end > start and not lines[end - 1].strip():
        end -= 1
    if end > start and re.match(r"^——", lines[end - 1].strip()):
        end -= 1
    section_lines = lines[start:end]
    heading = strip_md(section_lines[0])
    # title: prefer text after ｜ or —— or ： after the label
    title = heading
    for sep in ("｜", "|", "——", "—", "："):
        if sep in heading:
            left, right = heading.split(sep, 1)
            if "志怪" in left and right.strip():
                title = right.strip()
                break
    # if still generic (just 志怪小灶), take next bold or first prose line
    if (
        title in ("志怪小灶", "附加 · 志怪／民俗恐怖新知", "附加｜志怪与恐怖新知")
        or title.startswith("附加")
        or title.startswith("附｜志怪")
        or title.startswith("附:志怪")
    ):
        for l in section_lines[1:]:
            s = strip_md(l)
            if not s:
                continue
            if l.strip().startswith("**") and ("志怪" in l or "：" in l or ":" in l):
                title = s
                for sep in ("：", ":"):
                    if sep in title and ("志怪" in title.split(sep, 1)[0] or len(title.split(sep, 1)[0]) < 6):
                        title = title.split(sep, 1)[-1].strip() or title
                        break
                break
            # 书名优先，再取故事名「…」
            m = re.search(r"《([^》]{2,40})》", s)
            if m and ("志怪" in s or "知识史" in s or "研究" in s or "出版" in s):
                title = f"《{m.group(1)}》"
                break
            m = re.search(r"「([^」]{2,20})」", s)
            if m:
                title = m.group(1)
                break
            if len(s) > 8:
                title = s[:36] + ("…" if len(s) > 36 else "")
                break
    # excerpt: first substantial prose after heading (and after nested title if any)
    excerpt = ""
    skip_next_bold = title != strip_md(section_lines[0])
    for l in section_lines[1:]:
        s = strip_md(l)
        if not s:
            continue
        if skip_next_bold and l.strip().startswith("**"):
            skip_next_bold = False
            continue
        if re.match(r"^——", s):
            continue
        excerpt = s
        break
    if len(excerpt) > 120:
        excerpt = excerpt[:120] + "…"
    return title, excerpt, "\n".join(section_lines)


def parse(p):
    meta, lines = {}, p.read_text(encoding="utf-8").split("\n")
    while lines and re.match(r"#\s*[^\s:：]+[:：]", lines[0]):
        k, v = re.split(r"[:：]", lines.pop(0)[1:], maxsplit=1)
        meta[k.strip()] = v.strip()
    meta.setdefault("署名", "拓" if "期次" in meta else "日知")
    meta["slot"] = SLOT.get(meta.get("时段", ""), meta.get("时段", ""))
    meta["slug"] = p.stem
    return meta, "\n".join(lines).strip()


def page(title, body, root, active=None):
    nav_links = [
        ("index.html", "目录", "home"),
        ("zhiguai.html", "志怪专栏", "zhiguai"),
    ]
    links_html = "".join(
        f'<a href="{root}{href}" class="nav-link{" active" if active == key else ""}">{label}</a>'
        for href, label, key in nav_links
    )
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>
<link rel="stylesheet" href="{root}styles.css"><script>if(localStorage.theme)document.documentElement.dataset.theme=localStorage.theme</script></head>
<body><nav class="top"><a href="{root}index.html" class="brand">日知 · Lyn每日三次知识分享</a>
<div class="nav-right">{links_html}
<button type="button" onclick="var d=document.documentElement;d.dataset.theme=d.dataset.theme=='dark'?'light':'dark';localStorage.theme=d.dataset.theme" aria-label="切换主题">◐</button></div></nav>
<main>{body}</main><footer>日知连载 · 拓往期已归档 · 本地预览</footer></body></html>"""


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
        nav += '<a href="../index.html">目录</a>'
        nav += (
            f'<a href="{issues[idx+1][0]["slug"]}.html">下一期 →</a>'
            if idx < len(issues) - 1
            else "<span></span>"
        )
        nav += "</div>"
        head = (
            f'<header class="issue-head"><div class="kicker">{dlabel(m["日期"])} '
            f'<span class="sep">/</span> {m["slot"]}</div>'
            f"<h1>{html.escape(label)}</h1>"
            f'<div class="byline">文 · <span class="who who-{m["署名"]}">{m["署名"]}</span></div></header>'
        )
        parts = render(body)
        article_html, _ = wrap_zhiguai(parts, "../zhiguai.html")
        (OUT / "issues" / f'{m["slug"]}.html').write_text(
            page(
                f'{m.get("日期")} {m["slot"]} · {m["署名"]}',
                head + f"<article>{article_html}</article>" + nav,
                "../",
                active="home",
            ),
            encoding="utf-8",
        )
        zg = extract_zhiguai(body)
        if zg:
            title, excerpt, _ = zg
            zhiguai_entries.append((m, title, excerpt))

    # home by date
    days = {}
    for m, body in issues:
        first = next(
            (
                re.sub(r"[*#\[\]]|\(http\S+\)", "", l).strip()
                for l in body.split("\n")
                if l.strip() and not l.startswith("Lyn")
            ),
            "",
        )
        days.setdefault(m["日期"], []).append((m, first))
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
        + "".join(
            f'<a href="#d{d}">{dlabel(d).split(" ")[0]}</a>'
            for d in sorted(days, reverse=True)
        )
        + '</nav>'
    )
    intro = (
        '<h1>Lyn每日三次知识分享</h1>'
        '<p class="intro">每天上午、午间、晚间三档，跨领域新知加一份「志怪小灶」。'
        '自 2026-10-16 午间起由<strong>日知</strong>连载；此前第1–8期由<strong>拓</strong>发出，已归档于此。'
        '亦可单独翻阅 <a href="zhiguai.html">志怪专栏</a>。</p>'
    )
    (OUT / "index.html").write_text(
        page(
            "Lyn每日三次知识分享",
            intro
            + f'<p class="count">共 {len(issues)} 期 · 按日编排</p>'
            + jump
            + "".join(rows),
            "",
            active="home",
        ),
        encoding="utf-8",
    )

    # 志怪专栏 — newest first
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
        "<h1>志怪小灶</h1>"
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
