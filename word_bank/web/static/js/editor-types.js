'use strict';

import { CELL_REQUIRED_MESSAGE, state } from './state.js';
import { emptyNestedForms, isGenderEnabled } from './models.js';
import {
  adjectiveTypeRow,
  commonBaseCard,
  genderRequiredCardInner,
  genderRow,
  nounGridCardInner,
  otherTypeRow,
  pluralityCardInner,
  verbFormsInner,
  verbParticiplesInner,
} from './views.js';

export const EDITORS = {
  noun: {
    renderBody(model, isNew) {
      return `
        ${commonBaseCard(model, isNew, genderRow(model))}
        <p id="helper-text" class="helper"></p>
        <div id="noun-grid-card" class="card">${nounGridCardInner(model)}</div>`;
    },
    deriveUi(model) {
      const explanation = model.explanation.trim();
      const gender = model.gender_availability || '';
      const visibility = { 'noun-grid-card': !explanation || !gender };
      let helperText = '';
      if (!explanation) helperText = 'Enter the explanation to unlock gender and inflections.';
      else if (!gender) helperText = 'Choose gender to unlock the inflections table.';
      else if (!nounCellsComplete(model)) helperText = CELL_REQUIRED_MESSAGE;
      else if (!anyNounForm(model)) helperText = 'A noun needs at least one form.';
      const valid = Boolean(model.headword.trim() && explanation && gender && !helperText);
      return { valid, helperText, visibility };
    },
    collect(model) {
      if (!model.gender_availability) throw new Error('choose gender');
      if (!nounCellsComplete(model)) throw new Error(CELL_REQUIRED_MESSAGE);
      if (!anyNounForm(model)) throw new Error('A noun needs at least one form.');
      const forms = emptyNestedForms();
      const genderAvailability = model.gender_availability;
      for (const number of state.meta.numbers) {
        for (const gender of state.meta.genders) {
          const enabled = isGenderEnabled(genderAvailability, gender);
          const cell = model.forms[number][gender];
          forms[number][gender] = (cell.none || !enabled) ? null : (cell.text.trim() || null);
        }
      }
      return { gender_availability: genderAvailability, forms };
    },
  },

  adjective: {
    renderBody(model, isNew) {
      return `
        ${commonBaseCard(model, isNew, adjectiveTypeRow(model))}
        <p id="helper-text" class="helper"></p>
        <div id="adjective-plurality-card" class="card">${pluralityCardInner('Plurality', model, true)}</div>
        <div id="adjective-gender-grid-card" class="card">${genderRequiredCardInner('Plurality + gender', model, true)}</div>`;
    },
    deriveUi(model) {
      const explanation = model.explanation.trim();
      const type = model.inflection_type || '';
      const visibility = {
        'adjective-plurality-card': !explanation || type !== 'plurality',
        'adjective-gender-grid-card': !explanation || type !== 'gender_plurality',
      };
      let helperText = '';
      if (!explanation) helperText = 'Enter the explanation to unlock adjective forms.';
      else if (!type) helperText = 'Choose what the adjective is inflective by.';
      else if (type === 'plurality' && !pluralityComplete(model)) helperText = CELL_REQUIRED_MESSAGE;
      else if (type === 'gender_plurality' && !genderComplete(model)) helperText = CELL_REQUIRED_MESSAGE;
      const valid = Boolean(model.headword.trim() && explanation && type && !helperText);
      return { valid, helperText, visibility };
    },
    collect(model) {
      const type = model.inflection_type;
      if (!type) throw new Error('choose what the adjective is inflective by');
      return { adjective_inflection_type: type, forms: collectInflectionForms(model, type) };
    },
  },

  other: {
    renderBody(model, isNew) {
      return `
        ${commonBaseCard(model, isNew, otherTypeRow(model))}
        <p id="helper-text" class="helper"></p>
        <div id="other-plurality-card" class="card">${pluralityCardInner('Plurality', model, false)}</div>
        <div id="other-grid-card" class="card">${genderRequiredCardInner('Plurality + gender', model, false)}</div>`;
    },
    deriveUi(model) {
      const explanation = model.explanation.trim();
      const type = model.inflection_type || '';
      const visibility = {
        'other-plurality-card': !explanation || type !== 'plurality',
        'other-grid-card': !explanation || type !== 'gender_plurality',
      };
      let helperText = '';
      if (!explanation) helperText = 'Enter the explanation to unlock the inflection type.';
      else if (!type) helperText = 'Choose inflection type.';
      else if (type === 'plurality' && !pluralityComplete(model)) helperText = CELL_REQUIRED_MESSAGE;
      else if (type === 'gender_plurality' && !genderComplete(model)) helperText = CELL_REQUIRED_MESSAGE;
      const valid = Boolean(model.headword.trim() && explanation && type && !helperText);
      return { valid, helperText, visibility };
    },
    collect(model) {
      const type = model.inflection_type;
      if (!type) throw new Error('choose inflection type');
      const forms = type === 'plurality' || type === 'gender_plurality'
        ? collectInflectionForms(model, type)
        : emptyNestedForms();
      return { inflection_type: type, forms };
    },
  },

  verb: {
    renderBody(model, isNew) {
      return `
        ${commonBaseCard(model, isNew)}
        <p id="helper-text" class="helper"></p>
        <div id="verb-participles-card" class="card">${verbParticiplesInner(model)}</div>
        <div id="verb-forms-card" class="card">${verbFormsInner(model)}</div>`;
    },
    deriveUi(model) {
      const explanation = model.explanation.trim();
      const visibility = {
        'verb-participles-card': !explanation,
        'verb-forms-card': !explanation,
      };
      let helperText = '';
      if (!explanation) helperText = 'Enter the explanation to unlock participles and conjugations.';
      else if (!verbActiveComplete(model)) helperText = CELL_REQUIRED_MESSAGE;
      const valid = Boolean(model.headword.trim() && explanation && !helperText);
      return { valid, helperText, visibility };
    },
    collect(model) {
      if (!verbActiveComplete(model)) throw new Error(CELL_REQUIRED_MESSAGE);
      const forms = {};
      for (const code of state.editor.verbCodes.all) {
        const cell = model.verb[code];
        forms[code] = { form: cell.none ? null : (cell.text.trim() || null) };
      }
      return { forms };
    },
  },
};

function nounCellsComplete(model) {
  const genderAvailability = model.gender_availability || 'both';
  for (const number of state.meta.numbers) {
    for (const gender of state.meta.genders) {
      if (!isGenderEnabled(genderAvailability, gender)) continue;
      const cell = model.forms[number][gender];
      if (!(cell.none || cell.text.trim())) return false;
    }
  }
  return true;
}

function anyNounForm(model) {
  const genderAvailability = model.gender_availability || 'both';
  for (const number of state.meta.numbers) {
    for (const gender of state.meta.genders) {
      if (!isGenderEnabled(genderAvailability, gender)) continue;
      const cell = model.forms[number][gender];
      if (!cell.none && cell.text.trim()) return true;
    }
  }
  return false;
}

function pluralityComplete(model) {
  return state.meta.numbers.every(number => Boolean(model.forms[number].shared.text.trim()));
}

function genderComplete(model) {
  return state.meta.numbers.every(number =>
    state.meta.genders.every(gender => Boolean(model.forms[number][gender].text.trim())));
}

function verbActiveComplete(model) {
  const index = state.editor.verbCodes;
  const codes = [...index.participles, ...(index.byGroup[state.editor.activeVerbGroup] || [])];
  return codes.every(code => {
    const cell = model.verb[code];
    return cell.none || cell.text.trim();
  });
}

function collectInflectionForms(model, type) {
  const forms = emptyNestedForms();
  if (type === 'plurality') {
    if (!pluralityComplete(model)) throw new Error(CELL_REQUIRED_MESSAGE);
    for (const number of state.meta.numbers) {
      forms[number].shared = model.forms[number].shared.text.trim();
    }
  } else {
    if (!genderComplete(model)) throw new Error(CELL_REQUIRED_MESSAGE);
    for (const number of state.meta.numbers) {
      for (const gender of state.meta.genders) {
        forms[number][gender] = model.forms[number][gender].text.trim();
      }
    }
  }
  return forms;
}
