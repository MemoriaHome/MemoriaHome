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

  patients.forEach((p, index) => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${p.name}</td>
      <td>${p.age}</td>
      <td style="color: ${p.risk === "HIGH" ? "red" : p.risk === "Mid" ? "orange" : "green"}">${p.risk}</td>
      <td>${p.lastVisit}</td>
      <td>${p.nextCheck}</td>
      <td>${p.alert}</td>
      <td>
        <button onclick="window.location.href='patient_profile.html?index=${index}'">View Profile</button>
      </td>
    `;
    tableBody.appendChild(row);
  });

  // Activate Home tab by default
  openTab('home');
});