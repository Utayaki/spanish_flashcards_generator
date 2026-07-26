'use strict';

import { renderCollectionTitle, wireCollectionRename } from './collection-display.js';
import {
  computeChartScales,
  esc,
  number,
  renderForecastChart,
  renderMemoryGrowthChart,
  renderRangeToggle,
  renderStats,
} from './fsrs-dashboard-charts.js';

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
  if (status?.pending_word_form_count > 0) {
    return 'Continue Drills';
  }
  return 'Create Drills';
}

function renderOllamaStream(progress) {
  if (!progress?.generating && !progress?.ollama_stream) {
    return '';
  }
  const wordForm = progress?.current_word_form ? esc(progress.current_word_form) : '…';
  const streamText = progress?.ollama_stream ? esc(progress.ollama_stream) : '';
  return `
    <div class="ollama-stream-panel">
      <div class="ollama-stream-header">Ollama output — ${wordForm}</div>
      <pre class="ollama-stream-log" id="ollama-stream-log">${streamText || 'Waiting for output…'}</pre>
    </div>
  `;
}

function scrollOllamaStreamToBottom() {
  const log = document.getElementById('ollama-stream-log');
  if (log) {
    log.scrollTop = log.scrollHeight;
  }
}

export function renderInflectionDashboard(app, state) {
  const collection = state.collections.find(item => item.id === state.collectionId) ?? null;
  const status = state.inflectionStatus;
  const fsrsStats = state.inflectionFsrsStats;
  const analytics = state.inflectionFsrsAnalytics;
  const progress = state.inflectionProgress;
  const generating = Boolean(state.inflectionGenerating || progress?.generating);
  const hasInflectionData = status?.has_inflection_data !== false;
  const createLabel = createDrillsLabel(status, generating, state.creatingInflectionDrills);
  const canStartDrill = (number(fsrsStats?.due) + number(fsrsStats?.new)) > 0;

  const errorHtml = state.error
    ? `<div class="error-box" role="alert">${esc(state.error)}</div>`
    : '';

  const missingDataHtml = !hasInflectionData
    ? `<div class="error-box" role="alert">This collection was created before inflection data was supported. Recreate the collection to use inflection drills.</div>`
    : '';

  const pendingCount = status?.pending_word_form_count ?? 0;
  const statusParts = [];
  if (status) {
    statusParts.push(`${esc(status.word_form_count)} complete forms`);
    statusParts.push(`${esc(status.example_count)} examples`);
    if (pendingCount > 0) {
      statusParts.push(`${esc(pendingCount)} below 5 examples`);
    }
    if (status.is_complete) {
      statusParts.push('generation complete');
    }
  }
  const generationMetaHtml = status
    ? `<p class="collection-meta">${statusParts.join(' · ')}</p>`
    : '';

  const progressHtml = generating ? renderProgressBar(progress) : '';
  const ollamaStreamHtml = renderOllamaStream(progress);
  const scales = computeChartScales(analytics);
  const chartLoading = state.loading || state.inflectionAnalyticsLoading;
  const chartsHtml = analytics && !state.inflectionAnalyticsLoading
    ? `
      <div class="charts-grid">
        <section class="chart-block">${renderMemoryGrowthChart(analytics.memory_growth, 'Inflection', scales.memory)}</section>
        <section class="chart-block">${renderForecastChart(analytics.forecast, 'Inflection', scales.forecast)}</section>
      </div>
    `
    : `<p class="collection-meta chart-loading">${chartLoading ? 'Loading progress and forecast…' : 'No chart data available'}</p>`;

  app.innerHTML = `
    <section class="panel dashboard-panel">
      <div class="header-row">
        <div>
          <button id="back-home-button" type="button">Back</button>
          ${collection ? renderCollectionTitle(collection, state) : '<h1>Inflection Drills</h1>'}
          <p class="eyebrow">Word form FSRS</p>
          ${generationMetaHtml}
        </div>
      </div>
      ${errorHtml}
      ${missingDataHtml}
      <section class="dashboard-panel direction-panel">
        <h2>Review schedule</h2>
        ${renderStats(fsrsStats, state.loading)}
        ${renderRangeToggle(state.inflectionDashboardRangeDays, state.inflectionAnalyticsLoading)}
        ${chartsHtml}
        <div class="action-row dashboard-actions">
          <button
            id="start-inflection-drill-button"
            class="primary"
            type="button"
            ${!canStartDrill || generating ? 'disabled' : ''}
          >Start Drills</button>
        </div>
      </section>
      <section class="dashboard-panel direction-panel">
        <h2>Example generation</h2>
        <p class="collection-meta">Regenerate cloze examples when a form has fewer than 5 (fills back to 15).</p>
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
        </div>
        ${progressHtml}
        ${ollamaStreamHtml}
      </section>
    </section>
  `;

  document.getElementById('back-home-button')?.addEventListener('click', state.onBackHome);
  document.getElementById('create-inflection-drills-button')?.addEventListener('click', state.onCreateInflectionDrills);
  document.getElementById('stop-inflection-drills-button')?.addEventListener('click', state.onStopInflectionDrills);
  document.getElementById('start-inflection-drill-button')?.addEventListener('click', state.onStartInflectionDrill);
  document.querySelectorAll('.range-toggle-button').forEach(button => {
    button.addEventListener('click', () => {
      const rangeDays = Number(button.dataset.rangeDays);
      if (Number.isFinite(rangeDays)) {
        state.onSetInflectionDashboardRangeDays(rangeDays);
      }
    });
  });
  wireCollectionRename(state);
  if (generating || progress?.ollama_stream) {
    scrollOllamaStreamToBottom();
  }
}
