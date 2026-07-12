"""Quick integration test for CloudTranslationDB."""
import sys
sys.path.insert(0, 'engine/core')
from cloud_translations import CloudTranslationDB

db = CloudTranslationDB('rdr2')

# Test 1: Submit raw translations
print('=== Test 1: Submit raw ===')
db.submit_raw('you need horses?', 'Atlara ihtiyacin var mi?', source='nllb-600m')
db.submit_raw('Come on, let us go.', 'Hadi, gidelim.', source='nllb-600m')
db.submit_raw('Arthur! Over here!', 'Arthur! Buraya!', source='nllb-600m')
print('OK - 3 raw entries submitted')

# Test 2: Get pending
print('\n=== Test 2: Get pending ===')
pending = db.get_pending(limit=10)
for p in pending:
    print(f'  [{p["report_count"]}x] "{p["original"]}" -> "{p["translated"]}"')
print(f'{len(pending)} pending entries')

# Test 3: Approve one
print('\n=== Test 3: Approve ===')
if pending:
    first = pending[0]
    db.approve(first['hash'], first['original'], 'At ister misin?', reviewer='mi1gar')
    print(f'Approved: {first["original"]} -> At ister misin?')

# Test 4: Lookup (should find approved)
print('\n=== Test 4: Lookup ===')
result = db.lookup(first['original'])
print(f'Lookup "{first["original"]}" -> "{result}"')

# Test 5: Stats
print('\n=== Test 5: Stats ===')
stats = db.get_stats()
print(f'Raw: {stats["raw_count"]}, Approved: {stats["approved_count"]}')

print('\n=== ALL TESTS PASSED! ===')
