async function loadStats() {
  const resp = await fetch("/stats");
  const data = await resp.json();
  const area = document.getElementById("stats-area");
  if (data.total_reviews === 0) {
    area.innerHTML = '<p class="no-data">No reviews yet. Go to Review to start studying.</p>';
    return;
  }
  const days = Object.entries(data.reviews_per_day)
    .map(([day, count]) => `<li>${day}: ${count} reviews</li>`)
    .join("");
  area.innerHTML = `
    <div class="stats-grid">
      <div class="stat-card">
        <div class="value">${(data.accuracy * 100).toFixed(1)}%</div>
        <div class="label">Accuracy</div>
      </div>
      <div class="stat-card">
        <div class="value">${data.total_reviews}</div>
        <div class="label">Total reviews</div>
      </div>
    </div>
    <h2>Reviews per day</h2>
    <ul>${days}</ul>
  `;
}

loadStats();
