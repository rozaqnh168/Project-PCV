import math
import random
import time
import cv2
import numpy as np
import pygame

from . import config
from .assets import AssetManager
from .camera import PelacakKamera
from .entities import IkanMusuh, IkanPemain
from .particles import SistemPartikel


class Game:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((config.WIDTH, config.HEIGHT))
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
        self.state = "SIAP"
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
        lebar_lama, tinggi_lama = config.WIDTH, config.HEIGHT
        config.WIDTH, config.HEIGHT = ukuran
        self.screen = pygame.display.set_mode(ukuran)
        sx, sy = config.WIDTH / lebar_lama, config.HEIGHT / tinggi_lama
        for objek in [self.pemain, *self.musuh]:
            objek.x *= sx
            objek.y *= sy
        for partikel in self.partikel.partikel:
            partikel["x"] *= sx
            partikel["y"] *= sy
        self.pemain.x = max(self.pemain.radius,
                            min(config.WIDTH - self.pemain.radius, self.pemain.x))
        self.pemain.y = max(self.pemain.radius,
                            min(config.HEIGHT - self.pemain.radius, self.pemain.y))
        self.bg = self._buat_bg()
        self.menu_rect = None
        self.game_over_rect = None

    def _buat_bg(self):
        if self.assets.punya_eksternal("bg_underwater"):
            img = self.assets.sumber["bg_underwater"]
            bg = pygame.transform.smoothscale(img, (config.WIDTH, config.HEIGHT))
        else:
            bg = pygame.Surface((config.WIDTH, config.HEIGHT))
            for y in range(config.HEIGHT):
                t = y / config.HEIGHT
                warna = (int(10 + 25 * t), int(60 + 60 * t), int(110 + 70 * t))
                pygame.draw.line(bg, warna, (0, y), (config.WIDTH, y))
            for i in range(0, config.WIDTH, 90):
                tinggi = random.randint(50, 130)
                titik = [(i, config.HEIGHT)]
                for j in range(1, 6):
                    titik.append((i + random.randint(-14, 14), config.HEIGHT - tinggi * j // 5))
                pygame.draw.lines(bg, (20, 90, 70), False, titik, 6)
        for nama, jumlah in (("seaweed", 7), ("coral", 4), ("rock", 4)):
            if not self.assets.punya_eksternal(nama):
                continue
            for _ in range(jumlah):
                tinggi = random.randint(60, 150)
                sp = self.assets.ambil(nama, tinggi // 2)
                x = random.randint(-30, config.WIDTH - 40)
                bg.blit(sp, (x, config.HEIGHT - sp.get_height() + random.randint(0, 14)))
        return bg

    def reset(self):
        self.pemain = IkanPemain(self.assets)
        self.musuh = []
        self.partikel = SistemPartikel(self.assets)
        self.skor = 0
        self.terbaik = self.muat_terbaik()
        self.spawn_timer = 0.0
        self.ambil_pos = None
        self.pesan_makan = 0

    def muat_terbaik(self):
        try:
            with open(config.SKOR_FILE) as f:
                return int(f.read().strip())
        except Exception:
            return 0

    def simpan_terbaik(self):
        try:
            with open(config.SKOR_FILE, "w") as f:
                f.write(str(max(self.terbaik, self.skor)))
        except Exception:
            pass

    def _pilih_level_musuh(self):
        lvl = self.pemain.level
        if lvl == 1:
            levels, weights = [1, 2], [0.65, 0.35]
        elif lvl == 2:
            levels, weights = [1, 2, 3], [0.50, 0.35, 0.15]
        else:
            levels, weights = [1, 2, 3, 4], [0.32, 0.34, 0.20, 0.14]

        for level, batas in config.BATAS_MUSUH.items():
            if level in levels and sum(m.level == level for m in self.musuh) >= batas:
                index = levels.index(level)
                levels.pop(index)
                weights.pop(index)

        return random.choices(levels, weights=weights)[0]

    def update_spawner(self, dt):
        self.spawn_timer += dt
        interval = max(0.8, 2.0 - self.skor * 0.004) / 1.5
        if self.spawn_timer >= interval:
            self.spawn_timer = 0
            self.musuh.append(IkanMusuh(self.assets, self._pilih_level_musuh()))

    def update_tabrakan(self):
        p = self.pemain
        for m in self.musuh[:]:
            jarak = ((m.x - p.x) ** 2 + (m.y - p.y) ** 2) ** 0.5
            if jarak < m.radius + p.radius - 6:
                if m.level <= p.level:
                    self.skor += m.poin
                    p.mulai_makan()
                    tumbuh = p.perbarui_pertumbuhan(self.skor)
                    self.partikel.ledakan(m.x, m.y, n=20 + m.level * 6)
                    self.ambil_pos = (m.x, m.y, f"+{m.poin}")
                    self.pesan_makan = 40
                    if tumbuh:
                        self.ambil_pos = (p.x, p.y - 50, "BERTUMBUH!")
                        self.partikel.ledakan(p.x, p.y, n=40)
                    self.musuh.remove(m)
                else:                             
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

    def teks_tengah(self, string, y, font=None, warna=(255, 255, 255)):
        font = font or self.font_sedang
        img = font.render(string, True, warna)
        rect = img.get_rect(center=(config.WIDTH // 2, y))
        self.screen.blit(font.render(string, True, (20, 30, 40)), rect.move(2, 2))
        self.screen.blit(img, rect)
        return rect

    def _gambar_panel_ui(self, nama, ukuran, tengah):
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
        return {
            "retry": self._hitbox_panel(
                self.game_over_rect, (0.197, 0.745, 0.515, 0.874)),
            "menu": self._hitbox_panel(
                self.game_over_rect, (0.535, 0.745, 0.848, 0.876)),
        }

    def _gambar_highlight(self, rect, warna=(255, 235, 120), radius=24):
        if not rect:
            return
        if rect.collidepoint(pygame.mouse.get_pos()):
            self.hover_aktif = True
            pad = 10
            glow = pygame.Surface((rect.width + pad * 2, rect.height + pad * 2),
                                  pygame.SRCALPHA)
            for i, alfa in enumerate((18, 30, 46)):
                r = glow.get_rect().inflate(-i * 6, -i * 6)
                pygame.draw.rect(glow, (*warna, alfa), r, 3,
                                 border_radius=radius + pad - i * 3)
            dalam = pygame.Rect(pad, pad, rect.width, rect.height)
            pygame.draw.rect(glow, (255, 255, 255, 28), dalam,
                             border_radius=radius)          
            pygame.draw.rect(glow, (*warna, 235), dalam.inflate(2, 2), 3,
                             border_radius=radius)
            self.screen.blit(glow, (rect.left - pad, rect.top - pad))

    def _teks_angka(self, teks, tengah, tinggi):
        font = pygame.font.SysFont("dejavusansbold", tinggi, bold=True)
        isi = font.render(teks, True, (255, 255, 255))
        w, h = isi.get_size()
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
        rect = self._hitbox_panel(panel, area)
        if bersih:
            self._teks_angka(f"{nilai:06d}", rect.center, ukuran_font)
            return
        pygame.draw.rect(self.screen, (8, 65, 108), rect, border_radius=8)
        self._teks_ui(f"{nilai:06d}", rect.center, ukuran_font, rect.width - 8)

    def _gambar_options(self):
        kabut = pygame.Surface((config.WIDTH, config.HEIGHT), pygame.SRCALPHA)
        kabut.fill((0, 10, 35, 220))
        self.screen.blit(kabut, (0, 0))
        self.teks_tengah("OPTIONS", 100, self.font_besar, config.KUNING)
        self.teks_tengah("PILIH UKURAN WINDOW", 155, self.font_sedang)
        self.opsi_rects = []
        for i, (lebar, tinggi) in enumerate(self.pilihan_ukuran):
            rect = pygame.Rect(0, 0, min(360, config.WIDTH - 80), 62)
            rect.center = (config.WIDTH // 2, 225 + i * 85)
            aktif = (lebar, tinggi) == (config.WIDTH, config.HEIGHT)
            pygame.draw.rect(self.screen, (15, 115, 175) if aktif else (8, 65, 108),
                             rect, border_radius=16)
            pygame.draw.rect(self.screen, config.KUNING if aktif else (70, 195, 235),
                             rect, 3, border_radius=16)
            label = f"{lebar} x {tinggi}" + ("  (AKTIF)" if aktif else "")
            self._teks_ui(label, rect.center, 27, rect.width - 28)
            self._gambar_highlight(rect)
            self.opsi_rects.append((rect, (lebar, tinggi)))
        self.kembali_rect = pygame.Rect(0, 0, 180, 52)
        self.kembali_rect.center = (config.WIDTH // 2, 490)
        pygame.draw.rect(self.screen, (8, 65, 108), self.kembali_rect,
                         border_radius=14)
        pygame.draw.rect(self.screen, (70, 195, 235), self.kembali_rect,
                         3, border_radius=14)
        self._teks_ui("KEMBALI", self.kembali_rect.center, 25,
                      self.kembali_rect.width - 20)
        self._gambar_highlight(self.kembali_rect)

    def gambar_panel(self, frame, mask, pos):
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
        px, py = 12, config.HEIGHT - h - 12
        self.screen.blit(panel, (px, py))
        pygame.draw.rect(self.screen, (255, 255, 255), (px, py, w, h), 2)
        if pos:
            hx = px + int(pos[0] * w / config.CAM_W)
            hy = py + int(pos[1] * h / config.CAM_H)
            pygame.draw.circle(self.screen, (255, 60, 60), (hx, hy), 5, 2)

    def mulai_kalibrasi(self):
        self.reset()
        self.state = "KALIBRASI"
        self.kalib_sampel.clear()
        self.kalib_timer = 0.0
        self.kalib_selesai = 0.0
        self.kalib_gagal = False
        self.kalib_aktif = False
        self.kalib_pesan = "TEKAN K UNTUK MULAI KALIBRASI"

    def ulang_permainan(self):
        self.reset()
        self.waktu_persiapan = 3.0
        self.state = "HITUNG_MUNDUR"

    def update_kalibrasi(self, frame, dt):
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
        config.HSV_BAWAH = np.array([max(h - 12, 0), 60, 60])
        config.HSV_ATAS = np.array([min(h + 12, 179), 255, 255])
        self.kalib_selesai = 0.8
        self.kalib_pesan = "KALIBRASI BERHASIL - GAME DIMULAI!"

    def _gambar_kalibrasi(self, frame):
        kabut = pygame.Surface((config.WIDTH, config.HEIGHT), pygame.SRCALPHA)
        kabut.fill((0, 10, 35, 225))
        self.screen.blit(kabut, (0, 0))
        self.teks_tengah("KALIBRASI WARNA", 65, self.font_besar, config.KUNING)
        self.teks_tengah("Letakkan dan tahan tangan di dalam kotak", 112,
                         self.font_sedang)
        if frame is not None:
            gambar = np.transpose(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), (1, 0, 2))
            preview = pygame.surfarray.make_surface(gambar)
            preview = pygame.transform.smoothscale(preview, (400, 300))
            rect = preview.get_rect(center=(config.WIDTH // 2, 290))
            self.screen.blit(preview, rect)
            pygame.draw.rect(self.screen, (255, 255, 255), rect, 3,
                             border_radius=4)
            kotak = pygame.Rect(0, 0, 100, 100)
            kotak.center = rect.center
            pygame.draw.rect(self.screen, config.KUNING, kotak, 4)
        else:
            pygame.draw.rect(self.screen, (10, 55, 85),
                             (config.WIDTH // 2 - 200, 140, 400, 300))
        warna = (100, 255, 160) if self.kalib_selesai else (255, 255, 255)
        self.teks_tengah(self.kalib_pesan, 475, self.font_kecil, warna)
        if self.kalib_timer > 0:
            pygame.draw.rect(self.screen, (15, 75, 110),
                             (config.WIDTH // 2 - 200, 505, 400, 18), border_radius=9)
            lebar = int(400 * min(self.kalib_timer / 2.0, 1.0))
            if lebar:
                pygame.draw.rect(self.screen, (70, 220, 255),
                                 (config.WIDTH // 2 - 200, 505, lebar, 18), border_radius=9)
        self.teks_tengah("ESC: kembali ke menu", 555, self.font_kecil)

    def update(self, dt, frame, pos):
        if self.state == "SIAP":
            self.pemain.update(pos, config.LERP_NORMAL, dt)
        elif self.state == "HITUNG_MUNDUR":
            self.pemain.update(pos, config.LERP_NORMAL, dt)
            self.waktu_persiapan -= dt
            if self.waktu_persiapan <= 0:
                self.state = "MAIN"
        elif self.state == "MAIN":
            self.pemain.update(pos, config.LERP_NORMAL, dt)
            self.update_spawner(dt)
            for musuh in self.musuh:
                musuh.update(dt)
            self.musuh = [musuh for musuh in self.musuh
                          if not musuh.di_luar_layar()]
            self.update_tabrakan()
            if self.state == "MAIN":
                if random.random() < 0.3:
                    self.partikel.ambient()
                if random.random() < 0.008:
                    self.partikel.gelembung_besar(
                        random.randint(60, config.WIDTH - 60),
                        random.randint(80, config.HEIGHT - 80))
                if random.random() < 0.5:
                    self.partikel.jejak(
                        self.pemain.x - self.pemain.radius * self.pemain.arah,
                        self.pemain.y)
        elif self.state == "DIMAKAN":
            for musuh in self.musuh:
                if musuh.sedang_makan:
                    musuh.update(dt)
                    if musuh.animasi_selesai:
                        self.state = "OVER"
                        break
        elif self.state == "KALIBRASI":
            self.update_kalibrasi(frame, dt)

        self.partikel.update()

    def _proses_event(self, event):
        if event.type == pygame.QUIT:
            return False
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self.state == "SIAP":
                tombol = self._tombol_menu()
                if tombol.get("play") and tombol["play"].collidepoint(event.pos):
                    self.mulai_kalibrasi()
                elif tombol.get("options") and tombol["options"].collidepoint(event.pos):
                    self.state = "OPTIONS"
                elif tombol.get("quit") and tombol["quit"].collidepoint(event.pos):
                    return False
            elif self.state == "OPTIONS":
                if self.kembali_rect and self.kembali_rect.collidepoint(event.pos):
                    self.state = "SIAP"
                else:
                    for rect, ukuran in self.opsi_rects:
                        if rect.collidepoint(event.pos):
                            if ukuran != (config.WIDTH, config.HEIGHT):
                                self.ubah_ukuran(ukuran)
                            break
            elif self.state == "OVER":
                tombol = self._tombol_game_over()
                if tombol.get("retry") and tombol["retry"].collidepoint(event.pos):
                    self.ulang_permainan()
                elif tombol.get("menu") and tombol["menu"].collidepoint(event.pos):
                    self.reset()
                    self.state = "SIAP"
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE and self.state in ("OPTIONS", "KALIBRASI"):
                self.state = "SIAP"
                self.kalib_timer = 0
                self.kalib_selesai = 0
            elif event.key in (pygame.K_q, pygame.K_ESCAPE):
                return False
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE) and self.state == "SIAP":
                self.mulai_kalibrasi()
            elif event.key == pygame.K_o and self.state == "SIAP":
                self.state = "OPTIONS"
            elif event.key == pygame.K_m:
                self.panel_tampil = not self.panel_tampil
            elif event.key == pygame.K_r and self.state == "OVER":
                self.ulang_permainan()
            elif event.key == pygame.K_r and self.state in ("MAIN", "DIMAKAN"):
                self.reset()
                self.state = "SIAP"
            elif (event.key == pygame.K_k and self.state == "KALIBRASI"
                  and not self.kalib_selesai):
                self.kalib_aktif = True
                self.kalib_timer = 0.0001
                self.kalib_sampel.clear()
                self.kalib_gagal = False
                self.kalib_pesan = "TAHAN TANGAN TETAP DI DALAM KOTAK"
        return True

    def _update_kalibrasi_manual(self, frame, dt):
        if self.kalib_timer <= 0 or self.state != "SIAP":
            return

        self.kalib_timer += dt
        self.kamera.sampel_kalibrasi(frame, self.kalib_sampel)
        if self.kalib_timer < 1.0:
            return

        self.kalib_timer = 0
        if not self.kalib_sampel:
            return

        h = int(np.median([sampel[0] for sampel in self.kalib_sampel]))
        saturasi = int(np.median([sampel[1] for sampel in self.kalib_sampel]))
        value = int(np.median([sampel[2] for sampel in self.kalib_sampel]))
        if saturasi >= 60 and value >= 60:
            config.HSV_BAWAH = np.array([max(h - 12, 0), 60, 60])
            config.HSV_ATAS = np.array([min(h + 12, 179), 255, 255])
        else:
            print("Kalibrasi gagal: warna terlalu pucat.")

    def jalankan(self):
        t_sebelum = time.time()
        jalan = True
        while jalan:
            dt = min(time.time() - t_sebelum, 0.05)
            t_sebelum = time.time()

            frame, mask, pos = self.kamera.baca()
            self.update(dt, frame, pos)

            self.hover_aktif = False
            self.screen.blit(self.bg, (0, 0))
            self.partikel.gambar(self.screen)

            for m in self.musuh:
                sp = m.sprite
                if m.arah == -1:
                    sp = pygame.transform.flip(sp, True, False)
                self.screen.blit(sp, sp.get_rect(center=(int(m.x), int(m.y))))


            if self.state in ("SIAP", "MAIN", "HITUNG_MUNDUR"):
                sp = self.pemain.sprite
                if self.pemain.arah == -1:
                    sp = pygame.transform.flip(sp, True, False)
                self.screen.blit(sp, sp.get_rect(center=(int(self.pemain.x),
                                                         int(self.pemain.y))))


            if self.state == "MAIN":
                nama_status = config.STATUS_UKURAN[self.pemain.level]
                if self.assets.punya_eksternal(nama_status):
                    asli = self.assets.sumber[nama_status]
                    lebar_status = min(390, config.WIDTH // 2 - 20)
                    tinggi_status = int(asli.get_height() * lebar_status / asli.get_width())
                    status = pygame.transform.smoothscale(
                        asli, (lebar_status, tinggi_status))
                    self.screen.blit(status, (12, -30))
                score_rect = self._gambar_panel_ui("score", (270, 110), (config.WIDTH - 100, 45))
                if score_rect:
                    self._gambar_nilai_panel(
                        score_rect, (0.38, 0.42, 0.85, 0.65), self.skor, 38)
                else:
                    self.teks_tengah(f"SKOR {self.skor}", 35, self.font_sedang)
                if pos is None:
                    self.teks_tengah("TANGAN TIDAK TERDETEKSI!", config.HEIGHT - 60,
                                     self.font_sedang, (255, 90, 90))

                if self.ambil_pos:
                    x, y, txt = self.ambil_pos
                    img = self.font_sedang.render(txt, True, config.KUNING)
                    self.screen.blit(img, (int(x), int(y)))
                    self.ambil_pos = (x, y - 1.2, txt)
                    if y < 40:
                        self.ambil_pos = None

            elif self.state == "SIAP":
                kabut = pygame.Surface((config.WIDTH, config.HEIGHT), pygame.SRCALPHA)
                kabut.fill((0, 0, 20, 100))
                self.screen.blit(kabut, (0, 0))
                self.menu_rect = self._gambar_panel_ui(
                    "main_menu", (620, 590), (config.WIDTH // 2, config.HEIGHT // 2))
                for rect in self._tombol_menu().values():
                    self._gambar_highlight(rect)
                if not self.menu_rect:
                    self.teks_tengah("FEEDING FRENZY: HAND HUNTER", 180,
                                     self.font_besar, config.KUNING)
                    self.teks_tengah("ENTER: bermain | O: options | Q: keluar", 250)
                if self.kalib_timer > 0:
                    self.teks_tengah(f"MEREKAM WARNA {max(0, 1 - self.kalib_timer):.1f}s",
                                     config.HEIGHT - 36, self.font_sedang, (0, 220, 255))

            elif self.state == "KALIBRASI":
                self._gambar_kalibrasi(frame)

            elif self.state == "OPTIONS":
                self._gambar_options()

            elif self.state == "HITUNG_MUNDUR":
                self.teks_tengah(
                    f"BERSIAP! {max(1, math.ceil(self.waktu_persiapan))}",
                    config.HEIGHT // 2, self.font_besar, config.KUNING)

            elif self.state == "OVER":
                kabut = pygame.Surface((config.WIDTH, config.HEIGHT), pygame.SRCALPHA)
                kabut.fill((0, 0, 20, 125))
                self.screen.blit(kabut, (0, 0))
                self.game_over_rect = self._gambar_panel_ui(
                    "game_over", (620, 600), (config.WIDTH // 2, config.HEIGHT // 2))
                if self.game_over_rect:

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

            for event in pygame.event.get():
                jalan = self._proses_event(event) and jalan

            self._update_kalibrasi_manual(frame, dt)

            self.clock.tick(config.FPS)

        self.kamera.stop()
        pygame.quit()
