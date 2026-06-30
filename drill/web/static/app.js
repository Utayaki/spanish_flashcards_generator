'use strict';

const app = document.getElementById('app');

const LEXICAL_ITEM_TYPE_LABELS = {
  noun: 'Noun',
  verb: 'Verb',
  adjective: 'Adjective',
  other: 'Other',
};

const state = {
  meta: null,
  stats: null,
  dueCounts: null,
  mode: 'random',
  drillType: null,
  sessionId: null,
  question: null,
  answers: {},
  checked: false,
  checkResult: null,
  loading: false,
  questionStartedAt: null,
  lastAttemptId: null,
};

function esc(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function typeLabel(lexicalItemType) {
  return LEXICAL_ITEM_TYPE_LABELS[lexicalItemType] || lexicalItemType;
}

function formatAccuracy(accuracy) {
  if (accuracy === null || accuracy === undefined) return '—';
  return `${Math.round(accuracy * 100)}%`;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
  });
  const data = await response.json().catch(() => ({ ok: false, error: 'Server returned invalid JSON.' }));
  if (!response.ok || !data.ok) {
    throw new Error(data.error || `HTTP ${response.status}`);
  }
  return data;
}

function feedbackClass(correct) {
  return correct ? 'feedback-correct' : 'feedback-wrong';
}

function renderFeedback(label, result) {
  if (!result) return '';
  const expected = Array.isArray(result.expected)
    ? result.expected.map(item => esc(item)).join('; ')
    : esc(result.expected);
  return `
    <div class="feedback-box ${feedbackClass(result.correct)}">
      <strong>${esc(label)}:</strong>
      ${result.correct ? 'Correct' : `Expected ${expected}`}
    </div>
  `;
}

function selectOptions(options, selectedValue, placeholder) {
  const items = options.map(
    option => `<option value="${esc(option.value)}"${option.value === selectedValue ? ' selected' : ''}>${esc(option.label)}</option>`,
  );
  if (placeholder) {
    items.unshift(`<option value="">${esc(placeholder)}</option>`);
  }
  return items.join('');
}

function verbGroupOptions(selected) {
  return selectOptions(state.meta.verb_groups.map(group => ({ value: group.code, label: group.label })), selected, 'Choose mood/group');
}

function isParticipleRecognition(question) {
  return question.metadata_kind === 'verb' && question.group_code === 'participle';
}

function verbParticipleTenseOptions(selected) {
  return selectOptions(
    state.meta.verb_participles.map(participle => ({ value: participle.tense_code, label: participle.tense_label })),
    selected,
    'Choose participle type',
  );
}

function verbTenseOptions(selected) {
  const tenses = [];
  for (const group of state.meta.verb_groups) {
    for (const tense of group.tenses) {
      tenses.push({ value: tense.code, label: `${group.label} · ${tense.label}` });
    }
  }
  return selectOptions(tenses, selected, 'Choose tense');
}

function verbPersonOptions(selected) {
  const persons = [];
  for (const group of state.meta.verb_groups) {
    for (const person of group.persons) {
      persons.push({ value: person.code, label: person.label });
    }
  }
  const unique = [];
  const seen = new Set();
  for (const person of persons) {
    if (seen.has(person.value)) continue;
    seen.add(person.value);
    unique.push(person);
  }
  return selectOptions(unique, selected, 'Choose person');
}

function defaultAnswers(question) {
  if (question.drill_type === 'inflection') {
    return { user_inflection_pattern: '', user_form: '' };
  }
  if (question.drill_type === 'verb_form') {
    return { user_form: '' };
  }
  if (question.drill_type === 'transform') {
    return { user_form: '' };
  }
  if (question.drill_type === 'recognition') {
    if (question.metadata_kind === 'number_gender') {
      return { user_translation: '', user_number: '', user_gender: '' };
    }
    if (isParticipleRecognition(question)) {
      return { user_translation: '', user_group_code: 'participle', user_tense_code: '', user_person_code: '' };
    }
    return { user_translation: '', user_group_code: '', user_tense_code: '', user_person_code: '' };
  }
  return { user_headword: '', user_form: '' };
}

function buildCheckPayload() {
  return {
    drill_card_id: state.question.drill_card_id,
    session_id: state.sessionId,
    response_ms: state.questionStartedAt
      ? Math.round(performance.now() - state.questionStartedAt)
      : null,
    answers: { ...state.answers },
  };
}

async function loadStats() {
  try {
    const data = await api('/api/drill/stats');
    state.stats = data.stats;
  } catch {
    state.stats = null;
  }
}

async function loadDueCount() {
  try {
    const data = await api('/api/drill/due-count');
    state.dueCounts = data;
  } catch {
    state.dueCounts = null;
  }
}

function suggestedRating(checkResult, responseMs) {
  if (!checkResult.correct) return 'again';
  if (responseMs > 12000) return 'hard';
  if (responseMs < 3000) return 'easy';
  return 'good';
}

async function init() {
  try {
    const data = await api('/api/meta');
    state.meta = data;
    await Promise.all([loadStats(), loadDueCount()]);
    renderHome();
  } catch (error) {
    app.innerHTML = `<section class="panel"><h1>Spanish Drill</h1><div class="error-box">${esc(error.message)}</div></section>`;
  }
}

function statsBlock() {
  if (!state.stats) return '';
  const overall = state.stats.overall;
  return `
    <div class="stats-card">
      <h2>Your stats</h2>
      <p><strong>${esc(String(overall.total_attempts))}</strong> attempts · <strong>${formatAccuracy(overall.accuracy)}</strong> accuracy</p>
    </div>
  `;
}

function dueCountBlock() {
  if (!state.dueCounts) return '';
  const dueReview = state.dueCounts.due_review_count ?? 0;
  const newCards = state.dueCounts.new_card_count ?? 0;
  const totalDue = dueReview + newCards;
  return `
    <div class="due-count-card">
      <h2>Today's Reviews</h2>
      <p><strong>${esc(String(dueReview))}</strong> due · <strong>${esc(String(newCards))}</strong> new cards available</p>
      ${totalDue > 0 ? '<button type="button" class="primary review-start-btn" id="start-reviews-btn">Start Today\'s Reviews</button>' : '<p class="muted">No cards due right now.</p>'}
    </div>
  `;
}

function renderHome() {
  state.mode = 'random';
  state.drillType = null;
  state.sessionId = null;
  state.question = null;
  state.checked = false;
  state.checkResult = null;
  state.questionStartedAt = null;
  state.lastAttemptId = null;
  const drillTypes = Object.keys(state.meta.drill_types);
  app.innerHTML = `
    <section class="panel">
      <div class="header-row">
        <h1>Spanish Drill</h1>
      </div>
      ${dueCountBlock()}
      ${statsBlock()}
      <p class="muted helper">Random practice — choose a drill type.</p>
      <div class="drill-type-grid" role="group" aria-label="Drill type">
        ${drillTypes.map(type => `
          <button type="button" class="drill-type-btn" data-type="${esc(type)}">
            <strong>${esc(state.meta.drill_types[type].button)}</strong>
            <span class="muted">${esc(state.meta.drill_types[type].description)}</span>
          </button>
        `).join('')}
      </div>
    </section>
  `;
  const startReviewsBtn = document.getElementById('start-reviews-btn');
  if (startReviewsBtn) {
    startReviewsBtn.addEventListener('click', startTodayReviews);
  }
  app.querySelectorAll('.drill-type-btn').forEach(button => {
    button.addEventListener('click', () => startDrill(button.dataset.type));
  });
}

function renderLoading() {
  app.innerHTML = `
    <section class="panel loading-panel">
      <h1>Spanish Drill</h1>
      <p class="muted">Loading…</p>
    </section>
  `;
}

function renderError(message, retryType) {
  app.innerHTML = `
    <section class="panel">
      <div class="header-row">
        <h1>Spanish Drill</h1>
        <button type="button" class="ghost" id="back-btn">Back</button>
      </div>
      <div class="error-box">${esc(message)}</div>
      <div class="action-row">
        ${retryType ? '<button type="button" class="primary" id="retry-btn">Try again</button>' : ''}
      </div>
    </section>
  `;
  document.getElementById('back-btn').addEventListener('click', renderHome);
  if (retryType) {
    document.getElementById('retry-btn').addEventListener('click', () => startDrill(retryType));
  }
}

async function startDrill(drillType) {
  state.mode = 'random';
  state.drillType = drillType;
  state.checked = false;
  state.checkResult = null;
  state.lastAttemptId = null;
  renderLoading();
  try {
    if (!state.sessionId) {
      const session = await api('/api/drill/sessions', {
        method: 'POST',
        body: JSON.stringify({
          mode: 'random',
          drill_type: drillType,
        }),
      });
      state.sessionId = session.session_id;
    }

    const data = await api(`/api/drill/random?type=${encodeURIComponent(drillType)}`);
    state.question = data.question;
    state.answers = defaultAnswers(state.question);
    state.questionStartedAt = performance.now();
    renderDrill();
  } catch (error) {
    renderError(error.message, drillType);
  }
}

async function startTodayReviews() {
  state.mode = 'review';
  state.drillType = null;
  state.checked = false;
  state.checkResult = null;
  state.lastAttemptId = null;
  state.sessionId = null;
  renderLoading();
  try {
    const session = await api('/api/drill/sessions', {
      method: 'POST',
      body: JSON.stringify({ mode: 'review' }),
    });
    state.sessionId = session.session_id;
    await loadNextReviewQuestion();
  } catch (error) {
    renderError(error.message, null);
  }
}

async function loadNextReviewQuestion() {
  renderLoading();
  try {
    const data = await api('/api/drill/review/next');
    state.dueCounts = data;

    if (data.done) {
      state.question = null;
      renderReviewDone(data);
      return;
    }

    state.question = data.question;
    state.answers = defaultAnswers(state.question);
    state.questionStartedAt = performance.now();
    state.checked = false;
    state.checkResult = null;
    state.lastAttemptId = null;
    renderDrill();
  } catch (error) {
    renderError(error.message, null);
  }
}

function renderReviewDone(data) {
  const newCards = data.new_card_count ?? 0;
  app.innerHTML = `
    <section class="panel">
      <div class="header-row">
        <h1>Today's Reviews</h1>
        <button type="button" class="ghost" id="back-btn">Back</button>
      </div>
      <div class="success-box">Done for now. Reviews completed.</div>
      <p class="helper">New cards remaining: <strong>${esc(String(newCards))}</strong></p>
    </section>
  `;
  document.getElementById('back-btn').addEventListener('click', async () => {
    if (state.sessionId) {
      try {
        await api(`/api/drill/sessions/${state.sessionId}/finish`, { method: 'POST', body: '{}' });
      } catch {
        // ignore finish errors on back navigation
      }
    }
    state.sessionId = null;
    await Promise.all([loadStats(), loadDueCount()]);
    renderHome();
  });
}

function renderDrill() {
  const question = state.question;
  const renderers = {
    inflection: renderInflectionDrill,
    verb_form: renderVerbFormDrill,
    transform: renderTransformDrill,
    recognition: renderRecognitionDrill,
    reverse: renderReverseDrill,
  };
  renderers[question.drill_type]();
  bindDrillActions();
}

function drillHeader(title) {
  return `
    <div class="header-row">
      <h1>${esc(title)}</h1>
      <button type="button" class="ghost" id="back-btn">Back</button>
    </div>
  `;
}

function actionRow() {
  if (state.mode === 'review' && state.checked) {
    return renderRatingButtons();
  }
  const nextLabel = state.checked ? 'Next' : 'Check';
  return `
    <div class="action-row">
      <button type="button" class="primary" id="primary-action-btn">${nextLabel}</button>
    </div>
  `;
}

function renderRatingButtons() {
  if (state.mode !== 'review' || !state.checked) {
    return '';
  }

  const responseMs = state.questionStartedAt
    ? Math.round(performance.now() - state.questionStartedAt)
    : null;
  const suggested = suggestedRating(state.checkResult, responseMs);

  const ratings = [
    { key: 'again', label: 'Again' },
    { key: 'hard', label: 'Hard' },
    { key: 'good', label: 'Good' },
    { key: 'easy', label: 'Easy' },
  ];

  return `
    <div class="rating-section">
      <p class="helper">How well did you remember it?</p>
      <div class="rating-row" role="group" aria-label="Rate recall difficulty">
        ${ratings.map(r => `
          <button
            type="button"
            class="rating-btn rating-${esc(r.key)}${r.key === suggested ? ' rating-suggested' : ''}"
            data-rating="${esc(r.key)}"
          >${esc(r.label)}</button>
        `).join('')}
      </div>
    </div>
  `;
}

async function rateCurrentCard(rating) {
  const reviewDurationMs = state.questionStartedAt
    ? Math.round(performance.now() - state.questionStartedAt)
    : null;

  try {
    await api('/api/drill/review/rate', {
      method: 'POST',
      body: JSON.stringify({
        drill_card_id: state.question.drill_card_id,
        attempt_id: state.lastAttemptId,
        rating,
        review_duration_ms: reviewDurationMs,
      }),
    });
    await loadNextReviewQuestion();
  } catch (error) {
    app.insertAdjacentHTML('beforeend', `<div class="error-box">${esc(error.message)}</div>`);
  }
}

function revealBlock() {
  if (!state.checked || !state.checkResult) return '';
  const reveal = state.checkResult.reveal;
  const overall = state.checkResult.correct
    ? '<div class="success-box">All correct.</div>'
    : '<div class="error-box">Some answers were incorrect.</div>';

  let details = '';
  if (reveal.explanations) {
    details = `
      <div class="reveal-card">
        <h3>All meanings</h3>
        <ul>${reveal.explanations.map(item => `<li>${esc(item)}</li>`).join('')}</ul>
      </div>
    `;
  } else if (reveal.explanation) {
    details = `<div class="reveal-card"><strong>Meaning:</strong> ${esc(reveal.explanation)}</div>`;
  }

  return `
    ${overall}
    <div class="reveal-card">
      ${reveal.headword ? `<div><strong>Headword:</strong> ${esc(reveal.headword)}</div>` : ''}
      ${reveal.lexical_item_type ? `<div><strong>Type:</strong> ${esc(typeLabel(reveal.lexical_item_type))}</div>` : ''}
      ${reveal.slot_label ? `<div><strong>Form slot:</strong> ${esc(reveal.slot_label)}</div>` : ''}
      ${reveal.source_slot_label ? `<div><strong>From:</strong> ${esc(reveal.source_slot_label)}</div>` : ''}
      ${reveal.target_slot_label ? `<div><strong>To:</strong> ${esc(reveal.target_slot_label)}</div>` : ''}
      ${reveal.context_label ? `<div><strong>Verb context:</strong> ${esc(reveal.context_label)}</div>` : ''}
      ${reveal.inflection_pattern ? `<div><strong>Inflection pattern:</strong> ${esc(reveal.inflection_pattern)}</div>` : ''}
      ${reveal.form ? `<div><strong>Form:</strong> ${esc(reveal.form)}</div>` : ''}
    </div>
    ${details}
  `;
}

function resultsBlock() {
  if (!state.checked || !state.checkResult) return '';
  const results = state.checkResult.results;
  return Object.entries(results).map(([key, result]) => {
    const label = key.replaceAll('_', ' ');
    return renderFeedback(label.charAt(0).toUpperCase() + label.slice(1), result);
  }).join('');
}

function renderInflectionDrill() {
  const question = state.question;
  app.innerHTML = `
    <section class="panel">
      ${drillHeader(state.meta.drill_types.inflection.button)}
      <div class="card">
        <h2>${esc(question.headword)}</h2>
        <span class="flashcard-type">${esc(typeLabel(question.lexical_item_type))}</span>
      </div>
      <div class="form-row">
        <label for="inflection-pattern">How does this word inflect?</label>
        <select id="inflection-pattern" ${state.checked ? 'disabled' : ''}>
          ${selectOptions(question.pattern_options, state.answers.user_inflection_pattern, 'Choose pattern')}
        </select>
      </div>
      <div class="form-row">
        <label for="inflection-form">Form (${esc(question.slot_label)})</label>
        <input id="inflection-form" type="text" autocomplete="off" spellcheck="false" value="${esc(state.answers.user_form)}" ${state.checked ? 'readonly' : ''}>
      </div>
      ${resultsBlock()}
      ${revealBlock()}
      ${actionRow()}
    </section>
  `;
}

function renderVerbFormDrill() {
  const question = state.question;
  app.innerHTML = `
    <section class="panel">
      ${drillHeader(state.meta.drill_types.verb_form.button)}
      <div class="card prompt-card">
        <h2 class="flashcard-headword">${esc(question.headword)}</h2>
        <p class="muted">Type the conjugated form for <strong>${esc(question.context_label)}</strong>.</p>
      </div>
      <div class="form-row">
        <label for="verb-form">${esc(question.context_label)}</label>
        <input
          id="verb-form"
          type="text"
          autocomplete="off"
          spellcheck="false"
          value="${esc(state.answers.user_form || '')}"
          ${state.checked ? 'readonly' : ''}
        >
      </div>
      ${resultsBlock()}
      ${revealBlock()}
      ${actionRow()}
    </section>
  `;
}

function renderTransformDrill() {
  const question = state.question;
  app.innerHTML = `
    <section class="panel">
      ${drillHeader(state.meta.drill_types.transform.button)}
      <div class="flashcard prompt-card">
        <h2 class="flashcard-headword">${esc(question.shown_form)}</h2>
        <span class="flashcard-type">${esc(typeLabel(question.lexical_item_type))}</span>
        <p class="muted">Currently: <strong>${esc(question.source_slot_label)}</strong></p>
      </div>
      <div class="form-row">
        <label for="transform-form">Type the ${esc(question.target_slot_label)} form</label>
        <input
          id="transform-form"
          type="text"
          autocomplete="off"
          spellcheck="false"
          value="${esc(state.answers.user_form || '')}"
          ${state.checked ? 'readonly' : ''}
        >
      </div>
      ${resultsBlock()}
      ${revealBlock()}
      ${actionRow()}
    </section>
  `;
}

function renderRecognitionDrill() {
  const question = state.question;
  let metadataFields;
  if (question.metadata_kind === 'number_gender') {
    metadataFields = `
      <div class="form-row">
        <label for="recognition-number">Number</label>
        <select id="recognition-number" ${state.checked ? 'disabled' : ''}>
          ${selectOptions(state.meta.numbers, state.answers.user_number, 'Choose number')}
        </select>
      </div>
      <div class="form-row">
        <label for="recognition-gender">Gender</label>
        <select id="recognition-gender" ${state.checked ? 'disabled' : ''}>
          ${selectOptions(state.meta.genders, state.answers.user_gender, 'Choose gender')}
        </select>
      </div>
    `;
  } else if (isParticipleRecognition(question)) {
    metadataFields = `
      <div class="form-row">
        <label>Mood / group</label>
        <p class="muted"><strong>${esc(question.group_label || 'Participles')}</strong></p>
        <input type="hidden" id="recognition-group" value="participle">
      </div>
      <div class="form-row">
        <label for="recognition-tense">Participle type</label>
        <select id="recognition-tense" ${state.checked ? 'disabled' : ''}>${verbParticipleTenseOptions(state.answers.user_tense_code)}</select>
      </div>
    `;
  } else {
    metadataFields = `
      <div class="form-row">
        <label for="recognition-group">Mood / group</label>
        <select id="recognition-group" ${state.checked ? 'disabled' : ''}>${verbGroupOptions(state.answers.user_group_code)}</select>
      </div>
      <div class="form-row">
        <label for="recognition-tense">Tense</label>
        <select id="recognition-tense" ${state.checked ? 'disabled' : ''}>${verbTenseOptions(state.answers.user_tense_code)}</select>
      </div>
      ${question.has_person ? `
      <div class="form-row">
        <label for="recognition-person">Person</label>
        <select id="recognition-person" ${state.checked ? 'disabled' : ''}>${verbPersonOptions(state.answers.user_person_code)}</select>
      </div>` : ''}
    `;
  }

  app.innerHTML = `
    <section class="panel">
      ${drillHeader(state.meta.drill_types.recognition.button)}
      <div class="flashcard prompt-card">
        <h2 class="flashcard-headword">${esc(question.shown_form)}</h2>
        <span class="flashcard-type">${esc(typeLabel(question.lexical_item_type))}</span>
      </div>
      <div class="form-row">
        <label for="recognition-translation">Translation</label>
        <input id="recognition-translation" type="text" autocomplete="off" spellcheck="false" value="${esc(state.answers.user_translation)}" ${state.checked ? 'readonly' : ''}>
      </div>
      ${metadataFields}
      ${resultsBlock()}
      ${revealBlock()}
      ${actionRow()}
    </section>
  `;
}

function renderReverseDrill() {
  const question = state.question;
  app.innerHTML = `
    <section class="panel">
      ${drillHeader(state.meta.drill_types.reverse.button)}
      <div class="card prompt-card">
        <p class="flashcard-translation">${esc(question.explanation)}</p>
        <span class="flashcard-type">${esc(typeLabel(question.lexical_item_type))}</span>
        <p class="helper">Give the <strong>${esc(question.slot_label)}</strong> form and the headword.</p>
      </div>
      <div class="form-row">
        <label for="reverse-headword">Headword</label>
        <input id="reverse-headword" type="text" autocomplete="off" spellcheck="false" value="${esc(state.answers.user_headword)}" ${state.checked ? 'readonly' : ''}>
      </div>
      <div class="form-row">
        <label for="reverse-form">Inflected form</label>
        <input id="reverse-form" type="text" autocomplete="off" spellcheck="false" value="${esc(state.answers.user_form)}" ${state.checked ? 'readonly' : ''}>
      </div>
      ${resultsBlock()}
      ${revealBlock()}
      ${actionRow()}
    </section>
  `;
}

function readAnswersFromDom() {
  const question = state.question;
  if (question.drill_type === 'inflection') {
    state.answers.user_inflection_pattern = document.getElementById('inflection-pattern').value;
    state.answers.user_form = document.getElementById('inflection-form').value;
    return;
  }
  if (question.drill_type === 'verb_form') {
    state.answers.user_form = document.getElementById('verb-form').value;
    return;
  }
  if (question.drill_type === 'transform') {
    state.answers.user_form = document.getElementById('transform-form').value;
    return;
  }
  if (question.drill_type === 'recognition') {
    state.answers.user_translation = document.getElementById('recognition-translation').value;
    if (question.metadata_kind === 'number_gender') {
      state.answers.user_number = document.getElementById('recognition-number').value;
      state.answers.user_gender = document.getElementById('recognition-gender').value;
    } else if (isParticipleRecognition(question)) {
      state.answers.user_group_code = 'participle';
      state.answers.user_tense_code = document.getElementById('recognition-tense').value;
      state.answers.user_person_code = '';
    } else {
      state.answers.user_group_code = document.getElementById('recognition-group').value;
      state.answers.user_tense_code = document.getElementById('recognition-tense').value;
      const personField = document.getElementById('recognition-person');
      state.answers.user_person_code = personField ? personField.value : '';
    }
    return;
  }
  state.answers.user_headword = document.getElementById('reverse-headword').value;
  state.answers.user_form = document.getElementById('reverse-form').value;
}

async function handlePrimaryAction() {
  if (state.checked) {
    if (state.mode === 'review') {
      return;
    }
    await startDrill(state.drillType);
    return;
  }
  readAnswersFromDom();
  try {
    const data = await api('/api/drill/check', {
      method: 'POST',
      body: JSON.stringify(buildCheckPayload()),
    });
    state.checked = true;
    state.checkResult = data;
    state.lastAttemptId = data.attempt_id ?? null;
    renderDrill();
  } catch (error) {
    app.insertAdjacentHTML('beforeend', `<div class="error-box">${esc(error.message)}</div>`);
  }
}

function bindDrillActions() {
  document.getElementById('back-btn').addEventListener('click', async () => {
    if (state.sessionId) {
      try {
        await api(`/api/drill/sessions/${state.sessionId}/finish`, { method: 'POST', body: '{}' });
      } catch {
        // ignore finish errors on back navigation
      }
    }
    state.sessionId = null;
    await Promise.all([loadStats(), loadDueCount()]);
    renderHome();
  });
  const primaryBtn = document.getElementById('primary-action-btn');
  if (primaryBtn) {
    primaryBtn.addEventListener('click', handlePrimaryAction);
  }
  app.querySelectorAll('.rating-btn').forEach(button => {
    button.addEventListener('click', () => rateCurrentCard(button.dataset.rating));
  });
  document.querySelector('.panel')?.addEventListener('keydown', event => {
    if (event.key !== 'Enter' || event.isComposing) return;
    if (!document.getElementById('primary-action-btn')) return;
    if (event.target.tagName === 'BUTTON') return;
    event.preventDefault();
    handlePrimaryAction();
  });
}

init();
