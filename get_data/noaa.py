"""NOAA Storm Events: dated county/zone joins and explicit UTC conversion."""
from collections import Counter, defaultdict
import csv
from datetime import date, datetime, timedelta, timezone
import gzip
import re
from urllib.parse import urljoin

from get_data.eia import Links
from get_data.weather_values import iso

INDEX = "https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/"
CROSSWALKS = (
    (date(2025,3,18), "https://www.weather.gov/source/gis/Shapefiles/County/bp18mr25.dbx"),
    (date(2026,4,16), "https://www.weather.gov/source/gis/Shapefiles/County/bp16ap26.dbx"),
)
EVENT_HAZARDS = {
    "Heat":"heat", "Excessive Heat":"heat", "Lightning":"lightning",
    "Flood":"flooding", "Flash Flood":"flooding", "Coastal Flood":"flooding",
    "Lakeshore Flood":"flooding", "Storm Surge/Tide":"flooding", "Wildfire":"wildfire",
    "Thunderstorm Wind":"other", "High Wind":"other", "Strong Wind":"other",
}
SUPPORTED_HAZARDS = tuple(sorted(set(EVENT_HAZARDS.values())))


def discover_years(html, years):
    links=Links(); links.feed(html)
    result={}
    for link in links.links:
        match=re.fullmatch(r"StormEvents_details-ftp_v1\.0_d(\d{4})_c(\d{8})\.csv\.gz", link.rsplit('/',1)[-1])
        if match and int(match[1]) in years and urljoin(INDEX,link).startswith(INDEX):
            year=int(match[1]); candidate=(match[2],urljoin(INDEX,link))
            if year not in result or candidate>result[year]: result[year]=candidate
    if set(result)!=set(years): raise ValueError("NOAA annual files are missing")
    return {year:result[year][1] for year in sorted(result)}


def read_crosswalk(path, audit=None):
    mapping=defaultdict(set);blocked=set()
    with open(path,encoding="utf-8-sig",newline="") as handle:
        for parts in csv.reader(handle,delimiter='|'):
            if not parts: continue
            if len(parts)!=11: raise ValueError("NWS crosswalk column count changed")
            state,zone,_,_,state_zone,_,fips,*_= (p.strip() for p in parts)
            if not re.fullmatch(r"[A-Z]{2}",state) or not re.fullmatch(r"\d{3}",zone) or not re.fullmatch(r"\d{5}",fips):
                raise ValueError("Invalid NWS county/zone mapping")
            if state_zone!=state+zone:
                blocked.update((state+zone,state_zone))
                if audit is not None: audit.append({'source':str(path),'zone_field':state+zone,'state_zone_field':state_zone,'county_fips':fips,'reason':'conflicting_zone_columns_quarantined'})
                continue
            mapping[state_zone].add(fips)
    for code in blocked: mapping.pop(code,None)
    if not mapping: raise ValueError("NWS crosswalk is empty")
    return dict(mapping)


def noaa_time(row,prefix):
    """Honor the offset in CZ_TIMEZONE, including explicit EDT/CDT records.

    Never apply an IANA daylight-saving adjustment to these already-offset times.
    """
    code=row['CZ_TIMEZONE'].strip()
    match=re.fullmatch(r"[A-Z]+([+-]\d{1,2})",code)
    if not match: raise ValueError(f"Unsupported NOAA time zone: {code}")
    offset=int(match[1])
    if not -12<=offset<=14: raise ValueError("Invalid NOAA UTC offset")
    ym=int(row[prefix+'_YEARMONTH']); day=int(row[prefix+'_DAY'])
    hhmm=int(row[prefix+'_TIME']); hour,minute=divmod(hhmm,100)
    if hour<0 or hour>24 or minute>59 or (hour==24 and minute): raise ValueError("Invalid NOAA HHMM time")
    local=datetime(ym//100,ym%100,day,tzinfo=timezone(timedelta(hours=offset)))+timedelta(hours=hour,minutes=minute)
    return local.astimezone(timezone.utc)


def overlaps(event,start,end):
    a=datetime.fromisoformat(event['starts_at'].replace('Z','+00:00'))
    b=datetime.fromisoformat(event['ends_at'].replace('Z','+00:00'))
    return start<a<=end if a==b else a<=end and b>start


def load_events(annual_sources, crosswalks, sites):
    """Return per-site county-context events, unresolved geography and an audit.

    Public forecast zones intersect counties; a matched report is county context,
    not proof that an event occurred at a particular plant or in its parcel.
    """
    state_by_fips={s['county_fips'][:2]:s['state'] for s in sites}
    sites_by_county=defaultdict(list)
    for site in sites: sites_by_county[site['county_fips']].append(site['site_id'])
    events,unresolved,counts=[],[],Counter(); seen=set(); coverage={}
    required={'EVENT_ID','EPISODE_ID','EVENT_TYPE','STATE_FIPS','CZ_TYPE','CZ_FIPS','CZ_TIMEZONE',
              'BEGIN_YEARMONTH','BEGIN_DAY','BEGIN_TIME','END_YEARMONTH','END_DAY','END_TIME'}
    for year,path,receipt in annual_sources:
        months=set()
        with gzip.open(path,'rt',encoding='utf-8-sig',newline='') as handle:
            reader=csv.DictReader(handle)
            if not required.issubset(reader.fieldnames or []): raise ValueError("NOAA event headers changed")
            for row in reader:
                counts['source_records']+=1; months.add(int(row['BEGIN_YEARMONTH'])%100)
                if row['EVENT_TYPE'] not in EVENT_HAZARDS: continue
                state_code=str(int(row['STATE_FIPS'])).zfill(2)
                if state_code not in state_by_fips: continue
                if row['CZ_TYPE']=='M': counts['marine_records_excluded']+=1; continue
                start,end=noaa_time(row,'BEGIN'),noaa_time(row,'END')
                if end<start: raise ValueError("NOAA event ends before it starts")
                event_id=int(row['EVENT_ID'])
                if event_id in seen: raise ValueError("Duplicate NOAA event ID across annual sources")
                seen.add(event_id)
                state=state_by_fips[state_code]; county_codes=set(); crosswalk_source=None
                code=str(int(row['CZ_FIPS'])).zfill(3)
                if row['CZ_TYPE']=='C': county_codes={state_code+code}
                elif row['CZ_TYPE']=='Z':
                    if any(start.date()<boundary<=end.date() for boundary,_ in CROSSWALKS):
                        counts['zone_events_spanning_geography_change']+=1
                        unresolved.append({'state':state,'hazard_type':EVENT_HAZARDS[row['EVENT_TYPE']],
                                           'starts_at':iso(start),'ends_at':iso(end),'event_id':event_id})
                        continue
                    versions=[item for item in crosswalks if item[0]<=start.date()]
                    if versions:
                        _,mapping,crosswalk_source=max(versions,key=lambda item:item[0])
                        county_codes=mapping.get(state+code,set())
                    if not county_codes:
                        counts['unresolved_zone_events']+=1
                        unresolved.append({'state':state,'hazard_type':EVENT_HAZARDS[row['EVENT_TYPE']],
                                           'starts_at':iso(start),'ends_at':iso(end),'event_id':event_id})
                        continue
                else:
                    counts['invalid_geography_type_records']+=1
                    unresolved.append({'state':state,'hazard_type':EVENT_HAZARDS[row['EVENT_TYPE']],
                        'starts_at':iso(start),'ends_at':iso(end),'event_id':event_id,
                        'reason':'invalid_geography_type','source_value':row['CZ_TYPE']})
                    continue
                counts['matched_'+row['CZ_TYPE']+'_geography_records']+=1
                for county in sorted(county_codes):
                    for site_id in sites_by_county.get(county,[]):
                        events.append({'id':str(event_id),'site_id':site_id,'hazard_type':EVENT_HAZARDS[row['EVENT_TYPE']],
                            'event_kind':'historical_storm_event','title':row['EVENT_TYPE'],'severity':None,
                            'starts_at':iso(start),'ends_at':iso(end),'source_name':'NOAA Storm Events',
                            'source_url':receipt['url'],'retrieved_at':receipt['retrieved_at'],
                            'episode_id':int(row['EPISODE_ID']) if row['EPISODE_ID'] else None,
                            'county_fips':county,'geography_kind':row['CZ_TYPE'],
                            'crosswalk_source':crosswalk_source})
        coverage[year]=sorted(months)
    counts['site_event_rows']=len(events)
    return sorted(events,key=lambda r:(r['site_id'],r['starts_at'],r['id'])),unresolved,dict(counts),coverage


def label_window(site,start,end,events,unresolved):
    applicable=[e for e in events if e['site_id']==site['site_id'] and overlaps(e,start,end)]
    unknown={e['hazard_type'] for e in unresolved if e['state']==site['state'] and overlaps(e,start,end)}
    # A target touching a known crosswalk change day is uncertain at the exact
    # effective-hour boundary. Do not manufacture a confident negative there.
    if any(start.date()<=day<=end.date() for day,_ in CROSSWALKS):
        unknown.update(SUPPORTED_HAZARDS)
    positive={e['hazard_type'] for e in applicable}
    labels={hazard:1 if hazard in positive else (None if hazard in unknown else 0) for hazard in SUPPORTED_HAZARDS}
    labels.update(soil_saturation=None,wildlife=None)
    any_report=1 if positive else (None if unknown else 0)
    return {'reported_event':any_report,'hazard_labels':labels,
            'event_ids':sorted({e['id'] for e in applicable}),
            'episode_ids':sorted({e['episode_id'] for e in applicable if e['episode_id'] is not None}),
            'unknown_hazards':sorted(unknown)}
