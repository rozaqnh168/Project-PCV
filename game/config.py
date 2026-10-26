import os
import numpy as np

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WIDTH, HEIGHT = 960, 640
FPS           = 60
CAM_W, CAM_H  = 320, 240

HSV_BAWAH = np.array([40, 70, 70])
HSV_ATAS  = np.array([85, 255, 255])
MIN_AREA  = 500

DASH_RASIO      = 1.65
DASH_COOlDOWN   = 1.6
DASH_DURASI     = 0.8
DASH_LERP       = 0.30
LERP_NORMAL     = 0.09

GROWTH = [
    {"lvl": 1, "nama": "KECIL",   "radius": 20, "makan_total": 0},
    {"lvl": 2, "nama": "SEDANG",  "radius": 34, "makan_total": 8},
    {"lvl": 3, "nama": "BESAR",   "radius": 52, "makan_total": 20},
]

MUSUH = {
    1: {"radius": 16, "kecepatan": (2.0, 3.6), "poin": 10,  "nama": "kecil"},
    2: {"radius": 30, "kecepatan": (1.5, 2.6), "poin": 25,  "nama": "sedang"},
    3: {"radius": 48, "kecepatan": (1.0, 1.8), "poin": 60,  "nama": "besar"},
    4: {"radius": 75, "kecepatan": (0.7, 1.1), "poin": 0,   "nama": "BOSS"},
}

SKOR_FILE = os.path.join(BASE_DIR, "skor_frenzy.txt")
KUNING    = (255, 220, 60)


ASSET_PATHS = {
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

SPRITE_PEMAIN = {1: "player_small", 2: "player_medium", 3: "player_large"}

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
