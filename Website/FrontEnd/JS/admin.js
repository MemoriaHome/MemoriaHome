// TAB SWITCHING
function selectTab(element, tabId) {
  document.querySelectorAll('.nav-item').forEach(item => {
    item.classList.remove('active');
  });

  element.classList.add('active');

  document.querySelectorAll('.tab-content').forEach(tab => {
    tab.classList.remove('active');
  });

  const selectedTab = document.getElementById(tabId);
  if (selectedTab) selectedTab.classList.add('active');
}

// DEFAULT ACTIVE TAB
document.addEventListener("DOMContentLoaded", () => {
  const firstItem = document.querySelector('.nav-item');
  if (firstItem) firstItem.classList.add('active');
});


// -------------------- PATIENT MANAGEMENT --------------------

let patients = [];
let patientCounter = 1;

// ADD PATIENT
function addPatient() {
  const first_name = document.getElementById("first_name").value;
  const last_name = document.getElementById("last_name").value;
  const date_of_birth = document.getElementById("date_of_birth").value;
  const gender = document.getElementById("gender").value;
  const emergency_contact = document.getElementById("emergency_contact").value;
  const emergency_contact_name = document.getElementById("emergency_contact_name").value;
  const address = document.getElementById("address").value;
  const dementia_stage = document.getElementById("dementia_stage").value;

  if (!first_name || !last_name || !date_of_birth || !gender) {
    alert("Please fill required fields");
    return;
  }

  const today = new Date();

  const patient = {
    userId: "U" + Math.floor(Math.random() * 10000), // auto
    patientId: "P" + patientCounter++,              // auto
    first_name,
    last_name,
    date_of_birth,
    gender,
    emergency_contact,
    emergency_contact_name,
    address,
    dementia_stage,
  };

  patients.push(patient);
  renderPatients();

  // Clear inputs
  document.querySelectorAll(".form-card input").forEach(input => input.value = "");
  document.getElementById("risk").value = "";
}

// DELETE
function deletePatient(index) {
  patients.splice(index, 1);
  renderPatients();
}

// EDIT
function editPatient(index) {
  const p = patients[index];

  document.getElementById("first_name").value = p.first_name;
  document.getElementById("last_name").value = p.last_name;
  document.getElementById("date_of_birth").value = p.date_of_birth;
  document.getElementById("gender").value = p.gender;
  document.getElementById("emergency_contact").value = p.emergency_contact;
  document.getElementById("emergency_contact_name").value = p.emergency_contact_name;
  document.getElementById("address").value = p.address;
  document.getElementById("dementia_stage").value = p.dementia_stage;

  deletePatient(index);
}

// RENDER TABLE
function renderPatients() {
  const tbody = document.querySelector("#patients-table tbody");
  tbody.innerHTML = "";

  patients.forEach((p, index) => {
    const row = document.createElement("tr");

    row.innerHTML = `
      <td>${p.first_name}</td>
      <td>${p.last_name}</td>
      <td>${p.date_of_birth}</td>
      <td>${p.gender}</td>
      <td>${p.emergency_contact}</td>
      <td>${p.emergency_contact_name}</td>
      <td>${p.address}</td>
      <td>${p.dementia_stage}</td>
      <td>
        <button onclick="editPatient(${index})">Edit</button>
        <button onclick="deletePatient(${index})">Delete</button>
      </td>
    `;

    tbody.appendChild(row);
  });
}

function getRiskColor(risk) {
  if (risk === "HIGH") return "red";
  if (risk === "MID") return "orange";
  return "green";
}