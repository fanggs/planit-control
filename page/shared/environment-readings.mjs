const finite = value => typeof value === 'number' && Number.isFinite(value);

// The current API has no separate heat-index reason field. Temperature only
// supports these conservative labels; never turn a null index into "safe".
export function heatIndexDisplay(weather) {
  if (finite(weather?.heat_index_f)) return `Heat index ${weather.heat_index_f} °F`;
  const air = weather?.temperature_f;
  if (finite(air) && air < 80) return `Not calculated below 80 °F · air temperature ${air} °F`;
  if (finite(air) && air > 112) return `Outside supported range above 112 °F · air temperature ${air} °F`;
  return `Unavailable${finite(air) ? ` · air temperature ${air} °F` : ''}`;
}
