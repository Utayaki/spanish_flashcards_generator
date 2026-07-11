'use strict';

import { api } from './api.js';
import { app, state } from './state.js';
import { esc } from './utils.js';
import { buildModel, buildVerbCodeIndex, sameCell } from './models.js';
import { EDITORS } from './editor-types.js';
import {
  editorTitle,
  refreshUi,
  renderMessage,
} from './editor-status.js';
import {
  onFormClick,
  onFormEvent,
  onFormKeydown,
} from './editor-events.js';

let goHome = null;

export function configureEditor(goHomeCallback) {
  goHome = goHomeCallback;
}

export function startEditor(item, isNew) {
  const firstVerbGroup = state.meta.verb_groups[0]?.code || 'indicative';
  const model = buildModel(item, isNew);
  const editor = {
    model,
    isNew,
    dirty: false,
    activeVerbGroup: firstVerbGroup,
    error: '',
  };
  if (model.lexical_item_type === 'verb') {
    editor.verbCodes = buildVerbCodeIndex();
    editor.vosManual = {};
    for (const tu of Object.keys(editor.verbCodes.tuToVos)) {
      const vos = editor.verbCodes.tuToVos[tu];
      editor.vosManual[vos] = !sameCell(model.verb[tu], model.verb[vos]);
    }
  }
  state.editor = editor;
  renderEditor();
}

function renderEditor() {
  const editor = state.editor;
  if (!editor) return;
  const model = editor.model;
  app.innerHTML = `
    <section class="panel editor-panel">
      <div class="header-row">
        <h1 id="editor-title">${esc(editorTitle(model))}${editor.dirty ? ' *' : ''}</h1>
        <button id="back-button" type="button" class="ghost">Go back</button>
      </div>
      <div id="editor-message">${renderMessage()}</div>
      <form id="editor-form" novalidate>
        ${EDITORS[model.lexical_item_type].renderBody(model, editor.isNew)}
      </form>
      <div class="status-row">
        <span id="dirty-status" class="${editor.dirty ? 'unsaved' : 'muted'}">${editor.dirty ? 'Unsaved changes' : editor.isNew ? 'New lexical item' : 'Saved'}</span>
        <div class="action-row">
          <button type="button" id="discard-button" class="ghost">Discard</button>
          <button type="button" id="save-button" class="primary">Save &amp; go back</button>
        </div>
      </div>
    </section>`;

  document.getElementById('back-button').addEventListener('click', leaveEditor);
  document.getElementById('discard-button').addEventListener('click', leaveEditor);
  document.getElementById('save-button').addEventListener('click', saveEditor);

  const form = document.getElementById('editor-form');
  form.addEventListener('input', onFormEvent);
  form.addEventListener('change', onFormEvent);
  form.addEventListener('click', onFormClick);
  form.addEventListener('keydown', onFormKeydown);

  refreshUi();
}

function collectPayload() {
  const model = state.editor.model;
  const lexicalItemType = model.lexical_item_type;
  const payload = {
    lexical_item_type: lexicalItemType,
    headword: model.headword.trim(),
    explanation: model.explanation.trim(),
  };
  if (!payload.headword) throw new Error('headword cannot be empty');
  if (!payload.explanation) throw new Error('explanation cannot be empty');
  Object.assign(payload, EDITORS[lexicalItemType].collect(model));
  return payload;
}

async function saveEditor() {
  try {
    state.editor.error = '';
    const payload = collectPayload();
    const isNew = state.editor.isNew;
    const path = isNew ? '/api/lexical-items' : `/api/lexical-items/${state.editor.model.id}`;
    const method = isNew ? 'POST' : 'PUT';
    const data = await api(path, { method, body: JSON.stringify(payload) });
    state.selectedType = data.lexical_item.lexical_item_type;
    state.query = '';
    state.results = [];
    state.searching = false;
    clearTimeout(state.searchTimer);
    goHome();
  } catch (error) {
    state.editor.error = error.message;
    const message = document.getElementById('editor-message');
    if (message) message.innerHTML = renderMessage();
  }
}

function leaveEditor() {
  if (state.editor?.dirty && !confirm('Go back without saving these changes?')) return;
  goHome();
}
