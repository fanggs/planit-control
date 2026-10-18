const finite = value => typeof value === 'number' && Number.isFinite(value);

// The current API has no separate heat-index reason field. Temperature only
// supports these conservative labels; never turn a null index into "safe".
export function heatIndexDisplay(weather) {
  if (finite(weather?.heat_index_f)) return `Heat index ${weather.heat_index_f} °F`;
  const air = weather?.temperature_f;
  if (finite(air) && air < 80) return `Heat index only applies above 80 °F · it’s ${air} °F now`;
  if (finite(air) && air > 112) return `Too hot for the heat index formula (above 112 °F) · it’s ${air} °F. Treat as extreme heat.`;
  return `Unavailable${finite(air) ? ` · air temperature ${air} °F` : ''}`;
}
