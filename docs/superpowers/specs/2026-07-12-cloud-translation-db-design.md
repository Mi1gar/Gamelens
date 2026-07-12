# Cloud Translation Database — Firebase Entegrasyonu

## Özet

GameLens kullanıcıları oyun oynarken OCR+NLLB ile canlı çeviri yapıyor. Şu an her kullanıcı aynı diyalogları sıfırdan çeviriyor. Bu tasarım, Firebase Firestore üzerinde iki aşamalı (raw → approved) bir cloud çeviri veritabanı kurarak:

1. Kullanıcıların onaylanmış çevirileri 0ms'de almasını
2. Yeni diyalogların "raw" olarak birikmesini
3. Bizim review edip "approved"a taşımamızı
4. Robotik NLLB çevirilerinin yayılmasını engellemeyi

sağlar.

---

## Firestore Veri Modeli

```
/games/{game_slug}/
  │
  ├── raw/                              ← Oyuncular YAZAR (asla okumaz)
  │     {text_hash}/                     ← hash = sha256(original.lower().strip())[:16]
  │     │   original: "you need horses?"
  │     │   translated: "Atlara ihtiyacın var mı?"   ← NLLB output
  │     │   source: "nllb-600m"
  │     │   ocr_confidence: 0.92        ← RapidOCR güven skoru
  │     │   report_count: 3             ← kaç farklı kullanıcıda geçti
  │     │   first_seen: Timestamp
  │     │   last_seen: Timestamp
  │     │
  │     └── {text_hash}/
  │           original: "Arthur! Over here!"
  │           translated: "Arthur! Buradayım!"
  │           source: "nllb-600m"
  │           ocr_confidence: 0.88
  │           report_count: 7
  │           ...
  │
  ├── approved/                         ← Oyuncular OKUR (realtime sync)
  │     {text_hash}/
  │     │   original: "you need horses?"
  │     │   translated: "At ister misin?"           ← insan düzeltmesi
  │     │   reviewed_by: "mi1gar"
  │     │   approved_at: Timestamp
  │     │   quality: "natural"           ← natural | literal | needs_review
  │     │
  │     └── {text_hash}/
  │           original: "Arthur! Over here!"
  │           translated: "Arthur! Buraya!"
  │           reviewed_by: "mi1gar"
  │           approved_at: ...
  │           quality: "natural"
  │
  └── meta/
        game_name: "Red Dead Redemption 2"
        raw_count: 1523
        approved_count: 450
        last_updated: Timestamp
        locales: ["en", "tr"]
```

### Hash Stratejisi

`text_hash = sha256(original.lower().strip())[:16]`

- Case-insensitive, whitespace-normalized
- Aynı diyalog farklı OCR varyasyonları alsa bile aynı hash'e düşmez — bu bilinçli. "you need horses?" ile "You need horses." farklı hash. Review sırasında varyasyonları görüp merge ederiz.
- 16 hex karakter = 2^64 kombinasyon, collision riski yok denecek kadar az

---

## Veri Akışı

### Oyuncu Tarafı (Client — Read Path)

```
OCR output: "you need horses?"
         │
    ┌────▼─────────┐
    │ 1. Local DB   │  120 entry  0ms   en hızlı, her zaman önce
    └────┬─────────┘
         │ (miss)
    ┌────▼─────────┐
    │ 2. Firestore  │  approved/{hash}  50-200ms   internet varsa
    │   approved    │  → bulursa local DB'ye kaydet
    └────┬─────────┘
         │ (miss)
    ┌────▼─────────┐
    │ 3. NLLB-200   │  35-60ms  GPU   her zaman son çare
    │              │  → sonucu Firebase raw'a yaz
    └─────────────┘
```

### Oyuncu Tarafı (Client — Write Path)

```
NLLB çevirdi "Atlara ihtiyacın var mı?"
         │
    ┌────▼────────────┐
    │ Local DB'ye yaz  │  hemen, her zaman
    └────┬────────────┘
         │
    ┌────▼────────────┐
    │ Firebase raw'a   │  async, batch, internet varsa
    │ report_count++   │  offline → queue → sync sonra
    └─────────────────┘
```

### Review Workflow (Bizim Taraf)

```
┌─────────────────────────────────────────────┐
│  Review Dashboard (HTML veya CLI)           │
│                                             │
│  raw koleksiyonu, report_count'a göre sıralı│
│  En çok raporlanan → önce review            │
│                                             │
│  "you need horses?"                         │
│    NLLB: "Atlara ihtiyacın var mı?"  [ROBOTİK] │
│    Biz:  "At ister misin?"          [DOĞAL] │
│                                             │
│  [Approve] [Skip] [Delete as noise]         │
└─────────────────────────────────────────────┘
         │
         ▼
  raw'dan sil, approved'a yaz
  Tüm oyuncular anında alır (Firestore realtime listener)
```

---

## Güvenlik Kuralları

```javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {

    match /games/{game}/approved/{entry} {
      allow read: if true;                      // herkes okur
      allow write: if request.auth != null
                   && request.auth.token.role == 'reviewer';  // sadece reviewer
    }

    match /games/{game}/raw/{entry} {
      allow read: if request.auth != null
                   && request.auth.token.role == 'reviewer';  // sadece reviewer okur
      allow create, update: if true;            // herkes yazabilir (anonim)
      allow delete: if request.auth != null
                    && request.auth.token.role == 'reviewer';
    }

    match /games/{game}/meta {
      allow read: if true;
      allow write: if request.auth != null
                   && request.auth.token.role == 'reviewer';
    }
  }
}
```

- **Anonim yazma:** Kullanıcı girişi zorunlu değil. Oyuncular raw'a yazmak için auth'a ihtiyaç duymaz.
- **Reviewer yetkisi:** Sadece biz (Mi1gar + belirlenen reviewer'lar) approved'a yazabilir.
- **Okuma:** approved herkese açık. raw sadece reviewer'lara.

---

## Offline Stratejisi

Firestore SDK'nın yerleşik offline persistence özelliği kullanılacak:

```
İnternet VAR:
  approved → realtime listener → güncellemeler anında
  raw      → batch write, throttle (en fazla 10 saniyede bir flush)

İnternet YOK:
  approved → localStorage'dan oku (son sync'lenmiş cache)
  raw      → kuyruğa al (local queue), internet gelince flush
```

Firestore offline cache boyutu: varsayılan 100 MB. Oyun başına approved koleksiyonu ~5000 satır, her biri ~200 byte = ~1 MB. 100 oyun bile ~100 MB, sığar.

---

## Mevcut Kodla Entegrasyon

### Değişecek Dosyalar

1. **`engine/services/translation_service.py`** — Mevcut 3-tier sisteme Firebase tier'ı eklenecek:
   ```
   Tier 0: Local DB     (growing_memory.json)    — 0ms
   Tier 1: Firestore     (approved koleksiyonu)   — 50-200ms
   Tier 2: Fuzzy Memory  (manual_translations)    — 0ms
   Tier 3: NLLB-200      (GPU translation)        — 35-60ms
   ```

2. **`engine/core/cloud_translations.py`** (YENİ) — Firebase bağlantısı, cache yönetimi, queue

3. **`engine/core/review_dashboard.html`** (YENİ) — Raw → approved review arayüzü

### Firebase SDK

```python
# engine/core/cloud_translations.py
import firebase_admin
from firebase_admin import credentials, firestore

class CloudTranslationDB:
    def __init__(self, game_slug: str):
        self.game = game_slug
        self.db = firestore.client()
        self._local_cache: dict[str, str] = {}  # in-memory hot cache
        self._write_queue: list[dict] = []        # offline queue
        self._last_flush = 0

    def lookup(self, text: str) -> str | None:
        """Check Firestore approved + local cache."""
        ...

    def submit_raw(self, original: str, translated: str,
                   ocr_conf: float = 0.0):
        """Submit NLLB translation to raw collection."""
        ...

    def flush(self):
        """Flush write queue to Firestore."""
        ...
```

### Local DB Genişletme

`growing_memory.json` yapısı şu an düz `{en: tr}`. Genişletilmiş:

```json
{
  "you need horses?": {
    "tr": "At ister misin?",
    "source": "firestore_approved",
    "quality": "natural",
    "synced_at": "2026-07-12T15:30:00Z"
  }
}
```

`source` alanı sayesinde hangi çevirinin nereden geldiği bilinir: `"nllb"` | `"firestore_approved"` | `"manual"` | `"user_override"`.

---

## Review Dashboard (Basit HTML)

Bizim için tek sayfalık bir HTML dashboard:

```
┌──────────────────────────────────────────────────────┐
│  GameLens Review Dashboard                    [rdr2] │
├──────────────────────────────────────────────────────┤
│  Pending: 1073  │  Approved: 450  │  By me: 127      │
├──────────────────────────────────────────────────────┤
│                                                      │
│  #512  │ report_count: 23  │ "you need horses?"     │
│        │ NLLB: "Atlara ihtiyacın var mı?"            │
│        │ ┌──────────────────────────────────────┐    │
│        │ │ At ister misin?                      │    │
│        │ └──────────────────────────────────────┘    │
│        │ [✓ Approve] [→ Skip] [✗ Delete as noise]    │
│                                                      │
├──────────────────────────────────────────────────────┤
│  #513  │ report_count: 19  │ "Arthur! Over here!"   │
│        │ ...                                          │
└──────────────────────────────────────────────────────┘
```

Sıralama: `report_count` azalan → en popüler diyaloglar önce review edilir.

---

## Gürültü Filtreleme

OCR'dan gürültü gelme ihtimali yüksek. `raw` koleksiyonu bunları filtrelemek için iyi bir yer:

| Sinyal | Aksiyon |
|--------|---------|
| `report_count = 1`, `ocr_confidence < 0.5` | Muhtemelen çöp — review'da hızlıca silinir |
| `report_count >= 5` | Muhtemelen gerçek diyalog — öncelikli review |
| `len(original) < 6` | Muhtemelen HUD/UI parçası — otomatik işaretle |
| `original.isupper()` ve `len(original.split()) >= 2` | Muhtemelen credit satırı — otomatik reddet |
| `report_count >= 30`, hala approved'da yok | Acil review — popüler diyalog robotik çeviriyle dolaşıyor |

Firebase Cloud Function ile `report_count >= 30` olup approved'da olmayan entry'ler için otomatik e-posta/Slack bildirimi gönderilebilir.

---

## Uygulama Planı

### Faz 1: Firebase Projesi Kurulumu (1-2 saat)
- Firebase projesi oluştur (gamelens-cloud)
- Firestore veritabanı oluştur
- Güvenlik kurallarını deploy et
- Service account key oluştur (`gamelens-firebase-key.json`)
- `.gitignore`'a key dosyasını ekle

### Faz 2: CloudTranslationDB Sınıfı (2-3 saat)
- `engine/core/cloud_translations.py` yaz
- `translation_service.py`'ye Tier-1 olarak entegre et
- Local cache + offline queue implementasyonu

### Faz 3: Review Dashboard (1-2 saat)
- `engine/core/review_dashboard.html` yaz
- Firebase Web SDK ile read/write
- Bulk approve/delete işlemleri

### Faz 4: Test & Launch (1 saat)
- RDR2 ile canlı test
- Farklı oyunlara geçiş testi (`/games/rdr2` → `/games/gta5`)
- Offline → online geçiş testi

---

## Riskler

| Risk | Mitigation |
|------|-----------|
| Firestore maliyeti (çok okuma) | Offline cache sayesinde her lookup network çağrısı değil. 5000 aktif kullanıcı × günde 1000 okuma = 5M/gün → ücretli tier sınırında. Batch read ile optimize edilebilir. |
| Anonim yazma spam'i | `report_count` önemsiz entry'leri filtreler. Kötü niyetli spam Cloud Function ile rate-limit edilebilir. |
| Service account key güvenliği | Key sadece client'ta, dağıtımda obfuscate edilecek. Gerçek üretimde Firebase Auth + anonim giriş kullanılacak. |
| Hash collision (farklı cümleler aynı hash) | 2^64 olasılık, pratikte imkansız. Yine de lookup'ta `original` alanını da karşılaştırarak double-check. |

---

## Gelecek V2 Özellikleri

- **Oyunlar arası çeviri paylaşımı:** "Come on, let's go" RDR2'de de GTA5'te de aynı anlamda — `/shared/` koleksiyonu
- **Topluluk oylaması:** Kullanıcılar çeviriyi beğenirse upvote, alternatif önerebilir
- **Çeviri alternatifleri:** Bir diyalog için birden fazla onaylanmış varyant (bağlama göre)
- **Auto-approve threshold:** `report_count > 100` ve NLLB çevirisi doğal görünüyorsa otomatik approved'a taşı
