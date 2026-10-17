// Keep viewed private photos in memory through routine same-site refreshes.
// Clear them on site changes/page exit, and never store bytes in browser storage.
export function createPhotoCache({createURL = blob => URL.createObjectURL(blob), revokeURL = url => URL.revokeObjectURL(url)} = {}) {
  const urls = new Map();
  function forget(key) {
    const url = urls.get(key);
    if (url) revokeURL(url);
    urls.delete(key);
  }
  return {
    get: key => urls.get(key) ?? null,
    remember(key, blob) {
      if (!urls.has(key)) urls.set(key, createURL(blob));
      return urls.get(key);
    },
    retain(keys) {
      const current = new Set(keys);
      for (const key of urls.keys()) if (!current.has(key)) forget(key);
    },
    clear() { for (const key of urls.keys()) forget(key); }
  };
}
