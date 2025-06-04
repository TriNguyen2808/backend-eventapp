import hashlib, hmac, json, requests, uuid
from django.conf import settings


def create_momo_payment(amount, order_id, redirect_url, ipn_url):
    endpoint = "https://test-payment.momo.vn/v2/gateway/api/create"
    partner_code = settings.MOMO_PARTNER_CODE
    access_key = settings.MOMO_ACCESS_KEY
    secret_key = settings.MOMO_SECRET_KEY

    request_id = str(uuid.uuid4())
    order_info = "Thanh toán vé sự kiện"
    order_type = "momo_wallet"

    raw_signature = f"accessKey={access_key}&amount={amount}&extraData=&ipnUrl={ipn_url}&orderId={order_id}&orderInfo={order_info}&partnerCode={partner_code}&redirectUrl={redirect_url}&requestId={request_id}&requestType=captureWallet"

    signature = hmac.new(secret_key.encode(), raw_signature.encode(), hashlib.sha256).hexdigest()

    payload = {
        "partnerCode": partner_code,
        "accessKey": access_key,
        "requestId": request_id,
        "amount": str(amount),
        "orderId": order_id,
        "orderInfo": order_info,
        "redirectUrl": redirect_url,
        "ipnUrl": ipn_url,
        "lang": "vi",
        "extraData": "",
        "requestType": "captureWallet",
        "signature": signature
    }

    response = requests.post(endpoint, json=payload)
    return response.json()