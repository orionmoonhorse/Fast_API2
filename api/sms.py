# sms.py

import requests

def send_sms(to, text):
    try:
        requests.post(
            "http://127.0.0.1:4000/api/sms/send",
            json={"to": to, "text": text}
        )
    except Exception as e:
        print("SMS bridge error:", e)
