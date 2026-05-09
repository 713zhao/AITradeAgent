import yfinance as yf

symbols = ["GFS", "JNJ", "JPM", "MCHP", "MRVL", "MU", "NXPI", "UNH", "XOM"]
for sym in symbols:
    try:
        ticker = yf.Ticker(sym)
        # Try to get the latest close price
        hist = ticker.history(period="1d")
        if not hist.empty:
            print(f"{sym}: {hist['Close'].iloc[-1]:.2f}")
        else:
            print(f"{sym}: No data")
    except Exception as e:
        print(f"{sym}: Error {e}")
