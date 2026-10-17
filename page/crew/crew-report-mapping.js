/* Frontend part 5
Commit: feat(crew): add photo reporting and next-day briefing flows
Why: The team's strict report schema forbids extra fields. Build an explicit
allowlist after the photo upload rather than sending UI state or user identity.
*/
const types=new Map([
  ['wildlife','wildlife'],['flooding / standing water','flooding'],
  ['soil / access','soil_saturation'],['weather','other'],['heat','heat'],
  ['lightning','lightning'],['wildfire / smoke','wildfire'],['other','other']
]);
// Use in the custom adapter after DeepSpace returns its stored photo key.
// request_id belongs in a backend-agreed idempotency header, not this JSON body.
export function createHazardReportPayload(report,photoKey=null){
  const id=String(report.site_id);
  if(!/^[1-9]\d*$/.test(id)||!Number.isSafeInteger(Number(id)))throw new Error('A positive numeric EIA plant ID is required.');
  const hazard_type=types.get(String(report.category).trim().toLowerCase());
  if(!hazard_type)throw new Error('Choose a supported hazard type.');
  if(!['low','medium','high'].includes(report.severity))throw new Error('Choose a report severity.');
  const description=String(report.description??'').trim();
  if(!description||description.length>2000||description.includes('\0'))throw new Error('Description must be 1–2000 characters without NUL.');
  if(!Number.isFinite(report.latitude)||Math.abs(report.latitude)>90||!Number.isFinite(report.longitude)||Math.abs(report.longitude)>180)throw new Error('Valid latitude and longitude are required.');
  if(photoKey!==null&&(typeof photoKey!=='string'||photoKey.length<1||photoKey.length>1024))throw new Error('The upload must return a valid stored photo key.');
  // Follow-up commit: fix(crew): match current photo storage key validation.
  // A key is an opaque storage identity. Reject URLs/control characters and do
  // not trim or rewrite the exact key returned by the upload service.
  if(photoKey!==null&&(photoKey!==photoKey.trim()||/[\u0000-\u001f\u007f]/.test(photoKey)||photoKey.startsWith('//')||/^[A-Za-z][A-Za-z0-9+.-]*:/.test(photoKey)))throw new Error('Use the exact storage key, not a URL, whitespace or control characters.');
  return {site_id:Number(id),hazard_type,severity:report.severity,description,latitude:report.latitude,longitude:report.longitude,photo_key:photoKey};
}
