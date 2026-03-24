import sqlite3
import numpy as np
from sklearn.linear_model import LogisticRegression

model = None

def train_model():
    global model

    conn = sqlite3.connect("data.db")
    c = conn.cursor()

    c.execute("SELECT time_spent, sessions, actions, upgraded FROM users")
    rows = c.fetchall()
    conn.close()

    if len(rows) < 10:
        return None

    X = []
    y = []

    for r in rows:
        X.append([r[0], r[1], r[2]])
        y.append(r[3])

    model = LogisticRegression()
    model.fit(X, y)

def simple_model(features):
    global model

    if model is None:
        train_model()

    if model is None:
        score = np.mean(features)

        if score > 50:
            return (
                "Likely to upgrade",
                float(score),
                "High activity detected",
                "High Intent"
            )
        else:
            return (
                "Unlikely to upgrade",
                float(score),
                "Low activity detected",
                "Low Intent"
            )

    prob = model.predict_proba([features])[0][1]

    if prob > 0.7:
        action = "Show premium plan"
        reason = "High engagement (time + sessions high)"
        segment = "High Intent"
    elif prob > 0.4:
        action = "Send targeted offers"
        reason = "Moderate engagement detected"
        segment = "Medium Intent"
    else:
        action = "Increase engagement"
        reason = "Low activity detected"
        segment = "Low Intent"

    return action, float(prob), reason, segment
