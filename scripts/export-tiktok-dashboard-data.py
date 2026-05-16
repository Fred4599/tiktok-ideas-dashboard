#!/usr/bin/env python3
"""Export sanitized TikTok idea dashboard data from Hermes local workspace.

Keeps only public/operational summary fields. Does not publish raw Apify payloads,
credentials, run IDs, Telegram metadata, or local runtime state.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path('/opt/data/hermes-content/tiktok')
REPO = Path('/opt/data/repos/tiktok-ideas-dashboard')
OUT = REPO / 'data' / 'latest.json'


def read_text(path: Path) -> str:
    return path.read_text(encoding='utf-8') if path.exists() else ''


def latest_file(pattern: str, base: Path) -> Path | None:
    files = sorted(base.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def clean(s: str) -> str:
    return re.sub(r'\s+', ' ', (s or '').strip())


def parse_ideas(markdown: str) -> list[dict]:
    chunks = re.split(r'\n## Idea\s+\d+:\s+', markdown)
    ideas = []
    for chunk in chunks[1:]:
        title, _, rest = chunk.partition('\n')
        body = rest.split('\n---\n', 1)[0]
        tags_line = re.search(r'`([^`]+)`', body)
        tags = [t.strip() for t in re.split(r'\s*\+\s*|\s*/\s*', tags_line.group(1))] if tags_line else []
        def field(name: str) -> str:
            m = re.search(rf'- \*\*{re.escape(name)}:\*\*\s*(.*?)(?=\n- \*\*|\n\|---|\n---\n|\Z)', body, re.S)
            return clean(m.group(1).strip().strip('"')) if m else ''
        ideas.append({
            'title': clean(title),
            'tags': tags,
            'about': field("What it's about"),
            'evidence': field('Evidence'),
            'onScreenTitle': field('On-screen title'),
            'spokenHook': field('Spoken hook'),
            'contentType': field('Content type'),
            'why': field('Why this should work'),
        })
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


def enrich_items(items: list[dict], cache_section: dict) -> list[dict]:
    enriched = []
    for item in items:
        vid = str(item.get('id') or '')
        cached = cache_section.get(vid, {}) if isinstance(cache_section, dict) else {}
        title = cached.get('on_screen_title') or cached.get('onScreenTitle') or ''
        hook = cached.get('spoken_hook') or cached.get('spokenHook') or ''
        title = '' if title in {'—', 'NEEDS_VISION_OCR'} else title
        hook = '' if hook == '—' else hook
        enriched.append({
            'id': vid,
            'creator': item.get('creator'),
            'date': (item.get('createTimeISO') or '')[:10],
            'text': clean(item.get('text', '')),
            'topic': clean(title or item.get('text', '')),
            'onScreenTitle': clean(title),
            'spokenHook': clean(hook),
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
    source_signals = sum(1 for x in recent if (x.get('playCount') or 0) >= 10000)
    monitoring_signals = sum(1 for x in recent if 2000 <= (x.get('playCount') or 0) < 10000)
    return {
        'competitorPosts': summary.get('competitor_count') or total,
        'handlesCovered': len(summary.get('covered') or handles),
        'coveredHandles': summary.get('covered') or handles,
        'missingHandles': summary.get('missing') or [],
        'titleCoverage': f'{title_count}/{total}',
        'spokenHookCoverage': f'{hook_count}/{total}',
        'recentWindowDays': 10,
        'recentCompetitorPosts': recent_total,
        'recentTitleCoverage': f'{recent_title_count}/{recent_total}' if recent_total else '0/0',
        'recentSpokenHookCoverage': f'{recent_hook_count}/{recent_total}' if recent_total else '0/0',
        'sourceIdeaSignals': source_signals,
        'monitoringSignals': monitoring_signals,
    }


def main() -> int:
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
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Exported {len(data["ideas"])} ideas, {len(competitors)} competitor posts to {OUT}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
