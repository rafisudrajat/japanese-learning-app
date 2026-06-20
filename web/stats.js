async function loadStats() {
  const resp = await fetch("/stats");
  const data = await resp.json();
  const area = document.getElementById("stats-area");
  if (data.total_reviews === 0) {
    area.innerHTML = "<p>No reviews yet.</p>";
    return;
  }
  const days = Object.entries(data.reviews_per_day)
    .map(([day, count]) => `<li>${day}: ${count} reviews</li>`)
    .join("");
  area.innerHTML = `
    <p><strong>Accuracy:</strong> ${(data.accuracy * 100).toFixed(1)}%</p>
    <p><strong>Total reviews:</strong> ${data.total_reviews}</p>
    <h2>Reviews per day</h2>
    <ul>${days}</ul>
  `;
}

loadStats();
