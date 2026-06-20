document.getElementById("analyze-btn").addEventListener("click", async () => {
  const text = document.getElementById("text-input").value;
  const resp = await fetch("/analyze", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({text}),
  });
  const data = await resp.json();
  const output = document.getElementById("reader-output");
  output.innerHTML = data.tokens.map(t => {
    const hasKanji = /[一-鿿]/.test(t.surface);
    const display = hasKanji
      ? `<ruby>${t.surface}<rt>${t.reading_hiragana}</rt></ruby>`
      : t.surface;
    const meanings = JSON.stringify(t.meanings).replace(/'/g, "&#39;");
    return `<span class="word" data-lemma="${t.lemma}" data-reading="${t.reading_hiragana}" data-meanings='${meanings}'>${display}</span>`;
  }).join("");
});

document.getElementById("reader-output").addEventListener("click", (e) => {
  const word = e.target.closest(".word");
  if (!word) return;

  document.querySelectorAll(".popover").forEach(p => p.remove());

  const lemma = word.dataset.lemma;
  const reading = word.dataset.reading;
  const meanings = JSON.parse(word.dataset.meanings || "[]");

  const popover = document.createElement("div");
  popover.className = "popover";
  const meaningsHtml = meanings.length > 0
    ? meanings.map(m => `<li>${m}</li>`).join("")
    : "<li>(no dictionary entry)</li>";
  popover.innerHTML = `<strong>${reading}</strong><ul>${meaningsHtml}</ul>`;
  word.appendChild(popover);
});

document.addEventListener("click", (e) => {
  if (!e.target.closest(".word")) {
    document.querySelectorAll(".popover").forEach(p => p.remove());
  }
});
