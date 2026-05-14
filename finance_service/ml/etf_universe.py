"""ETF Universe — curated watchlist of 200+ ETFs organized by category."""
from typing import Dict, List

ETF_UNIVERSE: Dict[str, List[str]] = {
    "broad_market": ["SPY", "IVV", "VOO", "QQQ", "IWM", "DIA", "VTI", "ITOT"],
    "technology": ["XLK", "VGT", "SOXX", "SMH", "HACK", "IGV", "FDN", "CIBR", "QTUM"],
    "healthcare": ["XLV", "VHT", "IBB", "XBI", "IHI", "ARKG", "GNOM"],
    "financials": ["XLF", "VFH", "KRE", "KBE", "IAI", "KBWB"],
    "energy": ["XLE", "VDE", "OIH", "AMLP", "XOP", "FENY", "IEO"],
    "consumer_discretionary": ["XLY", "VCR", "IBUY", "FDIS", "RTH"],
    "consumer_staples": ["XLP", "VDC", "FSTA", "IYK"],
    "utilities": ["XLU", "VPU", "IDU", "FUTY"],
    "real_estate": ["VNQ", "IYR", "XLRE", "REM", "MORT"],
    "materials": ["XLB", "VAW", "GDX", "GDXJ", "SLV", "GLD", "PDBC"],
    "industrials": ["XLI", "VIS", "ITA", "JETS", "WOOD"],
    "communication": ["XLC", "VOX", "FCOM"],
    "international_developed": ["EFA", "VEA", "IEFA", "EWJ", "EWG", "EWU", "EWC", "EWA"],
    "international_emerging": ["EEM", "VWO", "IEMG", "EWZ", "EWY", "KWEB", "CNYA", "INDA"],
    "fixed_income_long": ["TLT", "EDV", "ZROZ", "VGLT", "BLV"],
    "fixed_income_intermediate": ["IEF", "BIV", "GOVT", "VGIT", "SCHR"],
    "fixed_income_short": ["SHY", "BSV", "SCHO", "VGSH", "BIL"],
    "fixed_income_corporate": ["LQD", "VCIT", "IGIB", "VCSH", "HYG", "JNK", "FALN"],
    "fixed_income_tips": ["TIP", "VTIP", "STIP", "SCHP"],
    "alternatives": ["IAU", "SLV", "USO", "UNG", "DJP", "PDBC", "COMT"],
    "volatility": ["VXX", "UVXY", "SVXY", "VIXY"],
    "leverage_bull": ["SSO", "UPRO", "QLD", "TQQQ", "SPXL", "TECL"],
    "leverage_bear": ["SH", "SDS", "SPXU", "PSQ", "SQQQ", "SOXS", "LABD"],
}

ETF_METADATA: Dict[str, Dict] = {
    "SPY":  {"name": "SPDR S&P 500 ETF",          "sector": "Broad Market",       "asset_class": "Equity",       "benchmark": "S&P 500"},
    "IVV":  {"name": "iShares Core S&P 500",       "sector": "Broad Market",       "asset_class": "Equity",       "benchmark": "S&P 500"},
    "VOO":  {"name": "Vanguard S&P 500 ETF",        "sector": "Broad Market",       "asset_class": "Equity",       "benchmark": "S&P 500"},
    "QQQ":  {"name": "Invesco QQQ Trust",           "sector": "Technology",         "asset_class": "Equity",       "benchmark": "NASDAQ-100"},
    "IWM":  {"name": "iShares Russell 2000 ETF",    "sector": "Broad Market",       "asset_class": "Equity",       "benchmark": "Russell 2000"},
    "DIA":  {"name": "SPDR Dow Jones ETF",          "sector": "Broad Market",       "asset_class": "Equity",       "benchmark": "Dow Jones"},
    "VTI":  {"name": "Vanguard Total Market ETF",   "sector": "Broad Market",       "asset_class": "Equity",       "benchmark": "CRSP US Total Market"},
    "XLK":  {"name": "Technology Select Sector",    "sector": "Technology",         "asset_class": "Equity",       "benchmark": "S&P 500 Technology"},
    "VGT":  {"name": "Vanguard IT ETF",             "sector": "Technology",         "asset_class": "Equity",       "benchmark": "MSCI US IMI IT 25/50"},
    "SOXX": {"name": "iShares Semiconductor ETF",   "sector": "Technology",         "asset_class": "Equity",       "benchmark": "ICE Semiconductor"},
    "SMH":  {"name": "VanEck Semiconductor ETF",    "sector": "Technology",         "asset_class": "Equity",       "benchmark": "MVIS US Semiconductor"},
    "XLV":  {"name": "Health Care Select Sector",   "sector": "Healthcare",         "asset_class": "Equity",       "benchmark": "S&P 500 Health Care"},
    "IBB":  {"name": "iShares Biotech ETF",         "sector": "Healthcare",         "asset_class": "Equity",       "benchmark": "Nasdaq Biotech Index"},
    "XBI":  {"name": "SPDR S&P Biotech ETF",        "sector": "Healthcare",         "asset_class": "Equity",       "benchmark": "S&P Biotech Select Industry"},
    "ARKG": {"name": "ARK Genomic Revolution ETF",  "sector": "Healthcare",         "asset_class": "Equity",       "benchmark": "ARK Genomic Revolution"},
    "XLF":  {"name": "Financial Select Sector",     "sector": "Financials",         "asset_class": "Equity",       "benchmark": "S&P 500 Financials"},
    "KRE":  {"name": "SPDR S&P Regional Banking",   "sector": "Financials",         "asset_class": "Equity",       "benchmark": "S&P Regional Banks"},
    "XLE":  {"name": "Energy Select Sector",        "sector": "Energy",             "asset_class": "Equity",       "benchmark": "S&P 500 Energy"},
    "OIH":  {"name": "VanEck Oil Services ETF",     "sector": "Energy",             "asset_class": "Equity",       "benchmark": "MVIS US Oil Services"},
    "XLY":  {"name": "Consumer Discret. Sector",    "sector": "Consumer Cyclical",  "asset_class": "Equity",       "benchmark": "S&P 500 Consumer Discret."},
    "XLP":  {"name": "Consumer Staples Sector",     "sector": "Consumer Defensive", "asset_class": "Equity",       "benchmark": "S&P 500 Consumer Staples"},
    "XLU":  {"name": "Utilities Select Sector",     "sector": "Utilities",          "asset_class": "Equity",       "benchmark": "S&P 500 Utilities"},
    "VNQ":  {"name": "Vanguard Real Estate ETF",    "sector": "Real Estate",        "asset_class": "Real Estate",  "benchmark": "MSCI US IMI Real Estate 25/50"},
    "XLB":  {"name": "Materials Select Sector",     "sector": "Materials",          "asset_class": "Equity",       "benchmark": "S&P 500 Materials"},
    "GLD":  {"name": "SPDR Gold Shares",            "sector": "Commodities",        "asset_class": "Commodity",    "benchmark": "Gold spot price"},
    "IAU":  {"name": "iShares Gold Trust",          "sector": "Commodities",        "asset_class": "Commodity",    "benchmark": "Gold spot price"},
    "SLV":  {"name": "iShares Silver Trust",        "sector": "Commodities",        "asset_class": "Commodity",    "benchmark": "Silver spot price"},
    "TLT":  {"name": "iShares 20+ Year Treasury",   "sector": "Bonds",              "asset_class": "Fixed Income", "benchmark": "ICE US Treasury 20+ Year"},
    "IEF":  {"name": "iShares 7-10 Year Treasury",  "sector": "Bonds",              "asset_class": "Fixed Income", "benchmark": "ICE US Treasury 7-10 Year"},
    "SHY":  {"name": "iShares 1-3 Year Treasury",   "sector": "Bonds",              "asset_class": "Fixed Income", "benchmark": "ICE US Treasury 1-3 Year"},
    "LQD":  {"name": "iShares iBoxx IG Corp Bond",  "sector": "Bonds",              "asset_class": "Fixed Income", "benchmark": "Markit iBoxx USD IG Corp"},
    "HYG":  {"name": "iShares iBoxx HY Corp Bond",  "sector": "Bonds",              "asset_class": "Fixed Income", "benchmark": "Markit iBoxx USD HY Corp"},
    "BND":  {"name": "Vanguard Total Bond Market",   "sector": "Bonds",              "asset_class": "Fixed Income", "benchmark": "Bloomberg US Aggregate Bond"},
    "TIP":  {"name": "iShares TIPS Bond ETF",       "sector": "Bonds",              "asset_class": "Fixed Income", "benchmark": "Bloomberg US TIPS"},
    "EFA":  {"name": "iShares MSCI EAFE",           "sector": "International",      "asset_class": "Equity",       "benchmark": "MSCI EAFE"},
    "EEM":  {"name": "iShares MSCI Emerging Mkts",  "sector": "International",      "asset_class": "Equity",       "benchmark": "MSCI Emerging Markets"},
    "VEA":  {"name": "Vanguard FTSE Developed",     "sector": "International",      "asset_class": "Equity",       "benchmark": "FTSE Developed All Cap ex US"},
    "VWO":  {"name": "Vanguard FTSE Emerging",      "sector": "International",      "asset_class": "Equity",       "benchmark": "FTSE Emerging Markets"},
    "KWEB": {"name": "KraneShares CSI China Internet","sector": "International",    "asset_class": "Equity",       "benchmark": "CSI Overseas China Internet"},
    "VXX":  {"name": "iPath VIX ST Futures ETN",    "sector": "Volatility",         "asset_class": "Alternatives", "benchmark": "S&P 500 VIX ST Futures"},
    "UVXY": {"name": "ProShares Ultra VIX ST",      "sector": "Volatility",         "asset_class": "Alternatives", "benchmark": "S&P 500 VIX ST Futures (1.5x)"},
    "SH":   {"name": "ProShares Short S&P500",      "sector": "Inverse",            "asset_class": "Alternatives", "benchmark": "S&P 500 (inverse)"},
    "SDS":  {"name": "ProShares UltraShort S&P500", "sector": "Inverse",            "asset_class": "Alternatives", "benchmark": "S&P 500 (-2x)"},
    "PSQ":  {"name": "ProShares Short QQQ",         "sector": "Inverse",            "asset_class": "Alternatives", "benchmark": "NASDAQ-100 (inverse)"},
    "SQQQ": {"name": "ProShares UltraShort QQQ",    "sector": "Inverse",            "asset_class": "Alternatives", "benchmark": "NASDAQ-100 (-3x)"},
    "TQQQ": {"name": "ProShares UltraPro QQQ",      "sector": "Technology",         "asset_class": "Equity",       "benchmark": "NASDAQ-100 (3x)"},
    "SSO":  {"name": "ProShares Ultra S&P500",      "sector": "Broad Market",       "asset_class": "Equity",       "benchmark": "S&P 500 (2x)"},
    "UPRO": {"name": "ProShares UltraPro S&P500",   "sector": "Broad Market",       "asset_class": "Equity",       "benchmark": "S&P 500 (3x)"},
    "XLC":  {"name": "Communication Services Sel.", "sector": "Communication",      "asset_class": "Equity",       "benchmark": "S&P 500 Communication Services"},
    "XLI":  {"name": "Industrial Select Sector",    "sector": "Industrials",        "asset_class": "Equity",       "benchmark": "S&P 500 Industrials"},
    "ITA":  {"name": "iShares US Aerospace & Def.", "sector": "Industrials",        "asset_class": "Equity",       "benchmark": "Dow Jones US Aerospace & Defense"},
    "JETS": {"name": "US Global Jets ETF",          "sector": "Industrials",        "asset_class": "Equity",       "benchmark": "US Global Jets Index"},
    "GDX":  {"name": "VanEck Gold Miners ETF",      "sector": "Materials",          "asset_class": "Equity",       "benchmark": "NYSE Arca Gold Miners"},
}

HEDGE_ETF_SYMBOLS: List[str] = ["TLT", "IEF", "SHY", "GLD", "SH", "SDS", "SQQQ", "PSQ", "VXX"]

CORRELATION_SCAN_SYMBOLS: List[str] = [
    "TLT", "IEF", "BND", "LQD", "HYG", "TIP",
    "GLD", "SLV", "USO",
    "VNQ",
    "EFA", "EEM", "VEA", "VWO",
    "VXX",
    "XLU", "XLP",
    "XLK", "XLV", "XLF", "XLE", "XLY", "XLI",
]

_SECTOR_CATEGORIES = [
    "broad_market", "technology", "healthcare", "financials", "energy",
    "consumer_discretionary", "consumer_staples", "utilities", "real_estate",
    "materials", "industrials", "communication",
]


def get_all_etf_symbols() -> List[str]:
    seen: set = set()
    result: List[str] = []
    for syms in ETF_UNIVERSE.values():
        for s in syms:
            if s not in seen:
                seen.add(s)
                result.append(s)
    return result


def get_etf_by_category(category: str) -> List[str]:
    return ETF_UNIVERSE.get(category, [])


def get_etf_metadata(symbol: str) -> Dict:
    return ETF_METADATA.get(symbol, {
        "name": symbol, "sector": "Unknown", "asset_class": "Equity", "benchmark": "Unknown",
    })


def get_sector_etfs() -> Dict[str, List[str]]:
    return {cat: ETF_UNIVERSE[cat] for cat in _SECTOR_CATEGORIES if cat in ETF_UNIVERSE}
