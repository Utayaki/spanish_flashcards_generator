'use strict';

import { api } from './js/api.js';
import { renderHome } from './js/home.js';

const app = document.getElementById('app');

const state = {
  collections: [],
  creating: false,
  error: null,
  onCreateCollection: null,
};

async function loadCollections() {
  const data = await api('/api/collections');
  state.collections = data.collections;
  state.error = null;
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

function render() {
  renderHome(app, state);
}

state.onCreateCollection = createCollection;

try {
  await loadCollections();
  render();
} catch (error) {
  state.error = error instanceof Error ? error.message : String(error);
  render();
}
