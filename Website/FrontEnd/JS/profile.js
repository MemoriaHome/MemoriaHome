// -------------------- Global Patient Data --------------------
const patients = [
  {
    name: "Andrea Adams",
    age: 78,
    risk: "HIGH",
    lastVisit: "SEP 9/25",
    nextCheck: "JUN 6/26",
    alert: "Active",
    description: "Andrea Adams 78, mother of 3 and does not work blah blah blah",
    riskScore: 69,
    diagnoses: "severe dementia",
    medications: "anti psychosis meds",
    caregivers: "Elena (Primary), Rose (Nurse), Gilbert (Nurse)",
    recentAlerts: 56
  },
  // Add more patients here
];

// -------------------- Helper: Get patient index from URL --------------------
function getPatientIndex() {
  const params = new URLSearchParams(window.location.search);
  return parseInt(params.get('index'));
}

// -------------------- Populate Profile Page --------------------
document.addEventListener("DOMContentLoaded", () => {
  const index = getPatientIndex();
  if (isNaN(index) || !patients[index]) return alert("Invalid patient index!");

  const patient = patients[index];

  // Fill patient name in header
  document.getElementById("profile-name").innerText = patient.name;

  // Fill Overview tab
 document.getElementById("overview").innerHTML = `
  <div class="patient-card">

    <div class="patient-info">
      <p>${patient.description}</p>
      <div class="patient-info-inside">
        <p>Risk Score: ${patient.riskScore}</p>
        <p>Current Diagnosis: ${patient.diagnoses}</p>
        <p>Medications List: ${patient.medications}</p>
        <p>Assigned Caregivers: ${patient.caregivers}</p>
        <p>Recent ALerts: ${patient.recentAlerts}</p>
      </div>
    </div>
  </div>
`;

  // Fill Medical History tab
  document.getElementById("medical_history").innerHTML = `
    <div class="medical-card">
    <div class="dashboard-grid">
      <div class="medical-card-inside">
        <div class="round-sections four">
          <div class="round-section">Past Diagnosis</div>
          <div class="round-section">Lab Results</div>
          <div class="round-section">Imaging</div>
          <div class="round-section">Previous Interventions</div>
          <div class="round-section">Timeline View</div>
        </div>
      </div>
      <div class="medical-card-inside">
        <div class="vitals">
          <div class="vital-header">
          <h4>Current Vitals</h4>
          </div>
          <div class="vital-item">Heart Rate: 123</div>
          <div class="vital-item">Blood Pressure: 130/85</div>
          <div class="vital-item">Temperature: 36</div>
        </div>
        <div class="new-plan">
            <button type="button" class="plan-btn" onclick="openAssessmentForm()">
              Create New Assessment Plan
              <img src="../Assets/plus.png" class="btn-icon">
            </button>
        </div>
      </div>
    </div>
  `;

  // Fill Treatment Plan tab
  document.getElementById("treatment_plan").innerHTML = `
    <p>Recent alerts: ${patient.recentAlerts}</p>
  `;

  // Activate Overview tab by default
  openProfileTab('overview');
});


// -------------------- Assessment Plan Form --------------------
function openAssessmentForm() {

  const medicalTab = document.getElementById("medical_history");

  medicalTab.innerHTML = `
  <div class="medical-card-assessment">

    <form class="assessment-form">

      <input type="text" placeholder="Assessment Type e.g Cognitive, Physical etc">

      <textarea placeholder="Enter objectives"></textarea>

      <input type="text" placeholder="Assigned Caregivers e.g Elena, Rose etc">

      <textarea placeholder="Assigned Caregiver Tasks"></textarea>

      <input type="text" placeholder="Timeline e.g 3 months">

      <input type="date" placeholder="Follow-up Date">

      <div class="form-actions">
        <button type="submit">
          Save
          <img src="../Assets/check.png" class="btn-icon">
          </button>
      </div>

    </form>

  </div>
  `;
}


// -------------------- Tab Switching Function --------------------
function openProfileTab(tabId) {
  // Hide all tab contents
  document.querySelectorAll(".tab-content").forEach(tab => tab.classList.remove("active"));

  // Remove active from all buttons
  document.querySelectorAll(".bottom-nav button").forEach(btn => btn.classList.remove("active"));

  // Show selected tab
  document.getElementById(tabId).classList.add("active");

  // Activate the corresponding button
  const btn = document.getElementById(`btn-${tabId}`);
  if (btn) btn.classList.add("active");
}

// -------------------- Back Button --------------------
function goBack() {
  window.history.back();
}