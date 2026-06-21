async function loadVocab(q) {
  const url = q ? `/vocab?q=${encodeURIComponent(q)}` : "/vocab";
  const resp = await fetch(url);
  const data = await resp.json();
  const list = document.getElementById("vocab-list");
  if (data.vocab.length === 0) {
    list.innerHTML = '<p class="no-data">No words saved yet. Use the Reader or the "+ Add word" button above.</p>';
    return;
  }
  list.innerHTML = data.vocab.map(v => `
    <div class="vocab-item" data-id="${v.id}">
      <span class="lemma">${v.lemma}</span>
      <span class="status ${v.status}">${v.status}</span>
      <button class="edit-btn" title="Edit this word">Edit</button>
      <button class="delete-btn" title="Delete this word">Delete</button>
      <div class="detail">${v.reading || ""} — ${(v.meanings || []).join("; ")}</div>
    </div>
  `).join("");
}

async function deleteVocab(id) {
  const resp = await fetch(`/vocab/${id}`, { method: "DELETE" });
  return resp.ok;
}

async function editVocab(id, data) {
  const resp = await fetch(`/vocab/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return resp.ok ? await resp.json() : null;
}

function showEditForm(item) {
  if (item.querySelector(".vocab-edit-form")) return;
  var lemma = item.querySelector(".lemma").textContent;
  var detail = item.querySelector(".detail").textContent;
  var parts = detail.split(" — ");
  var reading = parts[0] || "";
  var meaning = parts.slice(1).join(" — ") || "";

  var form = document.createElement("form");
  form.className = "vocab-edit-form";
  form.innerHTML =
    '<div class="vocab-form-grid">' +
    '<input name="reading" type="text" value="' + reading.replace(/"/g, "&quot;") + '" placeholder="Reading">' +
    '<input name="meaning" type="text" value="' + meaning.replace(/"/g, "&quot;") + '" placeholder="Meanings (separate with ;)">' +
    '<input name="pos" type="text" placeholder="Part of speech (optional)">' +
    '</div>' +
    '<div class="vocab-form-actions">' +
    '<button type="submit" class="primary-btn">Save</button>' +
    '<button type="button" class="cancel-btn edit-cancel">Cancel</button>' +
    '</div>';

  item.appendChild(form);

  form.querySelector(".edit-cancel").addEventListener("click", function () {
    form.remove();
  });

  form.addEventListener("submit", async function (e) {
    e.preventDefault();
    var fd = new FormData(form);
    var body = {};
    if (fd.get("reading")) body.reading = fd.get("reading");
    if (fd.get("meaning")) body.meanings = fd.get("meaning").split(";").map(function (s) { return s.trim(); }).filter(Boolean);
    if (fd.get("pos")) body.pos = fd.get("pos");
    var updated = await editVocab(item.dataset.id, body);
    if (updated) {
      loadVocab(document.getElementById("search").value);
    } else {
      alert("Failed to update the word.");
    }
  });
}

document.getElementById("search").addEventListener("input", (e) => {
  loadVocab(e.target.value);
});

document.getElementById("vocab-list").addEventListener("click", async (e) => {
  var editBtn = e.target.closest(".edit-btn");
  if (editBtn) {
    showEditForm(editBtn.closest(".vocab-item"));
    return;
  }

  var deleteBtn = e.target.closest(".delete-btn");
  if (!deleteBtn) return;
  var item = deleteBtn.closest(".vocab-item");
  var lemma = item.querySelector(".lemma").textContent;
  if (!confirm('Delete "' + lemma + '" from your vocabulary? This also removes its review history.')) return;
  if (await deleteVocab(item.dataset.id)) {
    item.remove();
  } else {
    alert("Failed to delete the word.");
  }
});

// --- Manual add ---
var addToggle = document.getElementById("add-vocab-toggle");
var addForm = document.getElementById("add-vocab-form");
var addCancel = document.getElementById("add-vocab-cancel");
var addStatus = document.getElementById("add-vocab-status");

addToggle.addEventListener("click", function () {
  addForm.style.display = addForm.style.display === "none" ? "block" : "none";
  addToggle.style.display = addForm.style.display === "none" ? "" : "none";
});

addCancel.addEventListener("click", function () {
  addForm.style.display = "none";
  addToggle.style.display = "";
  addForm.reset();
  addStatus.textContent = "";
});

addForm.addEventListener("submit", async function (e) {
  e.preventDefault();
  var fd = new FormData(addForm);
  var meaningRaw = fd.get("meaning") || "";
  var body = {
    lemma: fd.get("lemma"),
    reading: fd.get("reading") || "",
    meanings: meaningRaw.split(";").map(function (s) { return s.trim(); }).filter(Boolean),
    pos: fd.get("pos") || "",
  };
  var resp = await fetch("/vocab", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (resp.ok) {
    var data = await resp.json();
    addStatus.className = "status-ok";
    addStatus.textContent = data.created ? "Word added!" : "Word already exists (updated count).";
    addForm.reset();
    loadVocab(document.getElementById("search").value);
  } else {
    addStatus.className = "status-error";
    addStatus.textContent = "Failed to add word.";
  }
});

loadVocab();
