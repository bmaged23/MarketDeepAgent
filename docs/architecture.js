'use strict';
const map = document.getElementById('map');
let paused = false;
function inspectMap() {
  const doc = map.contentDocument;
  if (!doc) return;
  for (const node of doc.querySelectorAll('.node')) {
    const inspect = () => { document.getElementById('detail').textContent = node.dataset.detail; };
    node.addEventListener('mouseenter', inspect);
    node.addEventListener('focus', inspect);
  }
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) setPaused(true);
}
function setPaused(value) {
  const doc = map.contentDocument;
  if (!doc) return;
  paused = value;
  const svg = doc.documentElement;
  if (paused) svg.pauseAnimations(); else svg.unpauseAnimations();
  for (const flow of doc.querySelectorAll('.flow')) flow.style.animationPlayState = paused ? 'paused' : 'running';
  document.getElementById('motion').textContent = paused ? 'Resume animation' : 'Pause animation';
}
map.addEventListener('load', inspectMap);
document.getElementById('motion').addEventListener('click', () => setPaused(!paused));
