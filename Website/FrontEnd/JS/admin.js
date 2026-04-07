// -------------------- TAB SWITCHING --------------------

function selectTab(element, tabId) {
  document.querySelectorAll('.nav-item').forEach(item => item.classList.remove('active'));
  element.classList.add('active');
  document.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));
  const selectedTab = document.getElementById(tabId);
  if (selectedTab) selectedTab.classList.add('active');
}

document.addEventListener("DOMContentLoaded", () => {
  const firstItem = document.querySelector('.nav-item');
  if (firstItem) firstItem.classList.add('active');
});


// -------------------- PATIENT MANAGEMENT --------------------

const API_BASE = "https://localhost:3000";

let patients = [];

// ADD & ONBOARD PATIENT
async function addPatient() {
  const first_name             = document.getElementById("first_name").value.trim();
  const last_name              = document.getElementById("last_name").value.trim();
  const date_of_birth          = document.getElementById("date_of_birth").value;
  const gender                 = document.getElementById("gender").value;
  const emergency_contact      = document.getElementById("emergency_contact").value.trim();
  const emergency_contact_name = document.getElementById("emergency_contact_name").value.trim();
  const address                = document.getElementById("address").value.trim();
  const dementia_stage         = document.getElementById("dementia_stage").value.trim();

  if (!first_name || !last_name || !date_of_birth || !gender) {
    alert("Please fill in all required fields: First Name, Last Name, Date of Birth, and Gender.");
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
  };

  const submitBtn = document.querySelector(".btn-primary[onclick='addPatient()']");
  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.textContent = "Onboarding...";
  }

  try {
    const response = await fetch(`${API_BASE}/administrator/onboard`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      let errorMsg = `Server error: ${response.status} ${response.statusText}`;
      try {
        const errData = await response.json();
        if (errData.message) errorMsg = errData.message;
      } catch (_) {}
      throw new Error(errorMsg);
    }

    const data = await response.json();

    const newPatient = {
      patient_id:             data.patient_id,
      user_id:                data.user_id,
      first_name:             data.first_name             ?? first_name,
      last_name:              data.last_name              ?? last_name,
      date_of_birth:          data.date_of_birth          ?? date_of_birth,
      gender:                 data.gender                 ?? gender,
      emergency_contact:      data.emergency_contact      ?? emergency_contact,
      emergency_contact_name: data.emergency_contact_name ?? emergency_contact_name,
      address:                data.address                ?? address,
      dementia_stage:         data.dementia_stage         ?? dementia_stage,
    };

    patients.push(newPatient);
    renderPatients();
    clearForm();
    alert(`Patient "${first_name} ${last_name}" successfully onboarded (Patient ID: ${newPatient.patient_id}).`);

  } catch (error) {
    console.error("Onboarding failed:", error);
    alert(`Failed to onboard patient.\n\n${error.message}`);
  } finally {
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.textContent = "Onboard Patient";
    }
  }
}

// CLEAR FORM
function clearForm() {
  document.querySelectorAll(".form-card input").forEach(input => input.value = "");
  ["gender", "dementia_stage"].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = "";
  });
}

// DELETE
function deletePatient(index) {
  patients.splice(index, 1);
  renderPatients();
}

// EDIT
function editPatient(index) {
  const p = patients[index];
  document.getElementById("first_name").value             = p.first_name;
  document.getElementById("last_name").value              = p.last_name;
  document.getElementById("date_of_birth").value          = p.date_of_birth;
  document.getElementById("gender").value                 = p.gender;
  document.getElementById("emergency_contact").value      = p.emergency_contact;
  document.getElementById("emergency_contact_name").value = p.emergency_contact_name;
  document.getElementById("address").value                = p.address;
  document.getElementById("dementia_stage").value         = p.dementia_stage;
  deletePatient(index);
}

// RENDER TABLE
function renderPatients() {
  const tbody = document.getElementById("patients-tbody");
  tbody.innerHTML = "";

  // Update count badge
  const countEl = document.getElementById("patient-count");
  if (countEl) {
    countEl.textContent = patients.length === 1 ? "1 patient" : `${patients.length} patients`;
  }

  // Empty state
  if (patients.length === 0) {
    const emptyRow = document.createElement("tr");
    emptyRow.innerHTML = `
      <td colspan="10">
        <div class="empty-state">
          <div class="empty-icon">👥</div>
          <p>No patients onboarded yet. Use the form above to add one.</p>
        </div>
      </td>
    `;
    tbody.appendChild(emptyRow);
    return;
  }

  patients.forEach((p, index) => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td><span class="id-pill">${p.patient_id ?? "—"}</span></td>
      <td>${p.first_name}</td>
      <td>${p.last_name}</td>
      <td>${p.date_of_birth}</td>
      <td>${p.gender}</td>
      <td>${p.dementia_stage ? `<span class="stage-badge">${p.dementia_stage}</span>` : "—"}</td>
      <td>${p.emergency_contact || "—"}</td>
      <td>${p.emergency_contact_name || "—"}</td>
      <td>${p.address || "—"}</td>
      <td>
        <button class="action-btn edit"   onclick="editPatient(${index})">Edit</button>
        <button class="action-btn delete" onclick="deletePatient(${index})">Delete</button>
      </td>
    `;
    tbody.appendChild(row);
  });
}

function getRiskColor(risk) {
  if (risk === "HIGH") return "red";
  if (risk === "MID")  return "orange";
  return "green";
}

// Initialise table on load
document.addEventListener("DOMContentLoaded", renderPatients);