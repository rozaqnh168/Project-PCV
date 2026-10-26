# Feeding Frenzy: Hand Hunter

Game makan-memakan ikan ala **Feeding Frenzy** yang dikendalikan dengan **gerakan tangan lewat webcam**.
Posisi tangan dideteksi memakai **color masking HSV + contour** dari OpenCV, tanpa MediaPipe atau deep learning, sehingga cukup ringan untuk dijalankan di CPU.

Project ini dibuat untuk mata kuliah **Pengolahan Citra dan Video (PCV)**.

Kode game dipisahkan ke beberapa modul Python berdasarkan tanggung jawabnya. File
`game_frenzy.py` tetap menjadi entry point untuk menjalankan permainan.

---

## Fitur

- **Kontrol tangan tanpa keyboard**: ikan pemain mengikuti posisi tangan (atau benda berwarna) yang terlihat di webcam.
- **Sistem pertumbuhan 3 tingkat berbasis poin**: Kecil → Sedang (80 poin) → Besar (400 poin).
- **Animasi pemain 8 frame** untuk berenang serta membuka dan menutup mulut saat makan.
- **4 tingkat musuh**, termasuk **Boss** dengan animasi berenang dan makan.
- **Musuh muncul 1,5× lebih sering**, sehingga lebih banyak ikan berada di window.
- **Kalibrasi warna sebelum bermain**: pilih warna penanda yang jelas dan tahan di kotak kamera selama 2 detik.
- **Skor terbaik tersimpan** di `skor_frenzy.txt` saat pemain mengalami Game Over.
- **Partikel gelembung** dan efek makan.
- **Menu Options** untuk mengganti ukuran jendela (800×600, 960×640, 1280×720).
- **Preview webcam + mask** di pojok kiri bawah untuk membantu debugging deteksi.
- **Fallback prosedural**: bila file aset tidak ada, sprite digambar langsung oleh kode.

---

## Cara Kerja (Pengolahan Citra)

Pemrosesan kamera berjalan di **thread terpisah** (`PelacakKamera`) agar game tetap lancar di 60 FPS.

```
Webcam (320x240)
   │  cv2.flip            → efek cermin
   ▼
BGR → HSV (cv2.cvtColor)
   │  cv2.inRange          → mask biner warna tangan
   ▼
Erode + Dilate             → buang noise bintik
   │  cv2.findContours     → ambil kontur terbesar (area ≥ 500 px)
   ▼
cv2.moments                → titik pusat (centroid) tangan
   │
   ▼
Petakan ke layar game + LERP → gerak ikan yang halus seperti di air
```

- **Translasi koordinat**: posisi tangan di kamera dipetakan proporsional ke layar,
  `x_game = (x_tangan / CAM_W) * WIDTH`.
- **Linear interpolation (LERP)**: ikan tidak langsung menempel ke posisi tangan, tetapi bergerak sebagian
  tiap frame (`x += (target - x) * faktor`) sehingga terasa seperti bergerak di dalam air.
- **Kalibrasi**: dari menu utama, tekan **PLAY**, lalu tekan `K`. Tahan penanda di kotak tengah
  selama 2 detik. Program mengambil median HSV sampel dan membuat rentang `Hue ± 12`, dengan
  batas Saturation dan Value minimal 60. Kalibrasi ditolak bila penanda terlalu pucat.
- Kalibrasi dilakukan saat memulai permainan dari menu. Tombol **RETRY** setelah Game Over
  memulai hitung mundur persiapan 3 detik, lalu memulai ronde baru dengan rentang warna hasil
  kalibrasi sebelumnya.

---

## Kebutuhan

- Python 3.10 atau lebih baru (sudah diuji di Python 3.14)
- Webcam
- Benda berwarna mencolok sebagai penanda tangan, misalnya sarung tangan atau karton **hijau terang**
  (warna default). Warna lain juga bisa dipakai lewat kalibrasi.

Library Python:

| Library | Kegunaan |
|---|---|
| `opencv-python` | Akses webcam & pengolahan citra |
| `numpy` | Operasi array / HSV |
| `pygame` | Render grafis game serta input keyboard & mouse |

---

## Instalasi

```bash
git clone https://github.com/rozaqnh168/Project-PCV.git
cd Project-PCV

# (opsional) buat virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install opencv-python numpy pygame
```

## Menjalankan

```bash
python game_frenzy.py
```

---

## Kontrol

### Saat bermain

| Aksi | Cara |
|---|---|
| Menggerakkan ikan | Gerakkan tangan/benda berwarna di depan webcam |

### Keyboard & mouse

| Tombol | Fungsi |
|---|---|
| Klik **PLAY** / `Enter` / `Space` | Mulai (masuk ke layar kalibrasi) |
| Klik **OPTIONS** / `O` | Buka menu ukuran jendela |
| `K` | Mulai kalibrasi warna (di layar kalibrasi) |
| `M` | Tampilkan/sembunyikan preview webcam |
| `R` | Saat bermain: kembali ke menu utama; saat Game Over: mulai ulang setelah hitung mundur 3 detik tanpa kalibrasi |
| Klik **RETRY** | Mulai ulang setelah hitung mundur 3 detik tanpa kalibrasi |
| Klik **MENU** | Kembali ke menu utama |
| `Esc` | Kembali ke menu dari Options/Kalibrasi; keluar dari game di layar lain |
| Klik **QUIT** / `Q` | Keluar dari game |

### Alur permainan

```
Main Menu ──PLAY──► Kalibrasi (tekan K, tahan tangan di kotak 2 detik) ──► Bermain ──► Game Over
Game Over ──RETRY──► Persiapan 3 detik (tanpa kalibrasi) ──► Bermain
Game Over ──MENU─────────────────────────────────────────────────────────────► Main Menu
```

---

## Aturan Permainan

- Makan ikan yang **sama besar atau lebih kecil** untuk menambah skor dan tumbuh.
- Menyentuh ikan yang **lebih besar** membuat permainan berakhir (**Game Over**).
- Maksimal **tiga ikan besar** dan **dua Boss** aktif bersamaan dalam satu window; ikan kecil dan sedang tetap muncul seperti biasa.
- **Boss** selalu mematikan dan tidak dapat dimakan. Animasi makan Boss ditampilkan sebelum Game Over.
- Semakin tinggi skor, musuh muncul semakin cepat. Frekuensi spawn telah dinaikkan **1,5×**, dengan jeda minimal sekitar **0,53 detik**.

### Pertumbuhan pemain

Pertumbuhan ditentukan oleh **total poin**, bukan jumlah ikan yang dimakan. Indikator ukuran di HUD menggunakan aset `saatkecil.png`, `saatsedang.png`, dan `saatbesar.png` sesuai level aktif.

| Tingkat | Ukuran | Syarat (total poin) |
|---|---|---|
| 1 | Kecil | 0 |
| 2 | Sedang | 80 |
| 3 | Besar | 400 |

Ukuran sprite pemain dan musuh ditentukan oleh radius di `game/config.py`. Radius pemain Kecil/Sedang/Besar adalah **23/37/54**; radius musuh setara adalah **13/27/44**. Radius Boss adalah **80**. Radius juga dipakai pada perhitungan tabrakan.

### Musuh

| Tingkat | Jenis | Poin | Bisa dimakan saat pemain |
|---|---|---|---|
| 1 | Kecil | 10 | Kecil, Sedang, Besar |
| 2 | Sedang | 25 | Sedang, Besar |
| 3 | Besar | 60 | Besar |
| 4 | **Boss** | – | Tidak pernah (selalu mematikan) |

Boss baru dapat muncul setelah pemain mencapai ukuran **Besar**. Dalam satu ronde, maksimal ada
tiga ikan Besar dan dua Boss aktif sekaligus. Ikan yang bisa dimakan menghilang dan menambah
poin; kontak dengan ikan lebih besar mengakhiri ronde. Jika penyebabnya Boss, animasi Boss makan
ditampilkan sebelum layar Game Over.

---

## Konfigurasi

Pengaturan utama ada di [`game/config.py`](game/config.py):

| Konstanta | Default | Keterangan |
|---|---|---|
| `WIDTH`, `HEIGHT` | `960, 640` | Ukuran jendela awal |
| `CAM_W`, `CAM_H` | `320, 240` | Resolusi pemrosesan kamera (kecil supaya ringan) |
| `HSV_BAWAH`, `HSV_ATAS` | `[40,70,70]`–`[85,255,255]` | Rentang warna default (hijau terang) |
| `MIN_AREA` | `500` | Luas kontur minimum agar dianggap tangan |
| `LERP_NORMAL` | `0.09` | Kehalusan gerak ikan mengikuti tangan |
| `GROWTH` | poin total `0 / 80 / 400`; radius `23 / 37 / 54` | Ambang pertumbuhan dan ukuran pemain |
| `MUSUH` | radius `13 / 27 / 44 / 80` | Radius, kecepatan, dan poin musuh level 1 sampai Boss |
| `BATAS_MUSUH` | `{3: 3, 4: 2}` | Batas ikan Besar dan Boss yang aktif |

---

## Struktur Folder

```
Project-PCV/
├── game_frenzy.py        # entry point untuk menjalankan game
├── game/
│   ├── __init__.py       # package modul game
│   ├── config.py         # konfigurasi, aturan, dan pemetaan aset
│   ├── assets.py         # AssetManager dan fallback sprite
│   ├── camera.py         # PelacakKamera dan kalibrasi warna
│   ├── entities.py       # IkanPemain dan IkanMusuh
│   ├── particles.py      # SistemPartikel
│   └── game.py           # class Game: loop, input, update, dan render
├── skor_frenzy.txt       # skor terbaik (dibuat/diperbarui otomatis)
├── assets/
│   ├── Mainmenu.png      # panel menu utama
│   ├── Gameover_ui.png   # panel game over (dipakai game)
│   ├── Score.png         # panel skor di HUD
│   ├── saatkecil.png, saatsedang.png, saatbesar.png  # indikator ukuran pemain
│   ├── bg_underwater.png # latar bawah laut
│   ├── ikanp_frame_01.png ... ikanp_frame_08.png  # animasi pemain berenang/makan
│   ├── enemy_*.png       # sprite musuh dan variasinya
│   ├── Boss/swim/, Boss/eat/  # animasi Boss, masing-masing 6 frame
│   ├── bubble_*.png      # partikel gelembung
│   ├── eat_effect.png  # efek visual saat ikan dimakan
│   └── coral.png, rock.png, seaweed.png  # dekorasi dasar laut
└── README.md
```

Aset bertanda variasi (misalnya `enemy_medium_2.png` dan `coral.png`) bersifat opsional. Bila tidak ada,
game tetap berjalan tanpa aset tersebut.

### Tanggung jawab modul

- `game/config.py`: ukuran layar, parameter kamera, aturan pertumbuhan, skor,
  dan pemetaan file aset.
- `game/assets.py`: memuat aset gambar dan menyediakan gambar fallback.
- `game/camera.py`: membaca webcam di thread terpisah, melacak warna, dan mengambil
  sampel untuk kalibrasi.
- `game/entities.py`: perilaku ikan pemain dan ikan musuh, termasuk animasi Boss.
- `game/particles.py`: mengelola gelembung dan efek visual.
- `game/game.py`: mengatur ronde permainan, antarmuka, event, serta game loop.

---

## Troubleshooting

| Masalah | Solusi |
|---|---|
| `ERROR: Kamera tidak bisa dibuka!` | Pastikan webcam terpasang dan tidak sedang dipakai aplikasi lain. |
| Muncul tulisan **"TANGAN TIDAK TERDETEKSI!"** | Pakai penanda berwarna lebih mencolok dan perbaiki pencahayaan. Untuk mengkalibrasi ulang, kembali ke menu, mulai permainan baru, lalu tekan `K` di layar kalibrasi. |
| Kalibrasi gagal: **warna terlalu pucat** | Warna penanda kurang jenuh. Gunakan warna cerah seperti hijau, biru, atau merah terang. |
| Ikan bergerak sendiri / melompat-lompat | Ada benda lain dengan warna serupa di latar. Jauhkan benda tersebut atau ganti warna penanda. |

---

## Pembuat

**rozaqnh168** — [github.com/rozaqnh168](https://github.com/rozaqnh168)
