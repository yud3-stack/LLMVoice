# Referans Ses Kalite Skoru

## Yapılanlar

- `llmvoice voice inspect reference.wav` artık `0-100` arası kalite skoru gösteriyor.
- FFmpeg `silencedetect` ile sessizlik oranı ölçülüyor.
- Skor; süre, kanal sayısı, clipping, ortalama ses seviyesi ve sessizlik oranını değerlendiriyor.
- İnsan çıktısına `Quality score` ve `Silence ratio` alanları eklendi.
- `--json` çıktısı yeni alanları otomatik olarak içeriyor.
- Yüksek sessizlik oranı için referansı kırpma önerisi gösteriliyor.

## Skor Aralıkları

- `80-100`: good
- `60-79`: review
- `0-59`: poor

## Doğrulama

- Ses entegrasyon testleri: `8 passed`
- Normalizer, chunker ve service testleri: `19 passed`

## Sonraki Adaylar

1. Gerçek SNR/noise-floor ölçümü eklemek
2. Skoru `voice add` sırasında uyarı olarak göstermek
3. Kalite skoruna göre otomatik referans trimming/denoise önermek
