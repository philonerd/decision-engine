import requests

API_URL = "http://127.0.0.1:8000/api/predict"

headers = {
    "x-api-key": "YOUR_API_KEY"
}

data = {
    "client_id": "YOUR_CLIENT_ID",
    "user_id": 101,
    "time_spent": 75,
    "sessions": 9,
    "actions": 20
}

res = requests.post(API_URL, json=data, headers=headers)

print(res.json())
