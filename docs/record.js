'use strict';
let capture = null, recorder = null, previewURL = null;
const start = document.getElementById('startRecording');
const stop = document.getElementById('stopRecording');
const status = document.getElementById('captureStatus');
start.onclick = async () => {
  if (!navigator.mediaDevices?.getDisplayMedia || !window.MediaRecorder) {
    status.textContent = 'Open this page through http://localhost:8700 in Chrome or Edge to record.'; return;
  }
  start.disabled = true;
  try {
    capture = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: false });
    const mime = ['video/mp4', 'video/webm;codecs=vp9', 'video/webm;codecs=vp8', 'video/webm'].find(t => MediaRecorder.isTypeSupported(t));
    if (!mime) throw new Error('No supported encoder');
    const parts = []; recorder = new MediaRecorder(capture, { mimeType: mime, videoBitsPerSecond: 2500000 });
    recorder.ondataavailable = event => { if (event.data.size) parts.push(event.data); };
    recorder.onstop = () => {
      const url = URL.createObjectURL(new Blob(parts, { type: mime }));
      const link = document.createElement('a'); link.href = url;
      link.download = 'market-demo.' + (mime.startsWith('video/mp4') ? 'mp4' : 'webm'); link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      capture.getTracks().forEach(t => t.stop());start.disabled = false;stop.disabled = true;
      status.textContent = 'Recording downloaded. Preview it below before adding it to the repository.';
    };
    recorder.onerror = () => { capture.getTracks().forEach(t => t.stop());start.disabled = false;stop.disabled = true;status.textContent = 'Recording failed; try another supported browser.'; };
    capture.getVideoTracks()[0].onended = () => { if (recorder.state === 'recording') recorder.stop(); };
    recorder.start(1000);stop.disabled = false;
    status.textContent = 'Recording the selected tab. Continue shopping there, then return here to stop.';
  } catch (error) {
    capture?.getTracks().forEach(t => t.stop());start.disabled = false;
    status.textContent = 'Recording did not start. Select a tab and allow browser screen sharing to record.';
  }
};
stop.onclick = () => { if (recorder?.state === 'recording') recorder.stop(); };
document.getElementById('previewFile').onchange = event => {
  const file = event.target.files[0]; if (!file) return;
  if (previewURL) URL.revokeObjectURL(previewURL);
  previewURL = URL.createObjectURL(file);
  const video = document.getElementById('preview');video.src = previewURL;video.hidden = false;
};
