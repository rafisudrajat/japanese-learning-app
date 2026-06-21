let queue = [];
let current = 0;

async function loadQueue() {
  const resp = await fetch("/review/queue");
  const data = await resp.json();
  queue = data.cards;
  current = 0;
  showCard();
}

function showCard() {
  const area = document.getElementById("review-area");
  if (current >= queue.length) {
    area.innerHTML = "<p>No cards due.</p>";
    return;
  }
  const c = queue[current];
  area.innerHTML = `
    <div class="review-card">
      <p class="review-word">${c.lemma}</p>
      <div id="answer" style="display:none">
        <p>${c.reading || ""}</p>
        <p>${(c.meanings || []).join("; ")}</p>
      </div>
      <button id="show-btn" onclick="document.getElementById('answer').style.display='block'; this.style.display='none'; document.getElementById('rating-btns').style.display='flex'">Show Answer</button>
      <div id="rating-btns" style="display:none; gap:0.5rem;">
        <button onclick="answer(1)">Again</button>
        <button onclick="answer(2)">Hard</button>
        <button onclick="answer(3)">Good</button>
        <button onclick="answer(4)">Easy</button>
      </div>
    </div>
  `;
}

async function answer(rating) {
  const c = queue[current];
  await fetch("/review/answer", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({card_db_id: c.card_db_id, rating})
  });
  current++;
  showCard();
}

loadQueue();
