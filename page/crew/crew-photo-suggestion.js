// Gemini suggests a category; a crew member always makes the final choice.
const labels = Object.freeze({
  heat: 'Heat', lightning: 'Lightning', flooding: 'Flooding / standing water',
  wildfire: 'Wildfire / smoke', soil_saturation: 'Soil / access',
  wildlife: 'Wildlife', other: 'Other'
});

export function categoryForSuggestion(suggestion) {
  if (!suggestion || typeof suggestion.hazard_type !== 'string') return null;
  return Object.hasOwn(labels, suggestion.hazard_type) ? labels[suggestion.hazard_type] : null;
}

export function mayApplySuggestion({samePhoto, currentForm, userChoseCategory}) {
  return samePhoto && currentForm && !userChoseCategory;
}

export function applySuggestedCategory(suggestion, categoryField, confirmationField) {
  const label = categoryForSuggestion(suggestion);
  if (!label) return null;
  categoryField.value = label;
  // Even if the box was checked before Gemini finished, a new suggestion
  // needs a fresh human confirmation.
  confirmationField.checked = false;
  return label;
}

export function freezeReportInputs(form) {
  const controls = Array.from(form.elements);
  const previous = controls.map(control => control.disabled);
  controls.forEach(control => { control.disabled = true; });
  return () => controls.forEach((control, index) => {
    if (control.isConnected !== false) control.disabled = previous[index];
  });
}
