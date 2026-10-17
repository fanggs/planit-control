import test from 'node:test';
import assert from 'node:assert/strict';
import {applySuggestedCategory, categoryForSuggestion, freezeReportInputs, mayApplySuggestion} from '../crew-photo-suggestion.js';

test('only contract hazard types become crew select options', () => {
  assert.equal(categoryForSuggestion({hazard_type: 'soil_saturation'}), 'Soil / access');
  assert.equal(categoryForSuggestion({hazard_type: 'wildlife'}), 'Wildlife');
  assert.equal(categoryForSuggestion({hazard_type: '__proto__'}), null);
  assert.equal(categoryForSuggestion(null), null);
});

test('a late suggestion cannot replace a human choice or a new photo/form', () => {
  assert.equal(mayApplySuggestion({samePhoto: true, currentForm: true, userChoseCategory: false}), true);
  assert.equal(mayApplySuggestion({samePhoto: true, currentForm: true, userChoseCategory: true}), false);
  assert.equal(mayApplySuggestion({samePhoto: false, currentForm: true, userChoseCategory: false}), false);
  assert.equal(mayApplySuggestion({samePhoto: true, currentForm: false, userChoseCategory: false}), false);
});

test('a late Gemini prefill requires a fresh human confirmation', () => {
  const category={value:''},confirmation={checked:true};
  assert.equal(applySuggestedCategory({hazard_type:'wildlife'},category,confirmation),'Wildlife');
  assert.equal(category.value,'Wildlife');
  assert.equal(confirmation.checked,false);
});

test('in-flight report submission freezes photo and category and restores their prior state', () => {
  const photo={disabled:false},category={disabled:false},button={disabled:true};
  const release=freezeReportInputs({elements:[photo,category,button]});
  assert.equal(photo.disabled,true);
  assert.equal(category.disabled,true);
  release();
  assert.equal(photo.disabled,false);
  assert.equal(category.disabled,false);
  assert.equal(button.disabled,true);
});
