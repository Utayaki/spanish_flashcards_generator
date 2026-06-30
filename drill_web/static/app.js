'use strict';

const app = document.getElementById('app');

const LEXICAL_ITEM_TYPE_LABELS = {
  noun: 'Noun',
  verb: 'Verb',
  adjective: 'Adjective',
  other: 'Other',
};

const state = {
  lexicalItem: null,
  flipped: false,
  loading: true,
};

function esc(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

async function api(path) {
  const response = await fetch(path);
  const data = await response.json().catch(() => ({ ok: false, error: 'Server returned invalid JSON.' }));
  if (!response.ok || !data.ok) {
    throw new Error(data.error || `HTTP ${response.status}`);
  }
  return data;
}

function typeLabel(lexicalItemType) {
  return LEXICAL_ITEM_TYPE_LABELS[lexicalItemType] || lexicalItemType;
}

function renderLoading() {
  app.innerHTML = `
    <section class="panel loading-panel">
      <h1>Spanish Drill</h1>
      <p class="muted">Loading…</p>
    </section>
  `;
}

function renderError(message) {
  app.innerHTML = `
    <section class="panel">
      <div class="header-row">
        <h1>Spanish Drill</h1>
      </div>
      <div class="error-box">${esc(message)}</div>
      <div class="action-row">
        <button type="button" class="primary" id="retry-btn">Try again</button>
      </div>
    </section>
  `;
  document.getElementById('retry-btn').addEventListener('click', () => loadRandomCard());
}

function renderCard() {
  const item = state.lexicalItem;
  const showFront = !state.flipped;
  app.innerHTML = `
    <section class="panel">
      <div class="header-row">
        <h1>Spanish Drill</h1>
      </div>
      <div
        class="flashcard"
        id="flashcard"
        role="button"
        tabindex="0"
        aria-label="${showFront ? 'Show translation' : 'Show headword'}"
      >
        <div class="flashcard-face ${showFront ? '' : 'hidden'}" id="flashcard-front">
          <h2 class="flashcard-headword">${esc(item.headword)}</h2>
          <span class="flashcard-type">${esc(typeLabel(item.lexical_item_type))}</span>
        </div>
        <div class="flashcard-face ${showFront ? 'hidden' : ''}" id="flashcard-back">
          <p class="flashcard-translation">${esc(item.explanation)}</p>
        </div>
      </div>
      <div class="action-row">
        <button type="button" class="ghost" id="flip-btn">${showFront ? 'Show translation' : 'Show headword'}</button>
        <button type="button" class="primary" id="next-btn">Next word</button>
      </div>
    </section>
  `;

  const flashcard = document.getElementById('flashcard');
  flashcard.addEventListener('click', toggleFlip);
  flashcard.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      toggleFlip();
    }
  });
  document.getElementById('flip-btn').addEventListener('click', (event) => {
    event.stopPropagation();
    toggleFlip();
  });
  document.getElementById('next-btn').addEventListener('click', (event) => {
    event.stopPropagation();
    loadRandomCard();
  });
}

function toggleFlip() {
  state.flipped = !state.flipped;
  renderCard();
}

async function loadRandomCard() {
  state.loading = true;
  state.flipped = false;
  renderLoading();
  try {
    const data = await api('/api/random');
    state.lexicalItem = data.lexical_item;
    state.loading = false;
    renderCard();
  } catch (error) {
    state.loading = false;
    renderError(error.message);
  }
}

loadRandomCard();
