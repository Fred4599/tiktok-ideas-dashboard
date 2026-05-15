const fmt = new Intl.NumberFormat('en-US');
const get = id => document.getElementById(id);
let state = { latest: null, creator: 'all' };

function escapeHtml(value = '') {
  return String(value).replace(/[&<>"]/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch]));
}
function compact(value, max = 180) {
  const s = String(value || '').replace(/\s+/g, ' ').trim();
  return s.length > max ? `${s.slice(0, max - 1)}…` : s;
}
function metricLine(item) {
  const bits = [];
  if (item.playCount != null) bits.push(`${fmt.format(item.playCount)} views`);
  if (item.diggCount != null) bits.push(`${fmt.format(item.diggCount)} likes`);
  if (item.shareCount != null) bits.push(`${fmt.format(item.shareCount)} shares`);
  if (item.collectCount != null) bits.push(`${fmt.format(item.collectCount)} saves`);
  return bits.join(' · ') || 'metrics n/a';
}
async function loadData() {
  const latest = await fetch('data/latest.json', { cache: 'no-store' }).then(r => r.json());
  return latest;
}
function renderHero() {
  const d = state.latest;
  get('ideaCount').textContent = fmt.format(d.ideas.length);
  get('competitorCount').textContent = fmt.format(d.stats.competitorPosts || d.competitors.length);
  get('coverageCount').textContent = `${fmt.format(d.stats.handlesCovered || 0)}/10`;
  get('latestDate').textContent = d.date;
  get('generatedAt').textContent = `Generated ${new Date(d.generatedAt).toLocaleString()} · title coverage ${d.stats.titleCoverage || 'n/a'} · spoken-hook coverage ${d.stats.spokenHookCoverage || 'n/a'}`;
  get('footerUpdated').textContent = `Published ${new Date(d.publishedAt).toLocaleString()}`;
}
function renderIdeas() {
  get('ideasGrid').innerHTML = state.latest.ideas.map((idea, i) => `
    <article class="idea-card">
      <div class="badge-row"><span class="badge">#${i + 1}</span>${(idea.tags || []).map(t => `<span class="badge">${escapeHtml(t)}</span>`).join('')}</div>
      <h3>${escapeHtml(idea.title)}</h3>
      <p>${escapeHtml(idea.evidence || idea.about || '')}</p>
      <div class="label">On-screen title</div>
      <div class="hook">${escapeHtml(idea.onScreenTitle || '—')}</div>
      <div class="label">Spoken hook</div>
      <div class="hook">${escapeHtml(idea.spokenHook || '—')}</div>
    </article>
  `).join('');
}
function renderCreatorFilter() {
  const creators = ['all', ...Array.from(new Set(state.latest.competitors.map(x => x.creator))).sort()];
  get('creatorFilter').innerHTML = creators.map(c => `<option value="${escapeHtml(c)}">${c === 'all' ? 'All creators' : escapeHtml(c)}</option>`).join('');
  get('creatorFilter').value = state.creator;
  get('creatorFilter').addEventListener('change', e => { state.creator = e.target.value; renderCompetitors(); });
}
function renderCompetitors() {
  let items = state.latest.competitors.slice();
  if (state.creator !== 'all') items = items.filter(x => x.creator === state.creator);
  items.sort((a, b) => (b.playCount || 0) - (a.playCount || 0));
  get('competitorList').innerHTML = items.slice(0, 60).map(item => `
    <article class="feed-item">
      <div class="feed-top"><strong>@${escapeHtml(item.creator)}</strong><span class="metric">${escapeHtml(metricLine(item))}</span></div>
      <div class="meta-line">${escapeHtml(item.date || '')}${item.isSponsored ? ' · sponsored/ad signal' : ''}</div>
      <p>${escapeHtml(compact(item.topic || item.text || '', 230))}</p>
      ${item.onScreenTitle ? `<div class="label">Title</div><div class="hook">${escapeHtml(item.onScreenTitle)}</div>` : ''}
      ${item.spokenHook ? `<div class="label">Hook</div><div class="hook">${escapeHtml(item.spokenHook)}</div>` : ''}
      ${item.webVideoUrl ? `<a href="${escapeHtml(item.webVideoUrl)}" target="_blank" rel="noopener">Open TikTok →</a>` : ''}
    </article>
  `).join('') || '<p>No competitor items found for this filter.</p>';
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
function renderBrief() {
  const brief = state.latest.briefMarkdown || '';
  get('briefMarkdown').innerHTML = escapeHtml(brief.slice(0, 9000));
}
function render() {
  renderHero();
  renderIdeas();
  renderCreatorFilter();
  renderCompetitors();
  renderPerformance();
  renderNews();
  renderBrief();
}
loadData().then(latest => { state.latest = latest; render(); }).catch(err => {
  console.error(err);
  document.body.insertAdjacentHTML('afterbegin', `<pre style="color:white;padding:20px">Failed to load dashboard data: ${escapeHtml(err.message)}</pre>`);
});
