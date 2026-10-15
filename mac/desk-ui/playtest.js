/* Standalone recorder: never navigate this tab while sharing or holding an unsent clip. */
const $ = (id) => document.getElementById(id) || pip?.document.getElementById(id);
const clock = () => performance.now() / 1000;
const mmss = (n) => Math.floor(Math.max(0, n) / 60) + ':' + String(Math.floor(Math.max(0, n) % 60)).padStart(2, '0');
const entries = [];
let session = null, clip = null, starting = false, finishing = false, pip = null, deskAvailable = true;
const query = new URLSearchParams(location.search);
let saved = {};
try { saved = JSON.parse(localStorage.getItem('playtest-laptop') || '{}') || {}; } catch { /* Ignore stale settings. */ }
$('captureGame').value = query.get('game') || saved.game || '';
$('gameUrl').value = query.get('url') || saved.url || '';
$('lookback').value = Number.isFinite(saved.lookback) ? Math.max(0, Math.min(30, saved.lookback)) : 10;
$('lookback').oninput = () => { $('lookbackValue').textContent = $('lookback').value + ' seconds' + (+$('lookback').value === 10 ? ' · suggested' : ''); };
$('lookback').oninput();

function error(message = '') { $('captureError').textContent = message; $('captureError').hidden = !message; }
function settings() {
  const game = $('captureGame').value.trim().replace(/\s+/g, ' '), raw = $('gameUrl').value.trim();
  if (!game) throw new Error('Choose a game or type a new name first.');
  let url = '';
  if (raw) {
    try {
      const u = new URL(raw);
      if (!['https:', 'http:'].includes(u.protocol) || u.username || u.password) throw new Error();
      url = u.href;
    } catch { throw new Error('Paste a full http or https game link without a password.'); }
  }
  return { game, url, lookback: +$('lookback').value, mic: $('useMic').checked };
}
$('openGame').onclick = () => {
  try {
    const config = settings();
    if (!config.url) throw new Error('Paste the game link first, or open your game yourself.');
    window.open(config.url, '_blank', 'noopener,noreferrer'); error();
  } catch (e) { error(e.message); }
};

// Each buffer is a COMPLETE MediaRecorder container, including its own header.
// Start a new one every 30 seconds; keep at most 60 seconds unless a clip pins one.
// Overlap avoids missing footage at a rotation. Discarding timeslice blobs would corrupt WebM.
function newBuffer(s) {
  const options = { videoBitsPerSecond: 1500000, audioBitsPerSecond: 96000 };
  const mime = ['video/webm;codecs=vp8,opus', 'video/webm', 'video/mp4'].find((t) => MediaRecorder.isTypeSupported(t));
  if (mime) options.mimeType = mime;
  const recorder = new MediaRecorder(s.stream, options);
  const b = { recorder, start: clock(), chunks: [], size: 0, stopped: false };
  b.ready = new Promise((resolve, reject) => {
    recorder.ondataavailable = (e) => {
      if (e.data.size) { b.chunks.push(e.data); b.size += e.data.size; }
      if (session === s && !s.ending) {
        if (b.size > 100 * 1024 * 1024) {
          if (clip?.buffer === b) finishClip();
          else { stopBuffer(b, false); s.buffers = s.buffers.filter((x) => x !== b); }
        }
        maintainBuffers(s);
      }
    };
    recorder.onstop = () => { b.stopped = true; resolve(new Blob(b.chunks, { type: recorder.mimeType })); b.chunks = []; };
    recorder.onerror = () => { reject(new Error('The browser stopped recording. Please start a new session.')); if (session === s) { error('The browser recorder failed. End this session and start again.'); stopSession(); } };
  });
  // Idle buffers also need a rejection handler.
  b.ready.catch(() => {});
  recorder.start(1000);
  s.buffers.push(b);
  return b;
}
function stopBuffer(b, keep) {
  // ondataavailable precedes onstop. Rotation may see this inactive recorder in between.
  // Its clip owner still needs all chunks until the stop promise resolves.
  if (keep) b.keep = true;
  if (!keep && !b.keep) b.chunks = [];
  if (b.recorder.state !== 'inactive') b.recorder.stop();
  return b.ready;
}
function maintainBuffers(s) {
  if (session !== s || s.ending) return;
  const now = clock();
  s.buffers = s.buffers.filter((b) => {
    if (b === clip?.buffer) return true;
    if (b.recorder.state === 'inactive' || now - b.start > 61) { stopBuffer(b, false); return false; }
    return true;
  });
  const latest = s.buffers[s.buffers.length - 1];
  if (!latest || now - latest.start >= 30) newBuffer(s);
}
function renderSession() {
  if (!session) return;
  const available = Math.min(session.lookback, clock() - Math.min(...session.buffers.map((b) => b.start)));
  $('captureState').textContent = clip ? 'Recording your observation' : available + .2 >= session.lookback ? 'Ready when you spot something' : 'Lookback warming up…';
  $('captureDetail').textContent = (clip ? 'Describe it aloud, then Finish & send.' : Math.floor(available) + 's of ' + session.lookback + 's lookback ready.') + (session.mic ? ' Microphone on.' : ' Microphone off.');
  $('clipTimer').textContent = clip ? mmss(clock() - clip.pressed) : mmss(clock() - session.started);
  $('markClip').textContent = clip ? 'Finish & send' : 'Start clip';
  $('markClip').disabled = finishing || session.ending;
  $('discardClip').disabled = !clip || finishing;
  $('recordDot').classList.toggle('recording', !!clip);
  document.title = (clip ? '● Recording' : 'Session live') + ' · Playtest Demon';
}
$('startSession').onclick = async () => {
  if (starting || session) return;
  let config, display, mic;
  try {
    config = settings(); error();
    if (!navigator.mediaDevices?.getDisplayMedia || !window.MediaRecorder) throw new Error('Open this page in Chrome, Edge, Firefox or Safari on your laptop. Screen capture is not available in this browser.');
    starting = true; $('startSession').disabled = true; $('startSession').textContent = 'Choose what to share…';
    // Call synchronously from the click: browsers require transient user activation.
    display = await navigator.mediaDevices.getDisplayMedia({ video: { width: { ideal: 1280 }, height: { ideal: 720 }, frameRate: { ideal: 20, max: 30 } }, audio: false });
    if (config.mic) mic = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true }, video: false });
    if (!display.getVideoTracks().some((t) => t.readyState === 'live')) throw new Error('Screen sharing ended before the session started. Try again.');
    const s = { ...config, display, micStream: mic, stream: new MediaStream([...display.getVideoTracks(), ...(mic?.getAudioTracks() || [])]), started: clock(), buffers: [], ending: false };
    session = s; newBuffer(s);
    localStorage.setItem('playtest-laptop', JSON.stringify(config));
    $('setup').hidden = true; $('guide').hidden = true; $('session').hidden = false;
    $('sessionGame').textContent = config.game; $('screenPreview').srcObject = display;
    $('floatControls').hidden = !window.documentPictureInPicture;
    display.getVideoTracks()[0].addEventListener('ended', () => { if (session === s && !s.ending) stopSession(); });
    mic?.getAudioTracks()[0]?.addEventListener('ended', () => { if (session === s && !s.ending) { error('Microphone disconnected. The session has ended; any current clip is being sent with the audio captured so far.'); stopSession(); } });
    s.timer = setInterval(() => { maintainBuffers(s); renderSession(); if (clip && clock() - clip.pressed >= 180) finishClip(); }, 500);
    renderSession();
  } catch (e) {
    if (session) await stopSession();
    for (const t of [...(display?.getTracks() || []), ...(mic?.getTracks() || [])]) t.stop();
    error(e.name === 'NotAllowedError' ? 'Sharing or microphone permission was cancelled. Allow access and try again, or uncheck Record my voice for a silent clip.' : e.message);
  } finally { starting = false; $('startSession').disabled = !deskAvailable; $('startSession').textContent = '◉ Start playtest session'; }
};
$('markClip').onclick = () => {
  if (!session || session.ending || finishing) return;
  if (clip) return finishClip();
  maintainBuffers(session);
  const now = clock(), desired = now - session.lookback;
  const buffer = [...session.buffers].reverse().find((b) => b.start <= desired) || session.buffers[0];
  const from = Math.max(buffer.start, desired);
  clip = { buffer, from, pressed: now, config: { game: session.game, url: session.url, lookback: session.lookback } };
  renderSession();
};
async function finishClip() {
  if (!clip || finishing) return;
  const c = clip, end = clock(); clip = null; finishing = true;
  const owner = session;
  try {
    const blob = await stopBuffer(c.buffer, true);
    if (!blob.size) throw new Error('The browser produced an empty clip. Start another clip.');
    const entry = { blob, game: c.config.game, name: 'playtest-' + new Date().toISOString().replace(/[:.]/g, '-') + (blob.type.includes('mp4') ? '.mp4' : '.webm'),
      timing: { start: c.from - c.buffer.start, duration: Math.min(end, c.pressed + 180) - c.from, pressed: c.pressed - c.from, lookback: c.config.lookback, url: c.config.url }, status: 'Waiting to send', busy: false };
    entries.unshift(entry); renderEntries(); send(entry);
  } catch (e) { error(e.message); }
  finally { finishing = false; if (session === owner && owner && !owner.ending) { maintainBuffers(owner); renderSession(); } }
}
$('discardClip').onclick = () => {
  if (!clip || finishing) return;
  const b = clip.buffer; clip = null; stopBuffer(b, false);
  maintainBuffers(session); renderSession();
};
async function stopSession() {
  const s = session;
  if (!s || s.ending) return;
  s.ending = true; clearInterval(s.timer);
  if (clip) await finishClip();
  // If a send was already being prepared, its stop event still owns its buffer.
  for (const b of s.buffers) if (b.recorder.state !== 'inactive') stopBuffer(b, false);
  for (const t of [...s.stream.getTracks(), ...s.display.getTracks()]) t.stop();
  session = null;
  if (pip && !pip.closed) pip.close();
  $('screenPreview').srcObject = null; $('session').hidden = true; $('setup').hidden = false; $('guide').hidden = false;
  document.title = 'Laptop playtest · Playtest Demon';
}
$('endSession').onclick = () => { if (!clip || confirm('Finish and send this clip, then end screen sharing?')) stopSession(); };
$('floatControls').onclick = async () => {
  try {
    if (pip && !pip.closed) { pip.focus(); return; }
    pip = await window.documentPictureInPicture.requestWindow({ width: 430, height: 285 });
    for (const path of ['/app.css', '/playtest.css']) { const link = pip.document.createElement('link'); link.rel = 'stylesheet'; link.href = new URL(path, location.href); pip.document.head.append(link); }
    pip.document.title = 'Playtest Demon controls'; pip.document.body.className = 'pip-body';
    pip.document.addEventListener('keydown', shortcut);
    pip.document.body.append($('captureControls'));
    pip.addEventListener('pagehide', () => { $('controlsHome').append(pip.document.getElementById('captureControls')); pip = null; });
  } catch (e) { error('Could not float controls. Keep this recorder window beside the game. ' + e.message); }
};
function renderEntries() {
  $('sentSection').hidden = !entries.length;
  $('sentClips').replaceChildren(...entries.map((e, i) => {
    const row = document.createElement('article'); row.className = 'sent-clip';
    const info = document.createElement('div'); info.className = 'clip-info';
    const title = document.createElement('b'); title.textContent = e.game + ' · Clip ' + (entries.length - i) + ' · ' + mmss(e.timing.duration);
    const status = document.createElement('small'); status.textContent = e.status; status.setAttribute('role', 'status'); info.append(title, status);
    const actions = document.createElement('div'); actions.className = 'clip-actions';
    if (e.blob) {
      if (!e.busy) {
        const retry = document.createElement('button'); retry.className = 'btn compact'; retry.textContent = 'Retry send'; retry.onclick = () => send(e); actions.append(retry);
      }
      const download = document.createElement('button'); download.className = 'text-button'; download.textContent = 'Download backup';
      download.onclick = () => { const url = URL.createObjectURL(e.blob), a = document.createElement('a'); a.href = url; a.download = e.name; a.click(); setTimeout(() => URL.revokeObjectURL(url), 60000); };
      actions.append(download);
      if (!e.busy) { const discard = document.createElement('button'); discard.className = 'text-button'; discard.textContent = 'Remove'; discard.onclick = () => { if (confirm('Remove this unsent clip? Download a backup first if needed.')) { entries.splice(entries.indexOf(e), 1); renderEntries(); } }; actions.append(discard); }
    } else { const link = document.createElement('a'); link.href = '/#videos'; link.target = '_blank'; link.rel = 'noopener'; link.textContent = 'View in live feed ↗'; actions.append(link); }
    row.append(info, actions); return row;
  }));
}
function send(e) {
  if (e.busy || !e.blob) return;
  e.busy = true; e.status = 'Sending to your local desk…'; renderEntries();
  const xhr = new XMLHttpRequest(); xhr.open('POST', '/api/import'); xhr.timeout = 360000;
  xhr.setRequestHeader('Content-Type', 'application/octet-stream'); xhr.setRequestHeader('X-Platform', 'Browser');
  xhr.setRequestHeader('X-Game', encodeURIComponent(e.game)); xhr.setRequestHeader('X-Filename', encodeURIComponent(e.name));
  xhr.setRequestHeader('X-Capture', encodeURIComponent(JSON.stringify(e.timing)));
  xhr.upload.onprogress = (p) => { e.status = p.lengthComputable && p.loaded < p.total ? 'Sending ' + Math.round(p.loaded / p.total * 100) + '%' : 'Preparing your clip for analysis…'; renderEntries(); };
  xhr.onload = () => {
    e.busy = false; let result;
    try { result = JSON.parse(xhr.responseText); } catch { result = { error: 'The desk returned an unreadable response.' }; }
    if (xhr.status === 200) { e.status = result.duplicate ? 'Already received · no duplicate created' : 'Received · in the analysis queue'; e.blob = null; }
    else e.status = (result.error || 'Transfer failed.') + ' Retry safely, or download a backup (includes untrimmed lookback buffer).';
    renderEntries();
  };
  xhr.onerror = xhr.ontimeout = () => { e.busy = false; e.status = 'Connection interrupted. Keep this tab open and retry safely. Your clip is still here. Backups include the untrimmed buffer.'; renderEntries(); };
  xhr.send(e.blob);
}
function shortcut(e) {
  if (e.altKey && e.shiftKey && e.code === 'KeyC' && !e.repeat && !['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName)) { e.preventDefault(); $('markClip').click(); }
}
document.addEventListener('keydown', shortcut);
window.addEventListener('beforeunload', (e) => { if (session || starting || finishing || entries.some((x) => x.blob)) { e.preventDefault(); e.returnValue = ''; } });
if (!navigator.mediaDevices?.getDisplayMedia || !window.MediaRecorder) {
  $('supportNotice').hidden = false;
  $('supportNotice').textContent = 'Screen recording needs a supported desktop browser. Open this page in Chrome, Edge, Firefox or Safari.';
  $('startSession').disabled = true;
}
fetch('/api/state').then((r) => { if (!r.ok) throw new Error(); return r.json(); }).then((state) => {
  for (const game of state.games || []) { const option = document.createElement('option'); option.value = game; $('captureGames').append(option); }
  if (!state.flags?.tools?.ffmpeg || !state.flags?.tools?.ffprobe) { deskAvailable = false; $('startSession').disabled = true; error('Install ffmpeg on this Mac before recording, then reload this page. Your agent can follow the setup guide.'); }
  else if (!state.flags?.tools?.whisper_model || !state.flags?.tools?.whisper) { $('supportNotice').hidden = false; $('supportNotice').textContent = 'Voice transcription is not set up on this Mac. Clips can be recorded, but the analyst cannot read your spoken instructions until whisper and its model are installed.'; }
}).catch(() => { deskAvailable = false; $('startSession').disabled = true; error('The local desk is unavailable. Open Playtest Demon and reload this page.'); });
