const roleSelect = document.getElementById('role-select');
const caregiverFields = document.getElementById('caregiver-fields');
const submitBtn = document.getElementById('submit-btn');

// Show/hide fields based on role
roleSelect.addEventListener('change', () => {
  const role = roleSelect.value;

  // Hide all role fields first
  document.querySelectorAll('.role-fields').forEach(f => f.style.display = 'none');
  submitBtn.style.display = 'none';

  if (role === 'caregiver') {
    caregiverFields.style.display = 'contents';
    submitBtn.style.display = 'block';
  }
  // doctor and family member cases will go here later
});

// Form submission
document.getElementById('signup-form').addEventListener('submit', async (e) => {
  e.preventDefault();

  const role = roleSelect.value;

  if (role === 'caregiver') {
    const password = document.getElementById('password').value;
    const confirmPassword = document.getElementById('confirm-password').value;

    if (password !== confirmPassword) {
      alert('Passwords do not match');
      return;
    }

    if (password.length < 8) {
      alert('Password must be at least 8 characters');
      return;
    }

    const body = {
      role: roleSelect.value,
      first_name: document.getElementById('first-name').value.trim(),
      last_name: document.getElementById('last-name').value.trim(),
      email: document.getElementById('email').value.trim(),
      pass: document.getElementById('password').value,
      phone: document.getElementById('phone').value.trim(),
      specialization: document.getElementById('specialization').value.trim(),
      license_number: document.getElementById('licence-number').value.trim(),
      years_experience: parseInt(document.getElementById('years-experience').value)
    };

    try {
      const response = await fetch('http://localhost:3000/auth/signup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });

      const data = await response.json();

      if (response.ok) {
        alert('Account created successfully!');
        window.location.href = '../Pages/log_in.html';
      } else {
        alert(data.message || 'Signup failed');
      }
    } catch (error) {
      alert('Could not connect to server');
      console.error(error);
    }
  }
});