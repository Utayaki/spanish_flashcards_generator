'use strict';

import { api } from './api.js';
import { app, state } from './state.js';
import { esc } from './utils.js';
import { makeDraftLexicalItem } from './models.js';

let startEditor = null;

export function configureHome(startEditorCallback) {
  startEditor = startEditorCallback;
}

function resetSearchExpansion() {
  state.hasMoreResults = false;
  state.searchExpanded = false;
  state.loadingAll = false;
}

function searchUrl(type, query, { all = false } = {}) {
  const params = new URLSearchParams({
    lexical_item_type: type,
    q: query,
  });
  if (all) params.set('all', '1');
  return `/api/search?${params.toString()}`;
}

function debounceSearch() {
  clearTimeout(state.searchTimer);
  state.searchTimer = setTimeout(() => runSearch(), 140);
}

export function renderHome() {
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
      resetSearchExpansion();
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
  resetSearchExpansion();
  clearTimeout(state.searchTimer);
  renderHome();
}

async function runSearch({ all = false } = {}) {
  const type = state.selectedType;
  const query = state.query.trim();
  if (!type || !query) return;
  if (all) {
    state.loadingAll = true;
  } else {
    state.searching = true;
    state.searchExpanded = false;
  }
  renderSearchResults();
  try {
    const data = await api(searchUrl(type, query, { all }));
    if (state.selectedType === type && state.query.trim() === query) {
      state.results = data.results;
      state.hasMoreResults = Boolean(data.has_more);
      if (all) {
        state.searchExpanded = true;
        state.hasMoreResults = false;
        state.loadingAll = false;
      } else {
        state.searching = false;
      }
      renderSearchResults();
      updateCreateButton();
    }
  } catch (error) {
    state.searching = false;
    state.loadingAll = false;
    const results = document.getElementById('search-results');
    if (results) results.innerHTML = `<div class="error-box">${esc(error.message)}</div>`;
  }
}

async function loadAllResults() {
  if (!state.hasMoreResults || state.searchExpanded || state.loadingAll) return;
  await runSearch({ all: true });
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
  if (state.loadingAll) {
    box.innerHTML = '<p class="muted">Loading…</p>';
    return;
  }
  if (!state.results.length) {
    box.innerHTML = '<p class="muted">None</p>';
    return;
  }
  const loadAllButton = state.hasMoreResults && !state.searchExpanded
    ? '<button type="button" id="load-all-button" class="ghost load-all-button">Load all</button>'
    : '';
  box.innerHTML = `${state.results.map(result => `
    <div class="search-result" data-lexical-item-id="${Number(result.id)}">
      <div class="search-result-main" tabindex="0" role="button">
        <strong>${highlightMatch(result.headword, state.query)}</strong>
        ${result.explanation ? `<span class="muted">${highlightMatch(result.explanation, state.query)}</span>` : ''}
      </div>
      <button type="button" class="danger" data-delete-id="${Number(result.id)}">Delete</button>
    </div>`).join('')}${loadAllButton}`;

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
  document.getElementById('load-all-button')?.addEventListener('click', loadAllResults);
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
    if (state.query.trim()) {
      if (state.searchExpanded) {
        runSearch({ all: true });
      } else {
        runSearch();
      }
    }
  } catch (error) {
    showHomeError(error.message);
  }
}

function showHomeError(message) {
  const box = document.getElementById('search-results');
  if (box) box.innerHTML = `<div class="error-box">${esc(message)}</div>`;
}
