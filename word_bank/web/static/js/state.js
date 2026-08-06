'use strict';

export const app = document.getElementById('app');

export const state = {
  meta: null,
  selectedType: null,
  query: '',
  results: [],
  searching: false,
  searchTimer: null,
  hasMoreResults: false,
  searchExpanded: false,
  loadingAll: false,
  editor: null,
};

export const CELL_REQUIRED_MESSAGE = 'Every cell must be filled or explicitly marked None.';

export const LEXICAL_ITEM_TYPE_LABELS = {
  noun: 'Noun',
  verb: 'Verb',
  adjective: 'Adjective',
  other: 'Other',
};
