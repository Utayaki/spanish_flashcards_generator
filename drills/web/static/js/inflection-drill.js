'use strict';

import { esc } from './fsrs-dashboard-charts.js';

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

function renderPromptFields(review, { showExplanation = true } = {}) {
  const explanationHtml = showExplanation
    ? `
    <div class="prompt-box">
      <p class="prompt-label">Explanation</p>
      <p>${esc(review.explanation)}</p>
    </div>`
    : '';

  return `
    ${explanationHtml}
    <div class="prompt-box">
      <p class="prompt-label">Use this form</p>
      <p>${esc(review.form_descriptor)}</p>
    </div>
  `;
}

function renderAnswerInput(formId, inputId, label) {
  return `
    <form id="${esc(formId)}" class="prompt-box">
      <p class="prompt-label">${esc(label)}</p>
      <input
        id="${esc(inputId)}"
        class="cloze-input"
        type="text"
        autocomplete="off"
        spellcheck="false"
        aria-label="${esc(label)}"
      >
    </form>
  `;
}

function isEnterKey(key) {
  return key === 'Enter' || key === 'NumpadEnter';
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

  if (state.inflectionPhase === 'rating' && state.inflectionResult?.correct) {
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
        ${renderPromptFields(review)}
        <div class="feedback-correct" role="status">Correct!</div>
        <div class="action-row rating-row">
          <button type="button" class="rating-button again" disabled>Again <kbd>1</kbd></button>
          <button type="button" class="rating-button hard" data-rating="hard">Hard <kbd>2</kbd></button>
          <button type="button" class="rating-button good" data-rating="good">Good <kbd>3</kbd></button>
          <button type="button" class="rating-button easy" data-rating="easy">Easy <kbd>4</kbd></button>
        </div>
        <p class="keyboard-hint">Press <kbd>2</kbd>–<kbd>4</kbd> to rate and continue.</p>
        ${busyHtml}
      </section>
    `;
  }

  if (state.inflectionPhase === 'retry' && state.inflectionResult) {
    const { word_form } = state.inflectionResult;
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
        ${renderPromptFields(review)}
        <div class="feedback-incorrect" role="status">
          Incorrect — the answer was ${esc(word_form)}. Rated Again automatically.
        </div>
        <div class="answer-box">
          <p class="prompt-label">Correct form</p>
          <p class="answer-text">${esc(word_form)}</p>
        </div>
        ${renderAnswerInput('inflection-retry-form', 'inflection-retry-input', 'Type the correct form to continue')}
        <p class="keyboard-hint">Type the correct form and press <kbd>Enter</kbd> to continue.</p>
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
      ${renderPromptFields(review, { showExplanation: false })}
      ${renderAnswerInput('inflection-answer-form', 'inflection-answer-input', 'Type the form')}
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

  const answerForm = document.getElementById('inflection-answer-form');
  const answerInput = document.getElementById('inflection-answer-input');
  if (answerForm && answerInput && state.inflectionPhase === 'answering') {
    answerInput.focus();
    answerForm.addEventListener('submit', event => {
      event.preventDefault();
      if (state.inflectionBusy || typeof state.onSubmitInflectionAnswer !== 'function') {
        return;
      }
      state.onSubmitInflectionAnswer(answerInput.value);
    });
    answerInput.addEventListener('keydown', event => {
      if (!isEnterKey(event.key) || state.inflectionBusy) {
        return;
      }
      event.preventDefault();
      if (typeof state.onSubmitInflectionAnswer === 'function') {
        state.onSubmitInflectionAnswer(answerInput.value);
      }
    });
  }

  const retryForm = document.getElementById('inflection-retry-form');
  const retryInput = document.getElementById('inflection-retry-input');
  if (retryForm && retryInput && state.inflectionPhase === 'retry') {
    retryInput.focus();
    retryForm.addEventListener('submit', event => {
      event.preventDefault();
      if (state.inflectionBusy || typeof state.onConfirmInflectionRetry !== 'function') {
        return;
      }
      state.onConfirmInflectionRetry(retryInput.value);
    });
    retryInput.addEventListener('keydown', event => {
      if (!isEnterKey(event.key) || state.inflectionBusy) {
        return;
      }
      event.preventDefault();
      if (typeof state.onConfirmInflectionRetry === 'function') {
        state.onConfirmInflectionRetry(retryInput.value);
      }
    });
  }
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

    if (state.inflectionPhase === 'rating' && state.inflectionResult?.correct) {
      if (event.target.closest('input, textarea, select, [contenteditable="true"]')) {
        return;
      }
      const rating = RATING_BY_KEY[event.key];
      if (rating) {
        event.preventDefault();
        state.onRateInflectionCard(rating);
      }
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
}
