from __future__ import annotations

import html
import re
import urllib.parse
from typing import Any

from domain.artifact.workspace import ArtifactWorkspace


DEFAULT_OUTPUT_PATH = "research/summary-site.html"
MAX_SOURCES = 80
MAX_SECTIONS = 40


def build_summary_site(input_data: dict[str, Any] | None) -> dict[str, Any]:
    data = input_data if isinstance(input_data, dict) else {}
    title = _clean_text(data.get("title") or data.get("query") or "Research Summary Site", 180)
    query = _clean_text(data.get("query") or "", 220)
    summary = _clean_text(data.get("summary") or data.get("overview") or "", 4000)
    sources = _normalize_sources(data.get("sources"))
    sections = _normalize_sections(data.get("sections"), sources)
    if not summary and not sections and sources:
        summary = _clean_text(sources[0].get("summary") or "", 1200)
    if not summary and not sections:
        raise ValueError("'summary' or 'sections' is required")

    html_content = _render_html(
        title=title,
        query=query,
        summary=summary,
        sections=sections,
        sources=sources,
    )
    return {
        "type": "html",
        "title": title,
        "query": query,
        "summary": summary,
        "source_count": len(sources),
        "section_count": len(sections),
        "content": html_content,
    }


def write_summary_site(
    input_data: dict[str, Any] | None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = input_data if isinstance(input_data, dict) else {}
    site = build_summary_site(data)
    output_path = str(data.get("output_path") or DEFAULT_OUTPUT_PATH)
    workspace = ArtifactWorkspace(context)
    target = workspace.resolve(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(site["content"], encoding="utf-8")
    relative_path = workspace.relative(target)
    artifact = {
        "path": relative_path,
        "type": "file",
        "mime_type": "text/html",
        "title": site["title"],
    }
    return {
        **site,
        "path": relative_path,
        "size": target.stat().st_size,
        "artifact": artifact,
        "artifacts": [artifact],
    }


def _normalize_sources(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("'sources' must be a list")
    sources: list[dict[str, Any]] = []
    for index, item in enumerate(value[:MAX_SOURCES], start=1):
        if not isinstance(item, dict):
            continue
        url = _safe_url(item.get("url"))
        path = _clean_text(item.get("path") or "", 300)
        source_id = _clean_text(item.get("source_id") or f"source-{index}", 220)
        title = _clean_text(item.get("title") or path or url or source_id, 220)
        summary = _clean_text(item.get("summary") or item.get("excerpt") or "", 1200)
        provider = _clean_text(item.get("provider") or item.get("type") or "", 80)
        trust_level = _clean_text(item.get("trust_level") or "", 80)
        retrieved_at = _clean_text(item.get("retrieved_at") or "", 80)
        sources.append(
            {
                "index": index,
                "source_id": source_id,
                "title": title,
                "summary": summary,
                "url": url,
                "path": path,
                "provider": provider,
                "trust_level": trust_level,
                "retrieved_at": retrieved_at,
            }
        )
    return sources


def _normalize_sections(value: Any, sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [{"title": "Findings", "body": value}]
    if not isinstance(value, list):
        raise ValueError("'sections' must be a list or string")

    sections: list[dict[str, Any]] = []
    source_count = len(sources)
    for index, item in enumerate(value[:MAX_SECTIONS], start=1):
        if isinstance(item, str):
            item = {"title": f"Finding {index}", "body": item}
        if not isinstance(item, dict):
            continue
        title = _clean_text(item.get("title") or f"Finding {index}", 180)
        body = _clean_text(item.get("body") or item.get("content") or "", 3000)
        bullets = _normalize_text_list(item.get("bullets") or item.get("points"), 16, 500)
        refs = _normalize_refs(item.get("sources") or item.get("source_indexes"), source_count)
        if body or bullets:
            sections.append(
                {
                    "id": _unique_section_id(title, index),
                    "title": title,
                    "body": body,
                    "bullets": bullets,
                    "sources": refs,
                }
            )
    return sections


def _normalize_text_list(value: Any, max_items: int, max_chars: int) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [line for line in value.splitlines() if line.strip()]
    if not isinstance(value, list):
        return []
    cleaned: list[str] = []
    for item in value[:max_items]:
        text = _clean_text(item, max_chars)
        if text:
            cleaned.append(text)
    return cleaned


def _normalize_refs(value: Any, source_count: int) -> list[int]:
    if value is None:
        return []
    if not isinstance(value, list):
        value = [value]
    refs: list[int] = []
    for item in value:
        try:
            ref = int(item)
        except (TypeError, ValueError):
            continue
        if 1 <= ref <= source_count and ref not in refs:
            refs.append(ref)
    return refs


def _render_html(
    *,
    title: str,
    query: str,
    summary: str,
    sections: list[dict[str, Any]],
    sources: list[dict[str, Any]],
) -> str:
    section_links = "\n".join(
        f'<a href="#{_attr(section["id"])}">{_text(section["title"])}</a>' for section in sections
    )
    source_links = '<a href="#sources">Sources</a>' if sources else ""
    nav = "\n".join(part for part in (section_links, source_links) if part)
    query_html = f'<p class="query">Research query: {_text(query)}</p>' if query else ""
    summary_html = f'<p class="summary">{_text(summary)}</p>' if summary else ""

    section_cards = "\n".join(_render_section(section) for section in sections)
    if not section_cards:
        section_cards = '<section class="empty"><h2>Findings</h2><p>No structured findings were provided.</p></section>'

    source_cards = "\n".join(_render_source(source) for source in sources)
    if not source_cards:
        source_cards = '<p class="muted">No sources were attached to this summary.</p>'

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_text(title)}</title>
  <style>
    :root {{
      color-scheme: light dark;
      --bg: #f7f8fb;
      --paper: #ffffff;
      --ink: #17202a;
      --muted: #637083;
      --line: #dce2ea;
      --accent: #0f766e;
      --accent-soft: #e0f2ef;
      --warn: #9a3412;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      line-height: 1.58;
    }}
    .shell {{
      max-width: 1120px;
      margin: 0 auto;
      padding: 32px 20px 48px;
    }}
    header {{
      display: grid;
      gap: 14px;
      padding: 28px 0 22px;
      border-bottom: 1px solid var(--line);
    }}
    h1 {{
      margin: 0;
      max-width: 900px;
      font-size: clamp(2rem, 4vw, 4rem);
      line-height: 1.05;
      letter-spacing: 0;
    }}
    h2, h3 {{
      letter-spacing: 0;
      line-height: 1.2;
    }}
    .summary, .query {{
      max-width: 860px;
      margin: 0;
      color: var(--muted);
      font-size: 1rem;
    }}
    .stats {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 6px;
    }}
    .stat, .badge {{
      display: inline-flex;
      align-items: center;
      min-height: 28px;
      padding: 0 10px;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: var(--paper);
      color: var(--muted);
      font-size: 0.86rem;
      white-space: nowrap;
    }}
    nav {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin: 18px 0 26px;
    }}
    nav a {{
      color: var(--accent);
      background: var(--accent-soft);
      border: 1px solid transparent;
      border-radius: 999px;
      padding: 7px 11px;
      text-decoration: none;
      font-weight: 650;
      font-size: 0.9rem;
    }}
    main {{
      display: grid;
      gap: 18px;
    }}
    section {{
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 22px;
    }}
    section h2 {{
      margin: 0 0 12px;
      font-size: 1.28rem;
    }}
    section p {{
      margin: 0 0 12px;
    }}
    ul {{
      margin: 12px 0 0;
      padding-left: 1.25rem;
    }}
    .refs {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 16px;
    }}
    .refs a, .source-index {{
      color: var(--accent);
      font-weight: 700;
      text-decoration: none;
    }}
    .source-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 14px;
      margin-top: 14px;
    }}
    .source-card {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
      background: color-mix(in srgb, var(--paper), var(--bg) 18%);
    }}
    .source-card h3 {{
      margin: 0 0 8px;
      font-size: 1rem;
    }}
    .source-card p {{
      color: var(--muted);
      font-size: 0.92rem;
    }}
    .source-card a {{
      overflow-wrap: anywhere;
      color: var(--accent);
    }}
    .meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 12px;
    }}
    .muted {{
      color: var(--muted);
    }}
    footer {{
      margin-top: 24px;
      color: var(--muted);
      font-size: 0.88rem;
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --bg: #111418;
        --paper: #191f26;
        --ink: #eef3f7;
        --muted: #a7b1bd;
        --line: #313a45;
        --accent: #5eead4;
        --accent-soft: #123d38;
      }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <header>
      <h1>{_text(title)}</h1>
      {query_html}
      {summary_html}
      <div class="stats">
        <span class="stat">{len(sections)} findings</span>
        <span class="stat">{len(sources)} sources</span>
        <span class="stat">Local HTML artifact</span>
      </div>
    </header>
    <nav aria-label="Summary sections">
      {nav}
    </nav>
    <main>
      {section_cards}
      <section id="sources">
        <h2>Sources</h2>
        <div class="source-grid">
          {source_cards}
        </div>
      </section>
    </main>
    <footer>
      Generated by Rumi defaultspack research summary-site builder.
    </footer>
  </div>
</body>
</html>
"""


def _render_section(section: dict[str, Any]) -> str:
    bullets = "".join(f"<li>{_text(item)}</li>" for item in section.get("bullets", []))
    bullet_block = f"<ul>{bullets}</ul>" if bullets else ""
    refs = "".join(
        f'<a class="badge" href="#source-{ref}">Source {ref}</a>' for ref in section.get("sources", [])
    )
    ref_block = f'<div class="refs">{refs}</div>' if refs else ""
    body = f"<p>{_text(section.get('body', ''))}</p>" if section.get("body") else ""
    return f"""<section id="{_attr(section["id"])}">
  <h2>{_text(section["title"])}</h2>
  {body}
  {bullet_block}
  {ref_block}
</section>"""


def _render_source(source: dict[str, Any]) -> str:
    index = int(source.get("index") or 0)
    title = _text(source.get("title") or f"Source {index}")
    url = source.get("url") or ""
    path = source.get("path") or ""
    summary = source.get("summary") or ""
    destination = url or path
    if url:
        heading = f'<h3><a href="{_attr(url)}" rel="noreferrer">{title}</a></h3>'
        destination_html = f'<a href="{_attr(url)}" rel="noreferrer">{_text(url)}</a>'
    else:
        heading = f"<h3>{title}</h3>"
        destination_html = _text(destination)
    provider = source.get("provider") or "source"
    trust = source.get("trust_level") or "unrated"
    retrieved = source.get("retrieved_at") or ""
    retrieved_badge = f'<span class="badge">{_text(retrieved)}</span>' if retrieved else ""
    summary_html = f"<p>{_text(summary)}</p>" if summary else ""
    return f"""<article class="source-card" id="source-{index}">
  <div class="source-index">Source {index}</div>
  {heading}
  {summary_html}
  <p>{destination_html}</p>
  <div class="meta">
    <span class="badge">{_text(provider)}</span>
    <span class="badge">{_text(trust)}</span>
    {retrieved_badge}
  </div>
</article>"""


def _clean_text(value: Any, max_chars: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:max_chars]


def _safe_url(value: Any) -> str:
    url = _clean_text(value, 800)
    if not url:
        return ""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return urllib.parse.urlunparse(parsed)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", str(value or "").lower()).strip("-")
    return slug[:80].strip("-")


def _unique_section_id(title: str, index: int) -> str:
    slug = _slugify(title) or "finding"
    return f"{slug}-{index}"


def _text(value: Any) -> str:
    return html.escape(str(value or ""), quote=False)


def _attr(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)
