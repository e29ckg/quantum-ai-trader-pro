def choose_strategy(trend: str) -> str:
    """
    เลือกกลยุทธ์ตั้งต้นจากเทรนด์ของตลาด
    
    :param trend: "uptrend", "downtrend", "sideway"
    :return: สัญญาณดิบ "buy", "sell", หรือ "hold"
    """
    if trend == "uptrend":
        return "buy"
    elif trend == "downtrend":
        return "sell"
    else:
        return "hold"