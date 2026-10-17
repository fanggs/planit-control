"""Synthetic fixtures check historical geography, timestamps, labels and leakage."""
import csv
from datetime import date,datetime,timedelta,timezone
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from get_data.history import build_history,days,make_example
from get_data.history_features import historical_series,window_features
from get_data.noaa import discover_years,label_window,load_events,noaa_time,read_crosswalk
from get_data.wildlife import normalize_occurrence

UTC=timezone.utc
CUTOFF=datetime(2025,7,1,12,tzinfo=UTC)
SITE={'site_id':621,'state':'FL','county_fips':'12086','hazard_region':'florida_gulf'}
RECEIPT={'url':'https://example.org/explicitly-synthetic-test','retrieved_at':'2026-10-17T12:00:00Z'}


def event(**changes):
    return {'id':'1','site_id':621,'episode_id':99,'hazard_type':'heat',
            'starts_at':'2025-07-01T13:00:00Z','ends_at':'2025-07-02T01:00:00Z',**changes}


def series():
    return {CUTOFF+timedelta(hours=i):{'temperature_2m':30.,'relative_humidity_2m':70.,
        'wind_speed_10m':16.09344,'wind_gusts_10m':32.18688,'precipitation':1.,
        'soil_moisture_0_to_7cm':0.25} for i in range(1,25)}


class GeographyTests(unittest.TestCase):
    def test_discovery_selects_latest_noaa_revision(self):
        html=''.join(f'<a href="StormEvents_details-ftp_v1.0_d2025_c{stamp}.csv.gz">file</a>' for stamp in ('20260101','20260819'))
        self.assertTrue(discover_years(html,{2025})[2025].endswith('c20260819.csv.gz'))
        with self.assertRaises(ValueError): discover_years(html,{2024,2025})

    def test_crosswalk_keeps_multi_county_zones_and_quarantines_conflicts(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'test.dbx'
            path.write_text('FL|001|AAA|Test|FL001|A|12001|E|x|25|-80\nFL|001|AAA|Test|FL001|B|12003|E|x|25|-80\nFL|002|AAA|Test|FL099|C|12005|E|x|25|-80\n')
            audit=[];mapping=read_crosswalk(path,audit)
            self.assertEqual(mapping,{'FL001':{'12001','12003'}})
            self.assertEqual(audit[0]['reason'],'conflicting_zone_columns_quarantined')

    def test_offset_in_source_controls_utc_not_iana_dst(self):
        row={'CZ_TIMEZONE':'EST-5','BEGIN_YEARMONTH':'202507','BEGIN_DAY':'1','BEGIN_TIME':'1200'}
        self.assertEqual(noaa_time(row,'BEGIN').hour,17)
        row['CZ_TIMEZONE']='EDT-4'
        self.assertEqual(noaa_time(row,'BEGIN').hour,16)
        row['BEGIN_TIME']='2400'
        self.assertEqual(noaa_time(row,'BEGIN'),datetime(2025,7,2,4,tzinfo=UTC))
        row['BEGIN_TIME']='2460'
        with self.assertRaises(ValueError):noaa_time(row,'BEGIN')

    def test_county_and_zone_identical_digits_are_not_interchangeable(self):
        row={'EVENT_ID':'11','EPISODE_ID':'2','EVENT_TYPE':'Heat','STATE_FIPS':'12','CZ_TYPE':'Z','CZ_FIPS':'86','CZ_TIMEZONE':'EST-5',
             'BEGIN_YEARMONTH':'202507','BEGIN_DAY':'1','BEGIN_TIME':'1200','END_YEARMONTH':'202507','END_DAY':'1','END_TIME':'1800'}
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'events.csv.gz'
            with gzip.open(path,'wt',newline='') as handle:
                writer=csv.DictWriter(handle,fieldnames=list(row));writer.writeheader();writer.writerow(row)
            # A Z086 event maps through the crosswalk to a DIFFERENT county.
            found,unknown,_,_=load_events([(2025,path,RECEIPT)],[(date(2025,3,18),{'FL086':{'12001'}},'source')],[SITE])
            self.assertEqual(found,[]);self.assertEqual(unknown,[])
            found,unknown,_,_=load_events([(2025,path,RECEIPT)],[(date(2025,3,18),{},'source')],[SITE])
            self.assertEqual(found,[]);self.assertEqual(len(unknown),1)
            row['CZ_TYPE']='5'
            with gzip.open(path,'wt',newline='') as handle:
                writer=csv.DictWriter(handle,fieldnames=list(row));writer.writeheader();writer.writerow(row)
            found,unknown,audit,_=load_events([(2025,path,RECEIPT)],[],[SITE])
            self.assertEqual(found,[])
            self.assertEqual(unknown[0]['reason'],'invalid_geography_type')
            self.assertEqual(audit['invalid_geography_type_records'],1)


class LabelTests(unittest.TestCase):
    def test_known_positive_and_unknown_geography_are_preserved(self):
        unknown=[{'state':'FL',**event(site_id=999,hazard_type='wildfire')}]
        label=label_window(SITE,CUTOFF,CUTOFF+timedelta(days=1),[event()],unknown)
        self.assertEqual(label['reported_event'],1)
        self.assertEqual(label['hazard_labels']['heat'],1)
        self.assertIsNone(label['hazard_labels']['wildfire'])
        self.assertIsNone(label['hazard_labels']['soil_saturation'])
        self.assertEqual(label['episode_ids'],[99])

    def test_unresolved_event_masks_negative_not_turns_it_safe(self):
        unknown=[{'state':'FL',**event(site_id=999)}]
        label=label_window(SITE,CUTOFF,CUTOFF+timedelta(days=1),[],unknown)
        self.assertIsNone(label['reported_event'])
        self.assertEqual(label_window(SITE,CUTOFF,CUTOFF+timedelta(days=1),[],[])['reported_event'],0)

    def test_other_sites_never_create_a_positive(self):
        label=label_window(SITE,CUTOFF,CUTOFF+timedelta(days=1),[event(site_id=999)],[])
        self.assertEqual(label['reported_event'],0)

    def test_instantaneous_boundary_events_match_exact_window(self):
        for stamp,expected in (('2025-07-01T12:00:00Z',0),('2025-07-02T12:00:00Z',1)):
            result=label_window(SITE,CUTOFF,CUTOFF+timedelta(days=1),[event(starts_at=stamp,ends_at=stamp)],[])
            self.assertEqual(result['reported_event'],expected)


class FeatureTests(unittest.TestCase):
    def test_invalid_historical_soil_is_null_not_clipped_to_safe_zero(self):
        from get_data.tests.test_weather import payload,SITE as WEATHER_SITE,RUN
        source=payload(RUN)
        source['hourly']['soil_moisture_0_to_7cm'][0]=-0.001
        normalized,quarantine=historical_series(source,WEATHER_SITE)
        self.assertIsNone(normalized[RUN]['soil_moisture_0_to_7cm'])
        self.assertEqual(source['hourly']['soil_moisture_0_to_7cm'][0],-0.001)
        self.assertEqual(quarantine[0]['variable'],'soil_moisture_0_to_7cm')

    def test_units_and_nonoverlapping_rain_totals(self):
        f=window_features(series(),CUTOFF)
        self.assertEqual(f['temperature_max_f'],86)
        self.assertAlmostEqual(f['wind_max_mph'],10)
        self.assertAlmostEqual(f['wind_gust_max_mph'],20)
        self.assertAlmostEqual(f['precip_total_24h_in'],24/25.4)

    def test_missing_hours_and_values_are_not_partial_averages(self):
        data=series();data.pop(next(iter(data)))
        with self.assertRaises(ValueError):window_features(data,CUTOFF)
        data=series();data[next(iter(data))]['precipitation']=None
        self.assertIsNone(window_features(data,CUTOFF)['precip_total_24h_in'])

    def test_forecast_availability_assumption_is_not_claimed_as_verified(self):
        row=make_example(SITE,CUTOFF.date(),'forecast',series(),'test',RECEIPT,[],[])
        self.assertFalse(row['historical_publication_time_verified'])
        self.assertEqual(row['forecast_run_at'],'2025-07-01T00:00:00Z')
        self.assertNotIn('event_ids',row['features'])
        self.assertNotIn('reported_event',row['features'])

    def test_failed_build_replaces_old_success_status(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'latest.json').write_text('{"status":"ok"}')
            with patch('get_data.history._build_history',side_effect=ValueError('synthetic failure')):
                with self.assertRaises(ValueError):build_history([SITE],root=root)
            self.assertEqual(json.loads((root/'latest.json').read_text())['status'],'failed')


class WildlifeTests(unittest.TestCase):
    def record(self,**changes):
        return {'key':123,'occurrenceStatus':'PRESENT','countryCode':'US','basisOfRecord':'HUMAN_OBSERVATION',
                'decimalLatitude':25.4,'decimalLongitude':-80.3,'eventDate':'2025-07-01',
                'species':'Alligator mississippiensis','datasetKey':'synthetic-dataset',
                'license':'http://creativecommons.org/licenses/by/4.0/',**changes}

    def test_day_precision_and_unknown_uncertainty_remain_explicit(self):
        row=normalize_occurrence(self.record(),RECEIPT)
        self.assertIn('calendar_day',row['date_precision'])
        self.assertIsNone(row['coordinate_uncertainty_m'])
        self.assertFalse(row['uncertainty_reported'])
        self.assertIn('calendar-day anchor',row['source_name'])
        self.assertNotIn('absence',row)

    def test_offset_datetime_keeps_actual_source_offset(self):
        row=normalize_occurrence(self.record(eventDate='2025-07-01T20:00:00-04:00'),RECEIPT)
        self.assertEqual(row['observed_at'],'2025-07-02T00:00:00Z')
        self.assertEqual(row['observed_calendar_date'],'2025-07-01')

    def test_absence_uncertain_dates_and_very_imprecise_locations_are_rejected(self):
        for changes in ({'occurrenceStatus':'ABSENT'},{'eventDate':'2025-07'},{'eventDate':'2025-07-01/2025-07-31'},
                        {'coordinateUncertaintyInMeters':20000},{'license':None},{'basisOfRecord':'PRESERVED_SPECIMEN'}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                normalize_occurrence(self.record(**changes),RECEIPT)


if __name__=='__main__':unittest.main()
