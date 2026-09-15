# Referans Bazlı Kalite Yönetimi

## Yapılanlar

- `llmvoice voice references friday` komutu eklendi.
- Her referans için ayrı kalite skoru, sessizlik oranı, clipping durumu ve öneriler gösteriliyor.
- `--json` çıktısı otomasyon için referans bazlı rapor döndürüyor.
- `llmvoice start` için opsiyonel `--strict-reference-quality` seçeneği eklendi.
- Strict modda yalnızca `60/100` ve üzeri referanslar XTTS’e gönderiliyor.
- Varsayılan davranış değişmedi; strict seçenek verilmezse tüm referanslar kullanılıyor.

## Kullanım

```cmd
llmvoice voice references friday
llmvoice start transcript.txt --voice friday --strict-reference-quality
```

## Doğrulama

- CLI, XTTS ve voice testleri: `40 passed`
- Ses entegrasyon testleri: `8 passed`

## Mevcut Sample Sonuçları

`samples/reference.m4a` referans adayı olarak `75/100` aldı. Kayıt 30 saniye ve
stereo olduğu için strict modda kullanılabilir, ancak 6-15 saniyelik mono bir
kesit daha uygun olur.

Diğer sample MP3 dosyaları (`transcript.mp3`, `normal.mp3`, `balanced-v2` ile
`balanced-v6`) üretim çıktısı olduğu için referans kalitesi açısından uygun
değil. Çoğu `55-65/100` aralığında görünüyor ve MP3 tepe seviyesi nedeniyle
clipping uyarısı veriyor.

## Sonraki Adaylar

1. Kalite raporlarını profil metadata'sında cache'lemek
2. Referans ekleme/çıkarma için ayrı profile komutları eklemek
3. Strict modda kullanılan ve elenen referansları üretim özetinde göstermek
