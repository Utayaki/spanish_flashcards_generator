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
  drillType: null,
  question: null,
  answers: {},
  checked: false,
  checkResult: null,
  loading: false,
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
    const userForms = {};
    for (const slot of question.slots) {
      userForms[slot.verb_form_code] = '';
    }
    return { user_forms: userForms };
  }
  if (question.drill_type === 'recognition') {
    if (question.metadata_kind === 'number_gender') {
      return { user_translation: '', user_number: '', user_gender: '' };
    }
    return { user_translation: '', user_group_code: '', user_tense_code: '', user_person_code: '' };
  }
  return { user_headword: '', user_form: '' };
}

function buildCheckPayload() {
  const question = state.question;
  const payload = { drill_type: question.drill_type, ...question, ...state.answers };
  const keysToOmit = ['pattern_options', 'context_label', 'slot_label', 'has_gender', 'group_label', 'tense_label', 'person_label'];
  for (const key of keysToOmit) {
    delete payload[key];
  }
  return payload;
}

async function init() {
  try {
    const data = await api('/api/meta');
    state.meta = data;
    renderHome();
  } catch (error) {
    app.innerHTML = `<section class="panel"><h1>Spanish Drill</h1><div class="error-box">${esc(error.message)}</div></section>`;
  }
}

function renderHome() {
  state.drillType = null;
  state.question = null;
  state.checked = false;
  state.checkResult = null;
  const drillTypes = Object.keys(state.meta.drill_types);
  app.innerHTML = `
    <section class="panel">
      <div class="header-row">
        <h1>Spanish Drill</h1>
      </div>
      <p class="muted helper">Choose a drill type to practice.</p>
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
  state.drillType = drillType;
  state.checked = false;
  state.checkResult = null;
  renderLoading();
  try {
    const data = await api(`/api/drill/random?type=${encodeURIComponent(drillType)}`);
    state.question = data.question;
    state.answers = defaultAnswers(state.question);
    renderDrill();
  } catch (error) {
    renderError(error.message, drillType);
  }
}

function renderDrill() {
  const question = state.question;
  const renderers = {
    inflection: renderInflectionDrill,
    verb_form: renderVerbFormDrill,
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
  const nextLabel = state.checked ? 'Next' : 'Check';
  return `
    <div class="action-row">
      <button type="button" class="primary" id="primary-action-btn">${nextLabel}</button>
    </div>
  `;
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

  let verbFormsReveal = '';
  if (reveal.forms) {
    verbFormsReveal = `
      <div class="reveal-card">
        <h3>Correct forms</h3>
        <ul>${reveal.forms.map(item => `<li><strong>${esc(item.context_label)}:</strong> ${esc(item.form)}</li>`).join('')}</ul>
      </div>
    `;
  }

  return `
    ${overall}
    <div class="reveal-card">
      ${reveal.headword ? `<div><strong>Headword:</strong> ${esc(reveal.headword)}</div>` : ''}
      ${reveal.lexical_item_type ? `<div><strong>Type:</strong> ${esc(typeLabel(reveal.lexical_item_type))}</div>` : ''}
      ${reveal.slot_label ? `<div><strong>Form slot:</strong> ${esc(reveal.slot_label)}</div>` : ''}
      ${reveal.context_label ? `<div><strong>Verb context:</strong> ${esc(reveal.context_label)}</div>` : ''}
      ${reveal.inflection_pattern ? `<div><strong>Inflection pattern:</strong> ${esc(reveal.inflection_pattern)}</div>` : ''}
      ${reveal.form ? `<div><strong>Form:</strong> ${esc(reveal.form)}</div>` : ''}
    </div>
    ${verbFormsReveal}
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
  const slotFields = question.slots.map(slot => `
    <div class="form-row">
      <label for="verb-form-${esc(slot.verb_form_code)}">${esc(slot.context_label)}</label>
      <input
        id="verb-form-${esc(slot.verb_form_code)}"
        type="text"
        autocomplete="off"
        spellcheck="false"
        value="${esc(state.answers.user_forms[slot.verb_form_code] || '')}"
        ${state.checked ? 'readonly' : ''}
      >
    </div>
  `).join('');

  app.innerHTML = `
    <section class="panel">
      ${drillHeader(state.meta.drill_types.verb_form.button)}
      <div class="card prompt-card">
        <h2 class="flashcard-headword">${esc(question.headword)}</h2>
        <p class="muted">Type ${esc(String(question.form_count))} conjugated form${question.form_count === 1 ? '' : 's'}.</p>
      </div>
      ${slotFields}
      ${resultsBlock()}
      ${revealBlock()}
      ${actionRow()}
    </section>
  `;
}

function renderRecognitionDrill() {
  const question = state.question;
  const metadataFields = question.metadata_kind === 'number_gender'
    ? `
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
    `
    : `
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
    state.answers.user_forms = {};
    for (const slot of question.slots) {
      const field = document.getElementById(`verb-form-${slot.verb_form_code}`);
      state.answers.user_forms[slot.verb_form_code] = field ? field.value : '';
    }
    return;
  }
  if (question.drill_type === 'recognition') {
    state.answers.user_translation = document.getElementById('recognition-translation').value;
    if (question.metadata_kind === 'number_gender') {
      state.answers.user_number = document.getElementById('recognition-number').value;
      state.answers.user_gender = document.getElementById('recognition-gender').value;
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

function bindDrillActions() {
  document.getElementById('back-btn').addEventListener('click', renderHome);
  document.getElementById('primary-action-btn').addEventListener('click', async () => {
    if (state.checked) {
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
      renderDrill();
    } catch (error) {
      app.insertAdjacentHTML('beforeend', `<div class="error-box">${esc(error.message)}</div>`);
    }
  });
}

init();
