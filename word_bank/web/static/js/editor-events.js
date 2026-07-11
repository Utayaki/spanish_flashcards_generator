'use strict';

import { state } from './state.js';
import { cssEscape } from './utils.js';
import {
  defaultInflectionForms,
  defaultNounForms,
  findVerbDefinition,
  isGenderEnabled,
} from './models.js';
import {
  genderRequiredCardInner,
  nounGridCardInner,
  pluralityCardInner,
  verbFormsInner,
  verbParticiplesInner,
} from './views.js';
import {
  markDirty,
  onModelChanged,
  refreshUi,
  showEditorError,
} from './editor-status.js';

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

export function onFormKeydown(event) {
  if (event.key !== 'Enter') return;
  const target = event.target;
  if (!isNavigableCellInput(target)) return;
  const cellEl = target.closest('[data-cell]');
  if (!cellEl) return;
  event.preventDefault();
  focusNextCellInput(cellEl);
}

export function onFormEvent(event) {
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

export function onFormClick(event) {
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

export function setActiveVerbGroup(code) {
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
