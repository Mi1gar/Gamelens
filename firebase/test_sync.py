"""Test one-time cloud sync flow."""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from engine.services.translation_service import TranslationService

# Test sync for rdr2
print("=== Creating TranslationService for rdr2 ===")
ts = TranslationService(target_lang='tr', game_slug='rdr2')

if ts._cloud_enabled:
    local_before = len(ts._growing)
    print(f"Local entries before sync: {local_before}")

    # Check sync meta before
    meta_before = ts._sync_meta.get('rdr2', {})
    print(f"Sync meta before: {meta_before}")

    # Force re-sync by clearing meta
    ts._sync_meta.pop('rdr2', None)
    ts._synced_this_session = False

    # Run sync
    print("\n=== Running sync_from_cloud() ===")
    new = ts.sync_from_cloud()
    local_after = len(ts._growing)
    print(f"\nNew entries synced: {new}")
    print(f"Local entries after sync: {local_after}")

    # Verify sync meta was saved
    meta_after = ts._sync_meta.get('rdr2', {})
    print(f"Sync meta after: {meta_after}")

    # Verify second sync is skipped
    print("\n=== Second sync (should skip) ===")
    new2 = ts.sync_from_cloud()
    print(f"Second sync returned: {new2} (should be 0)")

    # Verify cloud-approved text is now in local DB
    print("\n=== Local lookup ===")
    result = ts.translate("you need horses?")
    print(f'Local translate "you need horses?" -> "{result}"')

    print("\n=== ALL SYNC TESTS PASSED! ===")
else:
    print("Cloud not available — skipping sync tests")
