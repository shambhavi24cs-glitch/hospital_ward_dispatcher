import sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import app as dispatcher

class DispatcherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        dispatcher.DB_PATH = Path(cls.tmp.name) / 'test.db'
        dispatcher.init_db()
        cls.client = dispatcher.app.test_client()
    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()
    def submit(self, category='ROUTINE', ident=None, urgency='Normal'):
        return self.client.post('/api/reports', json={'reporter':'Test Nurse','ward':'Ward 2','identifier':ident or f'WARDAB12-ALERT[{category}]','description':'Test report','urgency':urgency})
    def test_01_valid_critical(self): self.assertEqual(self.submit('CRITICAL').status_code,201)
    def test_02_valid_urgent(self): self.assertEqual(self.submit('URGENT').status_code,201)
    def test_03_valid_routine(self): self.assertEqual(self.submit('ROUTINE').status_code,201)
    def test_04_valid_supply(self): self.assertEqual(self.submit('SUPPLY').status_code,201)
    def test_05_valid_maintenance(self): self.assertEqual(self.submit('MAINTENANCE').status_code,201)
    def test_06_missing_reporter(self): self.assertEqual(self.client.post('/api/reports',json={'ward':'W','identifier':'WARDAB12-ALERT[ROUTINE]','description':'x'}).status_code,400)
    def test_07_bad_prefix(self): self.assertEqual(self.submit(ident='HOSPAB12-ALERT[ROUTINE]').status_code,400)
    def test_08_lowercase(self): self.assertEqual(self.submit(ident='WARDab12-ALERT[ROUTINE]').status_code,400)
    def test_09_bad_digits(self): self.assertEqual(self.submit(ident='WARDAB1X-ALERT[ROUTINE]').status_code,400)
    def test_10_missing_suffix(self): self.assertEqual(self.submit(ident='WARDAB12-ALERT').status_code,400)
    def test_11_unknown_category(self): self.assertEqual(self.submit(ident='WARDAB12-ALERT[OTHER]').status_code,400)
    def test_12_critical_override(self):
        r=self.submit('SUPPLY', urgency='Critical').get_json(); self.assertEqual(r['department'],'Nursing Supervisor'); self.assertEqual(r['priority'],1)
    def test_13_search_existing(self):
        r=self.submit().get_json(); self.assertEqual(self.client.get('/api/reports/'+r['id']).status_code,200)
    def test_14_status_update(self):
        r=self.submit().get_json(); self.assertEqual(self.client.patch('/api/reports/'+r['id']+'/status',json={'status':'In Progress'}).status_code,200)
    def test_15_invalid_status(self):
        r=self.submit().get_json(); self.assertEqual(self.client.patch('/api/reports/'+r['id']+'/status',json={'status':'Closed'}).status_code,400)
    def test_16_unknown_report(self): self.assertEqual(self.client.get('/api/reports/not-real').status_code,404)
    def test_17_analytics(self): self.assertEqual(self.client.get('/api/analytics').status_code,200)
    def test_18_handler_update(self): self.assertEqual(self.client.patch('/api/handlers/Nurse%20Supervisor%20A',json={'available':False,'capacity':3}).status_code,200)

if __name__=='__main__': unittest.main(verbosity=2)
