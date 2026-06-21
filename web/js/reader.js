document.querySelectorAll(".reader-tabs .tab").forEach(tab => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".reader-tabs .tab").forEach(t => t.classList.remove("active"));
    tab.classList.add("active");
    document.querySelectorAll(".reader-panel").forEach(p => p.style.display = "none");
    document.getElementById(tab.dataset.tab + "-panel").style.display = "block";
  });
});

function showReaderStatus(msg, isError) {
  const el = document.getElementById("reader-status");
  el.textContent = msg;
  el.className = isError ? "status-error" : "status-ok";
}

function clearReaderStatus() {
  const el = document.getElementById("reader-status");
  el.textContent = "";
  el.className = "";
}

function renderTokens(tokens) {
  const output = document.getElementById("reader-output");
  output.innerHTML = tokens.map(t => {
    const hasKanji = /[一-鿿]/.test(t.surface);
    const display = hasKanji
      ? `<ruby>${t.surface}<rt>${t.reading_hiragana}</rt></ruby>`
      : t.surface;
    const meanings = JSON.stringify(t.meanings).replace(/'/g, "&#39;");
    const knownClass = t.known ? " known" : "";
    return `<span class="word${knownClass}" data-lemma="${t.lemma}" data-reading="${t.reading_hiragana}" data-meanings='${meanings}' data-pos="${t.pos[0] || ''}">${display}</span>`;
  }).join("");
}

document.getElementById("analyze-btn").addEventListener("click", async () => {
  const text = document.getElementById("text-input").value;
  if (!text.trim()) { showReaderStatus("Please paste some text first.", true); return; }
  clearReaderStatus();
  const resp = await fetch("/analyze", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({text}),
  });
  const data = await resp.json();
  renderTokens(data.tokens);
});

document.getElementById("fetch-btn").addEventListener("click", async () => {
  const url = document.getElementById("url-input").value;
  if (!url.trim()) { showReaderStatus("Please enter a URL.", true); return; }
  showReaderStatus("Fetching article...", false);
  try {
    const resp = await fetch("/import/url", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({url}),
    });
    if (!resp.ok) {
      const err = await resp.text();
      showReaderStatus("Fetch failed: " + err, true);
      return;
    }
    const data = await resp.json();
    if (data.tokens.length === 0) {
      showReaderStatus("No text could be extracted from that URL.", true);
      return;
    }
    showReaderStatus(`Fetched ${data.tokens.length} tokens, ${data.candidates.length} new words found.`, false);
    renderTokens(data.tokens);
  } catch (e) {
    showReaderStatus("Error: " + e.message, true);
  }
});

document.getElementById("furigana-toggle").addEventListener("click", () => {
  const btn = document.getElementById("furigana-toggle");
  const output = document.getElementById("reader-output");
  output.classList.toggle("hide-furigana");
  const on = !output.classList.contains("hide-furigana");
  btn.textContent = on ? "振り仮名 On" : "振り仮名 Off";
  btn.classList.toggle("active", on);
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
    ? meanings.map((m, i) => `<li><label><input type="checkbox" class="meaning-check" data-index="${i}" checked> ${m}</label></li>`).join("")
    : "<li>(no dictionary entry)</li>";
  popover.innerHTML = `
    <strong>${reading}</strong>
    <ul>${meaningsHtml}</ul>
    <div class="triage-btns">
      <button class="keep-btn">Keep</button>
      <button class="know-btn">Already know</button>
    </div>`;
  document.body.appendChild(popover);
  const rect = word.getBoundingClientRect();
  const popW = popover.offsetWidth;
  const popH = popover.offsetHeight;
  const left = Math.min(Math.max(4, rect.left + rect.width / 2 - popW / 2), window.innerWidth - popW - 4);
  let top;
  if (rect.top - popH - 8 < 0) {
    top = rect.bottom + 8 + window.scrollY;
  } else {
    top = rect.top - popH - 8 + window.scrollY;
  }
  popover.style.left = left + "px";
  popover.style.top = top + "px";
  popover.style.position = "absolute";

  async function triage(decision) {
    var checks = popover.querySelectorAll(".meaning-check:checked");
    var selected = Array.from(checks).map(function (cb) {
      return meanings[parseInt(cb.dataset.index)];
    });
    if (selected.length === 0) selected = meanings.slice();
    const resp = await fetch("/triage", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        lemma,
        reading,
        meanings: selected,
        pos: word.dataset.pos || "",
        decision,
      }),
    });
    return resp.json();
  }

  popover.querySelector(".keep-btn").addEventListener("click", async (ev) => {
    ev.stopPropagation();
    await triage("keep");
    word.classList.add("saved");
    word.classList.remove("known");
    popover.innerHTML = `<strong>${reading}</strong><p>Saved for review</p>`;
  });

  popover.querySelector(".know-btn").addEventListener("click", async (ev) => {
    ev.stopPropagation();
    await triage("known");
    word.classList.add("known");
    word.classList.remove("saved");
    popover.innerHTML = `<strong>${reading}</strong><p>Marked as known</p>`;
  });
});

document.addEventListener("click", (e) => {
  if (!e.target.closest(".word")) {
    document.querySelectorAll(".popover").forEach(p => p.remove());
  }
});
