import asyncio
from finance_service.data.yfinance_provider import YfinanceProvider
import logging

async def main():
    provider = YfinanceProvider()
    res = provider.fetch_ohlcv(["GFS", "MCHP", "0002.HK"], period="1d", interval="2m")
    for sym, df in res.items():
        if df is not None:
            print(f"{sym}: length {len(df)}")
        else:
            print(f"{sym}: None")

asyncio.run(main())
