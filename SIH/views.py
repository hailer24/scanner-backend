import string
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse, JsonResponse
import json
from . import scan
import base64


@csrf_exempt
def index(request):
    #print(request.body)
    if(request.method == "POST"):
        req_body = request.body.decode('utf-8')
        body = json.loads(req_body)
        ret = scan.decode(body["img"],99)
        if ret == "blurred":
            print ("The image is blurry")
            return HttpResponse(ret)
        print("POST request processed")
        return HttpResponse(ret)
        
    if(request.method == "GET"):
        
        return HttpResponse("GET is not a valid method")

@csrf_exempt
def filtered(request):
    if(request.method == "POST"):
        req_body = request.body.decode('utf-8')
        body = json.loads(req_body)
        ret = scan.decode(body["img"],body["filter"])
        if ret == "blurred":
            print ("The image is blurry")
            return HttpResponse(ret)
        print("POST request processed")
        return HttpResponse(ret)