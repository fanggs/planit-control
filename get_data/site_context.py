"""Wildlife sightings as dated evidence, never encounter probabilities."""
import argparse
from datetime import datetime,timezone
import json
import math
from pathlib import Path
from get_data.forecast_study import ROOT,write,digest
from db.validation import validate_provenance


def distance_km(a,b):
    lat1,lat2=map(math.radians,(a['latitude'],b['latitude']))
    dlat=lat2-lat1;dlon=math.radians(b['longitude']-a['longitude'])
    return 6371*2*math.asin(min(1,math.sqrt(math.sin(dlat/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2)))


def wildlife_context(sites,observations,radius_km=25):
    if not 0<radius_km<=100:raise ValueError('Context radius must be explicit and bounded')
    for row in observations:validate_provenance(row)
    result=[]
    for site in sites:
        matches=[]
        for row in observations:
            distance=distance_km(site,row)
            if distance<=radius_km:matches.append(dict(row,distance_km=distance))
        matches.sort(key=lambda r:(r['distance_km'],r['occurrence_id']))
        result.append({'site_id':site['site_id'],'status':'recorded_sightings' if matches else 'no_records_in_sample',
                       'radius_km':radius_km,'radius_meaning':'Map context filter, not a safety boundary',
                       'sample_match_count':len(matches),'sightings':matches[:20],
                       'encounter_probability':None,'numeric_score_contribution':None,
                       'limitations':'Presence-only capped sample; no records does not mean absence. Dates and coordinate uncertainty retained.'})
    return result


def build():
    m=json.loads((ROOT/'data/raw/history/latest.json').read_text())
    if m['status']!='ok':raise ValueError('Verified wildlife build required')
    path=ROOT/m['output_directory']/'wildlife-observations.json'
    if digest(path)!=m['artifact_checksums'][path.name]:raise ValueError('Wildlife checksum mismatch')
    sites=json.loads((ROOT/'get_data/generated/sites.json').read_text());obs=json.loads(path.read_text())
    result={'built_at':datetime.now(timezone.utc).isoformat(),'source_sha256':digest(path),'sites':wildlife_context(sites,obs)}
    write(ROOT/'get_data/generated/wildlife-site-context.json',result);return result


if __name__=='__main__':
    result=build();print('Wildlife context prepared for',len(result['sites']),'sites; no invented probability or weights.')


def for_site(site_id):
    """Small, precomputed public evidence layer for the site's API/map panel."""
    path=ROOT/'get_data/generated/wildlife-site-context.json'
    if not path.exists():return {'site_id':site_id,'status':'unavailable','sightings':[],'encounter_probability':None}
    document=json.loads(path.read_text())
    match=next((r for r in document['sites'] if r['site_id']==site_id),None)
    if match is None:return {'site_id':site_id,'status':'unavailable','sightings':[],'encounter_probability':None}
    return dict(match,context_built_at=document['built_at'],source_sha256=document['source_sha256'])
