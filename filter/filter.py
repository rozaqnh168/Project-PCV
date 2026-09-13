import cv2
from matplotlib import pyplot as plt

#Filter Gambar
"""
gambar = cv2.imread("gambar.jpg")
gmbtype = gambar.dtype
(w,h,c) = gambar.shape

for i in range(w):
    for j in range(h):
        # Lapisan Green = 0
        gambar[i,j,1]=0
        # Lapisan Blue = 0
        gambar[i,j,0]=0
        #Lapisan Red = 0
        #gambar[i,j,2]=0

plt.imshow(gambar)
plt.title("Gambar")
#plt.show()

cv2.imshow("Gambar", gambar)
cv2.waitKey(0)
cv2.destroyAllWindows()
cv2.waitKey(1)
"""


#Video Webcam

kamera = cv2.VideoCapture(0)

while True:
    ret, frame = kamera.read()
    (w, h, c) = frame.shape

    # FILTER
    for i in range(w):
        for j in range(h):
            frame[i,j,1] = 0
            frame[i,j,0] = 0

    cv2.imshow("Video", frame)

    key = cv2.waitKey(1) & 0xFF

    if key == 27:
        break
    try :
        if cv2.getWindowProperty("Video", cv2.WND_PROP_VISIBLE) < 1:
         break
    except cv2.error:
        break

kamera.release()
cv2.destroyAllWindows()
