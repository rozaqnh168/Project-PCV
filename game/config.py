import os
import numpy as np

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WIDTH, HEIGHT = 960, 640
FPS           = 60
CAM_W, CAM_H  = 320, 240

HSV_BAWAH = np.array([40, 70, 70])
HSV_ATAS  = np.array([85, 255, 255])
MIN_AREA  = 500

LERP_NORMAL = 0.09

GROWTH = [
    {"lvl": 1, "nama": "KECIL",  "radius": 23, "poin_total": 0},
    {"lvl": 2, "nama": "SEDANG", "radius": 37, "poin_total": 80},
    {"lvl": 3, "nama": "BESAR",  "radius": 54, "poin_total": 400},
]

MUSUH = {
    1: {"radius": 13, "kecepatan": (2.0, 3.6), "poin": 10,  "nama": "kecil"},
    2: {"radius": 27, "kecepatan": (1.5, 2.6), "poin": 25,  "nama": "sedang"},
    3: {"radius": 44, "kecepatan": (1.0, 1.8), "poin": 60,  "nama": "besar"},
    4: {"radius": 80, "kecepatan": (0.7, 1.1), "poin": 0,   "nama": "BOSS"},
}

SKOR_FILE = os.path.join(BASE_DIR, "skor_frenzy.txt")
KUNING    = (255, 220, 60)


ASSET_PATHS = {
    "enemy_small":   "assets/enemy_small.png",
    "enemy_medium":  "assets/enemy_medium.png",
    "enemy_large":   "assets/enemy_large.png",
    "bg_underwater": "assets/bg_underwater.png",
    "bubble":        "assets/bubble_particle.png",
    "main_menu":     "assets/Mainmenu.png",
    "game_over":     "assets/Gameover_ui.png",
    "score":         "assets/Score.png",
    "status_kecil":  "assets/saatkecil.png",
    "status_sedang": "assets/saatsedang.png",
    "status_besar":  "assets/saatbesar.png",
}
for nomor in range(1, 9):
    nama = f"ikanp_frame_{nomor:02d}"
    ASSET_PATHS[nama] = f"assets/{nama}.png"
for aksi in ("swim", "eat"):
    for nomor in range(1, 7):
        nama = f"enemy_boss_{aksi}_{nomor:02d}"
        ASSET_PATHS[nama] = f"assets/Boss/{aksi}/{nama}.png"
ASSET_PATHS.update({
    "enemy_small_2":   "assets/enemy_small_sarden.png",
    "enemy_medium_2":  "assets/enemy_medium_2.png",
    "enemy_medium_3":  "assets/enemy_medium_3.png",
    "enemy_large_2":   "assets/enemy_large_2.png",
    "enemy_large_3":   "assets/largefish.png",
    "eat_effect":      "assets/eat_effect.png",
    "bubble_cluster":  "assets/bubble_cluster.png",
    "coral":           "assets/coral.png",
    "rock":            "assets/rock.png",
    "seaweed":         "assets/seaweed.png",
})

ANIMASI_PEMAIN = [f"ikanp_frame_{nomor:02d}" for nomor in range(1, 9)]
STATUS_UKURAN = {1: "status_kecil", 2: "status_sedang", 3: "status_besar"}
FPS_PEMAIN = 8
FPS_MAKAN_PEMAIN = 20
DURASI_MAKAN_PEMAIN = 0.4

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
