from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from fastapi.responses import HTMLResponse, RedirectResponse
import sqlite3
import uuid
import requests
import yagmail
from model import simple_model

app = FastAPI()

# -----------------------------
# CONFIG
# -----------------------------
EMAIL_USER = "your_email@gmail.com"
EMAIL_PASS = "your_app_password"
SLACK_WEBHOOK_URL = ""  # optional

# -----------------------------
# MODELS
# -----------------------------
class UserInput(BaseModel):
    client_id: str
    user_id: int
    time_spent: float
    sessions: int
    actions: int

class RegisterInput(BaseModel):
    username: str
    password: str

class LoginInput(BaseModel):
    username: str
    password: str

# -----------------------------
# HELPERS
# -----------------------------
def send_email(to, subject, content):
    try:
        if EMAIL_USER and EMAIL_PASS:
            yag = yagmail.SMTP(EMAIL_USER, EMAIL_PASS)
            yag.send(to, subject, content)
    except Exception as e:
        print("Email error:", e)

def send_slack(message):
    try:
        if SLACK_WEBHOOK_URL:
            requests.post(SLACK_WEBHOOK_URL, json={"text": message})
    except Exception as e:
        print("Slack error:", e)

def send_webhook(client_id, payload):
    conn = sqlite3.connect("data.db")
    c = conn.cursor()
    c.execute("SELECT webhook_url FROM clients WHERE client_id=?", (client_id,))
    row = c.fetchone()
    conn.close()

    if row and row[0]:
        try:
            requests.post(row[0], json=payload, timeout=3)
        except Exception as e:
            print("Webhook error:", e)

def validate_api_key(api_key):
    conn = sqlite3.connect("data.db")
    c = conn.cursor()
    c.execute("SELECT client_id, api_calls, plan FROM clients WHERE api_key=?", (api_key,))
    result = c.fetchone()
    conn.close()

    if not result:
        raise HTTPException(status_code=403, detail="Invalid API Key")

    return result

def trigger_action(client_id, user_id, segment):
    if segment == "High Intent":
        action = "Send premium offer"
    elif segment == "Medium Intent":
        action = "Send targeted offer"
    else:
        action = "Re-engage user"

    conn = sqlite3.connect("data.db")
    c = conn.cursor()
    c.execute(
        "INSERT INTO actions_log (client_id, user_id, action) VALUES (?, ?, ?)",
        (client_id, user_id, action)
    )
    conn.commit()
    conn.close()

    send_email(EMAIL_USER, "User Action", f"{action} for user {user_id}")
    send_slack(
        f"""
    AI Alert

    User: {user_id}
    Segment: {segment}
    Action: {action}

    Triggered automatically.
    """

    )
    return action

# -----------------------------
# AUTH
# -----------------------------
@app.post("/register")
def register(data: RegisterInput):
    client_id = str(uuid.uuid4())
    api_key = str(uuid.uuid4())

    conn = sqlite3.connect("data.db")
    c = conn.cursor()
    c.execute(
        "INSERT INTO clients VALUES (?, ?, ?, ?, 0, 'free', NULL)",
        (client_id, data.username, data.password, api_key)
    )
    conn.commit()
    conn.close()

    return {"client_id": client_id, "api_key": api_key}

@app.post("/login")
def login(data: LoginInput):
    conn = sqlite3.connect("data.db")
    c = conn.cursor()
    c.execute(
        "SELECT client_id, api_key FROM clients WHERE username=? AND password=?",
        (data.username, data.password)
    )
    user = c.fetchone()
    conn.close()

    if not user:
        return {"success": False}

    return {"success": True, "client_id": user[0], "api_key": user[1]}


# -----------------------------
# SET WEBHOOK
# -----------------------------
@app.post("/set-webhook")
def set_webhook(api_key: str, webhook_url: str):
    conn = sqlite3.connect("data.db")
    c = conn.cursor()
    c.execute(
        "UPDATE clients SET webhook_url=? WHERE api_key=?",
        (webhook_url, api_key)
    )
    conn.commit()
    conn.close()
    return {"message": "Webhook set"}

# -----------------------------
# API PREDICT
# -----------------------------
@app.post("/api/predict")
def api_predict(data: UserInput, x_api_key: str = Header(...)):

    client_id, api_calls, plan = validate_api_key(x_api_key)

    if client_id != data.client_id:
        raise HTTPException(status_code=403, detail="Client mismatch")

    if plan == "free" and api_calls >= 100:
        raise HTTPException(status_code=403, detail="Free limit exceeded")

    conn = sqlite3.connect("data.db")
    c = conn.cursor()

    c.execute(
        "UPDATE clients SET api_calls = api_calls + 1 WHERE api_key=?",
        (x_api_key,)
    )

    f1 = data.time_spent
    f2 = data.sessions
    f3 = data.actions

    upgraded = 1 if f1 > 50 else 0

    c.execute(
        "INSERT INTO users VALUES (?, ?, ?, ?, ?, ?)",
        (client_id, data.user_id, f1, f2, f3, upgraded)
    )

    conn.commit()
    conn.close()

    action, score, reason, segment = simple_model([f1, f2, f3])

    conn = sqlite3.connect("data.db")
    c = conn.cursor()
    c.execute(
        "INSERT INTO user_history (client_id, user_id, time_spent, sessions, actions, prediction, segment) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (client_id, data.user_id, f1, f2, f3, score, segment)
    )
    conn.commit()
    conn.close()

    auto_action = trigger_action(client_id, data.user_id, segment)


    send_webhook(client_id, {
        "event": "user_prediction",
        "client_id": client_id,
        "user_id": data.user_id,
        "metrics": {
            "time_spent": f1,
            "sessions": f2,
            "actions": f3
        },
        "prediction": {
            "score": score,
            "segment": segment,
            "recommended_action": action,
            "auto_action": auto_action
        },
        "timestamp": "now"
    })
    return {
        "recommended_action": action,
        "score": score,
        "reason": reason,
        "segment": segment,
        "auto_action": auto_action
    }

# -----------------------------
# SIMPLE UI
# -----------------------------
@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <html>
    <body style="font-family:Arial; text-align:center; margin-top:100px;">
        <h2>AI Conversion Intelligence Platform</h2>
        <a href='/app'>Open App</a>
    </body>
    </html>
    """

@app.get("/app", response_class=HTMLResponse)
def app_ui():
    return """
    <html>
    <body style="background:#0f172a;color:white;text-align:center;padding:40px;">
        <h1>AI Predictor</h1>
        <input id="time" placeholder="time"><br><br>
        <input id="sessions" placeholder="sessions"><br><br>
        <input id="actions" placeholder="actions"><br><br>
        <button onclick="predict()">Predict</button>
        <div id="result"></div>

        <script>
        async function predict(){
            const res = await fetch('/api/predict',{
                method:'POST',
                headers:{
                    'Content-Type':'application/json',
                    'x-api-key':'d7b4be78-e969-43c3-87ac-38a2a64612c1'
                },
                body:JSON.stringify({
                    client_id:'106b33ae-6050-469d-9484-5136329ad72b',
                    user_id:1,
                    time_spent:parseFloat(time.value),
                    sessions:parseInt(sessions.value),
                    actions:parseInt(actions.value)
                })
            });
            const data = await res.json();
            result.innerHTML = JSON.stringify(data);
        }
        </script>
    </body>
    </html>
    """
@app.get("/user-history")
def get_user_history(client_id: str, user_id: int):

    conn = sqlite3.connect("data.db")
    c = conn.cursor()

    c.execute(
        "SELECT time_spent, sessions, actions, prediction, segment, timestamp FROM user_history WHERE client_id=? AND user_id=? ORDER BY timestamp DESC",
        (client_id, user_id)
    )

    rows = c.fetchall()
    conn.close()

    return {
        "history": [
            {
                "time_spent": r[0],
                "sessions": r[1],
                "actions": r[2],
                "prediction": r[3],
                "segment": r[4],
                "timestamp": r[5]
            }
            for r in rows
        ]
    }


@app.get("/actions")
def get_actions(client_id: str):

    conn = sqlite3.connect("data.db")
    c = conn.cursor()

    c.execute(
        "SELECT user_id, action, timestamp FROM actions_log WHERE client_id=? ORDER BY timestamp DESC",
        (client_id,)
    )

    rows = c.fetchall()
    conn.close()

    return {
        "actions": [
            {
                "user_id": r[0],
                "action": r[1],
                "timestamp": r[2]
            }
            for r in rows
        ]
    }
