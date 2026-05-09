import yfinance as yf
import datetime
print(f"Current time: {datetime.datetime.utcnow()}")
data = yf.download("MCHP", period="1d", interval="2m", progress=False)
print("1d 2m:")
print(data.tail())
data2 = yf.download("MCHP", period="5d", interval="2m", progress=False)
print("5d 2m:")
print(data2.tail())
