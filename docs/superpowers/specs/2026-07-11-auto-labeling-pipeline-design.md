# Otomatik Dataset Oluşturma Pipeline'ı — Tasarım Dokümanı

**Tarih:** 2026-07-11
**Proje:** Game Lens
**Amaç:** YOLO altyazı tespit modeli için otomatik, ölçeklenebilir dataset oluşturma pipeline'ı

---

## 1. Özet

Game Lens'in YOLO altyazı tespit modelini eğitmek için internetten otomatik video indiren, frame'leri çıkaran, Florence-2 görsel LLM ile etiketleyen ve yarı-otomatik review süreciyle kalite kontrolü yapan bir pipeline.

**Kaynak:** https://www.youtube.com/@MKIceAndFire (ve ek kanallar)
**Model:** Florence-2 base (Microsoft, `microsoft/Florence-2-base`)
**GPU:** RTX 5070 12GB
**Çıktı:** YOLO formatında onaylanmış dataset (tek sınıf: `s-subtittle`)
**Review:** Teknik olmayan kişi için statik HTML arayüzü, zip ile paylaşım

---

## 2. Mimari

```
yt-dlp (video indir)
    ↓
FFmpeg (frame çıkar, fps=0.5)
    ↓
Canny Edge Ön Filtre (altyazısız frame'leri ele)
    ↓
Florence-2 <OCR_WITH_REGION> (bbox + metin)
    ↓
Pozisyon Filtresi (alt %40, genişlik kontrolü)
    ↓
YOLO Format Dönüşümü
    ↓
Review HTML Paketi (zip)
    ↓ [Arkadaş review yapar, JSON döner]
Review Importer (onaylananları dataset'e alır)
    ↓
data.yaml + train/val split
```

### Neden tek sınıf?

HookManager'daki 7 katmanlı filtre zinciri (region, temporal, UI, credit, watermark, alpha, vowel) altyazıyı diğer metin türlerinden zaten ayırıyor. Modele sadece "metin nerede?" öğretilmesi yeterli. Çok sınıflı etiketleme gereksiz karmaşıklık ve hata kaynağı olur.

### Neden Florence-2?

- Microsoft'un görsel grounding için özel eğittiği model
- `<OCR_WITH_REGION>` task'ı tam olarak ihtiyacımızı karşılıyor: metin + bounding box
- Yapılandırılmış JSON çıktısı, deterministik parse
- ~1.5 GB VRAM (fp16), 12GB'de batch_size=4 mümkün
- 100-150ms/frame, halüsinasyon riski düşük
- Aktif geliştirilen, SOTA seviyesinde

### Neden yarı otomatik review?

Tam otomatik etiketlemede hatalar birikir ve model kalitesini düşürür. Teknik olmayan bir kişinin bile yapabileceği basit onay/red/düzelt işlemi ile kalite garantilenir.

---

## 3. Bileşenler

### 3.1 config.py

```python
@dataclass
class PipelineConfig:
    # Video kaynakları
    channels: list[str]       # ["MKIceAndFire", ...]
    max_videos: int           # 50
    video_quality: str        # "best[height<=1080]"
    title_filter: str         # "(?i)walkthrough|gameplay|full game|no commentary|cutscenes"

    # Frame çıkarma
    frame_fps: float          # 0.5 (2 saniyede 1)
    output_format: str        # "png"

    # Ön filtre
    edge_density_threshold: float  # 0.02

    # Florence-2
    model_name: str           # "microsoft/Florence-2-base"
    confidence_threshold: float  # 0.6
    device: str               # "cuda"
    batch_size: int           # 4

    # Pozisyon filtresi
    min_y_ratio: float        # 0.40 (alt %40)
    min_width_ratio: float    # 0.02 (ekran genişliğinin %2'si)
    min_text_length: int      # 3

    # Dataset
    train_split: float        # 0.8
    output_dir: str           # "output/approved"
    seed: int                 # 42
```

### 3.2 video_collector.py

yt-dlp wrapper. Kanal URL'sinden video listesini çeker, başlık filtresinden geçirir, indirir.

```
python pipeline.py --collect --channel MKIceAndFire --max-videos 50
```

- `--max-videos`: En fazla kaç video indirilecek
- `--game-filter`: Belirli oyun isimlerini içeren başlıklara filtrele (opsiyonel)
- `--sleep-interval`: YouTube rate limiting için bekleme (varsayılan 3s)
- İndirilenler `data/videos/` altına kaydedilir
- Başarısız indirmeler `pipeline_state.json`'a kaydedilir

### 3.3 frame_extractor.py

FFmpeg ile frame çıkarma + Canny edge ön filtre.

```
python pipeline.py --extract
```

- Her video için `ffmpeg -vf fps=0.5` ile 2 saniyede 1 frame
- Çıktı: `data/frames/{video_adı}_frame_000001.png`
- Ön filtre: Her frame'in alt %40'ında Canny edge density hesaplanır
- Edge density < 0.02 olan frame'ler atlanır (altyazı yok)
- Tahmini eleme oranı: %70-80
- Aday frame'ler `data/frames/` altında `.candidates` dosyasına liste olarak yazılır

### 3.4 auto_labeler.py

Florence-2 entegrasyonu.

```
python pipeline.py --label
```

Akış:
1. Florence-2 modelini lazy-load (ilk kullanımda ~5-10s)
2. Aday frame'i yükle, RGB'ye çevir
3. `<OCR_WITH_REGION>` task'ını çalıştır
4. JSON çıktıyı parse et
5. Her quad_box için:
   - Quad'ı YOLO bbox formatına çevir (normalize x_center, y_center, width, height)
   - Pozisyon filtresini uygula (alt %40, genişlik > %2, metin > 3 karakter)
   - Geçenleri `data/labeled/labels/{frame_adı}.txt` olarak kaydet
6. Frame'i `data/labeled/images/{frame_adı}.png` olarak kopyala
7. `pipeline_state.json` güncelle

YOLO label formatı:
```
# Her satır: class_id x_center y_center width height
0 0.500000 0.825000 0.260000 0.030000
```

### 3.5 review_packager.py

Statik HTML review paketi oluşturur.

```
python pipeline.py --package
```

Oluşturulan zip yapısı:
```
review_r1.zip
├── review.html
├── frames/
│   ├── frame_000001.png
│   └── ...
└── labels/
    ├── frame_000001.txt
    └── ...
```

### 3.6 review_template.html

Teknik olmayan kişi için interaktif review arayüzü.

**Özellikler:**
- Her frame'de kırmızı bounding box'lar çizili
- Klavye kısayolları: ← → gezin, Enter onayla, Delete sil
- Bbox düzeltme: fareyle sürükle ve köşelerinden boyutlandır (Canvas API)
- İlerleme çubuğu: onaylanan/silinen/düzeltilen sayısı
- localStorage: tüm kararlar anında kaydedilir, sayfa kapanıp açılsa bile kalır
- "Kararları Dışa Aktar" butonu → `review_results.json` indirir
- Her kararın görsel geri bildirimi: yeşil çerçeve (onay), kırmızı çizgi (sil)
- Frame listesi sidebar'da, onay durumu ikonlarla gösterilir

**review_results.json formatı:**
```json
{
  "approved": ["video1_frame_000001", "video1_frame_000005"],
  "rejected": ["video1_frame_000003"],
  "edited": {
    "video1_frame_000004": {"bbox": [0.5, 0.83, 0.26, 0.03]}
  },
  "reviewer": "Ahmet",
  "completed_at": "2026-07-12T15:30:00"
}
```

### 3.7 review_importer.py

Review sonuçlarını dataset'e entegre eder.

```
python pipeline.py --import review_results.json
```

- Onaylanan frame'ler → `output/approved/{train,val}/` (seed=42, %80/%20 split)
- Düzenlenen bbox'lar → güncellenmiş YOLO label
- Reddedilenler → `output/rejected/` (analiz için)
- `output/approved/data.yaml` otomatik oluşturulur
- İstatistik: kaç onaylandı, kaç reddedildi, kaç düzenlendi

### 3.8 pipeline.py

Ana orkestratör. Tüm adımları sırayla veya kısmi çalıştırır.

```
# Tam pipeline
python pipeline.py --full --max-videos 50

# Kısmi çalıştırma
python pipeline.py --collect --channel MKIceAndFire
python pipeline.py --extract
python pipeline.py --label
python pipeline.py --package
python pipeline.py --import review_results.json

# Resume (kaldığı yerden devam)
python pipeline.py --resume
```

`pipeline_state.json` ile her adımın durumu takip edilir. İnternet kesintisi, GPU OOM gibi durumlarda kayıp olmaz.

---

## 4. Klasör Yapısı

```
otomatik_egitim_pipeline/
├── pipeline.py                 # Ana orkestratör
├── config.py                   # Ayarlar
├── requirements_labeling.txt   # Ek bağımlılıklar
├── video_collector.py          # yt-dlp wrapper
├── frame_extractor.py          # FFmpeg + Canny ön filtre
├── auto_labeler.py             # Florence-2 etiketleme
├── review_packager.py          # HTML + PNG paketi
├── review_importer.py          # JSON içe aktarma
├── review_template.html        # Review HTML şablonu
├── data/
│   ├── pipeline_state.json     # Durum takibi (resume için)
│   ├── videos/                 # İndirilen videolar
│   ├── frames/                 # Çıkarılan frame'ler
│   │   └── .candidates         # Aday frame listesi
│   ├── labeled/                # Florence-2 çıktısı
│   │   ├── images/
│   │   └── labels/
│   └── exports/                # Review zip paketleri
└── output/
    ├── approved/               # Onaylanmış dataset
    │   ├── train/
    │   │   ├── images/
    │   │   └── labels/
    │   ├── val/
    │   │   ├── images/
    │   │   └── labels/
    │   └── data.yaml
    └── rejected/               # Reddedilmiş (analiz)
```

---

## 5. Veri Akışı — Uçtan Uca

### Adım 1: Video Toplama
```
> python pipeline.py --collect --channel MKIceAndFire --max-videos 50

[VideoCollector] Searching @MKIceAndFire videos...
[VideoCollector] Found 847 videos, filtering by title...
[VideoCollector] 312 videos match gameplay filter
[VideoCollector] Downloading 50 videos (limited by --max-videos)...
[VideoCollector] ✓ rdr2_chapter1_walkthrough.mp4 (1.2 GB)
[VideoCollector] ✓ metro_exodus_full_game.mp4 (2.1 GB)
...
[VideoCollector] Done. 47 downloaded, 3 failed.
```

### Adım 2: Frame Çıkarma
```
> python pipeline.py --extract

[FrameExtractor] Processing 47 videos...
[FrameExtractor] rdr2_chapter1: 4200 frames → 1100 candidates
[FrameExtractor] metro_exodus: 6100 frames → 1450 candidates
...
[FrameExtractor] Done. 14,832 frames → 4,523 candidates
```

### Adım 3: Etiketleme
```
> python pipeline.py --label

[AutoLabeler] Loading Florence-2 base (fp16)...
[AutoLabeler] Model loaded. VRAM: 1.5 GB
[AutoLabeler] Processing 4523 candidates in batches of 4...
[Progress] ████████░░░░░░ 3200/4523 (70%)
[AutoLabeler] Done. 3847 frames labeled, 676 empty (no text found)
```

### Adım 4: Review Paketi
```
> python pipeline.py --package

[ReviewPackager] Creating review package...
[ReviewPackager] 3847 frames → review_r1/
[ReviewPackager] Compressing...
[ReviewPackager] Done. review_r1.zip (892 MB)
[ReviewPackager] ⚠️  Send this to your reviewer!
```

### Adım 5: Review (Arkadaş)
```
Arkadaş: review_r1.zip'i açar, review.html'e çift tıklar
Arkadaş: 3847 frame'i inceler, Enter/Delete ile onaylar/reddeder
Arkadaş: "Kararları Dışa Aktar" → review_results.json iner
Arkadaş: JSON'u size gönderir
```

### Adım 6: İçe Aktarma
```
> python pipeline.py --import review_results.json

[ReviewImporter] Loading review_results.json...
[ReviewImporter] Approved: 3201 | Rejected: 502 | Edited: 144
[ReviewImporter] Train/Val split (80/20, seed=42):
                   Train: 2676 images + labels
                   Val:   669 images + labels
[ReviewImporter] data.yaml written.
[ReviewImporter] Done. Dataset ready for training!
```

---

## 6. Tahmini Ölçek

50 video (~500 dakika toplam) için:

| Adım | Süre | Disk |
|------|------|------|
| Video indirme | 2-3 saat | ~15 GB |
| Frame çıkarma | 30-45 dk | ~7.5 GB |
| Ön filtre | Anlık (içinde) | — |
| Florence-2 etiketleme | 7-12 dk (GPU) | ~2 GB |
| Review paketi | 2-5 dk | ~1 GB zip |
| Review (insan) | 2-4 saat | — |
| İçe aktarma | <1 dk | ~1.5 GB |

---

## 7. Hata Yönetimi

| Durum | Davranış |
|-------|----------|
| İnternet kesintisi | yt-dlp resume desteği var, kaldığı yerden devam |
| GPU OOM | Batch size otomatik düşür (4→2→1), log'a yaz |
| Florence-2 hata | Frame atlanır, hata log'a yazılır, sonraki frame'le devam |
| Bozuk video | FFmpeg hatasını yakala, videoyu atla, state'e kaydet |
| Boş frame (altyazı yok) | Normal, label dosyası oluşturulmaz, frame atlanır |
| Disk dolu | Kontrol et, kullanıcıyı uyar, dur |

---

## 8. Bağımlılıklar

### Python paketleri (`requirements_labeling.txt`):
```
yt-dlp
transformers>=4.38.0
torch>=2.2.0
einops
timm
opencv-python
Pillow
numpy
```

### Sistem araçları:
- FFmpeg (PATH'te olmalı)
- NVIDIA CUDA 12.x (zaten kurulu)

### Model:
- `microsoft/Florence-2-base` — ilk çalıştırmada HuggingFace'ten otomatik indirilir (~1.5 GB)

---

## 9. Gelecek Genişletmeler (v2)

- Birden fazla YouTube kanalı desteği
- Web UI (Tauri entegrasyonu) ile canlı review
- Aktif öğrenme: modelin zayıf olduğu frame'leri otomatik tespit edip review'e gönderme
- Çok sınıflı etiketleme (altyazı, hint, quest, UI) — eğer ileride gerekirse
- Otomatik eğitim tetikleme: dataset belli bir boyuta ulaşınca YOLO eğitimini başlat
```

