"""
FEEDING FRENZY: HAND HUNTER
===========================
Game makan-menan ala Feeding Frenzy yang dikontrol penuh lewat webcam dengan
deteksi warna tangan (OpenCV color masking) — TANPA MediaPipe/deep-learning,
murni HSV threshold + contour yang ringan di CPU.

Kontrol (tanpa keyboard saat bermain!):
  - Gerakkan tangan berwarna     -> ikan pemain mengikuti (lerp halus)
  - Dorong tangan mendekat kamera -> DASH / boost (area kontur membesar cepat)
  - Makan ikan yang lebih kecil  -> skor + tumbuh (Small -> Medium -> Large)
  - Kena ikan yang lebih besar   -> GAME OVER

Struktur file (OOP modular):
  AssetManager   -> pemuat aset visual (PNG eksternal / fallback prosedural)
  PelacakKamera  -> thread background: baca webcam, HSV mask, contour, dash
  IkanPemain     -> ikan yang dikendalikan tangan (growth system)
  IkanMusuh      -> AI ikan musuh yang melintas kiri/kanan
  SistemPartikel -> gelembung dekoratif + ledakan saat ikan dimakan
  Game           -> state machine + game loop utama

Cara mengganti aset dengan PNG dari itch.io / Unity / Sketchfab:
  1. Buat folder  assets/  di samping file ini.
  2. Letakkan PNG transparan dengan nama persis seperti di ASSET_PATHS
     (mis. assets/player_small.png, assets/enemy_shark.png, dst).
  3. Jalankan ulang — AssetManager otomatis memakai PNG bila ada;
     bila tidak ada, game memakai gambar fallback yang digambar kode.
"""

import cv2
import numpy as np
import pygame
import random
import threading
import time
import os

# ==========================================
# 1. KONFIGURASI GLOBAL
# ==========================================
WIDTH, HEIGHT = 960, 640
FPS           = 60

# Kamera diproses di resolusi kecil agar ringan (CPU-friendly)
CAM_W, CAM_H  = 320, 240

# --- Deteksi warna (HSV). Default: HIJAU terang (sarung tangan/karton) ---
# Ganti angka ini bila memakai warna lain, atau kalibrasi dengan tombol [C].
HSV_BAWAH = np.array([40, 70, 70])
HSV_ATAS  = np.array([85, 255, 255])
MIN_AREA  = 500          # area kontur minimum agar dianggap "tangan"

# --- Mekanik dash: dorong tangan ke depan kamera ---
DASH_RASIO      = 1.65   # area kontur harus > 1.65x rata-rata normal
DASH_COOlDOWN   = 1.6    # jeda antar dash (detik)
DASH_DURASI     = 0.8    # durasi boost (detik)
DASH_LERP       = 0.30   # kecepatan lerp saat dash (default 0.09)
LERP_NORMAL     = 0.09   # kecepatan lerp normal (fluid underwater physics)

# --- Sistem pertumbuhan pemain (3 tingkat: Small / Medium / Large) ---
# "makan_total" adalah jumlah ikan yang harus dimakan kumulatif untuk naik tingkat.
GROWTH = [
    {"lvl": 1, "nama": "KECIL",   "radius": 20, "makan_total": 0},
    {"lvl": 2, "nama": "SEDANG",  "radius": 34, "makan_total": 8},
    {"lvl": 3, "nama": "BESAR",   "radius": 52, "makan_total": 20},
]

# --- Tingkat ikan musuh (1 kecil .. 4 BOSS/Leviathan) ---
# Ikan pemain hanya bisa memakan musuh yang tingkatnya <= tingkat dirinya.
# Boss (4) SELALU mematikan, sebesar apa pun pemainnya.
MUSUH = {
    1: {"radius": 16, "kecepatan": (2.0, 3.6), "poin": 10,  "nama": "kecil"},
    2: {"radius": 30, "kecepatan": (1.5, 2.6), "poin": 25,  "nama": "sedang"},
    3: {"radius": 48, "kecepatan": (1.0, 1.8), "poin": 60,  "nama": "besar"},
    4: {"radius": 95, "kecepatan": (0.7, 1.1), "poin": 0,   "nama": "BOSS"},
}

SKOR_FILE = "skor_frenzy.txt"
KUNING    = (255, 220, 60)


# ==========================================
# 2. ASSET MANAGER  (titik integrasi aset eksternal)
# ==========================================
# ALUR PENGGANTIAN ASET (itch.io / Unity Asset Store / Sketchfab):
#   -> Unduh sprite PNG transparan (mis. "Pixel Fishing Pack" dari itch.io,
#      atau render frame model ikan 2D dari Sketchfab/Unity).
#   -> Simpan ke folder  assets/  dengan nama file di bawah ini.
#   -> Sprite otomatis diskalakan ke radius kolisi; pastikan PNG menghadap
#      KE KANAN (game membalik otomatis saat ikan berenang ke kiri).
ASSET_PATHS = {
    "player_small":  "assets/player_small.png",
    "player_medium": "assets/player_medium.png",
    "player_large":  "assets/player_large.png",
    "enemy_small":   "assets/enemy_small.png",
    "enemy_medium":  "assets/enemy_medium.png",
    "enemy_large":   "assets/enemy_large.png",
    "enemy_boss":    "assets/enemy_boss.png",     # ganti dengan hiu/raja ikan
    "bg_underwater": "assets/bg_underwater.png",  # latar dasar laut
    "bubble":        "assets/bubble_particle.png" # gelembung partikel
}


class AssetManager:
    """Pemuat aset: pakai PNG eksternal bila ada, jika tidak gambar fallback."""

    def __init__(self):
        self.sprites = {}
        for nama, path in ASSET_PATHS.items():
            if os.path.exists(path):
                img = pygame.image.load(path).convert_alpha()
                self.sprites[nama] = ("file", img)
            else:
                self.sprites[nama] = ("fallback", None)  # digambar belakangan

    def ambil(self, nama, radius=None):
        """Kembalikan surface sprite, diskalakan ke `radius` (kolisi bulat).
        Bila aset PNG belum ada, pakai gambar fallback yang digambar kode."""
        jenis, img = self.sprites[nama]
        if jenis == "file":
            if radius is not None:
                ukuran = (radius * 2, radius * 2)
                if img.get_size() != ukuran:
                    img = pygame.transform.smoothscale(img, ukuran)
                    self.sprites[nama] = ("file", img)
            return img
        # ---- fallback prosedural (digambar langsung dengan pygame.draw) ----
        r = radius or 20
        return self._gambar_fallback(nama, r)

    def _gambar_fallback(self, nama, r):
        s = pygame.Surface((r * 2 + 10, r * 2 + 10), pygame.SRCALPHA)
        cx, cy = r + 5, r + 5
        if nama == "bubble":
            pygame.draw.circle(s, (200, 235, 255), (cx, cy), max(2, r // 2), 2)
            return s
        if nama == "bg_underwater":
            return None  # latar digambar prosedural oleh Game
        # ---- bentuk ikan generik; warna membedakan tingkat ----
        palet = {
            "player_small": (255, 170, 40), "player_medium": (255, 130, 30),
            "player_large": (255, 90, 20),  "enemy_small": (120, 200, 240),
            "enemy_medium": (80, 160, 230), "enemy_large": (70, 110, 220),
            "enemy_boss": (60, 70, 160),
        }
        warna = palet.get(nama, (200, 200, 200))
        gelap = tuple(int(c * 0.65) for c in warna)
        # badan
        pygame.draw.ellipse(s, warna, (cx - r, cy - r * 0.7, r * 1.6, r * 1.4))
        # ekor
        pygame.draw.polygon(s, gelap, [(cx - r, cy), (cx - r - 14, cy - r * 0.5),
                                       (cx - r - 14, cy + r * 0.5)])
        # sirip atas
        pygame.draw.polygon(s, gelap, [(cx - r * 0.2, cy - r * 0.7),
                                       (cx, cy - r * 1.05), (cx + r * 0.3, cy - r * 0.6)])
        # mata
        pygame.draw.circle(s, (255, 255, 255), (int(cx + r * 0.45), int(cy - r * 0.2)), max(3, r // 5))
        pygame.draw.circle(s, (20, 20, 20), (int(cx + r * 0.5), int(cy - r * 0.2)), max(2, r // 9))
        if nama == "enemy_boss":  # boss: tambahkan gigi
            pygame.draw.polygon(s, (255, 255, 255),
                                [(cx + r * 0.6, cy + r * 0.25), (cx + r * 0.45, cy + r * 0.5),
                                 (cx + r * 0.3, cy + r * 0.25)])
        return s

    def punya_eksternal(self, nama):
        return self.sprites[nama][0] == "file"


# ==========================================
# 3. PELACAK KAMERA (thread background, OpenCV)
# ==========================================
class PelacakKamera:
    """Membaca & memproses webcam di thread TERPISAH supaya game loop
    pygame tetap 60 FPS mulus meski OpenCV bekerja terus.

    Hasil pemrosesan (posisi tangan, luas area, frame, mask) disimpan ke
    atribut yang aman dibaca dari thread utama lewat threading.Lock.
    """

    def __init__(self):
        self.cap = cv2.VideoCapture(0)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAM_W)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_H)
        self.buka = self.cap.isOpened()

        self.lock = threading.Lock()
        self.frame = None            # frame terakhir (untuk panel preview)
        self.mask = None             # mask biner hasil HSV threshold
        self.pos = None              # (x, y) pusat kontur terbesar, koordinat kamera
        self.area = 0                # luas kontur (px^2) -> untuk deteksi DASH

        self.riwayat_area = []       # baseline area normal (median 60 frame)
        self.dash_aktif = False      # sedang boost?
        self.dash_mulai = 0.0
        self.dash_terakhir = 0.0     # waktu dash sebelumnya (cooldown)

        self.aktif = True
        if self.buka:
            self.thread = threading.Thread(target=self._loop, daemon=True)
            self.thread.start()

    # ---------------- thread pemrosesan ----------------
    def _loop(self):
        while self.aktif:
            ret, frame = self.cap.read()
            if not ret:
                time.sleep(0.01)
                continue
            frame = cv2.flip(frame, 1)          # efek cermin
            if frame.shape[1] != CAM_W or frame.shape[0] != CAM_H:
                frame = cv2.resize(frame, (CAM_W, CAM_H))  # paksa ukuran tetap

            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            mask = cv2.inRange(hsv, HSV_BAWAH, HSV_ATAS)
            mask = cv2.erode(mask, None, iterations=2)   # buang noise bintik
            mask = cv2.dilate(mask, None, iterations=2)

            pos, area = None, 0
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL,
                                           cv2.CHAIN_APPROX_SIMPLE)
            if contours:
                terbesar = max(contours, key=cv2.contourArea)
                area = cv2.contourArea(terbesar)
                if area >= MIN_AREA:
                    M = cv2.moments(terbesar)
                    if M["m00"] > 0:
                        pos = (int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"]))
                        cv2.circle(frame, pos, 8, (0, 0, 255), -1)  # penanda debug

            with self.lock:
                self.frame = frame
                self.mask = mask
                self.pos = pos
                self.area = area

            time.sleep(0.004)  # ±150-200 fps proses, hemat CPU

    # ---------------- akses dari thread utama ----------------
    def baca(self):
        """Ambil snapshot aman: (frame, mask, pos, area, dash_aktif)."""
        with self.lock:
            return self.frame, self.mask, self.pos, self.area, self.dash_aktif

    def cek_dash(self, area):
        """DETEKSI DASH: jika area kontur meledak cepat (tangan didorong ke
        kamera -> objek terlihat jauh lebih besar), aktifkan boost."""
        now = time.time()
        if self.dash_aktif or now - self.dash_terakhir < DASH_COOlDOWN:
            self._simpan_baseline(area)
            return False
        self.riwayat_area.append(area)
        if len(self.riwayat_area) > 60:
            self.riwayat_area.pop(0)
        if len(self.riwayat_area) >= 12:
            baseline = np.median(self.riwayat_area)
            if baseline > MIN_AREA and area > baseline * DASH_RASIO:
                self.dash_aktif = True
                self.dash_mulai = now
                self.dash_terakhir = now
                self.riwayat_area.clear()   # reset baseline pasca-dash
                return True
        return False

    def _simpan_baseline(self, area):
        self.riwayat_area.append(area)
        if len(self.riwayat_area) > 60:
            self.riwayat_area.pop(0)

    def update_dash(self):
        """Matikan dash bila durasinya habis (dipanggil tiap frame)."""
        if self.dash_aktif and time.time() - self.dash_mulai >= DASH_DURASI:
            self.dash_aktif = False
            self.riwayat_area.clear()
        return self.dash_aktif

    def sampel_kalibrasi(self, frame, kumpulan):
        """Rekam median HSV dari kotak tengah frame (untuk tombol [C])."""
        if frame is None:
            return
        x1, y1 = CAM_W // 2 - 40, CAM_H // 2 - 40
        x2, y2 = CAM_W // 2 + 40, CAM_H // 2 + 40
        roi = frame[y1:y2, x1:x2]
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        h, s, v = cv2.split(hsv)
        kumpulan.append((int(np.median(h)), int(np.median(s)), int(np.median(v))))

    def stop(self):
        self.aktif = False
        if self.buka:
            time.sleep(0.05)
            self.cap.release()


# ==========================================
# 4. KELAS IKAN
# ==========================================
class IkanPemain:
    """Ikan yang dikendalikan tangan. Punya sistem pertumbuhan 3 tingkat."""

    def __init__(self, assets: AssetManager):
        self.assets = assets
        self.x, self.y = WIDTH // 2, HEIGHT // 2
        self.makan = 0                 # jumlah ikan yang sudah dimakan
        self.level = 1                 # 1=KECIL, 2=SEDANG, 3=BESAR
        self.radius = GROWTH[0]["radius"]
        self.mati = False
        self.dash = False
        self.arah = 1                  # 1 kanan / -1 kiri (untuk flip sprite)

    @property
    def sprite(self):
        return self.assets.ambil(f"player_{GROWTH[self.level-1]['nama'].lower()}", self.radius)

    def makan_ikan(self):
        """Naikkan hitungan makan; bila melewati ambang, tumbuh ke level berikut."""
        self.makan += 1
        for g in GROWTH:
            if self.makan >= g["makan_total"]:
                level_baru = g["lvl"]
        if level_baru > self.level:
            self.level = level_baru
            self.radius = GROWTH[self.level - 1]["radius"]
            return True  # bertumbuh!
        return False

    def update(self, target, lerp_faktor, dt):
        """=== TRANSLASI KOORDINAT (bagian terpenting) ===
        `target` adalah posisi tangan dalam koordinat KAMERA (0..CAM_W, 0..CAM_H).
        Kita petakan proporsional ke jendela game:
            pos_x_game = (tangan_x / CAM_W) * WIDTH
        Lalu ikan TIDAK langsung menempel ke titik itu, melainkan bergerak
        sebagian saja tiap frame (LINEAR INTERPOLATION / LERP):
            x += (target - x) * faktor
        Faktor kecil (0.09) memberi efek fisika air yang 'lengket & halus';
        saat DASH faktor dinaikkan agar ikan melesat. Skala faktor oleh dt
        supaya kecepatan konsisten di semua FPS.
        """
        if target is None:
            return
        tx = (target[0] / CAM_W) * WIDTH
        ty = (target[1] / CAM_H) * HEIGHT
        k = 1 - (1 - lerp_faktor) ** (dt * 60)   # normalisasi ke 60 fps
        if tx != self.x:
            self.arah = 1 if tx > self.x else -1
        self.x += (tx - self.x) * k
        self.y += (ty - self.y) * k


class IkanMusuh:
    """Ikan musuh yang melintas dari kiri->kanan atau kanan->kiri.
    Tingkat 1-3 biasa; tingkat 4 = BOSS (selalu mematikan)."""

    def __init__(self, assets: AssetManager, level, y=None):
        self.assets = assets
        cfg = MUSUH[level]
        self.level = level
        self.radius = cfg["radius"]
        self.poin = cfg["poin"]
        # arah acak: 1 = berenang ke kanan (masuk dari kiri), -1 = sebaliknya
        self.arah = random.choice([1, -1])
        self.vx = random.uniform(*cfg["kecepatan"]) * self.arah
        self.x = -self.radius - 30 if self.arah == 1 else WIDTH + self.radius + 30
        self.y = y if y is not None else random.randint(self.radius + 20,
                                                        HEIGHT - self.radius - 20)
        self.wiggle = random.uniform(0, 6.28)   # gerak naik-turun sinus kecil

    def update(self, dt):
        self.x += self.vx * dt * 60
        self.wiggle += 0.05
        self.y += np.sin(self.wiggle) * 0.4     # ikan 'bernapas' naik turun

    @property
    def sprite(self):
        nama = {1: "enemy_small", 2: "enemy_medium",
                3: "enemy_large", 4: "enemy_boss"}[self.level]
        return self.assets.ambil(nama, self.radius)

    def di_luar_layar(self):
        return (self.arah == 1 and self.x > WIDTH + self.radius + 40) or \
               (self.arah == -1 and self.x < -self.radius - 40)


# ==========================================
# 5. SISTEM PARTIKEL (gelembung)
# ==========================================
class SistemPartikel:
    """Gelembung dekoratif: muncul ambient dari dasar, mengikuti ikan pemain,
    dan meledak saat ikan dimakan."""

    def __init__(self, assets: AssetManager):
        self.assets = assets
        self.partikel = []

    def _tambah(self, x, y, vx, vy, radius, umur):
        self.partikel.append({"x": x, "y": y, "vx": vx, "vy": vy,
                              "r": radius, "umur": umur, "umur0": umur})

    def ambient(self):
        """Gelembung acak dari dasar laut."""
        self._tambah(random.randint(0, WIDTH), HEIGHT + 10,
                     random.uniform(-0.3, 0.3), random.uniform(-1.5, -0.6),
                     random.randint(3, 9), random.randint(120, 260))

    def jejak(self, x, y, dash=False):
        """Gelembung kecil di belakang ikan pemain (lebih banyak saat dash)."""
        n = 3 if dash else 1
        for _ in range(n):
            self._tambah(x + random.uniform(-6, 6), y + random.uniform(-6, 6),
                         random.uniform(-0.5, 0.5), random.uniform(-2.4, -1.2),
                         random.randint(2, 6), random.randint(20, 45))

    def ledakan(self, x, y, n=18):
        """Ledakan gelembung saat ikan dimakan."""
        for _ in range(n):
            sudut = random.uniform(0, 6.28)
            kec = random.uniform(0.8, 4)
            self._tambah(x, y, kec * np.cos(sudut), kec * np.sin(sudut) - 1,
                         random.randint(3, 10), random.randint(25, 55))

    def update(self):
        for p in self.partikel[:]:
            p["x"] += p["vx"]
            p["y"] += p["vy"]
            p["vy"] *= 0.99            # gesekan air
            p["umur"] -= 1
            if p["umur"] <= 0 or p["y"] < -20:
                self.partikel.remove(p)

    def gambar(self, surf):
        for p in self.partikel:
            alfa = p["umur"] / p["umur0"]
            r = max(1, int(p["r"] * (0.5 + 0.5 * alfa)))
            sprite = self.assets.ambil("bubble", r)
            sprite.set_alpha(int(150 * alfa))
            surf.blit(sprite, (int(p["x"] - r), int(p["y"] - r)))


# ==========================================
# 6. GAME UTAMA
# ==========================================
class Game:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("Feeding Frenzy: Hand Hunter")
        self.clock = pygame.time.Clock()
        self.font_besar  = pygame.font.SysFont("dejavusansbold", 48, bold=True)
        self.font_sedang = pygame.font.SysFont("dejavusans", 28)
        self.font_kecil  = pygame.font.SysFont("dejavusans", 20)

        self.assets = AssetManager()
        self.kamera = PelacakKamera()
        if not self.kamera.buka:
            raise RuntimeError("Kamera tidak bisa dibuka!")

        self.bg = self._buat_bg()
        self.state = "SIAP"          # SIAP -> MAIN -> OVER
        self.reset()

        self.panel_tampil = True
        self.kalib_sampel = []
        self.kalib_timer = 0.0

    # ---------------- latar prosedural ----------------
    def _buat_bg(self):
        """Latar dasar laut: gradasi biru + siluet rumput laut.
        (Otomatis tergantikan bila assets/bg_underwater.png tersedia.)"""
        if self.assets.punya_eksternal("bg_underwater"):
            img = self.assets.sprites["bg_underwater"][1]
            return pygame.transform.smoothscale(img, (WIDTH, HEIGHT))
        bg = pygame.Surface((WIDTH, HEIGHT))
        for y in range(HEIGHT):
            t = y / HEIGHT
            warna = (int(10 + 25 * t), int(60 + 60 * t), int(110 + 70 * t))
            pygame.draw.line(bg, warna, (0, y), (WIDTH, y))
        for i in range(0, WIDTH, 90):  # rumput laut siluet
            tinggi = random.randint(50, 130)
            titik = [(i, HEIGHT)]
            for j in range(1, 6):
                titik.append((i + random.randint(-14, 14), HEIGHT - tinggi * j // 5))
            pygame.draw.lines(bg, (20, 90, 70), False, titik, 6)
        return bg

    def reset(self):
        self.pemain = IkanPemain(self.assets)
        self.musuh = []
        self.partikel = SistemPartikel(self.assets)
        self.skor = 0
        self.terbaik = self.muat_terbaik()
        self.spawn_timer = 0.0
        self.ambil_pos = None      # popup "+10" melayang
        self.pesan_makan = 0

    def muat_terbaik(self):
        try:
            with open(SKOR_FILE) as f:
                return int(f.read().strip())
        except Exception:
            return 0

    def simpan_terbaik(self):
        try:
            with open(SKOR_FILE, "w") as f:
                f.write(str(max(self.terbaik, self.skor)))
        except Exception:
            pass

    # ---------------- spawn musuh ----------------
    def _pilih_level_musuh(self):
        """Distribusi musuh menyesuaikan level pemain agar selalu ada yang
        bisa dimakan DAN ancaman — rasa Feeding Frenzy yang seimbang."""
        lvl = self.pemain.level
        if lvl == 1:
            return random.choices([1, 2], weights=[0.65, 0.35])[0]
        if lvl == 2:
            return random.choices([1, 2, 3], weights=[0.50, 0.35, 0.15])[0]
        return random.choices([1, 2, 3, 4],
                              weights=[0.32, 0.34, 0.20, 0.14])[0]

    def update_spawner(self, dt):
        self.spawn_timer += dt
        interval = max(0.8, 2.0 - self.skor * 0.004)
        if self.spawn_timer >= interval:
            self.spawn_timer = 0
            self.musuh.append(IkanMusuh(self.assets, self._pilih_level_musuh()))

    # ---------------- tabrakan & makan ----------------
    def update_tabrakan(self):
        p = self.pemain
        for m in self.musuh[:]:
            jarak = ((m.x - p.x) ** 2 + (m.y - p.y) ** 2) ** 0.5
            if jarak < m.radius + p.radius - 6:   # -6 = toleransi biar adil
                if m.level <= p.level:            # musuh lebih kecil -> MAKAN
                    self.skor += m.poin
                    tumbuh = p.makan_ikan()
                    self.partikel.ledakan(m.x, m.y, n=20 + m.level * 6)
                    self.ambil_pos = (m.x, m.y, f"+{m.poin}")
                    self.pesan_makan = 40
                    if tumbuh:
                        self.ambil_pos = (p.x, p.y - 50, "BERTUMBUH!")
                        self.partikel.ledakan(p.x, p.y, n=40)
                    self.musuh.remove(m)
                else:                              # musuh lebih besar -> DIMAKAN
                    p.mati = True
                    self.partikel.ledakan(p.x, p.y, n=50)
                    self.terbaik = max(self.terbaik, self.skor)
                    self.simpan_terbaik()
                    self.state = "OVER"
                    return

    # ---------------- helper teks ----------------
    def teks_tengah(self, string, y, font=None, warna=(255, 255, 255)):
        font = font or self.font_sedang
        img = font.render(string, True, warna)
        rect = img.get_rect(center=(WIDTH // 2, y))
        self.screen.blit(font.render(string, True, (20, 30, 40)), rect.move(2, 2))
        self.screen.blit(img, rect)
        return rect

    # ---------------- panel kamera ----------------
    def gambar_panel(self, frame, mask, pos):
        """Panel preview webcam + mask overlay di pojok kiri bawah."""
        if frame is None:
            return
        w, h = 200, 150
        kecil = cv2.resize(frame, (w, h))
        kecil = np.transpose(cv2.cvtColor(kecil, cv2.COLOR_BGR2RGB), (1, 0, 2))
        panel = pygame.surfarray.make_surface(kecil)
        if mask is not None:
            m = cv2.resize(mask, (w, h))
            ov = np.zeros((h, w, 3), dtype=np.uint8)
            ov[m > 0] = (0, 255, 0)
            ov_s = pygame.surfarray.make_surface(np.transpose(ov, (1, 0, 2)))
            ov_s.set_alpha(100)
            panel.blit(ov_s, (0, 0))
        px, py = 12, HEIGHT - h - 12
        self.screen.blit(panel, (px, py))
        pygame.draw.rect(self.screen, (255, 255, 255), (px, py, w, h), 2)
        if pos:
            hx = px + int(pos[0] * w / CAM_W)
            hy = py + int(pos[1] * h / CAM_H)
            pygame.draw.circle(self.screen, (255, 60, 60), (hx, hy), 5, 2)

    # ==========================================
    # GAME LOOP
    # ==========================================
    def jalankan(self):
        t_sebelum = time.time()
        jalan = True
        while jalan:
            dt = min(time.time() - t_sebelum, 0.05)
            t_sebelum = time.time()

            # ---- baca hasil tracking dari thread background ----
            frame, mask, pos, area, dash_aktif = self.kamera.baca()
            self.kamera.update_dash()
            if pos is not None:
                self.kamera.cek_dash(area)
            dash_aktif = self.kamera.update_dash()

            # ---- update game ----
            if self.state == "SIAP":
                # mulai otomatis begitu tangan terdeteksi & digerakkan
                if pos is not None:
                    self.state = "MAIN"
                self.pemain.update(pos, LERP_NORMAL, dt)

            elif self.state == "MAIN":
                lerp = DASH_LERP if dash_aktif else LERP_NORMAL
                self.pemain.dash = dash_aktif
                self.pemain.update(pos, lerp, dt)
                self.update_spawner(dt)
                for m in self.musuh:
                    m.update(dt)
                self.musuh = [m for m in self.musuh if not m.di_luar_layar()]
                self.update_tabrakan()
                if self.state == "MAIN":   # masih hidup?
                    if random.random() < 0.3:
                        self.partikel.ambient()
                    if random.random() < 0.5:
                        self.partikel.jejak(self.pemain.x - self.pemain.radius * self.pemain.arah,
                                            self.pemain.y, dash_aktif)

            elif self.state == "OVER":
                pass

            self.partikel.update()

            # ---- RENDER ----
            self.screen.blit(self.bg, (0, 0))
            self.partikel.gambar(self.screen)

            # musuh (sprite dibalik sesuai arah renang)
            for m in self.musuh:
                sp = m.sprite
                if m.arah == -1:
                    sp = pygame.transform.flip(sp, True, False)
                self.screen.blit(sp, sp.get_rect(center=(int(m.x), int(m.y))))

            # pemain
            if self.state in ("SIAP", "MAIN"):
                sp = self.pemain.sprite
                if self.pemain.arah == -1:
                    sp = pygame.transform.flip(sp, True, False)
                # efek glow saat dash
                if self.pemain.dash:
                    glow = pygame.Surface((sp.get_width() + 30, sp.get_height() + 30),
                                          pygame.SRCALPHA)
                    pygame.draw.circle(glow, (120, 220, 255),
                                       glow.get_rect().center, self.pemain.radius + 12, 4)
                    self.screen.blit(glow, glow.get_rect(
                        center=(int(self.pemain.x), int(self.pemain.y))))
                self.screen.blit(sp, sp.get_rect(center=(int(self.pemain.x),
                                                         int(self.pemain.y))))

            # ---- HUD ----
            lvl_nama = GROWTH[self.pemain.level - 1]["nama"]
            progres = GROWTH[min(self.pemain.level, 2)]["makan_total"]
            awal = GROWTH[self.pemain.level - 1]["makan_total"]
            butuh = max(0, progres - self.pemain.makan) if self.pemain.level < 3 else 0
            hud = f"SKOR {self.skor}   |   UKURAN: {lvl_nama}"
            if butuh:
                hud += f" (makan {butuh} lagi)"
            img = self.font_sedang.render(hud, True, (255, 255, 255))
            self.screen.blit(self.font_sedang.render(hud, True, (20, 30, 40)), (12, 10))
            self.screen.blit(img, (10, 8))
            best = self.font_kecil.render(f"Terbaik: {self.terbaik}", True, (220, 220, 220))
            self.screen.blit(best, (WIDTH - best.get_width() - 12, 10))
            if dash_aktif:
                self.teks_tengah("DASH!", 60, self.font_besar, (120, 220, 255))
            if self.state == "MAIN" and pos is None:
                self.teks_tengah("TANGAN TIDAK TERDETEKSI!", HEIGHT - 60,
                                 self.font_sedang, (255, 90, 90))

            # popup skor melayang
            if self.ambil_pos:
                x, y, txt = self.ambil_pos
                img = self.font_sedang.render(txt, True, KUNING)
                self.screen.blit(img, (int(x), int(y)))
                self.ambil_pos = (x, y - 1.2, txt)
                if y < 40:
                    self.ambil_pos = None

            # ---- UI per state ----
            if self.state == "SIAP":
                self.teks_tengah("FEEDING FRENZY: HAND HUNTER", 130,
                                 self.font_besar, KUNING)
                self.teks_tengah("Tunjukkan TANGAN BERWARNA ke kamera", 210)
                self.teks_tengah("untuk memulai ...", 245)
                self.teks_tengah("makan ikan lebih KECIL dari kamu, hindari yang lebih besar",
                                 300, self.font_kecil, (210, 220, 230))
                self.teks_tengah("DORONG TANGAN KE KAMERA = DASH!", 330,
                                 self.font_kecil, (120, 220, 255))
                self.teks_tengah("[C] kalibrasi warna   [M] panel kamera   [Q] keluar",
                                 360, self.font_kecil, (180, 190, 200))
                if self.kalib_timer > 0:
                    self.teks_tengah(f"MEREKAM WARNA {max(0, 1 - self.kalib_timer):.1f}s",
                                     400, self.font_sedang, (0, 220, 255))

            elif self.state == "OVER":
                kabut = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
                kabut.fill((0, 0, 20, 160))
                self.screen.blit(kabut, (0, 0))
                self.teks_tengah("KAMU DIMAKAN!", 180, self.font_besar, (255, 80, 80))
                self.teks_tengah(f"Skor akhir : {self.skor}", 260)
                self.teks_tengah(f"Terbaik    : {self.terbaik}", 300)
                self.teks_tengah(f"Ikan dimakan: {self.pemain.makan}", 340)
                if self.skor >= self.terbaik and self.skor > 0:
                    self.teks_tengah("*** REKOR BARU! ***", 390, self.font_sedang, KUNING)
                self.teks_tengah("[R] main lagi      [Q] keluar", 440,
                                 self.font_sedang, (0, 220, 255))

            if self.panel_tampil:
                self.gambar_panel(frame, mask, pos)

            pygame.display.flip()

            # ---- EVENT ----
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    jalan = False
                elif ev.type == pygame.KEYDOWN:
                    if ev.key in (pygame.K_q, pygame.K_ESCAPE):
                        jalan = False
                    elif ev.key == pygame.K_m:
                        self.panel_tampil = not self.panel_tampil
                    elif ev.key == pygame.K_r and self.state in ("MAIN", "OVER"):
                        self.reset()
                        self.state = "SIAP"
                    elif ev.key == pygame.K_c and self.state != "MAIN":
                        self.kalib_timer = 0.0001
                        self.kalib_sampel.clear()

            # ---- proses kalibrasi [C] ----
            if self.kalib_timer > 0:
                self.kalib_timer += dt
                self.kamera.sampel_kalibrasi(frame, self.kalib_sampel)
                if self.kalib_timer >= 1.0:
                    self.kalib_timer = 0
                    global HSV_BAWAH, HSV_ATAS
                    if self.kalib_sampel:
                        h = int(np.median([s[0] for s in self.kalib_sampel]))
                        s_ = int(np.median([s[1] for s in self.kalib_sampel]))
                        v = int(np.median([s[2] for s in self.kalib_sampel]))
                        if s_ >= 60 and v >= 60:
                            HSV_BAWAH = np.array([max(h - 12, 0), 60, 60])
                            HSV_ATAS  = np.array([min(h + 12, 179), 255, 255])
                        else:
                            print("Kalibrasi gagal: warna terlalu pucat.")

            self.clock.tick(FPS)

        self.kamera.stop()
        pygame.quit()


# ==========================================
# 7. ENTRY POINT
# ==========================================
if __name__ == "__main__":
    try:
        Game().jalankan()
    except RuntimeError as e:
        print(f"ERROR: {e}")
