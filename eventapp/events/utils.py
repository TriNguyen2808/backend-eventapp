from rest_framework.response import Response

def custom_response( status_code=200, message=None, data=None, extra=None):
    response = {
        "statusCode": status_code,
        "message": message,
        "data": data
    }
    if extra:
        response.update(extra)
    return Response(response)
