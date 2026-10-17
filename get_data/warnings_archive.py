"""Site-specific warning-exposure labels from IEM archived NWS geometries.

These are warning/advisory outcomes, never injury labels or measured lightning.
Final archive geometries/expiration metadata are outcomes, NOT predictors.
"""
from datetime import datetime, timezone
import io
import zipfile

import shapefile
from shapely.geometry import Point, shape

PHENOMENA = {'HT': 'heat', 'EH': 'heat', 'XH': 'heat', 'FF': 'flooding',
             'FA': 'flooding', 'FL': 'flooding', 'FW': 'wildfire',
             'SV': 'other', 'HW': 'other', 'TO': 'other'}
PAIRS = tuple((code, 'Y' if code == 'HT' else 'W') for code in PHENOMENA)
ENDPOINT = 'https://mesonet.agron.iastate.edu/cgi-bin/request/gis/watchwarn.py'


def utc(value):
    return datetime.strptime(value, '%Y%m%d%H%M').replace(tzinfo=timezone.utc)


def read_warnings(path, sites, receipt):
    """Fail invalid geometry; never silently turn an unparsed archive into zero."""
    points = [(s, Point(s['longitude'], s['latitude'])) for s in sites]
    events = []; seen = set(); records = 0
    with zipfile.ZipFile(path) as archive:
        names = [n[:-4] for n in archive.namelist() if n.endswith('.shp')]
        if len(names) != 1:
            raise ValueError('Expected one warning shapefile')
        name = names[0]
        prj = archive.read(name + '.prj').decode()
        if 'WGS_1984' not in prj or 'PROJCS' in prj:
            raise ValueError('Warning CRS must be geographic WGS84')
        reader = shapefile.Reader(**{kind: io.BytesIO(archive.read(name + '.' + kind))
                                     for kind in ('shp', 'shx', 'dbf')})
        bbox=(min(s['longitude'] for s in sites)-.002,min(s['latitude'] for s in sites)-.002,
              max(s['longitude'] for s in sites)+.002,max(s['latitude'] for s in sites)+.002)
        fields=['WFO','ISSUED','EXPIRED','PHENOM','SIG','ETN','VTEC_YR']
        for record in reader.iterShapeRecords(bbox=bbox,fields=fields):
            row = record.record.as_dict(); records += 1
            if (row['PHENOM'], row['SIG']) not in PAIRS:
                raise ValueError('Unexpected warning type; archive filter changed')
            start, end = utc(row['ISSUED']), utc(row['EXPIRED'])
            if end == start:  # no active exposure in a zero-length archive interval
                continue
            uncertain = end < start
            if uncertain:
                start,end = end,start  # mask ambiguity, never manufacture a positive/negative
            bounds=record.shape.bbox
            candidates=[(site,point) for site,point in points if bounds[0]-.002<=point.x<=bounds[2]+.002 and bounds[1]-.002<=point.y<=bounds[3]+.002]
            if not candidates:continue
            polygon = shape(record.shape.__geo_interface__)
            invalid_geometry = polygon.is_empty or not polygon.is_valid
            event_id = f"iem:{int(row['VTEC_YR'])}:{row['WFO']}:{row['PHENOM']}:{row['SIG']}:{int(row['ETN'])}"
            for site, point in candidates:
                if invalid_geometry or polygon.covers(point):
                    key = (site['site_id'], event_id, start.isoformat(), end.isoformat())
                    if key in seen:
                        continue
                    seen.add(key)
                    events.append({'site_id': site['site_id'], 'event_id': event_id,
                                   'hazard_type': PHENOMENA[row['PHENOM']], 'phenomenon': row['PHENOM'],
                                   'unknown': uncertain or invalid_geometry,
                                   'quality': 'ambiguous_interval_or_geometry' if uncertain or invalid_geometry else 'ok',
                                   'starts_at': start.isoformat(), 'ends_at': end.isoformat(),
                                   'source_name': 'IEM archived NWS warning geometry',
                                   'source_url': receipt['url'], 'retrieved_at': receipt['retrieved_at']})
    return events, records


def label(events, start, end):
    relevant = [e for e in events if datetime.fromisoformat(e['starts_at']) < end
                and datetime.fromisoformat(e['ends_at']) > start]
    unknown = any(e.get('unknown') for e in relevant)
    relevant = [e for e in relevant if not e.get('unknown')]
    return {'reported_event': 1 if relevant else (None if unknown else 0),
            'event_ids': sorted({e['event_id'] for e in relevant}),
            'episode_ids': sorted({e['event_id'] for e in relevant}),
            'hazard_labels': {h: int(any(e['hazard_type'] == h for e in relevant))
                              for h in ('heat', 'flooding', 'wildfire', 'other')}}
