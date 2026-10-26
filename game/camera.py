import threading
import time
import cv2
import numpy as np

from . import config


class PelacakKamera:
    def __init__(self):
        self.cap = cv2.VideoCapture(0)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.CAM_W)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.CAM_H)
        self.buka = self.cap.isOpened()

        self.lock = threading.Lock()
        self.frame = None            
        self.mask = None             
        self.pos = None              
        self.area = 0                

        self.riwayat_area = []       
        self.dash_aktif = False      
        self.dash_mulai = 0.0
        self.dash_terakhir = 0.0     

        self.aktif = True
        if self.buka:
            self.thread = threading.Thread(target=self._loop, daemon=True)
            self.thread.start()

    def _loop(self):
        while self.aktif:
            ret, frame = self.cap.read()
            if not ret:
                time.sleep(0.01)
                continue
            frame = cv2.flip(frame, 1)          
            if frame.shape[1] != config.CAM_W or frame.shape[0] != config.CAM_H:
                frame = cv2.resize(frame, (config.CAM_W, config.CAM_H))  

            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            mask = cv2.inRange(hsv, config.HSV_BAWAH, config.HSV_ATAS)
            mask = cv2.erode(mask, None, iterations=2)  
            mask = cv2.dilate(mask, None, iterations=2)

            pos, area = None, 0
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL,
                                           cv2.CHAIN_APPROX_SIMPLE)
            if contours:
                terbesar = max(contours, key=cv2.contourArea)
                area = cv2.contourArea(terbesar)
                if area >= config.MIN_AREA:
                    M = cv2.moments(terbesar)
                    if M["m00"] > 0:
                        pos = (int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"]))
                        cv2.circle(frame, pos, 8, (0, 0, 255), -1)  

            with self.lock:
                self.frame = frame
                self.mask = mask
                self.pos = pos
                self.area = area

            time.sleep(0.004)  

    def baca(self):
        with self.lock:
            return self.frame, self.mask, self.pos, self.area, self.dash_aktif

    def cek_dash(self, area):
        now = time.time()
        if self.dash_aktif or now - self.dash_terakhir < config.DASH_COOlDOWN:
            self._simpan_baseline(area)
            return False
        self.riwayat_area.append(area)
        if len(self.riwayat_area) > 60:
            self.riwayat_area.pop(0)
        if len(self.riwayat_area) >= 12:
            baseline = np.median(self.riwayat_area)
            if baseline > config.MIN_AREA and area > baseline * config.DASH_RASIO:
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
        if self.dash_aktif and time.time() - self.dash_mulai >= config.DASH_DURASI:
            self.dash_aktif = False
            self.riwayat_area.clear()
        return self.dash_aktif

    def sampel_kalibrasi(self, frame, kumpulan):
        if frame is None:
            return
        x1, y1 = config.CAM_W // 2 - 40, config.CAM_H // 2 - 40
        x2, y2 = config.CAM_W // 2 + 40, config.CAM_H // 2 + 40
        roi = frame[y1:y2, x1:x2]
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        h, s, v = cv2.split(hsv)
        kumpulan.append((int(np.median(h)), int(np.median(s)), int(np.median(v))))

    def stop(self):
        self.aktif = False
        if self.buka:
            time.sleep(0.05)
            self.cap.release()
