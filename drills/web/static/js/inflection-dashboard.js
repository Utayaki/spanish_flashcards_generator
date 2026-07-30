'use strict';

import { renderCollectionTitle, wireCollectionRename } from './collection-display.js';
import {
  esc,
  number,
  renderForecastChart,
  renderMemoryGrowthChart,
  renderRangeToggle,
  renderStats,
} from './fsrs-dashboard-charts.js';

export function renderInflectionDashboard(app, state) {
  const collection = state.collections.find(item => item.id === state.collectionId) ?? null;
  const fsrsStats = state.inflectionFsrsStats;
  const analytics = state.inflectionFsrsAnalytics;
  const canStartDrill = (number(fsrsStats?.due) + number(fsrsStats?.new)) > 0;

  const errorHtml = state.error
    ? `<div class="error-box" role="alert">${esc(state.error)}</div>`
    : '';

  const wordFormMeta = collection
    ? `<p class="collection-meta">${esc(collection.inflection_drill_count ?? '—')} word forms</p>`
    : '';

  const chartLoading = state.loading || state.inflectionAnalyticsLoading;
  const chartsHtml = analytics && !state.inflectionAnalyticsLoading
    ? `
      <div class="charts-grid">
        <section class="chart-block">${renderMemoryGrowthChart(analytics.memory_growth, 'Inflection')}</section>
        <section class="chart-block">${renderForecastChart(analytics.forecast, 'Inflection')}</section>
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
          ${wordFormMeta}
        </div>
      </div>
      ${errorHtml}
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
            ${!canStartDrill || state.loading ? 'disabled' : ''}
          >Start Drills</button>
        </div>
      </section>
    </section>
  `;

  document.getElementById('back-home-button')?.addEventListener('click', state.onBackHome);
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
}
