const fmt = new Intl.NumberFormat('en-US');
const get = id => document.getElementById(id);
let state = { latest: null, creator: 'all', signal: 'source' };

function escapeHtml(value = '') {
  return String(value).replace(/[&<>"]/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch]));
}
function compact(value, max = 180) {
  const s = String(value || '').replace(/\s+/g, ' ').trim();
  return s.length > max ? `${s.slice(0, max - 1)}…` : s;
}
function inlineMd(text = '') {
  let s = escapeHtml(text);
  s = s.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  s = s.replace(/`([^`]+)`/g, '<code>$1</code>');
  return s;
}
function mdBlock(markdown = '', maxChars = 6000) {
  const clipped = String(markdown || '').trim().slice(0, maxChars);
  if (!clipped) return '<p class="muted">No notes in today’s brief.</p>';
  const lines = clipped.split(/\n/);
  let html = '';
  let inList = false;
  const closeList = () => { if (inList) { html += '</ul>'; inList = false; } };
  for (const raw of lines) {
    const line = raw.trim();
    if (!line) { closeList(); continue; }
    if (/^---+$/.test(line)) { closeList(); html += '<hr>'; continue; }
    const h = line.match(/^(#{2,4})\s+(.*)$/);
    if (h) { closeList(); const level = Math.min(4, h[1].length + 1); html += `<h${level}>${inlineMd(h[2])}</h${level}>`; continue; }
    const bullet = line.match(/^[-*]\s+(.*)$/) || line.match(/^\d+\.\s+(.*)$/);
    if (bullet) { if (!inList) { html += '<ul>'; inList = true; } html += `<li>${inlineMd(bullet[1])}</li>`; continue; }
    closeList();
    html += `<p>${inlineMd(line)}</p>`;
  }
  closeList();
  return html;
}
function metricLine(item) {
  const bits = [];
  if (item.playCount != null) bits.push(`${fmt.format(item.playCount)} views`);
  if (item.diggCount != null) bits.push(`${fmt.format(item.diggCount)} likes`);
  if (item.shareCount != null) bits.push(`${fmt.format(item.shareCount)} shares`);
  if (item.collectCount != null) bits.push(`${fmt.format(item.collectCount)} saves`);
  return bits.join(' · ') || 'metrics n/a';
}
function daysOld(item) {
  if (!item.date || !state.latest?.date) return null;
  const itemDate = new Date(`${item.date}T00:00:00Z`);
  const scanDate = new Date(`${state.latest.date}T00:00:00Z`);
  if (Number.isNaN(itemDate.getTime()) || Number.isNaN(scanDate.getTime())) return null;
  return Math.round((scanDate - itemDate) / 86400000);
}
function recentWindowItems(items, maxDays = 10) {
  return items.filter(item => {
    const age = daysOld(item);
    return age !== null && age >= 0 && age <= maxDays;
  });
}
function signalBadge(item) {
  const views = item.playCount || 0;
  const age = daysOld(item);
  if (age === null) return 'date unknown';
  if (views >= 10000) return 'source idea signal · 10K+';
  if (views >= 2000) return 'monitoring signal · 2K+';
  return 'recent post';
}
async function loadData() {
  return fetch(`data/latest.json?v=${Date.now()}`, { cache: 'no-store' }).then(r => r.json());
}
function renderHero() {
  const d = state.latest;
  const sections = d.briefSections || {};
  const newPosts = d.stats.newCompetitorPosts ?? d.stats.cacheMisses ?? 0;
  get('ideaCount').textContent = fmt.format(d.ideas.length);
  get('competitorCount').textContent = fmt.format(d.stats.handlesCovered || new Set((d.competitors || []).map(x => x.creator)).size || 0);
  get('coverageCount').textContent = d.stats.recentCompleteHookCoverage || d.stats.newCompleteHookCoverage || 'n/a';
  get('latestDate').textContent = d.date;
  get('generatedAt').textContent = `Generated ${new Date(d.generatedAt).toLocaleString()} · ${newPosts} new competitor posts · recent title+hook ${d.stats.recentCompleteHookCoverage || 'n/a'} · ${fmt.format(d.stats.sourceIdeaSignals || 0)} source signals`;
  get('footerUpdated').textContent = `Published ${new Date(d.publishedAt).toLocaleString()}`;
  const heroRead = (sections.strategistRead && sections.strategistRead.length > 60) ? sections.strategistRead : compact(sections.introMarkdown || state.latest.briefMarkdown || '', 900);
  get('strategistRead').innerHTML = heroRead ? inlineMd(heroRead) : 'Latest brief loaded. Scroll for today’s ideas, performance, competitor research, and news.';
}
function renderPriorityBrief() {
  const s = state.latest.briefSections || {};
  const blocks = [];
  if (s.revision?.markdown) blocks.push(`<article class="brief-card urgent"><div class="eyebrow">ACTIVE REVISION</div>${mdBlock(s.revision.markdown, 2500)}</article>`);
  if (s.shooting?.length) {
    for (const shoot of s.shooting) {
      blocks.push(`<article class="brief-card shooting"><div class="eyebrow">SHOOTING NOW</div><h3>${escapeHtml(shoot.title)}</h3><p>${escapeHtml(shoot.summary || '')}</p>${shoot.onScreenTitle ? `<div class="label">On-screen title</div><div class="big-hook">${escapeHtml(shoot.onScreenTitle)}</div>` : ''}${shoot.spokenHook ? `<div class="label">Spoken hook</div><div class="big-hook">${escapeHtml(shoot.spokenHook)}</div>` : ''}</article>`);
    }
  }
  if (s.postingOrderMarkdown) blocks.push(`<article class="brief-card"><div class="eyebrow">POSTING ORDER</div>${mdBlock(s.postingOrderMarkdown, 2200)}</article>`);
  if (s.todaySummaryMarkdown) blocks.push(`<article class="brief-card"><div class="eyebrow">TODAY’S PLAYS</div>${mdBlock(s.todaySummaryMarkdown, 2000)}</article>`);
  get('priorityBrief').innerHTML = blocks.join('') || `<article class="brief-card"><div class="eyebrow">DAILY BRIEF</div><p>${escapeHtml(compact(state.latest.briefMarkdown || '', 500))}</p></article>`;
}
function renderIdeas() {
  get('ideasGrid').innerHTML = state.latest.ideas.map((idea, i) => `
    <article class="idea-card">
      <div class="badge-row"><span class="badge">#${i + 1}</span>${(idea.tags || []).map(t => `<span class="badge">${escapeHtml(t)}</span>`).join('')}</div>
      <h3>${escapeHtml(idea.title)}</h3>
      <p>${escapeHtml(idea.evidence || idea.about || '')}</p>
      ${idea.about ? `<div class="label">What it’s about</div><div class="hook">${escapeHtml(idea.about)}</div>` : ''}
      <div class="label">On-screen title</div>
      <div class="hook">${escapeHtml(idea.onScreenTitle || '—')}</div>
      <div class="label">Spoken hook</div>
      <div class="hook">${escapeHtml(idea.spokenHook || '—')}</div>
      ${idea.why ? `<div class="label">Why it should work</div><div class="hook">${escapeHtml(idea.why)}</div>` : ''}
    </article>
  `).join('');
}
function renderFilters() {
  const creators = ['all', ...Array.from(new Set(state.latest.competitors.map(x => x.creator))).filter(Boolean).sort()];
  get('creatorFilter').innerHTML = creators.map(c => `<option value="${escapeHtml(c)}">${c === 'all' ? 'All creators' : escapeHtml(c)}</option>`).join('');
  get('creatorFilter').value = state.creator;
  get('creatorFilter').onchange = e => { state.creator = e.target.value; renderCompetitors(); };
  const signalOptions = [['source', 'Doing well · 10K+'], ['monitor', 'Monitoring · 2K-10K'], ['all', 'All recent posts'], ['low', 'Under 2K']];
  get('signalFilter').innerHTML = signalOptions.map(([value, label]) => `<option value="${value}">${label}</option>`).join('');
  get('signalFilter').value = state.signal;
  get('signalFilter').onchange = e => { state.signal = e.target.value; renderCompetitors(); };
}
function passesSignalFilter(item) {
  const views = item.playCount || 0;
  if (state.signal === 'source') return views >= 10000;
  if (state.signal === 'monitor') return views >= 2000 && views < 10000;
  if (state.signal === 'low') return views < 2000;
  return true;
}
function renderCompetitors() {
  let items = state.latest.competitors.slice();
  if (state.creator !== 'all') items = items.filter(x => x.creator === state.creator);
  const recentItems = recentWindowItems(items, 10).filter(passesSignalFilter);
  recentItems.sort((a, b) => {
    if (state.signal !== 'all') return (b.playCount || 0) - (a.playCount || 0) || String(b.date || '').localeCompare(String(a.date || ''));
    const dateDiff = String(b.date || '').localeCompare(String(a.date || ''));
    return dateDiff || ((b.playCount || 0) - (a.playCount || 0));
  });
  get('competitorList').innerHTML = recentItems.slice(0, 60).map(item => {
    const age = daysOld(item);
    const badge = signalBadge(item);
    const badgeClass = (item.playCount || 0) >= 10000 ? 'signal-badge source' : ((item.playCount || 0) >= 2000 ? 'signal-badge monitor' : 'signal-badge');
    return `
    <article class="feed-item">
      <div class="feed-top"><strong>@${escapeHtml(item.creator)}</strong><span class="metric">${escapeHtml(metricLine(item))}</span></div>
      <div class="meta-line">${escapeHtml(item.date || '')}${age !== null ? ` · ${age}d old` : ''}${item.isSponsored ? ' · sponsored/ad signal' : ''}</div>
      <div class="${badgeClass}">${escapeHtml(badge)}</div>
      <p>${escapeHtml(compact(item.topic || item.text || '', 230))}</p>
      ${item.onScreenTitle ? `<div class="label">Title</div><div class="hook">${escapeHtml(item.onScreenTitle)}</div>` : '<div class="label missing">Title not extracted</div>'}
      ${item.spokenHook ? `<div class="label">Hook</div><div class="hook">${escapeHtml(item.spokenHook)}</div>` : '<div class="label missing">Spoken hook not extracted</div>'}
      ${item.webVideoUrl ? `<a href="${escapeHtml(item.webVideoUrl)}" target="_blank" rel="noopener">Open TikTok →</a>` : ''}
    </article>`;
  }).join('') || '<p>No competitor posts match this filter in the last 10 days. Try All recent posts or another creator.</p>';
}
function renderPerformance() {
  const p = state.latest.performance || [];
  get('performanceList').innerHTML = p.map(row => `
    <div class="insight"><strong>${escapeHtml(row.title || row.metric || 'Performance signal')}</strong><span>${escapeHtml(row.detail || row.value || '')}</span></div>
  `).join('') || '<div class="insight"><strong>No performance notes yet</strong><span>The next daily scrape will fill this in.</span></div>';
}
function renderNews() {
  const items = state.latest.news || [];
  get('newsList').innerHTML = items.map(item => `
    <article class="feed-item"><div class="feed-top"><strong>${escapeHtml(item.status || 'News')}</strong><span class="metric">${escapeHtml(item.date || '')}</span></div><p>${escapeHtml(item.text || item.title || '')}</p></article>
  `).join('') || '<p>No early-catch items extracted yet.</p>';
}
function renderResearchFromBrief() {
  const s = state.latest.briefSections || {};
  get('researchBrief').innerHTML = mdBlock(s.researchMarkdown || s.whyMarkdown || '', 9000);
  get('sourcesList').innerHTML = (s.sources || []).map(src => `<a class="source-link" href="${escapeHtml(src.url)}" target="_blank" rel="noopener">${escapeHtml(src.label)}</a>`).join('') || '<span class="muted">No source links parsed from this brief.</span>';
}
function renderBrief() {
  const brief = state.latest.briefMarkdown || '';
  get('briefMarkdown').innerHTML = mdBlock(brief, 50000);
}
function renderWarnings() {
  const d = state.latest;
  const missing = d.stats.missingHandles || [];
  const covered = d.stats.coveredHandles || [];
  const warnings = [];
  if (covered.length && covered.length < 10) warnings.push(`Competitor scan is partial: ${covered.length}/10 handles covered${missing.length ? `; missing ${missing.join(', ')}` : ''}.`);
  if ((d.stats.recentSpokenHookCoverage || '').startsWith('0/')) warnings.push('Recent competitor spoken-hook coverage is 0. Treat competitor cards as performance/caption signals unless hooks are shown.');
  get('warnings').innerHTML = warnings.map(w => `<div class="warning">${escapeHtml(w)}</div>`).join('');
}
function render() {
  renderHero();
  renderWarnings();
  renderPriorityBrief();
  renderIdeas();
  renderFilters();
  renderCompetitors();
  renderPerformance();
  renderNews();
  renderResearchFromBrief();
  renderBrief();
}
loadData().then(latest => { state.latest = latest; render(); }).catch(err => {
  console.error(err);
  document.body.insertAdjacentHTML('afterbegin', `<pre style="color:white;padding:20px">Failed to load dashboard data: ${escapeHtml(err.message)}</pre>`);
});
