'use strict';

import { state } from './state.js';
import { esc } from './utils.js';
import {
  findVerbDefinition,
  isGenderEnabled,
  nounVisibleGenders,
} from './models.js';

export function commonBaseCard(model, isNew, extraRows = '') {
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

export function genderRow(model) {
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

export function adjectiveTypeRow(model) {
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

export function otherTypeRow(model) {
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

export function nounGridCardInner(model) {
  return `<h2>Inflections</h2>${renderAutoFillButton()}${renderGenderNullableGrid(model)}`;
}

export function pluralityCardInner(title, model, includeAutoFill) {
  return `<h2>${esc(title)}</h2>${includeAutoFill ? renderAutoFillButton() : ''}${renderPluralityGrid(model)}`;
}

export function genderRequiredCardInner(title, model, includeAutoFill) {
  return `<h2>${esc(title)}</h2>${includeAutoFill ? renderAutoFillButton() : ''}${renderGenderRequiredGrid(model)}`;
}

export function verbParticiplesInner(model) {
  return `<h2>Participles</h2>${state.meta.verb_participles.map(part => {
    const cell = model.verb[part.code];
    return `<div class="form-row"><label>${esc(part.label)}</label>${verbCellHtml({ code: part.code, cell })}</div>`;
  }).join('')}`;
}

export function verbFormsInner(model) {
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
