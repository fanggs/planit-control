"""GBIF presence records, original licensing and explicit location/date quality."""
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re

import requests

from db.validation import finite_number, validate_provenance
from get_data.download import download, session
from get_data.weather_values import iso

TAXA = ("Alligator mississippiensis", "Agkistrodon piscivorus", "Agkistrodon conanti",
        "Agkistrodon contortrix", "Crotalus", "Sistrurus")
GBIF = "https://api.gbif.org/v1"
WILDLIFE_COLUMNS = ("occurrence_id","species","observed_at","latitude","longitude",
                    "source_name","source_url","retrieved_at")


def normalize_occurrence(record, receipt):
    if record.get('occurrenceStatus')!='PRESENT' or record.get('countryCode')!='US':
        raise ValueError('not_a_us_presence_record')
    if record.get('basisOfRecord') not in ('HUMAN_OBSERVATION','MACHINE_OBSERVATION'):
        raise ValueError('not_an_observation')
    lat=finite_number(record.get('decimalLatitude'));lon=finite_number(record.get('decimalLongitude'))
    if not (24<=lat<=50 and -125<=lon<=-66): raise ValueError('outside_contiguous_us_scope')
    uncertainty=record.get('coordinateUncertaintyInMeters')
    if uncertainty is not None:
        finite_number(uncertainty)
        if uncertainty<0 or uncertainty>10_000: raise ValueError('location_uncertainty_over_10km_or_invalid')
    raw=record.get('eventDate','')
    if not re.match(r'^\d{4}-\d{2}-\d{2}(T|$)',raw) or '/' in raw:
        raise ValueError('day_precision_date_required')
    observed=datetime.fromisoformat(raw.replace('Z','+00:00'))
    if not 2020<=observed.year<=2025: raise ValueError('outside_2020_2025_window')
    original_day=observed.date().isoformat()
    if observed.tzinfo is None:
        # Explicit date anchor, not a claimed measurement time. GBIF's supplied
        # calendar date/month remains in quality metadata for ecological use.
        normalized=datetime.combine(observed.date(),datetime.min.time(),timezone.utc)
        precision='calendar_day_utc_anchor_not_actual_time'
    else:
        normalized=observed.astimezone(timezone.utc);precision='source_datetime_with_offset'
    occurrence_id=record.get('key')
    if type(occurrence_id) is not int or occurrence_id<=0: raise ValueError('invalid_occurrence_id')
    species=record.get('species') or record.get('scientificName')
    if not species or not record.get('datasetKey') or not record.get('license'):
        raise ValueError('missing_taxon_dataset_or_license')
    row={'occurrence_id':occurrence_id,'species':species,'observed_at':iso(normalized),
         'latitude':lat,'longitude':lon,'source_name':'GBIF occurrence / '+record['datasetKey']+
             (' (calendar-day anchor)' if observed.tzinfo is None else ''),
         'source_url':f'https://www.gbif.org/occurrence/{occurrence_id}','retrieved_at':receipt['retrieved_at'],
         'event_date_raw':raw,'observed_calendar_date':original_day,'date_precision':precision,
         'coordinate_uncertainty_m':uncertainty,'uncertainty_reported':uncertainty is not None,
         'basis_of_record':record['basisOfRecord'],'dataset_key':record['datasetKey'],
         'license':record['license'],'query_source_url':receipt['url'],
         'sampling_protocol':record.get('samplingProtocol'),
         'occurrence_record_id':record.get('occurrenceID')}
    validate_provenance(row)
    return row


def collect_wildlife(raw_dir, *, per_taxon=600, refresh=False):
    if not 1<=per_taxon<=3000: raise ValueError('Choose 1–3000 GBIF records per taxon')
    raw_dir=Path(raw_dir); rows={}; audit=[]; rejected=Counter(); receipts=[]
    with session() as client:
        for name in TAXA:
            slug=name.lower().replace(' ','-')
            rank='GENUS' if ' ' not in name else 'SPECIES'
            match_url=requests.Request('GET',GBIF+'/species/match',params={'name':name,'strict':'true',
                'rank':rank,'kingdom':'Animalia','family':'Alligatoridae' if name.startswith('Alligator ') else 'Viperidae'}).prepare().url
            path=raw_dir/(slug+'-taxonomy-'+rank.lower()+'.json'); receipt=download(client,match_url,path,refresh=refresh)
            match=json.loads(path.read_text());receipts.append(receipt)
            key=match.get('acceptedUsageKey') or match.get('usageKey')
            allowed=match.get('matchType')=='EXACT' or (rank=='GENUS' and match.get('matchType')=='HIGHERRANK')
            if not allowed or match.get('rank')!=rank or match.get('canonicalName')!=name or not key:
                raise ValueError(f'GBIF did not resolve the requested taxon exactly: {name}')
            fetched,accepted,offset=0,0,0; total=None
            while fetched<per_taxon:
                limit=min(300,per_taxon-fetched)
                params={'taxonKey':key,'country':'US','eventDate':'2020-01-01,2025-12-31',
                        'hasCoordinate':'true','hasGeospatialIssue':'false','occurrenceStatus':'PRESENT',
                        'limit':limit,'offset':offset}
                url=requests.Request('GET',GBIF+'/occurrence/search',params=params).prepare().url
                page=raw_dir/f'{slug}-{offset:05d}-{limit:03d}.json'
                receipt=download(client,url,page,refresh=refresh,max_bytes=10_000_000)
                payload=json.loads(page.read_text());receipts.append(receipt)
                records=payload.get('results')
                if not isinstance(records,list): raise ValueError('GBIF occurrence response has no results array')
                total=payload.get('count');fetched+=len(records);offset+=len(records)
                for record in records:
                    try:
                        row=normalize_occurrence(record,receipt)
                    except (ValueError,TypeError) as exc:
                        rejected[str(exc)]+=1;continue
                    if row['occurrence_id'] not in rows:
                        rows[row['occurrence_id']]=row;accepted+=1
                if payload.get('endOfRecords') or not records: break
            audit.append({'taxon':name,'taxon_key':key,'api_reported_count':total,'fetched':fetched,
                          'accepted_unique':accepted,'capped_subset':bool(total is not None and total>fetched)})
    if not rows: raise ValueError('No usable GBIF observations; no wildlife dataset was fabricated')
    return sorted(rows.values(),key=lambda r:r['occurrence_id']), {
        'taxa':audit,'accepted_records':len(rows),'rejections':dict(rejected),'sources':receipts,
        'date_anchoring':'Naive/date-only source values become explicitly marked UTC calendar-day anchors, not exact observation times.',
        'limitations':['Presence-only API subsets do not provide absence labels or encounter/injury probabilities.',
                       'API ordering and record caps are not representative random sampling or survey effort.',
                       'Unknown uncertainty is retained as unknown, never replaced with zero.',
                       'The 10-km uncertainty filter is a declared data-quality choice, not a safety distance.',
                       'Species list follows the current contract; Turkey Point crocodile coverage remains a team question.']}
