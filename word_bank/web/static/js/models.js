'use strict';

import { state } from './state.js';

export function emptyNestedForms() {
  return {
    singular: { masculine: null, feminine: null, shared: null },
    plural: { masculine: null, feminine: null, shared: null },
  };
}

export function makeDraftLexicalItem(lexicalItemType, headwordText) {
  const item = { id: null, lexical_item_type: lexicalItemType, headword: headwordText, explanation: '' };
  if (lexicalItemType === 'noun') {
    item.noun = { gender_availability: '', inflections: emptyNestedForms() };
  } else if (lexicalItemType === 'adjective') {
    item.adjective = { adjective_inflection_type: '', inflections: emptyNestedForms() };
  } else if (lexicalItemType === 'other') {
    item.other = { inflection_type: '', inflections: emptyNestedForms() };
  } else if (lexicalItemType === 'verb') {
    item.verb = { forms: {} };
  }
  return item;
}

export function makeCell(text, none) {
  return { text: text || '', none: Boolean(none) };
}

export function sameCell(a, b) {
  return a.none === b.none && a.text === b.text;
}

export function buildModel(item, isNew) {
  const model = {
    id: item.id ?? null,
    lexical_item_type: item.lexical_item_type,
    headword: item.headword || '',
    explanation: item.explanation || '',
  };
  const type = model.lexical_item_type;
  if (type === 'noun') {
    const details = item.noun || {};
    model.gender_availability = details.gender_availability || '';
    model.forms = buildNounForms(details.inflections, model.gender_availability, isNew);
  } else if (type === 'adjective') {
    const details = item.adjective || {};
    model.inflection_type = details.adjective_inflection_type || '';
    model.forms = buildNullableInflectionForms(details.inflections, isNew);
  } else if (type === 'other') {
    const details = item.other || {};
    model.inflection_type = details.inflection_type || '';
    model.forms = buildRequiredForms(details.inflections);
  } else if (type === 'verb') {
    model.verb = buildVerbCells(item, isNew);
  }
  return model;
}

function buildNounForms(inflections, genderAvailability, isNew) {
  const forms = {};
  for (const number of state.meta.numbers) {
    forms[number] = {};
    for (const gender of state.meta.genders) {
      const enabled = isGenderEnabled(genderAvailability || 'both', gender);
      const raw = inflections?.[number]?.[gender];
      forms[number][gender] = enabled
        ? makeCell(raw ?? '', !isNew && raw === null)
        : makeCell('', true);
    }
  }
  return forms;
}

function buildNullableInflectionForms(inflections, isNew) {
  const forms = {};
  for (const number of state.meta.numbers) {
    forms[number] = {};
    for (const gender of state.meta.genders) {
      const raw = inflections?.[number]?.[gender];
      forms[number][gender] = makeCell(raw ?? '', !isNew && raw === null);
    }
    const sharedRaw = inflections?.[number]?.shared;
    forms[number].shared = makeCell(sharedRaw ?? '', !isNew && sharedRaw === null);
  }
  return forms;
}

function buildRequiredForms(inflections) {
  const forms = {};
  for (const number of state.meta.numbers) {
    forms[number] = {
      masculine: makeCell(inflections?.[number]?.masculine ?? '', false),
      feminine: makeCell(inflections?.[number]?.feminine ?? '', false),
      shared: makeCell(inflections?.[number]?.shared ?? '', false),
    };
  }
  return forms;
}

function buildVerbCells(item, isNew) {
  const forms = item.verb?.forms || {};
  const cells = {};
  for (const code of allVerbCodes()) {
    const raw = forms[code]?.form;
    cells[code] = makeCell(raw ?? '', !isNew && raw === null);
  }
  return cells;
}

function allVerbCodes() {
  const codes = [];
  for (const participle of state.meta.verb_participles) codes.push(participle.code);
  for (const group of state.meta.verb_groups) {
    for (const tense of group.tenses) {
      for (const form of tense.forms) codes.push(form.code);
    }
  }
  return codes;
}

export function buildVerbCodeIndex() {
  const participles = state.meta.verb_participles.map(participle => participle.code);
  const byGroup = {};
  const tuToVos = {};
  for (const group of state.meta.verb_groups) {
    const list = [];
    for (const tense of group.tenses) {
      let tu = null;
      let vos = null;
      for (const form of tense.forms) {
        list.push(form.code);
        if (form.person_code === 'tu') tu = form.code;
        if (form.person_code === 'vos') vos = form.code;
      }
      if (tu && vos) tuToVos[tu] = vos;
    }
    byGroup[group.code] = list;
  }
  const all = [...participles];
  for (const group of state.meta.verb_groups) all.push(...byGroup[group.code]);
  return { participles, byGroup, all, tuToVos };
}

export function defaultNounForms(genderAvailability, headword) {
  const forms = {};
  for (const number of state.meta.numbers) {
    forms[number] = {};
    for (const gender of state.meta.genders) {
      const enabled = isGenderEnabled(genderAvailability || 'both', gender);
      if (!enabled) {
        forms[number][gender] = makeCell('', true);
        continue;
      }
      const defaultValue = shouldDefaultNounForm(true, number, gender, genderAvailability) ? (headword || '') : '';
      forms[number][gender] = makeCell(defaultValue, false);
    }
  }
  return forms;
}

function shouldDefaultNounForm(isNew, number, gender, genderAvailability) {
  return isNew
    && number === 'singular'
    && isGenderEnabled(genderAvailability, gender)
    && (genderAvailability !== 'both' || gender === 'masculine');
}

export function defaultInflectionForms(type, headword) {
  const forms = {};
  for (const number of state.meta.numbers) {
    const isSingular = number === 'singular';
    forms[number] = {
      masculine: makeCell(type === 'gender_plurality' && isSingular ? headword : '', false),
      feminine: makeCell('', false),
      shared: makeCell(type === 'plurality' && isSingular ? headword : '', false),
    };
  }
  return forms;
}

export function nounVisibleGenders(availability) {
  if (availability === 'masculine') return ['masculine'];
  if (availability === 'feminine') return ['feminine'];
  return state.meta.genders;
}

export function isGenderEnabled(availability, gender) {
  if (availability === 'masculine') return gender === 'masculine';
  if (availability === 'feminine') return gender === 'feminine';
  return true;
}

export function findVerbDefinition(tense, personCode) {
  return tense.forms.find(form => form.person_code === personCode) || null;
}
