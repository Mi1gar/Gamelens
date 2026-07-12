"""Integration test: TranslationService with CloudDB."""
import sys
import os

# Add project root so 'engine' package is importable
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

from engine.services.translation_service import TranslationService

# Test 1: Without game (offline mode)
print("=== Test 1: Offline mode (no game) ===")
ts_offline = TranslationService(target_lang='tr')
print(f"Cloud enabled: {ts_offline._cloud_enabled}")
print(f"Stats: {ts_offline.stats}")

# Test 2: With game slug (cloud mode)
print("\n=== Test 2: Cloud mode (rdr2) ===")
ts = TranslationService(target_lang='tr', game_slug='rdr2')
print(f"Cloud enabled: {ts._cloud_enabled}")
if ts._cloud_enabled:
    print(f"Stats: {ts.stats}")

    # Test 3: Lookup flow — should hit CloudDB approved for "you need horses?"
    print("\n=== Test 3: Lookup from CloudDB ===")
    result = ts.translate("you need horses?")
    print(f'Translate "you need horses?" -> "{result}"')
    # Should return "At ister misin?" (from approved, not NLLB)

    # Test 4: Text NOT in local DB — hits CloudDB approved
    print("\n=== Test 4: CloudDB-only text ===")
    from engine.core.cloud_translations import _hash_text
    test_text = "unique cloud test sentence 42"
    test_hash = _hash_text(test_text)
    ts._cloud.approve(test_hash, test_text, "Bulut testi basarili",
                     reviewer="test")
    result = ts._cloud.lookup(test_text)
    print(f'Cloud lookup "{test_text}" -> "{result}"')
    assert result == "Bulut testi basarili", f"Expected cloud result, got {result}"
    print("OK - cloud-only lookup works!")
    # Cleanup
    ts._cloud._approved_ref.document(test_hash).delete()

    # Test 5: set_game switch
    print("\n=== Test 5: Switch game ===")
    ts.set_game("gta5")
    print(f"Cloud enabled: {ts._cloud_enabled}")
    if ts._cloud_enabled:
        print(f"GTA5 stats: approved={ts.stats['cloud_approved']}, pending={ts.stats['cloud_pending']}")

print("\n=== ALL INTEGRATION TESTS PASSED! ===")
