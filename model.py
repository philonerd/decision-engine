def simple_model(features):
    f1, f2, f3 = features

    score = (f1 * 0.4 + f2 * 0.3 + f3 * 0.3) / 100

    if score > 0.7:
        return (
            "Show premium plan",
            score,
            "High engagement detected",
            "High Intent"
        )
    elif score > 0.4:
        return (
            "Send targeted offers",
            score,
            "Moderate engagement",
            "Medium Intent"
        )
    else:
        return (
            "Increase engagement",
            score,
            "Low activity detected",
            "Low Intent"
        )
