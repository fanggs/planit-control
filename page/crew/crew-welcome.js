import {config} from './crew-config.js';
// Sample access is explicit and never grants an Auth0 role or API permission.
if (config.dataMode === 'mock') {
  document.getElementById('explore-demo').hidden = false;
  document.getElementById('workflow-preview-note').hidden = false;
  for(const link of document.querySelectorAll('a[href="crew-supervisor.html"]'))link.href='crew-supervisor.html?demo=1';
}
else document.getElementById('welcome-demo-link').hidden = true;
