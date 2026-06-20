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
    <div class="vocab-item" data-id="${v.id}">
      <span class="lemma">${v.lemma}</span>
      <span class="status ${v.status}">${v.status}</span>
      <button class="delete-btn" title="Delete this word">Delete</button>
      <div class="detail">${v.reading || ""} — ${v.primary_meaning || ""}</div>
    </div>
  `).join("");
}

async function deleteVocab(id) {
  const resp = await fetch(`/vocab/${id}`, { method: "DELETE" });
  return resp.ok;
}

document.getElementById("search").addEventListener("input", (e) => {
  loadVocab(e.target.value);
});

document.getElementById("vocab-list").addEventListener("click", async (e) => {
  const btn = e.target.closest(".delete-btn");
  if (!btn) return;
  const item = btn.closest(".vocab-item");
  const lemma = item.querySelector(".lemma").textContent;
  if (!confirm(`Delete "${lemma}" from your vocabulary? This also removes its review history.`)) return;
  if (await deleteVocab(item.dataset.id)) {
    item.remove();
  } else {
    alert("Failed to delete the word.");
  }
});

loadVocab();
