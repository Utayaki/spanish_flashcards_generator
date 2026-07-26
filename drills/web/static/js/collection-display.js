'use strict';

function esc(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

const PENCIL_SVG = `
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
    <path d="M12 20h9"></path>
    <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"></path>
  </svg>
`;

export function renderCollectionTitle(collection, state, options = {}) {
  const titleClass = options.titleClass ?? 'collection-name';
  const isEditing = state.editingCollectionId === collection.id;

  if (isEditing) {
    return `
      <div class="collection-title-row">
        <input
          type="text"
          class="inline-rename-input ${esc(titleClass)}"
          id="rename-input-${esc(collection.id)}"
          value="${esc(state.editingCollectionName)}"
          ${state.renaming ? 'disabled' : ''}
        />
        <button
          type="button"
          class="rename-save-button"
          data-collection-id="${esc(collection.id)}"
          ${state.renaming ? 'disabled' : ''}
        >${state.renaming ? 'Saving…' : 'Save'}</button>
        <button
          type="button"
          class="rename-cancel-button"
          ${state.renaming ? 'disabled' : ''}
        >Cancel</button>
      </div>
    `;
  }

  return `
    <div class="collection-title-row">
      <span class="${esc(titleClass)}">${esc(collection.name)}</span>
      <button
        type="button"
        class="icon-button rename-start-button"
        data-collection-id="${esc(collection.id)}"
        aria-label="Rename collection"
      >${PENCIL_SVG}</button>
    </div>
  `;
}

export function wireCollectionRename(state) {
  document.querySelectorAll('.rename-start-button').forEach(button => {
    button.addEventListener('click', () => {
      const collectionId = Number(button.dataset.collectionId);
      if (collectionId) {
        state.onStartRenameCollection(collectionId);
      }
    });
  });

  document.querySelectorAll('.rename-save-button').forEach(button => {
    button.addEventListener('click', () => {
      const collectionId = Number(button.dataset.collectionId);
      if (collectionId && state.editingCollectionId === collectionId) {
        const input = document.getElementById(`rename-input-${collectionId}`);
        if (input instanceof HTMLInputElement) {
          state.editingCollectionName = input.value;
        }
        state.onSaveRenameCollection();
      }
    });
  });

  document.querySelectorAll('.rename-cancel-button').forEach(button => {
    button.addEventListener('click', () => {
      state.onCancelRenameCollection();
    });
  });

  if (state.editingCollectionId !== null) {
    const input = document.getElementById(`rename-input-${state.editingCollectionId}`);
    if (input instanceof HTMLInputElement) {
      input.focus();
      input.select();
      input.addEventListener('keydown', event => {
        if (event.key === 'Enter') {
          event.preventDefault();
          state.editingCollectionName = input.value;
          state.onSaveRenameCollection();
        }
        if (event.key === 'Escape') {
          event.preventDefault();
          state.onCancelRenameCollection();
        }
      });
    }
  }
}
