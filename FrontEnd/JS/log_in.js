
const submitBtn = document.getElementById('submit-btn');

// Form submission
document.getElementById('login-form').addEventListener('submit', async (e) => {
  e.preventDefault();


    const body = {
  email: document.getElementById('email').value.trim(),
  pass: document.getElementById('password').value.trim(),
  role: 'caregiver',
};

    try {
      const response = await fetch('https://localhost:3000/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });

      const data = await response.json();

      if (response.ok) {
  localStorage.setItem('token', data.access_token);
  window.location.href = 'geriatric.html';
      
      } else {
        alert(data.message || 'Login failed');
      }
    } catch (error) {
      alert('Could not connect to server');
      console.error(error);
    }
  }
);