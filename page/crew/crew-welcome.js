import {config} from './crew-config.js';
import {supervisorDashboardURL} from './crew-routing.js';
// The header always opens the canonical supervisor dashboard. Demo cards keep
// Isaiah's sample preview so offline walkthroughs remain possible.
document.querySelector('.welcome-supervisor-link').href=supervisorDashboardURL(location.href).href;
// Sample access is explicit and never grants an Auth0 role or API permission.
if (config.dataMode === 'mock') {
  document.getElementById('explore-demo').hidden = false;
  document.getElementById('workflow-preview-note').hidden = false;
  for(const link of document.querySelectorAll('.welcome-demo-options a[href="crew-supervisor.html"]'))link.href='crew-supervisor.html?demo=1';
}
else document.getElementById('welcome-demo-link').hidden = true;
