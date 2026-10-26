# Feeding Frenzy: Hand Hunter

Game makan-memakan ikan ala **Feeding Frenzy** yang dikendalikan dengan **gerakan tangan lewat webcam**.
Posisi tangan dideteksi memakai **color masking HSV + contour** dari OpenCV, tanpa MediaPipe atau deep learning, sehingga cukup ringan untuk dijalankan di CPU.

Project ini dibuat untuk mata kuliah **Pengolahan Citra dan Video (PCV)**.

Kode game dipisahkan ke beberapa modul Python berdasarkan tanggung jawabnya. File
`game_frenzy.py` tetap menjadi entry point untuk menjalankan permainan.

---

## Fitur

- **Kontrol tangan tanpa keyboard**: ikan pemain mengikuti posisi tangan (atau benda berwarna) yang terlihat di webcam.
- **Dash/boost**: dorong tangan mendekat ke kamera dan ikan akan melesat.
- **Sistem pertumbuhan 3 tingkat**: Kecil → Sedang → Besar.
- **4 tingkat musuh**, termasuk **Boss** dengan animasi berenang dan makan.
- **Kalibrasi warna otomatis** sebelum bermain, sehingga warna apa pun bisa dipakai sebagai penanda.
- **Skor terbaik tersimpan** di `skor_frenzy.txt`.
- **Partikel gelembung**, efek makan, dan efek dash.
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
- **Deteksi dash**: luas kontur dibandingkan dengan median 60 frame terakhir. Jika luasnya tiba-tiba
  lebih dari **1,65×** rata-rata (karena tangan didorong ke arah kamera), dash aktif selama 0,8 detik
  dengan cooldown 1,6 detik.
- **Kalibrasi**: game mengambil median nilai HSV dari kotak di tengah frame selama 2 detik, lalu membuat
  rentang warna `Hue ± 12`. Kalibrasi ditolak bila warna terlalu pucat (Saturation atau Value < 60).

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
| Dash / boost | Dorong tangan dengan cepat mendekat ke kamera |

### Keyboard & mouse

| Tombol | Fungsi |
|---|---|
| Klik **PLAY** / `Enter` / `Space` | Mulai (masuk ke layar kalibrasi) |
| Klik **OPTIONS** / `O` | Buka menu ukuran jendela |
| `K` | Mulai kalibrasi warna (di layar kalibrasi) |
| `M` | Tampilkan/sembunyikan preview webcam |
| `R` | Kembali ke menu utama (saat bermain / game over) |
| Klik **RETRY** | Main lagi (kalibrasi ulang) |
| Klik **MENU** | Kembali ke menu utama |
| `Esc` | Kembali ke menu dari Options/Kalibrasi; keluar dari game di layar lain |
| Klik **QUIT** / `Q` | Keluar dari game |

### Alur permainan

```
Main Menu ──PLAY──► Kalibrasi (tekan K, tahan tangan di kotak 2 detik) ──► Bermain ──► Game Over
    ▲                                                                                      │
    └──────────────────────────────── MENU ◄──────────────────────────────────────────────┤
                                       RETRY ──► Kalibrasi ◄──────────────────────────────┘
```

---

## Aturan Permainan

- Makan ikan yang **sama besar atau lebih kecil** untuk menambah skor dan tumbuh.
- Menyentuh ikan yang **lebih besar** membuat permainan berakhir (**Game Over**).
- Maksimal **tiga ikan besar** dan **dua Boss** aktif bersamaan dalam satu window; ikan kecil dan sedang tetap muncul seperti biasa.
- **Boss** selalu mematikan dan tidak dapat dimakan. Animasi makan Boss ditampilkan sebelum Game Over.
- Semakin tinggi skor, musuh muncul semakin cepat (jeda spawn minimal 0,8 detik).

### Pertumbuhan pemain

| Tingkat | Ukuran | Syarat (total ikan dimakan) |
|---|---|---|
| 1 | Kecil | 0 |
| 2 | Sedang | 8 |
| 3 | Besar | 20 |

### Musuh

| Tingkat | Jenis | Poin | Bisa dimakan saat pemain |
|---|---|---|---|
| 1 | Kecil | 10 | Kecil, Sedang, Besar |
| 2 | Sedang | 25 | Sedang, Besar |
| 3 | Besar | 60 | Besar |
| 4 | **Boss** | – | Tidak pernah (selalu mematikan) |

Boss baru muncul setelah pemain mencapai ukuran **Besar**.

---

## Konfigurasi

Pengaturan utama ada di [`game/config.py`](game/config.py):

| Konstanta | Default | Keterangan |
|---|---|---|
| `WIDTH`, `HEIGHT` | `960, 640` | Ukuran jendela awal |
| `CAM_W`, `CAM_H` | `320, 240` | Resolusi pemrosesan kamera (kecil supaya ringan) |
| `HSV_BAWAH`, `HSV_ATAS` | `[40,70,70]`–`[85,255,255]` | Rentang warna default (hijau terang) |
| `MIN_AREA` | `500` | Luas kontur minimum agar dianggap tangan |
| `DASH_RASIO` | `1.65` | Pengali luas kontur untuk memicu dash |
| `DASH_DURASI` | `0.8` | Durasi dash (detik) |
| `LERP_NORMAL` / `DASH_LERP` | `0.09` / `0.30` | Kehalusan gerak normal / saat dash |
| `GROWTH`, `MUSUH` | – | Tabel pertumbuhan pemain dan data musuh |

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
│   ├── bg_underwater.png # latar bawah laut
│   ├── player_*.png      # sprite pemain (small/medium/large)
│   ├── enemy_*.png       # sprite musuh dan variasinya
│   ├── Boss/swim/, Boss/eat/  # animasi Boss, masing-masing 6 frame
│   ├── bubble_*.png      # partikel gelembung
│   ├── dash_effect.png, eat_effect.png
│   └── coral.png, rock.png, seaweed.png  # dekorasi dasar laut
└── README.md
```

Aset bertanda variasi (misalnya `enemy_medium_2.png` dan `coral.png`) bersifat opsional. Bila tidak ada,
game tetap berjalan tanpa aset tersebut.

### Tanggung jawab modul

- `game/config.py`: ukuran layar, parameter kamera, aturan pertumbuhan, skor,
  dan pemetaan file aset.
- `game/assets.py`: memuat aset gambar dan menyediakan gambar fallback.
- `game/camera.py`: membaca webcam di thread terpisah, melacak warna, mendeteksi
  dash, dan mengambil sampel untuk kalibrasi.
- `game/entities.py`: perilaku ikan pemain dan ikan musuh, termasuk animasi Boss.
- `game/particles.py`: mengelola gelembung dan efek visual.
- `game/game.py`: mengatur ronde permainan, antarmuka, event, serta game loop.

---

## Troubleshooting

| Masalah | Solusi |
|---|---|
| `ERROR: Kamera tidak bisa dibuka!` | Pastikan webcam terpasang dan tidak sedang dipakai aplikasi lain. |
| Muncul tulisan **"TANGAN TIDAK TERDETEKSI!"** | Pakai benda berwarna lebih mencolok, perbaiki pencahayaan, lalu kalibrasi ulang. |
| Kalibrasi gagal: **warna terlalu pucat** | Warna penanda kurang jenuh. Gunakan warna cerah seperti hijau, biru, atau merah terang. |
| Ikan bergerak sendiri / melompat-lompat | Ada benda lain dengan warna serupa di latar. Jauhkan benda tersebut atau ganti warna penanda. |
| Dash terlalu sering / sulit aktif | Ubah nilai `DASH_RASIO` (lebih besar = lebih sulit aktif). |

---

## Pembuat

**rozaqnh168** — [github.com/rozaqnh168](https://github.com/rozaqnh168)
