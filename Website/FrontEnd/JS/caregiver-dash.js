// ── CONFIG ───────────────────────────────────────────────────────────────────
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
let caregiverData = null;
let patientData   = [];


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

    // Update home stat
    const statEl = document.getElementById('stat-patients');
    if (statEl) statEl.textContent = patientData.length;

  } catch (error) {
    console.error('Failed to load dashboard:', error);
    document.getElementById('patient-list').innerHTML =
      '<p class="error-msg">Could not load patients. Make sure the server is running.</p>';
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

  document.getElementById('profile-avatar').textContent = getInitials(p.first_name, p.last_name);
  document.getElementById('profile-name').textContent   = p.first_name + ' ' + p.last_name;

  const stageBadge = document.getElementById('profile-stage-badge');
  stageBadge.textContent = p.dementia_stage || 'Stage Unknown';

  // Overview tab
  document.getElementById('overview').innerHTML =
    '<div class="detail-card">' +
      detailRow('Date of Birth', p.date_of_birth ? formatDate(p.date_of_birth) : 'N/A') +
      detailRow('Gender',        p.gender        || 'N/A') +
      detailRow('Address',       p.address       || 'N/A') +
    '</div>';

  // Medical tab
  document.getElementById('medical').innerHTML =
    '<div class="detail-card">' +
      detailRow('Dementia Stage',  p.dementia_stage  || 'N/A') +
      detailRow('Medical History', p.medical_history ? JSON.stringify(p.medical_history) : 'None recorded') +
    '</div>';

  // Contact tab
  document.getElementById('contact').innerHTML =
    '<div class="detail-card">' +
      detailRow('Emergency Contact',      p.emergency_contact      || 'N/A') +
      detailRow('Emergency Contact Name', p.emergency_contact_name || 'N/A') +
    '</div>';

  // Reset sub-tabs to overview
  document.querySelectorAll('.ptab-btn').forEach(b => b.classList.remove('active-ptab'));
  document.querySelectorAll('.profile-section').forEach(s => s.classList.remove('active-psection'));
  document.querySelector('.ptab-btn').classList.add('active-ptab');
  document.getElementById('overview').classList.add('active-psection');

  // Switch tab
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  document.getElementById('patient-profile').classList.add('active');
}

function closeProfile() {
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


// ── INIT ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  // Set today's date on home tab
  const dateEl = document.getElementById('today-date');
  if (dateEl) {
    dateEl.textContent = new Date().toLocaleDateString('en-US', {
      weekday: 'long', month: 'long', day: 'numeric'
    });
  }

  loadDashboard();
  openTab('home');
});