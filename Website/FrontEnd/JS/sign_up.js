const API_BASE = 'https://localhost:3000';

const domainTypeSelect = document.getElementById('domain-type');
const instituteFields = document.getElementById('institute-fields');
const personalFields = document.getElementById('personal-fields');
const signupForm = document.getElementById('signup-form');
const submitBtn = document.getElementById('submit-btn');

domainTypeSelect.addEventListener('change', () => {
  const domainType = domainTypeSelect.value;
  instituteFields.style.display = domainType === 'institute' ? 'block' : 'none';
  personalFields.style.display = domainType === 'personal' ? 'block' : 'none';
  setSectionEnabled(instituteFields, domainType === 'institute');
  setSectionEnabled(personalFields, domainType === 'personal');
});

setSectionEnabled(instituteFields, false);
setSectionEnabled(personalFields, false);

signupForm.addEventListener('submit', async (e) => {
  e.preventDefault();

  const domainType = domainTypeSelect.value;
  if (!domainType) {
    alert('Please choose Institute or Personal / Family Home.');
    return;
  }

  const password = getValue(`${domainType}-password`);
  const confirmPassword = getValue(`${domainType}-confirm-password`);

  if (password !== confirmPassword) {
    alert('Passwords do not match');
    return;
  }

  if (password.length < 8) {
    alert('Password must be at least 8 characters');
    return;
  }

  const body = domainType === 'institute'
    ? buildInstitutePayload(password)
    : buildPersonalPayload(password);

  submitBtn.disabled = true;
  submitBtn.textContent = 'Creating account...';

  try {
    const response = await fetch(`${API_BASE}/auth/enroll-domain`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(Array.isArray(data.message) ? data.message.join('\n') : data.message || 'Signup failed');
    }

    localStorage.setItem('access_token', data.access_token);
    localStorage.setItem('user', JSON.stringify(data.user));
    window.location.href = '../Pages/admin.html';
  } catch (error) {
    alert(error.message || 'Could not create account');
    console.error(error);
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = 'Create Account';
  }
});

function buildInstitutePayload(password) {
  return {
    domain_type: 'institute',
    domain: {
      name: getValue('institute-name'),
      contact_email: getValue('institute-contact-email'),
      phone: getValue('institute-phone'),
      address: getValue('institute-address'),
    },
    user: {
      first_name: getValue('institute-admin-first-name'),
      last_name: getValue('institute-admin-last-name'),
      phone: getValue('institute-admin-phone'),
      job_title: getValue('institute-admin-job-title') || 'Administrator',
      email: getValue('institute-admin-email'),
      pass: password,
    },
  };
}

function buildPersonalPayload(password) {
  return {
    domain_type: 'personal',
    domain: {
      name: getValue('personal-home-name'),
      contact_email: getValue('personal-contact-email'),
      phone: getValue('personal-phone'),
      address: getValue('personal-address'),
    },
    user: {
      first_name: getValue('family-first-name'),
      last_name: getValue('family-last-name'),
      phone: getValue('family-phone'),
      email: getValue('family-email'),
      pass: password,
    },
    patient: {
      first_name: getValue('patient-first-name'),
      last_name: getValue('patient-last-name'),
      date_of_birth: getValue('patient-date-of-birth'),
      gender: getValue('patient-gender'),
      emergency_contact: getValue('patient-emergency-contact'),
      emergency_contact_name: getValue('patient-emergency-contact-name'),
      address: getValue('patient-address'),
      dementia_stage: getValue('patient-dementia-stage'),
    },
    relationship: getValue('patient-relationship'),
  };
}

function getValue(id) {
  return document.getElementById(id).value.trim();
}

function setSectionEnabled(section, enabled) {
  section.querySelectorAll('input, select').forEach((field) => {
    field.disabled = !enabled;
  });
}
