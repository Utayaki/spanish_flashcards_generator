'use strict';

import { renderCollectionTitle, wireCollectionRename } from './collection-display.js';

function esc(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

export function renderHome(app, state) {
  const errorHtml = state.error
    ? `<div class="error-box" role="alert">${esc(state.error)}</div>`
    : '';

  const collectionsHtml = state.collections.length
    ? state.collections.map(collection => `
        <div class="collection-row">
          <div class="collection-main">
            ${renderCollectionTitle(collection, state)}
            <span class="collection-meta">${esc(collection.subtitle ?? '')}</span>
            <span class="collection-count">${esc(collection.item_count)} lexical items · ${esc(collection.english_to_spanish_card_count ?? '—')} EN→ES · ${esc(collection.noun_gender_card_count ?? '—')} noun gender · ${esc(collection.adjective_inflection_type_card_count ?? '—')} adj inflection · ${esc(collection.spanish_to_english_card_count ?? '—')} ES→EN cards</span>
          </div>
          <div class="collection-actions">
            <button
              type="button"
              class="primary learn-lexical-button"
              data-collection-id="${esc(collection.id)}"
            >Learn Lexical Items</button>
            <button
              type="button"
              class="inflection-drill-button"
              data-collection-id="${esc(collection.id)}"
            >Start inflection drills</button>
          </div>
        </div>
      `).join('')
    : '<p class="collection-meta">No collections yet. Create one from the current word bank.</p>';

  app.innerHTML = `
    <section class="panel">
      <div class="header-row">
        <h1>Spanish Drills</h1>
      </div>
      ${errorHtml}
      <div class="action-row">
        <button id="create-collection-button" class="primary" type="button" ${state.creating ? 'disabled' : ''}>
          ${state.creating ? 'Creating…' : 'Create drill collection'}
        </button>
      </div>
      <div class="collection-list" id="collection-list">
        ${collectionsHtml}
      </div>
    </section>
  `;

  document.getElementById('create-collection-button')?.addEventListener('click', state.onCreateCollection);
  document.querySelectorAll('.learn-lexical-button').forEach(button => {
    button.addEventListener('click', () => {
      const collectionId = Number(button.dataset.collectionId);
      state.onOpenLexicalDashboard(collectionId);
    });
  });
  document.querySelectorAll('.inflection-drill-button').forEach(button => {
    button.addEventListener('click', () => {
      const collectionId = Number(button.dataset.collectionId);
      state.onOpenInflectionDashboard(collectionId);
    });
  });
  wireCollectionRename(state);
}
