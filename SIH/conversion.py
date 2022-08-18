import base64
from sys import argv

def encode():  
    with open("1.jpeg", "rb") as image2string:
        converted_string = base64.b64encode(image2string.read())
    print(converted_string)
    
    with open('encode.bin', "wb") as file:
        file.write(converted_string)


def decode():
    file = open('encode.bin', 'rb')
    byte = file.read()
    file.close()
    # print(base64.b64decode((byte)))
  
    decodeit = open('out.jpeg', 'wb')
    decodeit.write(base64.b64decode((byte)))
    decodeit.close()
decode()

    