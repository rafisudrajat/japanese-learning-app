async function loadVocab(q) {
  const url = q ? `/vocab?q=${encodeURIComponent(q)}` : "/vocab";
  const resp = await fetch(url);
  const data = await resp.json();
  const list = document.getElementById("vocab-list");
  if (data.vocab.length === 0) {
    list.innerHTML = "<p>No words saved yet.</p>";
    return;
  }
  list.innerHTML = "<ul>" + data.vocab.map(v =>
    `<li><strong>${v.lemma}</strong> (${v.reading || ""}) — ${v.primary_meaning || ""} <em>[${v.status}]</em></li>`
  ).join("") + "</ul>";
}

document.getElementById("search").addEventListener("input", (e) => {
  loadVocab(e.target.value);
});

loadVocab();
