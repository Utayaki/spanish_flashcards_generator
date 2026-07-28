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

function formatCount(value) {
  const count = Number(value);
  return Number.isFinite(count) ? count.toLocaleString() : '0';
}

function renderProgressPanel(label, completed, total, percent) {
  return `
    <div class="progress-panel progress-panel-secondary" aria-live="polite">
      <div class="progress-label">${label}</div>
      <div class="progress-bar" role="progressbar" aria-valuemin="0" aria-valuemax="${esc(total)}" aria-valuenow="${esc(completed)}">
        <div class="progress-bar-fill" style="width: ${esc(percent)}%"></div>
      </div>
    </div>
  `;
}

function renderWordProgressBar(progress) {
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
      <div class="progress-label">Word forms ${esc(completed)} / ${esc(total)}${current}${esc(eta)}</div>
      <div class="progress-bar" role="progressbar" aria-valuemin="0" aria-valuemax="${esc(total)}" aria-valuenow="${esc(completed)}">
        <div class="progress-bar-fill" style="width: ${esc(percent)}%"></div>
      </div>
    </div>
  `;
}

function shouldPreserveGenerationUI(progress, generating) {
  return generating || Boolean(progress?.error) || Boolean(progress?.stopped);
}

function renderParquetProgressBar(progress) {
  if (!progress?.corpus_file_total) {
    return '';
  }
  const fileIndex = Number(progress.corpus_file_index) || 0;
  const fileTotal = Number(progress.corpus_file_total) || 0;
  const percent = fileTotal > 0 ? Math.min(100, Math.round((fileIndex / fileTotal) * 100)) : 0;
  const fileName = progress.corpus_file_name ? ` — ${esc(progress.corpus_file_name)}` : '';
  const label = progress.indexing_corpus
    ? `Indexing Parquet ${esc(fileIndex)} / ${esc(fileTotal)}${fileName}`
    : `Parquet ${esc(fileIndex)} / ${esc(fileTotal)}${fileName}`;
  return renderProgressPanel(label, fileIndex, fileTotal, percent);
}

function renderEntryProgressBar(progress) {
  if (!progress?.corpus_entry_total) {
    return '';
  }
  const processed = Number(progress.corpus_entry_processed) || 0;
  const total = Number(progress.corpus_entry_total) || 0;
  const percent = total > 0 ? Math.min(100, Math.round((processed / total) * 100)) : 0;
  const label = `Entries ${esc(formatCount(processed))} / ${esc(formatCount(total))}`;
  return renderProgressPanel(label, processed, total, percent);
}

function createDrillsLabel(status, generating, creating) {
  if (generating || creating) {
    return 'Creating drills…';
  }
  if (status?.pending_word_form_count > 0) {
    return 'Generate Drills';
  }
  return 'Create Drills';
}

function searchLogFallback(progress) {
  if (progress?.indexing_corpus) {
    return 'Indexing corpus files…';
  }
  return 'Searching corpus…';
}

function renderSearchLog(progress, showGenerationUI) {
  if (!showGenerationUI && !progress?.search_log) {
    return '';
  }
  const wordForm = progress?.current_word_form ? esc(progress.current_word_form) : '…';
  const logText = progress?.search_log ? esc(progress.search_log) : '';
  const bodyText = logText || esc(searchLogFallback(progress));
  return `
    <div class="search-log-panel">
      <div class="search-log-header">Found sentences — ${wordForm}</div>
      <pre class="search-log" id="search-log">${bodyText}</pre>
    </div>
  `;
}

function scrollSearchLogToBottom() {
  const log = document.getElementById('search-log');
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
      statusParts.push(`${esc(pendingCount)} forms need examples`);
    }
    if (status.is_complete) {
      statusParts.push('generation complete');
    }
  }
  const generationMetaHtml = status
    ? `<p class="collection-meta">${statusParts.join(' · ')}</p>`
    : '';

  const showGenerationUI = shouldPreserveGenerationUI(progress, generating);
  const wordProgressHtml = showGenerationUI ? renderWordProgressBar(progress) : '';
  const parquetProgressHtml = showGenerationUI ? renderParquetProgressBar(progress) : '';
  const entryProgressHtml = showGenerationUI ? renderEntryProgressBar(progress) : '';
  const searchLogHtml = renderSearchLog(progress, showGenerationUI);
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
        <p class="collection-meta">Generate up to 20 cloze examples per word form (at least 5, one-time).</p>
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
        ${wordProgressHtml}
        ${parquetProgressHtml}
        ${entryProgressHtml}
        ${searchLogHtml}
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
  if (showGenerationUI || progress?.search_log) {
    scrollSearchLogToBottom();
  }
}
