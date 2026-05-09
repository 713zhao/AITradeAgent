import asyncio
from finance_service.data.yfinance_provider import YfinanceProvider

async def main():
    provider = YfinanceProvider()
    res = provider.fetch_ohlcv(["GFS", "MCHP"], period="1d", interval="2m")
    df = res["MCHP"]
    print("Columns:", df.columns.tolist() if df is not None else "None")
    print("Head:")
    print(df.head() if df is not None else "None")

asyncio.run(main())
