/* Visual update
   Why: Category icons make scanning easier; decorative contour lines give PlanIT
   its own identity without adding controls, data dependencies or map claims. */
const paths = {
  weather:'<path d="M5 16h12a4 4 0 0 0 0-8h-.6A6 6 0 0 0 5 9a3.5 3.5 0 0 0 0 7Z"/><path d="M7 20h6m3 0h2"/>',
  heat:'<path d="M9 14.5V5a3 3 0 0 1 6 0v9.5a5 5 0 1 1-6 0Z"/><path d="M12 7v10m6-9h3m-3 4h2"/>',
  lightning:'<path d="m13 2-8 12h6l-1 8 9-13h-6l1-7Z"/>',
  flood:'<path d="M3 12c3-4 5 4 9 0s6 4 9 0M3 18c3-4 5 4 9 0s6 4 9 0"/><path d="m8 8 4-5 4 5"/>',
  wildfire:'<path d="M12 2c1 6-6 7-6 13a6 6 0 0 0 12 0c0-3-1.5-5-3-6 0 3-2 4-2 4s2-5-1-11Z"/>',
  soil:'<path d="m3 8 9-5 9 5-9 5-9-5Zm0 5 9 5 9-5M3 18l9 5 9-5"/>',
  wildlife:'<ellipse cx="7" cy="7" rx="2" ry="3"/><ellipse cx="17" cy="7" rx="2" ry="3"/><ellipse cx="3" cy="12" rx="1.5" ry="2"/><ellipse cx="21" cy="12" rx="1.5" ry="2"/><path d="M7 20c-3-2 0-5 2-7 2-2 4-2 6 0 2 2 5 5 2 7-2 1-3-1-5-1s-3 2-5 1Z"/>',
  site:'<path d="M12 22s8-7 8-13A8 8 0 0 0 4 9c0 6 8 13 8 13Z"/><circle cx="12" cy="9" r="2.5"/>',
  report:'<path d="M4 7h4l2-3h4l2 3h4v14H4V7Z"/><circle cx="12" cy="13" r="4"/>',
  briefing:'<path d="M6 3h9l4 4v14H6V3Z"/><path d="M14 3v5h5M9 12h7m-7 4h7"/>',
  switch:'<path d="M4 8h16l-4-4M20 16H4l4 4"/>',
  shield:'<path d="m12 2 8 3v6c0 5-8 11-8 11S4 16 4 11V5l8-3Z"/><path d="m8 11 3 3 5-6"/>'
};
export function icon(name){return `<svg class="crew-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${paths[name]||paths.site}</svg>`;}
export function brandMark(){return '<span class="crew-brand-mark" aria-hidden="true"><svg viewBox="0 0 32 32" fill="none"><path d="m7 21 8-13 10 1-8 13-10-1Z" fill="#d6e8a2"/><path d="M10 24V10h8a5 5 0 0 1 0 10h-4" stroke="white" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"/></svg></span>';}
export function contourArt(){return `<div class="crew-contour-art" aria-hidden="true"><svg viewBox="0 0 260 150" fill="none"><path d="M12 116c-20-55 36-107 81-93s53-38 97-16 70 82 40 115-53-1-90 9-107 44-128-15Z" fill="#d6e8a2" fill-opacity=".55"/><g stroke="#609582" stroke-width="1.2"><path d="M14 114C-7 62 51 9 94 25s58-33 95-14 66 78 39 109-50-1-88 10-106 39-126-16Z"/><path d="M32 108C17 66 58 26 98 40s50-28 82-11 54 60 32 86-42-6-76 4-88 32-104-11Z"/><path d="M51 104c-9-32 20-59 51-49s41-22 68-10 42 43 24 64-35-10-64-2-68 25-79-3Z"/><path d="M72 100c-7-23 17-39 35-30s34-17 53-8 30 27 16 42-27-13-49-6-47 20-55 2Z"/></g><path d="m127 42 5 13-5 13-5-13 5-13Z" fill="#173f32"/><circle cx="127" cy="55" r="23" stroke="#173f32" stroke-opacity=".16" stroke-dasharray="3 5"/><circle cx="209" cy="39" r="7" fill="#e2ac5c"/><circle cx="49" cy="124" r="5" fill="#5a8f9f"/></svg></div>`;}
