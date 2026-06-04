// -------------------- Global Patient Data --------------------
const patients = [
  {
    name: "Andrea Adams",
    age: 78,
    risk: "HIGH",
    lastVitalSync: "Today 08:30 AM",  // Changed from lastVisit
    nextVisit: "JUN 6/26",             // Changed from nextCheck
    alert: "Active",
    description: "Andrea Adams 78, mother of 3 and does not work blah blah blah",
    riskScore: 69,
    diagnoses: "severe dementia",
    medications: "anti psychosis meds",
    caregivers: "Elena (Primary), Rose (Nurse), Gilbert (Nurse)",
    recentAlerts: 56
  },
  // Add more sample patients with the new structure
  {
    name: "Robert Chen",
    age: 82,
    risk: "MID",
    lastVitalSync: "Yesterday 04:15 PM",
    nextVisit: "JUN 12/26",
    alert: "Stable",
    description: "Robert Chen 82, retired teacher",
    riskScore: 45,
    diagnoses: "early stage Alzheimer's",
    medications: "memory support supplements",
    caregivers: "Linda (Primary), James (Nurse)",
    recentAlerts: 12
  },
  {
    name: "Margaret O'Brien",
    age: 91,
    risk: "HIGH",
    lastVitalSync: "3 hours ago",
    nextVisit: "MAY 28/26",
    alert: "Critical",
    description: "Margaret O'Brien 91, requires constant monitoring",
    riskScore: 85,
    diagnoses: "advanced dementia, hypertension",
    medications: "blood pressure meds, antipsychotics",
    caregivers: "Sarah (Primary), Michael (Nurse), Patricia (Nurse)",
    recentAlerts: 89
  },
  {
    name: "William Foster",
    age: 76,
    risk: "LOW",
    lastVitalSync: "Today 10:15 AM",
    nextVisit: "JUL 3/26",
    alert: "Inactive",
    description: "William Foster 76, lives with daughter",
    riskScore: 25,
    diagnoses: "mild cognitive impairment",
    medications: "vitamin supplements",
    caregivers: "Emma (Primary)",
    recentAlerts: 3
  }
];

// -------------------- Tab Switching Function --------------------
function openTab(tabName) {
  // Hide all tab contents
  document.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));

  // Show selected tab
  const selectedTab = document.getElementById(tabName);
  if (selectedTab) selectedTab.classList.add('active');

  // Remove active from all bottom-nav buttons
  document.querySelectorAll('.bottom-nav button').forEach(btn => btn.classList.remove('active'));

  // Add active to the clicked button
  const btn = document.getElementById(`btn-${tabName}`);
  if (btn) btn.classList.add('active');
}

// -------------------- Populate Patients Table --------------------
document.addEventListener("DOMContentLoaded", () => {
  const tableBody = document.querySelector("#patients-table tbody");
  
  // Clear any existing rows (if any)
  tableBody.innerHTML = '';

  patients.forEach((p, index) => {
    const row = document.createElement("tr");
    
    // Determine risk color
    let riskColor = "green";
    if (p.risk === "HIGH") riskColor = "red";
    else if (p.risk === "MID") riskColor = "orange";
    
    // Determine alert status color
    let alertColor = "green";
    if (p.alert === "Active") alertColor = "orange";
    else if (p.alert === "Critical") alertColor = "red";
    else if (p.alert === "Inactive") alertColor = "gray";
    
    row.innerHTML = `
      <td>${p.name}</td>
      <td style="color: ${riskColor}; font-weight: bold;">${p.risk}</td>
      <td>${p.lastVitalSync}</td>
      <td style="color: ${alertColor};">${p.alert}</td>
      <td>${p.nextVisit}</td>
      <td>
        <button onclick="viewPatientProfile(${index})" style="
          background-color: #0e6b6f;
          color: white;
          border: none;
          padding: 8px 16px;
          border-radius: 20px;
          cursor: pointer;
          font-size: 14px;
        ">View Profile</button>
      </td>
    `;
    tableBody.appendChild(row);
  });

  // Activate Home tab by default
  openTab('home');
});

// -------------------- View Patient Profile Function --------------------
function viewPatientProfile(index) {
  // For now, just log to console
  console.log("Viewing patient:", patients[index].name);
  
  // You can either:
  // Option 1: Navigate to a profile page with query parameter
  window.location.href = `patient_profile.html?index=${index}`;
  
  // Option 2: Or if you want to show profile in a modal/tab within the same page
  // showPatientProfile(index);
}