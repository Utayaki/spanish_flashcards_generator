'use strict';

import { renderCollectionTitle } from './collection-display.js';

function esc(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

export function renderInflectionDrill(app, state) {
  const collection = state.collections.find(item => item.id === state.collectionId) ?? null;

  app.innerHTML = `
    <section class="panel">
      <div class="header-row">
        <div>
          <button id="back-inflection-dashboard-button" type="button">Back to dashboard</button>
          ${collection ? renderCollectionTitle(collection, state) : '<h1>Inflection Drills</h1>'}
        </div>
      </div>
      <p class="collection-meta">Inflection drill session coming soon.</p>
    </section>
  `;

  document.getElementById('back-inflection-dashboard-button')?.addEventListener('click', state.onBackInflectionDashboard);
}
