import string
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse, JsonResponse
import json
from . import scan
import base64


@csrf_exempt
def index(request):
    print(request.body)
    if(request.method == "POST"):
        req_body = request.body.decode('utf-8')
        body = json.loads(req_body)
        ret = scan.decode(body["img"])
        print(ret)
        return HttpResponse(ret)
        # return HttpResponse("req rec")
    if(request.method == "GET"):
        print(request.body)
        return HttpResponse("yo yi s")
