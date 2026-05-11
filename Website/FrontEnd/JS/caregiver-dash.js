// ── CONFIG ────────────────────────────────────────────────────────────────────
const API_BASE = 'https://localhost:3000';

const token = localStorage.getItem("access_token");

let CAREGIVER_ID = null

if(token){
  const payload = token.split('.')[1]
  const decodedPayload =  JSON.parse(atob(payload))
  CAREGIVER_ID = decodedPayload.rid
}else{
  window.location.href = '../Pages/log_in.html';
}

// Loaded from API
let caregiverData  = null;
let patientData    = [];
let currentPatient = null;
let latestHeartRate = '--';

// ── ALERTS STATE ──────────────────────────────────────────────────────────────
let allAlerts      = [];   // active (unacknowledged)
let resolvedAlerts = [];   // acknowledged
let alertFilter    = 'all';
let resolvedOpen   = false;

// ── TAB SWITCHING ─────────────────────────────────────────────────────────────
function openTab(tabName) {
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));

  const tab = document.getElementById(tabName);
  if (tab) tab.classList.add('active');

  const btn = document.getElementById('btn-' + tabName);
  if (btn) btn.classList.add('active');
}


// ── LOAD CAREGIVER + PATIENTS FROM API ────────────────────────────────────────
async function loadDashboard() {
  try {
    const response = await fetch(`${API_BASE}/caregiver/${CAREGIVER_ID}/patients`);

    if (!response.ok) throw new Error(`Server error: ${response.status}`);

    const data     = await response.json();
    caregiverData  = data.caregiver;
    patientData    = data.patients ?? [];

    renderHeader();
    renderPatientList();
    renderAccountCard();

    const statEl = document.getElementById('stat-patients');
    if (statEl) statEl.textContent = patientData.length;

  } catch (error) {
    console.error('Failed to load dashboard:', error);
    document.getElementById('patient-list').innerHTML =
      '<p class="error-msg">Could not load patients. Make sure the server is running.</p>';
  }
}


// ── LOAD ALERTS FROM API (page load seed) ─────────────────────────────────────
async function loadAlerts() {
  try {
    const res  = await fetch(`${API_BASE}/alert/caregiver/${CAREGIVER_ID}`);
    if (!res.ok) return;
    const data = await res.json();

    allAlerts      = [];
    resolvedAlerts = [];

    data.forEach(a => {
      if (a.acknowledged) {
        resolvedAlerts.push({ ...a, unread: false });
      } else {
        allAlerts.push({ ...a, unread: false });
      }
    });

    renderAlertCards();
    renderResolvedSection();
  } catch (err) {
    console.error('[ALERTS] Failed to load alerts:', err);
  }
}


// ── RENDER HEADER ─────────────────────────────────────────────────────────────
function renderHeader() {
  if (!caregiverData) return;

  const initials = (caregiverData.first_name[0] + caregiverData.last_name[0]).toUpperCase();
  const fullName = caregiverData.first_name + ' ' + caregiverData.last_name;

  document.getElementById('header-avatar').textContent = initials;
  document.getElementById('header-name').textContent   = fullName;
  document.getElementById('welcome-msg').textContent   = 'Welcome back, ' + caregiverData.first_name;
}


// ── RENDER PATIENT LIST ───────────────────────────────────────────────────────
function renderPatientList() {
  const list = document.getElementById('patient-list');
  list.innerHTML = '';

  if (patientData.length === 0) {
    list.innerHTML = '<p class="loading-msg">No patients assigned yet.</p>';
    return;
  }

  patientData.forEach((p, index) => {
    const initials = getInitials(p.first_name, p.last_name);
    const dob      = p.date_of_birth ? formatDate(p.date_of_birth) : 'N/A';

    const card = document.createElement('div');
    card.className = 'patient-card';
    card.onclick   = () => viewPatient(index);

    card.innerHTML =
      '<div class="pc-avatar">' + initials + '</div>' +
      '<div class="pc-info">' +
        '<div class="pc-name">' + p.first_name + ' ' + p.last_name + '</div>' +
        '<div class="pc-meta">' + dob + (p.gender ? ' · ' + p.gender : '') + '</div>' +
      '</div>' +
      '<div class="pc-right">' +
        (p.dementia_stage ? '<span class="stage-tag">' + p.dementia_stage + '</span>' : '') +
        '<span class="chevron">›</span>' +
      '</div>';

    list.appendChild(card);
  });
}


// ── VIEW PATIENT PROFILE ──────────────────────────────────────────────────────
function viewPatient(index) {
  const p = patientData[index];
  currentPatient = p;

  document.getElementById('profile-avatar').textContent = getInitials(p.first_name, p.last_name);
  document.getElementById('profile-name').textContent   = p.first_name + ' ' + p.last_name;

  const stageBadge = document.getElementById('profile-stage-badge');
  stageBadge.textContent = p.dementia_stage || 'Stage Unknown';

  document.getElementById('overview').innerHTML =
    '<div class="detail-card">' +
      detailRow('Date of Birth', p.date_of_birth ? formatDate(p.date_of_birth) : 'N/A') +
      detailRow('Gender',        p.gender        || 'N/A') +
      detailRow('Address',       p.address       || 'N/A') +
    '</div>' +

    '<div class="detail-card" style="padding:20px 24px;margin-bottom:16px">' +
      '<h3 style="margin:0 0 12px;font-size:1rem;opacity:0.7">Heart Rate Monitor</h3>' +
      '<div style="display:flex;align-items:center;gap:16px;margin:8px 0">' +
        '<span id="hr-value" style="font-size:2.5rem;font-weight:700">--</span>' +
        '<span style="opacity:0.5">bpm</span>' +
      '</div>' +
      '<p id="device-connected" style="margin:12px 0 0;font-size:0.85rem;opacity:0.5">No device connected — real-time data will appear here</p>' +
    '</div>'

  document.getElementById('medical').innerHTML =
    '<div class="detail-card">' +
      detailRow('Dementia Stage',  p.dementia_stage  || 'N/A') +
      detailRow('Medical History', p.medical_history ? JSON.stringify(p.medical_history) : 'None recorded') +
    '</div>';

  document.getElementById('contact').innerHTML =
    '<div class="detail-card">' +
      detailRow('Emergency Contact',      p.emergency_contact      || 'N/A') +
      detailRow('Emergency Contact Name', p.emergency_contact_name || 'N/A') +
    '</div>';

  document.querySelectorAll('.ptab-btn').forEach(b => b.classList.remove('active-ptab'));
  document.querySelectorAll('.profile-section').forEach(s => s.classList.remove('active-psection'));
  document.querySelector('.ptab-btn').classList.add('active-ptab');
  document.getElementById('overview').classList.add('active-psection');

  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  document.getElementById('patient-profile').classList.add('active');
}

function closeProfile() {
  currentPatient = null;
  openTab('patients');
}

function showProfileTab(tabId, btnEl) {
  document.querySelectorAll('.profile-section').forEach(s => s.classList.remove('active-psection'));
  document.querySelectorAll('.ptab-btn').forEach(b => b.classList.remove('active-ptab'));
  document.getElementById(tabId).classList.add('active-psection');
  if (btnEl) btnEl.classList.add('active-ptab');
}


// ── ACCOUNT CARD ──────────────────────────────────────────────────────────────
function renderAccountCard() {
  const card = document.getElementById('account-card');
  if (!caregiverData) return;

  card.innerHTML =
    infoRow('Name',            caregiverData.first_name + ' ' + caregiverData.last_name) +
    infoRow('Specialization',  caregiverData.specialization) +
    infoRow('License',         caregiverData.license_number) +
    infoRow('Phone',           caregiverData.phone) +
    infoRow('Experience',      caregiverData.years_experience + ' years') +
    infoRow('Patients Assigned', patientData.length + ' patients');
}


// ── HELPERS ───────────────────────────────────────────────────────────────────
function getInitials(first, last) {
  return ((first?.[0] ?? '') + (last?.[0] ?? '')).toUpperCase();
}

function formatDate(dateStr) {
  if (!dateStr) return 'N/A';
  const d = new Date(dateStr);
  return d.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
}

function detailRow(label, value) {
  return '<div class="detail-row"><span class="detail-lbl">' + label + '</span><span class="detail-val">' + value + '</span></div>';
}

function infoRow(label, value) {
  return '<div class="info-row"><span class="info-lbl">' + label + '</span><span class="info-val">' + (value ?? 'N/A') + '</span></div>';
}


// ── ALERTS ────────────────────────────────────────────────────────────────────

// Called on incoming Socket.IO event — always active (unacknowledged)
function pushAlert(payload) {
  allAlerts.unshift({ ...payload, unread: true });
  renderAlertCards();
  renderResolvedSection();
}

function filterAlerts(type, btn) {
  alertFilter = type;
  document.querySelectorAll('.alerts-filter-btn').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  renderAlertCards();
}

function renderAlertCards() {
  const list  = document.getElementById('alert-card-list');
  const label = document.getElementById('alerts-count-label');
  const badge = document.getElementById('alerts-nav-badge');
  if (!list) return;

  const visible = allAlerts.filter(a => {
    if (alertFilter === 'unread')   return a.unread;
    if (alertFilter === 'critical') return a.severity === 'critical';
    return true;
  });

  const unreadCount = allAlerts.filter(a => a.unread).length;
  badge.style.display = unreadCount ? 'flex' : 'none';
  badge.textContent   = unreadCount;

  const statAlertEl = document.querySelector('.stat-tile--alert .stat-num');
  if (statAlertEl) statAlertEl.textContent = unreadCount || allAlerts.length;

  if (label) label.textContent = visible.length
    ? `${visible.length} active alert${visible.length !== 1 ? 's' : ''}`
    : '';

  if (!visible.length) {
    list.innerHTML = `
      <div class="alerts-empty">
        <div class="alerts-empty__icon">✅</div>
        <div class="alerts-empty__text">No active alerts</div>
      </div>`;
    return;
  }

  list.innerHTML = visible.map(a => `
    <div class="alert-card severity--${a.severity || 'critical'} ${a.unread ? 'unread' : ''}"
         data-id="${a.alertId}">
      <div class="alert-card__bar"></div>
      <div class="alert-card__body">
        <span class="alert-card__icon">🚨</span>
        <div class="alert-card__info">
          <div class="alert-card__header">
            <span class="alert-card__patient">${a.patientName || 'Unknown'}</span>
            <span class="alert-card__type-tag">${(a.eventType || 'fall detected').replace(/_/g, ' ')}</span>
            <span class="alert-card__unread-dot"></span>
          </div>
          <div class="alert-card__desc">Room: ${a.room || '—'}</div>
          <div class="alert-card__meta">${formatAlertTime(a.timestamp)}</div>
        </div>
      </div>
      <div class="alert-card__actions">
        <button class="alert-ack-btn" onclick="acknowledgeAlert(${a.alertId})">
          ✓ Acknowledge
        </button>
        <button class="alert-view-btn secondary"
          ${a.videoUrl ? '' : 'disabled'}
          onclick="openVideoModal(${a.alertId})">
          ${a.videoUrl ? '▶ View Recording' : 'No Recording'}
        </button>
      </div>
    </div>`).join('');
}

// ── ACKNOWLEDGE ───────────────────────────────────────────────────────────────
async function acknowledgeAlert(alertId) {
  try {
    const res = await fetch(`${API_BASE}/alert/${alertId}/acknowledge`, {
      method:  'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ caregiverId: CAREGIVER_ID }),
    });

    if (!res.ok) throw new Error(`Server returned ${res.status}`);

    // Move from active to resolved
    const idx = allAlerts.findIndex(a => String(a.alertId) === String(alertId));
    if (idx !== -1) {
      const [acked] = allAlerts.splice(idx, 1);
      acked.acknowledged   = true;
      acked.acknowledgedAt = new Date().toISOString();
      acked.unread         = false;
      resolvedAlerts.unshift(acked);
    }

    renderAlertCards();
    renderResolvedSection();

    console.log(`[ACK] Alert #${alertId} acknowledged`);
  } catch (err) {
    console.error('[ACK] Failed to acknowledge alert:', err);
  }
}

// ── RESOLVED SECTION ──────────────────────────────────────────────────────────
function renderResolvedSection() {
  let section = document.getElementById('resolved-section');

  // Create section on first render
  if (!section) {
    const container = document.getElementById('alert-card-list')?.parentElement;
    if (!container) return;
    section = document.createElement('div');
    section.id        = 'resolved-section';
    section.className = 'resolved-section';
    container.appendChild(section);
  }

  if (!resolvedAlerts.length) {
    section.innerHTML = '';
    return;
  }

  section.innerHTML = `
    <div class="resolved-toggle" onclick="toggleResolved()">
      <span class="resolved-toggle__label">Resolved</span>
      <span class="resolved-toggle__count">${resolvedAlerts.length}</span>
      <span class="resolved-toggle__chevron ${resolvedOpen ? 'open' : ''}">▼</span>
    </div>
    <div class="resolved-list ${resolvedOpen ? '' : 'hidden'}" id="resolved-list">
      ${resolvedAlerts.map(a => `
        <div class="alert-card alert-card--resolved">
          <div class="alert-card__bar"></div>
          <div class="alert-card__body">
            <span class="alert-card__icon">✅</span>
            <div class="alert-card__info">
              <div class="alert-card__header">
                <span class="alert-card__patient">${a.patientName || 'Unknown'}</span>
                <span class="alert-card__resolved-tag">Resolved</span>
              </div>
              <div class="alert-card__desc">${(a.eventType || 'fall detected').replace(/_/g, ' ')} · Room: ${a.room || '—'}</div>
              <div class="alert-card__meta">${formatAlertTime(a.timestamp)}</div>
              ${a.acknowledgedAt
                ? `<div class="alert-card__ack-meta">Acknowledged ${formatAlertTime(a.acknowledgedAt)}</div>`
                : ''}
            </div>
          </div>
          <div class="alert-card__actions">
            <button class="alert-view-btn secondary"
              ${a.videoUrl ? '' : 'disabled'}
              onclick="openVideoModal(${a.alertId})">
              ${a.videoUrl ? '▶ View Recording' : 'No Recording'}
            </button>
          </div>
        </div>`).join('')}
    </div>`;
}

function toggleResolved() {
  resolvedOpen = !resolvedOpen;
  renderResolvedSection();
}

function formatAlertTime(ts) {
  if (!ts) return '—';
  const d    = new Date(ts);
  const diff = Math.floor((Date.now() - d) / 1000);
  if (diff < 60)    return 'Just now';
  if (diff < 3600)  return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}


// ── VIDEO MODAL ───────────────────────────────────────────────────────────────
function openVideoModal(alertId) {
  // Search both arrays
  const a = [...allAlerts, ...resolvedAlerts].find(x => String(x.alertId) === String(alertId));
  if (!a || !a.videoUrl) return;

  a.unread = false;
  renderAlertCards();

  const overlay  = document.getElementById('video-modal-overlay');
  const player   = document.getElementById('vmodal-player');
  const status   = document.getElementById('vmodal-status');
  const download = document.getElementById('vmodal-download');

  document.getElementById('vmodal-patient').textContent  = a.patientName || 'Unknown';
  document.getElementById('vmodal-subtitle').textContent =
    `${(a.eventType || 'Fall detected').replace(/_/g, ' ')} · ${formatAlertTime(a.timestamp)}`;
  document.getElementById('vmodal-info').innerHTML =
    `<strong>Room:</strong> ${a.room || '—'} &nbsp;|&nbsp;
     <strong>Time:</strong> ${a.timestamp ? new Date(a.timestamp).toLocaleString() : '—'}`;

  download.href     = a.videoUrl;
  download.download = `incident_${alertId}.mp4`;

  status.classList.remove('hidden');
  player.oncanplay = () => status.classList.add('hidden');
  player.onerror   = () => {
    document.getElementById('vmodal-status-text').textContent = 'Could not load recording.';
    status.querySelector('.video-modal__status-icon').textContent = '⚠️';
  };

  player.src = a.videoUrl;
  player.load();
  overlay.classList.remove('hidden');
}

function closeVideoModal() {
  const overlay = document.getElementById('video-modal-overlay');
  const player  = document.getElementById('vmodal-player');
  overlay.classList.add('hidden');
  player.pause();
  player.src = '';
}

document.getElementById('video-modal-overlay')?.addEventListener('click', function(e) {
  if (e.target === this) closeVideoModal();
});

document.addEventListener('keydown', e => {
  if (e.key === 'Escape') closeVideoModal();
});


// ── INIT ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  const dateEl = document.getElementById('today-date');
  if (dateEl) {
    dateEl.textContent = new Date().toLocaleDateString('en-US', {
      weekday: 'long', month: 'long', day: 'numeric'
    });
  }

  loadDashboard();
  loadAlerts();
  openTab('home');

  const socket = io('https://localhost:3000');

  socket.on('connect', () => {
    console.log('Socket connected:', socket.id);
    socket.emit('join-as-caregiver', { caregiverId: CAREGIVER_ID });
  });

  socket.on('connect_error', (err) => console.error('Socket error:', err.message));

  socket.on('heartrate', (value) => {
    latestHeartRate = value;
    const hr_element = document.getElementById('hr-value');
    const device_connection = document.getElementById('device-connected');
    if (hr_element) hr_element.textContent = value;
    if (device_connection) device_connection.textContent = 'Real-time heart rate data from the watch';
  });

  socket.on('fall-alert', (data) => {
    console.log('[ALERT] Fall detected:', data);

    pushAlert({
      alertId:     data.alertId || ('alert-' + Date.now()),
      patientName: data.patientName,
      eventType:   data.eventType,
      room:        data.room,
      timestamp:   data.timestamp,
      videoUrl:    data.videoUrl || null,
      severity:    'critical',
    });

    // Show toast banner
    const banner  = document.getElementById('fall-alert-banner');
    const details = document.getElementById('fall-alert-details');

    details.innerHTML =
      'Patient: <strong>' + data.patientName + '</strong><br>' +
      'Room: <strong>' + data.room + '</strong> · ' +
      'Type: <strong>' + data.eventType + '</strong> · ' +
      new Date(data.timestamp).toLocaleTimeString();

    banner.style.display = 'flex';
  });
});

function dismissAlert() {
  document.getElementById('fall-alert-banner').style.display = 'none';
}