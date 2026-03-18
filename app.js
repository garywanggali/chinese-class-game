const state = {
  qa: [],
  mode: "mcq", // mcq | match
  mcq: {
    order: [],
    idx: 0,
    score: 0,
    locked: false,
    lastCorrect: null,
  },
  match: {
    size: 6,
    pairs: [],
    score: 0,
    lockedCount: 0,
    selectedLeft: null,
    selectedRight: null,
  },
};

function $(sel) {
  const el = document.querySelector(sel);
  if (!el) throw new Error(`Missing element: ${sel}`);
  return el;
}

function shuffle(arr) {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

function clamp(n, lo, hi) {
  return Math.max(lo, Math.min(hi, n));
}

function normalizeQA(qa) {
  const cleaned = [];
  const seen = new Set();
  for (const item of qa) {
    if (!item || typeof item.q !== "string" || typeof item.a !== "string") continue;
    const q = item.q.trim().replace(/\s+/g, " ");
    const a = item.a.trim().replace(/\s+/g, " ");
    if (!q || !a) continue;
    const key = `${q}::${a}`;
    if (seen.has(key)) continue;
    seen.add(key);
    cleaned.push({ q, a });
  }
  return cleaned;
}

function setMode(mode) {
  state.mode = mode;
  $("#tab-mcq").classList.toggle("active", mode === "mcq");
  $("#tab-match").classList.toggle("active", mode === "match");
  $("#mcqView").style.display = mode === "mcq" ? "" : "none";
  $("#matchView").style.display = mode === "match" ? "" : "none";
  if (mode === "mcq") renderMCQ();
  if (mode === "match") renderMatch(true);
}

function updateHeader() {
  $("#pill-total").textContent = `${state.qa.length} 题`;
  const mcq = state.mcq;
  $("#pill-progress").textContent = state.mode === "mcq"
    ? `${mcq.idx + 1}/${mcq.order.length}`
    : `配对：${state.match.lockedCount}/${state.match.pairs.length}`;
  $("#pill-score").textContent = state.mode === "mcq"
    ? `${mcq.score} 分`
    : `${state.match.score} 分`;
}

// ---------------- MCQ ----------------

function startMCQ() {
  state.mcq.order = shuffle(state.qa.map((_, i) => i));
  state.mcq.idx = 0;
  state.mcq.score = 0;
  state.mcq.locked = false;
  state.mcq.lastCorrect = null;
  renderMCQ();
}

function buildMCQOptions(correctIdx, optionCount = 4) {
  const correct = state.qa[correctIdx];
  const pool = state.qa
    .map((x, i) => ({ ...x, i }))
    .filter((x) => x.i !== correctIdx);
  const distractors = shuffle(pool).slice(0, Math.max(0, optionCount - 1));
  const options = shuffle([{ text: correct.a, idx: correctIdx }, ...distractors.map((d) => ({ text: d.a, idx: d.i }))]);
  return options;
}

function renderMCQ() {
  const { order, idx } = state.mcq;
  if (state.qa.length === 0) return;
  if (order.length === 0) startMCQ();

  const qIdx = order[clamp(idx, 0, order.length - 1)];
  const qa = state.qa[qIdx];
  $("#mcqQuestion").textContent = qa.q;
  $("#mcqHint").textContent = "从下面四个回答中选出最符合苏轼原话的一项。";

  const options = buildMCQOptions(qIdx, 4);
  const container = $("#mcqAnswers");
  container.innerHTML = "";
  state.mcq.locked = false;
  state.mcq.lastCorrect = qIdx;

  for (const opt of options) {
    const btn = document.createElement("button");
    btn.className = "choice";
    btn.type = "button";
    btn.textContent = opt.text;
    btn.addEventListener("click", () => onPickMCQ(btn, opt.idx === qIdx, qIdx));
    container.appendChild(btn);
  }

  $("#mcqExplain").textContent = "";
  $("#btnNext").disabled = true;
  updateHeader();
}

function onPickMCQ(btn, isCorrect, qIdx) {
  if (state.mcq.locked) return;
  state.mcq.locked = true;

  const buttons = [...$("#mcqAnswers").querySelectorAll("button.choice")];
  for (const b of buttons) b.disabled = true;

  if (isCorrect) {
    btn.classList.add("good");
    state.mcq.score += 1;
    $("#mcqExplain").innerHTML = `<strong>正确</strong>：${state.qa[qIdx].a}`;
  } else {
    btn.classList.add("bad");
    const correct = state.qa[qIdx].a;
    for (const b of buttons) {
      if (b.textContent === correct) b.classList.add("good");
    }
    $("#mcqExplain").innerHTML = `<strong>正确答案</strong>：${correct}`;
  }
  $("#btnNext").disabled = false;
  updateHeader();
}

function nextMCQ() {
  if (state.mcq.idx < state.mcq.order.length - 1) {
    state.mcq.idx += 1;
    renderMCQ();
    return;
  }
  $("#mcqQuestion").textContent = "本轮选择题已完成。";
  $("#mcqHint").textContent = "你可以点击“再来一轮”重新洗牌。";
  $("#mcqAnswers").innerHTML = "";
  $("#mcqExplain").innerHTML = `<strong>得分</strong>：${state.mcq.score} / ${state.mcq.order.length}`;
  $("#btnNext").disabled = true;
  updateHeader();
}

// ---------------- Match ----------------

function startMatch() {
  const size = clamp(parseInt($("#matchSize").value, 10) || 6, 3, 10);
  state.match.size = size;
  state.match.score = 0;
  state.match.lockedCount = 0;
  state.match.selectedLeft = null;
  state.match.selectedRight = null;

  const chosen = shuffle(state.qa).slice(0, Math.min(size, state.qa.length));
  state.match.pairs = chosen.map((x, i) => ({ id: `p${i}`, q: x.q, a: x.a, locked: false }));
  renderMatch(true);
}

function renderMatch(reset) {
  if (state.qa.length === 0) return;
  if (reset || state.match.pairs.length === 0) startMatch();

  const leftCol = $("#matchLeft");
  const rightCol = $("#matchRight");
  leftCol.innerHTML = "";
  rightCol.innerHTML = "";

  const left = state.match.pairs.map((p) => ({ id: p.id, text: p.q }));
  const right = shuffle(state.match.pairs.map((p) => ({ id: p.id, text: p.a })));

  for (const item of left) leftCol.appendChild(renderMatchItem("left", item));
  for (const item of right) rightCol.appendChild(renderMatchItem("right", item));

  $("#matchExplain").textContent = "玩法：先点左边一个问题，再点右边一个回答完成配对。";
  updateHeader();
}

function renderMatchItem(side, item) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "matchItem";
  btn.dataset.side = side;
  btn.dataset.id = item.id;
  btn.textContent = item.text;
  btn.addEventListener("click", () => onPickMatch(btn));
  return btn;
}

function clearSelections() {
  for (const el of document.querySelectorAll(".matchItem.selected")) el.classList.remove("selected");
  state.match.selectedLeft = null;
  state.match.selectedRight = null;
}

function lockPair(pairId, good) {
  const left = document.querySelector(`.matchItem[data-side="left"][data-id="${pairId}"]`);
  const right = document.querySelector(`.matchItem[data-side="right"][data-id="${pairId}"]`);
  if (left) {
    left.classList.add("locked", good ? "good" : "bad");
    left.disabled = true;
  }
  if (right) {
    right.classList.add("locked", good ? "good" : "bad");
    right.disabled = true;
  }
}

function onPickMatch(btn) {
  if (btn.classList.contains("locked")) return;
  const side = btn.dataset.side;
  const id = btn.dataset.id;

  btn.classList.toggle("selected");

  if (side === "left") {
    state.match.selectedLeft = btn.classList.contains("selected") ? id : null;
  } else {
    state.match.selectedRight = btn.classList.contains("selected") ? id : null;
  }

  // Ensure only one selection per side
  for (const other of document.querySelectorAll(`.matchItem[data-side="${side}"]`)) {
    if (other !== btn) other.classList.remove("selected");
  }

  if (state.match.selectedLeft && state.match.selectedRight) {
    const good = state.match.selectedLeft === state.match.selectedRight;
    if (good) state.match.score += 1;
    lockPair(state.match.selectedLeft, good);
    state.match.lockedCount += 1;

    if (!good) {
      $("#matchExplain").innerHTML = `<strong>不匹配</strong>：再试一次。`;
    } else {
      $("#matchExplain").innerHTML = `<strong>匹配成功</strong>：+1 分`;
    }

    clearSelections();
    updateHeader();

    if (state.match.lockedCount >= state.match.pairs.length) {
      $("#matchExplain").innerHTML = `<strong>本轮配对完成</strong>：得分 ${state.match.score} / ${state.match.pairs.length}。可点击“再来一轮”重新抽题。`;
    }
  }
}

// ---------------- Init ----------------

async function loadQA() {
  const res = await fetch("./data/qa.json", { cache: "no-store" });
  if (!res.ok) throw new Error(`加载题库失败：${res.status}`);
  const qa = await res.json();
  state.qa = normalizeQA(qa);
  if (state.qa.length < 4) throw new Error("题库题目过少，至少需要 4 题。");
  $("#pill-total").textContent = `${state.qa.length} 题`;
  startMCQ();
  renderMatch(true);
  setMode("mcq");
}

function wireUI() {
  $("#tab-mcq").addEventListener("click", () => setMode("mcq"));
  $("#tab-match").addEventListener("click", () => setMode("match"));

  $("#btnRestart").addEventListener("click", () => {
    if (state.mode === "mcq") startMCQ();
    else startMatch();
  });

  $("#btnNext").addEventListener("click", () => nextMCQ());
  window.addEventListener("keydown", (e) => {
    if (state.mode !== "mcq") return;
    if (e.key === "Enter") {
      if (!$("#btnNext").disabled) nextMCQ();
    }
  });

  $("#btnNewMatch").addEventListener("click", () => startMatch());
}

wireUI();
loadQA().catch((err) => {
  console.error(err);
  $("#app").innerHTML = `
    <div class="panel card">
      <p class="q">加载失败</p>
      <p class="hint">${String(err && err.message ? err.message : err)}</p>
      <p class="small">请确认已用本地服务器打开（例如 python -m http.server），并且存在 data/qa.json。</p>
    </div>
  `;
});

