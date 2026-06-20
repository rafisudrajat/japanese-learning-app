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
    return `<span class="word" data-lemma="${t.lemma}" data-reading="${t.reading_hiragana}" data-meanings='${JSON.stringify(t.meanings)}'>${display}</span>`;
  }).join("");
});
