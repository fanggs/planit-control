// Legacy crew-owned entry now opens Aryan's independent supervisor application.
// Its own configuration controls sample/live mode and Auth0 role validation.
import {workspaceURL} from './crew-routing.js';
location.replace(workspaceURL('supervisor',import.meta.url).href);
