import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from goldguard.market.binance import BinancePublicClient
from goldguard.market.history import DatasetStatus, bootstrap_history


async def main() -> int:
    symbol = "PAXGUSDT"
    end_date = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    start_date = end_date - timedelta(days=3 * 365)
    warmup_days = 30
    storage_dir = Path("data")

    print(f"[*] Starting 3-year historical bootstrap for {symbol}")
    print(
        f"[*] Target range: {start_date.isoformat()} to {end_date.isoformat()} "
        f"(+{warmup_days}d warmup)"
    )

    async with httpx.AsyncClient(timeout=30.0) as http_client:
        client = BinancePublicClient(http_client=http_client)
        manifest = await bootstrap_history(
            symbol=symbol,
            start=start_date,
            end=end_date,
            timeframes=("15m", "1h"),
            warmup_days=warmup_days,
            client=client,
            storage_dir=storage_dir,
        )

    print(f"[+] Bootstrap status: {manifest.status}")
    print(f"[+] Checksum: {manifest.checksum}")
    print(f"[+] Counts: {manifest.timeframe_counts}")

    if manifest.status == DatasetStatus.VERIFIED:
        print("[+] Dataset successfully verified.")
        return 0
    else:
        print("[-] Dataset verification failed or corrupt.")
        return 1


if __name__ == "__main__":
    code = asyncio.run(main())
    sys.exit(code)
