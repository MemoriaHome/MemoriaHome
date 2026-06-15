// -------------------- SESSION / API --------------------

const API_BASE = 'https://localhost:3000';
const token = localStorage.getItem('access_token');
const currentUser = JSON.parse(localStorage.getItem('user') || 'null');

if (!token || !currentUser) {
  window.location.href = '../Pages/log_in.html';
}

let patients = [];
let allCaregivers = [];
let admins = [];
let breakGlassLogs = [];
let activePatientId = null;

function authHeaders(extraHeaders = {}) {
  return {
    Authorization: `Bearer ${token}`,
    ...extraHeaders,
  };
}

async function apiFetch(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: authHeaders(options.headers || {}),
  });

  if (response.status === 401 || response.status === 403) {
    localStorage.removeItem('access_token');
    localStorage.removeItem('user');
    window.location.href = '../Pages/log_in.html';
    throw new Error('Session expired');
  }

  return response;
}

// -------------------- TAB SWITCHING --------------------

function selectTab(element, tabId) {
  document.querySelectorAll('.nav-item').forEach(item => item.classList.remove('active'));
  element.classList.add('active');
  document.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));
  const selectedTab = document.getElementById(tabId);
  if (selectedTab) selectedTab.classList.add('active');

  if (tabId === 'users') {
    loadAllCaregivers();
    loadAdmins();
  }

  if (tabId === 'security') {
    loadBreakGlassLogs();
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const firstItem = document.querySelector('.nav-item');
  if (firstItem) firstItem.classList.add('active');

  const domainLabel = document.getElementById('domain-label');
  if (domainLabel && currentUser) {
    domainLabel.textContent = `${currentUser.domain_name || 'Workspace'} - ${currentUser.role}`;
  }

  loadPatients();
  loadAllCaregivers();
  loadAdmins();
});

// -------------------- USER MANAGEMENT --------------------

async function createCaregiver() {
  const payload = {
    first_name: getValue('caregiver_first_name'),
    last_name: getValue('caregiver_last_name'),
    email: getValue('caregiver_email'),
    pass: getValue('caregiver_password'),
    phone: getValue('caregiver_phone'),
    specialization: getValue('caregiver_specialization'),
    license_number: getValue('caregiver_license_number'),
    years_experience: Number(getValue('caregiver_years_experience')),
  };

  if (!payload.first_name || !payload.last_name || !payload.email || !payload.pass || !payload.phone || !payload.specialization) {
    alert('Please fill in all required caregiver fields.');
    return;
  }

  if (payload.pass.length < 8) {
    alert('Caregiver password must be at least 8 characters.');
    return;
  }

  try {
    const response = await apiFetch('/administrator/caregivers', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!response.ok) throw await responseError(response);
    clearCaregiverForm();
    await loadAllCaregivers();
    alert('Caregiver account created.');
  } catch (error) {
    alert(`Failed to create caregiver.\n\n${error.message}`);
  }
}

async function createAdmin() {
  const payload = {
    first_name: getValue('admin_first_name'),
    last_name: getValue('admin_last_name'),
    email: getValue('admin_email'),
    pass: getValue('admin_password'),
    phone: getValue('admin_phone'),
    job_title: getValue('admin_job_title') || 'Administrator',
  };

  if (!payload.first_name || !payload.last_name || !payload.email || !payload.pass || !payload.phone) {
    alert('Please fill in all required admin fields.');
    return;
  }

  if (payload.pass.length < 8) {
    alert('Admin password must be at least 8 characters.');
    return;
  }

  try {
    const response = await apiFetch('/administrator/admins', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!response.ok) throw await responseError(response);
    clearAdminForm();
    await loadAdmins();
    alert('Admin account created.');
  } catch (error) {
    alert(`Failed to create admin.\n\n${error.message}`);
  }
}

async function loadAdmins() {
  const tbody = document.getElementById('admins-tbody');
  if (!tbody) return;

  try {
    const response = await apiFetch('/administrator/admins');
    if (!response.ok) throw await responseError(response);
    admins = await response.json();
    renderAdmins();
  } catch (error) {
    console.error('Could not load admins:', error);
  }
}

function renderAdmins() {
  const tbody = document.getElementById('admins-tbody');
  const countEl = document.getElementById('admin-count');
  if (!tbody) return;

  tbody.innerHTML = '';
  if (countEl) countEl.textContent = admins.length === 1 ? '1 admin' : `${admins.length} admins`;

  if (!admins.length) {
    tbody.innerHTML = emptyRow(5, 'No admins created yet.');
    return;
  }

  admins.forEach((admin) => {
    const row = document.createElement('tr');
    row.innerHTML = `
      <td><span class="id-pill">${escapeHtml(admin.admin_id)}</span></td>
      <td>${escapeHtml(admin.first_name)} ${escapeHtml(admin.last_name)}</td>
      <td>${escapeHtml(admin.phone || '-')}</td>
      <td>${escapeHtml(admin.job_title || '-')}</td>
      <td>${escapeHtml(admin.user_id)}</td>`;
    tbody.appendChild(row);
  });
}

function renderCaregiversTable() {
  const tbody = document.getElementById('caregivers-tbody');
  const countEl = document.getElementById('caregiver-count');
  if (!tbody) return;

  tbody.innerHTML = '';
  if (countEl) countEl.textContent = allCaregivers.length === 1 ? '1 caregiver' : `${allCaregivers.length} caregivers`;

  if (!allCaregivers.length) {
    tbody.innerHTML = emptyRow(6, 'No caregivers created yet.');
    return;
  }

  allCaregivers.forEach((caregiver) => {
    const row = document.createElement('tr');
    row.innerHTML = `
      <td><span class="id-pill">${escapeHtml(caregiver.caregiver_id)}</span></td>
      <td>${escapeHtml(caregiver.first_name)} ${escapeHtml(caregiver.last_name)}</td>
      <td>${escapeHtml(caregiver.phone || '-')}</td>
      <td>${escapeHtml(caregiver.specialization || '-')}</td>
      <td>${escapeHtml(caregiver.license_number || '-')}</td>
      <td>${escapeHtml(caregiver.years_experience ?? '-')}</td>`;
    tbody.appendChild(row);
  });
}

function clearCaregiverForm() {
  [
    'caregiver_first_name',
    'caregiver_last_name',
    'caregiver_email',
    'caregiver_password',
    'caregiver_phone',
    'caregiver_specialization',
    'caregiver_license_number',
    'caregiver_years_experience',
  ].forEach(id => setValue(id, ''));
}

function clearAdminForm() {
  [
    'admin_first_name',
    'admin_last_name',
    'admin_email',
    'admin_password',
    'admin_phone',
    'admin_job_title',
  ].forEach(id => setValue(id, ''));
}

// -------------------- PATIENT MANAGEMENT --------------------

async function loadPatients() {
  try {
    const response = await apiFetch('/administrator/patients');
    if (!response.ok) throw await responseError(response);
    patients = await response.json();
    renderPatients();
  } catch (error) {
    console.error('Could not load patients:', error);
  }
}

async function addPatient() {
  const first_name = getValue('first_name');
  const last_name = getValue('last_name');
  const date_of_birth = getValue('date_of_birth');
  const gender = getValue('gender');
  const emergency_contact = getValue('emergency_contact');
  const emergency_contact_name = getValue('emergency_contact_name');
  const address = getValue('address');
  const dementia_stage = getValue('dementia_stage');
  const relationship = getValue('relationship') || 'family';

  if (!first_name || !last_name || !date_of_birth || !gender) {
    alert('Please fill in all required fields: First Name, Last Name, Date of Birth, and Gender.');
    return;
  }

  const payload = {
    first_name,
    last_name,
    date_of_birth,
    gender,
    emergency_contact,
    emergency_contact_name,
    address,
    dementia_stage,
    relationship,
  };

  const submitBtn = document.querySelector(".btn-primary[onclick='addPatient()']");
  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.textContent = 'Onboarding...';
  }

  try {
    const response = await apiFetch('/administrator/onboard', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!response.ok) throw await responseError(response);
    const data = await response.json();
    patients.push(data);
    renderPatients();
    clearPatientForm();
    alert(`Patient "${data.first_name} ${data.last_name}" successfully onboarded.`);
  } catch (error) {
    alert(`Failed to onboard patient.\n\n${error.message}`);
  } finally {
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.textContent = 'Onboard Patient';
    }
  }
}

function clearPatientForm() {
  [
    'first_name',
    'last_name',
    'date_of_birth',
    'emergency_contact',
    'emergency_contact_name',
    'address',
    'relationship',
  ].forEach(id => setValue(id, ''));
  ['gender', 'dementia_stage'].forEach(id => setValue(id, ''));
}

function editPatient(index) {
  const p = patients[index];
  setValue('first_name', p.first_name);
  setValue('last_name', p.last_name);
  setValue('date_of_birth', p.date_of_birth);
  setValue('gender', p.gender);
  setValue('emergency_contact', p.emergency_contact);
  setValue('emergency_contact_name', p.emergency_contact_name);
  setValue('address', p.address);
  setValue('dementia_stage', p.dementia_stage);
}

function renderPatients() {
  const tbody = document.getElementById('patients-tbody');
  const countEl = document.getElementById('patient-count');
  if (!tbody) return;

  tbody.innerHTML = '';
  if (countEl) countEl.textContent = patients.length === 1 ? '1 patient' : `${patients.length} patients`;

  if (!patients.length) {
    tbody.innerHTML = emptyRow(10, 'No patients onboarded yet. Use the form above to add one.');
    return;
  }

  patients.forEach((p, index) => {
    const patientName = `${p.first_name} ${p.last_name}`;
    const row = document.createElement('tr');
    row.innerHTML = `
      <td><span class="id-pill">${escapeHtml(p.patient_id ?? '-')}</span></td>
      <td>${escapeHtml(p.first_name)}</td>
      <td>${escapeHtml(p.last_name)}</td>
      <td>${escapeHtml(p.date_of_birth)}</td>
      <td>${escapeHtml(p.gender)}</td>
      <td>${p.dementia_stage ? '<span class="stage-badge">' + escapeHtml(p.dementia_stage) + '</span>' : '-'}</td>
      <td>${escapeHtml(p.emergency_contact || '-')}</td>
      <td>${escapeHtml(p.emergency_contact_name || '-')}</td>
      <td>${escapeHtml(p.address || '-')}</td>
      <td>
        <button class="action-btn edit" onclick="editPatient(${index})">Edit</button>
        <button class="action-btn assign" onclick="openAssignModal(${p.patient_id}, '${escapeJs(patientName)}')">Caregivers</button>
        <button class="action-btn delete" onclick="deletePatient(${p.patient_id}, ${index})">Delete</button>
      </td>`;
    tbody.appendChild(row);
  });
}

async function deletePatient(patientId, index) {
  if (!confirm('Are you sure you want to delete this patient? This cannot be undone.')) return;

  try {
    const response = await apiFetch(`/administrator/patient/${patientId}`, {
      method: 'DELETE',
    });

    if (!response.ok) throw await responseError(response);
    patients.splice(index, 1);
    renderPatients();
  } catch (error) {
    alert(`Failed to delete patient.\n\n${error.message}`);
  }
}

// -------------------- CAREGIVER ASSIGNMENT --------------------

async function loadAllCaregivers() {
  try {
    const response = await apiFetch('/administrator/caregivers');
    if (!response.ok) throw await responseError(response);
    allCaregivers = await response.json();
    populateCaregiverDropdown();
    renderCaregiversTable();
  } catch (error) {
    console.error('Could not load caregiver list:', error);
  }
}

function populateCaregiverDropdown() {
  const select = document.getElementById('caregiver-select');
  if (!select) return;

  select.innerHTML = '<option value="">Select a caregiver...</option>';
  allCaregivers.forEach(c => {
    const option = document.createElement('option');
    option.value = c.caregiver_id;
    option.textContent = `${c.first_name} ${c.last_name} - ${c.specialization}`;
    select.appendChild(option);
  });
}

async function openAssignModal(patientId, patientName) {
  activePatientId = patientId;
  document.getElementById('modal-patient-name').textContent = patientName;
  document.getElementById('modal-patient-id').textContent = `Patient ID: ${patientId}`;
  document.getElementById('caregiver-select').value = '';
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
    const response = await apiFetch(`/administrator/patient/${patientId}/caregivers`);
    if (!response.ok) throw await responseError(response);
    const assignments = await response.json();
    renderAssignedCaregivers(assignments);
  } catch (error) {
    listEl.innerHTML = `<p class="muted-text error-text">Could not load assignments: ${escapeHtml(error.message)}</p>`;
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
    const c = a.caregiver;
    const item = document.createElement('div');
    item.className = 'assigned-caregiver-item';
    item.innerHTML = `
      <div class="assigned-caregiver-info">
        <span class="assigned-caregiver-name">${escapeHtml(c.first_name)} ${escapeHtml(c.last_name)}</span>
        <span class="assigned-caregiver-meta">${escapeHtml(c.specialization)} - ID ${escapeHtml(c.caregiver_id)}</span>
      </div>
      <button class="action-btn delete" onclick="unassignCaregiver(${activePatientId}, ${c.caregiver_id}, this)">Remove</button>`;
    listEl.appendChild(item);
  });
}

async function assignCaregiver() {
  const select = document.getElementById('caregiver-select');
  const caregiverId = Number(select.value);

  if (!caregiverId) {
    alert('Please select a caregiver from the list.');
    return;
  }

  try {
    const response = await apiFetch('/administrator/assign-caregiver', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ patient_id: activePatientId, caregiver_id: caregiverId }),
    });

    if (!response.ok) throw await responseError(response);
    select.value = '';
    await loadAssignedCaregivers(activePatientId);
  } catch (error) {
    alert(`Failed to assign caregiver.\n\n${error.message}`);
  }
}

async function unassignCaregiver(patientId, caregiverId, btnEl) {
  if (!confirm('Remove this caregiver from the patient?')) return;

  btnEl.disabled = true;
  btnEl.textContent = 'Removing...';

  try {
    const response = await apiFetch(`/administrator/patient/${patientId}/caregiver/${caregiverId}`, {
      method: 'DELETE',
    });

    if (!response.ok) throw await responseError(response);
    await loadAssignedCaregivers(patientId);
  } catch (error) {
    alert(`Failed to remove caregiver.\n\n${error.message}`);
    btnEl.disabled = false;
    btnEl.textContent = 'Remove';
  }
}

// -------------------- SECURITY / BREAK-GLASS LOGS --------------------

async function loadBreakGlassLogs() {
  const tbody = document.getElementById('breakglass-tbody');
  if (tbody) tbody.innerHTML = emptyRow(6, 'Loading break-glass logs...');

  try {
    const response = await apiFetch('/administrator/break-glass-logs');
    if (!response.ok) throw await responseError(response);
    breakGlassLogs = await response.json();
    renderBreakGlassLogs();
  } catch (error) {
    console.error('Could not load break-glass logs:', error);
    if (tbody) tbody.innerHTML = emptyRow(6, 'Could not load break-glass logs.');
  }
}

function renderBreakGlassLogs() {
  const tbody = document.getElementById('breakglass-tbody');
  const countEl = document.getElementById('breakglass-count');
  if (!tbody) return;

  tbody.innerHTML = '';
  if (countEl) countEl.textContent = breakGlassLogs.length === 1 ? '1 log' : `${breakGlassLogs.length} logs`;

  if (!breakGlassLogs.length) {
    tbody.innerHTML = emptyRow(6, 'No break-glass access has been logged yet.');
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

// -------------------- HELPERS --------------------

async function responseError(response) {
  let message = `Server error: ${response.status}`;
  try {
    const body = await response.json();
    if (Array.isArray(body.message)) message = body.message.join('\n');
    else if (body.message) message = body.message;
  } catch (_) {}
  return new Error(message);
}

function getValue(id) {
  return document.getElementById(id)?.value.trim() || '';
}

function setValue(id, value) {
  const el = document.getElementById(id);
  if (el) el.value = value || '';
}

function emptyRow(colspan, message) {
  return `
    <tr>
      <td colspan="${colspan}">
        <div class="empty-state">
          <p>${escapeHtml(message)}</p>
        </div>
      </td>
    </tr>`;
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

function escapeJs(value) {
  return String(value ?? '').replace(/\\/g, '\\\\').replace(/'/g, "\\'");
}
