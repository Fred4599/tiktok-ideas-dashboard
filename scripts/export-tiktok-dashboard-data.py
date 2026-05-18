#!/usr/bin/env python3
"""Export sanitized TikTok idea dashboard data from Hermes local workspace.

Keeps only public/operational summary fields. Does not publish raw Apify payloads,
credentials, run IDs, Telegram metadata, or local runtime state.
"""
from __future__ import annotations

import json
import re
import shutil
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path('/opt/data/hermes-content/tiktok')
REPO = Path('/opt/data/repos/tiktok-ideas-dashboard')
OUT = REPO / 'data' / 'latest.json'
PUBLIC_IDEAS = REPO / 'data' / 'ideas'
MT = ZoneInfo('America/Denver')


def read_text(path: Path) -> str:
    return path.read_text(encoding='utf-8') if path.exists() else ''


def latest_file(pattern: str, base: Path) -> Path | None:
    files = list(base.glob(pattern))
    if not files:
        return None
    def key(path: Path):
        m = re.match(r'(\d{4}-\d{2}-\d{2})', path.name)
        return (m.group(1) if m else '', path.stat().st_mtime)
    return sorted(files, key=key, reverse=True)[0]


def clean(s: str) -> str:
    return re.sub(r'\s+', ' ', (s or '').strip())


def idea_from_chunk(title: str, body: str) -> dict:
    tags_line = re.search(r'`([^`]+)`', body)
    tags = [t.strip() for t in re.split(r'\s*\+\s*|\s*/\s*', tags_line.group(1))] if tags_line else []

    def field(name: str) -> str:
        m = re.search(rf'- \*\*{re.escape(name)}:\*\*\s*(.*?)(?=\n- \*\*|\n\*\*[^\n]+\*\*\s*`|\n## |\n---\n|\Z)', body, re.S)
        return clean(m.group(1).strip().strip('"')) if m else ''

    return {
        'title': clean(title),
        'tags': tags,
        'about': field("What it's about"),
        'evidence': field('Evidence'),
        'onScreenTitle': field('On-screen title'),
        'spokenHook': field('Spoken hook'),
        'contentType': field('Content type'),
        'why': field('Why this should work'),
    }


def parse_ideas(markdown: str) -> list[dict]:
    ideas = []

    # Older briefs used explicit headings like "## Idea 1: Title".
    chunks = re.split(r'\n## Idea\s+\d+:\s+', markdown)
    for chunk in chunks[1:]:
        title, _, rest = chunk.partition('\n')
        body = rest.split('\n---\n', 1)[0]
        ideas.append(idea_from_chunk(title, body))

    if ideas:
        return ideas

    # Current Hermes-native briefs put ideas under "## Best ideas for today"
    # as bold title lines followed by the same field bullets.
    section_match = re.search(r'\n## Best ideas for today\n\n(.*?)(?=\n## |\Z)', markdown, re.S)
    if not section_match:
        return []

    section = section_match.group(1).strip()
    pattern = re.compile(r'(?:^|\n)\*\*([^\n*]+?)\*\*[^\n]*\n')
    matches = list(pattern.finditer(section))
    for i, match in enumerate(matches):
        title = match.group(1)
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(section)
        body = section[start:end]
        ideas.append(idea_from_chunk(title, body))

    return ideas


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default


def find_latest_run_dir() -> Path | None:
    tmp = ROOT / 'tmp'
    candidates = [p for p in tmp.glob('*cron-run') if p.is_dir()]
    if not candidates:
        candidates = [p for p in tmp.glob('*run') if p.is_dir()]
    candidates = [p for p in candidates if (p / 'summary.json').exists()]
    return sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)[0] if candidates else None


def load_hook_cache() -> dict:
    return load_json(ROOT / 'data' / 'tiktok-hooks-cache.json', {})


def post_dates(create_time_iso: str) -> tuple[str, str]:
    """Return (mountain_date, utc_date) for a TikTok createTimeISO string."""
    if not create_time_iso:
        return '', ''
    utc_date = create_time_iso[:10]
    try:
        dt = datetime.fromisoformat(create_time_iso.replace('Z', '+00:00'))
        return dt.astimezone(MT).date().isoformat(), utc_date
    except Exception:
        return utc_date, utc_date


def enrich_items(items: list[dict], cache_section: dict) -> list[dict]:
    enriched = []
    for item in items:
        vid = str(item.get('id') or '')
        cached = cache_section.get(vid, {}) if isinstance(cache_section, dict) else {}
        title = cached.get('on_screen_title') or cached.get('onScreenTitle') or ''
        hook = cached.get('spoken_hook') or cached.get('spokenHook') or ''
        title = '' if title in {'—', 'NEEDS_VISION_OCR'} else title
        hook = '' if hook == '—' else hook
        mountain_date, utc_date = post_dates(item.get('createTimeISO') or '')
        enriched.append({
            'id': vid,
            'creator': item.get('creator'),
            'date': mountain_date,
            'postDateMountain': mountain_date,
            'postDateUtc': utc_date,
            'createTimeISO': item.get('createTimeISO') or '',
            'text': clean(item.get('text', '')),
            'topic': clean(title or item.get('text', '')),
            'onScreenTitle': clean(title),
            'spokenHook': clean(hook),
            'cacheHit': bool(cached),
            'hasExtractedTitle': bool(clean(title)),
            'hasExtractedSpokenHook': bool(clean(hook)),
            'playCount': item.get('playCount'),
            'diggCount': item.get('diggCount'),
            'commentCount': item.get('commentCount'),
            'shareCount': item.get('shareCount'),
            'collectCount': item.get('collectCount'),
            'webVideoUrl': item.get('webVideoUrl'),
            'coverUrl': item.get('coverUrl'),
            'subtitleCount': item.get('subtitleCount'),
            'isSponsored': bool(item.get('isSponsored') or item.get('isAd')),
        })
    return enriched


def parse_performance(markdown: str, braydon_items: list[dict], braydon_cache: dict) -> list[dict]:
    notes = []
    perf_match = re.search(r'### Braydon performance snapshot\n\n(.*?)(?=\n### |\n---\n|\Z)', markdown, re.S)
    if perf_match:
        for line in perf_match.group(1).splitlines():
            line = line.strip('- ').strip()
            if line:
                title = re.sub(r'^\*\*(.*?):\*\*.*$', r'\1', line)
                notes.append({'title': title[:80], 'detail': clean(re.sub(r'\*\*', '', line))})
    for item in sorted(braydon_items, key=lambda x: x.get('playCount') or 0, reverse=True)[:5]:
        cached = braydon_cache.get(str(item.get('id')), {})
        notes.append({
            'title': cached.get('on_screen_title') or clean(item.get('text', ''))[:70] or 'Recent post',
            'detail': f"{item.get('playCount', 0):,} views · {item.get('collectCount', 0):,} saves · {item.get('shareCount', 0):,} shares",
        })
    return notes[:10]


def parse_news(markdown: str) -> list[dict]:
    news = []
    m = re.search(r'### Early-catch opportunities\n\n(.*?)(?=\n---\n|\n## |\Z)', markdown, re.S)
    if m:
        for line in m.group(1).splitlines():
            line = line.strip()
            if line.startswith('- '):
                text = re.sub(r'\*\*', '', line[2:])
                status = text.split(':', 1)[0][:60]
                news.append({'status': status, 'text': clean(text), 'date': ''})
    return news[:12]


def coverage_stats(summary: dict, competitors: list[dict], scan_date: str = '') -> dict:
    handles = sorted({x.get('creator') for x in competitors if x.get('creator')})
    title_count = sum(1 for x in competitors if x.get('onScreenTitle'))
    hook_count = sum(1 for x in competitors if x.get('spokenHook'))
    total = len(competitors)
    recent = []
    try:
        anchor = date.fromisoformat(scan_date)
        for item in competitors:
            if not item.get('date'):
                continue
            age = (anchor - date.fromisoformat(item['date'])).days
            if 0 <= age <= 10:
                recent.append(item)
    except Exception:
        recent = []
    recent_total = len(recent)
    recent_title_count = sum(1 for x in recent if x.get('onScreenTitle'))
    recent_hook_count = sum(1 for x in recent if x.get('spokenHook'))
    recent_complete_count = sum(1 for x in recent if x.get('onScreenTitle') and x.get('spokenHook'))
    cache_hits = sum(1 for x in competitors if x.get('cacheHit'))
    cache_misses = total - cache_hits
    recent_cache_hits = sum(1 for x in recent if x.get('cacheHit'))
    summary_new_ids = {str(x) for x in (summary.get('new_competitor_ids') or summary.get('newCompetitorIds') or [])}
    if summary_new_ids:
        new_items = [x for x in competitors if str(x.get('id') or '') in summary_new_ids]
    else:
        # Backward-compatible fallback for older run artifacts: uncached items are
        # the closest public proxy for posts newly discovered by this run. Future
        # run summaries should write new_competitor_ids before hook extraction so
        # successful extraction does not hide that a post was new.
        new_items = [x for x in competitors if not x.get('cacheHit')]
    new_total = len(new_items)
    new_title_count = sum(1 for x in new_items if x.get('onScreenTitle'))
    new_hook_count = sum(1 for x in new_items if x.get('spokenHook'))
    new_complete_count = sum(1 for x in new_items if x.get('onScreenTitle') and x.get('spokenHook'))
    source_signals = sum(1 for x in recent if (x.get('playCount') or 0) >= 10000)
    monitoring_signals = sum(1 for x in recent if 2000 <= (x.get('playCount') or 0) < 10000)
    summary_handles = summary.get('handles') if isinstance(summary.get('handles'), dict) else None
    summary_covered = summary.get('covered')
    if summary_handles:
        covered_handles = sorted(summary_handles.keys())
    elif isinstance(summary_covered, list):
        covered_handles = summary_covered
    else:
        covered_handles = handles
    summary_missing = summary.get('missing')
    missing_handles = summary_missing if isinstance(summary_missing, list) else []
    return {
        'competitorPosts': summary.get('competitor_count') or total,
        'handlesCovered': len(covered_handles),
        'coveredHandles': covered_handles,
        'missingHandles': missing_handles,
        'titleCoverage': f'{title_count}/{total}',
        'spokenHookCoverage': f'{hook_count}/{total}',
        'recentWindowDays': 10,
        'recentCompetitorPosts': recent_total,
        'recentTitleCoverage': f'{recent_title_count}/{recent_total}' if recent_total else '0/0',
        'recentSpokenHookCoverage': f'{recent_hook_count}/{recent_total}' if recent_total else '0/0',
        'recentCompleteHookCoverage': f'{recent_complete_count}/{recent_total}' if recent_total else '0/0',
        'newCompetitorPosts': new_total,
        'newTitleCoverage': f'{new_title_count}/{new_total}' if new_total else '0/0',
        'newSpokenHookCoverage': f'{new_hook_count}/{new_total}' if new_total else '0/0',
        'newCompleteHookCoverage': f'{new_complete_count}/{new_total}' if new_total else '0/0',
        'cacheHits': cache_hits,
        'cacheMisses': cache_misses,
        'cacheCoverage': f'{cache_hits}/{total}',
        'recentCacheCoverage': f'{recent_cache_hits}/{recent_total}' if recent_total else '0/0',
        'sourceIdeaSignals': source_signals,
        'monitoringSignals': monitoring_signals,
    }



def strip_md(s: str) -> str:
    s = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'\1', s or '')
    s = re.sub(r'[`*_#>]', '', s)
    return clean(s)


def section_between(markdown: str, heading_regex: str, stop_regex: str = r'\n## ') -> str:
    m = re.search(heading_regex + r'\n\n?(.*?)(?=' + stop_regex + r'|\Z)', markdown, re.S | re.I)
    return m.group(1).strip() if m else ''


def top_context(markdown: str) -> dict:
    # Capture the human strategist read near the top before REVISION/Idea/Research sections.
    title_end = re.search(r'\n# [^\n]+\n', markdown)
    start = title_end.end() if title_end else 0
    end_match = re.search(r'\n## (REVISION|SHOOTING|Idea\s+\d+|Research Notes|Bullet-Point Scripts)', markdown[start:], re.I)
    end = start + end_match.start() if end_match else min(len(markdown), start + 5000)
    block = markdown[start:end].strip('-\n ')
    strategist = ''
    posting_order = ''
    m = re.search(r'\*\*Strategist read\.\*\*\s*(.*?)(?=\n\n\*\*|\n\n---|\Z)', block, re.S)
    if m:
        strategist = clean(m.group(1))
    po = re.search(r'\*\*Recommended posting order:\*\*\s*(.*?)(?=\n\n---|\n\n## |\Z)', block, re.S)
    if po:
        posting_order = po.group(1).strip()
    today = re.search(r"\*\*Today's [^\n]+?\*\*\s*(.*?)(?=\n\n\*\*Recommended posting order|\n\n---|\Z)", block, re.S)
    return {
        'introMarkdown': block,
        'strategistRead': strategist or strip_md(block.split('\n\n')[0] if block else ''),
        'postingOrderMarkdown': posting_order,
        'todaySummaryMarkdown': today.group(1).strip() if today else '',
    }


def parse_bullets(markdown: str) -> list[str]:
    items = []
    for line in (markdown or '').splitlines():
        line = line.strip()
        if line.startswith('- '):
            items.append(clean(line[2:]))
        elif re.match(r'^\d+\.\s+', line):
            items.append(clean(re.sub(r'^\d+\.\s+', '', line)))
    return items


def parse_sources(markdown: str) -> list[dict]:
    out = []
    src = section_between(markdown, r'\n## Sources', stop_regex=r'\n## ')
    for label, url in re.findall(r'\[([^\]]+)\]\((https?://[^)]+)\)', src):
        out.append({'label': clean(label), 'url': url})
    return out[:40]


def parse_shooting(markdown: str) -> list[dict]:
    cards = []
    pattern = re.compile(r'\n## SHOOTING:\s*([^\n]+)\n\n(.*?)(?=\n## |\Z)', re.S | re.I)
    for m in pattern.finditer(markdown):
        body = m.group(2).strip()
        def bold_field(name):
            mm = re.search(rf'\*\*{re.escape(name)}:\*\*\s*(.*?)(?=\n\n\*\*|\n\n### |\n\n## |\Z)', body, re.S | re.I)
            return clean(mm.group(1)) if mm else ''
        cards.append({
            'title': clean(m.group(1)),
            'summary': strip_md(body.split('\n\n', 1)[0]),
            'onScreenTitle': bold_field('On-screen title'),
            'spokenHook': bold_field('Spoken hook (0-3s)') or bold_field('Spoken hook'),
            'structureMarkdown': body,
        })
    return cards


def parse_revision(markdown: str) -> dict:
    body = section_between(markdown, r'\n## REVISION[^\n]*', stop_regex=r'\n## (SHOOTING|Idea\s+\d+|Research Notes|Bullet-Point Scripts|Sources)')
    if not body:
        return {}
    return {'markdown': body, 'bullets': parse_bullets(body), 'summary': strip_md(body.split('\n\n')[0])}


def parse_brief_sections(markdown: str) -> dict:
    top = top_context(markdown)
    research = section_between(markdown, r'\n## Research Notes', stop_regex=r'\n## (Bullet-Point Scripts|Sources)')
    why = section_between(markdown, r'\n## Why [^\n]+', stop_regex=r'\n## (Research Notes|Bullet-Point Scripts|Sources)')
    scripts = section_between(markdown, r'\n## Bullet-Point Scripts', stop_regex=r'\n## Sources')
    return {
        **top,
        'revision': parse_revision(markdown),
        'shooting': parse_shooting(markdown),
        'whyMarkdown': why,
        'researchMarkdown': research,
        'scriptsMarkdown': scripts,
        'sources': parse_sources(markdown),
    }



def sync_idea_markdown_archive() -> list[dict]:
    """Copy raw daily idea markdown files into the public dashboard repo.

    Braydon explicitly approved publishing the raw historical MD files to the
    public GitHub Pages dashboard repo on 2026-05-18 so the dashboard can treat
    the idea-folder archive as its source-of-truth data layer.
    """
    src_dir = ROOT / 'ideas'
    PUBLIC_IDEAS.mkdir(parents=True, exist_ok=True)
    src_files = sorted(src_dir.glob('*.md'), key=lambda p: p.name)
    src_names = {p.name for p in src_files}
    for stale in PUBLIC_IDEAS.glob('*.md'):
        if stale.name not in src_names:
            stale.unlink()
    archive = []
    for src in src_files:
        dst = PUBLIC_IDEAS / src.name
        shutil.copy2(src, dst)
        m = re.match(r'(\d{4}-\d{2}-\d{2})', src.name)
        archive.append({
            'date': m.group(1) if m else '',
            'file': src.name,
            'path': f'data/ideas/{src.name}',
            'bytes': src.stat().st_size,
            'updatedAt': datetime.fromtimestamp(src.stat().st_mtime, timezone.utc).isoformat(),
        })
    archive.sort(key=lambda x: (x['date'], x['file']), reverse=True)
    (PUBLIC_IDEAS / 'index.json').write_text(json.dumps({
        'generatedAt': datetime.now(timezone.utc).isoformat(),
        'count': len(archive),
        'files': archive,
    }, indent=2) + '\n')
    return archive


def main() -> int:
    idea_archive = sync_idea_markdown_archive()
    idea_path = latest_file('*-tiktok-ideas.md', ROOT / 'ideas')
    if not idea_path:
        raise SystemExit('No TikTok idea file found')
    markdown = read_text(idea_path)
    run_dir = find_latest_run_dir()
    summary = load_json(run_dir / 'summary.json', {}) if run_dir else {}
    competitor_raw = load_json(run_dir / 'competitors_compact.json', []) if run_dir else []
    braydon_raw = load_json(run_dir / 'braydon_compact.json', []) if run_dir else []
    cache = load_hook_cache()
    competitors = enrich_items(competitor_raw, cache.get('competitors', {}))
    braydon = enrich_items(braydon_raw, cache.get('braydon', {}))
    scan_date = idea_path.name[:10]
    data = {
        'date': scan_date,
        'generatedAt': datetime.fromtimestamp(idea_path.stat().st_mtime, timezone.utc).isoformat(),
        'publishedAt': datetime.now(timezone.utc).isoformat(),
        'sourceIdeaFile': str(idea_path),
        'ideas': parse_ideas(markdown),
        'stats': coverage_stats(summary, competitors, scan_date),
        'competitors': competitors,
        'braydonRecent': braydon,
        'performance': parse_performance(markdown, braydon, cache.get('braydon', {})),
        'news': parse_news(markdown),
        'briefMarkdown': markdown,
        'ideaArchive': idea_archive,
        'briefSections': parse_brief_sections(markdown),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Exported {len(data["ideas"])} ideas, {len(competitors)} competitor posts to {OUT}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
