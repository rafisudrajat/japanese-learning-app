let quizType = "meaning";

document.querySelectorAll(".quiz-type-tabs .tab").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".quiz-type-tabs .tab").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    quizType = btn.dataset.type;
    loadQuestion();
  });
});

async function loadQuestion() {
  const area = document.getElementById("quiz-area");
  area.innerHTML = "<p>Loading...</p>";
  const resp = await fetch(`/quiz/next?type=${quizType}`);
  if (!resp.ok) {
    const err = await resp.json();
    area.innerHTML = `<p class="status-error">${err.detail || "Not enough vocabulary for a quiz."}</p>`;
    return;
  }
  const q = await resp.json();
  renderQuestion(q);
}

function renderQuestion(q) {
  const area = document.getElementById("quiz-area");
  let html = '<div class="quiz-card">';
  if (q.context_html) {
    html += `<div class="quiz-context">${q.context_html}</div>`;
  }
  html += `<p class="quiz-prompt">${q.prompt}</p>`;
  html += '<div class="quiz-choices">';
  q.choices.forEach((choice, i) => {
    html += `<button class="quiz-choice" data-index="${i}">${choice}</button>`;
  });
  html += '</div>';
  html += '<div id="quiz-feedback"></div>';
  html += '</div>';
  area.innerHTML = html;

  area.querySelectorAll(".quiz-choice").forEach(btn => {
    btn.addEventListener("click", () => submitAnswer(q.question_id, parseInt(btn.dataset.index), q.choices));
  });
}

async function submitAnswer(questionId, choiceIndex, choices) {
  document.querySelectorAll(".quiz-choice").forEach(b => { b.disabled = true; });

  const resp = await fetch("/quiz/answer", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({question_id: questionId, choice_index: choiceIndex})
  });
  if (!resp.ok) {
    document.getElementById("quiz-feedback").innerHTML = '<p class="status-error">Error submitting answer.</p>';
    return;
  }
  const result = await resp.json();

  document.querySelectorAll(".quiz-choice").forEach(btn => {
    const idx = parseInt(btn.dataset.index);
    if (idx === result.correct_index) {
      btn.classList.add("correct");
    } else if (idx === choiceIndex && !result.correct) {
      btn.classList.add("wrong");
    }
  });

  const feedback = document.getElementById("quiz-feedback");
  if (result.correct) {
    feedback.innerHTML = '<p class="status-ok">Correct!</p>';
  } else {
    feedback.innerHTML = `<p class="status-error">Incorrect. The answer is: ${result.correct_answer}</p>`;
  }
  feedback.innerHTML += '<button class="primary-btn" id="next-btn">Next</button>';
  document.getElementById("next-btn").addEventListener("click", loadQuestion);
}

loadQuestion();
