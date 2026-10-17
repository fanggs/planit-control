/* Frontend part 5
Commit: feat(crew): add photo reporting and next-day briefing flows
Why: The team's strict report schema forbids extra fields. Build an explicit
allowlist after the photo upload rather than sending UI state or user identity.
*/
const types=new Map([
  ['wildlife','wildlife'],['flooding / standing water','flooding'],
  ['soil / access','soil_saturation'],['weather','other'],['heat','heat'],
  ['lightning','lightning'],['wildfire / smoke','wildfire'],['other','other'],
  ['flooding','flooding'],['soil_saturation','soil_saturation'],['wildfire','wildfire']
]);
// POST /photos returns this private server key. DeepSpace does not store photos.
// request_id belongs in a backend-agreed idempotency header, not this JSON body.
export const MAX_PHOTO_BYTES=5*1024*1024;
export function validateReportPhoto(photo){
  if(photo==null)return;
  if(!(photo instanceof Blob)||!['image/jpeg','image/png'].includes(photo.type)||photo.size===0||photo.size>MAX_PHOTO_BYTES)throw new Error('Choose a JPEG or PNG photo up to 5 MB.');
}
export function createHazardReportPayload(report,photoKey=null){
  const id=String(report.site_id);
  if(!/^[1-9]\d*$/.test(id)||!Number.isSafeInteger(Number(id)))throw new Error('A positive numeric EIA plant ID is required.');
  const hazard_type=types.get(String(report.hazard_type??report.category).trim().toLowerCase());
  if(!hazard_type)throw new Error('Choose a supported hazard type.');
  if(!['low','medium','high'].includes(report.severity))throw new Error('Choose a report severity.');
  const description=typeof report.description==='string'?report.description.trim():'';
  if(!description||description.length>2000||description.includes('\0'))throw new Error('Description must be 1–2000 characters without NUL.');
  const latitude=report.latitude??null,longitude=report.longitude??null;
  if((latitude===null)!==(longitude===null))throw new Error('Provide both latitude and longitude, or neither.');
  if(latitude!==null&&(!Number.isFinite(latitude)||Math.abs(latitude)>90||!Number.isFinite(longitude)||Math.abs(longitude)>180))throw new Error('Valid latitude and longitude are required.');
  if(photoKey!==null&&(typeof photoKey!=='string'||photoKey.length<1||photoKey.length>1024))throw new Error('The upload must return a valid stored photo key.');
  // Follow-up commit: fix(crew): match current photo storage key validation.
  // A key is an opaque storage identity. Reject URLs/control characters and do
  // not trim or rewrite the exact key returned by the upload service.
  if(photoKey!==null&&(photoKey!==photoKey.trim()||/[\u0000-\u001f\u007f]/.test(photoKey)||photoKey.startsWith('//')||/^[A-Za-z][A-Za-z0-9+.-]*:/.test(photoKey)))throw new Error('Use the exact storage key, not a URL, whitespace or control characters.');
  return {site_id:Number(id),hazard_type,severity:report.severity,description,latitude,longitude,photo_key:photoKey};
}
