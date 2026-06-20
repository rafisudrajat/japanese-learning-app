async function loadVocab(q) {
  const url = q ? `/vocab?q=${encodeURIComponent(q)}` : "/vocab";
  const resp = await fetch(url);
  const data = await resp.json();
  const list = document.getElementById("vocab-list");
  if (data.vocab.length === 0) {
    list.innerHTML = '<p class="no-data">No words saved yet. Go to the Reader to collect vocabulary.</p>';
    return;
  }
  list.innerHTML = data.vocab.map(v => `
    <div class="vocab-item">
      <span class="lemma">${v.lemma}</span>
      <span class="status ${v.status}">${v.status}</span>
      <div class="detail">${v.reading || ""} — ${v.primary_meaning || ""}</div>
    </div>
  `).join("");
}

document.getElementById("search").addEventListener("input", (e) => {
  loadVocab(e.target.value);
});

loadVocab();
