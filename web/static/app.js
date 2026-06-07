'use strict';

const app = document.getElementById('app');
const state = {
  meta: null,
  selectedType: null,
  query: '',
  results: [],
  searching: false,
  searchTimer: null,
  editor: null,
};

const CELL_REQUIRED_MESSAGE = 'Every cell must be filled or explicitly marked None.';

const LEMMA_TYPE_LABELS = {
  noun: 'Noun',
  verb: 'Verb',
  adjective: 'Adjective',
  other: 'Other',
};

function esc(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function debounceSearch() {
  clearTimeout(state.searchTimer);
  state.searchTimer = setTimeout(runSearch, 140);
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

async function init() {
  try {
    const data = await api('/api/meta');
    state.meta = data;
    renderHome();
  } catch (error) {
    app.innerHTML = `<section class="panel"><h1>Spanish Lemma DB</h1><div class="error-box">${esc(error.message)}</div></section>`;
  }
}

function renderHome() {
  state.editor = null;
  const lemmaTypes = Object.keys(state.meta.lemma_types);
  app.innerHTML = `
    <section class="panel">
      <div class="header-row">
        <h1>Spanish Lemma DB</h1>
      </div>
      <div class="lemma-type-grid" role="group" aria-label="Lemma class">
        ${lemmaTypes.map(type => `<button type="button" data-type="${esc(type)}" class="${state.selectedType === type ? 'active' : ''}">${esc(state.meta.lemma_types[type].button)}</button>`).join('')}
      </div>
      <div id="entry-panel" class="${state.selectedType ? '' : 'hidden'}">
        <div class="card">
          <h2 id="selected-class">${state.selectedType ? esc(state.meta.lemma_types[state.selectedType].button) : ''}</h2>
          <div class="form-row">
            <label for="lemma-search">Lemma</label>
            <input id="lemma-search" type="text" autocomplete="off" spellcheck="false" value="${esc(state.query)}" placeholder="Type a Spanish lemma">
          </div>
          <div class="results-title" id="results-title">${state.selectedType ? `Already added ${esc(state.meta.lemma_types[state.selectedType].plural)}` : ''}</div>
          <div id="search-results" class="search-results"></div>
          <div class="action-row" style="margin-top: 14px;">
            <button id="create-button" class="primary" type="button">Create</button>
          </div>
        </div>
      </div>
    </section>`;

  document.querySelectorAll('[data-type]').forEach(button => {
    button.addEventListener('click', () => selectType(button.dataset.type));
  });

  const input = document.getElementById('lemma-search');
  if (input) {
    input.addEventListener('input', () => {
      state.query = input.value;
      state.searching = Boolean(state.query.trim());
      state.results = [];
      renderSearchResults();
      updateCreateButton();
      if (state.query.trim()) debounceSearch();
    });
    input.addEventListener('keydown', event => {
      if (event.key === 'Enter') {
        event.preventDefault();
        const exact = findExactMatch();
        if (exact) openLemma(exact.id);
        else createDraft();
      }
    });
    input.focus();
    input.setSelectionRange(input.value.length, input.value.length);
  }

  document.getElementById('create-button')?.addEventListener('click', createDraft);
  renderSearchResults();
  updateCreateButton();
}

function selectType(type) {
  state.selectedType = type;
  state.query = '';
  state.results = [];
  state.searching = false;
  clearTimeout(state.searchTimer);
  renderHome();
}

async function runSearch() {
  const type = state.selectedType;
  const query = state.query.trim();
  if (!type || !query) return;
  state.searching = true;
  renderSearchResults();
  try {
    const data = await api(`/api/search?lemma_type=${encodeURIComponent(type)}&q=${encodeURIComponent(query)}`);
    if (state.selectedType === type && state.query.trim() === query) {
      state.results = data.results;
      state.searching = false;
      renderSearchResults();
      updateCreateButton();
    }
  } catch (error) {
    state.searching = false;
    const results = document.getElementById('search-results');
    if (results) results.innerHTML = `<div class="error-box">${esc(error.message)}</div>`;
  }
}

function renderSearchResults() {
  const box = document.getElementById('search-results');
  if (!box) return;
  if (!state.query.trim()) {
    box.innerHTML = '<p class="muted">None</p>';
    return;
  }
  if (state.searching) {
    box.innerHTML = '<p class="muted">Searching…</p>';
    return;
  }
  if (!state.results.length) {
    box.innerHTML = '<p class="muted">None</p>';
    return;
  }
  box.innerHTML = state.results.map(result => `
    <div class="search-result" data-lemma-id="${Number(result.id)}">
      <div class="search-result-main" tabindex="0" role="button">
        <strong>${highlightMatch(result.lemma, state.query)}</strong>
        ${result.english ? `<span class="muted">${esc(result.english)}</span>` : ''}
      </div>
      <button type="button" class="danger" data-delete-id="${Number(result.id)}">Delete</button>
    </div>`).join('');

  box.querySelectorAll('.search-result-main').forEach(row => {
    const id = Number(row.closest('.search-result').dataset.lemmaId);
    row.addEventListener('click', () => openLemma(id));
    row.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        openLemma(id);
      }
    });
  });
  box.querySelectorAll('[data-delete-id]').forEach(button => {
    button.addEventListener('click', () => deleteLemma(Number(button.dataset.deleteId)));
  });
}

function highlightMatch(lemma, query) {
  const text = String(lemma || '');
  const needle = String(query || '').trim();
  if (!needle) return esc(text);
  const index = text.toLocaleLowerCase().indexOf(needle.toLocaleLowerCase());
  if (index < 0) return esc(text);
  return `${esc(text.slice(0, index))}<b>${esc(text.slice(index, index + needle.length))}</b>${esc(text.slice(index + needle.length))}`;
}

function findExactMatch() {
  const query = state.query.trim().toLocaleLowerCase();
  if (!query) return null;
  return state.results.find(result => String(result.lemma || '').trim().toLocaleLowerCase() === query) || null;
}

function updateCreateButton() {
  const button = document.getElementById('create-button');
  if (!button || !state.selectedType) return;
  const query = state.query.trim();
  const label = state.meta.lemma_types[state.selectedType].singular;
  const exact = findExactMatch();
  button.disabled = !query;
  button.textContent = !query
    ? `Create new ${label}`
    : exact
      ? `Create duplicate ${label}: ${query}`
      : `Create new ${label}: ${query}`;
}

async function openLemma(id) {
  try {
    const data = await api(`/api/lemmas/${id}`);
    startEditor(data.lemma, false);
  } catch (error) {
    showHomeError(error.message);
  }
}

function createDraft() {
  const lemma = state.query.trim();
  if (!state.selectedType || !lemma) return;
  startEditor(makeDraftLemma(state.selectedType, lemma), true);
}

async function deleteLemma(id) {
  const item = state.results.find(result => Number(result.id) === id);
  const lemma = item?.lemma || 'this lemma';
  if (!confirm(`Delete ${lemma}? This cannot be undone.`)) return;
  try {
    await api(`/api/lemmas/${id}`, { method: 'DELETE' });
    state.results = state.results.filter(result => Number(result.id) !== id);
    renderSearchResults();
    updateCreateButton();
    if (state.query.trim()) runSearch();
  } catch (error) {
    showHomeError(error.message);
  }
}

function showHomeError(message) {
  const box = document.getElementById('search-results');
  if (box) box.innerHTML = `<div class="error-box">${esc(message)}</div>`;
}

function makeDraftLemma(lemmaType, lemmaText) {
  const lemma = { id: null, lemma_type: lemmaType, lemma: lemmaText, english: '' };
  if (lemmaType === 'noun') {
    lemma.noun = { gender_availability: '', inflections: emptyNestedForms() };
  } else if (lemmaType === 'adjective') {
    lemma.adjective = { adjective_inflection_type: '', inflections: emptyNestedForms() };
  } else if (lemmaType === 'other') {
    lemma.other = { inflection_type: '', inflections: emptyNestedForms() };
  } else if (lemmaType === 'verb') {
    lemma.verb = { forms: {} };
  }
  return lemma;
}

function startEditor(lemma, isNew) {
  const firstVerbGroup = state.meta.verb_groups[0]?.code || 'indicative';
  state.editor = {
    lemma,
    isNew,
    dirty: false,
    activeVerbGroup: firstVerbGroup,
    message: '',
    error: '',
  };
  renderEditor();
}

function renderEditor() {
  const editor = state.editor;
  if (!editor) return;
  const lemma = editor.lemma;
  app.innerHTML = `
    <section class="panel editor-panel">
      <div class="header-row">
        <h1 id="editor-title">${esc(editorTitle(lemma))}${editor.dirty ? ' *' : ''}</h1>
        <button id="back-button" type="button" class="ghost">Go back</button>
      </div>
      <div id="editor-message">${renderMessage()}</div>
      <form id="editor-form" novalidate>
        ${renderEditorBody(lemma, editor.isNew)}
      </form>
      <div class="status-row">
        <span id="dirty-status" class="${editor.dirty ? 'unsaved' : 'muted'}">${editor.dirty ? 'Unsaved changes' : editor.isNew ? 'New lemma' : 'Saved'}</span>
        <div class="action-row">
          <button type="button" id="discard-button" class="ghost">Discard</button>
          <button type="button" id="save-button" class="primary">Save &amp; go back</button>
        </div>
      </div>
    </section>`;

  document.getElementById('back-button').addEventListener('click', leaveEditor);
  document.getElementById('discard-button').addEventListener('click', leaveEditor);
  document.getElementById('save-button').addEventListener('click', saveEditor);
  document.getElementById('editor-form').addEventListener('input', onEditorChanged);
  document.getElementById('editor-form').addEventListener('change', onEditorChanged);

  wireNullableCells();
  wireTuVosSync();
  wireEditorSpecificControls();
  updateEditorUi();
}

function renderMessage() {
  if (state.editor.error) return `<div class="error-box">${esc(state.editor.error)}</div>`;
  if (state.editor.message) return `<div class="success-box">${esc(state.editor.message)}</div>`;
  return '';
}

function renderEditorBody(lemma, isNew) {
  if (lemma.lemma_type === 'noun') return renderNounEditor(lemma, isNew);
  if (lemma.lemma_type === 'adjective') return renderAdjectiveEditor(lemma, isNew);
  if (lemma.lemma_type === 'other') return renderOtherEditor(lemma, isNew);
  if (lemma.lemma_type === 'verb') return renderVerbEditor(lemma, isNew);
  return `<div class="error-box">Unsupported lemma type: ${esc(lemma.lemma_type)}</div>`;
}

function commonBaseCard(lemma, isNew, extraRows = '') {
  return `
    <div class="card">
      <h2>Base</h2>
      <div class="form-row">
        <label for="lemma-input">Lemma</label>
        <input id="lemma-input" name="lemma" value="${esc(lemma.lemma)}" ${isNew ? 'readonly' : ''} required autocomplete="off" spellcheck="false">
      </div>
      <div class="form-row">
        <label for="english-input">English</label>
        <input id="english-input" name="english" value="${esc(lemma.english)}" required placeholder="Write the English definition first" autocomplete="off" spellcheck="false">
      </div>
      ${extraRows}
    </div>`;
}


function renderNounEditor(lemma, isNew) {
  const details = lemma.noun || { gender_availability: '', inflections: emptyNestedForms() };
  const choices = state.meta.gender_choices.map(choice => `
    <option value="${esc(choice.value)}" ${details.gender_availability === choice.value ? 'selected' : ''}>${esc(choice.label)}</option>`).join('');
  return `
    ${commonBaseCard(lemma, isNew, `
      <div class="form-row">
        <label for="gender-select">Gender</label>
        <select id="gender-select" name="gender_availability">
          <option value="">Choose gender…</option>
          ${choices}
        </select>
      </div>`)}
    <p id="helper-text" class="helper"></p>
    <div id="noun-grid-card" class="card">
      <h2>Inflections</h2>
      ${renderNounFormsGrid(details.inflections || emptyNestedForms(), details.gender_availability || 'both', isNew, lemma, {
        allowNone: false,
        visibleGenders: nounVisibleGenders(details.gender_availability || 'both'),
      })}
    </div>`;
}

function renderAdjectiveEditor(lemma, isNew) {
  const details = lemma.adjective || { adjective_inflection_type: '', inflections: emptyNestedForms() };
  const selected = details.adjective_inflection_type || '';
  const options = state.meta.adjective_inflection_types.map(type => `
    <option value="${esc(type.value)}" ${selected === type.value ? 'selected' : ''}>${esc(type.label)}</option>`).join('');
  return `
    ${commonBaseCard(lemma, isNew, `
      <div id="adjective-type-row" class="form-row">
        <label for="adjective-inflection-type-select">Is inflective by</label>
        <select id="adjective-inflection-type-select" name="adjective_inflection_type">
          <option value="" ${selected ? '' : 'selected'}>Choose type…</option>
          ${options}
        </select>
      </div>`)}
    <p id="helper-text" class="helper"></p>
    <div id="adjective-plurality-card" class="card">
      <h2>Plurality</h2>
      ${renderPluralityFormsGrid(details.inflections || emptyNestedForms(), isNew, lemma)}
    </div>
    <div id="adjective-gender-grid-card" class="card">
      <h2>Plurality + gender</h2>
      ${renderRequiredFormsGrid(details.inflections || emptyNestedForms(), isNew, lemma)}
    </div>`;
}

function renderOtherEditor(lemma, isNew) {
  const details = lemma.other || { inflection_type: '', inflections: emptyNestedForms() };
  const selected = details.inflection_type || '';
  const options = state.meta.other_inflection_types.map(type => `
    <option value="${esc(type.value)}" ${selected === type.value ? 'selected' : ''}>${esc(type.label)}</option>`).join('');
  return `
    ${commonBaseCard(lemma, isNew, `
      <div class="form-row">
        <label for="inflection-type-select">Inflection type</label>
        <select id="inflection-type-select" name="inflection_type">
          <option value="" ${selected ? '' : 'selected'}>Choose type…</option>
          ${options}
        </select>
      </div>`)}
    <p id="helper-text" class="helper"></p>
    <div id="other-plurality-card" class="card">
      <h2>Plurality</h2>
      ${renderPluralityFormsGrid(details.inflections || emptyNestedForms(), isNew, lemma)}
    </div>
    <div id="other-grid-card" class="card">
      <h2>Plurality + gender</h2>
      ${renderRequiredFormsGrid(details.inflections || emptyNestedForms(), isNew, lemma)}
    </div>`;
}

function renderNounFormsGrid(forms, genderAvailability, isNew, lemma = null, options = {}) {
  const allowNone = options.allowNone !== false;
  const visibleGenders = options.visibleGenders || state.meta.genders;
  const rows = state.meta.numbers.map(number => `
    <tr>
      <th scope="row">${esc(number)}</th>
      ${visibleGenders.map(gender => {
        const enabled = isGenderEnabled(genderAvailability, gender);
        const locked = isLockedNounDefault(genderAvailability, number, gender);
        const value = locked ? (lemma?.lemma || '') : (forms?.[number]?.[gender] ?? null);
        const explicitNone = allowNone && !locked && (enabled ? (!isNew && value === null) : true);
        return `<td>${nullableCellHtml({ type: 'noun', number, gender, value, explicitNone, disabled: !enabled || locked, locked, allowNone })}</td>`;
      }).join('')}
    </tr>`).join('');
  return `
    <table class="inflection-grid">
      <thead><tr><th></th>${visibleGenders.map(g => `<th>${esc(g)}</th>`).join('')}</tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}

function renderPluralityFormsGrid(forms, isNew, lemma) {
  const rows = state.meta.numbers.map(number => {
    const value = forms?.[number]?.shared ?? forms?.[number]?.masculine ?? '';
    const defaultValue = isNew && number === 'singular' ? lemma.lemma : '';
    return `
      <tr>
        <th scope="row">${esc(number)}</th>
        <td>
          <div class="nullable-cell" data-cell="plurality-form" data-number="${esc(number)}">
            <input type="text" value="${esc(value || defaultValue)}" autocomplete="off" spellcheck="false">
          </div>
        </td>
      </tr>`;
  }).join('');
  return `
    <table class="inflection-grid">
      <thead><tr><th></th><th>Form</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}

function renderRequiredFormsGrid(forms, isNew = false, lemma = null) {
  const rows = state.meta.numbers.map(number => `
    <tr>
      <th scope="row">${esc(number)}</th>
      ${state.meta.genders.map(gender => {
        const value = forms?.[number]?.[gender] ?? '';
        const defaultValue = isNew && number === 'singular' && gender === 'masculine' ? (lemma?.lemma || '') : '';
        return `<td>
          <div class="nullable-cell" data-cell="required-form" data-number="${esc(number)}" data-gender="${esc(gender)}">
            <input type="text" value="${esc(value || defaultValue)}" autocomplete="off" spellcheck="false">
          </div>
        </td>`;
      }).join('')}
    </tr>`).join('');
  return `
    <table class="inflection-grid">
      <thead><tr><th></th>${state.meta.genders.map(g => `<th>${esc(g)}</th>`).join('')}</tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}

function renderVerbEditor(lemma, isNew) {
  return `
    ${commonBaseCard(lemma, isNew)}
    <p id="helper-text" class="helper"></p>
    <div id="verb-participles-card" class="card">
      <h2>Participles</h2>
      ${state.meta.verb_participles.map(part => {
        const payload = verbFormValue(lemma, part.code);
        const explicitNone = !isNew && payload.form === null;
        return `<div class="form-row"><label>${esc(part.label)}</label>${verbCellHtml({ code: part.code, value: payload.form, explicitNone })}</div>`;
      }).join('')}
    </div>
    <div id="verb-forms-card" class="card">
      <h2>Conjugations</h2>
      <div class="tabs" role="tablist">
        ${state.meta.verb_groups.map(group => `<button type="button" role="tab" data-verb-group="${esc(group.code)}" class="${state.editor.activeVerbGroup === group.code ? 'active' : ''}">${esc(group.label)}</button>`).join('')}
      </div>
      ${state.meta.verb_groups.map(group => renderVerbGroupTable(lemma, group, isNew)).join('')}
      <button type="button" class="ghost" data-action="set-visible-none">Set blank visible cells to None</button>
    </div>`;
}

function renderVerbGroupTable(lemma, group, isNew) {
  const active = state.editor.activeVerbGroup === group.code;
  return `
    <div class="verb-table-wrap ${active ? '' : 'hidden'}" data-verb-table="${esc(group.code)}">
      <table class="verb-table">
        <thead>
          <tr><th>Person</th>${group.tenses.map(tense => `<th>${esc(tense.label)}</th>`).join('')}</tr>
        </thead>
        <tbody>
          ${group.persons.map(person => `
            <tr>
              <th scope="row">${esc(person.label)}</th>
              ${group.tenses.map(tense => {
                const form = findVerbDefinition(tense, person.code);
                if (!form) return '<td class="muted">—</td>';
                const payload = verbFormValue(lemma, form.code);
                const explicitNone = !isNew && payload.form === null;
                return `<td>${verbCellHtml({ code: form.code, slot: tense.code, person: person.code, value: payload.form, explicitNone })}</td>`;
              }).join('')}
            </tr>`).join('')}
        </tbody>
      </table>
    </div>`;
}

function nullableCellHtml({ type, number, gender, value, explicitNone, disabled, locked = false, allowNone = true }) {
  const noneToggle = allowNone
    ? `<label class="none-toggle"><input type="checkbox" data-role="none" ${explicitNone ? 'checked' : ''} ${disabled ? 'disabled' : ''}> ${locked ? 'Locked' : 'None'}</label>`
    : '';
  return `
    <div class="nullable-cell ${locked ? 'locked-cell' : ''}" data-cell="nullable" data-type="${esc(type)}" data-number="${esc(number)}" data-gender="${esc(gender)}" data-locked="${locked ? 'true' : 'false'}" data-disabled="${disabled ? 'true' : 'false'}">
      <input type="text" value="${esc(value || '')}" ${disabled ? 'disabled' : ''} autocomplete="off" spellcheck="false">
      ${noneToggle}
    </div>`;
}


function verbCellHtml({ code, slot = '', person = '', value, explicitNone }) {
  return `
    <div class="nullable-cell verb-cell" data-cell="verb-cell" data-code="${esc(code)}" data-slot="${esc(slot)}" data-person="${esc(person)}">
      <input type="text" value="${esc(value || '')}" autocomplete="off" spellcheck="false">
      <label class="none-toggle"><input type="checkbox" data-role="none" ${explicitNone ? 'checked' : ''}> None</label>
    </div>`;
}

function wireNullableCells() {
  document.querySelectorAll('[data-cell]').forEach(cell => {
    const input = cell.querySelector('input[type="text"]');
    const none = cell.querySelector('[data-role="none"]');
    const sync = () => {
      if (cell.dataset.locked === 'true' || cell.dataset.disabled === 'true') {
        input.disabled = true;
        if (none) {
          none.checked = cell.dataset.locked === 'true' ? false : none.checked;
          none.disabled = true;
        }
        return;
      }
      if (none?.checked) input.value = '';
      input.disabled = Boolean(none?.checked || none?.disabled);
    };
    input.addEventListener('input', () => {
      if (input.value.trim() && none) none.checked = false;
      sync();
    });
    none?.addEventListener('change', sync);
    sync();
  });
}

function wireTuVosSync() {
  setupTuVosPairs();
}

function setupTuVosPairs() {
  document.querySelectorAll(`[data-cell="verb-cell"][data-person="vos"]`).forEach(vosCell => {
    const tuCell = matchingTuCell(vosCell);
    vosCell.dataset.manualVos = tuCell && sameNullableState(tuCell, vosCell) ? 'false' : 'true';
    vosCell.querySelector('input[type="text"]')?.addEventListener('input', () => {
      vosCell.dataset.manualVos = 'true';
    });
    vosCell.querySelector('[data-role="none"]')?.addEventListener('change', () => {
      vosCell.dataset.manualVos = 'true';
    });
  });

  document.querySelectorAll(`[data-cell="verb-cell"][data-person="tu"]`).forEach(tuCell => {
    const copyToVos = () => {
      const vosCell = matchingVosCell(tuCell);
      if (!vosCell || vosCell.dataset.manualVos === 'true') return;
      copyNullableState(tuCell, vosCell);
    };
    tuCell.querySelector('input[type="text"]')?.addEventListener('input', copyToVos);
    tuCell.querySelector('[data-role="none"]')?.addEventListener('change', copyToVos);
  });
}

function matchingTuCell(vosCell) {
  return matchingPersonCell(vosCell, 'tu');
}

function matchingVosCell(tuCell) {
  return matchingPersonCell(tuCell, 'vos');
}

function matchingPersonCell(cell, person) {
  return document.querySelector(
    `[data-cell="verb-cell"][data-slot="${cssEscape(cell.dataset.slot)}"][data-person="${person}"]`
  );
}

function nullableState(cell) {
  const input = cell.querySelector('input[type="text"]');
  const none = cell.querySelector('[data-role="none"]');
  return { text: input?.value || '', none: Boolean(none?.checked) };
}

function sameNullableState(left, right) {
  const a = nullableState(left);
  const b = nullableState(right);
  return a.none === b.none && a.text === b.text;
}

function copyNullableState(fromCell, toCell) {
  const value = nullableState(fromCell);
  const input = toCell.querySelector('input[type="text"]');
  const none = toCell.querySelector('[data-role="none"]');
  if (none) none.checked = value.none;
  if (input) {
    input.value = value.none ? '' : value.text;
    input.disabled = value.none;
  }
}

function wireEditorSpecificControls() {
  document.querySelectorAll('[data-verb-group]').forEach(button => {
    button.addEventListener('click', () => {
      state.editor.activeVerbGroup = button.dataset.verbGroup;
      document.querySelectorAll('[data-verb-group]').forEach(item => item.classList.toggle('active', item === button));
      document.querySelectorAll('[data-verb-table]').forEach(table => table.classList.toggle('hidden', table.dataset.verbTable !== state.editor.activeVerbGroup));
    });
  });

  document.getElementById('gender-select')?.addEventListener('change', event => {
    resetNounGridForGender(event.target.value);
    wireNullableCells();
  });

  document.getElementById('inflection-type-select')?.addEventListener('change', event => {
    resetOtherGridForType(event.target.value);
  });

  document.getElementById('adjective-inflection-type-select')?.addEventListener('change', event => {
    resetAdjectiveGridForType(event.target.value);
  });

  document.querySelectorAll('[data-action="set-visible-none"]').forEach(button => {
    button.addEventListener('click', () => {
      const isVerbButton = state.editor?.lemma.lemma_type === 'verb' && button.closest('#verb-forms-card');
      const cells = isVerbButton
        ? document.querySelectorAll('#verb-participles-card [data-cell="verb-cell"], #verb-forms-card [data-cell="verb-cell"]')
        : button.closest('.card').querySelectorAll('[data-cell]');

      cells.forEach(cell => {
        if (!isVerbButton && cell.closest('.hidden')) return;
        setBlankCellToNone(cell);
      });
      markDirty();
      updateEditorUi();
    });
  });
}

function resetNounGridForGender(genderAvailability) {
  const card = document.getElementById('noun-grid-card');
  if (!card) return;

  const lemma = currentLemmaShell();
  card.innerHTML = `
    <h2>Inflections</h2>
    ${renderNounFormsGrid(emptyNestedForms(), genderAvailability || 'both', true, lemma, {
      allowNone: false,
      visibleGenders: nounVisibleGenders(genderAvailability || 'both'),
    })}`;
}

function resetOtherGridForType(type) {
  const lemma = document.getElementById('lemma-input')?.value.trim() || '';

  document.querySelectorAll('#other-plurality-card [data-cell="plurality-form"] input[type="text"]').forEach(input => {
    input.value = input.closest('[data-number]')?.dataset.number === 'singular' && type === 'plurality' ? lemma : '';
  });

  document.querySelectorAll('#other-grid-card [data-cell="required-form"] input[type="text"]').forEach(input => {
    const cell = input.closest('[data-cell="required-form"]');
    input.value = cell?.dataset.number === 'singular' && cell?.dataset.gender === 'masculine' && type === 'gender_plurality' ? lemma : '';
  });
}

function resetAdjectiveGridForType(type) {
  const lemma = document.getElementById('lemma-input')?.value.trim() || '';

  document.querySelectorAll('#adjective-plurality-card [data-cell="plurality-form"] input[type="text"]').forEach(input => {
    input.value = input.closest('[data-number]')?.dataset.number === 'singular' && type === 'plurality' ? lemma : '';
  });

  document.querySelectorAll('#adjective-gender-grid-card [data-cell="required-form"] input[type="text"]').forEach(input => {
    const cell = input.closest('[data-cell="required-form"]');
    input.value = cell?.dataset.number === 'singular' && cell?.dataset.gender === 'masculine' && type === 'gender_plurality' ? lemma : '';
  });
}

function setBlankCellToNone(cell) {
  const input = cell.querySelector('input[type="text"]');
  const none = cell.querySelector('[data-role="none"]');
  if (!input || !none || input.disabled || none.disabled || input.value.trim()) return;
  none.checked = true;
  input.value = '';
  input.dispatchEvent(new Event('input', { bubbles: true }));
  none.dispatchEvent(new Event('change', { bubbles: true }));
}

function setNullableCell(cell, text, noneChecked, disabled, locked = false) {
  if (!cell) return;
  const input = cell.querySelector('input[type="text"]');
  const none = cell.querySelector('[data-role="none"]');
  if (input) {
    input.value = noneChecked ? '' : text;
    input.disabled = disabled || noneChecked;
  }
  if (none) {
    none.checked = noneChecked;
    none.disabled = disabled;
    none.closest('label').lastChild.textContent = locked ? ' Locked' : ' None';
  }
  cell.dataset.locked = locked ? 'true' : 'false';
  cell.dataset.disabled = disabled ? 'true' : 'false';
  cell.classList.toggle('locked-cell', locked);
}

function findNounCell(scopeSelector, number, gender) {
  return document.querySelector(`${scopeSelector} [data-cell="nullable"][data-number="${cssEscape(number)}"][data-gender="${cssEscape(gender)}"]`);
}

function onEditorChanged() {
  markDirty();
  updateEditorUi();
}

function markDirty() {
  if (!state.editor) return;
  state.editor.dirty = true;
  state.editor.message = '';
  state.editor.error = '';
  const lemma = currentLemmaShell();
  const title = document.getElementById('editor-title');
  if (title) title.textContent = `${editorTitle(lemma)} *`;
  const status = document.getElementById('dirty-status');
  if (status) {
    status.textContent = 'Unsaved changes';
    status.className = 'unsaved';
  }
  const message = document.getElementById('editor-message');
  if (message) message.innerHTML = '';
}

function updateEditorUi() {
  const lemmaType = state.editor?.lemma.lemma_type;
  const english = document.getElementById('english-input')?.value.trim() || '';
  const helper = document.getElementById('helper-text');
  const saveButton = document.getElementById('save-button');
  let valid = false;
  let helperText = '';

  if (lemmaType === 'noun') {
    const gender = document.getElementById('gender-select')?.value || '';
    const grid = document.getElementById('noun-grid-card');
    if (grid) grid.classList.toggle('hidden', !english || !gender);
    syncNounGridAvailability(gender || 'both');
    if (!english) helperText = 'Enter the English definition to unlock gender and inflections.';
    else if (!gender) helperText = 'Choose gender to unlock the inflections table.';
    else if (!allVisibleNullableCellsComplete(grid)) helperText = CELL_REQUIRED_MESSAGE;
    valid = Boolean(document.getElementById('lemma-input')?.value.trim() && english && gender && !helperText);
  } else if (lemmaType === 'adjective') {
    const type = document.getElementById('adjective-inflection-type-select')?.value || '';
    const typeRow = document.getElementById('adjective-type-row');
    const pluralityGrid = document.getElementById('adjective-plurality-card');
    const genderGrid = document.getElementById('adjective-gender-grid-card');
    if (typeRow) typeRow.classList.toggle('hidden', !english);
    if (pluralityGrid) pluralityGrid.classList.toggle('hidden', !english || type !== 'plurality');
    if (genderGrid) genderGrid.classList.toggle('hidden', !english || type !== 'gender_plurality');
    if (!english) helperText = 'Enter the English definition to unlock adjective forms.';
    else if (!type) helperText = 'Choose what the adjective is inflective by.';
    else if (type === 'plurality' && !allPluralityFormCellsComplete(pluralityGrid)) helperText = CELL_REQUIRED_MESSAGE;
    else if (type === 'gender_plurality' && !allRequiredFormCellsComplete(genderGrid)) helperText = CELL_REQUIRED_MESSAGE;
    valid = Boolean(document.getElementById('lemma-input')?.value.trim() && english && type && !helperText);
  } else if (lemmaType === 'other') {
    const type = document.getElementById('inflection-type-select')?.value || '';
    const pluralityGrid = document.getElementById('other-plurality-card');
    const grid = document.getElementById('other-grid-card');
    if (pluralityGrid) pluralityGrid.classList.toggle('hidden', !english || type !== 'plurality');
    if (grid) grid.classList.toggle('hidden', !english || type !== 'gender_plurality');
    if (!english) helperText = 'Enter the English definition to unlock the inflection type.';
    else if (!type) helperText = 'Choose inflection type.';
    else if (type === 'plurality' && !allPluralityFormCellsComplete(pluralityGrid)) helperText = CELL_REQUIRED_MESSAGE;
    else if (type === 'gender_plurality' && !allRequiredFormCellsComplete(grid)) helperText = CELL_REQUIRED_MESSAGE;
    valid = Boolean(document.getElementById('lemma-input')?.value.trim() && english && type && !helperText);
  } else if (lemmaType === 'verb') {
    const cards = [document.getElementById('verb-participles-card'), document.getElementById('verb-forms-card')];
    cards.forEach(card => card?.classList.toggle('hidden', !english));
    if (!english) helperText = 'Enter the English definition to unlock participles and conjugations.';
    else if (!allVerbCellsComplete()) helperText = CELL_REQUIRED_MESSAGE;
    valid = Boolean(document.getElementById('lemma-input')?.value.trim() && english && !helperText);
  }

  if (helper) {
    helper.textContent = helperText;
    helper.classList.toggle('hidden', !helperText);
  }
  if (saveButton) saveButton.disabled = !valid;
}

function syncNounGridAvailability(genderAvailability) {
  const lemma = document.getElementById('lemma-input')?.value.trim() || '';
  document.querySelectorAll('[data-cell="nullable"]').forEach(cell => {
    const number = cell.dataset.number;
    const gender = cell.dataset.gender;
    const locked = isLockedNounDefault(genderAvailability, number, gender);
    const enabled = isGenderEnabled(genderAvailability, gender);
    const input = cell.querySelector('input[type="text"]');
    const none = cell.querySelector('[data-role="none"]');

    cell.dataset.locked = locked ? 'true' : 'false';
    cell.dataset.disabled = (!enabled || locked) ? 'true' : 'false';
    cell.classList.toggle('locked-cell', locked);

    if (locked) {
      input.value = lemma;
      input.disabled = true;
      if (none) {
        none.checked = false;
        none.disabled = true;
        none.closest('label').lastChild.textContent = ' Locked';
      }
    } else if (!enabled) {
      input.value = '';
      input.disabled = true;
      if (none) {
        none.checked = true;
        none.disabled = true;
        none.closest('label').lastChild.textContent = ' None';
      }
    } else {
      if (none) {
        none.disabled = false;
        none.closest('label').lastChild.textContent = ' None';
        input.disabled = none.checked;
      } else {
        input.disabled = false;
      }
    }
  });
}

function allVisibleNullableCellsComplete(scope) {
  if (!scope || scope.classList.contains('hidden')) return true;
  return Array.from(scope.querySelectorAll('[data-cell]')).every(cell => {
    if (cell.closest('.hidden')) return true;
    const input = cell.querySelector('input[type="text"]');
    const none = cell.querySelector('[data-role="none"]');
    if (input?.disabled || none?.disabled) return true;
    return Boolean(none?.checked || input.value.trim());
  });
}

function allRequiredFormCellsComplete(scope) {
  if (!scope || scope.classList.contains('hidden')) return true;
  return Array.from(scope.querySelectorAll('[data-cell="required-form"] input[type="text"]')).every(input => Boolean(input.value.trim()));
}

function allPluralityFormCellsComplete(scope) {
  if (!scope || scope.classList.contains('hidden')) return true;
  return Array.from(scope.querySelectorAll('[data-cell="plurality-form"] input[type="text"]')).every(input => Boolean(input.value.trim()));
}

function allVerbCellsComplete() {
  const cards = [document.getElementById('verb-participles-card'), document.getElementById('verb-forms-card')];
  return cards.every(card => allVisibleNullableCellsComplete(card));
}

function currentLemmaShell() {
  const base = state.editor.lemma;
  return {
    ...base,
    lemma: document.getElementById('lemma-input')?.value || base.lemma,
    english: document.getElementById('english-input')?.value || base.english,
  };
}

function editorTitle(lemmaItem) {
  const title = (lemmaItem.lemma || '').trim() || 'Untitled';
  const label = LEMMA_TYPE_LABELS[lemmaItem.lemma_type] || lemmaItem.lemma_type;
  return `${label}: ${title}`;
}

function nounVisibleGenders(availability) {
  if (availability === 'masculine') return ['masculine'];
  if (availability === 'feminine') return ['feminine'];
  return state.meta.genders;
}

function isGenderEnabled(availability, gender) {
  if (availability === 'masculine') return gender === 'masculine';
  if (availability === 'feminine') return gender === 'feminine';
  return true;
}

function isLockedNounDefault(availability, number, gender) {
  return number === 'singular'
    && ((availability === 'masculine' && gender === 'masculine') || (availability === 'feminine' && gender === 'feminine'));
}

function collectPayload() {
  const lemmaType = state.editor.lemma.lemma_type;
  const payload = {
    lemma_type: lemmaType,
    lemma: document.getElementById('lemma-input').value.trim(),
    english: document.getElementById('english-input').value.trim(),
  };
  if (!payload.lemma) throw new Error('lemma cannot be empty');
  if (!payload.english) throw new Error('english definition cannot be empty');

  if (lemmaType === 'noun') {
    payload.gender_availability = document.getElementById('gender-select').value;
    if (!payload.gender_availability) throw new Error('choose gender');
    if (!allVisibleNullableCellsComplete(document.getElementById('noun-grid-card'))) throw new Error(CELL_REQUIRED_MESSAGE);
    payload.forms = collectNounForms(document.getElementById('noun-grid-card'));
  } else if (lemmaType === 'adjective') {
    const type = document.getElementById('adjective-inflection-type-select').value;
    if (!type) throw new Error('choose what the adjective is inflective by');
    payload.adjective_inflection_type = type;
    if (type === 'plurality') {
      const grid = document.getElementById('adjective-plurality-card');
      if (!allPluralityFormCellsComplete(grid)) throw new Error(CELL_REQUIRED_MESSAGE);
      payload.forms = collectPluralityForms(grid);
    } else {
      const grid = document.getElementById('adjective-gender-grid-card');
      if (!allRequiredFormCellsComplete(grid)) throw new Error(CELL_REQUIRED_MESSAGE);
      payload.forms = collectRequiredForms(grid);
    }
  } else if (lemmaType === 'other') {
    const type = document.getElementById('inflection-type-select').value;
    if (!type) throw new Error('choose inflection type');
    payload.inflection_type = type;
    payload.forms = emptyNestedForms();
    if (type === 'plurality') {
      const grid = document.getElementById('other-plurality-card');
      if (!allPluralityFormCellsComplete(grid)) throw new Error(CELL_REQUIRED_MESSAGE);
      payload.forms = collectPluralityForms(grid);
    } else if (type === 'gender_plurality') {
      const grid = document.getElementById('other-grid-card');
      if (!allRequiredFormCellsComplete(grid)) throw new Error(CELL_REQUIRED_MESSAGE);
      payload.forms = collectRequiredForms(grid);
    }
  } else if (lemmaType === 'verb') {
    if (!allVerbCellsComplete()) throw new Error(CELL_REQUIRED_MESSAGE);
    payload.forms = collectVerbForms();
  }
  return payload;
}

function collectNounForms(scope) {
  const forms = emptyNestedForms();
  scope.querySelectorAll('[data-cell="nullable"]').forEach(cell => {
    const number = cell.dataset.number;
    const gender = cell.dataset.gender;
    const input = cell.querySelector('input[type="text"]');
    const none = cell.querySelector('[data-role="none"]');
    forms[number][gender] = cell.dataset.locked === 'true'
      ? (input.value.trim() || null)
      : (none?.checked || input.disabled) ? null : (input.value.trim() || null);
  });
  return forms;
}

function collectRequiredForms(scope) {
  const forms = emptyNestedForms();
  scope.querySelectorAll('[data-cell="required-form"]').forEach(cell => {
    const number = cell.dataset.number;
    const gender = cell.dataset.gender;
    const input = cell.querySelector('input[type="text"]');
    forms[number][gender] = input.value.trim();
  });
  return forms;
}

function collectPluralityForms(scope) {
  const forms = emptyNestedForms();
  scope.querySelectorAll('[data-cell="plurality-form"]').forEach(cell => {
    const number = cell.dataset.number;
    const input = cell.querySelector('input[type="text"]');
    const value = input.value.trim();
    forms[number].shared = value;
  });
  return forms;
}

function collectVerbForms() {
  const forms = {};
  document.querySelectorAll('[data-cell="verb-cell"]').forEach(cell => {
    forms[cell.dataset.code] = collectVerbCell(cell);
  });
  return forms;
}

function collectVerbCell(cell) {
  const input = cell.querySelector('input[type="text"]');
  const none = cell.querySelector('[data-role="none"]');
  return { form: none.checked ? null : (input.value.trim() || null) };
}

async function saveEditor() {
  try {
    state.editor.error = '';
    const payload = collectPayload();
    const isNew = state.editor.isNew;
    const path = isNew ? '/api/lemmas' : `/api/lemmas/${state.editor.lemma.id}`;
    const method = isNew ? 'POST' : 'PUT';
    const data = await api(path, { method, body: JSON.stringify(payload) });
    state.editor.lemma = data.lemma;
    state.editor.isNew = false;
    state.editor.dirty = false;
    state.selectedType = data.lemma.lemma_type;
    state.query = '';
    state.results = [];
    state.searching = false;
    clearTimeout(state.searchTimer);
    renderHome();
  } catch (error) {
    state.editor.error = error.message;
    state.editor.message = '';
    const message = document.getElementById('editor-message');
    if (message) message.innerHTML = renderMessage();
  }
}

function leaveEditor() {
  if (state.editor?.dirty && !confirm('Go back without saving these changes?')) return;
  renderHome();
}

function emptyNestedForms() {
  return {
    singular: { masculine: null, feminine: null, shared: null },
    plural: { masculine: null, feminine: null, shared: null },
  };
}

function findVerbDefinition(tense, personCode) {
  return tense.forms.find(form => form.person_code === personCode) || null;
}

function verbFormValue(lemma, code) {
  return lemma.verb?.forms?.[code] || { form: null };
}

function cssEscape(value) {
  if (window.CSS?.escape) return CSS.escape(value);
  return String(value).replace(/[^a-zA-Z0-9_-]/g, '\\$&');
}

init();
