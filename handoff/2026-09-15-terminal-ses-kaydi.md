# Terminalden Ses Kaydı

## Yapılanlar

- `llmvoice audio devices` komutu eklendi.
- Windows FFmpeg DirectShow cihazları listeleniyor.
- `llmvoice voice record <name> --duration 10` komutu eklendi.
- İlk kayıt yeni profil oluşturuyor; aynı isimle sonraki kayıtlar ek referans oluyor.
- Kayıtlar mono, 24 kHz PCM WAV olarak alınıyor.
- Kayıt sonrası kalite skoru, sessizlik ve clipping kontrolü yapılıyor.
- `60/100` altındaki kayıtlar profile eklenmiyor.
- `--device` ile mikrofon seçilebiliyor, `--yes` ile onay atlanabiliyor.
- Mevcut ses profilleri başarısız veya iptal edilen kayıtlardan korunuyor.

## Gerçek Makine Doğrulaması

`llmvoice audio devices` başarıyla çalıştı ve şu cihazlar bulundu:

- `Mikrofon (4- USBZH3-ENC)`
- `Mikrofon Dizisi (Realtek(R) Audio)`

## Testler

- Recording, CLI ve voice testleri: `36 passed`

## Kullanım

```cmd
llmvoice audio devices
llmvoice voice record friday --duration 10
llmvoice voice references friday
```

## Sonraki Adaylar

1. Kayıt sırasında seviye metre ve sessizlik uyarısı göstermek
2. Kaydı kaydetmeden önce oynatmak
3. Mikrofon cihazını config içinde varsayılan olarak saklamak
