# Early Access Release

## Yapılanlar

- Python Early Access release `v0.1.8` yayınlandı.
- Tauri updater signing key çifti üretildi; GitHub Actions secrets olarak eklendi.
- Tauri public key config'e güncellendi.
- Updater artifact üretimi `createUpdaterArtifacts` ile etkinleştirildi.
- Desktop Early Access release `desktop-v1.0.0-ea.2` yayınlandı.
- `desktop-latest` updater channel `latest.json` ile güncellendi.
- Updater manifest, installer URL'si ve detached signature doğrulandı.

## Değişen Dosyalar

- `desktop/src-tauri/tauri.conf.json`
- `handoff/2026-09-17-early-access-release.md`
- `handoff/README.md`
- `handoff/AI-CONTEXT.md`

## Doğrulama

- Komut: `python -m pytest`
- Sonuç: `113 passed, 13 deselected`.
- Komut: `python -m pytest -m integration`
- Sonuç: `13 passed, 113 deselected`.
- Komut: `npm.cmd run build` (desktop)
- Sonuç: başarılı.
- GitHub CI run `35211674816`
- Sonuç: unit/build, FFmpeg integration, Windows installer ve Tauri build başarılı.
- GitHub Desktop release run `35222601754`
- Sonuç: signed installer, `.sig` ve `latest.json` başarıyla yayınlandı.
- Updater manifest
- Sonuç: `desktop-latest/latest.json`, `desktop-v1.0.0-ea.2` installer URL'sini ve signature'ı içeriyor.

## Bilinen Sorunlar

- `desktop-v1.0.0-ea.1` manifest üretimi etkin olmadan oluşturuldu; kullanılabilir sürüm `ea.2`.
- Installer manifest detached signature akışı hâlâ yalnızca SHA256/checksum seviyesinde.
- Çalışma ağacında kullanıcıya ait commitlenmemiş desktop UI değişiklikleri var; bunlara dokunulmadı.
- Yeni signing private key workspace dışındaki geçici key dosyasında ve GitHub secret'ta bulunuyor; güvenli yedeklenmeli.

## Sonraki Adım

1. Desktop UI değişikliklerini kullanıcı çalışması olarak ayrı incelemek ve uygun commit'e almak.
2. Installer manifest detached signature tasarımını uygulamak.
3. Tauri save/render ve multi-reference Windows integration testleri eklemek.
4. Signed updater ile gerçek Windows kurulum ve update geçişini test etmek.
