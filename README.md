# LLMVoice

LLMVoice, UTF-8 bir `.txt` dosyasını tamamen yerel çalışan bir voice-cloning
modeliyle uzun biçimli MP3 sese dönüştüren Windows CLI uygulamasıdır.

```text
TXT → normalize → doğal metin parçaları → XTTS-v2 → WAV birleştirme → MP3
```

Cloud API, telemetry veya harici veri gönderimi yoktur. Model ağırlıkları ilk
çalıştırmada indirildikten sonra sentez çevrimdışı yapılabilir.

> [!IMPORTANT]
> Varsayılan XTTS-v2 model ağırlıkları Coqui Public Model License (CPML)
> kapsamındadır ve **yalnızca ticari olmayan kullanıma** izin verir. Modeli veya
> çıktısını ticari amaçla kullanmadan önce farklı lisanslı bir motor ekleyin.
> LLMVoice kaynak kodunun MIT lisansı, model ağırlıklarının lisansını değiştirmez.

## Gereksinimler

- Windows 10 veya 11 (64 bit)
- Python 3.11–3.14
- 64-bit FFmpeg ve FFprobe (`PATH` içinde)
- Yaklaşık 4 GB model/disk alanı
- NVIDIA GPU önerilir; CPU fallback çalışır fakat uzun metinlerde çok yavaştır
- Voice cloning için tercihen 6–30 saniye temiz, tek konuşmacılı referans ses

XTTS-v2 Türkçe (`tr`) ve İngilizce (`en`) dahil 17 dili destekler.

## Sıfırdan kurulum

### 1. Python ve sanal ortam

[python.org](https://www.python.org/downloads/windows/) üzerinden Python kurarken
`Add python.exe to PATH` seçeneğini işaretleyin. Ardından proje klasöründe:

```cmd
py -3.11 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
```

Python 3.12 veya 3.13 de kullanılabilir.

### 2. FFmpeg

Windows Package Manager ile:

```cmd
winget install --id Gyan.FFmpeg.Shared
```

Terminali yeniden açın ve doğrulayın:

```cmd
ffmpeg -version
ffprobe -version
```

Alternatif Windows derlemeleri [FFmpeg indirme sayfasında](https://ffmpeg.org/download.html)
listelenir.

### 3. PyTorch

NVIDIA sürücünüzü güncelleyin. Güncel komutu
[PyTorch kurulum seçicisinden](https://pytorch.org/get-started/locally/) alın.
Örnek CUDA 13.0 kurulumu:

```cmd
pip install torch==2.11.0+cu130 torchaudio==2.11.0+cu130 torchcodec==0.13.0+cu130 --index-url https://download.pytorch.org/whl/cu130
```

CPU kurulumu:

```cmd
pip install torch torchaudio torchcodec --index-url https://download.pytorch.org/whl/cpu
```

Doğrulama:

```cmd
python -c "import torch; print(torch.cuda.is_available()); print(torch.__version__)"
```

`True` görülüyorsa `device: auto` CUDA'yı seçer. Sistem CUDA toolkit'inin ayrıca
kurulu olması çoğu hazır PyTorch wheel'i için gerekmez; uyumlu NVIDIA sürücüsü
gereklidir.

### 4. LLMVoice ve XTTS

```cmd
pip install -e ".[tts]"
```

Geliştirme/test bağımlılıkları:

```cmd
pip install -e ".[tts,dev]"
```

İlk `start` çağrısında XTTS-v2 modeli indirilebilir ve CPML koşullarını kabul
etmeniz istenebilir. Koşulları okuyup yalnızca kabul ediyorsanız onaylayın. Model
dosyaları `%LOCALAPPDATA%\LLMVoice\models` altında tutulur.

## Kullanım

Bir referans sesi kaydedin:

```cmd
llmvoice voice add friday samples\friday.wav
llmvoice voice list
```

Transcript'i aynı klasöre `transcript.mp3` olarak üretin:

```cmd
llmvoice start samples\transcript.txt --voice friday
```

Özel çıktı, dil ve hız:

```cmd
llmvoice start transcript.txt --voice friday --language tr --speed 0.95 -o output.mp3
```

Doğrudan referans dosyası:

```cmd
llmvoice start transcript.txt --voice "C:\Voices\friday.wav" --language en
```

Otomatik Türkçe/İngilizce dil sezgisi:

```cmd
llmvoice start transcript.txt --voice friday --language auto
```

Ses silme ve config görüntüleme:

```cmd
llmvoice voice remove friday
llmvoice config show
llmvoice --version
```

Hız aralığı `0.5–2.0` değeridir. Hız, birleştirilmiş seste FFmpeg `atempo`
filtresiyle uygulanır ve perde mümkün olduğunca korunur.

## Data dizini ve config

İlk komutta şu yapı otomatik oluşur:

```text
%LOCALAPPDATA%\LLMVoice\
├── voices\
├── models\
├── cache\
└── config.json
```

Varsayılan config:

```json
{
  "default_voice": null,
  "default_language": "tr",
  "default_speed": 1.0,
  "output_format": "mp3",
  "device": "auto",
  "engine": "xtts",
  "chunk_size": 220
}
```

`default_voice` değerini kayıtlı bir adla değiştirebilirsiniz. `device`,
`auto`, `cuda` veya `cpu` olabilir. Config'i uygulama kapalıyken geçerli JSON
olarak düzenleyin; hatalı değerler açıklayıcı bir hata üretir.

## Uzun metin davranışı

Metin önce boşlukları normalize eder, fakat içeriği yeniden yazmaz. Paragraf ve
cümle sınırları tercih edilerek `chunk_size` limitinde parçalara ayrılır. Her
parça ayrı WAV üretilir. XTTS konuşmacı embedding'i ilk parçada hesaplanıp sonraki
parçalarda tekrar kullanılır. Parçalar güvenli geçici dizinde birleştirilip MP3'e
atomik olarak yazılır. Başarılı veya hatalı işlemden sonra geçici iş dizini temizlenir.

Saatler süren transcript'lerde:

- CUDA kullanın ve başlangıçta kısa bir dosyayla ses kalitesini kontrol edin.
- Referans kaydında müzik, yankı, birden çok kişi ve uzun sessizliklerden kaçının.
- Çıktı için yeterli boş disk alanı bırakın.
- Model yeniden yüklenmesin diye her transcript'i tek `start` çağrısında çalıştırın.

## Mimari

```text
Typer CLI
  └─ VoiceService
      ├─ text normalizer / chunker / language detector
      ├─ TTSEngine
      │   └─ XTTSEngine (değiştirilebilir)
      ├─ voice reference cache
      └─ FFmpeg merge / MP3 encoder
```

CLI, Coqui API'sine doğrudan bağlı değildir. Yeni motor,
`llmvoice.tts.base.TTSEngine` arayüzünü uygulayıp factory'ye kaydedilerek
eklenebilir. Ağır model import'u lazy yapılır; unit testler model indirmez.

## Test

```cmd
pip install -e ".[dev]"
pytest
```

Unit testler text normalization/chunking, çıktı adı, voice çözümleme, config,
geçersiz input ve mock TTS servis akışını kapsar. Gerçek XTTS GPU sentezi,
model boyutu ve donanım gereksinimi nedeniyle unit testlere dahil değildir.

## Sorun giderme

### `FFmpeg and FFprobe were not found`

`winget install --id Gyan.FFmpeg.Shared` çalıştırın, terminali yeniden açın ve
`ffmpeg -version` ile doğrulayın.

### `CUDA was requested but ... cannot access a CUDA GPU`

NVIDIA sürücüsünü ve CUDA uyumlu PyTorch wheel'ini kontrol edin. Geçici olarak
config'te `"device": "cpu"` kullanabilirsiniz; CPU sentezi oldukça yavaştır.

### XTTS yüklenemiyor

- İlk indirme için internet bağlantısını ve disk alanını kontrol edin.
- CPML lisans istemini okuyup yanıtlayın.
- `pip show coqui-tts torch torchaudio torchcodec` ile paketleri doğrulayın.
- Ayrıntılı hata için komutu `--debug` ile çalıştırın.

### Referans ses okunamıyor

Dosyanın `.wav`, `.mp3`, `.flac`, `.m4a`, `.aac`, `.ogg` veya `.opus`
olduğunu ve FFmpeg'in dosyayı açabildiğini kontrol edin. LLMVoice orijinali
değiştirmez; kırpılmış mono 24 kHz WAV kopyasını cache altında üretir.

### Çıktıda kopukluk veya ton değişimi

Daha temiz bir referans kullanın, transcript noktalamasını düzeltin ve gerekirse
config'teki `chunk_size` değerini 160–300 aralığında deneyin. XTTS üretimi
deterministik değildir; uzun içerikte parçalar arasında küçük ton farkları
oluşabilir.
