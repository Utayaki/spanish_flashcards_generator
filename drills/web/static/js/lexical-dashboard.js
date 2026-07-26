'use strict';

function esc(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function statBlock(label, value) {
  return `
    <div class="stat-block">
      <span class="stat-value">${esc(value)}</span>
      <span class="stat-label">${esc(label)}</span>
    </div>
  `;
}

function renderStatsPanel(title, stats, loading) {
  const statsHtml = stats
    ? `
      <div class="stats-grid">
        ${statBlock('Total', stats.total)}
        ${statBlock('New', stats.new)}
        ${statBlock('Due', stats.due)}
        ${statBlock('Future', stats.future)}
      </div>
    `
    : `<p class="collection-meta">${loading ? 'Loading stats…' : 'No stats available'}</p>`;

  return `
    <div class="dashboard-panel">
      <h2>${esc(title)}</h2>
      ${statsHtml}
    </div>
  `;
}

export function renderLexicalDashboard(app, state) {
  const collection = state.collections.find(item => item.id === state.collectionId);
  const collectionName = collection?.name ?? `Collection ${state.collectionId}`;
  const lexicalMeta = collection
    ? `<p class="collection-meta">${esc(collection.item_count)} lexical items · ${esc(collection.spanish_to_english_card_count ?? '—')} ES→EN · ${esc(collection.english_to_spanish_card_count ?? '—')} EN→ES cards</p>`
    : '';
  const errorHtml = state.error
    ? `<div class="error-box" role="alert">${esc(state.error)}</div>`
    : '';

  app.innerHTML = `
    <section class="panel">
      <div class="header-row">
        <div>
          <p class="eyebrow">Lexical items</p>
          <h1>${esc(collectionName)}</h1>
          ${lexicalMeta}
        </div>
        <button type="button" id="back-home-button">Back</button>
      </div>
      ${errorHtml}
      ${renderStatsPanel('Spanish to English', state.fsrsStatsS2E, state.loading)}
      <div class="action-row dashboard-actions">
        <button
          type="button"
          class="primary learn-direction-button"
          data-direction="spanish_to_english"
          ${state.loading ? 'disabled' : ''}
        >Learn Spanish to English</button>
      </div>
      ${renderStatsPanel('English to Spanish', state.fsrsStatsE2S, state.loading)}
      <div class="action-row dashboard-actions">
        <button
          type="button"
          class="primary learn-direction-button"
          data-direction="english_to_spanish"
          ${state.loading ? 'disabled' : ''}
        >Learn English to Spanish</button>
      </div>
    </section>
  `;

  document.getElementById('back-home-button')?.addEventListener('click', state.onBackHome);
  document.querySelectorAll('.learn-direction-button').forEach(button => {
    button.addEventListener('click', () => {
      const direction = button.dataset.direction;
      if (direction) {
        state.onStartFsrsDrill(direction);
      }
    });
  });
}
