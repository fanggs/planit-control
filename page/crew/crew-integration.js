/* Frontend part 2
Commit: feat(crew): add authenticated backend connection adapters
Why: Keep authentication and configurable network contracts separate from the UI; a failed live request must never become a synthetic success.
*/
// Optional custom backend adapter. Imported before service calls.
// Choose config.transport = 'custom', then assign window.PlanITCrewAPI here.
// Implement the methods described in ../BACKEND-CONNECTION.md using the team's
// agreed API and DeepSpace SDK. Never place server secrets in frontend files.
