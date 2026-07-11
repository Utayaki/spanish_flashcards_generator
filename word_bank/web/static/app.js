'use strict';

import { api } from './js/api.js';
import { configureEditor, startEditor } from './js/editor-controller.js';
import { configureHome, renderHome } from './js/home.js';
import { app, state } from './js/state.js';
import { esc } from './js/utils.js';

configureEditor(renderHome);
configureHome(startEditor);

async function init() {
  try {
    const data = await api('/api/meta');
    state.meta = data;
    renderHome();
  } catch (error) {
    app.innerHTML = `<section class="panel"><h1>Spanish Word Bank</h1><div class="error-box">${esc(error.message)}</div></section>`;
  }
}

init();
