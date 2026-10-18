import unittest
from db.ask_query import validate_query,MAX_SELECT_DEPTH


class QueryComplexityTests(unittest.TestCase):
    def test_newest_forecast_join_and_correlated_subquery_are_supported(self):
        queries=[
            '''SELECT s.name,f.temperature_f FROM sites s JOIN weather_forecasts f
            ON f.site_id=s.site_id WHERE f.issued_at=(SELECT max(w.issued_at)
            FROM weather_forecasts w WHERE w.site_id=s.site_id)''',
            '''SELECT s.name,p.score FROM sites s JOIN
            (SELECT site_id,max(score) AS score FROM screening_predictions
            WHERE scored_at>now()-interval '2 hours' GROUP BY site_id) p
            ON s.site_id=p.site_id ORDER BY p.score DESC''']
        for q in queries:self.assertEqual(validate_query(q),q)

    def test_actual_select_depth_has_a_hard_boundary(self):
        q='SELECT site_id FROM sites'
        for i in range(MAX_SELECT_DEPTH-1):q=f'SELECT * FROM ({q}) AS x{i}'
        validate_query(q)
        with self.assertRaisesRegex(ValueError,'nested SELECTs'):
            validate_query(f'SELECT * FROM ({q}) AS beyond')

    def test_deep_expressions_and_large_node_counts_are_rejected(self):
        with self.assertRaises(ValueError):
            validate_query('SELECT '+'abs('*40+'site_id'+')'*40+' FROM sites')
        with self.assertRaises(ValueError):
            validate_query('SELECT '+','.join('site_id' for _ in range(550))+' FROM sites')

    def test_restrictions_remain_effective_inside_nested_queries(self):
        for q in ('SELECT * FROM (SELECT * FROM hazard_reports) x',
                  'SELECT pg_sleep(1) FROM sites','SELECT * FROM sites FOR UPDATE',
                  'WITH x AS (SELECT * FROM sites) SELECT * FROM x',
                  'SELECT * FROM sites; DELETE FROM sites',
                  'SELECT * FROM pg_stat_statements'):
            with self.subTest(q=q),self.assertRaises(ValueError):validate_query(q)
