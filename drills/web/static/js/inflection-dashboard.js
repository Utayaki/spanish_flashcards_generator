'use strict';

import { renderCollectionTitle, wireCollectionRename } from './collection-display.js';

function esc(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function formatEta(progress) {
  if (progress?.eta_seconds == null) {
    return '';
  }
  const seconds = Number(progress.eta_seconds);
  if (!Number.isFinite(seconds) || seconds <= 0) {
    return '';
  }
  if (seconds < 60) {
    return ` · ~${seconds}s left`;
  }
  const minutes = Math.max(1, Math.round(seconds / 60));
  return ` · ~${minutes} min left`;
}

function renderProgressBar(progress) {
  if (!progress || !progress.total) {
    return '';
  }
  const completed = Number(progress.completed) || 0;
  const total = Number(progress.total) || 0;
  const percent = total > 0 ? Math.min(100, Math.round((completed / total) * 100)) : 0;
  const current = progress.current_word_form ? ` — ${esc(progress.current_word_form)}` : '';
  const eta = formatEta(progress);
  return `
    <div class="progress-panel" aria-live="polite">
      <div class="progress-label">Generating ${esc(completed)} / ${esc(total)}${current}${esc(eta)}</div>
      <div class="progress-bar" role="progressbar" aria-valuemin="0" aria-valuemax="${esc(total)}" aria-valuenow="${esc(completed)}">
        <div class="progress-bar-fill" style="width: ${esc(percent)}%"></div>
      </div>
    </div>
  `;
}

function createDrillsLabel(status, generating, creating) {
  if (generating || creating) {
    return 'Creating drills…';
  }
  if (status?.example_count > 0 && status?.pending_word_form_count > 0) {
    return 'Continue Drills';
  }
  return 'Create Drills';
}

export function renderInflectionDashboard(app, state) {
  const collection = state.collections.find(item => item.id === state.collectionId) ?? null;
  const status = state.inflectionStatus;
  const progress = state.inflectionProgress;
  const generating = Boolean(state.inflectionGenerating || progress?.generating);
  const hasDrills = Boolean(status?.has_drills);
  const hasInflectionData = status?.has_inflection_data !== false;
  const createLabel = createDrillsLabel(status, generating, state.creatingInflectionDrills);

  const errorHtml = state.error
    ? `<div class="error-box" role="alert">${esc(state.error)}</div>`
    : '';

  const missingDataHtml = !hasInflectionData
    ? `<div class="error-box" role="alert">This collection was created before inflection data was supported. Recreate the collection to use inflection drills.</div>`
    : '';

  const alreadyGenerated = status?.word_form_count ?? 0;
  const pendingCount = status?.pending_word_form_count ?? 0;
  const statusParts = [];
  if (status) {
    statusParts.push(`${esc(status.word_form_count)} complete forms`);
    statusParts.push(`${esc(status.example_count)} examples`);
    if (pendingCount > 0) {
      statusParts.push(`${esc(pendingCount)} pending`);
    }
    if (status.is_complete) {
      statusParts.push('generation complete');
    }
  }
  const statusHtml = status
    ? `<p class="collection-meta">${statusParts.join(' · ')}</p>`
    : `<p class="collection-meta">${state.loading ? 'Loading status…' : 'No status available'}</p>`;

  const progressHtml = generating ? renderProgressBar(progress) : '';
  const alreadyGeneratedHtml = generating && progress?.already_generated > 0
    ? `<p class="collection-meta">${esc(progress.already_generated)} forms already generated (skipped)</p>`
    : (!generating && alreadyGenerated > 0 && pendingCount > 0
      ? `<p class="collection-meta">${esc(alreadyGenerated)} forms already generated</p>`
      : '');

  app.innerHTML = `
    <section class="panel dashboard-panel">
      <div class="header-row">
        <div>
          <button id="back-home-button" type="button">Back</button>
          ${collection ? renderCollectionTitle(collection, state) : '<h1>Inflection Drills</h1>'}
          ${statusHtml}
          ${alreadyGeneratedHtml}
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
        >${esc(createLabel)}</button>
        <button
          id="stop-inflection-drills-button"
          type="button"
          ${generating ? '' : 'hidden'}
        >Stop</button>
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
  document.getElementById('stop-inflection-drills-button')?.addEventListener('click', state.onStopInflectionDrills);
  document.getElementById('start-inflection-drill-button')?.addEventListener('click', state.onStartInflectionDrill);
  wireCollectionRename(state);
}
