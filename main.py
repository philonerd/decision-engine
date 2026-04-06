from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from fastapi.responses import HTMLResponse, RedirectResponse
import sqlite3
import uuid
import requests
import yagmail
from model import simple_model

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # allow all (for now)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
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

class UpgradeInput(BaseModel):
    api_key: str
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


@app.post("/upgrade")
def upgrade(data: UpgradeInput):

    conn = sqlite3.connect("data.db")
    c = conn.cursor()

    c.execute(
        "UPDATE clients SET plan='pro' WHERE api_key=?",
        (data.api_key,)
    )

    conn.commit()
    conn.close()

    return {"status": "upgraded"}


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
        raise HTTPException(status_code=403, detail="Free limit exceeded ! Upgrade to Pro Plan")

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
    <head>
        <style>
            body {
                background:#0f172a;
                color:white;
                font-family: 'Segoe UI';
                text-align:center;
                padding:40px;
            }

            .card {
                background:#1e293b;
                padding:30px;
                border-radius:15px;
                width:300px;
                margin:auto;
            }

            input {
                width:90%;
                padding:10px;
                margin:10px 0;
                border-radius:8px;
                border:none;
            }

            button {
                width:100%;
                padding:12px;
                background:#22c55e;
                border:none;
                border-radius:8px;
                cursor:pointer;
            }

            .result {
                margin-top:20px;
                background:#020617;
                padding:15px;
                border-radius:10px;
            }
        </style>
    </head>

    <body>

        <h1>AI Predictor</h1>

        <div class="card">
            <input id="time" placeholder="Time Spent">
            <input id="sessions" placeholder="Sessions">
            <input id="actions" placeholder="Actions">

            <button onclick="predict()">Predict</button>

            <div id="result" class="result"></div>
        </div>

        <script>
        async function predict(){
            const res = await fetch('/api/predict',{
                method:'POST',
                headers:{
                    'Content-Type':'application/json',
                    'x-api-key':localStorage.getItem("api_key")
                },
                body:JSON.stringify({
                    client_id: localStorage.getItem("client_id"),
                    user_id:1,
                    time_spent:parseFloat(time.value),
                    sessions:parseInt(sessions.value),
                    actions:parseInt(actions.value)
                })
            });

            const data = await res.json();

            result.innerHTML =
                "<b>Segment:</b> " + data.segment +
                "<br><b>Score:</b> " + data.score +
                "<br><b>Action:</b> " + data.auto_action;
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


@app.get("/", response_class=HTMLResponse)
def landing():
    return """
    <html>
    <head>
        <title>Sentria AI</title>
        <style>
            body {
                margin:0;
                font-family: 'Segoe UI', sans-serif;
                background: linear-gradient(135deg, #0f172a, #020617);
                color:white;
            }

            .container {
                text-align:center;
                padding:120px 20px;
            }

            h1 {
                font-size:52px;
                margin-bottom:10px;
            }

            p {
                color:#94a3b8;
                font-size:18px;
                margin-bottom:30px;
            }

            .btn {
                padding:14px 28px;
                border-radius:10px;
                border:none;
                margin:10px;
                font-size:16px;
                cursor:pointer;
            }

            .primary {
                background:#22c55e;
                color:white;
            }

            .secondary {
                background:#1e293b;
                color:white;
            }
        </style>
    </head>

    <body>
        <div class="container">
            <h1>Sentria AI</h1>
            <p>AI-powered decision & automation engine for user behavior</p>

            <a href="/app"><button class="btn primary">Launch App</button></a>
            <a href="/dashboard"><button class="btn secondary">View Dashboard</button></a>
            <a href="/login"><button class="btn primary">Login</button></a>
            <a href="/pricing"><button class="btn secondary">Pricing</button></a>
            <a href="/app"><button class="btn primary">Try Demo</button></a>
        </div>
    </body>
    </html>
    """

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():

    conn = sqlite3.connect("data.db")
    c = conn.cursor()

    c.execute("SELECT segment, COUNT(*) FROM user_history GROUP BY segment")
    data = c.fetchall()

    conn.close()

    labels = [d[0] for d in data]
    values = [d[1] for d in data]

    return f"""
    <html>
    <head>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            body {{
                background:#0f172a;
                color:white;
                font-family: 'Segoe UI';
                padding:40px;
            }}

            .grid {{
                display:flex;
                justify-content:space-around;
                margin-bottom:30px;
            }}

            .card {{
                background:#1e293b;
                padding:20px;
                border-radius:10px;
                width:150px;
                text-align:center;
            }}
        </style>
    </head>

    <body>

        <h1>Dashboard</h1>

        <div class="grid">
            <div class="card">High Intent<br>{values[0] if len(values)>0 else 0}</div>
            <div class="card">Medium Intent<br>{values[1] if len(values)>1 else 0}</div>
            <div class="card">Low Intent<br>{values[2] if len(values)>2 else 0}</div>
        </div>

        <canvas id="chart"></canvas>

        <script>
        new Chart(document.getElementById("chart"), {{
            type: 'bar',
            data: {{
                labels: {labels},
                datasets: [{{
                    label: 'Users',
                    data: {values},
                    backgroundColor: ['#22c55e','#eab308','#ef4444']
                }}]
            }}
        }});
        </script>

    </body>
    </html>
    """


@app.get("/login", response_class=HTMLResponse)
def login_page():
    return """
    <html>
    <body style="background:#0f172a;color:white;text-align:center;padding:100px;">
        <h2>Login</h2>

        <input id="username" placeholder="Username"><br><br>
        <input id="password" type="password" placeholder="Password"><br><br>

        <button onclick="login()">Login</button>

        <script>
        async function login(){
            const res = await fetch('/login',{
                method:'POST',
                headers:{'Content-Type':'application/json'},
                body:JSON.stringify({
                    username:username.value,
                    password:password.value
                })
            });

            const data = await res.json();

            if(data.success){
                localStorage.setItem("api_key", data.api_key);
                localStorage.setItem("client_id", data.client_id);
                window.location = "/app";
            } else {
                alert("Login failed");
            }
        }
        </script>
    </body>
    </html>
    """



@app.get("/pricing", response_class=HTMLResponse)
def pricing():
    return """
    <html>
    <body style="background:#0f172a;color:white;text-align:center;padding:50px;">

        <h1>Pricing</h1>

        <div style="display:flex;justify-content:center;gap:30px;">

            <div style="background:#1e293b;padding:20px;border-radius:10px;">
                <h2>Free</h2>
                <p>100 API calls</p>
                <p>Basic analytics</p>
            </div>

            <div style="background:#22c55e;padding:20px;border-radius:10px;color:black;">
                <h2>Pro</h2>
                <p>Unlimited API calls</p>
                <p>Automation + Webhooks</p>
                <p>Priority support</p>
                <button onclick="upgrade()">Upgrade</button>
            </div>

        </div>

        <script>
        async function upgrade(){

            const api_key = localStorage.getItem("api_key");

            await fetch('/upgrade',{
                method:'POST',
                headers:{'Content-Type':'application/json'},
                body:JSON.stringify({api_key:api_key})
            });

            alert("Upgraded to Pro!");
        }
        </script>

    </body>
    </html>
    """
