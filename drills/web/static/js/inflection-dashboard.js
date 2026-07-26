'use strict';

import { renderCollectionTitle, wireCollectionRename } from './collection-display.js';

function esc(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function renderProgressBar(progress) {
  if (!progress || !progress.total) {
    return '';
  }
  const completed = Number(progress.completed) || 0;
  const total = Number(progress.total) || 0;
  const percent = total > 0 ? Math.min(100, Math.round((completed / total) * 100)) : 0;
  const current = progress.current_word_form ? ` — ${esc(progress.current_word_form)}` : '';
  return `
    <div class="progress-panel" aria-live="polite">
      <div class="progress-label">Generating ${esc(completed)} / ${esc(total)}${current}</div>
      <div class="progress-bar" role="progressbar" aria-valuemin="0" aria-valuemax="${esc(total)}" aria-valuenow="${esc(completed)}">
        <div class="progress-bar-fill" style="width: ${esc(percent)}%"></div>
      </div>
    </div>
  `;
}

export function renderInflectionDashboard(app, state) {
  const collection = state.collections.find(item => item.id === state.collectionId) ?? null;
  const status = state.inflectionStatus;
  const progress = state.inflectionProgress;
  const generating = Boolean(state.inflectionGenerating || progress?.generating);
  const hasDrills = Boolean(status?.has_drills);
  const hasInflectionData = status?.has_inflection_data !== false;

  const errorHtml = state.error
    ? `<div class="error-box" role="alert">${esc(state.error)}</div>`
    : '';

  const missingDataHtml = !hasInflectionData
    ? `<div class="error-box" role="alert">This collection was created before inflection data was supported. Recreate the collection to use inflection drills.</div>`
    : '';

  const statusHtml = status
    ? `<p class="collection-meta">${esc(status.word_form_count)} word forms · ${esc(status.example_count)} examples${status.generated_at ? ` · generated ${esc(status.generated_at)}` : ''}</p>`
    : `<p class="collection-meta">${state.loading ? 'Loading status…' : 'No status available'}</p>`;

  const progressHtml = generating ? renderProgressBar(progress) : '';

  app.innerHTML = `
    <section class="panel dashboard-panel">
      <div class="header-row">
        <div>
          <button id="back-home-button" type="button">Back</button>
          ${collection ? renderCollectionTitle(collection, state) : '<h1>Inflection Drills</h1>'}
          ${statusHtml}
        </div>
      </div>
      ${errorHtml}
      ${missingDataHtml}
      <div class="dashboard-actions">
        <button
          id="create-inflection-drills-button"
          class="primary"
          type="button"
          ${generating || !hasInflectionData || state.creatingInflectionDrills ? 'disabled' : ''}
        >${generating || state.creatingInflectionDrills ? 'Creating drills…' : 'Create Drills'}</button>
        <button
          id="start-inflection-drill-button"
          class="primary"
          type="button"
          ${!hasDrills || generating ? 'disabled' : ''}
        >Start Drills</button>
      </div>
      ${progressHtml}
    </section>
  `;

  document.getElementById('back-home-button')?.addEventListener('click', state.onBackHome);
  document.getElementById('create-inflection-drills-button')?.addEventListener('click', state.onCreateInflectionDrills);
  document.getElementById('start-inflection-drill-button')?.addEventListener('click', state.onStartInflectionDrill);
  wireCollectionRename(state);
}
