import {config} from './crew-config.js';
// Sample access is explicit and never grants an Auth0 role or API permission.
if (config.dataMode === 'mock') document.getElementById('explore-demo').hidden = false;
else document.getElementById('welcome-demo-link').hidden = true;
