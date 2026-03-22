import numpy as np

def simple_model(features):
    score = np.mean(features)

    if score > 0.7:
        return "High Value User -> Offer Premium Plan", float(score)
    elif score > 0.4:
        return "Medium Value User -> Offer Standard Plan", float(score)
    else:
        return "Low Value User -> Boost Engagement", float(score)
