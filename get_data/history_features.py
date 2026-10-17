"""Reproducible 24-hour feature windows shared by history and future inference."""
from datetime import timedelta
import copy
import math

from get_data.weather_values import VARIABLE_UNITS,heat_index_f,optional_number,parse_hourly

FEATURES = ('temperature_max_f','temperature_min_f','relative_humidity_mean_pct',
            'relative_humidity_min_pct','wind_max_mph','wind_gust_max_mph',
            'precip_max_1h_in','precip_total_24h_in','soil_moisture_mean_m3_m3',
            'heat_index_max_f','month_sin','month_cos')


def historical_series(payload,site):
    """Quarantine invalid historical cells as null; preserve the original source.

    Live polling remains strict in weather_values.py. One bad historical hour
    should not discard an otherwise usable year, nor be silently clipped to zero.
    """
    normalized=copy.deepcopy(payload);quarantine=[]
    for variable in VARIABLE_UNITS:
        values=normalized.get('hourly',{}).get(variable)
        if not isinstance(values,list): continue
        for i,value in enumerate(values):
            limits={} if variable=='temperature_2m' else {'minimum':0}
            if variable=='relative_humidity_2m':limits['maximum']=100
            if variable=='soil_moisture_0_to_7cm':limits['maximum']=1
            try:optional_number(value,**limits)
            except ValueError:
                quarantine.append({'variable':variable,'index':i,'source_value_repr':repr(value)})
                values[i]=None
    return parse_hourly(normalized,site),quarantine


def window_features(series,cutoff):
    """Exactly (cutoff, cutoff+24h], matching hourly accumulation end times."""
    stamps=[cutoff+timedelta(hours=i) for i in range(1,25)]
    if any(stamp not in series for stamp in stamps): raise ValueError('Incomplete 24-hour feature window')
    values=[series[stamp] for stamp in stamps]
    def complete(variable):
        numbers=[row[variable] for row in values]
        return numbers if all(n is not None for n in numbers) else None
    t=complete('temperature_2m'); rh=complete('relative_humidity_2m')
    wind=complete('wind_speed_10m'); gust=complete('wind_gusts_10m')
    rain=complete('precipitation');soil=complete('soil_moisture_0_to_7cm')
    heat=[heat_index_f(row['temperature_2m']*9/5+32 if row['temperature_2m'] is not None else None,
                       row['relative_humidity_2m']) for row in values]
    valid_heat=[value for value in heat if value is not None]
    # Heat-index maximum is only eligible when its underlying inputs are complete.
    heat_max=max(valid_heat) if t is not None and rh is not None and valid_heat else None
    angle=2*math.pi*((cutoff+timedelta(hours=12)).month-1)/12
    result={'temperature_max_f':max(t)*9/5+32 if t is not None else None,
            'temperature_min_f':min(t)*9/5+32 if t is not None else None,
            'relative_humidity_mean_pct':math.fsum(rh)/24 if rh is not None else None,
            'relative_humidity_min_pct':min(rh) if rh is not None else None,
            'wind_max_mph':max(wind)/1.609344 if wind is not None else None,
            'wind_gust_max_mph':max(gust)/1.609344 if gust is not None else None,
            'precip_max_1h_in':max(rain)/25.4 if rain is not None else None,
            'precip_total_24h_in':math.fsum(rain)/25.4 if rain is not None else None,
            'soil_moisture_mean_m3_m3':math.fsum(soil)/24 if soil is not None else None,
            'heat_index_max_f':heat_max,'month_sin':math.sin(angle),'month_cos':math.cos(angle)}
    if set(result)!=set(FEATURES): raise ValueError('Feature schema changed without documentation')
    return result
