# Game Lens — Engine Refactor & İlk Test

**Tarih:** 2026-07-10
**Durum:** Onaylandı
**Hedef:** Engine mimarisini tamamla, uygulamayı çalışır hale getir, ilk canlı testi yap.

## Mimari

```
Tauri UI (React)                    Python Engine (sidecar)
┌─────────────────┐    spawn        ┌──────────────────────┐
│  Oyun Seçici    │ ──────────────→ │  DublajEngine        │
│  Ayarlar        │                 │  ├─ HookManager       │
│  Çeviri Durumu  │ ←──stdout─────  │  │  ├─ YOLO det.     │
└─────────────────┘                 │  │  ├─ RapidOCR       │
                                    │  │  └─ Preprocessor   │
                                    │  ├─ TemporalFilter    │
                                    │  ├─ TranslationService│
                                    │  │  ├─ Growing DB     │
                                    │  │  ├─ Memory (fuzzy) │
                                    │  │  └─ NLLB-200       │
                                    │  └─ Tkinter Overlay   │
                                    └──────────────────────┘
```

## Aşama 1: Engine'i Çalışır Hale Getir

### 1.1 Model Path Düzeltmeleri
- `engine/core/subtitle_detector.py`: yolo model path'ini `models/yolo_subtitle.pt` olarak düzelt
- `engine/core/nllb_translator.py`: 600M model path'ini kullan, 1.3B path'ini yedek olarak bırak

### 1.2 TranslationService Birleştirme
- Tek `TranslationService` sınıfı, çeviri zinciri:
  1. Growing DB (0ms) — oynadıkça büyür
  2. TranslationMemory fuzzy match (0ms) — Claude çevirileri
  3. NLLB-200 GPU (35-60ms) — son çare
- Argos ve Google Translate servisleri çıkarılacak
- `engine/services/translator.py` → NLLB tabanlı yeni servis

### 1.3 Overlay'i Engine'e Taşı
- `live_test_optimized.py` içindeki kanıtlanmış SubtitleOverlay sınıfını `engine/overlay/` altına taşı
- Siyah şerit, Corbel font, altyazının altında konumlanma
- WDA_EXCLUDEFROMCAPTURE, pozisyon toleransı ±15px, 4sn timeout

### 1.4 Pipeline Entegrasyonu
- `live_test_optimized.py`'deki watermark/HUD/kredi filtrelerini HookManager'a entegre et
- `live_test_optimized.py`'deki merge overlapping bboxes ve en uzun metin seçme mantığını HookManager'a ekle
- Sonuç: `engine/` altında çalıştırılabilir bağımsız bir ana script

### 1.5 Giriş Noktası
- `run.py` proje kökünde — argümanlarla oyun seçimi (`--game rdr2`, `--monitor 1`)

## Aşama 2: Tauri UI Bağlantısı

### 2.1 Python Sidecar API
- Basit stdio tabanlı iletişim (arg pass + stdout JSON)
- Tauri Rust tarafında `Command::new_sidecar()` ile Python spawn
- "Başlat" → Python engine başlar
- Overlay bağımsız Tkinter penceresi olarak çalışır

### 2.2 UI Güncellemeleri
- Library sayfasını gerçek adapter listesiyle doldur
- GameDetail sayfasını engine state'e bağla
- "Oyunu Başlat" butonu Python engine'i spawn etsin

## Aşama 3: Test

### 3.1 Fonksiyonel Test
- RDR2 oyun içi test: OCR kalitesi, çeviri gecikmesi, overlay konumlandırma
- Farklı altyazı türleri: tek satır, çift satır, farklı font boyutları
- Watermark ve kredi filtreleme kontrolü

### 3.2 Başarı Kriterleri
- Pipeline başlatıldıktan sonra overlay'in 2 saniye içinde görünmesi
- Çeviri gecikmesi < 120ms (memory miss), < 30ms (memory hit)
- Feedback loop olmaması (orijinal altyazı her zaman görünür)
- Watermark/credit'lerin filtrelenmesi
