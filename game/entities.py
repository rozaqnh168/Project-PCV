import random
import numpy as np

from . import config
from .assets import AssetManager


class IkanPemain:

    def __init__(self, assets: AssetManager):
        self.assets = assets
        self.x, self.y = config.WIDTH // 2, config.HEIGHT // 2
        self.makan = 0
        self.level = 1
        self.radius = config.GROWTH[0]["radius"]
        self.mati = False
        self.dash = False
        self.arah = 1                 

    @property
    def sprite(self):
        return self.assets.ambil(config.SPRITE_PEMAIN[self.level], self.radius)

    def makan_ikan(self):
        self.makan += 1
        for g in config.GROWTH:
            if self.makan >= g["makan_total"]:
                level_baru = g["lvl"]
        if level_baru > self.level:
            self.level = level_baru
            self.radius = config.GROWTH[self.level - 1]["radius"]
            return True  # bertumbuh!
        return False

    def update(self, target, lerp_faktor, dt):
        if target is None:
            return
        tx = (target[0] / config.CAM_W) * config.WIDTH
        ty = (target[1] / config.CAM_H) * config.HEIGHT
        k = 1 - (1 - lerp_faktor) ** (dt * 60)   
        if tx != self.x:
            self.arah = 1 if tx > self.x else -1
        self.x += (tx - self.x) * k
        self.y += (ty - self.y) * k


class IkanMusuh:
    def __init__(self, assets: AssetManager, level, y=None):
        self.assets = assets
        cfg = config.MUSUH[level]
        self.level = level
        self.radius = cfg["radius"]
        self.poin = cfg["poin"]
        self.sedang_makan = False
        self.waktu_animasi = 0.0
        self.animasi_selesai = False
        variasi = config.SPRITE_MUSUH.get(level, [config.ANIMASI_BOSS["swim"][0]])
        self.sprite_nama = random.choice(
            [v for v in variasi if assets.punya_eksternal(v)] or variasi)
        self.arah = random.choice([1, -1])
        self.vx = random.uniform(*cfg["kecepatan"]) * self.arah
        self.x = -self.radius - 30 if self.arah == 1 else config.WIDTH + self.radius + 30
        self.y = y if y is not None else random.randint(self.radius + 20,
                                                        config.HEIGHT - self.radius - 20)
        self.wiggle = random.uniform(0, 6.28)   # gerak naik-turun sinus kecil

    def mulai_makan(self):
        self.sedang_makan = True
        self.waktu_animasi = 0.0
        self.animasi_selesai = False

    def update(self, dt):
        self.waktu_animasi += dt
        if self.sedang_makan:
            self.animasi_selesai = self.waktu_animasi >= len(config.ANIMASI_BOSS["eat"]) / 10
            return
        self.x += self.vx * dt * 60
        self.wiggle += 0.05
        self.y += np.sin(self.wiggle) * 0.4     
    @property
    def sprite(self):
        if self.level == 4:
            aksi = "eat" if self.sedang_makan else "swim"
            frames = config.ANIMASI_BOSS[aksi]
            indeks = int(self.waktu_animasi * 10)
            if self.sedang_makan:
                indeks = min(indeks, len(frames) - 1)
            else:
                indeks %= len(frames)
            return self.assets.ambil(frames[indeks], self.radius)
        return self.assets.ambil(self.sprite_nama, self.radius)

    def di_luar_layar(self):
        return (self.arah == 1 and self.x > config.WIDTH + self.radius + 40) or \
               (self.arah == -1 and self.x < -self.radius - 40)
