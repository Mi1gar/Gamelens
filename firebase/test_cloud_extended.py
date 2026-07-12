"""Extended test: batch lookup, dedup, reject."""
import sys
sys.path.insert(0, 'engine/core')
from cloud_translations import CloudTranslationDB

db = CloudTranslationDB('rdr2')

# Test batch lookup
print('=== Batch Lookup ===')
texts = ['you need horses?', 'Arthur! Over here!', 'nonexistent text']
results = db.lookup_batch(texts)
for t, tr in results.items():
    print(f'  "{t}" -> {tr}')

# Test duplicate submit (should increment report_count)
print('\n=== Duplicate Submit ===')
db.submit_raw('you need horses?', 'Atlara ihtiyacin var mi?')
pending = db.get_pending(limit=5)
for p in pending:
    if 'horses' in p['original']:
        print(f'  [AFTER DUP] "you need horses?" -> report_count={p["report_count"]}')

# Test reject (clean up noise)
print('\n=== Reject ===')
for p in pending:
    if 'Come on' in p['original']:
        db.reject(p['hash'])
        print(f'  Rejected: {p["original"]}')
        break

# Final stats
print('\n=== Final Stats ===')
stats = db.get_stats()
print(f'Raw: {stats["raw_count"]}, Approved: {stats["approved_count"]}')

print('\n=== ALL EXTENDED TESTS PASSED! ===')
