'use strict';

export const DASHBOARD_RANGE_OPTIONS = [
  { days: 7, label: '7 days' },
  { days: 30, label: '30 days' },
  { days: 180, label: '6 months' },
];

export function esc(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

export function number(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

export function formatDate(value) {
  const date = new Date(`${value}T00:00:00`);
  return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric' }).format(date);
}

export function renderRangeToggle(selectedDays, analyticsLoading) {
  const buttons = DASHBOARD_RANGE_OPTIONS.map(option => {
    const isActive = option.days === selectedDays;
    return `
      <button
        type="button"
        class="range-toggle-button${isActive ? ' is-active' : ''}"
        data-range-days="${option.days}"
        aria-pressed="${isActive ? 'true' : 'false'}"
        ${analyticsLoading ? 'disabled' : ''}
      >${esc(option.label)}</button>
    `;
  }).join('');

  return `
    <div class="range-toggle" role="group" aria-label="Dashboard time range">
      ${buttons}
    </div>
  `;
}

export function renderStats(stats, loading) {
  if (!stats) {
    return `<p class="collection-meta">${loading ? 'Loading stats…' : 'No stats available'}</p>`;
  }
  return `
    <div class="stats-grid">
      <div class="stat-block"><span class="stat-value">${esc(stats.total)}</span><span class="stat-label">Total</span></div>
      <div class="stat-block"><span class="stat-value">${esc(stats.new)}</span><span class="stat-label">New</span></div>
      <div class="stat-block"><span class="stat-value">${esc(stats.due)}</span><span class="stat-label">Due</span></div>
      <div class="stat-block"><span class="stat-value">${esc(stats.future)}</span><span class="stat-label">Future</span></div>
    </div>
  `;
}

function areaPath(points, x, y, lower, upper) {
  if (!points.length) {
    return '';
  }
  const top = points.map((point, index) => `${index ? 'L' : 'M'} ${x(index)} ${y(upper(point))}`).join(' ');
  const bottom = [...points]
    .reverse()
    .map((point, reverseIndex) => {
      const index = points.length - reverseIndex - 1;
      return `L ${x(index)} ${y(lower(point))}`;
    })
    .join(' ');
  return `${top} ${bottom} Z`;
}

export function renderMemoryGrowthChart(data, directionLabel, sharedMaximum) {
  const points = Array.isArray(data?.points) ? data.points : [];
  if (!points.length) {
    return '<p class="collection-meta">No progress history available.</p>';
  }

  const width = 560;
  const height = 220;
  const left = 38;
  const right = 12;
  const top = 12;
  const bottom = 42;
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;
  const total = Math.max(0, number(data.total));
  const yMaximum = Math.max(1, total, number(sharedMaximum));
  const x = index => left + (points.length === 1 ? plotWidth / 2 : (index / (points.length - 1)) * plotWidth);
  const y = value => top + plotHeight - (number(value) / yMaximum) * plotHeight;

  const durable = point => number(point.durable);
  const developing = point => durable(point) + number(point.developing);
  const fragile = point => developing(point) + number(point.fragile);
  const all = () => total;
  const zero = () => 0;

  const yTicks = [0, Math.round(yMaximum / 2), yMaximum]
    .filter((value, index, values) => values.indexOf(value) === index);
  const grid = yTicks.map(value => `
    <line class="chart-grid-line" x1="${left}" x2="${width - right}" y1="${y(value)}" y2="${y(value)}"></line>
    <text class="chart-axis-label" x="${left - 7}" y="${y(value) + 4}" text-anchor="end">${value}</text>
  `).join('');

  const labelIndexes = [...new Set([0, Math.floor((points.length - 1) / 2), points.length - 1])];
  const xLabels = labelIndexes.map(index => `
    <text class="chart-axis-label" x="${x(index)}" y="${height - 12}" text-anchor="middle">${esc(formatDate(points[index].date))}</text>
  `).join('');

  const hitWidth = plotWidth / points.length;
  const hitAreas = points.map((point, index) => `
    <rect class="chart-hit-area" x="${left + index * hitWidth}" y="${top}" width="${hitWidth}" height="${plotHeight}">
      <title>${esc(`${formatDate(point.date)}\nDurable: ${point.durable}\nDeveloping: ${point.developing}\nFragile: ${point.fragile}\nNot introduced: ${point.not_introduced}`)}</title>
    </rect>
  `).join('');

  const latest = points[points.length - 1];
  const change = number(data.durable_change);
  const changeText = `${change > 0 ? '+' : ''}${change} durable over ${number(data.days)} days`;

  return `
    <div class="chart-heading-row">
      <div>
        <h3>Memory growth</h3>
        <p class="chart-subtitle">How forms move toward durable recall.</p>
      </div>
      <span class="chart-summary">${esc(changeText)}</span>
    </div>
    <svg class="dashboard-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(`${directionLabel} memory growth over ${data.days} days`)}">
      ${grid}
      <path class="chart-area chart-area-not-introduced" d="${areaPath(points, x, y, fragile, all)}"></path>
      <path class="chart-area chart-area-fragile" d="${areaPath(points, x, y, developing, fragile)}"></path>
      <path class="chart-area chart-area-developing" d="${areaPath(points, x, y, durable, developing)}"></path>
      <path class="chart-area chart-area-durable" d="${areaPath(points, x, y, zero, durable)}"></path>
      ${xLabels}
      ${hitAreas}
    </svg>
    <div class="chart-legend" aria-hidden="true">
      <span><i class="legend-swatch durable"></i>Durable ${esc(latest.durable)}</span>
      <span><i class="legend-swatch developing"></i>Developing ${esc(latest.developing)}</span>
      <span><i class="legend-swatch fragile"></i>Fragile ${esc(latest.fragile)}</span>
      <span><i class="legend-swatch not-introduced"></i>Not introduced ${esc(latest.not_introduced)}</span>
    </div>
    <p class="chart-note">Fragile: under 7 days stability · Durable: 30+ days.</p>
  `;
}

export function renderForecastChart(data, directionLabel, sharedMaximum) {
  const points = Array.isArray(data?.points) ? data.points : [];
  if (!points.length) {
    return '<p class="collection-meta">No forecast available.</p>';
  }

  const width = 560;
  const height = 220;
  const left = 38;
  const right = 12;
  const top = 12;
  const bottom = 42;
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;
  const pace = data.recent_daily_pace === null ? null : number(data.recent_daily_pace);
  const maximum = Math.max(1, pace ?? 0, number(sharedMaximum), ...points.map(point => number(point.reviews)));
  const yMax = Math.ceil(maximum);
  const y = value => top + plotHeight - (number(value) / yMax) * plotHeight;
  const slot = plotWidth / points.length;
  const barWidth = Math.max(5, slot * 0.58);
  const barX = index => left + index * slot + (slot - barWidth) / 2;

  const yTicks = [0, Math.round(yMax / 2), yMax]
    .filter((value, index, values) => values.indexOf(value) === index);
  const grid = yTicks.map(value => `
    <line class="chart-grid-line" x1="${left}" x2="${width - right}" y1="${y(value)}" y2="${y(value)}"></line>
    <text class="chart-axis-label" x="${left - 7}" y="${y(value) + 4}" text-anchor="end">${value}</text>
  `).join('');

  const bars = points.map((point, index) => {
    const value = number(point.reviews);
    const barHeight = Math.max(0, plotHeight - (y(value) - top));
    return `
      <rect class="chart-bar" x="${barX(index)}" y="${y(value)}" width="${barWidth}" height="${barHeight}" rx="3">
        <title>${esc(`${formatDate(point.date)}\n${value} scheduled review${value === 1 ? '' : 's'}`)}</title>
      </rect>
    `;
  }).join('');

  const labelIndexes = [...new Set([0, Math.floor((points.length - 1) / 2), points.length - 1])];
  const xLabels = labelIndexes.map(index => `
    <text class="chart-axis-label" x="${barX(index) + barWidth / 2}" y="${height - 12}" text-anchor="middle">${esc(formatDate(points[index].date))}</text>
  `).join('');

  const paceLine = pace && pace > 0
    ? `
      <line class="chart-pace-line" x1="${left}" x2="${width - right}" y1="${y(pace)}" y2="${y(pace)}"></line>
      <text class="chart-pace-label" x="${width - right}" y="${Math.max(top + 10, y(pace) - 5)}" text-anchor="end">recent pace ${pace}/day</text>
    `
    : '';

  const summaryParts = [`${number(data.scheduled_total)} scheduled`];
  if (number(data.overdue) > 0) {
    summaryParts.push(`${number(data.overdue)} overdue`);
  }

  return `
    <div class="chart-heading-row">
      <div>
        <h3>Upcoming reviews</h3>
        <p class="chart-subtitle">Scheduled workload for the next ${esc(data.days)} days.</p>
      </div>
      <span class="chart-summary">${esc(summaryParts.join(' · '))}</span>
    </div>
    <svg class="dashboard-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(`${directionLabel} scheduled reviews for the next ${data.days} days`)}">
      ${grid}
      ${bars}
      ${paceLine}
      ${xLabels}
    </svg>
    <p class="chart-note">New cards are not included in this forecast.</p>
  `;
}

export function computeChartScales(analytics) {
  if (!analytics) {
    return { memory: 1, forecast: 1 };
  }
  return {
    memory: Math.max(1, number(analytics.memory_growth?.total)),
    forecast: Math.max(
      1,
      number(analytics.forecast?.recent_daily_pace),
      ...(analytics.forecast?.points ?? []).map(point => number(point.reviews)),
    ),
  };
}
