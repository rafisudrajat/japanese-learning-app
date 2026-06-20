document.querySelectorAll(".tab").forEach(tab => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
    tab.classList.add("active");
    document.querySelectorAll(".import-panel").forEach(p => p.style.display = "none");
    document.getElementById(tab.dataset.tab + "-panel").style.display = "block";
  });
});

function showStatus(msg, isError) {
  const el = document.getElementById("status-msg");
  el.textContent = msg;
  el.className = isError ? "status-error" : "status-ok";
}

function renderCandidates(candidates) {
  const area = document.getElementById("candidates-area");
  if (candidates.length === 0) {
    area.innerHTML = '<p class="no-data">No new vocabulary found in this text.</p>';
    return;
  }
  area.innerHTML = `
    <h2>New vocabulary (${candidates.length} words)</h2>
    <div class="candidate-actions">
      <button id="keep-all-btn" class="primary-btn">Keep all</button>
    </div>
    <div id="candidate-list">
      ${candidates.map((c, i) => `
        <div class="candidate" data-index="${i}">
          <div class="candidate-word">
            <strong>${c.lemma}</strong>
            <span class="freq-badge">${c.frequency}x</span>
          </div>
          <div class="candidate-detail">${c.reading} — ${c.meanings.slice(0, 3).join("; ") || "(no entry)"}</div>
          <div class="candidate-btns">
            <button class="keep-btn" onclick="triageWord(${i}, 'keep')">Keep</button>
            <button class="know-btn" onclick="triageWord(${i}, 'known')">Already know</button>
          </div>
        </div>
      `).join("")}
    </div>
  `;
  document.getElementById("keep-all-btn").addEventListener("click", keepAll);
}

let currentCandidates = [];

async function triageWord(index, decision) {
  const c = currentCandidates[index];
  if (!c) return;
  await fetch("/triage", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      lemma: c.lemma,
      reading: c.reading,
      meaning: c.meanings[0] || "",
      pos: c.pos,
      decision,
    }),
  });
  const el = document.querySelectorAll(".candidate")[index];
  const btns = el.querySelector(".candidate-btns");
  btns.innerHTML = decision === "keep"
    ? '<span class="triaged kept">Added to review</span>'
    : '<span class="triaged known-mark">Marked as known</span>';
}

async function keepAll() {
  const candidates = document.querySelectorAll(".candidate");
  for (let i = 0; i < currentCandidates.length; i++) {
    const btns = candidates[i].querySelector(".candidate-btns");
    if (btns.querySelector(".triaged")) continue;
    await triageWord(i, "keep");
  }
}

async function doImport(endpoint, body) {
  showStatus("Importing...", false);
  document.getElementById("candidates-area").innerHTML = "";
  try {
    const resp = await fetch(endpoint, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body),
    });
    if (!resp.ok) {
      const err = await resp.text();
      showStatus("Import failed: " + err, true);
      return;
    }
    const data = await resp.json();
    currentCandidates = data.candidates;
    showStatus(`Imported: ${data.tokens.length} tokens, ${data.candidates.length} new words`, false);
    renderCandidates(data.candidates);
  } catch (e) {
    showStatus("Error: " + e.message, true);
  }
}

document.getElementById("paste-btn").addEventListener("click", () => {
  const title = document.getElementById("paste-title").value || "Pasted text";
  const text = document.getElementById("paste-text").value;
  if (!text.trim()) { showStatus("Please paste some text first.", true); return; }
  doImport("/import/paste", {title, text});
});

document.getElementById("url-btn").addEventListener("click", () => {
  const url = document.getElementById("url-input").value;
  if (!url.trim()) { showStatus("Please enter a URL.", true); return; }
  doImport("/import/url", {url});
});
