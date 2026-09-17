# LLMVoice Handoff

Bu klasör Obsidian vault olarak kullanılabilir. Obsidian'da doğrudan `handoff/`
klasörünü açın.

Bu klasör uygulamanın bir parçası değildir; geliştirme oturumları arasında kısa
bağlam aktarmak için kullanılır. AI ile yeni bir oturuma başlamadan önce en güncel
notu ve ilgili dosyaları okuyun. Uzun logları nota kopyalamak yerine komutu,
özet sonucu ve kalan problemi yazın.

## Not Yapısı

- Her çalışma oturumu `YYYY-MM-DD-konu.md` biçiminde ayrı bir not kullanır.
- Notlarda yapılan değişiklikler, test sonucu, bilinen sorunlar ve sonraki adım bulunur.
- En güncel not: [[2026-09-17-early-access-release]]

## Oturum Protokolü

1. Çalışmaya başlamadan önce en güncel handoff notunu oku.
2. Sadece görevle ilgili dosyaları ve testleri incele.
3. Oturum sonunda `TEMPLATE.md` biçiminde yeni bir not oluştur.
4. Notu tarih, konu, değişen dosyalar, doğrulama ve sonraki adımla tamamla.

Dosya adları `YYYY-MM-DD-konu.md` biçiminde olmalıdır. Obsidian bağlantıları
konu veya dosya adı değiştiğinde güncellenmelidir.

## Çalışma Durumu

- Proje: LLMVoice
- Ana hedef: Yerel XTTS ses üretim kalitesini artırmak
- Son durum: Referans loudness normalization, çıktı normalization, akıllı chunking ve Türkçe telaffuz normalizasyonu eklendi.
