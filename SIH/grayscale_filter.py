import cv2
import numpy as np

def grayscaling_filter(img_path):
    img = cv2.imread(img_path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    cv2.imwrite('out1.png', gray)
    
    return img_path
    