import hashlib
import hmac
import urllib.parse
import datetime
from django.conf import settings

def build_vnpay_url(order_id, amount, return_url, ip_address, order_desc="Thanh toan ve su kien"):
    vnp_url = "https://sandbox.vnpayment.vn/paymentv2/vpcpay.html"
    vnp_params = {
        'vnp_Version': '2.1.0',
        'vnp_Command': 'pay',
        'vnp_TmnCode': settings.VNPAY_TMN_CODE,
        'vnp_Amount': str(int(amount)),  # Nhân đúng 100
        'vnp_CurrCode': 'VND',
        'vnp_TxnRef': str(order_id),
        'vnp_OrderInfo': order_desc,
        'vnp_OrderType': 'billpayment',
        'vnp_Locale': 'vn',
        'vnp_ReturnUrl': return_url,
        'vnp_IpAddr': ip_address,
        'vnp_CreateDate': datetime.datetime.now().strftime('%Y%m%d%H%M%S'),
    }

    # Sort and build hash string
    sorted_params = sorted(vnp_params.items())
    hash_data = '&'.join(f"{k}={v}" for k, v in sorted_params)

    secure_hash = hmac.new(
        settings.VNPAY_HASH_SECRET_KEY.encode('utf-8'),
        hash_data.encode('utf-8'),
        hashlib.sha512
    ).hexdigest()

    query_string = urllib.parse.urlencode(sorted_params, quote_via=urllib.parse.quote_plus)
    payment_url = f"{vnp_url}?{query_string}&vnp_SecureHash={secure_hash}"

    print(settings.VNPAY_HASH_SECRET_KEY)
    return payment_url


# import hashlib
# import hmac
# import urllib.parse
#
# class vnpay:
#     requestData = {}
#     responseData = {}
#
#     def get_payment_url(self, vnpay_payment_url, secret_key):
#         inputData = sorted(self.requestData.items())
#         queryString = ''
#         hasData = ''
#         seq = 0
#         for key, val in inputData:
#             if seq == 1:
#                 queryString = queryString + "&" + key + '=' + urllib.parse.quote_plus(str(val))
#             else:
#                 seq = 1
#                 queryString = key + '=' + urllib.parse.quote_plus(str(val))
#
#         hashValue = self.__hmacsha512(secret_key, queryString)
#         return vnpay_payment_url + "?" + queryString + '&vnp_SecureHash=' + hashValue
#
#     def validate_response(self, secret_key):
#         vnp_SecureHash = self.responseData['vnp_SecureHash']
#         # Remove hash params
#         if 'vnp_SecureHash' in self.responseData.keys():
#             self.responseData.pop('vnp_SecureHash')
#
#         if 'vnp_SecureHashType' in self.responseData.keys():
#             self.responseData.pop('vnp_SecureHashType')
#
#         inputData = sorted(self.responseData.items())
#         hasData = ''
#         seq = 0
#         for key, val in inputData:
#             if str(key).startswith('vnp_'):
#                 if seq == 1:
#                     hasData = hasData + "&" + str(key) + '=' + urllib.parse.quote_plus(str(val))
#                 else:
#                     seq = 1
#                     hasData = str(key) + '=' + urllib.parse.quote_plus(str(val))
#         hashValue = self.__hmacsha512(secret_key, hasData)
#
#         print(
#             'Validate debug, HashData:' + hasData + "\n HashValue:" + hashValue + "\nInputHash:" + vnp_SecureHash)
#
#         return vnp_SecureHash == hashValue
#
#     @staticmethod
#     def __hmacsha512(key, data):
#         byteKey = key.encode('utf-8')
#         byteData = data.encode('utf-8')
#         return hmac.new(byteKey, byteData, hashlib.sha512).hexdigest()
#
