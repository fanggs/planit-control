"""One feature definition for historical and live fixed-lead GFS forecasts."""
from datetime import timedelta
import math

from db.validation import finite_number
from get_data.weather_values import epoch, heat_index_f

SCHEMA = 'gfs-fixed-lead48-v1'
ENDPOINT = 'https://previous-runs-api.open-meteo.com/v1/forecast'
MODEL = 'gfs_global'
VARIABLES = {'temperature_2m': '°C', 'relative_humidity_2m': '%',
             'precipitation': 'mm', 'wind_speed_10m': 'km/h'}
FEATURES = ('temperature_max_f', 'temperature_min_f', 'humidity_mean_pct', 'humidity_min_pct',
            'wind_max_mph', 'rain_max_1h_in', 'rain_total_24h_in', 'heat_index_max_f',
            'antecedent_forecast_rain_24h_in', 'antecedent_forecast_rain_72h_in',
            'antecedent_forecast_rain_168h_in', 'latitude', 'longitude', 'elevation_m', 'month_sin', 'month_cos', 'hour_sin', 'hour_cos')
OPTIONAL = {'heat_index_max_f'}


def parse(payload, site):
    if payload.get('error') or payload.get('utc_offset_seconds') != 0:
        raise ValueError('Expected successful UTC forecast response')
    lat, lon = finite_number(payload['latitude']), finite_number(payload['longitude'])
    delta = ((lat-site['latitude'])**2 + ((lon-site['longitude'])*math.cos(math.radians(lat)))**2)**.5*111.2
    if delta > 50:
        raise ValueError('Forecast grid does not match requested site')
    hourly = payload['hourly']; units = payload['hourly_units']
    if units.get('time') != 'unixtime':
        raise ValueError('Expected UTC epoch times')
    times = [epoch(t) for t in hourly['time']]
    if not times or any(b-a != timedelta(hours=1) for a,b in zip(times,times[1:])):
        raise ValueError('Forecast hours must be complete, ordered and unique')
    for name, unit in VARIABLES.items():
        key = name + '_previous_day2'
        if units.get(key) != unit or len(hourly.get(key, [])) != len(times):
            raise ValueError('Forecast variable, lead offset or units changed')
    result = {}
    for i,t in enumerate(times):
        row = {}
        for name in VARIABLES:
            v = hourly[name+'_previous_day2'][i]
            if v is not None:
                finite_number(v)
                if name != 'temperature_2m' and v < 0 or name == 'relative_humidity_2m' and v > 100:
                    raise ValueError('Invalid forecast measurement')
            row[name] = v
        result[t] = row
    finite_number(payload['elevation'])
    return result


def features(series, cutoff, site, elevation):
    """(cutoff, cutoff+24h] forecast endpoints, plus preceding forecast rain.

    previous_day2 is a fixed 48h lead per valid hour: a composite of earlier
    runs, NOT one run issued at the decision cutoff. Even the final endpoint
    was nominally forecast 24h before cutoff. Antecedent rain is also forecast
    output, not a claim that all of that rain actually fell.
    """
    def window(name, hours, future):
        stamps = [cutoff+timedelta(hours=i) for i in range(1, hours+1)] if future else [cutoff-timedelta(hours=i) for i in range(hours)]
        values = [series.get(t, {}).get(name) for t in stamps]
        if any(v is None for v in values):
            raise ValueError(f'Incomplete {hours}-hour {name} window')
        return values
    t = window('temperature_2m',24,True); rh = window('relative_humidity_2m',24,True)
    rain = window('precipitation',24,True); wind = window('wind_speed_10m',24,True)
    heat = [h for c,r in zip(t,rh) if (h:=heat_index_f(c*9/5+32,r)) is not None]
    angle = 2*math.pi*(cutoff.month-1)/12
    values = [max(t)*9/5+32,min(t)*9/5+32,sum(rh)/24,min(rh),max(wind)/1.609344,
              max(rain)/25.4,sum(rain)/25.4,max(heat) if heat else None,
              *[sum(window('precipitation',h,False))/25.4 for h in (24,72,168)],
              site['latitude'],site['longitude'],elevation,math.sin(angle),math.cos(angle),
              math.sin(2*math.pi*cutoff.hour/24),math.cos(2*math.pi*cutoff.hour/24)]
    return dict(zip(FEATURES, values))
