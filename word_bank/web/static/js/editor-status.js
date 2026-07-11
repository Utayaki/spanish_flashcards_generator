'use strict';

import { LEXICAL_ITEM_TYPE_LABELS, state } from './state.js';
import { esc } from './utils.js';
import { EDITORS } from './editor-types.js';

export function renderMessage() {
  if (state.editor.error) return `<div class="error-box">${esc(state.editor.error)}</div>`;
  return '';
}

export function showEditorError(message) {
  if (state.editor) state.editor.error = message;
  const box = document.getElementById('editor-message');
  if (box) box.innerHTML = renderMessage();
}

export function onModelChanged() {
  markDirty();
  refreshUi();
}

export function markDirty() {
  if (!state.editor) return;
  state.editor.dirty = true;
  state.editor.error = '';
  const model = state.editor.model;
  const title = document.getElementById('editor-title');
  if (title) title.textContent = `${editorTitle(model)} *`;
  const status = document.getElementById('dirty-status');
  if (status) {
    status.textContent = 'Unsaved changes';
    status.className = 'unsaved';
  }
  const message = document.getElementById('editor-message');
  if (message) message.innerHTML = '';
}

export function refreshUi() {
  const model = state.editor.model;
  const { valid, helperText, visibility } = EDITORS[model.lexical_item_type].deriveUi(model);
  for (const id of Object.keys(visibility)) {
    document.getElementById(id)?.classList.toggle('hidden', visibility[id]);
  }
  const helper = document.getElementById('helper-text');
  if (helper) {
    helper.textContent = helperText;
    helper.classList.toggle('hidden', !helperText);
  }
  const saveButton = document.getElementById('save-button');
  if (saveButton) saveButton.disabled = !valid;
}

export function editorTitle(model) {
  const title = (model.headword || '').trim() || 'Untitled';
  const label = LEXICAL_ITEM_TYPE_LABELS[model.lexical_item_type] || model.lexical_item_type;
  return `${label}: ${title}`;
}
