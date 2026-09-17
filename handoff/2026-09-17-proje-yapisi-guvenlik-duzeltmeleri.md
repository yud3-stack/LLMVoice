# Proje Yapısı ve Güvenlik Düzeltmeleri

## Yapılanlar

- Config bilinmeyen alanları artık reddediyor.
- Config `engine` ve `default_language` değerlerini doğruluyor.
- XTTS ve config aynı ortak 17 dil kodu kümesini kullanıyor.
- Desktop render artık voice dosyasının yalnızca ilkini değil, Python voice profile çözümünü kullanıyor.
- Desktop proje ayarları ve script kaydı `save_project` komutuyla birlikte yürütülüyor; script yazımı başarısız olursa metadata rollback ediliyor.
- Synthesis output path üzerinde exclusive job lock eklendi.
- Stale lock dosyaları 24 saat sonra temizlenebiliyor.
- Resume checkpoint indeksleri range, duplicate ve tip açısından doğrulanıyor.
- Release wheel metadata içinde package name doğrulanıyor.
- Installer manifest wheel boyutu ve indirilen artifact boyutunu doğruluyor.
- Config, pipeline, release ve desktop build regresyonları çalıştırıldı.

## Değişen Dosyalar

- `llmvoice/core/config.py`
- `llmvoice/core/exceptions.py`
- `llmvoice/service.py`
- `llmvoice/text/languages.py`
- `llmvoice/tts/xtts.py`
- `desktop/src-tauri/src/lib.rs`
- `desktop/src/App.tsx`
- `installer/install.ps1`
- `scripts/release.py`
- `tests/test_config.py`
- `tests/test_pipeline.py`
- `tests/test_release.py`

## Doğrulama

- Komut: `python -m pytest tests/test_config.py tests/test_pipeline.py tests/test_release.py`
- Sonuç: `25 passed` (odaklı regresyon suite)
- Komut: `python -m pytest`
- Sonuç: `112 passed, 13 deselected`
- Komut: `python -m pytest -m integration`
- Sonuç: `13 passed, 112 deselected`
- Komut: `cargo test`
- Sonuç: başarılı, 1 Rust unit test geçti.
- Komut: `cargo check --release --locked`
- Sonuç: başarılı.
- Komut: `npm.cmd run build`
- Sonuç: başarılı.
- Komut: `npm.cmd run tauri build -- --ci --no-bundle`
- Sonuç: başarılı; release executable üretildi.
- Komut: PowerShell installer regression scripts
- Sonuç: Python detection 13, native invocation 10, runtime profiles 6, publish transaction 7 case geçti.
- Komut: `git diff --check`
- Sonuç: yalnızca Windows CRLF uyarıları.

## Bilinen Sorunlar

- Installer manifest bütünlüğü hâlâ release signing key ile doğrulanmıyor; SHA256 ve HTTPS kontrolleri mevcut.
- React desktop tarafında eski imperative DOM/effect katmanı hâlâ sadeleştirilmeyi bekliyor.
- Desktop için gerçek Tauri davranış ve çoklu-reference integration testi henüz yok.
- Concurrent synthesis lock dosyası stale temizliği için 24 saatlik eşik kullanıyor.

## Sonraki Adım

1. Installer manifest detached signature akışını tasarlayıp uygulamak.
2. Desktop React proje menülerini React bileşenlerine taşımak.
3. Tauri save/render ve multi-reference akışlarına Windows integration testleri eklemek.
4. Full Python, integration, Rust ve Tauri release doğrulamasını tekrar çalıştırmak.
