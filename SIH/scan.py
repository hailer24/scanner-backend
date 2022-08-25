# USAGE:
# python scan.py (--images <IMG_DIR> | --image <IMG_PATH>) [-i]
# For example, to scan a single image with interactive mode:
# python scan.py --image sample_images/desk.JPG -i
# To scan all images in a directory automatically:
# python scan.py --images sample_images

# Scanned images will be output to directory named 'output'

from . import transform
from . import imutils
from scipy.spatial import distance as dist
from matplotlib.patches import Polygon
import numpy as np
import matplotlib.pyplot as plt
import itertools
import math
import cv2
from io import BytesIO
from pylsd.lsd import lsd
from . import white_board
from . import grayscale_filter
import argparse
import os

MIN_QUAD_AREA_RATIO = 0.25
MAX_QUAD_ANGLE_RANGE = 40
def filter_corners( corners, min_dist=20):
    """Filters corners that are within min_dist of others"""
    def predicate(representatives, corner):
        return all(dist.euclidean(representative, corner) >= min_dist
                   for representative in representatives)

    filtered_corners = []
    for c in corners:
        if predicate(filtered_corners, c):
            filtered_corners.append(c)
    return filtered_corners

def angle_between_vectors_degrees( u, v):
    """Returns the angle between two vectors in degrees"""
    return np.degrees(
        math.acos(np.dot(u, v) / (np.linalg.norm(u) * np.linalg.norm(v))))

def get_angle( p1, p2, p3):
    """
    Returns the angle between the line segment from p2 to p1 
    and the line segment from p2 to p3 in degrees
    """
    a = np.radians(np.array(p1))
    b = np.radians(np.array(p2))
    c = np.radians(np.array(p3))

    avec = a - b
    cvec = c - b

    return angle_between_vectors_degrees(avec, cvec)

def angle_range( quad):
    """
    Returns the range between max and min interior angles of quadrilateral.
    The input quadrilateral must be a numpy array with vertices ordered clockwise
    starting with the top left vertex.
    """
    tl, tr, br, bl = quad
    ura = get_angle(tl[0], tr[0], br[0])
    ula = get_angle(bl[0], tl[0], tr[0])
    lra = get_angle(tr[0], br[0], bl[0])
    lla = get_angle(br[0], bl[0], tl[0])

    angles = [ura, ula, lra, lla]
    return np.ptp(angles)          

def get_corners( img):
    """
    Returns a list of corners ((x, y) tuples) found in the input image. With proper
    pre-processing and filtering, it should output at most 10 potential corners.
    This is a utility function used by get_contours. The input image is expected 
    to be rescaled and Canny filtered prior to be passed in.
    """
    lines = lsd(img)

    # massages the output from LSD
    # LSD operates on edges. One "line" has 2 edges, and so we need to combine the edges back into lines
    # 1. separate out the lines into horizontal and vertical lines.
    # 2. Draw the horizontal lines back onto a canvas, but slightly thicker and longer.
    # 3. Run connected-components on the new canvas
    # 4. Get the bounding box for each component, and the bounding box is final line.
    # 5. The ends of each line is a corner
    # 6. Repeat for vertical lines
    # 7. Draw all the final lines onto another canvas. Where the lines overlap are also corners

    corners = []
    if lines is not None:
        # separate out the horizontal and vertical lines, and draw them back onto separate canvases
        lines = lines.squeeze().astype(np.int32).tolist()
        horizontal_lines_canvas = np.zeros(img.shape, dtype=np.uint8)
        vertical_lines_canvas = np.zeros(img.shape, dtype=np.uint8)
        for line in lines:
            x1, y1, x2, y2, _ = line
            if abs(x2 - x1) > abs(y2 - y1):
                (x1, y1), (x2, y2) = sorted(((x1, y1), (x2, y2)), key=lambda pt: pt[0])
                cv2.line(horizontal_lines_canvas, (max(x1 - 5, 0), y1), (min(x2 + 5, img.shape[1] - 1), y2), 255, 2)
            else:
                (x1, y1), (x2, y2) = sorted(((x1, y1), (x2, y2)), key=lambda pt: pt[1])
                cv2.line(vertical_lines_canvas, (x1, max(y1 - 5, 0)), (x2, min(y2 + 5, img.shape[0] - 1)), 255, 2)

        lines = []

        # find the horizontal lines (connected-components -> bounding boxes -> final lines)
        (contours, hierarchy) = cv2.findContours(horizontal_lines_canvas, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        contours = sorted(contours, key=lambda c: cv2.arcLength(c, True), reverse=True)[:2]
        horizontal_lines_canvas = np.zeros(img.shape, dtype=np.uint8)
        for contour in contours:
            contour = contour.reshape((contour.shape[0], contour.shape[2]))
            min_x = np.amin(contour[:, 0], axis=0) + 2
            max_x = np.amax(contour[:, 0], axis=0) - 2
            left_y = int(np.average(contour[contour[:, 0] == min_x][:, 1]))
            right_y = int(np.average(contour[contour[:, 0] == max_x][:, 1]))
            lines.append((min_x, left_y, max_x, right_y))
            cv2.line(horizontal_lines_canvas, (min_x, left_y), (max_x, right_y), 1, 1)
            corners.append((min_x, left_y))
            corners.append((max_x, right_y))

        # find the vertical lines (connected-components -> bounding boxes -> final lines)
        (contours, hierarchy) = cv2.findContours(vertical_lines_canvas, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        contours = sorted(contours, key=lambda c: cv2.arcLength(c, True), reverse=True)[:2]
        vertical_lines_canvas = np.zeros(img.shape, dtype=np.uint8)
        for contour in contours:
            contour = contour.reshape((contour.shape[0], contour.shape[2]))
            min_y = np.amin(contour[:, 1], axis=0) + 2
            max_y = np.amax(contour[:, 1], axis=0) - 2
            top_x = int(np.average(contour[contour[:, 1] == min_y][:, 0]))
            bottom_x = int(np.average(contour[contour[:, 1] == max_y][:, 0]))
            lines.append((top_x, min_y, bottom_x, max_y))
            cv2.line(vertical_lines_canvas, (top_x, min_y), (bottom_x, max_y), 1, 1)
            corners.append((top_x, min_y))
            corners.append((bottom_x, max_y))

        # find the corners
        corners_y, corners_x = np.where(horizontal_lines_canvas + vertical_lines_canvas == 2)
        corners += zip(corners_x, corners_y)

    # remove corners in close proximity
    corners = filter_corners(corners)
    return corners

def is_valid_contour( cnt, IM_WIDTH, IM_HEIGHT):
    """Returns True if the contour satisfies all requirements set at instantitation"""
    global MIN_QUAD_AREA_RATIO , MAX_QUAD_ANGLE_RANGE
    return (len(cnt) == 4 and cv2.contourArea(cnt) > IM_WIDTH * IM_HEIGHT * MIN_QUAD_AREA_RATIO 
        and angle_range(cnt) < MAX_QUAD_ANGLE_RANGE)


def get_contour( rescaled_image):
    """
    Returns a numpy array of shape (4, 2) containing the vertices of the four corners
    of the document in the image. It considers the corners returned from get_corners()
    and uses heuristics to choose the four corners that most likely represent
    the corners of the document. If no corners were found, or the four corners represent
    a quadrilateral that is too small or convex, it returns the original four corners.
    """

    # these constants are carefully chosen
    MORPH = 9
    CANNY = 84
    HOUGH = 25

    IM_HEIGHT, IM_WIDTH, _ = rescaled_image.shape

    # convert the image to grayscale and blur it slightly
    gray = cv2.cvtColor(rescaled_image, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3,3), 0)

    # dilate helps to remove potential holes between edge segments
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT,(MORPH,MORPH))
    dilated = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, kernel)

    # find edges and mark them in the output map using the Canny algorithm
    edged = cv2.Canny(dilated, 0, CANNY)
    test_corners = get_corners(edged)

    approx_contours = []

    if len(test_corners) >= 4:
        quads = []

        for quad in itertools.combinations(test_corners, 4):
            points = np.array(quad)
            points = transform.order_points(points)
            points = np.array([[p] for p in points], dtype = "int32")
            quads.append(points)

        # get top five quadrilaterals by area
        quads = sorted(quads, key=cv2.contourArea, reverse=True)[:5]
        # sort candidate quadrilaterals by their angle range, which helps remove outliers
        quads = sorted(quads, key=angle_range)

        approx = quads[0]
        if is_valid_contour(approx, IM_WIDTH, IM_HEIGHT):
            approx_contours.append(approx)

        # for debugging: uncomment the code below to draw the corners and countour found 
        # by get_corners() and overlay it on the image

        # cv2.drawContours(rescaled_image, [approx], -1, (20, 20, 255), 2)
        # plt.scatter(*zip(*test_corners))
        # plt.imshow(rescaled_image)
        # plt.show()

    # also attempt to find contours directly from the edged image, which occasionally 
    # produces better results
    (cnts, hierarchy) = cv2.findContours(edged.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cnts = sorted(cnts, key=cv2.contourArea, reverse=True)[:5]

    # loop over the contours
    for c in cnts:
        # approximate the contour
        approx = cv2.approxPolyDP(c, 80, True)
        if is_valid_contour(approx, IM_WIDTH, IM_HEIGHT):
            approx_contours.append(approx)
            break

    # If we did not find any valid contours, just use the whole image
    if not approx_contours:
        TOP_RIGHT = (IM_WIDTH, 0)
        BOTTOM_RIGHT = (IM_WIDTH, IM_HEIGHT)
        BOTTOM_LEFT = (0, IM_HEIGHT)
        TOP_LEFT = (0, 0)
        screenCnt = np.array([[TOP_RIGHT], [BOTTOM_RIGHT], [BOTTOM_LEFT], [TOP_LEFT]])

    else:
        screenCnt = max(approx_contours, key=cv2.contourArea)
        
    return screenCnt.reshape(4, 2)

def data_uri_to_cv2_img(uri):
    encoded_data = uri.split(',')[1]
    nparr = np.fromstring(encoded_data.decode('base64'), np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    return img

def scan( image_path):

    RESCALED_HEIGHT = 500.0
    # load the image and compute the ratio of the old height
    # to the new height, clone it, and resize it

    image = cv2.imread(image_path)
    
    if image is None:
        return None

    ratio = image.shape[0] / RESCALED_HEIGHT
    orig = image.copy()
    # print(image.shape)
    rescaled_image = imutils.resize(image, height = int(RESCALED_HEIGHT))

    # get the contour of the document
    screenCnt = get_contour(rescaled_image)

    # apply the perspective transformation
    warped = transform.four_point_transform(orig, screenCnt * ratio)

    # convert the warped image to grayscale
    # gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
    # gray = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 29, 3)

    # sharpen image
    # sharpen = cv2.GaussianBlur(gray, (0,0), 3)
    # sharpen = cv2.addWeighted(gray, 1.5, sharpen, -0.5, 0)

    # apply adaptive threshold to get black and white effect
    # thresh = cv2.adaptiveThreshold(sharpen, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 21, 15)

    # save the transformed image
    basename = os.path.basename(image_path)
    # cv2.imshow('out',sharpen )
    # cv2.imshow('out_colorur', warped)
    # # press esc or q to quit
    # cv2.waitKey(0)
    # cv2.destroyAllWindows()
    cv2.imwrite('out1.png', warped)
    # print("Proccessed " + basename)

    # with open("out1.png", "rb") as image2string:
    #     converted_string = base64.b64encode(image2string.read())

    # return converted_string


    # enable return statement if u need to get the image in return 
    # return thresh

 

import base64
from PIL import Image as im



    
#thresholding filer 
def add_filter(img_path):
    image = cv2.imread(img_path)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    # gray = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 29, 3)
    sharpen = cv2.GaussianBlur(gray, (3,3), 3)
    sharpen = cv2.addWeighted(gray, 1.5, sharpen, -0.5, 0)

    thres = cv2.adaptiveThreshold(sharpen, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 9, 15)

    cv2.imwrite('out1.png', thres)
    
    return img_path


def encode():
    with open("out1.png", "rb") as image2string:
        converted_string = base64.b64encode(image2string.read())
    return converted_string

def create_opencv_image_from_stringio(img_stream, cv2_img_flag=0):
    img_stream.seek(0)
    img_array = np.asarray(bytearray(img_stream.read()), dtype=np.uint8)
    # print(img_array.shape)
    ret = im.fromarray(img_array)
    return cv2.cvtColor(np.array(ret), cv2.COLOR_RGB2BGR)

def fft(img_path,thres = 0):
    img = cv2.imread(img_path)
    laplcian_var = cv2.Laplacian(img,cv2.CV_64F).var()
    print(laplcian_var)
    if laplcian_var<400:
        return True
    
    return False
def decode(img_buf, filter):
    with open("pre_processed.png", "wb") as fh:
        fh.write(base64.b64decode(img_buf))
    fh.close()
    
    if fft("pre_processed.png"):
        return "blurred"

    scan("pre_processed.png")

    if filter == 0:
        white_board.white_board_filter("out1.png",4,5)
    elif filter == 1:
        add_filter("out1.png")
    elif filter == 2:
        grayscale_filter.grayscaling_filter("out1.png")
        

    return encode()
