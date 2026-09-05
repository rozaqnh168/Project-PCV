import cv2

# =========================
# 1. BACA GAMBAR
# =========================

gambar = cv2.imread("gambar.jpg")


# =========================
# 2. GRAYSCALE
# =========================

gray = cv2.cvtColor(gambar, cv2.COLOR_BGR2GRAY)


# =========================
# 3. RED FILTER
# =========================

red = gambar.copy()

red[:, :, 0] = 0
red[:, :, 1] = 0


# =========================
# 4. TAMPILKAN
# =========================

cv2.namedWindow("Original", cv2.WINDOW_NORMAL)
cv2.namedWindow("Grayscale", cv2.WINDOW_NORMAL)
cv2.namedWindow("Red Filter", cv2.WINDOW_NORMAL)

cv2.resizeWindow("Original", 800, 600)
cv2.resizeWindow("Grayscale", 800, 600)
cv2.resizeWindow("Red Filter", 800, 600)

cv2.imshow("Original", gambar)
cv2.imshow("Grayscale", gray)
cv2.imshow("Red Filter", red)

cv2.waitKey(0)
cv2.destroyAllWindows()