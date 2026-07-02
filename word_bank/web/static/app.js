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

const LEXICAL_ITEM_TYPE_LABELS = {
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
    app.innerHTML = `<section class="panel"><h1>Spanish Word Bank</h1><div class="error-box">${esc(error.message)}</div></section>`;
  }
}

function renderHome() {
  state.editor = null;
  const lexicalItemTypes = Object.keys(state.meta.lexical_item_types);
  app.innerHTML = `
    <section class="panel">
      <div class="header-row">
        <h1>Spanish Word Bank</h1>
      </div>
      <div class="lexical-item-type-grid" role="group" aria-label="Lexical item class">
        ${lexicalItemTypes.map(type => `<button type="button" data-type="${esc(type)}" class="${state.selectedType === type ? 'active' : ''}">${esc(state.meta.lexical_item_types[type].button)}</button>`).join('')}
      </div>
      <div id="entry-panel" class="${state.selectedType ? '' : 'hidden'}">
        <div class="card">
          <h2 id="selected-class">${state.selectedType ? esc(state.meta.lexical_item_types[state.selectedType].button) : ''}</h2>
          <div class="form-row">
            <label for="lexical-item-search">Headword</label>
            <input id="lexical-item-search" type="text" autocomplete="off" spellcheck="false" value="${esc(state.query)}" placeholder="Type a Spanish lexical item">
          </div>
          <div class="results-title" id="results-title">${state.selectedType ? `Already added ${esc(state.meta.lexical_item_types[state.selectedType].plural)}` : ''}</div>
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

  const input = document.getElementById('lexical-item-search');
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
        createDraft();
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
    const data = await api(`/api/search?lexical_item_type=${encodeURIComponent(type)}&q=${encodeURIComponent(query)}`);
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
    <div class="search-result" data-lexical-item-id="${Number(result.id)}">
      <div class="search-result-main" tabindex="0" role="button">
        <strong>${highlightMatch(result.headword, state.query)}</strong>
        ${result.explanation ? `<span class="muted">${highlightMatch(result.explanation, state.query)}</span>` : ''}
      </div>
      <button type="button" class="danger" data-delete-id="${Number(result.id)}">Delete</button>
    </div>`).join('');

  box.querySelectorAll('.search-result-main').forEach(row => {
    const id = Number(row.closest('.search-result').dataset.lexicalItemId);
    row.addEventListener('click', () => openLexicalItem(id));
    row.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        openLexicalItem(id);
      }
    });
  });
  box.querySelectorAll('[data-delete-id]').forEach(button => {
    button.addEventListener('click', () => deleteLexicalItem(Number(button.dataset.deleteId)));
  });
}

function highlightMatch(headword, query) {
  const text = String(headword || '');
  const needle = String(query || '').trim();
  if (!needle) return esc(text);
  const index = text.toLocaleLowerCase().indexOf(needle.toLocaleLowerCase());
  if (index < 0) return esc(text);
  return `${esc(text.slice(0, index))}<b>${esc(text.slice(index, index + needle.length))}</b>${esc(text.slice(index + needle.length))}`;
}

function findExactMatch() {
  const query = state.query.trim().toLocaleLowerCase();
  if (!query) return null;
  return state.results.find(result => String(result.headword || '').trim().toLocaleLowerCase() === query) || null;
}

function updateCreateButton() {
  const button = document.getElementById('create-button');
  if (!button || !state.selectedType) return;
  const query = state.query.trim();
  const label = state.meta.lexical_item_types[state.selectedType].singular;
  const exact = findExactMatch();
  button.disabled = !query;
  button.textContent = !query
    ? `Create new ${label}`
    : exact
      ? `Create duplicate ${label}: ${query}`
      : `Create new ${label}: ${query}`;
}

async function openLexicalItem(id) {
  try {
    const data = await api(`/api/lexical-items/${id}`);
    startEditor(data.lexical_item, false);
  } catch (error) {
    showHomeError(error.message);
  }
}

function createDraft() {
  const headword = state.query.trim();
  if (!state.selectedType || !headword) return;
  startEditor(makeDraftLexicalItem(state.selectedType, headword), true);
}

async function deleteLexicalItem(id) {
  const item = state.results.find(result => Number(result.id) === id);
  const headword = item?.headword || 'this lexical item';
  if (!confirm(`Delete ${headword}? This cannot be undone.`)) return;
  try {
    await api(`/api/lexical-items/${id}`, { method: 'DELETE' });
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

function makeDraftLexicalItem(lexicalItemType, headwordText) {
  const item = { id: null, lexical_item_type: lexicalItemType, headword: headwordText, explanation: '' };
  if (lexicalItemType === 'noun') {
    item.noun = { gender_availability: '', inflections: emptyNestedForms() };
  } else if (lexicalItemType === 'adjective') {
    item.adjective = { adjective_inflection_type: '', inflections: emptyNestedForms() };
  } else if (lexicalItemType === 'other') {
    item.other = { inflection_type: '', inflections: emptyNestedForms() };
  } else if (lexicalItemType === 'verb') {
    item.verb = { forms: {} };
  }
  return item;
}

// ---------------------------------------------------------------------------
// Editor model: the single source of truth.
// A "cell" is { text, none }. The DOM only ever reflects this model.
// ---------------------------------------------------------------------------

function makeCell(text, none) {
  return { text: text || '', none: Boolean(none) };
}

function sameCell(a, b) {
  return a.none === b.none && a.text === b.text;
}

function buildModel(item, isNew) {
  const model = {
    id: item.id ?? null,
    lexical_item_type: item.lexical_item_type,
    headword: item.headword || '',
    explanation: item.explanation || '',
  };
  const type = model.lexical_item_type;
  if (type === 'noun') {
    const details = item.noun || {};
    model.gender_availability = details.gender_availability || '';
    model.forms = buildNounForms(details.inflections, model.gender_availability, isNew);
  } else if (type === 'adjective') {
    const details = item.adjective || {};
    model.inflection_type = details.adjective_inflection_type || '';
    model.forms = buildRequiredForms(details.inflections);
  } else if (type === 'other') {
    const details = item.other || {};
    model.inflection_type = details.inflection_type || '';
    model.forms = buildRequiredForms(details.inflections);
  } else if (type === 'verb') {
    model.verb = buildVerbCells(item, isNew);
  }
  return model;
}

function buildNounForms(inflections, genderAvailability, isNew) {
  const forms = {};
  for (const number of state.meta.numbers) {
    forms[number] = {};
    for (const gender of state.meta.genders) {
      const enabled = isGenderEnabled(genderAvailability || 'both', gender);
      const raw = inflections?.[number]?.[gender];
      forms[number][gender] = enabled
        ? makeCell(raw ?? '', !isNew && raw === null)
        : makeCell('', true);
    }
  }
  return forms;
}

function buildRequiredForms(inflections) {
  const forms = {};
  for (const number of state.meta.numbers) {
    forms[number] = {
      masculine: makeCell(inflections?.[number]?.masculine ?? '', false),
      feminine: makeCell(inflections?.[number]?.feminine ?? '', false),
      shared: makeCell(inflections?.[number]?.shared ?? '', false),
    };
  }
  return forms;
}

function buildVerbCells(item, isNew) {
  const forms = item.verb?.forms || {};
  const cells = {};
  for (const code of allVerbCodes()) {
    const raw = forms[code]?.form;
    cells[code] = makeCell(raw ?? '', !isNew && raw === null);
  }
  return cells;
}

function allVerbCodes() {
  const codes = [];
  for (const participle of state.meta.verb_participles) codes.push(participle.code);
  for (const group of state.meta.verb_groups) {
    for (const tense of group.tenses) {
      for (const form of tense.forms) codes.push(form.code);
    }
  }
  return codes;
}

function buildVerbCodeIndex() {
  const participles = state.meta.verb_participles.map(participle => participle.code);
  const byGroup = {};
  const tuToVos = {};
  for (const group of state.meta.verb_groups) {
    const list = [];
    for (const tense of group.tenses) {
      let tu = null;
      let vos = null;
      for (const form of tense.forms) {
        list.push(form.code);
        if (form.person_code === 'tu') tu = form.code;
        if (form.person_code === 'vos') vos = form.code;
      }
      if (tu && vos) tuToVos[tu] = vos;
    }
    byGroup[group.code] = list;
  }
  const all = [...participles];
  for (const group of state.meta.verb_groups) all.push(...byGroup[group.code]);
  return { participles, byGroup, all, tuToVos };
}

// ---------------------------------------------------------------------------
// Per-type editor registry: render / derive UI / collect payload.
// ---------------------------------------------------------------------------

const EDITORS = {
  noun: {
    renderBody(model, isNew) {
      return `
        ${commonBaseCard(model, isNew, genderRow(model))}
        <p id="helper-text" class="helper"></p>
        <div id="noun-grid-card" class="card">${nounGridCardInner(model)}</div>`;
    },
    deriveUi(model) {
      const explanation = model.explanation.trim();
      const gender = model.gender_availability || '';
      const visibility = { 'noun-grid-card': !explanation || !gender };
      let helperText = '';
      if (!explanation) helperText = 'Enter the explanation to unlock gender and inflections.';
      else if (!gender) helperText = 'Choose gender to unlock the inflections table.';
      else if (!nounCellsComplete(model)) helperText = CELL_REQUIRED_MESSAGE;
      else if (!anyNounForm(model)) helperText = 'A noun needs at least one form.';
      const valid = Boolean(model.headword.trim() && explanation && gender && !helperText);
      return { valid, helperText, visibility };
    },
    collect(model) {
      if (!model.gender_availability) throw new Error('choose gender');
      if (!nounCellsComplete(model)) throw new Error(CELL_REQUIRED_MESSAGE);
      if (!anyNounForm(model)) throw new Error('A noun needs at least one form.');
      const forms = emptyNestedForms();
      const genderAvailability = model.gender_availability;
      for (const number of state.meta.numbers) {
        for (const gender of state.meta.genders) {
          const enabled = isGenderEnabled(genderAvailability, gender);
          const cell = model.forms[number][gender];
          forms[number][gender] = (cell.none || !enabled) ? null : (cell.text.trim() || null);
        }
      }
      return { gender_availability: genderAvailability, forms };
    },
  },

  adjective: {
    renderBody(model, isNew) {
      return `
        ${commonBaseCard(model, isNew, adjectiveTypeRow(model))}
        <p id="helper-text" class="helper"></p>
        <div id="adjective-plurality-card" class="card">${pluralityCardInner('Plurality', model, true)}</div>
        <div id="adjective-gender-grid-card" class="card">${genderRequiredCardInner('Plurality + gender', model, true)}</div>`;
    },
    deriveUi(model) {
      const explanation = model.explanation.trim();
      const type = model.inflection_type || '';
      const visibility = {
        'adjective-plurality-card': !explanation || type !== 'plurality',
        'adjective-gender-grid-card': !explanation || type !== 'gender_plurality',
      };
      let helperText = '';
      if (!explanation) helperText = 'Enter the explanation to unlock adjective forms.';
      else if (!type) helperText = 'Choose what the adjective is inflective by.';
      else if (type === 'plurality' && !pluralityComplete(model)) helperText = CELL_REQUIRED_MESSAGE;
      else if (type === 'gender_plurality' && !genderComplete(model)) helperText = CELL_REQUIRED_MESSAGE;
      const valid = Boolean(model.headword.trim() && explanation && type && !helperText);
      return { valid, helperText, visibility };
    },
    collect(model) {
      const type = model.inflection_type;
      if (!type) throw new Error('choose what the adjective is inflective by');
      return { adjective_inflection_type: type, forms: collectInflectionForms(model, type) };
    },
  },

  other: {
    renderBody(model, isNew) {
      return `
        ${commonBaseCard(model, isNew, otherTypeRow(model))}
        <p id="helper-text" class="helper"></p>
        <div id="other-plurality-card" class="card">${pluralityCardInner('Plurality', model, false)}</div>
        <div id="other-grid-card" class="card">${genderRequiredCardInner('Plurality + gender', model, false)}</div>`;
    },
    deriveUi(model) {
      const explanation = model.explanation.trim();
      const type = model.inflection_type || '';
      const visibility = {
        'other-plurality-card': !explanation || type !== 'plurality',
        'other-grid-card': !explanation || type !== 'gender_plurality',
      };
      let helperText = '';
      if (!explanation) helperText = 'Enter the explanation to unlock the inflection type.';
      else if (!type) helperText = 'Choose inflection type.';
      else if (type === 'plurality' && !pluralityComplete(model)) helperText = CELL_REQUIRED_MESSAGE;
      else if (type === 'gender_plurality' && !genderComplete(model)) helperText = CELL_REQUIRED_MESSAGE;
      const valid = Boolean(model.headword.trim() && explanation && type && !helperText);
      return { valid, helperText, visibility };
    },
    collect(model) {
      const type = model.inflection_type;
      if (!type) throw new Error('choose inflection type');
      const forms = type === 'plurality' || type === 'gender_plurality'
        ? collectInflectionForms(model, type)
        : emptyNestedForms();
      return { inflection_type: type, forms };
    },
  },

  verb: {
    renderBody(model, isNew) {
      return `
        ${commonBaseCard(model, isNew)}
        <p id="helper-text" class="helper"></p>
        <div id="verb-participles-card" class="card">${verbParticiplesInner(model)}</div>
        <div id="verb-forms-card" class="card">${verbFormsInner(model)}</div>`;
    },
    deriveUi(model) {
      const explanation = model.explanation.trim();
      const visibility = {
        'verb-participles-card': !explanation,
        'verb-forms-card': !explanation,
      };
      let helperText = '';
      if (!explanation) helperText = 'Enter the explanation to unlock participles and conjugations.';
      else if (!verbActiveComplete(model)) helperText = CELL_REQUIRED_MESSAGE;
      const valid = Boolean(model.headword.trim() && explanation && !helperText);
      return { valid, helperText, visibility };
    },
    collect(model) {
      if (!verbActiveComplete(model)) throw new Error(CELL_REQUIRED_MESSAGE);
      const forms = {};
      for (const code of state.editor.verbCodes.all) {
        const cell = model.verb[code];
        forms[code] = { form: cell.none ? null : (cell.text.trim() || null) };
      }
      return { forms };
    },
  },
};

// ---------------------------------------------------------------------------
// Validation helpers (model-driven, no DOM scans).
// ---------------------------------------------------------------------------

function nounCellsComplete(model) {
  const genderAvailability = model.gender_availability || 'both';
  for (const number of state.meta.numbers) {
    for (const gender of state.meta.genders) {
      if (!isGenderEnabled(genderAvailability, gender)) continue;
      const cell = model.forms[number][gender];
      if (!(cell.none || cell.text.trim())) return false;
    }
  }
  return true;
}

function anyNounForm(model) {
  const genderAvailability = model.gender_availability || 'both';
  for (const number of state.meta.numbers) {
    for (const gender of state.meta.genders) {
      if (!isGenderEnabled(genderAvailability, gender)) continue;
      const cell = model.forms[number][gender];
      if (!cell.none && cell.text.trim()) return true;
    }
  }
  return false;
}

function pluralityComplete(model) {
  return state.meta.numbers.every(number => Boolean(model.forms[number].shared.text.trim()));
}

function genderComplete(model) {
  return state.meta.numbers.every(number =>
    state.meta.genders.every(gender => Boolean(model.forms[number][gender].text.trim())));
}

function verbActiveComplete(model) {
  const index = state.editor.verbCodes;
  const codes = [...index.participles, ...(index.byGroup[state.editor.activeVerbGroup] || [])];
  return codes.every(code => {
    const cell = model.verb[code];
    return cell.none || cell.text.trim();
  });
}

function collectInflectionForms(model, type) {
  const forms = emptyNestedForms();
  if (type === 'plurality') {
    if (!pluralityComplete(model)) throw new Error(CELL_REQUIRED_MESSAGE);
    for (const number of state.meta.numbers) {
      forms[number].shared = model.forms[number].shared.text.trim();
    }
  } else {
    if (!genderComplete(model)) throw new Error(CELL_REQUIRED_MESSAGE);
    for (const number of state.meta.numbers) {
      for (const gender of state.meta.genders) {
        forms[number][gender] = model.forms[number][gender].text.trim();
      }
    }
  }
  return forms;
}

// ---------------------------------------------------------------------------
// Editor lifecycle + render.
// ---------------------------------------------------------------------------

function startEditor(item, isNew) {
  const firstVerbGroup = state.meta.verb_groups[0]?.code || 'indicative';
  const model = buildModel(item, isNew);
  const editor = {
    model,
    isNew,
    dirty: false,
    activeVerbGroup: firstVerbGroup,
    error: '',
  };
  if (model.lexical_item_type === 'verb') {
    editor.verbCodes = buildVerbCodeIndex();
    editor.vosManual = {};
    for (const tu of Object.keys(editor.verbCodes.tuToVos)) {
      const vos = editor.verbCodes.tuToVos[tu];
      editor.vosManual[vos] = !sameCell(model.verb[tu], model.verb[vos]);
    }
  }
  state.editor = editor;
  renderEditor();
}

function renderEditor() {
  const editor = state.editor;
  if (!editor) return;
  const model = editor.model;
  app.innerHTML = `
    <section class="panel editor-panel">
      <div class="header-row">
        <h1 id="editor-title">${esc(editorTitle(model))}${editor.dirty ? ' *' : ''}</h1>
        <button id="back-button" type="button" class="ghost">Go back</button>
      </div>
      <div id="editor-message">${renderMessage()}</div>
      <form id="editor-form" novalidate>
        ${EDITORS[model.lexical_item_type].renderBody(model, editor.isNew)}
      </form>
      <div class="status-row">
        <span id="dirty-status" class="${editor.dirty ? 'unsaved' : 'muted'}">${editor.dirty ? 'Unsaved changes' : editor.isNew ? 'New lexical item' : 'Saved'}</span>
        <div class="action-row">
          <button type="button" id="discard-button" class="ghost">Discard</button>
          <button type="button" id="save-button" class="primary">Save &amp; go back</button>
        </div>
      </div>
    </section>`;

  document.getElementById('back-button').addEventListener('click', leaveEditor);
  document.getElementById('discard-button').addEventListener('click', leaveEditor);
  document.getElementById('save-button').addEventListener('click', saveEditor);

  const form = document.getElementById('editor-form');
  form.addEventListener('input', onFormEvent);
  form.addEventListener('change', onFormEvent);
  form.addEventListener('click', onFormClick);
  form.addEventListener('keydown', onFormKeydown);

  refreshUi();
}

function renderMessage() {
  if (state.editor.error) return `<div class="error-box">${esc(state.editor.error)}</div>`;
  return '';
}

function commonBaseCard(model, isNew, extraRows = '') {
  return `
    <div class="card">
      <h2>Base</h2>
      <div class="form-row">
        <label for="headword-input">Headword</label>
        <input id="headword-input" name="headword" value="${esc(model.headword)}" ${isNew ? 'readonly' : ''} required autocomplete="off" spellcheck="false">
      </div>
      <div class="form-row">
        <label for="explanation-input">Explanation</label>
        <input id="explanation-input" name="explanation" value="${esc(model.explanation)}" required placeholder="Write the explanation first" autocomplete="off" spellcheck="false">
      </div>
      ${extraRows}
    </div>`;
}

function renderAutoFillButton() {
  return `<div class="action-row"><button type="button" class="ghost" data-action="auto-fill">Auto-fill</button></div>
    <p class="helper auto-fill-disclaimer hidden">Please check the forms yourself. Auto-fill is not always 100% correct.</p>`;
}

// ---- Type-specific selector rows -----------------------------------------

function genderRow(model) {
  const choices = state.meta.gender_choices.map(choice => `
    <option value="${esc(choice.value)}" ${model.gender_availability === choice.value ? 'selected' : ''}>${esc(choice.label)}</option>`).join('');
  return `
    <div class="form-row">
      <label for="gender-select">Gender</label>
      <select id="gender-select" name="gender_availability">
        <option value="">Choose gender…</option>
        ${choices}
      </select>
    </div>`;
}

function adjectiveTypeRow(model) {
  const selected = model.inflection_type || '';
  const options = state.meta.adjective_inflection_types.map(type => `
    <option value="${esc(type.value)}" ${selected === type.value ? 'selected' : ''}>${esc(type.label)}</option>`).join('');
  return `
    <div id="adjective-type-row" class="form-row">
      <label for="adjective-inflection-type-select">Is inflective by</label>
      <select id="adjective-inflection-type-select" name="adjective_inflection_type">
        <option value="" ${selected ? '' : 'selected'}>Choose type…</option>
        ${options}
      </select>
    </div>`;
}

function otherTypeRow(model) {
  const selected = model.inflection_type || '';
  const options = state.meta.other_inflection_types.map(type => `
    <option value="${esc(type.value)}" ${selected === type.value ? 'selected' : ''}>${esc(type.label)}</option>`).join('');
  return `
    <div class="form-row">
      <label for="inflection-type-select">Inflection type</label>
      <select id="inflection-type-select" name="inflection_type">
        <option value="" ${selected ? '' : 'selected'}>Choose type…</option>
        ${options}
      </select>
    </div>`;
}

// ---- Card bodies (re-rendered on structural changes) ----------------------

function nounGridCardInner(model) {
  return `<h2>Inflections</h2>${renderAutoFillButton()}${renderGenderNullableGrid(model)}`;
}

function pluralityCardInner(title, model, includeAutoFill) {
  return `<h2>${esc(title)}</h2>${includeAutoFill ? renderAutoFillButton() : ''}${renderPluralityGrid(model)}`;
}

function genderRequiredCardInner(title, model, includeAutoFill) {
  return `<h2>${esc(title)}</h2>${includeAutoFill ? renderAutoFillButton() : ''}${renderGenderRequiredGrid(model)}`;
}

function verbParticiplesInner(model) {
  return `<h2>Participles</h2>${state.meta.verb_participles.map(part => {
    const cell = model.verb[part.code];
    return `<div class="form-row"><label>${esc(part.label)}</label>${verbCellHtml({ code: part.code, cell })}</div>`;
  }).join('')}`;
}

function verbFormsInner(model) {
  return `
    <h2>Conjugations</h2>
    <div class="tabs" role="tablist">
      ${state.meta.verb_groups.map(group => `<button type="button" role="tab" data-verb-group="${esc(group.code)}" class="${state.editor.activeVerbGroup === group.code ? 'active' : ''}">${esc(group.label)}</button>`).join('')}
    </div>
    ${state.meta.verb_groups.map(group => renderVerbGroupTable(model, group)).join('')}
    <button type="button" class="ghost" data-action="set-visible-none">Set blank visible cells to None</button>`;
}

function renderVerbGroupTable(model, group) {
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
                const cell = model.verb[form.code];
                return `<td>${verbCellHtml({ code: form.code, group: group.code, slot: tense.code, person: person.code, cell })}</td>`;
              }).join('')}
            </tr>`).join('')}
        </tbody>
      </table>
    </div>`;
}

// ---- Grids ----------------------------------------------------------------

function renderGenderNullableGrid(model) {
  const genderAvailability = model.gender_availability || 'both';
  const visibleGenders = nounVisibleGenders(genderAvailability);
  const rows = state.meta.numbers.map(number => `
    <tr>
      <th scope="row">${esc(number)}</th>
      ${visibleGenders.map(gender => {
        const enabled = isGenderEnabled(genderAvailability, gender);
        const cell = model.forms[number][gender];
        return `<td>${nounCellHtml({ number, gender, cell, disabled: !enabled })}</td>`;
      }).join('')}
    </tr>`).join('');
  return `
    <table class="inflection-grid">
      <thead><tr><th></th>${visibleGenders.map(gender => `<th>${esc(gender)}</th>`).join('')}</tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}

function renderPluralityGrid(model) {
  const rows = state.meta.numbers.map(number => {
    const cell = model.forms[number].shared;
    return `
      <tr>
        <th scope="row">${esc(number)}</th>
        <td>${pluralityCellHtml({ number, cell })}</td>
      </tr>`;
  }).join('');
  return `
    <table class="inflection-grid">
      <thead><tr><th></th><th>Form</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}

function renderGenderRequiredGrid(model) {
  const rows = state.meta.numbers.map(number => `
    <tr>
      <th scope="row">${esc(number)}</th>
      ${state.meta.genders.map(gender => {
        const cell = model.forms[number][gender];
        return `<td>${requiredCellHtml({ number, gender, cell })}</td>`;
      }).join('')}
    </tr>`).join('');
  return `
    <table class="inflection-grid">
      <thead><tr><th></th>${state.meta.genders.map(gender => `<th>${esc(gender)}</th>`).join('')}</tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}

// ---- Cells ----------------------------------------------------------------

function nounCellHtml({ number, gender, cell, disabled }) {
  const inputDisabled = disabled || cell.none;
  return `
    <div class="nullable-cell" data-cell="nullable" data-number="${esc(number)}" data-gender="${esc(gender)}" data-disabled="${disabled ? 'true' : 'false'}">
      <input type="text" value="${esc(cell.text)}" ${inputDisabled ? 'disabled' : ''} autocomplete="off" spellcheck="false">
      <label class="none-toggle"><input type="checkbox" data-role="none" ${cell.none ? 'checked' : ''} ${disabled ? 'disabled' : ''}> None</label>
    </div>`;
}

function requiredCellHtml({ number, gender, cell }) {
  return `
    <div class="nullable-cell" data-cell="required-form" data-number="${esc(number)}" data-gender="${esc(gender)}">
      <input type="text" value="${esc(cell.text)}" autocomplete="off" spellcheck="false">
    </div>`;
}

function pluralityCellHtml({ number, cell }) {
  return `
    <div class="nullable-cell" data-cell="plurality-form" data-number="${esc(number)}">
      <input type="text" value="${esc(cell.text)}" autocomplete="off" spellcheck="false">
    </div>`;
}

function verbCellHtml({ code, group = '', slot = '', person = '', cell }) {
  return `
    <div class="nullable-cell verb-cell" data-cell="verb-cell" data-code="${esc(code)}" data-group="${esc(group)}" data-slot="${esc(slot)}" data-person="${esc(person)}">
      <input type="text" value="${esc(cell.text)}" ${cell.none ? 'disabled' : ''} autocomplete="off" spellcheck="false">
      <label class="none-toggle"><input type="checkbox" data-role="none" ${cell.none ? 'checked' : ''}> None</label>
    </div>`;
}

// ---- Cell navigation (Enter: column-major, then next section) ---------------

function isNavigableCellInput(input) {
  return Boolean(input && input.tagName === 'INPUT' && input.type === 'text' && !input.disabled);
}

function cellInputFromEl(cellEl) {
  const input = cellEl?.querySelector('input[type="text"]');
  return isNavigableCellInput(input) ? input : null;
}

function pushNavigableInput(items, cellEl, verbGroup = null) {
  const input = cellInputFromEl(cellEl);
  if (!input) return;
  items.push({ input, verbGroup });
}

function inflectionGridGenders(table) {
  const headers = [...table.querySelectorAll('thead th')].slice(1);
  if (headers.length) return headers.map(th => th.textContent.trim());
  const genders = [];
  const seen = new Set();
  for (const cell of table.querySelectorAll('[data-gender]')) {
    const gender = cell.dataset.gender;
    if (!seen.has(gender)) {
      seen.add(gender);
      genders.push(gender);
    }
  }
  return genders;
}

function collectInflectionGridInputs(table) {
  const items = [];
  const sample = table.querySelector('[data-cell]');
  if (!sample) return items;

  if (sample.dataset.cell === 'plurality-form') {
    for (const number of state.meta.numbers) {
      const cell = table.querySelector(`[data-cell="plurality-form"][data-number="${cssEscape(number)}"]`);
      pushNavigableInput(items, cell);
    }
    return items;
  }

  const cellType = sample.dataset.cell;
  for (const gender of inflectionGridGenders(table)) {
    for (const number of state.meta.numbers) {
      const cell = table.querySelector(
        `[data-cell="${cssEscape(cellType)}"][data-gender="${cssEscape(gender)}"][data-number="${cssEscape(number)}"]`,
      );
      pushNavigableInput(items, cell);
    }
  }
  return items;
}

function collectVerbGroupInputs(group) {
  const items = [];
  for (const tense of group.tenses) {
    for (const person of group.persons) {
      const form = findVerbDefinition(tense, person.code);
      if (!form) continue;
      const cell = document.querySelector(`[data-cell="verb-cell"][data-code="${cssEscape(form.code)}"]`);
      pushNavigableInput(items, cell, group.code);
    }
  }
  return items;
}

function collectVerbEditorInputs() {
  const items = [];
  for (const participle of state.meta.verb_participles) {
    const cell = document.querySelector(`[data-cell="verb-cell"][data-code="${cssEscape(participle.code)}"]`);
    pushNavigableInput(items, cell);
  }
  for (const group of state.meta.verb_groups) {
    items.push(...collectVerbGroupInputs(group));
  }
  return items;
}

function collectEditorCellInputs() {
  const model = state.editor?.model;
  if (!model) return [];

  switch (model.lexical_item_type) {
    case 'noun': {
      const table = document.querySelector('#noun-grid-card:not(.hidden) .inflection-grid');
      return table ? collectInflectionGridInputs(table) : [];
    }
    case 'adjective':
      return collectVisibleInflectionInputs([
        'adjective-plurality-card',
        'adjective-gender-grid-card',
      ]);
    case 'other':
      return collectVisibleInflectionInputs([
        'other-plurality-card',
        'other-grid-card',
      ]);
    case 'verb':
      return collectVerbEditorInputs();
    default:
      return [];
  }
}

function collectVisibleInflectionInputs(cardIds) {
  for (const id of cardIds) {
    const table = document.querySelector(`#${id}:not(.hidden) .inflection-grid`);
    if (table) return collectInflectionGridInputs(table);
  }
  return [];
}

function focusNextCellInput(currentCellEl) {
  const currentInput = cellInputFromEl(currentCellEl);
  if (!currentInput) return;

  const items = collectEditorCellInputs();
  const idx = items.findIndex(item => item.input === currentInput);
  if (idx < 0 || idx >= items.length - 1) return;

  const next = items[idx + 1];
  if (next.verbGroup && next.verbGroup !== state.editor.activeVerbGroup) {
    setActiveVerbGroup(next.verbGroup);
  }
  next.input.focus();
  next.input.select();
}

function onFormKeydown(event) {
  if (event.key !== 'Enter') return;
  const target = event.target;
  if (!isNavigableCellInput(target)) return;
  const cellEl = target.closest('[data-cell]');
  if (!cellEl) return;
  event.preventDefault();
  focusNextCellInput(cellEl);
}

// ---------------------------------------------------------------------------
// Delegated event handling: every interaction mutates the model, then the DOM
// is reflected from it (targeted patch or card re-render).
// ---------------------------------------------------------------------------

function onFormEvent(event) {
  const target = event.target;
  const model = state.editor.model;

  if (target.id === 'headword-input') {
    model.headword = target.value;
    onModelChanged();
    return;
  }
  if (target.id === 'explanation-input') {
    model.explanation = target.value;
    onModelChanged();
    return;
  }
  if (target.id === 'gender-select') {
    if (event.type === 'change') onGenderChange(target.value);
    return;
  }
  if (target.id === 'adjective-inflection-type-select' || target.id === 'inflection-type-select') {
    if (event.type === 'change') onInflectionTypeChange(target.value);
    return;
  }

  const cellEl = target.closest('[data-cell]');
  if (cellEl) handleCellInput(cellEl, target);
}

function onFormClick(event) {
  const groupButton = event.target.closest('[data-verb-group]');
  if (groupButton) {
    setActiveVerbGroup(groupButton.dataset.verbGroup);
    return;
  }
  const autoFillButton = event.target.closest('[data-action="auto-fill"]');
  if (autoFillButton) {
    event.preventDefault();
    doAutoFill(autoFillButton.closest('.card'));
    return;
  }
  const setNoneButton = event.target.closest('[data-action="set-visible-none"]');
  if (setNoneButton) {
    event.preventDefault();
    doSetVisibleNone();
  }
}

function modelCell(cellEl) {
  const model = state.editor.model;
  const data = cellEl.dataset;
  switch (data.cell) {
    case 'verb-cell': return model.verb[data.code];
    case 'nullable': return model.forms[data.number]?.[data.gender];
    case 'required-form': return model.forms[data.number]?.[data.gender];
    case 'plurality-form': return model.forms[data.number]?.shared;
    default: return null;
  }
}

function handleCellInput(cellEl, target) {
  const cell = modelCell(cellEl);
  if (!cell) return;

  if (target.dataset.role === 'none') {
    cell.none = target.checked;
    if (cell.none) cell.text = '';
    const input = cellEl.querySelector('input[type="text"]');
    if (input) {
      input.value = cell.text;
      input.disabled = cell.none || cellEl.dataset.disabled === 'true';
    }
  } else {
    cell.text = target.value;
    if (target.value.trim()) {
      cell.none = false;
      const checkbox = cellEl.querySelector('[data-role="none"]');
      if (checkbox) checkbox.checked = false;
    }
  }

  if (cellEl.dataset.cell === 'verb-cell') handleVerbSync(cellEl, cell);
  onModelChanged();
}

function handleVerbSync(cellEl, cell) {
  const code = cellEl.dataset.code;
  const person = cellEl.dataset.person;
  if (person === 'vos') {
    state.editor.vosManual[code] = true;
    return;
  }
  if (person !== 'tu') return;
  const vosCode = state.editor.verbCodes.tuToVos[code];
  if (!vosCode || state.editor.vosManual[vosCode]) return;
  const vosCell = state.editor.model.verb[vosCode];
  vosCell.text = cell.text;
  vosCell.none = cell.none;
  const vosEl = document.querySelector(`[data-cell="verb-cell"][data-code="${cssEscape(vosCode)}"]`);
  if (vosEl) mirrorVerbCellDom(vosEl, vosCell);
}

function mirrorVerbCellDom(cellEl, cell) {
  const input = cellEl.querySelector('input[type="text"]');
  const checkbox = cellEl.querySelector('[data-role="none"]');
  if (input) {
    input.value = cell.text;
    input.disabled = cell.none;
  }
  if (checkbox) checkbox.checked = cell.none;
}

function setActiveVerbGroup(code) {
  state.editor.activeVerbGroup = code;
  document.querySelectorAll('[data-verb-group]').forEach(button => button.classList.toggle('active', button.dataset.verbGroup === code));
  document.querySelectorAll('[data-verb-table]').forEach(table => table.classList.toggle('hidden', table.dataset.verbTable !== code));
}

function onGenderChange(value) {
  const model = state.editor.model;
  model.gender_availability = value;
  model.forms = defaultNounForms(value, model.headword);
  const card = document.getElementById('noun-grid-card');
  if (card) card.innerHTML = nounGridCardInner(model);
  onModelChanged();
}

function defaultNounForms(genderAvailability, headword) {
  const forms = {};
  for (const number of state.meta.numbers) {
    forms[number] = {};
    for (const gender of state.meta.genders) {
      const enabled = isGenderEnabled(genderAvailability || 'both', gender);
      if (!enabled) {
        forms[number][gender] = makeCell('', true);
        continue;
      }
      const defaultValue = shouldDefaultNounForm(true, number, gender, genderAvailability) ? (headword || '') : '';
      forms[number][gender] = makeCell(defaultValue, false);
    }
  }
  return forms;
}

function shouldDefaultNounForm(isNew, number, gender, genderAvailability) {
  return isNew
    && number === 'singular'
    && isGenderEnabled(genderAvailability, gender)
    && (genderAvailability !== 'both' || gender === 'masculine');
}

function onInflectionTypeChange(value) {
  const model = state.editor.model;
  model.inflection_type = value;
  model.forms = defaultInflectionForms(value, model.headword);
  const isAdjective = model.lexical_item_type === 'adjective';
  const pluralityCard = document.getElementById(isAdjective ? 'adjective-plurality-card' : 'other-plurality-card');
  const genderCard = document.getElementById(isAdjective ? 'adjective-gender-grid-card' : 'other-grid-card');
  if (pluralityCard) pluralityCard.innerHTML = pluralityCardInner('Plurality', model, isAdjective);
  if (genderCard) genderCard.innerHTML = genderRequiredCardInner('Plurality + gender', model, isAdjective);
  onModelChanged();
}

function defaultInflectionForms(type, headword) {
  const forms = {};
  for (const number of state.meta.numbers) {
    const isSingular = number === 'singular';
    forms[number] = {
      masculine: makeCell(type === 'gender_plurality' && isSingular ? headword : '', false),
      feminine: makeCell('', false),
      shared: makeCell(type === 'plurality' && isSingular ? headword : '', false),
    };
  }
  return forms;
}

function doAutoFill(card) {
  if (!card) return;
  const model = state.editor.model;
  const headword = model.headword.trim();
  if (!headword) {
    showEditorError('Enter a headword first.');
    return;
  }
  const plural = spanishPlural(headword);
  if (card.querySelector('[data-cell="plurality-form"]')) {
    model.forms.singular.shared.text = headword;
    model.forms.plural.shared.text = plural;
  } else {
    const filled = headword.toLocaleLowerCase().endsWith('o')
      ? (() => {
          const stem = headword.slice(0, -1);
          return {
            singular: { masculine: headword, feminine: `${stem}a` },
            plural: { masculine: `${stem}os`, feminine: `${stem}as` },
          };
        })()
      : {
          singular: { masculine: headword, feminine: headword },
          plural: { masculine: plural, feminine: plural },
        };
    const genderAvailability = model.gender_availability;
    for (const number of state.meta.numbers) {
      for (const gender of state.meta.genders) {
        if (genderAvailability && !isGenderEnabled(genderAvailability, gender)) continue;
        const cell = model.forms[number][gender];
        cell.none = false;
        cell.text = filled[number][gender];
      }
    }
  }
  showEditorError('');
  rerenderCard(card, model);
  markDirty();
  refreshUi();
  card.querySelector('.auto-fill-disclaimer')?.classList.remove('hidden');
}

function rerenderCard(cardEl, model) {
  switch (cardEl.id) {
    case 'noun-grid-card':
      cardEl.innerHTML = nounGridCardInner(model);
      break;
    case 'adjective-plurality-card':
      cardEl.innerHTML = pluralityCardInner('Plurality', model, true);
      break;
    case 'adjective-gender-grid-card':
      cardEl.innerHTML = genderRequiredCardInner('Plurality + gender', model, true);
      break;
    case 'other-plurality-card':
      cardEl.innerHTML = pluralityCardInner('Plurality', model, false);
      break;
    case 'other-grid-card':
      cardEl.innerHTML = genderRequiredCardInner('Plurality + gender', model, false);
      break;
    default:
      break;
  }
}

function doSetVisibleNone() {
  const model = state.editor.model;
  for (const code of state.editor.verbCodes.all) {
    const cell = model.verb[code];
    if (!cell.text.trim() && !cell.none) {
      cell.none = true;
      cell.text = '';
    }
  }
  const participlesCard = document.getElementById('verb-participles-card');
  if (participlesCard) participlesCard.innerHTML = verbParticiplesInner(model);
  const formsCard = document.getElementById('verb-forms-card');
  if (formsCard) formsCard.innerHTML = verbFormsInner(model);
  markDirty();
  refreshUi();
}

function spanishPlural(word) {
  const lower = word.toLocaleLowerCase();
  if (lower.endsWith('z')) return `${word.slice(0, -1)}ces`;
  return /[aeiouáéíóúü]$/.test(lower) ? `${word}s` : `${word}es`;
}

function showEditorError(message) {
  if (state.editor) state.editor.error = message;
  const box = document.getElementById('editor-message');
  if (box) box.innerHTML = renderMessage();
}

function onModelChanged() {
  markDirty();
  refreshUi();
}

function markDirty() {
  if (!state.editor) return;
  state.editor.dirty = true;
  state.editor.error = '';
  const model = state.editor.model;
  const title = document.getElementById('editor-title');
  if (title) title.textContent = `${editorTitle(model)} *`;
  const status = document.getElementById('dirty-status');
  if (status) {
    status.textContent = 'Unsaved changes';
    status.className = 'unsaved';
  }
  const message = document.getElementById('editor-message');
  if (message) message.innerHTML = '';
}

function refreshUi() {
  const model = state.editor.model;
  const { valid, helperText, visibility } = EDITORS[model.lexical_item_type].deriveUi(model);
  for (const id of Object.keys(visibility)) {
    document.getElementById(id)?.classList.toggle('hidden', visibility[id]);
  }
  const helper = document.getElementById('helper-text');
  if (helper) {
    helper.textContent = helperText;
    helper.classList.toggle('hidden', !helperText);
  }
  const saveButton = document.getElementById('save-button');
  if (saveButton) saveButton.disabled = !valid;
}

function editorTitle(model) {
  const title = (model.headword || '').trim() || 'Untitled';
  const label = LEXICAL_ITEM_TYPE_LABELS[model.lexical_item_type] || model.lexical_item_type;
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

function collectPayload() {
  const model = state.editor.model;
  const lexicalItemType = model.lexical_item_type;
  const payload = {
    lexical_item_type: lexicalItemType,
    headword: model.headword.trim(),
    explanation: model.explanation.trim(),
  };
  if (!payload.headword) throw new Error('headword cannot be empty');
  if (!payload.explanation) throw new Error('explanation cannot be empty');
  Object.assign(payload, EDITORS[lexicalItemType].collect(model));
  return payload;
}

async function saveEditor() {
  try {
    state.editor.error = '';
    const payload = collectPayload();
    const isNew = state.editor.isNew;
    const path = isNew ? '/api/lexical-items' : `/api/lexical-items/${state.editor.model.id}`;
    const method = isNew ? 'POST' : 'PUT';
    const data = await api(path, { method, body: JSON.stringify(payload) });
    state.selectedType = data.lexical_item.lexical_item_type;
    state.query = '';
    state.results = [];
    state.searching = false;
    clearTimeout(state.searchTimer);
    renderHome();
  } catch (error) {
    state.editor.error = error.message;
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

function cssEscape(value) {
  if (window.CSS?.escape) return CSS.escape(value);
  return String(value).replace(/[^a-zA-Z0-9_-]/g, '\\$&');
}

init();
