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

const WORD_TYPE_LABELS = {
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
    app.innerHTML = `<section class="panel"><h1>Spanish Word DB</h1><div class="error-box">${esc(error.message)}</div></section>`;
  }
}

function renderHome() {
  state.editor = null;
  const wordTypes = Object.keys(state.meta.word_types);
  app.innerHTML = `
    <section class="panel">
      <div class="header-row">
        <h1>Spanish Word DB</h1>
      </div>
      <div class="word-type-grid" role="group" aria-label="Word class">
        ${wordTypes.map(type => `<button type="button" data-type="${esc(type)}" class="${state.selectedType === type ? 'active' : ''}">${esc(state.meta.word_types[type].button)}</button>`).join('')}
      </div>
      <div id="entry-panel" class="${state.selectedType ? '' : 'hidden'}">
        <div class="card">
          <h2 id="selected-class">${state.selectedType ? esc(state.meta.word_types[state.selectedType].button) : ''}</h2>
          <div class="form-row">
            <label for="lemma-search">Lemma</label>
            <input id="lemma-search" type="text" autocomplete="off" spellcheck="false" value="${esc(state.query)}" placeholder="Type a Spanish lemma">
          </div>
          <div class="results-title" id="results-title">${state.selectedType ? `Already added ${esc(state.meta.word_types[state.selectedType].plural)}` : ''}</div>
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
        if (exact) openWord(exact.id);
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
    const data = await api(`/api/search?word_type=${encodeURIComponent(type)}&q=${encodeURIComponent(query)}`);
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
    <div class="search-result" data-word-id="${Number(result.id)}">
      <div class="search-result-main" tabindex="0" role="button">
        <strong>${highlightMatch(result.lemma, state.query)}</strong>
        ${result.english ? `<span class="muted">${esc(result.english)}</span>` : ''}
      </div>
      <button type="button" class="danger" data-delete-id="${Number(result.id)}">Delete</button>
    </div>`).join('');

  box.querySelectorAll('.search-result-main').forEach(row => {
    const id = Number(row.closest('.search-result').dataset.wordId);
    row.addEventListener('click', () => openWord(id));
    row.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        openWord(id);
      }
    });
  });
  box.querySelectorAll('[data-delete-id]').forEach(button => {
    button.addEventListener('click', () => deleteWord(Number(button.dataset.deleteId)));
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
  const label = state.meta.word_types[state.selectedType].singular;
  const exact = findExactMatch();
  button.disabled = !query;
  button.textContent = !query
    ? `Create new ${label}`
    : exact
      ? `Create duplicate ${label}: ${query}`
      : `Create new ${label}: ${query}`;
}

async function openWord(id) {
  try {
    const data = await api(`/api/words/${id}`);
    startEditor(data.word, false);
  } catch (error) {
    showHomeError(error.message);
  }
}

function createDraft() {
  const lemma = state.query.trim();
  if (!state.selectedType || !lemma) return;
  startEditor(makeDraftWord(state.selectedType, lemma), true);
}

async function deleteWord(id) {
  const item = state.results.find(result => Number(result.id) === id);
  const lemma = item?.lemma || 'this word';
  if (!confirm(`Delete ${lemma}? This cannot be undone.`)) return;
  try {
    await api(`/api/words/${id}`, { method: 'DELETE' });
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

function makeDraftWord(wordType, lemma) {
  const word = { id: null, word_type: wordType, lemma, english: '' };
  if (wordType === 'noun') {
    word.nominal = { gender_availability: '', inflections: emptyNestedForms() };
  } else if (wordType === 'adjective') {
    word.nominal = { gender_availability: 'both', inflections: emptyNestedForms() };
  } else if (wordType === 'other') {
    word.other = { inflection_type: '', inflections: emptyNestedForms(), person_inflections: emptyPersonGenderForms() };
  } else if (wordType === 'verb') {
    word.verb = { participles: emptyParticiples(), forms: {} };
  }
  return word;
}

function startEditor(word, isNew) {
  const firstVerbGroup = state.meta.verb_groups[0]?.code || 'indicative';
  state.editor = {
    word,
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
  const word = editor.word;
  app.innerHTML = `
    <section class="panel editor-panel">
      <div class="header-row">
        <h1 id="editor-title">${esc(editorTitle(word))}${editor.dirty ? ' *' : ''}</h1>
        <button id="back-button" type="button" class="ghost">Go back</button>
      </div>
      <div id="editor-message">${renderMessage()}</div>
      <form id="editor-form" novalidate>
        ${renderEditorBody(word, editor.isNew)}
      </form>
      <div class="status-row">
        <span id="dirty-status" class="${editor.dirty ? 'unsaved' : 'muted'}">${editor.dirty ? 'Unsaved changes' : editor.isNew ? 'New word' : 'Saved'}</span>
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

function renderEditorBody(word, isNew) {
  if (word.word_type === 'noun' || word.word_type === 'adjective') return renderNominalEditor(word, isNew);
  if (word.word_type === 'other') return renderOtherEditor(word, isNew);
  if (word.word_type === 'verb') return renderVerbEditor(word, isNew);
  return `<div class="error-box">Unsupported word type: ${esc(word.word_type)}</div>`;
}

function commonBaseCard(word, isNew, extraRows = '') {
  return `
    <div class="card">
      <h2>Base</h2>
      <div class="form-row">
        <label for="lemma-input">Lemma</label>
        <input id="lemma-input" name="lemma" value="${esc(word.lemma)}" ${isNew ? 'readonly' : ''} required autocomplete="off" spellcheck="false">
      </div>
      <div class="form-row">
        <label for="english-input">English</label>
        <input id="english-input" name="english" value="${esc(word.english)}" required placeholder="Write the English definition first" autocomplete="off" spellcheck="false">
      </div>
      ${extraRows}
    </div>`;
}

function renderNominalEditor(word, isNew) {
  if (word.word_type === 'adjective') return renderAdjectiveEditor(word, isNew);
  return renderNounEditor(word, isNew);
}

function renderNounEditor(word, isNew) {
  const details = word.nominal || { gender_availability: '', inflections: emptyNestedForms() };
  const choices = state.meta.gender_choices.map(choice => `
    <option value="${esc(choice.value)}" ${details.gender_availability === choice.value ? 'selected' : ''}>${esc(choice.label)}</option>`).join('');
  return `
    ${commonBaseCard(word, isNew, `
      <div class="form-row">
        <label for="gender-select">Gender</label>
        <select id="gender-select" name="gender_availability">
          <option value="">Choose gender…</option>
          ${choices}
        </select>
      </div>`)}
    <p id="helper-text" class="helper"></p>
    <div id="nominal-grid-card" class="card">
      <h2>Inflections</h2>
      ${renderNominalGrid(details.inflections || emptyNestedForms(), details.gender_availability || 'both', isNew, word)}
      <button type="button" class="ghost" data-action="set-visible-none">Set blank visible cells to None</button>
    </div>`;
}

function renderAdjectiveEditor(word, isNew) {
  const details = word.nominal || { gender_availability: 'both', inflections: emptyNestedForms() };
  return `
    ${commonBaseCard(word, isNew)}
    <p id="helper-text" class="helper"></p>
    <div id="adjective-grid-card" class="card">
      <h2>Forms</h2>
      ${renderRequiredFormsGrid(details.inflections || emptyNestedForms())}
    </div>`;
}

function renderOtherEditor(word, isNew) {
  const details = word.other || { inflection_type: '', inflections: emptyNestedForms(), person_inflections: emptyPersonGenderForms() };
  const selected = details.inflection_type || '';
  const options = state.meta.other_inflection_types.map(type => `
    <option value="${esc(type.value)}" ${selected === type.value ? 'selected' : ''}>${esc(type.label)}</option>`).join('');
  return `
    ${commonBaseCard(word, isNew, `
      <div class="form-row">
        <label for="inflection-type-select">Inflection type</label>
        <select id="inflection-type-select" name="inflection_type">
          <option value="" ${selected ? '' : 'selected'}>Choose type…</option>
          ${options}
        </select>
      </div>`)}
    <p id="helper-text" class="helper"></p>
    <div id="other-grid-card" class="card">
      <h2>Gender + plurality</h2>
      ${renderNominalGrid(details.inflections || emptyNestedForms(), 'both', isNew)}
      <button type="button" class="ghost" data-action="set-visible-none">Set blank visible cells to None</button>
    </div>
    <div id="other-person-grid-card" class="card">
      <h2>Person + gender + plurality</h2>
      ${renderOtherPersonGrid(details.person_inflections || emptyPersonGenderForms(), isNew)}
      <button type="button" class="ghost" data-action="set-visible-none">Set blank visible cells to None</button>
    </div>`;
}

function renderNominalGrid(forms, genderAvailability, isNew, word = null) {
  const rows = state.meta.numbers.map(number => `
    <tr>
      <th scope="row">${esc(number)}</th>
      ${state.meta.genders.map(gender => {
        const enabled = isGenderEnabled(genderAvailability, gender);
        const locked = isLockedNounDefault(word?.word_type, genderAvailability, number, gender);
        const value = locked ? (word?.lemma || '') : (forms?.[number]?.[gender] ?? null);
        const explicitNone = locked ? false : enabled ? (!isNew && value === null) : true;
        return `<td>${nullableCellHtml({ type: 'nominal', number, gender, value, explicitNone, disabled: !enabled || locked, locked })}</td>`;
      }).join('')}
    </tr>`).join('');
  return `
    <table class="inflection-grid">
      <thead><tr><th></th>${state.meta.genders.map(g => `<th>${esc(g)}</th>`).join('')}</tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}

function renderRequiredFormsGrid(forms) {
  const rows = state.meta.numbers.map(number => `
    <tr>
      <th scope="row">${esc(number)}</th>
      ${state.meta.genders.map(gender => {
        const value = forms?.[number]?.[gender] ?? '';
        return `<td>
          <div class="nullable-cell" data-cell="required-form" data-number="${esc(number)}" data-gender="${esc(gender)}">
            <input type="text" value="${esc(value || '')}" autocomplete="off" spellcheck="false">
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

function renderOtherPersonGrid(forms, isNew) {
  const rows = state.meta.persons.map(person => `
    <tr>
      <th scope="row">${esc(person.label)}</th>
      ${state.meta.genders.map(gender => {
        const value = forms?.[person.code]?.[gender] ?? null;
        const explicitNone = !isNew && value === null;
        return `<td>${otherPersonCellHtml({ person: person.code, gender, value, explicitNone })}</td>`;
      }).join('')}
    </tr>`).join('');
  return `
    <table class="inflection-grid">
      <thead><tr><th>Person</th>${state.meta.genders.map(g => `<th>${esc(g)}</th>`).join('')}</tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}

function renderVerbEditor(word, isNew) {
  return `
    ${commonBaseCard(word, isNew)}
    <p id="helper-text" class="helper"></p>
    <div id="verb-participles-card" class="card">
      <h2>Participles</h2>
      ${state.meta.participle_types.map(part => {
        const payload = verbParticipleValue(word, part.value);
        const explicitNone = !isNew && payload.form === null;
        return `<div class="form-row"><label>${esc(part.label)}</label>${verbCellHtml({ type: 'participle', participle: part.value, value: payload.form, explicitNone })}</div>`;
      }).join('')}
    </div>
    <div id="verb-forms-card" class="card">
      <h2>Conjugations</h2>
      <div class="tabs" role="tablist">
        ${state.meta.verb_groups.map(group => `<button type="button" role="tab" data-verb-group="${esc(group.code)}" class="${state.editor.activeVerbGroup === group.code ? 'active' : ''}">${esc(group.label)}</button>`).join('')}
      </div>
      ${state.meta.verb_groups.map(group => renderVerbGroupTable(word, group, isNew)).join('')}
      <button type="button" class="ghost" data-action="set-visible-none">Set blank visible cells to None</button>
    </div>`;
}

function renderVerbGroupTable(word, group, isNew) {
  const active = state.editor.activeVerbGroup === group.code;
  return `
    <div class="verb-table-wrap ${active ? '' : 'hidden'}" data-verb-table="${esc(group.code)}">
      <table class="verb-table">
        <thead>
          <tr><th>Person</th>${group.tenses.map(tense => `<th>${esc(tense.label)}</th>`).join('')}</tr>
        </thead>
        <tbody>
          ${state.meta.persons.map(person => `
            <tr>
              <th scope="row">${esc(group.code === 'imperative' ? person.imperative_label : person.label)}</th>
              ${group.tenses.map(tense => {
                const payload = verbFormValue(word, group.code, tense.code, person.code);
                const explicitNone = !isNew && payload.form === null;
                return `<td>${verbCellHtml({ type: 'verb-form', tense: tense.code, person: person.code, value: payload.form, explicitNone })}</td>`;
              }).join('')}
            </tr>`).join('')}
        </tbody>
      </table>
    </div>`;
}

function nullableCellHtml({ type, number, gender, value, explicitNone, disabled, locked = false }) {
  return `
    <div class="nullable-cell ${locked ? 'locked-cell' : ''}" data-cell="nullable" data-type="${esc(type)}" data-number="${esc(number)}" data-gender="${esc(gender)}" data-locked="${locked ? 'true' : 'false'}">
      <input type="text" value="${esc(value || '')}" ${disabled ? 'disabled' : ''} autocomplete="off" spellcheck="false">
      <label class="none-toggle"><input type="checkbox" data-role="none" ${explicitNone ? 'checked' : ''} ${disabled ? 'disabled' : ''}> ${locked ? 'Locked' : 'None'}</label>
    </div>`;
}

function otherPersonCellHtml({ person, gender, value, explicitNone }) {
  return `
    <div class="nullable-cell" data-cell="nullable" data-type="other-person" data-person="${esc(person)}" data-gender="${esc(gender)}">
      <input type="text" value="${esc(value || '')}" autocomplete="off" spellcheck="false">
      <label class="none-toggle"><input type="checkbox" data-role="none" ${explicitNone ? 'checked' : ''}> None</label>
    </div>`;
}

function verbCellHtml({ type, participle, tense, person, value, explicitNone }) {
  return `
    <div class="nullable-cell verb-cell" data-cell="verb-cell" data-type="${esc(type)}" data-participle="${esc(participle || '')}" data-tense="${esc(tense || '')}" data-person="${esc(person || '')}">
      <input type="text" value="${esc(value || '')}" autocomplete="off" spellcheck="false">
      <label class="none-toggle"><input type="checkbox" data-role="none" ${explicitNone ? 'checked' : ''}> None</label>
    </div>`;
}

function wireNullableCells() {
  document.querySelectorAll('[data-cell]').forEach(cell => {
    const input = cell.querySelector('input[type="text"]');
    const none = cell.querySelector('[data-role="none"]');
    const sync = () => {
      if (cell.dataset.locked === 'true') {
        input.disabled = true;
        if (none) {
          none.checked = false;
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
  setupTuVosPairs('verb-form');
  setupTuVosPairs('other-person');
}

function setupTuVosPairs(type) {
  document.querySelectorAll(`[data-type="${type}"][data-person="vos"]`).forEach(vosCell => {
    const tuCell = matchingTuCell(type, vosCell);
    vosCell.dataset.manualVos = tuCell && sameNullableState(tuCell, vosCell) ? 'false' : 'true';
    vosCell.querySelector('input[type="text"]')?.addEventListener('input', () => {
      vosCell.dataset.manualVos = 'true';
    });
    vosCell.querySelector('[data-role="none"]')?.addEventListener('change', () => {
      vosCell.dataset.manualVos = 'true';
    });
  });

  document.querySelectorAll(`[data-type="${type}"][data-person="tu"]`).forEach(tuCell => {
    const copyToVos = () => {
      const vosCell = matchingVosCell(type, tuCell);
      if (!vosCell || vosCell.dataset.manualVos === 'true') return;
      copyNullableState(tuCell, vosCell);
    };
    tuCell.querySelector('input[type="text"]')?.addEventListener('input', copyToVos);
    tuCell.querySelector('[data-role="none"]')?.addEventListener('change', copyToVos);
  });
}

function matchingTuCell(type, vosCell) {
  return matchingPersonCell(type, vosCell, 'tu');
}

function matchingVosCell(type, tuCell) {
  return matchingPersonCell(type, tuCell, 'vos');
}

function matchingPersonCell(type, cell, person) {
  if (type === 'verb-form') {
    return document.querySelector(
      `[data-type="verb-form"][data-tense="${cssEscape(cell.dataset.tense)}"][data-person="${person}"]`
    );
  }
  return document.querySelector(
    `[data-type="other-person"][data-gender="${cssEscape(cell.dataset.gender)}"][data-person="${person}"]`
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

  document.querySelectorAll('[data-action="set-visible-none"]').forEach(button => {
    button.addEventListener('click', () => {
      const scope = button.closest('.card');
      scope.querySelectorAll('[data-cell]').forEach(cell => {
        if (cell.closest('.hidden')) return;
        const input = cell.querySelector('input[type="text"]');
        const none = cell.querySelector('[data-role="none"]');
        if (!input.disabled && !input.value.trim() && none && !none.disabled) {
          none.checked = true;
          input.value = '';
          input.dispatchEvent(new Event('input', { bubbles: true }));
          none.dispatchEvent(new Event('change', { bubbles: true }));
        }
      });
      markDirty();
      updateEditorUi();
    });
  });
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
  const word = currentWordShell();
  const title = document.getElementById('editor-title');
  if (title) title.textContent = `${editorTitle(word)} *`;
  const status = document.getElementById('dirty-status');
  if (status) {
    status.textContent = 'Unsaved changes';
    status.className = 'unsaved';
  }
  const message = document.getElementById('editor-message');
  if (message) message.innerHTML = '';
}

function updateEditorUi() {
  const wordType = state.editor?.word.word_type;
  const english = document.getElementById('english-input')?.value.trim() || '';
  const helper = document.getElementById('helper-text');
  const saveButton = document.getElementById('save-button');
  let valid = false;
  let helperText = '';

  if (wordType === 'noun') {
    const gender = document.getElementById('gender-select')?.value || '';
    const grid = document.getElementById('nominal-grid-card');
    if (grid) grid.classList.toggle('hidden', !english || !gender);
    syncNominalGridAvailability(gender || 'both');
    if (!english) helperText = 'Enter the English definition to unlock gender and inflections.';
    else if (!gender) helperText = 'Choose gender to unlock the inflections table.';
    else if (!allVisibleNullableCellsComplete(grid)) helperText = 'Every visible form must be filled or explicitly marked None.';
    valid = Boolean(document.getElementById('lemma-input')?.value.trim() && english && gender && !helperText);
  } else if (wordType === 'adjective') {
    const grid = document.getElementById('adjective-grid-card');
    if (grid) grid.classList.toggle('hidden', !english);
    if (!english) helperText = 'Enter the English definition to unlock adjective forms.';
    else if (!allRequiredFormCellsComplete(grid)) helperText = 'Fill all four adjective forms.';
    valid = Boolean(document.getElementById('lemma-input')?.value.trim() && english && !helperText);
  } else if (wordType === 'other') {
    const type = document.getElementById('inflection-type-select')?.value || '';
    const grid = document.getElementById('other-grid-card');
    const personGrid = document.getElementById('other-person-grid-card');
    if (grid) grid.classList.toggle('hidden', !english || type !== 'gender_plurality');
    if (personGrid) personGrid.classList.toggle('hidden', !english || type !== 'person_gender_plurality');
    if (!english) helperText = 'Enter the English definition to unlock the inflection type.';
    else if (!type) helperText = 'Choose inflection type.';
    else if (type === 'gender_plurality' && !allVisibleNullableCellsComplete(grid)) helperText = 'Every visible form must be filled or explicitly marked None.';
    else if (type === 'person_gender_plurality' && !allVisibleNullableCellsComplete(personGrid)) helperText = 'Every visible form must be filled or explicitly marked None.';
    valid = Boolean(document.getElementById('lemma-input')?.value.trim() && english && type && !helperText);
  } else if (wordType === 'verb') {
    const cards = [document.getElementById('verb-participles-card'), document.getElementById('verb-forms-card')];
    cards.forEach(card => card?.classList.toggle('hidden', !english));
    if (!english) helperText = 'Enter the English definition to unlock participles and conjugations.';
    else if (!allVerbCellsComplete()) helperText = 'Every visible verb cell must be filled or explicitly marked None.';
    valid = Boolean(document.getElementById('lemma-input')?.value.trim() && english && !helperText);
  }

  if (helper) {
    helper.textContent = helperText;
    helper.classList.toggle('hidden', !helperText);
  }
  if (saveButton) saveButton.disabled = !valid;
}

function syncNominalGridAvailability(genderAvailability) {
  const wordType = state.editor?.word.word_type;
  const lemma = document.getElementById('lemma-input')?.value.trim() || '';
  document.querySelectorAll('[data-cell="nullable"]').forEach(cell => {
    const number = cell.dataset.number;
    const gender = cell.dataset.gender;
    const locked = isLockedNounDefault(wordType, genderAvailability, number, gender);
    const enabled = isGenderEnabled(genderAvailability, gender);
    const input = cell.querySelector('input[type="text"]');
    const none = cell.querySelector('[data-role="none"]');

    cell.dataset.locked = locked ? 'true' : 'false';
    cell.classList.toggle('locked-cell', locked);

    if (locked) {
      input.value = lemma;
      input.disabled = true;
      none.checked = false;
      none.disabled = true;
      none.closest('label').lastChild.textContent = ' Locked';
    } else if (!enabled) {
      input.value = '';
      input.disabled = true;
      none.checked = true;
      none.disabled = true;
      none.closest('label').lastChild.textContent = ' None';
    } else {
      none.disabled = false;
      none.closest('label').lastChild.textContent = ' None';
      input.disabled = none.checked;
    }
  });
}

function allVisibleNullableCellsComplete(scope) {
  if (!scope || scope.classList.contains('hidden')) return true;
  return Array.from(scope.querySelectorAll('[data-cell]')).every(cell => {
    if (cell.closest('.hidden')) return true;
    const input = cell.querySelector('input[type="text"]');
    const none = cell.querySelector('[data-role="none"]');
    if (none?.disabled) return true;
    return Boolean(none?.checked || input.value.trim());
  });
}

function allRequiredFormCellsComplete(scope) {
  if (!scope || scope.classList.contains('hidden')) return true;
  return Array.from(scope.querySelectorAll('[data-cell="required-form"] input[type="text"]')).every(input => Boolean(input.value.trim()));
}

function allVerbCellsComplete() {
  const cards = [document.getElementById('verb-participles-card'), document.getElementById('verb-forms-card')];
  return cards.every(card => allVisibleNullableCellsComplete(card));
}

function currentWordShell() {
  const base = state.editor.word;
  return {
    ...base,
    lemma: document.getElementById('lemma-input')?.value || base.lemma,
    english: document.getElementById('english-input')?.value || base.english,
  };
}

function editorTitle(word) {
  const lemma = (word.lemma || '').trim() || 'Untitled';
  const label = WORD_TYPE_LABELS[word.word_type] || word.word_type;
  return `${label}: ${lemma}`;
}

function isGenderEnabled(availability, gender) {
  if (availability === 'masc') return gender === 'masc';
  if (availability === 'fem') return gender === 'fem';
  return true;
}

function isLockedNounDefault(wordType, availability, number, gender) {
  return wordType === 'noun'
    && number === 'singular'
    && ((availability === 'masc' && gender === 'masc') || (availability === 'fem' && gender === 'fem'));
}

function collectPayload() {
  const wordType = state.editor.word.word_type;
  const payload = {
    word_type: wordType,
    lemma: document.getElementById('lemma-input').value.trim(),
    english: document.getElementById('english-input').value.trim(),
  };
  if (!payload.lemma) throw new Error('lemma cannot be empty');
  if (!payload.english) throw new Error('english definition cannot be empty');

  if (wordType === 'noun') {
    payload.gender_availability = document.getElementById('gender-select').value;
    if (!payload.gender_availability) throw new Error('choose gender');
    if (!allVisibleNullableCellsComplete(document.getElementById('nominal-grid-card'))) throw new Error('Every visible form must be filled or explicitly marked None.');
    payload.forms = collectNominalForms(document.getElementById('nominal-grid-card'));
  } else if (wordType === 'adjective') {
    if (!allRequiredFormCellsComplete(document.getElementById('adjective-grid-card'))) throw new Error('Fill all four adjective forms.');
    payload.gender_availability = 'both';
    payload.forms = collectRequiredForms(document.getElementById('adjective-grid-card'));
  } else if (wordType === 'other') {
    const type = document.getElementById('inflection-type-select').value;
    if (!type) throw new Error('choose inflection type');
    payload.inflection_type = type;
    payload.forms = emptyNestedForms();
    payload.person_forms = emptyPersonGenderForms();
    if (type === 'gender_plurality') {
      const grid = document.getElementById('other-grid-card');
      if (!allVisibleNullableCellsComplete(grid)) throw new Error('Every visible form must be filled or explicitly marked None.');
      payload.forms = collectNominalForms(grid);
    } else if (type === 'person_gender_plurality') {
      const grid = document.getElementById('other-person-grid-card');
      if (!allVisibleNullableCellsComplete(grid)) throw new Error('Every visible form must be filled or explicitly marked None.');
      payload.person_forms = collectOtherPersonForms(grid);
    }
  } else if (wordType === 'verb') {
    if (!allVerbCellsComplete()) throw new Error('Every visible verb cell must be filled or explicitly marked None.');
    payload.participles = collectParticiples();
    payload.forms = collectVerbForms();
  }
  return payload;
}

function collectNominalForms(scope) {
  const forms = emptyNestedForms();
  scope.querySelectorAll('[data-cell="nullable"]').forEach(cell => {
    const number = cell.dataset.number;
    const gender = cell.dataset.gender;
    const input = cell.querySelector('input[type="text"]');
    const none = cell.querySelector('[data-role="none"]');
    forms[number][gender] = cell.dataset.locked === 'true'
      ? (input.value.trim() || null)
      : (none.checked || input.disabled) ? null : (input.value.trim() || null);
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

function collectOtherPersonForms(scope) {
  const forms = emptyPersonGenderForms();
  scope.querySelectorAll('[data-cell="nullable"][data-type="other-person"]').forEach(cell => {
    const person = cell.dataset.person;
    const gender = cell.dataset.gender;
    const input = cell.querySelector('input[type="text"]');
    const none = cell.querySelector('[data-role="none"]');
    if (forms[person]) forms[person][gender] = none.checked ? null : (input.value.trim() || null);
  });
  return forms;
}

function collectParticiples() {
  const participles = {};
  state.meta.participle_types.forEach(part => {
    const cell = document.querySelector(`[data-cell="verb-cell"][data-type="participle"][data-participle="${cssEscape(part.value)}"]`);
    participles[part.value] = collectVerbCell(cell);
  });
  return participles;
}

function collectVerbForms() {
  const forms = {};
  document.querySelectorAll('[data-cell="verb-cell"][data-type="verb-form"]').forEach(cell => {
    const tense = cell.dataset.tense;
    const person = cell.dataset.person;
    forms[tense] ||= {};
    forms[tense][person] = collectVerbCell(cell);
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
    const path = isNew ? '/api/words' : `/api/words/${state.editor.word.id}`;
    const method = isNew ? 'POST' : 'PUT';
    const data = await api(path, { method, body: JSON.stringify(payload) });
    state.editor.word = data.word;
    state.editor.isNew = false;
    state.editor.dirty = false;
    state.query = data.word.lemma;
    state.selectedType = data.word.word_type;
    await runSearch();
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
    singular: { masc: null, fem: null },
    plural: { masc: null, fem: null },
  };
}

function emptyPersonGenderForms() {
  const forms = {};
  (state.meta?.persons || []).forEach(person => {
    forms[person.code] = { masc: null, fem: null };
  });
  return forms;
}

function emptyParticiples() {
  return {
    present: { form: null },
    past: { form: null },
  };
}

function verbParticipleValue(word, type) {
  return word.verb?.participles?.[type] || { form: null };
}

function verbFormValue(word, groupCode, tenseCode, personCode) {
  const person = word.verb?.forms?.[groupCode]?.[tenseCode]?.persons?.[personCode];
  return { form: person?.form ?? null };
}

function cssEscape(value) {
  if (window.CSS?.escape) return CSS.escape(value);
  return String(value).replace(/[^a-zA-Z0-9_-]/g, '\\$&');
}

init();
