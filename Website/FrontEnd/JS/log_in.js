document.getElementById('login-form').addEventListener('submit', async (e) => {
  e.preventDefault();

  const body = {
    email: document.getElementById('email').value.trim(),
    pass: document.getElementById('password').value.trim(),
  };

  try {
    const response = await fetch('https://localhost:3000/auth/login', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body), // Fixed nesting
    });

    const data = await response.json();
    console.log('Server Response:', data);

    if (!response.ok) {
      throw new Error(data.message || 'Login failed');
    }

    // Move session storage and redirect INSIDE the try block
    localStorage.setItem('access_token', data.access_token);
    localStorage.setItem('user', JSON.stringify(data.user));

    // Check data.role directly
    if (data.user.role === "caregiver") {
      window.location.href = '../Pages/caregiver-dash.html';
    } else {
      window.location.href = '/dashboard.html'; // Default redirect
    }

  } catch (error) {
    console.error('Error:', error.message);
    alert(error.message); // Tell the user why it failed
  }
});