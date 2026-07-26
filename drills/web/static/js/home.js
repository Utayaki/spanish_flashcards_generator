'use strict';

function esc(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function formatCollectionDate(createdAt) {
  const date = new Date(createdAt);
  if (Number.isNaN(date.getTime())) {
    return createdAt;
  }
  return date.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

export function renderHome(app, state) {
  const errorHtml = state.error
    ? `<div class="error-box" role="alert">${esc(state.error)}</div>`
    : '';

  const collectionsHtml = state.collections.length
    ? state.collections.map(collection => `
        <div class="collection-row">
          <div class="collection-main">
            <span class="collection-name">${esc(collection.name)}</span>
            <span class="collection-meta">${esc(formatCollectionDate(collection.created_at))}</span>
            <span class="collection-count">${esc(collection.item_count)} lexical items</span>
          </div>
          <button
            type="button"
            class="start-drill-button"
            data-collection-id="${esc(collection.id)}"
          >Start drilling</button>
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
  document.querySelectorAll('.start-drill-button').forEach(button => {
    button.addEventListener('click', () => {
      alert('Drill sessions are not implemented yet.');
    });
  });
}
