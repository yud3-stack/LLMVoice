# Ses Kalitesi, Chunking ve Telaffuz Normalizasyonu

## Yapılanlar

- Birleştirilmiş ses MP3'e çevrilmeden önce `loudnorm=I=-16:TP=-1.5:LRA=11` uygulanıyor.
- Referans ses XTTS'e verilmeden önce `loudnorm=I=-20:TP=-1.5:LRA=11` ile normalize ediliyor.
- Chunk sonu noktalamasına göre doğal bekleme süreleri eklendi:
  - Cümle sonu: temel sürenin `1.25x` değeri
  - Virgül ve benzeri: temel sürenin `0.75x` değeri
  - Diğer durumlar: temel sürenin `0.5x` değeri
- Kısa cümleler, maksimum chunk sınırı aşılmadığı sürece birleştiriliyor.
- `Dr.`, `Prof.`, `Mr.`, `e.g.` gibi kısaltmalarda yanlış chunk bölünmesi önlendi.
- Türkçe konuşma normalizasyonu şu örnekleri destekliyor:
  - Sayılar, yüzdeler ve ondalıklar
  - `TL`, `TRY`, `₺`
  - `km`, `kg`, `GB`, `MB`, `MHz`, `°C`

## Değişen Dosyalar

- `llmvoice/audio/merge.py`
- `llmvoice/audio/reference.py`
- `llmvoice/service.py`
- `llmvoice/text/chunker.py`
- `llmvoice/text/normalizer.py`
- İlgili `tests/` dosyaları

## Doğrulama

- Hedefli testler: `40 passed`
- Ses entegrasyon testleri: `8 passed`
- Önceki hedefli testler: `16 passed`
- Genel testlerde mevcut `samples/` klasöründeki ses artifact'ları nedeniyle paket metadata testi başarısız oluyor.

## Sonraki Adaylar

1. Referans ses için SNR ve sessizlik oranı skoru eklemek
2. Çoklu referans ses desteği eklemek
3. Tarih, saat, URL, e-posta ve teknik kısaltma telaffuzlarını genişletmek
4. Chunking için gerçek metin benchmark'ları ve ses karşılaştırma seti oluşturmak
5. Obsidian notlarına otomatik test ve git diff özeti eklemek
