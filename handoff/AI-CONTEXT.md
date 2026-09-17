# AI Geliştirme Bağlamı

## Proje

- `llmvoice/`: Python CLI ve ses işleme katmanı.
- `desktop/`: React + Vite + Tauri masaüstü stüdyosu.
- `handoff/`: Oturumlar arası geliştirme bağlamı; runtime verisi değildir.

## Çalışma Kuralları

- Önce en güncel handoff notunu oku, sonra yalnızca görevle ilgili dosyaları incele.
- Küçük ve mevcut mimariye uyan değişiklikleri tercih et.
- Python testleri için `pytest`, masaüstü frontend için `npm.cmd run build`, Rust/Tauri için `cargo check` kullan.
- Oturum sonunda `TEMPLATE.md` kullanarak yeni bir handoff notu yaz.

## Önemli Noktalar

- Tauri proje ve ses verilerini Windows'ta `%LOCALAPPDATA%/LLMVoice` altında saklar.
- Handoff notları repo içindeki Markdown dosyalarıdır ve uygulama UI'sına bağlı değildir.
- Ses üretimi yerel XTTS akışıyla yapılır; çıktı ve referans ses kalite kontrolleri Python tarafındadır.
- Config doğrulaması bilinmeyen alanları, geçersiz engine değerlerini ve desteklenmeyen dil kodlarını reddeder.
- Desktop render voice profile adını Python CLI'a verir; Python tarafı çoklu referansları çözer.
- Synthesis job output path üzerinde lock kullanır; resume checkpoint kayıtları doğrulanır.
- Son oturum notu: [[2026-09-17-early-access-release]]
