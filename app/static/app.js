const $ = (id) => document.getElementById(id);
let generated = null;
let chartFamiliarity = null;
let chartActivity = null;

const FAM_LABELS = ['0 · Unknown', '1 · Seen', '2 · Familiar', '3 · Known', '4 · Confident', '5 · Expert'];
const FAM_COLORS = ['#f04438', '#f79009', '#eaaa08', '#17b26a', '#2e90fa', '#7a5af8'];

function toast(message) {
  const el = $('toast');
  el.textContent = message;
  el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), 2200);
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

function csvToArray(value) {
  return value.split(',').map(x => x.trim()).filter(Boolean);
}

function normalizeMeanings(data) {
  return Array.isArray(data.meanings) ? data.meanings : [];
}

function fillGeneratedForm(data) {
  generated = data;
  $('generatedPanel').classList.remove('hidden');
  $('g_input_text').value = data.input_text || '';
  $('g_type').value = data.type || '';
  $('g_pronunciation').value = data.pronunciation || '';
  $('g_difficulty').value = data.difficulty || 'medium';
  $('g_similar').value = (data.similar_expressions || []).join(', ');
  $('g_tags').value = (data.tags || []).join(', ');
  $('g_meanings').value = JSON.stringify(normalizeMeanings(data), null, 2);
}

function readGeneratedForm() {
  let meanings = [];
  try {
    meanings = JSON.parse($('g_meanings').value || '[]');
    if (!Array.isArray(meanings)) throw new Error('Meanings JSON must be an array.');
  } catch (e) {
    toast(`Invalid meanings JSON: ${e.message}`);
    throw e;
  }
  return {
    input_text: $('g_input_text').value.trim(),
    type: $('g_type').value.trim(),
    meanings,
    pronunciation: $('g_pronunciation').value.trim(),
    difficulty: $('g_difficulty').value.trim() || 'medium',
    similar_expressions: csvToArray($('g_similar').value),
    tags: csvToArray($('g_tags').value),
    familiarity: 0,
  };
}

async function generate() {
  const text = $('newText').value.trim();
  if (!text) return toast('Enter a word or phrase first.');
  $('generateBtn').disabled = true;
  $('generateBtn').textContent = 'Generating...';
  try {
    const data = await api('/api/vocab/generate', {
      method: 'POST',
      body: JSON.stringify({ text }),
    });
    fillGeneratedForm(data);
    toast('Generated. You can edit before saving.');
  } catch (e) {
    toast(e.message);
  } finally {
    $('generateBtn').disabled = false;
    $('generateBtn').textContent = 'Generate';
  }
}

async function save() {
  let payload;
  try { payload = readGeneratedForm(); } catch { return; }
  if (!payload.input_text) return toast('Word / phrase is required.');
  try {
    await api('/api/vocab', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    $('newText').value = '';
    $('generatedPanel').classList.add('hidden');
    toast('Saved.');
    loadVocab();
  } catch (e) {
    toast(e.message);
  }
}

function meaningsHtml(item) {
  const meanings = normalizeMeanings(item);
  if (!meanings.length) return '<p class="hint">No meanings recorded.</p>';
  return meanings.map((m, i) => `<div class="meaning">
    <strong>Meaning ${i + 1}${m.part_of_speech ? ` · ${escapeHtml(m.part_of_speech)}` : ''}</strong>
    ${m.english_meaning ? `<p>${escapeHtml(m.english_meaning)}</p>` : ''}
    ${m.chinese_translation ? `<p class="zh-translation">${escapeHtml(m.chinese_translation)}</p>` : ''}
    ${m.chinese_explanation ? `<p><strong>說明：</strong>${escapeHtml(m.chinese_explanation)}</p>` : ''}
    ${m.example_sentence ? `<p><strong>Example:</strong> ${escapeHtml(m.example_sentence)}</p>` : ''}
    ${m.example_translation ? `<p><strong>例句中譯：</strong>${escapeHtml(m.example_translation)}</p>` : ''}
    ${m.usage_note ? `<p><strong>Usage:</strong> ${escapeHtml(m.usage_note)}</p>` : ''}
  </div>`).join('');
}

function vocabCard(item) {
  const tags = (item.tags || []).map(t => `<span class="tag">${escapeHtml(t)}</span>`).join('');
  return `<article class="card" data-id="${item.id}">
    <h3>${escapeHtml(item.input_text)}</h3>
    <div class="meta">${escapeHtml(item.type || 'vocabulary')} · familiarity ${item.familiarity}/5 · next review ${item.next_review_at || 'today'}</div>
    ${meaningsHtml(item)}
    <div class="tags">${tags}</div>
    <div class="actions">
      <button class="secondary" onclick="editItem(${item.id})">Edit</button>
      <button class="danger" onclick="deleteItem(${item.id})">Delete</button>
    </div>
  </article>`;
}

async function loadVocab() {
  const search = $('searchBox')?.value.trim() || '';
  const query = search ? `?search=${encodeURIComponent(search)}` : '';
  try {
    const items = await api(`/api/vocab${query}`);
    $('vocabList').innerHTML = items.length ? items.map(vocabCard).join('') : '<div class="panel">No vocabulary yet.</div>';
  } catch (e) {
    toast(e.message);
  }
}

async function editItem(id) {
  try {
    const item = await api(`/api/vocab/${id}`);
    const meaningsRaw = prompt('Edit meanings JSON (array of objects):', JSON.stringify(normalizeMeanings(item), null, 2));
    if (meaningsRaw === null) return;
    let meanings;
    try { meanings = JSON.parse(meaningsRaw); } catch { return toast('Invalid meanings JSON.'); }
    if (!Array.isArray(meanings)) return toast('Meanings must be a JSON array.');
    await api(`/api/vocab/${id}`, {
      method: 'PUT',
      body: JSON.stringify({ meanings }),
    });
    toast('Updated.');
    loadVocab();
  } catch (e) {
    toast(e.message);
  }
}

async function deleteItem(id) {
  if (!confirm('Delete this vocabulary item?')) return;
  try {
    await api(`/api/vocab/${id}`, { method: 'DELETE' });
    toast('Deleted.');
    loadVocab();
  } catch (e) {
    toast(e.message);
  }
}

let currentTask = null;

async function loadReview() {
  try {
    currentTask = await api('/api/review/today');
  } catch {
    currentTask = null;
  }
  renderReview();
}

async function startReview() {
  $('summaryModal').classList.add('hidden');
  try {
    currentTask = await api('/api/review/daily', { method: 'POST' });
    renderReview();
  } catch (e) {
    toast(e.message);
  }
}

function renderReview() {
  if (!currentTask || currentTask.status === 'completed') {
    $('reviewTask').innerHTML = `<div class="panel">
      <h2>Daily Review</h2>
      <p class="hint" style="margin-bottom:16px">Questions are selected from words whose next review date is due. Lower familiarity means more frequent review.</p>
      <button onclick="startReview()">Start Review</button>
    </div>`;
    return;
  }

  const questions = currentTask.questions || [];
  if (questions.length === 0) {
    $('reviewTask').innerHTML = `<div class="panel">
      <h2>Daily Review</h2>
      <p style="margin-bottom:16px">No words are due for review. Add more vocabulary or wait until tomorrow.</p>
      <button onclick="startReview()">Try Again</button>
    </div>`;
    return;
  }

  const answered = questions.filter(q => q.is_correct !== null && q.is_correct !== undefined);
  const next = questions.find(q => q.is_correct === null || q.is_correct === undefined);
  if (!next) {
    showSummaryModal(currentTask.summary);
    return;
  }

  const total = questions.length;
  const correct = answered.filter(q => q.is_correct === true).length;
  const wrong = answered.filter(q => q.is_correct === false).length;
  const pct = Math.round((answered.length / total) * 100);

  $('reviewTask').innerHTML = `
    <div class="panel">
      <div class="review-progress">
        <span>Question ${answered.length + 1} of ${total}</span>
        <span><span class="correct">✓ ${correct}</span>&nbsp;&nbsp;<span class="wrong">✗ ${wrong}</span></span>
      </div>
      <div class="progress-bar"><div class="progress-fill" style="width:${pct}%"></div></div>
    </div>
    <article class="card" id="questionCard">
      <div class="meta">${escapeHtml(next.question_type.replace('_', ' '))}</div>
      <h3>${escapeHtml(next.question_text)}</h3>
      ${(next.options || []).map(opt =>
        `<button class="option" data-answer="${escapeHtml(opt)}" onclick="answerQuestion(${next.id}, this.dataset.answer)">${escapeHtml(opt)}</button>`
      ).join('')}
    </article>`;
}

async function answerQuestion(id, user_answer) {
  document.querySelectorAll('.option').forEach(b => b.disabled = true);
  try {
    const result = await api(`/api/review/questions/${id}/answer`, {
      method: 'POST',
      body: JSON.stringify({ user_answer }),
    });

    document.querySelectorAll('.option').forEach(btn => {
      if (btn.dataset.answer === result.correct_answer) btn.classList.add('option-correct');
      else if (btn.dataset.answer === user_answer && !result.is_correct) btn.classList.add('option-wrong');
    });

    const feedback = document.createElement('div');
    feedback.className = `result ${result.is_correct ? 'correct' : 'wrong'}`;
    feedback.textContent = result.is_correct
      ? 'Correct!'
      : `Wrong · Correct answer: ${result.correct_answer}`;
    document.getElementById('questionCard')?.appendChild(feedback);

    if (currentTask) {
      const q = currentTask.questions.find(q => q.id === id);
      if (q) q.is_correct = result.is_correct;
      currentTask.summary = result.summary;
    }

    setTimeout(() => {
      if (result.summary.completed) {
        showSummaryModal(result.summary);
      } else {
        renderReview();
      }
    }, result.is_correct ? 1000 : 2000);

    loadVocab();
  } catch (e) {
    document.querySelectorAll('.option').forEach(b => b.disabled = false);
    toast(e.message);
  }
}

function showSummaryModal(summary) {
  if (!summary) return;
  $('modalContent').innerHTML = `<div class="summary-grid">
    <div class="summary-cell"><strong>${summary.answered_questions}</strong>Answered</div>
    <div class="summary-cell"><strong>${summary.correct_count}</strong>Correct</div>
    <div class="summary-cell"><strong>${summary.incorrect_count}</strong>Incorrect</div>
    <div class="summary-cell"><strong>${summary.words_improved}</strong>Improved</div>
    <div class="summary-cell"><strong>${escapeHtml(summary.time_spent_display)}</strong>Time</div>
  </div>`;
  $('summaryModal').classList.remove('hidden');
  $('reviewTask').innerHTML = '';
}

function closeSummaryModal() {
  $('summaryModal').classList.add('hidden');
  currentTask = null;
  renderReview();
}

// ── Home ─────────────────────────────────────────────────────────────────────

function destroyCharts() {
  if (chartFamiliarity) { chartFamiliarity.destroy(); chartFamiliarity = null; }
  if (chartActivity)    { chartActivity.destroy();    chartActivity    = null; }
}

async function loadHome() {
  destroyCharts();
  try {
    const stats = await api('/api/home/stats');
    renderFamiliarityChart(stats.familiarity_distribution);
    renderActivityChart(stats.activity);
    renderNeedsPractice(stats.needs_practice);
  } catch (e) {
    toast(e.message);
  }
}

function renderFamiliarityChart(dist) {
  const total = dist.reduce((a, b) => a + b, 0);
  const wrap = $('chartFamiliarity').parentElement;
  if (total === 0) {
    wrap.innerHTML = '<p class="home-empty">No vocabulary yet — add some words to see the chart.</p>';
    return;
  }
  chartFamiliarity = new Chart($('chartFamiliarity'), {
    type: 'pie',
    data: {
      labels: FAM_LABELS,
      datasets: [{ data: dist, backgroundColor: FAM_COLORS, borderWidth: 2, borderColor: '#fff' }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: 'bottom', labels: { font: { size: 12 }, padding: 10, boxWidth: 14 } },
        tooltip: { callbacks: { label: ctx => ` ${ctx.parsed} word${ctx.parsed !== 1 ? 's' : ''}` } },
      },
    },
  });
}

function renderActivityChart(activity) {
  const hasData = activity.added.some(v => v > 0)
               || activity.improved.some(v => v > 0)
               || activity.expert.some(v => v > 0);
  const wrap = $('chartActivity').parentElement;
  if (!hasData) {
    wrap.innerHTML = '<p class="home-empty">No activity in the last 30 days.</p>';
    return;
  }
  const displayLabels = activity.labels.map(d => {
    const dt = new Date(d + 'T00:00:00');
    return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  });
  chartActivity = new Chart($('chartActivity'), {
    type: 'line',
    data: {
      labels: displayLabels,
      datasets: [
        { label: 'Added',         data: activity.added,    borderColor: '#2f5bea', backgroundColor: 'rgba(47,91,234,0.08)',   tension: 0.3, fill: true, pointRadius: 2 },
        { label: 'Improved',      data: activity.improved, borderColor: '#17b26a', backgroundColor: 'rgba(23,178,106,0.08)',  tension: 0.3, fill: true, pointRadius: 2 },
        { label: 'Reached Expert',data: activity.expert,   borderColor: '#7a5af8', backgroundColor: 'rgba(122,90,248,0.08)', tension: 0.3, fill: true, pointRadius: 2 },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      scales: {
        x: { ticks: { maxTicksLimit: 10, maxRotation: 0, font: { size: 11 } }, grid: { color: 'rgba(0,0,0,0.04)' } },
        y: { beginAtZero: true, ticks: { precision: 0, font: { size: 11 } }, grid: { color: 'rgba(0,0,0,0.04)' } },
      },
      plugins: {
        legend: { position: 'bottom', labels: { font: { size: 12 }, padding: 10, boxWidth: 14 } },
      },
    },
  });
}

function renderNeedsPractice(words) {
  const el = $('needsPracticeGrid');
  if (!words.length) {
    el.innerHTML = '<p class="home-empty">No words at familiarity 0 or 1 — great work!</p>';
    return;
  }
  el.innerHTML = words.map(w => {
    const meanings = normalizeMeanings(w);
    const multi = meanings.length > 1;
    const meaningsHtml = meanings.map((m, i) => {
      const head = multi
        ? `<div class="practice-meaning-head">${i + 1}.${m.part_of_speech ? ` <span class="practice-pos">${escapeHtml(m.part_of_speech)}</span>` : ''}</div>`
        : (m.part_of_speech ? `<div class="practice-meaning-head"><span class="practice-pos">${escapeHtml(m.part_of_speech)}</span></div>` : '');
      return `<div class="practice-meaning">
        ${head}
        ${m.chinese_translation ? `<div class="practice-zh-translation">${escapeHtml(m.chinese_translation)}</div>` : ''}
        ${m.english_meaning ? `<div class="practice-line"><span class="practice-label">EN</span> ${escapeHtml(m.english_meaning)}</div>` : ''}
        ${m.chinese_explanation ? `<div class="practice-line"><span class="practice-label">中</span> ${escapeHtml(m.chinese_explanation)}</div>` : ''}
        ${m.example_sentence ? `<div class="practice-example">“${escapeHtml(m.example_sentence)}”${m.example_translation ? `<div class="practice-example-zh">${escapeHtml(m.example_translation)}</div>` : ''}</div>` : ''}
      </div>`;
    }).join('');
    return `<div class="practice-card">
      <div class="practice-head">
        <span class="word">${escapeHtml(w.input_text)}</span>
        ${w.type ? `<span class="practice-pos">${escapeHtml(w.type)}</span>` : ''}
        <span class="fam-badge">familiarity ${w.familiarity}/5</span>
      </div>
      ${meaningsHtml || '<p class="hint">No meanings recorded.</p>'}
    </div>`;
  }).join('');
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, ch => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
  }[ch]));
}

function setupTabs() {
  document.querySelectorAll('nav button').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('nav button').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
      btn.classList.add('active');
      $(`tab-${btn.dataset.tab}`).classList.add('active');
      if (btn.dataset.tab === 'home')       loadHome();
      if (btn.dataset.tab === 'list')       loadVocab();
      if (btn.dataset.tab === 'flashcards') loadFlashcards();
      if (btn.dataset.tab === 'review')     loadReview();
    });
  });
}

/* ---------- Flashcards ---------- */
let flashcardDeck = [];
let flashcardIndex = 0;

async function loadFlashcards() {
  try {
    const items = await api('/api/vocab');
    // Least familiar first; tie-break by oldest last_reviewed_at (or never reviewed) so stale words surface.
    flashcardDeck = items.slice().sort((a, b) => {
      const fa = a.familiarity ?? 0;
      const fb = b.familiarity ?? 0;
      if (fa !== fb) return fa - fb;
      const la = a.last_reviewed_at || '';
      const lb = b.last_reviewed_at || '';
      return la.localeCompare(lb);
    });
    flashcardIndex = 0;
    renderFlashcard();
  } catch (e) {
    toast(e.message);
  }
}

function renderFlashcard() {
  const card = $('flashcard');
  card.classList.remove('flipped');
  const count = $('flashcardCount');
  const famLabel = $('flashcardFam');
  if (!flashcardDeck.length) {
    $('flashcardWord').textContent = 'No vocabulary yet';
    $('flashcardBack').innerHTML = '<div class="flashcard-empty">Add some words on the Add tab first.</div>';
    count.textContent = '0 / 0';
    famLabel.textContent = '';
    return;
  }
  const w = flashcardDeck[flashcardIndex];
  count.textContent = `${flashcardIndex + 1} / ${flashcardDeck.length}`;
  famLabel.textContent = `familiarity ${w.familiarity}/5`;
  $('flashcardWord').textContent = w.input_text;

  const meanings = normalizeMeanings(w);
  const multi = meanings.length > 1;
  const meaningsHtml = meanings.map((m, i) => {
    const headParts = [];
    if (multi) headParts.push(`${i + 1}.`);
    if (m.part_of_speech) headParts.push(escapeHtml(m.part_of_speech));
    const head = headParts.length ? `<div class="flashcard-meaning-head">${headParts.join(' ')}</div>` : '';
    return `<div class="flashcard-meaning">
      ${head}
      ${m.chinese_translation ? `<div class="flashcard-zh-translation">${escapeHtml(m.chinese_translation)}</div>` : ''}
      ${m.english_meaning ? `<div class="flashcard-line"><strong>EN</strong>${escapeHtml(m.english_meaning)}</div>` : ''}
      ${m.chinese_explanation ? `<div class="flashcard-line"><strong>說明</strong>${escapeHtml(m.chinese_explanation)}</div>` : ''}
      ${m.example_sentence ? `<div class="flashcard-example">“${escapeHtml(m.example_sentence)}”${m.example_translation ? `<div class="flashcard-example-zh">${escapeHtml(m.example_translation)}</div>` : ''}</div>` : ''}
      ${m.usage_note ? `<div class="flashcard-line"><strong>Use</strong>${escapeHtml(m.usage_note)}</div>` : ''}
    </div>`;
  }).join('');
  $('flashcardBack').innerHTML = meaningsHtml || '<div class="flashcard-empty">No meanings recorded.</div>';
}

function flipFlashcard() {
  if (!flashcardDeck.length) return;
  $('flashcard').classList.toggle('flipped');
}

function nextFlashcard() {
  if (!flashcardDeck.length) return;
  flashcardIndex = (flashcardIndex + 1) % flashcardDeck.length;
  renderFlashcard();
}

function prevFlashcard() {
  if (!flashcardDeck.length) return;
  flashcardIndex = (flashcardIndex - 1 + flashcardDeck.length) % flashcardDeck.length;
  renderFlashcard();
}

// Keyboard shortcuts when the Flashcards tab is active.
document.addEventListener('keydown', e => {
  if (!$('tab-flashcards').classList.contains('active')) return;
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
  if (e.key === 'ArrowRight') { nextFlashcard(); e.preventDefault(); }
  else if (e.key === 'ArrowLeft') { prevFlashcard(); e.preventDefault(); }
  else if (e.key === ' ' || e.key === 'Enter') { flipFlashcard(); e.preventDefault(); }
});

$('generateBtn').addEventListener('click', generate);
$('saveBtn').addEventListener('click', save);
$('searchBtn').addEventListener('click', loadVocab);
$('clearSearchBtn').addEventListener('click', () => { $('searchBox').value = ''; loadVocab(); });
setupTabs();
loadHome();
