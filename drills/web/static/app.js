'use strict';

import { api } from './js/api.js';
import { renderFsrsDrill } from './js/fsrs-drill.js';
import { renderHome } from './js/home.js';
import { renderInflectionDashboard } from './js/inflection-dashboard.js';
import { renderInflectionDrill, createInflectionDrillKeydownHandler } from './js/inflection-drill.js';
import { renderLexicalDashboard } from './js/lexical-dashboard.js';

const app = document.getElementById('app');

const DIRECTION_SPANISH_TO_ENGLISH = 'spanish_to_english';
const DIRECTION_ENGLISH_TO_SPANISH = 'english_to_spanish';
const DIRECTION_NOUN_GENDER = 'noun_gender';
const DIRECTION_ADJECTIVE_INFLECTION_TYPE = 'adjective_inflection_type';
const DIRECTION_MIXED = 'mixed';

const state = {
  view: 'home',
  collectionId: null,
  collections: [],
  creating: false,
  loading: false,
  error: null,
  fsrsStatsS2E: null,
  fsrsStatsE2S: null,
  fsrsStatsNounGender: null,
  fsrsStatsAdjInflection: null,
  fsrsAnalyticsS2E: null,
  fsrsAnalyticsE2S: null,
  fsrsAnalyticsNounGender: null,
  fsrsAnalyticsAdjInflection: null,
  fsrsMixedStats: null,
  dashboardRangeDays: 30,
  analyticsLoading: false,
  drillMode: 'mixed',
  drillDirection: null,
  card: null,
  revealed: false,
  rating: false,
  done: false,
  optimizing: false,
  optimizeMessage: null,
  cardStartedAt: null,
  editingCollectionId: null,
  editingCollectionName: '',
  renaming: false,
  inflectionFsrsStats: null,
  inflectionFsrsAnalytics: null,
  inflectionDashboardRangeDays: 30,
  inflectionAnalyticsLoading: false,
  inflectionReview: null,
  inflectionPhase: 'answering',
  inflectionResult: null,
  inflectionDone: false,
  inflectionBusy: false,
  inflectionRating: false,
  inflectionOptimizing: false,
  inflectionOptimizeMessage: null,
  inflectionReviewStartedAt: null,
  onCreateCollection: null,
  onOpenLexicalDashboard: null,
  onOpenInflectionDashboard: null,
  onBackHome: null,
  onStartFsrsDrill: null,
  onBackDashboard: null,
  onStartInflectionDrill: null,
  onBackInflectionDashboard: null,
  onSubmitInflectionAnswer: null,
  onConfirmInflectionRetry: null,
  onRateInflectionCard: null,
  onOptimizeInflection: null,
  onSetInflectionDashboardRangeDays: null,
  onReveal: null,
  onRate: null,
  onOptimize: null,
  onStartRenameCollection: null,
  onCancelRenameCollection: null,
  onSaveRenameCollection: null,
  onSetDashboardRangeDays: null,
};

async function loadCollections() {
  const data = await api('/api/collections');
  state.collections = data.collections;
  state.error = null;
}

async function loadFsrsStats(collectionId, direction) {
  const timezoneOffset = new Date().getTimezoneOffset();
  const data = await api(
    `/api/collections/${collectionId}/fsrs/stats?direction=${encodeURIComponent(direction)}&timezone_offset_minutes=${timezoneOffset}&range_days=${state.dashboardRangeDays}`,
  );
  if (direction === DIRECTION_SPANISH_TO_ENGLISH) {
    state.fsrsStatsS2E = data.stats;
    state.fsrsAnalyticsS2E = data.analytics;
  } else if (direction === DIRECTION_ENGLISH_TO_SPANISH) {
    state.fsrsStatsE2S = data.stats;
    state.fsrsAnalyticsE2S = data.analytics;
  } else if (direction === DIRECTION_NOUN_GENDER) {
    state.fsrsStatsNounGender = data.stats;
    state.fsrsAnalyticsNounGender = data.analytics;
  } else if (direction === DIRECTION_ADJECTIVE_INFLECTION_TYPE) {
    state.fsrsStatsAdjInflection = data.stats;
    state.fsrsAnalyticsAdjInflection = data.analytics;
  }
}

function setFsrsStatsForDirection(direction, counts) {
  if (direction === DIRECTION_SPANISH_TO_ENGLISH) {
    state.fsrsStatsS2E = counts;
  } else if (direction === DIRECTION_ENGLISH_TO_SPANISH) {
    state.fsrsStatsE2S = counts;
  } else if (direction === DIRECTION_NOUN_GENDER) {
    state.fsrsStatsNounGender = counts;
  } else if (direction === DIRECTION_ADJECTIVE_INFLECTION_TYPE) {
    state.fsrsStatsAdjInflection = counts;
  }
}

async function loadDashboardStats(collectionId) {
  await Promise.all([
    loadFsrsStats(collectionId, DIRECTION_ENGLISH_TO_SPANISH),
    loadFsrsStats(collectionId, DIRECTION_NOUN_GENDER),
    loadFsrsStats(collectionId, DIRECTION_ADJECTIVE_INFLECTION_TYPE),
    loadFsrsStats(collectionId, DIRECTION_SPANISH_TO_ENGLISH),
  ]);
}

async function loadNextCard() {
  const data = await api(
    `/api/collections/${state.collectionId}/fsrs/next?direction=${encodeURIComponent(DIRECTION_MIXED)}`,
  );
  if (data.done) {
    state.done = true;
    state.card = null;
    state.fsrsMixedStats = data.stats;
    return;
  }
  state.done = false;
  state.card = data.card;
  state.fsrsMixedStats = data.card.counts;
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
  state.fsrsStatsS2E = null;
  state.fsrsStatsE2S = null;
  state.fsrsStatsNounGender = null;
  state.fsrsStatsAdjInflection = null;
  state.fsrsAnalyticsS2E = null;
  state.fsrsAnalyticsE2S = null;
  state.fsrsAnalyticsNounGender = null;
  state.fsrsAnalyticsAdjInflection = null;
  state.dashboardRangeDays = 30;
  state.analyticsLoading = false;
  state.loading = true;
  render();
  loadDashboardStats(collectionId)
    .catch(error => {
      state.error = error instanceof Error ? error.message : String(error);
    })
    .finally(() => {
      state.loading = false;
      render();
    });
}

async function loadInflectionFsrsStats(collectionId) {
  const timezoneOffset = new Date().getTimezoneOffset();
  const data = await api(
    `/api/collections/${collectionId}/inflection-fsrs/stats?timezone_offset_minutes=${timezoneOffset}&range_days=${state.inflectionDashboardRangeDays}`,
  );
  state.inflectionFsrsStats = data.stats;
  state.inflectionFsrsAnalytics = data.analytics;
}

function openInflectionDashboard(collectionId) {
  state.view = 'inflection-dashboard';
  state.collectionId = collectionId;
  state.error = null;
  state.inflectionFsrsStats = null;
  state.inflectionFsrsAnalytics = null;
  state.loading = true;
  state.inflectionAnalyticsLoading = true;
  render();
  loadInflectionFsrsStats(collectionId)
    .catch(error => {
      state.error = error instanceof Error ? error.message : String(error);
    })
    .finally(() => {
      state.loading = false;
      state.inflectionAnalyticsLoading = false;
      render();
    });
}

function normalizeAnswer(value) {
  const trimmed = String(value ?? '').trim();
  if (typeof trimmed.casefold === 'function') {
    return trimmed.casefold();
  }
  return trimmed.toLocaleLowerCase('es');
}

function resetInflectionDrillState() {
  state.inflectionReview = null;
  state.inflectionPhase = 'answering';
  state.inflectionResult = null;
  state.inflectionDone = false;
  state.inflectionBusy = false;
  state.inflectionRating = false;
  state.inflectionOptimizeMessage = null;
  state.inflectionReviewStartedAt = null;
}

async function loadNextInflectionReview() {
  const data = await api(`/api/collections/${state.collectionId}/inflection-fsrs/next`);
  if (data.done) {
    state.inflectionDone = true;
    state.inflectionReview = null;
    state.inflectionPhase = 'answering';
    state.inflectionResult = null;
    state.inflectionRating = false;
    if (data.stats) {
      state.inflectionFsrsStats = data.stats;
    }
    return;
  }
  state.inflectionDone = false;
  state.inflectionReview = data.review;
  state.inflectionPhase = 'answering';
  state.inflectionResult = null;
  state.inflectionRating = false;
  state.inflectionFsrsStats = data.review.counts;
  state.inflectionReviewStartedAt = performance.now();
}

async function startInflectionDrill() {
  if (state.collectionId === null) {
    return;
  }
  const due = Number(state.inflectionFsrsStats?.due ?? 0);
  const newCards = Number(state.inflectionFsrsStats?.new ?? 0);
  if (due + newCards <= 0) {
    return;
  }
  state.view = 'inflection-drill';
  state.error = null;
  resetInflectionDrillState();
  state.inflectionBusy = true;
  render();
  try {
    await loadNextInflectionReview();
  } catch (error) {
    state.error = error instanceof Error ? error.message : String(error);
  } finally {
    state.inflectionBusy = false;
    render();
  }
}

async function submitInflectionAnswer(answer) {
  if (
    state.inflectionBusy
    || state.inflectionPhase !== 'answering'
    || !state.inflectionReview
    || state.collectionId === null
  ) {
    return;
  }
  state.inflectionBusy = true;
  state.error = null;
  render();
  const reviewDurationMs = state.inflectionReviewStartedAt
    ? Math.max(0, Math.round(performance.now() - state.inflectionReviewStartedAt))
    : null;
  try {
    const data = await api(`/api/collections/${state.collectionId}/inflection-fsrs/submit`, {
      method: 'POST',
      body: JSON.stringify({
        word_form_id: state.inflectionReview.word_form_id,
        answer,
        review_duration_ms: reviewDurationMs,
      }),
    });
    const result = data.result;
    state.inflectionResult = {
      correct: result.correct,
      word_form: result.word_form,
    };
    state.inflectionPhase = result.correct ? 'rating' : 'retry';
    state.inflectionFsrsStats = result.counts;
    state.inflectionRating = false;
  } catch (error) {
    state.error = error instanceof Error ? error.message : String(error);
  } finally {
    state.inflectionBusy = false;
    render();
  }
}

async function confirmInflectionRetry(answer) {
  if (
    state.inflectionBusy
    || state.inflectionPhase !== 'retry'
    || !state.inflectionReview
    || !state.inflectionResult
  ) {
    return;
  }
  try {
    const expectedRaw = state.inflectionResult.word_form ?? state.inflectionReview.word_form;
    const expected = normalizeAnswer(expectedRaw);
    const typed = normalizeAnswer(answer);
    if (typed !== expected) {
      state.error = 'That does not match the correct form. Try again.';
      render();
      return;
    }
    state.error = null;
    state.inflectionBusy = true;
    render();
    await loadNextInflectionReview();
  } catch (error) {
    state.error = error instanceof Error ? error.message : String(error);
  } finally {
    state.inflectionBusy = false;
    render();
  }
}

async function rateInflectionCard(rating) {
  if (
    state.inflectionPhase !== 'rating'
    || !state.inflectionResult?.correct
    || state.inflectionRating
    || !state.inflectionReview
    || state.collectionId === null
  ) {
    return;
  }
  state.inflectionRating = true;
  state.inflectionBusy = true;
  state.error = null;
  render();
  const reviewDurationMs = state.inflectionReviewStartedAt
    ? Math.max(0, Math.round(performance.now() - state.inflectionReviewStartedAt))
    : null;
  try {
    const data = await api(`/api/collections/${state.collectionId}/inflection-fsrs/rate`, {
      method: 'POST',
      body: JSON.stringify({
        word_form_id: state.inflectionReview.word_form_id,
        rating,
        review_duration_ms: reviewDurationMs,
      }),
    });
    state.inflectionFsrsStats = data.result.counts;
    await loadNextInflectionReview();
  } catch (error) {
    state.error = error instanceof Error ? error.message : String(error);
    state.inflectionRating = false;
  } finally {
    state.inflectionBusy = false;
    render();
  }
}

function backInflectionDashboard() {
  state.view = 'inflection-dashboard';
  state.error = null;
  resetInflectionDrillState();
  render();
  if (state.collectionId !== null) {
    loadInflectionFsrsStats(state.collectionId)
      .catch(error => {
        state.error = error instanceof Error ? error.message : String(error);
      })
      .finally(() => render());
  }
}

function backHome() {
  state.view = 'home';
  state.collectionId = null;
  state.error = null;
  state.fsrsStatsS2E = null;
  state.fsrsStatsE2S = null;
  state.fsrsStatsNounGender = null;
  state.fsrsStatsAdjInflection = null;
  state.fsrsAnalyticsS2E = null;
  state.fsrsAnalyticsE2S = null;
  state.fsrsAnalyticsNounGender = null;
  state.fsrsAnalyticsAdjInflection = null;
  state.dashboardRangeDays = 30;
  state.analyticsLoading = false;
  state.fsrsMixedStats = null;
  state.drillMode = 'mixed';
  state.drillDirection = null;
  state.inflectionFsrsStats = null;
  state.inflectionFsrsAnalytics = null;
  state.inflectionDashboardRangeDays = 30;
  state.inflectionAnalyticsLoading = false;
  resetInflectionDrillState();
  render();
}

async function optimizeInflectionScheduler() {
  if (state.inflectionOptimizing || state.collectionId === null) {
    return;
  }
  state.inflectionOptimizing = true;
  state.error = null;
  state.inflectionOptimizeMessage = null;
  render();
  try {
    const data = await api(`/api/collections/${state.collectionId}/inflection-fsrs/optimize`, {
      method: 'POST',
      body: '{}',
    });
    state.inflectionOptimizeMessage = data.result.message;
    await loadInflectionFsrsStats(state.collectionId);
  } catch (error) {
    state.error = error instanceof Error ? error.message : String(error);
  } finally {
    state.inflectionOptimizing = false;
    render();
  }
}

async function setInflectionDashboardRangeDays(days) {
  if (state.inflectionDashboardRangeDays === days || state.collectionId === null) {
    return;
  }
  state.inflectionDashboardRangeDays = days;
  state.inflectionAnalyticsLoading = true;
  state.error = null;
  render();
  try {
    await loadInflectionFsrsStats(state.collectionId);
  } catch (error) {
    state.error = error instanceof Error ? error.message : String(error);
  } finally {
    state.inflectionAnalyticsLoading = false;
    render();
  }
}

async function startFsrsDrill() {
  state.view = 'fsrs-drill';
  state.drillMode = 'mixed';
  state.drillDirection = null;
  state.error = null;
  state.done = false;
  state.optimizeMessage = null;
  state.card = null;
  state.fsrsMixedStats = null;
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
  state.fsrsMixedStats = null;
  state.drillMode = 'mixed';
  state.drillDirection = null;
  render();
  if (state.collectionId !== null) {
    loadDashboardStats(state.collectionId)
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
        direction: state.card.direction,
        study_card_id: state.card.study_card_id,
        rating,
        review_duration_ms: reviewDurationMs,
      }),
    });
    setFsrsStatsForDirection(data.result.direction, data.result.counts);
    state.fsrsMixedStats = data.result.mixed_counts ?? data.result.counts;
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
    await loadDashboardStats(state.collectionId);
  } catch (error) {
    state.error = error instanceof Error ? error.message : String(error);
  } finally {
    state.optimizing = false;
    render();
  }
}

function startRenameCollection(collectionId) {
  const collection = state.collections.find(item => item.id === collectionId);
  if (!collection) {
    return;
  }
  state.editingCollectionId = collectionId;
  state.editingCollectionName = collection.display_name ?? collection.name;
  state.error = null;
  render();
}

function cancelRenameCollection() {
  state.editingCollectionId = null;
  state.editingCollectionName = '';
  state.renaming = false;
  render();
}

async function saveRenameCollection() {
  if (state.editingCollectionId === null || state.renaming) {
    return;
  }
  const name = state.editingCollectionName.trim();
  if (!name) {
    state.error = 'Collection name cannot be empty.';
    render();
    return;
  }
  state.renaming = true;
  state.error = null;
  render();
  try {
    const data = await api(`/api/collections/${state.editingCollectionId}`, {
      method: 'PATCH',
      body: JSON.stringify({ name }),
    });
    const updated = data.collection;
    const index = state.collections.findIndex(item => item.id === updated.id);
    if (index >= 0) {
      state.collections[index] = updated;
    }
    state.editingCollectionId = null;
    state.editingCollectionName = '';
  } catch (error) {
    state.error = error instanceof Error ? error.message : String(error);
  } finally {
    state.renaming = false;
    render();
  }
}

const RATING_BY_KEY = {
  '1': 'again',
  '2': 'hard',
  '3': 'good',
  '4': 'easy',
};

function handleFsrsDrillKeydown(event) {
  if (state.view !== 'fsrs-drill' || state.done || state.rating) {
    return;
  }
  if (event.target.closest('input, textarea, select, [contenteditable="true"]')) {
    return;
  }

  if (!state.revealed) {
    if (event.key === 'Enter') {
      event.preventDefault();
      revealCard();
    }
    return;
  }

  const rating = RATING_BY_KEY[event.key];
  if (rating) {
    event.preventDefault();
    rateCard(rating);
  }
}

async function setDashboardRangeDays(days) {
  if (state.dashboardRangeDays === days || state.collectionId === null) {
    return;
  }
  state.dashboardRangeDays = days;
  state.analyticsLoading = true;
  state.error = null;
  render();
  try {
    await loadDashboardStats(state.collectionId);
  } catch (error) {
    state.error = error instanceof Error ? error.message : String(error);
  } finally {
    state.analyticsLoading = false;
    render();
  }
}

function render() {
  if (state.view === 'lexical-dashboard') {
    renderLexicalDashboard(app, state);
    return;
  }
  if (state.view === 'inflection-dashboard') {
    renderInflectionDashboard(app, state);
    return;
  }
  if (state.view === 'inflection-drill') {
    renderInflectionDrill(app, state);
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
state.onOpenInflectionDashboard = openInflectionDashboard;
state.onBackHome = backHome;
state.onStartFsrsDrill = startFsrsDrill;
state.onBackDashboard = backDashboard;
state.onStartInflectionDrill = startInflectionDrill;
state.onBackInflectionDashboard = backInflectionDashboard;
state.onSubmitInflectionAnswer = submitInflectionAnswer;
state.onConfirmInflectionRetry = confirmInflectionRetry;
state.onRateInflectionCard = rateInflectionCard;
state.onOptimizeInflection = optimizeInflectionScheduler;
state.onSetInflectionDashboardRangeDays = setInflectionDashboardRangeDays;
state.onReveal = revealCard;
state.onRate = rateCard;
state.onOptimize = optimizeScheduler;
state.onStartRenameCollection = startRenameCollection;
state.onCancelRenameCollection = cancelRenameCollection;
state.onSaveRenameCollection = saveRenameCollection;
state.onSetDashboardRangeDays = setDashboardRangeDays;

document.addEventListener('keydown', handleFsrsDrillKeydown);
document.addEventListener('keydown', createInflectionDrillKeydownHandler(state));

try {
  await loadCollections();
  render();
} catch (error) {
  state.error = error instanceof Error ? error.message : String(error);
  render();
}
