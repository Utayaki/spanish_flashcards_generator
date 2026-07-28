'use strict';

import { esc } from './fsrs-dashboard-charts.js';

const CLOZE_BLANK = '_____';

function renderClozeSentence(exampleText) {
  const parts = exampleText.split(CLOZE_BLANK);
  if (parts.length < 2) {
    return `<p class="cloze-sentence">${esc(exampleText)}</p>`;
  }

  const segments = parts.map((part, index) => {
    let html = esc(part);
    if (index < parts.length - 1) {
      html += '<input id="cloze-input" class="cloze-input" type="text" autocomplete="off" spellcheck="false" aria-label="Cloze answer">';
    }
    return html;
  }).join('');

  return `<p class="cloze-sentence">${segments}</p>`;
}

function renderDoneScreen(state) {
  const stats = state.inflectionReview?.counts ?? state.inflectionFsrsStats;
  const statsHtml = stats
    ? `<p class="collection-meta">${esc(stats.due)} due · ${esc(stats.new)} new · ${esc(stats.total)} total</p>`
    : '';

  const optimizeMessage = state.inflectionOptimizeMessage
    ? `<div class="info-box" role="status">${esc(state.inflectionOptimizeMessage)}</div>`
    : '';

  return `
    <section class="panel drill-panel">
      <div class="header-row">
        <h1>All done</h1>
        <button type="button" id="back-inflection-dashboard-button">Back to dashboard</button>
      </div>
      <p>No more word forms to review right now.</p>
      ${statsHtml}
      ${optimizeMessage}
      <div class="action-row rating-row">
        <button
          type="button"
          id="optimize-inflection-button"
          class="primary"
          ${state.inflectionOptimizing ? 'disabled' : ''}
        >${state.inflectionOptimizing ? 'Optimizing…' : 'Update optimizer'}</button>
      </div>
    </section>
  `;
}

function renderReviewScreen(state) {
  const review = state.inflectionReview;
  if (!review) {
    return '<section class="panel drill-panel"><p>Loading next review…</p></section>';
  }

  const counts = review.counts;
  const countsHtml = counts
    ? `<p class="collection-meta">${esc(counts.due)} due · ${esc(counts.new)} new remaining</p>`
    : '';
  const busyHtml = state.inflectionBusy
    ? '<p class="collection-meta">Saving…</p>'
    : '';

  if (state.inflectionSubmitted && state.inflectionResult) {
    const { correct, word_form, filled_text } = state.inflectionResult;
    const feedbackClass = correct ? 'feedback-correct' : 'feedback-incorrect';
    const feedbackText = correct
      ? 'Correct!'
      : `Incorrect — the answer was ${word_form}. Rated Again automatically.`;

    const ratingHtml = correct && !state.inflectionRating
      ? `
        <div class="action-row rating-row">
          <button type="button" class="rating-button again" disabled>Again <kbd>1</kbd></button>
          <button type="button" class="rating-button hard" data-rating="hard">Hard <kbd>2</kbd></button>
          <button type="button" class="rating-button good" data-rating="good">Good <kbd>3</kbd></button>
          <button type="button" class="rating-button easy" data-rating="easy">Easy <kbd>4</kbd></button>
        </div>
        <p class="keyboard-hint">Press <kbd>2</kbd>–<kbd>4</kbd> to rate and continue.</p>
      `
      : '';

    const advanceHint = !correct
      ? '<p class="keyboard-hint">Press <kbd>Enter</kbd> for the next review.</p>'
      : '';

    return `
      <section class="panel drill-panel">
        <div class="header-row">
          <div>
            <p class="eyebrow">Lexical item</p>
            <h1>${esc(review.headword)}</h1>
          </div>
          <button type="button" id="back-inflection-dashboard-button">Back to dashboard</button>
        </div>
        ${countsHtml}
        <div class="prompt-box">
          <p class="prompt-label">Explanation</p>
          <p>${esc(review.explanation)}</p>
        </div>
        <div class="prompt-box">
          <p class="prompt-label">Use this form</p>
          <p>${esc(review.form_descriptor)}</p>
        </div>
        <div class="${feedbackClass}" role="status">${esc(feedbackText)}</div>
        <div class="answer-box">
          <p class="prompt-label">Sentence</p>
          <p class="answer-text">${esc(filled_text)}</p>
        </div>
        ${ratingHtml}
        ${advanceHint}
        ${busyHtml}
      </section>
    `;
  }

  return `
    <section class="panel drill-panel">
      <div class="header-row">
        <div>
          <p class="eyebrow">Lexical item</p>
          <h1>${esc(review.headword)}</h1>
        </div>
        <button type="button" id="back-inflection-dashboard-button">Back to dashboard</button>
      </div>
      ${countsHtml}
      <div class="prompt-box">
        <p class="prompt-label">Explanation</p>
        <p>${esc(review.explanation)}</p>
      </div>
      <div class="prompt-box">
        <p class="prompt-label">Use this form</p>
        <p>${esc(review.form_descriptor)}</p>
      </div>
      <div class="prompt-box">
        <p class="prompt-label">Complete the sentence</p>
        ${renderClozeSentence(review.example_text)}
      </div>
      <p class="keyboard-hint">Type the word form and press <kbd>Enter</kbd> to check your answer.</p>
      ${busyHtml}
    </section>
  `;
}

function wireInflectionDrillEvents(state) {
  document.getElementById('back-inflection-dashboard-button')?.addEventListener(
    'click',
    state.onBackInflectionDashboard,
  );
  document.getElementById('optimize-inflection-button')?.addEventListener(
    'click',
    state.onOptimizeInflection,
  );

  document.querySelectorAll('.rating-button[data-rating]').forEach(button => {
    button.addEventListener('click', () => {
      const rating = button.dataset.rating;
      if (rating) {
        state.onRateInflectionCard(rating);
      }
    });
  });

  const input = document.getElementById('cloze-input');
  if (!input || state.inflectionSubmitted) {
    return;
  }

  input.focus();

  input.addEventListener('keydown', event => {
    if (event.key !== 'Enter' || state.inflectionBusy) {
      return;
    }
    event.preventDefault();
    state.onSubmitInflectionAnswer(input.value);
  });
}

const RATING_BY_KEY = {
  '2': 'hard',
  '3': 'good',
  '4': 'easy',
};

export function createInflectionDrillKeydownHandler(state) {
  return event => {
    if (state.view !== 'inflection-drill' || state.inflectionDone || state.inflectionBusy) {
      return;
    }

    if (!state.inflectionSubmitted || !state.inflectionResult) {
      return;
    }

    if (state.inflectionResult.correct) {
      if (event.target.closest('input, textarea, select, [contenteditable="true"]')) {
        return;
      }
      const rating = RATING_BY_KEY[event.key];
      if (rating) {
        event.preventDefault();
        state.onRateInflectionCard(rating);
      }
      return;
    }

    if (event.key === 'Enter') {
      if (event.target.closest('input, textarea, select, [contenteditable="true"]')) {
        return;
      }
      event.preventDefault();
      state.onAdvanceInflectionDrill();
    }
  };
}

export function renderInflectionDrill(app, state) {
  const errorHtml = state.error
    ? `<div class="error-box" role="alert">${esc(state.error)}</div>`
    : '';

  const bodyHtml = state.inflectionDone ? renderDoneScreen(state) : renderReviewScreen(state);

  app.innerHTML = errorHtml + bodyHtml;

  wireInflectionDrillEvents(state);

  if (!state.inflectionSubmitted && !state.inflectionDone) {
    const input = document.getElementById('cloze-input');
    input?.focus();
  }
}
