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
 """ 
import cv2
import numpy as np
import pygame
import random
import threading
import time
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

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

# --- Tingkat ikan musuh (1 kecil .. 3 besar, 4 BOSS) ---
# Ikan pemain hanya bisa memakan musuh yang tingkatnya <= tingkat dirinya.
MUSUH = {
    1: {"radius": 16, "kecepatan": (2.0, 3.6), "poin": 10,  "nama": "kecil"},
    2: {"radius": 30, "kecepatan": (1.5, 2.6), "poin": 25,  "nama": "sedang"},
    3: {"radius": 48, "kecepatan": (1.0, 1.8), "poin": 60,  "nama": "besar"},
    4: {"radius": 95, "kecepatan": (0.7, 1.1), "poin": 0,   "nama": "BOSS"},
}

SKOR_FILE = os.path.join(BASE_DIR, "skor_frenzy.txt")
KUNING    = (255, 220, 60)


# ==========================================
# 2. ASSET MANAGER 
# ==========================================

ASSET_PATHS = {
    # ---- ASET WAJIB (game jalan penuh dengan ini) ----
    "player_small":  "assets/player_small.png",
    "player_medium": "assets/player_medium.png",
    "player_large":  "assets/player_large.png",
    "enemy_small":   "assets/enemy_small.png",
    "enemy_medium":  "assets/enemy_medium.png",
    "enemy_large":   "assets/enemy_large.png",
    "bg_underwater": "assets/bg_underwater.png",
    "bubble":        "assets/bubble_particle.png",
    "main_menu":     "assets/Mainmenu.png",
    "game_over":     "assets/Gameover_ui.png",
    "score":         "assets/Score.png",
}
for aksi in ("swim", "eat"):
    for nomor in range(1, 7):
        nama = f"enemy_boss_{aksi}_{nomor:02d}"
        ASSET_PATHS[nama] = f"assets/Boss/{aksi}/{nama}.png"
ASSET_PATHS.update({
    # ---- ASET VARIASI / OPSIONAL (dipakai bila ada, di-skip bila tidak) ----
    "enemy_small_2":   "assets/enemy_small_group.png",   
    "enemy_medium_2":  "assets/enemy_medium_2.png",
    "enemy_medium_3":  "assets/enemy_medium_3.png",
    "enemy_large_2":   "assets/enemy_large_2.png",
    "enemy_large_3":   "assets/enemy_large_3.png",
    "dash_effect":     "assets/dash_effect.png",         
    "eat_effect":      "assets/eat_effect.png",          
    "bubble_cluster":  "assets/bubble_cluster.png",      
    "coral":           "assets/coral.png",               
    "rock":            "assets/rock.png",                
    "seaweed":         "assets/seaweed.png",             
})

# Pemetaan tingkat pertumbuhan pemain -> nama sprite (nama aset berbahasa Inggris)
SPRITE_PEMAIN = {1: "player_small", 2: "player_medium", 3: "player_large"}

# Variasi sprite musuh per tingkat (dipilih acak saat spawn; variasi opsional)
SPRITE_MUSUH = {
    1: ["enemy_small", "enemy_small_2"],
    2: ["enemy_medium", "enemy_medium_2", "enemy_medium_3"],
    3: ["enemy_large", "enemy_large_2", "enemy_large_3"],
}
ANIMASI_BOSS = {
    aksi: [f"enemy_boss_{aksi}_{nomor:02d}" for nomor in range(1, 7)]
    for aksi in ("swim", "eat")
}
BATAS_MUSUH = {3: 3, 4: 2}


class AssetManager:
    """Pemuat aset: pakai PNG eksternal bila ada, jika tidak gambar fallback."""

    def __init__(self):
        self.sumber = {}    # sprite asli (ukuran penuh) dari file
        self.cache = {}     # cache hasil penskalaan {(nama, tinggi): surface}
        self.eksternal = set()
        for nama, path in ASSET_PATHS.items():
            path = os.path.join(BASE_DIR, path)
            if os.path.exists(path):
                try:
                    self.sumber[nama] = pygame.image.load(path).convert_alpha()
                    self.eksternal.add(nama)
                except pygame.error:
                    pass  # file rusak -> pakai fallback prosedural

    def punya_eksternal(self, nama):
        return nama in self.eksternal

    def ambil(self, nama, radius=None):
        """Kembalikan surface sprite dengan TINGGI = radius*2.

        Penskalaan menjaga RASIO ASPEK asli sprite (lebar menyesuaikan),
        jadi ikan tidak gepeng/lonjong. Hasil di-cache supaya tidak
        melakukan smoothscale setiap frame (hemat CPU).
        Bila PNG tidak ada, digambar fallback prosedural oleh kode.
        """
        tinggi = int(radius * 2) if radius else 0
        if nama in self.sumber:
            asli = self.sumber[nama]
            if tinggi and asli.get_height() != tinggi:
                key = (nama, tinggi)
                if key not in self.cache:
                    w, h = asli.get_size()
                    lebar = max(1, int(w * tinggi / h))
                    self.cache[key] = pygame.transform.smoothscale(
                        asli, (lebar, tinggi))
                return self.cache[key]
            return asli
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
        }
        warna = palet.get(nama, (200, 200, 200))
        if nama.startswith("enemy_boss"):
            warna = (60, 70, 160)
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
        return s


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
        self.makan = 0                 
        self.level = 1                
        self.radius = GROWTH[0]["radius"]
        self.mati = False
        self.dash = False
        self.arah = 1                  # 1 kanan / -1 kiri (untuk flip sprite)

    @property
    def sprite(self):
        # SPRITE_PEMAIN memetakan level -> nama file aset (player_small, dst.)
        return self.assets.ambil(SPRITE_PEMAIN[self.level], self.radius)

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
    """Ikan musuh level 1-3; Boss level 4 memiliki animasi swim dan eat."""

    def __init__(self, assets: AssetManager, level, y=None):
        self.assets = assets
        cfg = MUSUH[level]
        self.level = level
        self.radius = cfg["radius"]
        self.poin = cfg["poin"]
        self.sedang_makan = False
        self.waktu_animasi = 0.0
        self.animasi_selesai = False
        # pilih variasi sprite secara acak dari daftar yang tersedia
        # (mis. enemy_medium, enemy_medium_2, enemy_medium_3)
        variasi = SPRITE_MUSUH.get(level, [ANIMASI_BOSS["swim"][0]])
        self.sprite_nama = random.choice(
            [v for v in variasi if assets.punya_eksternal(v)] or variasi)
        # arah acak: 1 = berenang ke kanan (masuk dari kiri), -1 = sebaliknya
        self.arah = random.choice([1, -1])
        self.vx = random.uniform(*cfg["kecepatan"]) * self.arah
        self.x = -self.radius - 30 if self.arah == 1 else WIDTH + self.radius + 30
        self.y = y if y is not None else random.randint(self.radius + 20,
                                                        HEIGHT - self.radius - 20)
        self.wiggle = random.uniform(0, 6.28)   # gerak naik-turun sinus kecil

    def mulai_makan(self):
        """Putar animasi eat Boss sekali sambil menghentikan geraknya."""
        self.sedang_makan = True
        self.waktu_animasi = 0.0
        self.animasi_selesai = False

    def update(self, dt):
        self.waktu_animasi += dt
        if self.sedang_makan:
            self.animasi_selesai = self.waktu_animasi >= len(ANIMASI_BOSS["eat"]) / 10
            return
        self.x += self.vx * dt * 60
        self.wiggle += 0.05
        self.y += np.sin(self.wiggle) * 0.4     # ikan 'bernapas' naik turun

    @property
    def sprite(self):
        if self.level == 4:
            aksi = "eat" if self.sedang_makan else "swim"
            frames = ANIMASI_BOSS[aksi]
            indeks = int(self.waktu_animasi * 10)
            if self.sedang_makan:
                indeks = min(indeks, len(frames) - 1)
            else:
                indeks %= len(frames)
            return self.assets.ambil(frames[indeks], self.radius)
        return self.assets.ambil(self.sprite_nama, self.radius)

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
        self.partikel = []   # gelembung biasa (lingkaran kecil)
        self.efek = []       # efek sprite (eat_effect, bubble_cluster, ...)

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
        # efek sprite "makan" (membesar & memudar) bila asetnya tersedia
        if self.assets.punya_eksternal("eat_effect"):
            self.efek.append({"nama": "eat_effect", "x": x, "y": y,
                              "tinggi": 40, "umur": 24, "umur0": 24})

    def gelembung_besar(self, x, y):
        """Gelembung cluster besar dekoratif (aset bubble_cluster)."""
        if self.assets.punya_eksternal("bubble_cluster"):
            self.efek.append({"nama": "bubble_cluster", "x": x, "y": y,
                              "tinggi": 60, "umur": 90, "umur0": 90})

    def update(self):
        for p in self.partikel[:]:
            p["x"] += p["vx"]
            p["y"] += p["vy"]
            p["vy"] *= 0.99            # gesekan air
            p["umur"] -= 1
            if p["umur"] <= 0 or p["y"] < -20:
                self.partikel.remove(p)
        for e in self.efek[:]:
            e["umur"] -= 1
            e["y"] -= 1.0 if e["nama"] == "bubble_cluster" else 0.4
            if e["umur"] <= 0:
                self.efek.remove(e)

    def gambar(self, surf):
        for p in self.partikel:
            alfa = p["umur"] / p["umur0"]
            r = max(1, int(p["r"] * (0.5 + 0.5 * alfa)))
            sprite = self.assets.ambil("bubble", r)
            sprite.set_alpha(int(150 * alfa))
            surf.blit(sprite, (int(p["x"] - r), int(p["y"] - r)))
        for e in self.efek:
            alfa = e["umur"] / e["umur0"]
            # efek membesar saat lahir lalu memudar
            tumbuh = 1 + (1 - alfa) * 0.8
            tinggi = int(e["tinggi"] * tumbuh)
            sprite = self.assets.ambil(e["nama"], tinggi // 2)
            sprite = sprite.copy()          # copy agar set_alpha tidak menular
            sprite.set_alpha(int(220 * alfa))
            surf.blit(sprite, sprite.get_rect(center=(int(e["x"]), int(e["y"]))))


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
        self.ui = {
            nama: self.assets.sumber[nama]
            for nama in ("game_over", "main_menu", "score")
            if self.assets.punya_eksternal(nama)
        }
        self.kamera = PelacakKamera()
        if not self.kamera.buka:
            raise RuntimeError("Kamera tidak bisa dibuka!")

        self.bg = self._buat_bg()
        self.state = "SIAP"          # SIAP -> MAIN -> OVER
        self.reset()

        self.panel_tampil = True
        self.kalib_sampel = []
        self.kalib_timer = 0.0
        self.kalib_selesai = 0.0
        self.kalib_gagal = False
        self.kalib_pesan = ""
        self.menu_rect = None
        self.game_over_rect = None
        self.pilihan_ukuran = [(800, 600), (960, 640), (1280, 720)]
        self.opsi_rects = []
        self.kembali_rect = None
        self.hover_aktif = False
        self.cursor_panah = pygame.cursors.Cursor(pygame.SYSTEM_CURSOR_ARROW)
        self.cursor_tangan = pygame.cursors.Cursor(pygame.SYSTEM_CURSOR_HAND)

    def ubah_ukuran(self, ukuran):
        """Ubah jendela dan pertahankan posisi relatif seluruh objek permainan."""
        global WIDTH, HEIGHT
        lebar_lama, tinggi_lama = WIDTH, HEIGHT
        WIDTH, HEIGHT = ukuran
        self.screen = pygame.display.set_mode(ukuran)
        sx, sy = WIDTH / lebar_lama, HEIGHT / tinggi_lama
        for objek in [self.pemain, *self.musuh]:
            objek.x *= sx
            objek.y *= sy
        for partikel in self.partikel.partikel:
            partikel["x"] *= sx
            partikel["y"] *= sy
        self.pemain.x = max(self.pemain.radius,
                            min(WIDTH - self.pemain.radius, self.pemain.x))
        self.pemain.y = max(self.pemain.radius,
                            min(HEIGHT - self.pemain.radius, self.pemain.y))
        self.bg = self._buat_bg()
        self.menu_rect = None
        self.game_over_rect = None

    # ---------------- latar prosedural ----------------
    def _buat_bg(self):
        """Latar dasar laut.
        Bila assets/bg_underwater.png tersedia -> dipakai sebagai dasar,
        lalu dekorasi (coral/rock/seaweed) ditempel acak di dasarnya."""
        if self.assets.punya_eksternal("bg_underwater"):
            img = self.assets.sumber["bg_underwater"]
            bg = pygame.transform.smoothscale(img, (WIDTH, HEIGHT))
        else:
            # fallback: gradasi biru + siluet rumput laut
            bg = pygame.Surface((WIDTH, HEIGHT))
            for y in range(HEIGHT):
                t = y / HEIGHT
                warna = (int(10 + 25 * t), int(60 + 60 * t), int(110 + 70 * t))
                pygame.draw.line(bg, warna, (0, y), (WIDTH, y))
            for i in range(0, WIDTH, 90):
                tinggi = random.randint(50, 130)
                titik = [(i, HEIGHT)]
                for j in range(1, 6):
                    titik.append((i + random.randint(-14, 14), HEIGHT - tinggi * j // 5))
                pygame.draw.lines(bg, (20, 90, 70), False, titik, 6)
        # ---- tempel dekorasi aset di dasar laut (bila tersedia) ----
        for nama, jumlah in (("seaweed", 7), ("coral", 4), ("rock", 4)):
            if not self.assets.punya_eksternal(nama):
                continue
            for _ in range(jumlah):
                tinggi = random.randint(60, 150)
                sp = self.assets.ambil(nama, tinggi // 2)
                x = random.randint(-30, WIDTH - 40)
                bg.blit(sp, (x, HEIGHT - sp.get_height() + random.randint(0, 14)))
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
            levels, weights = [1, 2], [0.65, 0.35]
        elif lvl == 2:
            levels, weights = [1, 2, 3], [0.50, 0.35, 0.15]
        else:
            levels, weights = [1, 2, 3, 4], [0.32, 0.34, 0.20, 0.14]

        # Batasi ikan besar dan Boss tanpa menghentikan spawn jenis lain.
        for level, batas in BATAS_MUSUH.items():
            if level in levels and sum(m.level == level for m in self.musuh) >= batas:
                index = levels.index(level)
                levels.pop(index)
                weights.pop(index)

        return random.choices(levels, weights=weights)[0]

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
                    if m.level == 4:
                        m.mulai_makan()
                        self.state = "DIMAKAN"
                    else:
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

    def _gambar_panel_ui(self, nama, ukuran, tengah):
        """Gambar potongan UI dengan rasio aspek yang tetap."""
        if nama not in self.ui:
            return None
        asli = self.ui[nama]
        faktor = min(ukuran[0] / asli.get_width(),
                     ukuran[1] / asli.get_height())
        dimensi = (int(asli.get_width() * faktor),
                   int(asli.get_height() * faktor))
        gambar = pygame.transform.smoothscale(asli, dimensi)
        rect = gambar.get_rect(center=tengah)
        self.screen.blit(gambar, rect)
        return rect

    def _teks_ui(self, teks, posisi, ukuran, maksimum_lebar):
        font = pygame.font.SysFont("dejavusansbold", ukuran, bold=True)
        gambar = font.render(teks, True, (245, 250, 255))
        if gambar.get_width() > maksimum_lebar:
            faktor = maksimum_lebar / gambar.get_width()
            gambar = pygame.transform.smoothscale(
                gambar, (maksimum_lebar, max(1, int(gambar.get_height() * faktor))))
        rect = gambar.get_rect(center=posisi)
        bayangan = font.render(teks, True, (10, 35, 65))
        if bayangan.get_size() != gambar.get_size():
            bayangan = pygame.transform.smoothscale(bayangan, gambar.get_size())
        self.screen.blit(bayangan, rect.move(2, 2))
        self.screen.blit(gambar, rect)
        return rect

    @staticmethod
    def _hitbox_panel(rect, area):
        """Ubah area tombol ternormalisasi menjadi hitbox layar."""
        x1, y1, x2, y2 = area
        return pygame.Rect(rect.left + int(rect.width * x1),
                           rect.top + int(rect.height * y1),
                           int(rect.width * (x2 - x1)),
                           int(rect.height * (y2 - y1)))

    def _tombol_menu(self):
        if not self.menu_rect:
            return {}
        areas = {
            "play": (0.24, 0.385, 0.76, 0.53),
            "options": (0.24, 0.55, 0.76, 0.69),
            "quit": (0.24, 0.715, 0.76, 0.855),
        }
        return {nama: self._hitbox_panel(self.menu_rect, area)
                for nama, area in areas.items()}

    def _tombol_game_over(self):
        if not self.game_over_rect:
            return {}
        # area diukur dari piksel tombol pada assets/Gameover_ui.png (761x724)
        return {
            "retry": self._hitbox_panel(
                self.game_over_rect, (0.197, 0.745, 0.515, 0.874)),
            "menu": self._hitbox_panel(
                self.game_over_rect, (0.535, 0.745, 0.848, 0.876)),
        }

    def _gambar_highlight(self, rect, warna=(255, 235, 120), radius=24):
        """Glow hover lembut yang mengikuti bentuk tombol (sudut membulat)."""
        if not rect:
            return
        if rect.collidepoint(pygame.mouse.get_pos()):
            self.hover_aktif = True
            pad = 10
            glow = pygame.Surface((rect.width + pad * 2, rect.height + pad * 2),
                                  pygame.SRCALPHA)
            # lapisan glow memudar ke luar
            for i, alfa in enumerate((18, 30, 46)):
                r = glow.get_rect().inflate(-i * 6, -i * 6)
                pygame.draw.rect(glow, (*warna, alfa), r, 3,
                                 border_radius=radius + pad - i * 3)
            dalam = pygame.Rect(pad, pad, rect.width, rect.height)
            pygame.draw.rect(glow, (255, 255, 255, 28), dalam,
                             border_radius=radius)          # kilau tipis di tombol
            pygame.draw.rect(glow, (*warna, 235), dalam.inflate(2, 2), 3,
                             border_radius=radius)
            self.screen.blit(glow, (rect.left - pad, rect.top - pad))

    def _teks_angka(self, teks, tengah, tinggi):
        """Angka bergaya label aset: isi gradasi putih->cyan, outline navy
        tebal, dan bayangan lembut agar terlihat 'tercetak' di panel."""
        font = pygame.font.SysFont("dejavusansbold", tinggi, bold=True)
        isi = font.render(teks, True, (255, 255, 255))
        w, h = isi.get_size()
        # gradasi vertikal: putih di atas -> cyan muda di bawah
        gradasi = pygame.Surface((w, h), pygame.SRCALPHA)
        for y in range(h):
            t = y / max(1, h - 1)
            pygame.draw.line(gradasi, (int(255 - 70 * t), int(255 - 15 * t), 255),
                             (0, y), (w, y))
        isi.blit(gradasi, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

        tebal = max(2, tinggi // 12)
        hasil = pygame.Surface((w + tebal * 2 + 4, h + tebal * 2 + 4),
                               pygame.SRCALPHA)
        garis = font.render(teks, True, (12, 38, 78))
        bayangan = font.render(teks, True, (0, 12, 35))
        bayangan.set_alpha(110)
        for dx in range(-tebal, tebal + 1):
            for dy in range(-tebal, tebal + 1):
                if dx * dx + dy * dy <= tebal * tebal:
                    hasil.blit(bayangan, (tebal + dx + 2, tebal + dy + 3))
        for dx in range(-tebal, tebal + 1):
            for dy in range(-tebal, tebal + 1):
                if dx * dx + dy * dy <= tebal * tebal:
                    hasil.blit(garis, (tebal + dx, tebal + dy))
        hasil.blit(isi, (tebal, tebal))
        self.screen.blit(hasil, hasil.get_rect(center=tengah))

    def _gambar_nilai_panel(self, panel, area, nilai, ukuran_font, bersih=False):
        """Tulis nilai aktual pada panel; aset bersih tidak perlu kotak penutup."""
        rect = self._hitbox_panel(panel, area)
        if bersih:
            self._teks_angka(f"{nilai:06d}", rect.center, ukuran_font)
            return
        pygame.draw.rect(self.screen, (8, 65, 108), rect, border_radius=8)
        self._teks_ui(f"{nilai:06d}", rect.center, ukuran_font, rect.width - 8)

    def _gambar_options(self):
        kabut = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        kabut.fill((0, 10, 35, 220))
        self.screen.blit(kabut, (0, 0))
        self.teks_tengah("OPTIONS", 100, self.font_besar, KUNING)
        self.teks_tengah("PILIH UKURAN WINDOW", 155, self.font_sedang)
        self.opsi_rects = []
        for i, (lebar, tinggi) in enumerate(self.pilihan_ukuran):
            rect = pygame.Rect(0, 0, min(360, WIDTH - 80), 62)
            rect.center = (WIDTH // 2, 225 + i * 85)
            aktif = (lebar, tinggi) == (WIDTH, HEIGHT)
            pygame.draw.rect(self.screen, (15, 115, 175) if aktif else (8, 65, 108),
                             rect, border_radius=16)
            pygame.draw.rect(self.screen, KUNING if aktif else (70, 195, 235),
                             rect, 3, border_radius=16)
            label = f"{lebar} x {tinggi}" + ("  (AKTIF)" if aktif else "")
            self._teks_ui(label, rect.center, 27, rect.width - 28)
            self._gambar_highlight(rect)
            self.opsi_rects.append((rect, (lebar, tinggi)))
        self.kembali_rect = pygame.Rect(0, 0, 180, 52)
        self.kembali_rect.center = (WIDTH // 2, 490)
        pygame.draw.rect(self.screen, (8, 65, 108), self.kembali_rect,
                         border_radius=14)
        pygame.draw.rect(self.screen, (70, 195, 235), self.kembali_rect,
                         3, border_radius=14)
        self._teks_ui("KEMBALI", self.kembali_rect.center, 25,
                      self.kembali_rect.width - 20)
        self._gambar_highlight(self.kembali_rect)

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

    def mulai_kalibrasi(self):
        """Reset ronde dan tahan gameplay sampai warna tangan berhasil direkam."""
        self.reset()
        self.state = "KALIBRASI"
        self.kalib_sampel.clear()
        self.kalib_timer = 0.0
        self.kalib_selesai = 0.0
        self.kalib_gagal = False
        self.kalib_aktif = False
        self.kalib_pesan = "TEKAN K UNTUK MULAI KALIBRASI"

    def update_kalibrasi(self, frame, dt):
        """Kumpulkan sampel HSV selama 2 detik, lalu validasi hasilnya."""
        global HSV_BAWAH, HSV_ATAS
        if self.kalib_gagal or not self.kalib_aktif:
            return
        if self.kalib_selesai > 0:
            self.kalib_selesai -= dt
            if self.kalib_selesai <= 0:
                self.state = "MAIN"
            return
        if frame is None:
            self.kalib_pesan = "MENUNGGU KAMERA..."
            return
        self.kalib_timer += dt
        self.kamera.sampel_kalibrasi(frame, self.kalib_sampel)
        self.kalib_pesan = "TAHAN TANGAN TETAP DI DALAM KOTAK"
        if self.kalib_timer < 2.0:
            return
        self.kalib_timer = 0
        if not self.kalib_sampel:
            self.kalib_gagal = True
            self.kalib_pesan = "KALIBRASI GAGAL - TEKAN K UNTUK ULANG"
            return
        h = int(np.median([s[0] for s in self.kalib_sampel]))
        s = int(np.median([s[1] for s in self.kalib_sampel]))
        v = int(np.median([s[2] for s in self.kalib_sampel]))
        if s < 60 or v < 60:
            self.kalib_gagal = True
            self.kalib_sampel.clear()
            self.kalib_pesan = "WARNA TERLALU PUCAT - TEKAN K UNTUK ULANG"
            return
        HSV_BAWAH = np.array([max(h - 12, 0), 60, 60])
        HSV_ATAS = np.array([min(h + 12, 179), 255, 255])
        self.kalib_selesai = 0.8
        self.kalib_pesan = "KALIBRASI BERHASIL - GAME DIMULAI!"

    def _gambar_kalibrasi(self, frame):
        kabut = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        kabut.fill((0, 10, 35, 225))
        self.screen.blit(kabut, (0, 0))
        self.teks_tengah("KALIBRASI WARNA", 65, self.font_besar, KUNING)
        self.teks_tengah("Letakkan dan tahan tangan di dalam kotak", 112,
                         self.font_sedang)
        if frame is not None:
            gambar = np.transpose(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), (1, 0, 2))
            preview = pygame.surfarray.make_surface(gambar)
            preview = pygame.transform.smoothscale(preview, (400, 300))
            rect = preview.get_rect(center=(WIDTH // 2, 290))
            self.screen.blit(preview, rect)
            pygame.draw.rect(self.screen, (255, 255, 255), rect, 3,
                             border_radius=4)
            kotak = pygame.Rect(0, 0, 100, 100)
            kotak.center = rect.center
            pygame.draw.rect(self.screen, KUNING, kotak, 4)
        else:
            pygame.draw.rect(self.screen, (10, 55, 85),
                             (WIDTH // 2 - 200, 140, 400, 300))
        warna = (100, 255, 160) if self.kalib_selesai else (255, 255, 255)
        self.teks_tengah(self.kalib_pesan, 475, self.font_kecil, warna)
        if self.kalib_timer > 0:
            pygame.draw.rect(self.screen, (15, 75, 110),
                             (WIDTH // 2 - 200, 505, 400, 18), border_radius=9)
            lebar = int(400 * min(self.kalib_timer / 2.0, 1.0))
            if lebar:
                pygame.draw.rect(self.screen, (70, 220, 255),
                                 (WIDTH // 2 - 200, 505, lebar, 18), border_radius=9)
        self.teks_tengah("ESC: kembali ke menu", 555, self.font_kecil)

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
                    if random.random() < 0.008:   # sesekali: gelembung cluster besar
                        self.partikel.gelembung_besar(
                            random.randint(60, WIDTH - 60), random.randint(80, HEIGHT - 80))
                    if random.random() < 0.5:
                        self.partikel.jejak(self.pemain.x - self.pemain.radius * self.pemain.arah,
                                            self.pemain.y, dash_aktif)

            elif self.state == "DIMAKAN":
                for m in self.musuh:
                    if m.sedang_makan:
                        m.update(dt)
                        if m.animasi_selesai:
                            self.state = "OVER"
                            break

            elif self.state == "KALIBRASI":
                self.update_kalibrasi(frame, dt)

            elif self.state == "OVER":
                pass

            self.partikel.update()

            # ---- RENDER ----
            self.hover_aktif = False
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
                # efek dash: pakai sprite dash_effect bila ada, kalau tidak glow
                if self.pemain.dash:
                    px, py = int(self.pemain.x), int(self.pemain.y)
                    if self.assets.punya_eksternal("dash_effect"):
                        sp_efek = self.assets.ambil("dash_effect", self.pemain.radius)
                        sp_efek = sp_efek.copy()
                        sp_efek.set_alpha(150)
                        # efek berada di belakang ikan (sisi lawan arah renang)
                        pos = sp_efek.get_rect(center=(px - self.pemain.arah * self.pemain.radius,
                                                        py))
                        if self.pemain.arah == -1:
                            sp_efek = pygame.transform.flip(sp_efek, True, False)
                        self.screen.blit(sp_efek, pos)
                    else:
                        glow = pygame.Surface((sp.get_width() + 30, sp.get_height() + 30),
                                              pygame.SRCALPHA)
                        pygame.draw.circle(glow, (120, 220, 255),
                                           glow.get_rect().center, self.pemain.radius + 12, 4)
                        self.screen.blit(glow, glow.get_rect(center=(px, py)))
                self.screen.blit(sp, sp.get_rect(center=(int(self.pemain.x),
                                                         int(self.pemain.y))))

            # ---- HUD ----
            if self.state == "MAIN":
                lvl_nama = GROWTH[self.pemain.level - 1]["nama"]
                progres = GROWTH[min(self.pemain.level, 2)]["makan_total"]
                butuh = max(0, progres - self.pemain.makan) if self.pemain.level < 3 else 0
                hud = f"UKURAN: {lvl_nama}"
                if butuh:
                    hud += f" (makan {butuh} lagi)"
                self.screen.blit(self.font_sedang.render(hud, True, (20, 30, 40)), (14, 12))
                self.screen.blit(self.font_sedang.render(hud, True, (255, 255, 255)), (12, 10))
                score_rect = self._gambar_panel_ui("score", (270, 110), (WIDTH - 150, 68))
                if score_rect:
                    self._gambar_nilai_panel(
                        score_rect, (0.38, 0.42, 0.85, 0.65), self.skor, 38)
                else:
                    self.teks_tengah(f"SKOR {self.skor}", 35, self.font_sedang)
                if dash_aktif:
                    self.teks_tengah("DASH!", 130, self.font_besar, (120, 220, 255))
                if pos is None:
                    self.teks_tengah("TANGAN TIDAK TERDETEKSI!", HEIGHT - 60,
                                     self.font_sedang, (255, 90, 90))

                if self.ambil_pos:
                    x, y, txt = self.ambil_pos
                    img = self.font_sedang.render(txt, True, KUNING)
                    self.screen.blit(img, (int(x), int(y)))
                    self.ambil_pos = (x, y - 1.2, txt)
                    if y < 40:
                        self.ambil_pos = None

            elif self.state == "SIAP":
                kabut = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
                kabut.fill((0, 0, 20, 100))
                self.screen.blit(kabut, (0, 0))
                self.menu_rect = self._gambar_panel_ui(
                    "main_menu", (620, 590), (WIDTH // 2, HEIGHT // 2))
                for rect in self._tombol_menu().values():
                    self._gambar_highlight(rect)
                if not self.menu_rect:
                    self.teks_tengah("FEEDING FRENZY: HAND HUNTER", 180,
                                     self.font_besar, KUNING)
                    self.teks_tengah("ENTER: bermain | O: options | Q: keluar", 250)
                if self.kalib_timer > 0:
                    self.teks_tengah(f"MEREKAM WARNA {max(0, 1 - self.kalib_timer):.1f}s",
                                     HEIGHT - 36, self.font_sedang, (0, 220, 255))

            elif self.state == "KALIBRASI":
                self._gambar_kalibrasi(frame)

            elif self.state == "OPTIONS":
                self._gambar_options()

            elif self.state == "OVER":
                kabut = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
                kabut.fill((0, 0, 20, 125))
                self.screen.blit(kabut, (0, 0))
                self.game_over_rect = self._gambar_panel_ui(
                    "game_over", (620, 600), (WIDTH // 2, HEIGHT // 2))
                if self.game_over_rect:
                    # slot angka cekung pada aset: SCORE & BEST
                    ukuran_angka = int(self.game_over_rect.height * 0.064)
                    self._gambar_nilai_panel(
                        self.game_over_rect, (0.360, 0.457, 0.670, 0.526),
                        self.skor, ukuran_angka, bersih=True)
                    self._gambar_nilai_panel(
                        self.game_over_rect, (0.360, 0.648, 0.670, 0.717),
                        self.terbaik, ukuran_angka, bersih=True)
                    for rect in self._tombol_game_over().values():
                        self._gambar_highlight(rect, radius=int(rect.height * 0.3))
                else:
                    self.teks_tengah(f"GAME OVER - Skor: {self.skor}", 230,
                                     self.font_besar, (255, 80, 80))
                    self.teks_tengah("[R] main lagi      [Q] keluar", 320)

            if self.panel_tampil and self.state != "KALIBRASI":
                self.gambar_panel(frame, mask, pos)

            pygame.mouse.set_cursor(
                self.cursor_tangan if self.hover_aktif else self.cursor_panah)
            pygame.display.flip()

            # ---- EVENT ----
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    jalan = False
                elif ev.type == pygame.MOUSEBUTTONUP and ev.button == 1:
                    if self.state == "SIAP":
                        tombol = self._tombol_menu()
                        if tombol.get("play") and tombol["play"].collidepoint(ev.pos):
                            self.mulai_kalibrasi()
                        elif tombol.get("options") and tombol["options"].collidepoint(ev.pos):
                            self.state = "OPTIONS"
                        elif tombol.get("quit") and tombol["quit"].collidepoint(ev.pos):
                            jalan = False
                    elif self.state == "OPTIONS":
                        if self.kembali_rect and self.kembali_rect.collidepoint(ev.pos):
                            self.state = "SIAP"
                        else:
                            for rect, ukuran in self.opsi_rects:
                                if rect.collidepoint(ev.pos):
                                    if ukuran != (WIDTH, HEIGHT):
                                        self.ubah_ukuran(ukuran)
                                    break
                    elif self.state == "OVER":
                        tombol = self._tombol_game_over()
                        if tombol.get("retry") and tombol["retry"].collidepoint(ev.pos):
                            self.mulai_kalibrasi()
                        elif tombol.get("menu") and tombol["menu"].collidepoint(ev.pos):
                            self.reset()
                            self.state = "SIAP"
                elif ev.type == pygame.KEYDOWN:
                    if ev.key == pygame.K_ESCAPE and self.state in ("OPTIONS", "KALIBRASI"):
                        self.state = "SIAP"
                        self.kalib_timer = 0
                        self.kalib_selesai = 0
                    elif ev.key in (pygame.K_q, pygame.K_ESCAPE):
                        jalan = False
                    elif ev.key in (pygame.K_RETURN, pygame.K_SPACE) and self.state == "SIAP":
                        self.mulai_kalibrasi()
                    elif ev.key == pygame.K_o and self.state == "SIAP":
                        self.state = "OPTIONS"
                    elif ev.key == pygame.K_m:
                        self.panel_tampil = not self.panel_tampil
                    elif ev.key == pygame.K_r and self.state in ("MAIN", "DIMAKAN", "OVER"):
                        self.reset()
                        self.state = "SIAP"
                    elif ev.key == pygame.K_k and self.state == "KALIBRASI" \
                            and not self.kalib_selesai:
                        self.kalib_aktif = True
                        self.kalib_timer = 0.0001
                        self.kalib_sampel.clear()
                        self.kalib_gagal = False
                        self.kalib_pesan = "TAHAN TANGAN TETAP DI DALAM KOTAK"

            # ---- proses kalibrasi manual [C] pada main menu ----
            if self.kalib_timer > 0 and self.state == "SIAP":
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
