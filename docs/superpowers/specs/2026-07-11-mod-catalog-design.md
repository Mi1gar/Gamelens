# Game Lens — Altyazı Mod Kataloğu Tasarımı

**Tarih:** 2026-07-11
**Durum:** Onaylandı
**Kapsam:** Oyun altyazı modlarını GitHub kataloğundan otomatik bulup kurma, bulunamayan oyunlarda OCR pipeline fallback

---

## 1. Amaç

Game Lens şu anda her oyun için YOLO + OCR + NLLB-200 pipeline'ını çalıştırıyor. Bu yaklaşımın iki sorunu var:
- Gecikme: ~70-110ms (NLLB) veya ~20-60ms (memory hit)
- OCR hataları: %99 doğruluk bile olsa arada hatalı okumalar oluyor

Çoğu popüler oyunun internette hazır altyazı modları var. Program bu modları otomatik bulup kursun, OCR pipeline'ı sadece mod olmayan oyunlarda fallback olarak kullansın.

## 2. Yaklaşım

**Küratörlü Katalog (Seçenek 1):** Modları manuel olarak bulup, test edip, GitHub reposuna ekliyoruz. Kullanıcı oyunu seçince program kataloğu kontrol ediyor, varsa indirip kuruyor.

- GitHub raw URL'lerinden ücretsiz hosting
- İnternetsiz çalışma için local cache (24 saat TTL)
- İleride Firebase Storage'a geçiş mümkün (URL değişimi yeterli)

## 3. Mimari

### 3.1 Yeni Bileşenler

| Bileşen | Dosya | Görev |
|---------|-------|-------|
| CatalogManager | `engine/core/catalog_manager.py` | GitHub'dan katalog JSON çekme, local cache, oyun sorgulama |
| ModInstaller | `engine/core/mod_installer.py` | Mod zip indirme, oyun klasörünü bulma, dosya kopyalama, yedek alma |

### 3.2 Değişecek Dosyalar

| Dosya | Değişiklik |
|-------|-----------|
| `engine/core/engine.py` | `select_game()` metoduna catalog kontrolü + erken return |

### 3.3 Veri Akışı

```
DublajEngine.select_game("rdr2")
  │
  ├─ CatalogManager.check("rdr2", lang="tr")
  │     ├─ internet varsa: GitHub raw URL'den catalog.json çek
  │     │     └─ local cache'e kaydet (cache/catalog.json)
  │     └─ internet yoksa: cache dosyasını oku (24 saat TTL)
  │
  ├─ Katalogda mod var mı?
  │     │
  │     ├─ EVET → ModInstaller.install(mod)
  │     │          ├─ zip dosyasını indir
  │     │          ├─ oyun klasörünü bul (Steam/Epic/Game Pass)
  │     │          ├─ varsa orijinal dosyayı .backup yap
  │     │          ├─ dosyaları kopyala
  │     │          └─ "Mod kuruldu! Oyunu başlatabilirsin." mesajı
  │     │          → OCR pipeline BAŞLATILMAZ
  │     │
  │     └─ HAYIR → Mevcut akış: adapter yükle, OCR pipeline başlat
  │
```

### 3.4 Katalog JSON Formatı

```json
{
  "version": "1.0",
  "updated": "2026-07-11",
  "games": {
    "rdr2": {
      "name": "Red Dead Redemption 2",
      "steam_appid": "1174180",
      "epic_appname": "Heather",
      "search_dirs": ["Red Dead Redemption 2"],
      "mods": [
        {
          "lang": "tr",
          "version": "1.0",
          "install_type": "file_copy",
          "files": [
            {
              "from": "data/game.str",
              "to": "{game_dir}/data/game.str"
            }
          ],
          "download_url": "https://raw.githubusercontent.com/gammasoftware/gamelens-catalog/main/mods/rdr2_tr_v1.0.zip",
          "download_size_mb": 3.2,
          "notes": "Chapter 1-6 + Epilogue. Oyun menüsünden Turkish seçin."
        }
      ]
    }
  }
}
```

## 4. CatalogManager Detayı

```python
class CatalogManager:
    CATALOG_URL = "https://raw.githubusercontent.com/.../catalog.json"
    CACHE_DIR  = "cache"
    CACHE_TTL  = 86400  # 24 saat

    def check(self, game_id: str, lang: str = "tr") -> Optional[ModEntry]:
        """Catalog'da oyun varsa mod bilgisini döndür."""
        catalog = self._load_catalog()       # internet → cache → None
        if not catalog:
            return None
        game = catalog["games"].get(game_id)
        if not game:
            return None
        for mod in game["mods"]:
            if mod["lang"] == lang:
                return mod
        return None

    def _load_catalog(self) -> Optional[dict]:
        # 1. internet varsa GitHub'dan çek, cache'e yaz
        # 2. internet yoksa cache'den oku (TTL kontrolü)
        # 3. cache de yoksa None
```

## 5. ModInstaller Detayı

### 5.1 Oyun Klasörünü Bulma

| Platform | Yöntem |
|----------|--------|
| Steam | Windows registry: `HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Steam App {appid}` → `InstallLocation` |
| Epic Games | `C:\ProgramData\Epic\UnrealEngineLauncher\LauncherInstalled.dat` JSON parse |
| Game Pass | `Get-AppxPackage` PowerShell ile paket adına göre |
| Manuel | Kullanıcıya klasör seçme diyalogu (tkinter `filedialog.askdirectory`) |

### 5.2 Kurulum Adımları

```python
class ModInstaller:
    def install(self, mod: dict) -> bool:
        # 1. Oyun klasörünü bul
        game_dir = self._find_game_dir(mod)
        if not game_dir:
            return False  # → manuel seçime yönlendir

        # 2. Zip'i indir (geçici klasöre)
        zip_path = self._download(mod["download_url"])

        # 3. Dosyaları kopyala (yedek alarak)
        for file_entry in mod["files"]:
            dest = file_entry["to"].replace("{game_dir}", game_dir)
            # Varsa yedek al
            if os.path.exists(dest) and not os.path.exists(dest + ".backup"):
                shutil.copy2(dest, dest + ".backup")
            # Zip'ten çıkart
            with zipfile.ZipFile(zip_path) as zf:
                zf.extract(file_entry["from"], os.path.dirname(dest))

        # 4. Geçici zip'i temizle
        os.remove(zip_path)
        return True
```

## 6. Engine Entegrasyonu

`DublajEngine.select_game()` metodunda minimal değişiklik:

```python
def select_game(self, game_id: str):
    # ── YENİ: Catalog kontrolü ──
    catalog = CatalogManager()
    mod = catalog.check(game_id, lang="tr")

    if mod:
        installer = ModInstaller()
        success = installer.install(mod)
        if success:
            print(f"[Engine] Mod installed. OCR pipeline skipped.")
            if self.on_status_change_callback:
                self.on_status_change_callback("mod_installed")
            return  # ← pipeline başlatılmaz

    # ── Mevcut akış, değişiklik yok ──
    adapter = GameRegistry.get_adapter(game_id)
    if adapter:
        self.hook_manager.set_active_adapter(adapter)
```

## 7. Hata Senaryoları

| Durum | Davranış |
|-------|----------|
| İnternet yok | Local cache'den oku, cache de yoksa None dön → OCR |
| GitHub erişilemez / 404 | None dön → OCR |
| GitHub rate limit (60 req/saat) | Cache'den oku, TTL dolduysa bile 1 saat daha uzat |
| Oyun klasörü bulunamadı | Kullanıcıya tkinter klasör seçme diyalogu |
| Hedef dosya zaten değiştirilmiş (.backup var) | Dokunma, başarılı say |
| Zip indirme başarısız | Tekrar dene (1 kere), olmazsa → OCR |
| Zip bozuk | Sil, tekrar indir (1 kere), olmazsa → OCR |
| Mod kaldırılmak istenirse (ileride) | `.backup` dosyasını geri yükle |

## 8. GitHub Repo Yapısı

```
gammasoftware/gamelens-catalog/
├── catalog.json               (ana katalog)
├── mods/
│   ├── rdr2_tr_v1.0.zip
│   ├── witcher3_tr_v1.0.zip
│   └── ...
└── README.md                   (mod ekleme talimatları)
```

## 9. Yeni Dosya Listesi

| Dosya | Tahmini satır |
|-------|---------------|
| `engine/core/catalog_manager.py` | ~80 satır |
| `engine/core/mod_installer.py` | ~100 satır |
| `engine/core/engine.py` (değişiklik) | ~15 satır ekleme |

## 10. Kapsam Dışı (Sonraki Versiyonlar)

- Mod loader kurulumu (BepInEx, MelonLoader vb.)
- Topluluk mod gönderimi (PR review sistemi)
- Firebase Storage'a geçiş
- Mod güncelleme bildirimi
- Oyun içi mod seçme menüsü
