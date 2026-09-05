import cv2
import numpy as np
import pygame
import sys

# ==========================================
# 1. INISIALISASI GAME (PYGAME)
# ==========================================
pygame.init()
WIDTH, HEIGHT = 800, 600 # Ukuran layar game
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Game Kontrol Warna")
clock = pygame.time.Clock()

# Posisi awal kursor/karakter game
player_x, player_y = WIDTH // 2, HEIGHT // 2
player_radius = 20

# ==========================================
# 2. INISIALISASI KAMERA & WARNA (OPENCV)
# ==========================================
cap = cv2.VideoCapture(0) # 0 = webcam bawaan

# Tentukan batas bawah dan atas warna target (format HSV)
# Contoh di bawah ini untuk warna HIJAU
lower_color = np.array([40, 100, 100])
upper_color = np.array([80, 255, 255])

running = True
while running:
    # ==========================================
    # 3. PENGOLAHAN CITRA (DETEKSI WARNA)
    # ==========================================
    ret, frame = cap.read()
    if not ret:
        break
        
    # Balikkan gambar agar seperti cermin
    frame = cv2.flip(frame, 1)
    
    # Ubah warna BGR (standar OpenCV) ke HSV
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    
    # Buat "Mask" (Saringan warna)
    mask = cv2.inRange(hsv, lower_color, upper_color)
    
    # Bersihkan noise/bintik pada hasil masking
    mask = cv2.erode(mask, None, iterations=2)
    mask = cv2.dilate(mask, None, iterations=2)
    
    # Cari kontur (bentuk/area) dari warna yang terdeteksi
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if contours:
        # Cari area warna yang paling besar (mengabaikan objek kecil berwarna sama)
        largest_contour = max(contours, key=cv2.contourArea)
        
        # Dapatkan titik koordinat (x, y) dari area tersebut
        M = cv2.moments(largest_contour)
        if M["m00"] > 0:
            cam_x = int(M["m10"] / M["m00"])
            cam_y = int(M["m01"] / M["m00"])
            
            # Petakan koordinat kamera ke koordinat game
            # Misalnya kamera resolusi 640x480 ke game resolusi 800x600
            cam_width, cam_height = frame.shape[1], frame.shape[0]
            player_x = int(cam_x * (WIDTH / cam_width))
            player_y = int(cam_y * (HEIGHT / cam_height))
            
            # Gambar lingkaran di jendela kamera untuk melihat titik yang dilacak
            cv2.circle(frame, (cam_x, cam_y), 10, (0, 0, 255), -1)

    # ==========================================
    # 4. LOGIKA & TAMPILAN GAME
    # ==========================================
    # Cek jika tombol X (close) ditekan di game
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

    # Latar belakang game (Hitam)
    screen.fill((0, 0, 0))
    
    # Gambar pemain (kursor) di layar game (Warna Merah)
    pygame.draw.circle(screen, (255, 0, 0), (player_x, player_y), player_radius)
    
    # Perbarui layar game
    pygame.display.flip()
    
    # ==========================================
    # 5. TAMPILAN KAMERA UNTUK DEBUGGING
    # ==========================================
    cv2.imshow("Kamera Asli", frame)
    cv2.imshow("Hasil Masking Warna", mask)
    
    # Batasi frame rate game menjadi 60 FPS
    clock.tick(60)
    
    # Tekan 'q' pada keyboard untuk keluar dari jendela OpenCV
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# Bersihkan dan tutup program
cap.release()
cv2.destroyAllWindows()
pygame.quit()
sys.exit()