'use strict';

const DIRECTION_SPANISH_TO_ENGLISH = 'spanish_to_english';

const DRILL_COPY = {
  spanish_to_english: {
    eyebrow: 'Spanish',
    prompt: 'What does this mean?',
    answerLabel: 'Meanings',
  },
  english_to_spanish: {
    eyebrow: 'English',
    prompt: 'What is the Spanish word?',
    answerLabel: 'Spanish',
  },
};

function esc(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function currentStats(state) {
  if (state.drillDirection === DIRECTION_SPANISH_TO_ENGLISH) {
    return state.fsrsStatsS2E;
  }
  return state.fsrsStatsE2S;
}

function renderDoneScreen(state) {
  const stats = currentStats(state);
  const statsHtml = stats
    ? `<p class="collection-meta">${esc(stats.due)} due · ${esc(stats.new)} new · ${esc(stats.total)} total</p>`
    : '';

  const optimizeMessage = state.optimizeMessage
    ? `<div class="info-box" role="status">${esc(state.optimizeMessage)}</div>`
    : '';

  return `
    <section class="panel drill-panel">
      <div class="header-row">
        <h1>All done</h1>
        <button type="button" id="back-dashboard-button">Back to dashboard</button>
      </div>
      <p>No more cards to review right now.</p>
      ${statsHtml}
      ${optimizeMessage}
      <div class="action-row rating-row">
        <button
          type="button"
          id="optimize-button"
          class="primary"
          ${state.optimizing ? 'disabled' : ''}
        >${state.optimizing ? 'Optimizing…' : 'Update optimizer'}</button>
      </div>
    </section>
  `;
}

function renderCardScreen(state) {
  const card = state.card;
  if (!card) {
    return '<section class="panel drill-panel"><p>Loading next card…</p></section>';
  }

  const copy = DRILL_COPY[state.drillDirection] ?? DRILL_COPY.spanish_to_english;
  const counts = card.counts;
  const countsHtml = counts
    ? `<p class="collection-meta">${esc(counts.due)} due · ${esc(counts.new)} new remaining</p>`
    : '';

  const answerHtml = state.revealed
    ? `<div class="answer-box"><strong>${esc(copy.answerLabel)}</strong><p class="answer-text">${esc(card.back)}</p></div>`
    : `
      <button type="button" id="reveal-button" class="primary">Reveal <kbd>Enter</kbd></button>
      <p class="keyboard-hint">Press Enter to reveal the answer.</p>
    `;

  const ratingHtml = state.revealed && !state.rating
    ? `
      <div class="action-row rating-row">
        <button type="button" class="rating-button again" data-rating="again">Again <kbd>1</kbd></button>
        <button type="button" class="rating-button hard" data-rating="hard">Hard <kbd>2</kbd></button>
        <button type="button" class="rating-button good" data-rating="good">Good <kbd>3</kbd></button>
        <button type="button" class="rating-button easy" data-rating="easy">Easy <kbd>4</kbd></button>
      </div>
      <p class="keyboard-hint">Press 1–4 to rate and continue to the next card.</p>
    `
    : '';

  const busyHtml = state.rating
    ? '<p class="collection-meta">Saving review…</p>'
    : '';

  return `
    <section class="panel drill-panel">
      <div class="header-row">
        <div>
          <p class="eyebrow">${esc(copy.eyebrow)}</p>
          <h1>${esc(card.front)}</h1>
        </div>
        <button type="button" id="back-dashboard-button">Back to dashboard</button>
      </div>
      ${countsHtml}
      <div class="prompt-box">
        <p class="prompt-label">${esc(copy.prompt)}</p>
        ${answerHtml}
      </div>
      ${ratingHtml}
      ${busyHtml}
    </section>
  `;
}

export function renderFsrsDrill(app, state) {
  const errorHtml = state.error
    ? `<div class="error-box" role="alert">${esc(state.error)}</div>`
    : '';

  app.innerHTML = errorHtml + (state.done ? renderDoneScreen(state) : renderCardScreen(state));

  document.getElementById('back-dashboard-button')?.addEventListener('click', state.onBackDashboard);
  document.getElementById('reveal-button')?.addEventListener('click', state.onReveal);
  document.getElementById('optimize-button')?.addEventListener('click', state.onOptimize);

  document.querySelectorAll('.rating-button').forEach(button => {
    button.addEventListener('click', () => {
      const rating = button.dataset.rating;
      if (rating) {
        state.onRate(rating);
      }
    });
  });
}
