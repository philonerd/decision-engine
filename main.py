from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.responses import HTMLResponse
import sqlite3
from model import simple_model
from db import init_db

app = FastAPI()

# Initialize DB
init_db()

# -----------------------------
# MODELS
# -----------------------------

class UserInput(BaseModel):
    user_id: int
    features: list[float]

class LoginInput(BaseModel):
    username: str
    password: str

# -----------------------------
# HOME
# -----------------------------

@app.get("/")
def home():
    return {"message": "AI Decision Engine Running"}

# -----------------------------
# LOGIN PAGE
# -----------------------------

@app.get("/login", response_class=HTMLResponse)
def login_page():
    return """
    <html>
    <body style="text-align:center; margin-top:100px; font-family:Arial; background:#0f172a; color:white;">

        <h2>Login</h2>

        <input id="user" placeholder="Username" style="padding:10px;"><br><br>
        <input id="pass" type="password" placeholder="Password" style="padding:10px;"><br><br>

        <button onclick="login()" style="padding:10px 20px; background:#22c55e; border:none;">Login</button>

        <script>
        async function login(){

            const u = document.getElementById("user").value;
            const p = document.getElementById("pass").value;

            const res = await fetch("/login", {
                method:"POST",
                headers:{"Content-Type":"application/json"},
                body: JSON.stringify({username:u, password:p})
            });

            const data = await res.json();

            if(data.success){
                localStorage.setItem("auth", "true");
                window.location = "/app";
            } else {
                alert("Invalid login");
            }
        }
        </script>

    </body>
    </html>
    """

# -----------------------------
# LOGIN API
# -----------------------------

@app.post("/login")
def login(data: LoginInput):

    conn = sqlite3.connect("data.db")
    c = conn.cursor()

    c.execute(
        "SELECT * FROM admin WHERE username=? AND password=?",
        (data.username, data.password)
    )

    user = c.fetchone()
    conn.close()

    return {"success": bool(user)}

# -----------------------------
# MAIN APP UI
# -----------------------------

@app.get("/app", response_class=HTMLResponse)
def app_ui():
    return """
    <html>
    <head>
        <title>AI Decision Engine</title>
    </head>

    <body style="font-family:Arial; background:#0f172a; color:white; text-align:center; padding:40px;">

        <script>
            if(localStorage.getItem("auth") !== "true"){
                window.location = "/login";
            }
        </script>

        <h1>AI Decision Engine</h1>

        <p>Enter user features:</p>

        <input id="f1" placeholder="f1"><br><br>
        <input id="f2" placeholder="f2"><br><br>
        <input id="f3" placeholder="f3"><br><br>

        <button onclick="predict()">Predict</button>

        <div id="result" style="margin-top:20px;"></div>

        <br><br>
        <button onclick="logout()">Logout</button>

        <br><br>
        <a href="/dashboard" style="color:#22c55e;">Go to Dashboard</a>

        <script>
            async function predict() {

                const f1 = parseFloat(document.getElementById("f1").value);
                const f2 = parseFloat(document.getElementById("f2").value);
                const f3 = parseFloat(document.getElementById("f3").value);

                if (isNaN(f1) || isNaN(f2) || isNaN(f3)) {
                    document.getElementById("result").innerHTML = "Enter valid numbers";
                    return;
                }

                const response = await fetch('/predict', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        user_id: Math.floor(Math.random()*1000),
                        features: [f1, f2, f3]
                    })
                });

                const data = await response.json();

                document.getElementById("result").innerHTML =
                    "Decision: " + data.recommended_action +
                    "<br>Score: " + data.score;
            }

            function logout(){
                localStorage.removeItem("auth");
                window.location = "/login";
            }
        </script>

    </body>
    </html>
    """

# -----------------------------
# PREDICT API
# -----------------------------

@app.post("/predict")
def predict(data: UserInput):

    conn = sqlite3.connect("data.db")
    c = conn.cursor()

    f = data.features

    c.execute(
        "INSERT INTO users VALUES (?, ?, ?, ?)",
        (data.user_id, f[0], f[1], f[2])
    )

    conn.commit()
    conn.close()

    action, score = simple_model(data.features)

    return {
        "user_id": data.user_id,
        "recommended_action": action,
        "score": score
    }

# -----------------------------
# DASHBOARD
# -----------------------------

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():

    conn = sqlite3.connect("data.db")
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]

    conn.close()

    return f"""
    <html>
    <body style="font-family:Arial; background:#0f172a; color:white; text-align:center; padding:40px;">

        <script>
            if(localStorage.getItem("auth") !== "true"){{
                window.location = "/login";
            }}
        </script>

        <h1>Dashboard</h1>

        <h2>Total Users: {total_users}</h2>

        <br><br>
        <a href="/app" style="color:#22c55e;">Back to App</a>

    </body>
    </html>
    """
