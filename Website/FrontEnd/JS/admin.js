// -------------------- TAB SWITCHING --------------------

function selectTab(element, tabId) {
  document.querySelectorAll('.nav-item').forEach(item => item.classList.remove('active'));
  element.classList.add('active');
  document.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));
  const selectedTab = document.getElementById(tabId);
  if (selectedTab) selectedTab.classList.add('active');

  if (tabId === 'security') {
    loadBreakGlassLogs();
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const firstItem = document.querySelector('.nav-item');
  if (firstItem) firstItem.classList.add('active');
  loadPatients();       // fetch existing patients from DB on page load
  loadAllCaregivers();  // pre-fetch caregiver list for the assign dropdown
});

// -------------------- PATIENT MANAGEMENT --------------------

const API_BASE = 'https://localhost:3000';

let patients      = [];
let allCaregivers = [];
let breakGlassLogs = [];

// LOAD EXISTING PATIENTS FROM DB
async function loadPatients() {
  try {
    const response = await fetch(`${API_BASE}/administrator/patients`);
    if (!response.ok) throw new Error(`Server error: ${response.status}`);
    patients = await response.json();
    renderPatients();
  } catch (error) {
    console.error('Could not load patients:', error);
  }
}

// ADD & ONBOARD PATIENT
async function addPatient() {
  const first_name             = document.getElementById('first_name').value.trim();
  const last_name              = document.getElementById('last_name').value.trim();
  const date_of_birth          = document.getElementById('date_of_birth').value;
  const gender                 = document.getElementById('gender').value;
  const emergency_contact      = document.getElementById('emergency_contact').value.trim();
  const emergency_contact_name = document.getElementById('emergency_contact_name').value.trim();
  const address                = document.getElementById('address').value.trim();
  const dementia_stage         = document.getElementById('dementia_stage').value.trim();

  if (!first_name || !last_name || !date_of_birth || !gender) {
    alert('Please fill in all required fields: First Name, Last Name, Date of Birth, and Gender.');
    return;
  }

  const payload = { first_name, last_name, date_of_birth, gender, emergency_contact, emergency_contact_name, address, dementia_stage };

  const submitBtn = document.querySelector(".btn-primary[onclick='addPatient()']");
  if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = 'Onboarding...'; }

  try {
    const response = await fetch(`${API_BASE}/administrator/onboard`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      let errorMsg = `Server error: ${response.status} ${response.statusText}`;
      try { const e = await response.json(); if (e.message) errorMsg = e.message; } catch (_) {}
      throw new Error(errorMsg);
    }

    const data = await response.json();
    patients.push(data);
    renderPatients();
    clearForm();
    alert(`Patient "${data.first_name} ${data.last_name}" successfully onboarded (Patient ID: ${data.patient_id}).`);

  } catch (error) {
    console.error('Onboarding failed:', error);
    alert(`Failed to onboard patient.\n\n${error.message}`);
  } finally {
    if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = 'Onboard Patient'; }
  }
}

// CLEAR FORM
function clearForm() {
  document.querySelectorAll('.form-card input').forEach(input => input.value = '');
  ['gender', 'dementia_stage'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });
}

// DELETE (local only)
function deletePatient(index) {
  patients.splice(index, 1);
  renderPatients();
}

// EDIT
function editPatient(index) {
  const p = patients[index];
  document.getElementById('first_name').value             = p.first_name;
  document.getElementById('last_name').value              = p.last_name;
  document.getElementById('date_of_birth').value          = p.date_of_birth;
  document.getElementById('gender').value                 = p.gender;
  document.getElementById('emergency_contact').value      = p.emergency_contact;
  document.getElementById('emergency_contact_name').value = p.emergency_contact_name;
  document.getElementById('address').value                = p.address;
  document.getElementById('dementia_stage').value         = p.dementia_stage;
  deletePatient(index);
}

// RENDER TABLE
function renderPatients() {
  const tbody   = document.getElementById('patients-tbody');
  const countEl = document.getElementById('patient-count');
  tbody.innerHTML = '';

  if (countEl) {
    countEl.textContent = patients.length === 1 ? '1 patient' : `${patients.length} patients`;
  }

  if (patients.length === 0) {
    const emptyRow = document.createElement('tr');
    emptyRow.innerHTML = `
      <td colspan="10">
        <div class="empty-state">
          <div class="empty-icon">👥</div>
          <p>No patients onboarded yet. Use the form above to add one.</p>
        </div>
      </td>`;
    tbody.appendChild(emptyRow);
    return;
  }

  patients.forEach((p, index) => {
    const row = document.createElement('tr');
    row.innerHTML = `
      <td><span class="id-pill">${p.patient_id ?? '—'}</span></td>
      <td>${p.first_name}</td>
      <td>${p.last_name}</td>
      <td>${p.date_of_birth}</td>
      <td>${p.gender}</td>
      <td>${p.dementia_stage ? '<span class="stage-badge">' + p.dementia_stage + '</span>' : '—'}</td>
      <td>${p.emergency_contact || '—'}</td>
      <td>${p.emergency_contact_name || '—'}</td>
      <td>${p.address || '—'}</td>
      <td>
        <button class="action-btn edit"   onclick="editPatient(${index})">Edit</button>
        <button class="action-btn assign" onclick="openAssignModal(${p.patient_id}, '${p.first_name} ${p.last_name}')">Caregivers</button>
        <button class="action-btn delete" onclick="deletePatient(${p.patient_id}, ${index})">Delete</button>
      </td>`;
    tbody.appendChild(row);
  });
}

async function deletePatient(patientId, index) {
  if (!confirm('Are you sure you want to delete this patient? This cannot be undone.')) return;

  try {
    const response = await fetch(`${API_BASE}/administrator/patient/${patientId}`, {
      method: 'DELETE',
    });

    if (!response.ok) throw new Error(`Server error: ${response.status}`);

    patients.splice(index, 1);
    renderPatients();

  } catch (error) {
    console.error('Delete failed:', error);
    alert(`Failed to delete patient.\n\n${error.message}`);
  }
}

// -------------------- CAREGIVER ASSIGNMENT --------------------

let activePatientId = null;

async function loadAllCaregivers() {
  try {
    const response = await fetch(`${API_BASE}/administrator/caregivers`);
    if (!response.ok) throw new Error('Failed to load caregivers');
    allCaregivers = await response.json();
    populateCaregiverDropdown();
  } catch (error) {
    console.error('Could not load caregiver list:', error);
  }
}

function populateCaregiverDropdown() {
  const select = document.getElementById('caregiver-select');
  select.innerHTML = '<option value="">Select a caregiver...</option>';
  allCaregivers.forEach(c => {
    const option = document.createElement('option');
    option.value = c.caregiver_id;
    option.textContent = c.first_name + ' ' + c.last_name + ' — ' + c.specialization;
    select.appendChild(option);
  });
}

async function openAssignModal(patientId, patientName) {
  activePatientId = patientId;
  document.getElementById('modal-patient-name').textContent = patientName;
  document.getElementById('modal-patient-id').textContent   = 'Patient ID: ' + patientId;
  document.getElementById('caregiver-select').value         = '';
  document.getElementById('assign-modal-overlay').classList.add('active');
  await loadAssignedCaregivers(patientId);
}

function closeAssignModal() {
  document.getElementById('assign-modal-overlay').classList.remove('active');
  activePatientId = null;
}

async function loadAssignedCaregivers(patientId) {
  const listEl = document.getElementById('assigned-caregivers-list');
  listEl.innerHTML = '<p class="muted-text">Loading...</p>';

  try {
    const response = await fetch(`${API_BASE}/administrator/patient/${patientId}/caregivers`);
    if (!response.ok) throw new Error('Failed to fetch assignments');
    const assignments = await response.json();
    renderAssignedCaregivers(assignments);
  } catch (error) {
    listEl.innerHTML = '<p class="muted-text error-text">Could not load assignments: ' + error.message + '</p>';
  }
}

function renderAssignedCaregivers(assignments) {
  const listEl = document.getElementById('assigned-caregivers-list');

  if (!assignments || assignments.length === 0) {
    listEl.innerHTML = '<p class="muted-text">No caregivers assigned yet.</p>';
    return;
  }

  listEl.innerHTML = '';
  assignments.forEach(a => {
    const c    = a.caregiver;
    const item = document.createElement('div');
    item.className = 'assigned-caregiver-item';
    item.innerHTML =
      '<div class="assigned-caregiver-info">' +
        '<span class="assigned-caregiver-name">' + c.first_name + ' ' + c.last_name + '</span>' +
        '<span class="assigned-caregiver-meta">' + c.specialization + ' · ID ' + c.caregiver_id + '</span>' +
      '</div>' +
      '<button class="action-btn delete" onclick="unassignCaregiver(' + activePatientId + ', ' + c.caregiver_id + ', this)">Remove</button>';
    listEl.appendChild(item);
  });
}

async function assignCaregiver() {
  const select      = document.getElementById('caregiver-select');
  const caregiverId = parseInt(select.value);

  if (!caregiverId) {
    alert('Please select a caregiver from the list.');
    return;
  }

  try {
    const response = await fetch(`${API_BASE}/administrator/assign-caregiver`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ patient_id: activePatientId, caregiver_id: caregiverId }),
    });

    if (!response.ok) {
      let errorMsg = 'Error: ' + response.status;
      try { const e = await response.json(); if (e.message) errorMsg = e.message; } catch (_) {}
      throw new Error(errorMsg);
    }

    select.value = '';
    await loadAssignedCaregivers(activePatientId);

  } catch (error) {
    console.error('Assign failed:', error);
    alert('Failed to assign caregiver.\n\n' + error.message);
  }
}

async function unassignCaregiver(patientId, caregiverId, btnEl) {
  if (!confirm('Remove this caregiver from the patient?')) return;

  btnEl.disabled    = true;
  btnEl.textContent = 'Removing...';

  try {
    const response = await fetch(`${API_BASE}/administrator/patient/${patientId}/caregiver/${caregiverId}`, {
      method: 'DELETE',
    });

    if (!response.ok) throw new Error('Error: ' + response.status);
    await loadAssignedCaregivers(patientId);

  } catch (error) {
    console.error('Unassign failed:', error);
    alert('Failed to remove caregiver.\n\n' + error.message);
    btnEl.disabled    = false;
    btnEl.textContent = 'Remove';
  }
}

// -------------------- SECURITY / BREAK-GLASS LOGS --------------------

async function loadBreakGlassLogs() {
  const tbody = document.getElementById('breakglass-tbody');
  if (tbody) {
    tbody.innerHTML = `
      <tr>
        <td colspan="6">
          <div class="empty-state">
            <p>Loading break-glass logs...</p>
          </div>
        </td>
      </tr>`;
  }

  try {
    const response = await fetch(`${API_BASE}/administrator/break-glass-logs`);
    if (!response.ok) throw new Error(`Server error: ${response.status}`);
    breakGlassLogs = await response.json();
    renderBreakGlassLogs();
  } catch (error) {
    console.error('Could not load break-glass logs:', error);
    if (tbody) {
      tbody.innerHTML = `
        <tr>
          <td colspan="6">
            <div class="empty-state">
              <p>Could not load break-glass logs.</p>
            </div>
          </td>
        </tr>`;
    }
  }
}

function renderBreakGlassLogs() {
  const tbody = document.getElementById('breakglass-tbody');
  const countEl = document.getElementById('breakglass-count');
  if (!tbody) return;

  tbody.innerHTML = '';

  if (countEl) {
    countEl.textContent = breakGlassLogs.length === 1 ? '1 log' : `${breakGlassLogs.length} logs`;
  }

  if (!breakGlassLogs.length) {
    tbody.innerHTML = `
      <tr>
        <td colspan="6">
          <div class="empty-state">
            <div class="empty-icon">Security</div>
            <p>No break-glass access has been logged yet.</p>
          </div>
        </td>
      </tr>`;
    return;
  }

  breakGlassLogs.forEach((log) => {
    const row = document.createElement('tr');
    row.innerHTML = `
      <td><span class="id-pill">${escapeHtml(log.logId ?? '-')}</span></td>
      <td>${escapeHtml(formatDateTime(log.timestamp))}</td>
      <td>${escapeHtml(log.caregiverName || 'Unknown')} <span class="muted-inline">#${escapeHtml(log.caregiverId ?? '-')}</span></td>
      <td>${escapeHtml(log.patientName || 'Unknown')} <span class="muted-inline">#${escapeHtml(log.patientId ?? '-')}</span></td>
      <td><span class="stream-badge">${escapeHtml(String(log.accessedStream || '').toUpperCase())}</span></td>
      <td class="reason-cell">${escapeHtml(log.reason || '-')}</td>`;
    tbody.appendChild(row);
  });
}

function getRiskColor(risk) {
  if (risk === 'HIGH') return 'red';
  if (risk === 'MID')  return 'orange';
  return 'green';
}

function formatDateTime(value) {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '-';
  return date.toLocaleString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}
