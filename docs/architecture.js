'use strict';
const map = document.getElementById('map');
const views = {
  overview: {file:'architecture.svg',title:'One coordinator. Two specialists.',description:'The browser sends authenticated requests and page context to FastAPI. The customer agent delegates discovery and shopping operations, then returns a grounded reply and allowlisted UI actions.',steps:['Customer + page context → authenticated application','Coordinator → retrieval / cart specialists','Facts + tool results → reply + storefront actions']},
  retrieval: {file:'architecture-retrieval.svg',title:'Retrieve, approve, check — repeat when needed.',description:'Ollama rewrites the request and chooses hybrid discovery, structured SQL selection or both. Approval is batched; the coverage check can generate more subqueries within configured limits.',steps:['Rewrite → query tasks + filters + requested fields','BM25 / BGE–Qdrant → weighted ranking + fresh SQL facts','Batch 0/1 approval → accumulated evidence → coverage','Missing facts → new searches; sufficient → return query-grouped evidence']},
  ordering: {file:'architecture-ordering.svg',title:'An agent can prepare checkout. The customer confirms it.',description:'The cart agent uses customer-bound services. A real browser form provides checkout confirmation; an SQL transaction validates the quote, creates the order and deducts stock exactly once.',steps:['Product references → validated shared SQL cart','Quote snapshot → customer reviews the checkout form','Explicit confirmation → authenticated checkout API','Atomic stock / order / cart transaction → receipt + history']},
  memory: {file:'architecture-memory.svg',title:'Remember the customer without mixing customers.',description:'Conversation history remains in SQL. Optional explicit preferences use a separate Qdrant collection, followed by an authoritative SQL ownership, active-state and version check.',steps:['Request → BGE embedding → owner-filtered vector recall','Candidate memory IDs → SQL verification → bounded prompt','Approved preferences → SQL facts + durable sync jobs','BGE → vector upsert/delete; SQL revocations take effect immediately']},
  indexing: {file:'architecture-indexing.svg',title:'Write once to SQL. Derive both search indexes.',description:'Catalog transactions update SQLite FTS5 and queue vector work. The indexing process encodes current product documents and writes Qdrant points with the same product and category IDs.',steps:['Catalog write → SQL product + transactional FTS triggers','Product revision → durable index job → current document','BGE document embedding → Qdrant upsert/delete','Job results + reconciliation → consistent derived index']}
};
const tabs = [...document.querySelectorAll('[data-view]')];
let paused = matchMedia('(prefers-reduced-motion: reduce)').matches;
function setPaused(value) {
  paused = value;
  const svg = map.contentDocument?.documentElement;
  if (svg?.pauseAnimations) { if (paused) svg.pauseAnimations(); else svg.unpauseAnimations(); }
  document.getElementById('motion').textContent = paused ? 'Resume animation' : 'Pause animation';
  document.getElementById('motion').setAttribute('aria-pressed', String(paused));
}
function inspectMap() {
  const doc = map.contentDocument;
  if (!doc) return;
  for (const node of doc.querySelectorAll('.node')) {
    const inspect = () => { document.getElementById('detail').textContent = node.dataset.detail; };
    for (const event of ['mouseenter','focus','click']) node.addEventListener(event, inspect);
  }
  setPaused(paused);
}
function selectView(key) {
  const view = views[key];
  if (!view) return;
  for (const tab of tabs) {
    const selected = tab.dataset.view === key;
    tab.setAttribute('aria-selected', String(selected)); tab.tabIndex = selected ? 0 : -1;
  }
  const active = tabs.find(tab => tab.dataset.view === key);
  const label = active.textContent.trim();
  document.getElementById('diagramPanel').setAttribute('aria-labelledby', active.id);
  map.setAttribute('data', 'assets/' + view.file);
  map.setAttribute('aria-label', label + ' architecture diagram');
  document.getElementById('openDiagram').href = 'assets/' + view.file;
  document.getElementById('storyLabel').textContent = label;
  document.getElementById('storyTitle').textContent = view.title;
  document.getElementById('storyDescription').textContent = view.description;
  const steps = document.getElementById('storySteps'); steps.replaceChildren();
  for (const text of view.steps) { const li = document.createElement('li'); li.textContent = text; steps.appendChild(li); }
  document.getElementById('detail').textContent = 'Hover, focus or click a component to inspect this workflow.';
}
for (const [index, tab] of tabs.entries()) {
  tab.addEventListener('click', () => selectView(tab.dataset.view));
  tab.addEventListener('keydown', event => {
    let next;
    if (event.key === 'ArrowRight') next = (index+1)%tabs.length;
    if (event.key === 'ArrowLeft') next = (index+tabs.length-1)%tabs.length;
    if (event.key === 'Home') next = 0;
    if (event.key === 'End') next = tabs.length-1;
    if (next !== undefined) { event.preventDefault(); tabs[next].focus(); selectView(tabs[next].dataset.view); }
  });
}
map.addEventListener('load', inspectMap);
document.getElementById('motion').addEventListener('click', () => setPaused(!paused));
setPaused(paused);
if (map.contentDocument?.documentElement?.tagName === 'svg') inspectMap();
