# Opsiyonel Çoklu Referans Ses

## Yapılanlar

- Tek referans kullanımı korunuyor:
  - `llmvoice voice add friday reference.wav`
- İsteğe bağlı ek referans desteği eklendi:
  - `llmvoice voice add friday reference.wav --reference second.wav`
  - `--reference` birden fazla kez kullanılabilir.
- Aynı ses profiline ait dosyalar `friday.wav`, `friday-2.wav` gibi saklanıyor.
- XTTS tek referansta eski davranışı, çoklu referansta liste halinde `speaker_wav` kullanıyor.
- Speaker cache kimliği tüm referansların yolu, boyutu ve değişim zamanından oluşturuluyor.
- `voice list --json` çıktısına `reference_count` eklendi.
- Tek referans kullanan mevcut profiller ve komutlar geriye dönük uyumlu.

## Doğrulama

- XTTS, CLI, voice manager ve pipeline testleri: `43 passed`

## Sonraki Adaylar

1. Her referans için ayrı kalite skoru göstermek
2. Düşük kaliteli referansı çoklu profilden hariç tutma seçeneği
3. Referansların aynı konuşmacıya ait olduğunu doğrulayan profil kontrolü
4. Çoklu referansları sonradan profile ekleme/çıkarma komutları
