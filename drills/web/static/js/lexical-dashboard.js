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

export function renderLexicalDashboard(app, state) {
  const collection = state.collections.find(item => item.id === state.collectionId);
  const collectionName = collection?.name ?? `Collection ${state.collectionId}`;
  const errorHtml = state.error
    ? `<div class="error-box" role="alert">${esc(state.error)}</div>`
    : '';
  const stats = state.fsrsStats;

  const statsHtml = stats
    ? `
      <div class="stats-grid">
        ${statBlock('Total', stats.total)}
        ${statBlock('New', stats.new)}
        ${statBlock('Due', stats.due)}
        ${statBlock('Future', stats.future)}
      </div>
    `
    : '<p class="collection-meta">Loading stats…</p>';

  app.innerHTML = `
    <section class="panel">
      <div class="header-row">
        <div>
          <p class="eyebrow">Lexical items</p>
          <h1>${esc(collectionName)}</h1>
        </div>
        <button type="button" id="back-home-button">Back</button>
      </div>
      ${errorHtml}
      <div class="dashboard-panel">
        <h2>FSRS overview</h2>
        ${statsHtml}
      </div>
      <div class="action-row dashboard-actions">
        <button type="button" id="learn-fsrs-button" class="primary" ${state.loading ? 'disabled' : ''}>
          Learn FSRS
        </button>
      </div>
    </section>
  `;

  document.getElementById('back-home-button')?.addEventListener('click', state.onBackHome);
  document.getElementById('learn-fsrs-button')?.addEventListener('click', state.onStartFsrsDrill);
}
