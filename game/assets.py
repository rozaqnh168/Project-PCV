import os
import pygame

from . import config


class AssetManager:
    def __init__(self):
        self.sumber = {}    
        self.cache = {}     
        self.eksternal = set()
        for nama, path in config.ASSET_PATHS.items():
            path = os.path.join(config.BASE_DIR, path)
            if os.path.exists(path):
                try:
                    self.sumber[nama] = pygame.image.load(path).convert_alpha()
                    self.eksternal.add(nama)
                except pygame.error:
                    pass  

    def punya_eksternal(self, nama):
        return nama in self.eksternal

    def ambil(self, nama, radius=None):
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
        r = radius or 20
        return self._gambar_fallback(nama, r)

    def _gambar_fallback(self, nama, r):
        s = pygame.Surface((r * 2 + 10, r * 2 + 10), pygame.SRCALPHA)
        cx, cy = r + 5, r + 5
        if nama == "bubble":
            pygame.draw.circle(s, (200, 235, 255), (cx, cy), max(2, r // 2), 2)
            return s
        if nama == "bg_underwater":
            return None  
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
