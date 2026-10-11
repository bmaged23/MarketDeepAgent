'use strict';
const tourVideo = document.getElementById('tourVideo');
const videoSection = document.getElementById('videoSection');
const fullscreenButton = document.getElementById('videoFullscreen');
const fullscreenStatus = document.getElementById('fullscreenStatus');
const playButton = document.getElementById('videoPlay');
let expanded = false, previousOverflow = '';
playButton.addEventListener('click', async () => {
  try { await tourVideo.play(); }
  catch { document.getElementById('videoAvailability').textContent = 'Playback could not start. Use the native video controls or Open video directly.'; }
});
tourVideo.addEventListener('play', () => { playButton.hidden = true; });
tourVideo.addEventListener('pause', () => { playButton.hidden = false; });
tourVideo.addEventListener('ended', () => { playButton.hidden = false; });
function expandPlayer() {
  previousOverflow = document.body.style.overflow;
  document.body.style.overflow = 'hidden';
  videoSection.classList.add('expanded-player');
  expanded = true;
  fullscreenButton.textContent = 'Exit fullscreen';
  fullscreenButton.setAttribute('aria-expanded', 'true');
}
function collapsePlayer() {
  videoSection.classList.remove('expanded-player');
  document.body.style.overflow = previousOverflow;
  expanded = false;
  fullscreenButton.textContent = 'Fullscreen video';
  fullscreenButton.setAttribute('aria-expanded', 'false');
  fullscreenStatus.textContent = '';
  fullscreenButton.focus();
}
fullscreenButton.addEventListener('click', async () => {
  if (expanded) {
    if (document.fullscreenElement && document.exitFullscreen) await document.exitFullscreen().catch(() => {});
    if (expanded) collapsePlayer();
    return;
  }
  expandPlayer();
  try {
    if (videoSection.requestFullscreen && document.fullscreenEnabled !== false) await videoSection.requestFullscreen();
    else if (tourVideo.webkitEnterFullscreen) { collapsePlayer();tourVideo.webkitEnterFullscreen(); }
    else fullscreenStatus.textContent = 'Player expanded across the browser window. Press F11 for browser fullscreen, or Esc to exit.';
  } catch {
    fullscreenStatus.textContent = 'Player expanded across the browser window. Press F11 for browser fullscreen, or Esc to exit.';
  }
});
document.addEventListener('fullscreenchange', () => {
  if (!document.fullscreenElement && expanded) collapsePlayer();
});
document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && expanded && !document.fullscreenElement) collapsePlayer();
});
fetch('assets/storefront-tour.mp4', {method: 'HEAD', cache: 'no-store'})
  .then(response => {
    if (!response.ok) throw new Error('Video unavailable');
    videoSection.hidden = false;
    document.getElementById('recordingPending').hidden = true;
    document.getElementById('videoAvailability').textContent = 'Actual storefront recording. Live replies and real UI interactions; long waiting periods trimmed.';
  })
  .catch(() => { document.getElementById('videoAvailability').textContent = 'The customer demo video is unavailable.'; document.getElementById('recordingPending').hidden = false; });
