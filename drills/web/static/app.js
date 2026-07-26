'use strict';

import { api } from './js/api.js';
import { renderFsrsDrill } from './js/fsrs-drill.js';
import { renderHome } from './js/home.js';
import { renderLexicalDashboard } from './js/lexical-dashboard.js';

const app = document.getElementById('app');

const state = {
  view: 'home',
  collectionId: null,
  collections: [],
  creating: false,
  loading: false,
  error: null,
  fsrsStats: null,
  card: null,
  revealed: false,
  rating: false,
  done: false,
  optimizing: false,
  optimizeMessage: null,
  cardStartedAt: null,
  onCreateCollection: null,
  onOpenLexicalDashboard: null,
  onBackHome: null,
  onStartFsrsDrill: null,
  onBackDashboard: null,
  onReveal: null,
  onRate: null,
  onOptimize: null,
};

async function loadCollections() {
  const data = await api('/api/collections');
  state.collections = data.collections;
  state.error = null;
}

async function loadFsrsStats(collectionId) {
  const data = await api(`/api/collections/${collectionId}/fsrs/stats`);
  state.fsrsStats = data.stats;
}

async function loadNextCard() {
  const data = await api(`/api/collections/${state.collectionId}/fsrs/next`);
  if (data.done) {
    state.done = true;
    state.card = null;
    state.fsrsStats = data.stats;
    return;
  }
  state.done = false;
  state.card = data.card;
  state.fsrsStats = data.card.counts;
  state.revealed = false;
  state.rating = false;
  state.cardStartedAt = performance.now();
}

async function createCollection() {
  if (state.creating) {
    return;
  }
  state.creating = true;
  state.error = null;
  render();
  try {
    await api('/api/collections', { method: 'POST', body: '{}' });
    await loadCollections();
  } catch (error) {
    state.error = error instanceof Error ? error.message : String(error);
  } finally {
    state.creating = false;
    render();
  }
}

function openLexicalDashboard(collectionId) {
  state.view = 'lexical-dashboard';
  state.collectionId = collectionId;
  state.error = null;
  state.fsrsStats = null;
  state.loading = true;
  render();
  loadFsrsStats(collectionId)
    .catch(error => {
      state.error = error instanceof Error ? error.message : String(error);
    })
    .finally(() => {
      state.loading = false;
      render();
    });
}

function backHome() {
  state.view = 'home';
  state.collectionId = null;
  state.error = null;
  state.fsrsStats = null;
  render();
}

async function startFsrsDrill() {
  state.view = 'fsrs-drill';
  state.error = null;
  state.done = false;
  state.optimizeMessage = null;
  state.card = null;
  render();
  try {
    await loadNextCard();
  } catch (error) {
    state.error = error instanceof Error ? error.message : String(error);
  }
  render();
}

function backDashboard() {
  state.view = 'lexical-dashboard';
  state.error = null;
  state.card = null;
  state.done = false;
  state.optimizeMessage = null;
  render();
  if (state.collectionId !== null) {
    loadFsrsStats(state.collectionId)
      .catch(error => {
        state.error = error instanceof Error ? error.message : String(error);
      })
      .finally(() => render());
  }
}

function revealCard() {
  state.revealed = true;
  render();
}

async function rateCard(rating) {
  if (!state.card || state.rating) {
    return;
  }
  state.rating = true;
  state.error = null;
  render();
  const reviewDurationMs = state.cardStartedAt
    ? Math.max(0, Math.round(performance.now() - state.cardStartedAt))
    : null;
  try {
    const data = await api(`/api/collections/${state.collectionId}/fsrs/rate`, {
      method: 'POST',
      body: JSON.stringify({
        lexical_item_id: state.card.lexical_item_id,
        rating,
        review_duration_ms: reviewDurationMs,
      }),
    });
    state.fsrsStats = data.result.counts;
    await loadNextCard();
  } catch (error) {
    state.error = error instanceof Error ? error.message : String(error);
    state.rating = false;
  }
  render();
}

async function optimizeScheduler() {
  if (state.optimizing || state.collectionId === null) {
    return;
  }
  state.optimizing = true;
  state.error = null;
  state.optimizeMessage = null;
  render();
  try {
    const data = await api(`/api/collections/${state.collectionId}/fsrs/optimize`, {
      method: 'POST',
      body: '{}',
    });
    state.optimizeMessage = data.result.message;
    await loadFsrsStats(state.collectionId);
  } catch (error) {
    state.error = error instanceof Error ? error.message : String(error);
  } finally {
    state.optimizing = false;
    render();
  }
}

function render() {
  if (state.view === 'lexical-dashboard') {
    renderLexicalDashboard(app, state);
    return;
  }
  if (state.view === 'fsrs-drill') {
    renderFsrsDrill(app, state);
    return;
  }
  renderHome(app, state);
}

state.onCreateCollection = createCollection;
state.onOpenLexicalDashboard = openLexicalDashboard;
state.onBackHome = backHome;
state.onStartFsrsDrill = startFsrsDrill;
state.onBackDashboard = backDashboard;
state.onReveal = revealCard;
state.onRate = rateCard;
state.onOptimize = optimizeScheduler;

try {
  await loadCollections();
  render();
} catch (error) {
  state.error = error instanceof Error ? error.message : String(error);
  render();
}
