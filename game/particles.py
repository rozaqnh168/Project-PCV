import random
import numpy as np
from . import config
from .assets import AssetManager


class SistemPartikel:
    def __init__(self, assets: AssetManager):
        self.assets = assets
        self.partikel = []   # gelembung biasa (lingkaran kecil)
        self.efek = []       # efek sprite (eat_effect, bubble_cluster, ...)

    def _tambah(self, x, y, vx, vy, radius, umur):
        self.partikel.append({"x": x, "y": y, "vx": vx, "vy": vy,
                              "r": radius, "umur": umur, "umur0": umur})

    def ambient(self):
        """Gelembung acak dari dasar laut."""
        self._tambah(random.randint(0, config.WIDTH), config.HEIGHT + 10,
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
