import argparse
import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from goldguard.market.binance import BinancePublicClient
from goldguard.market.dataset_service import DatasetProgress, DatasetService
from goldguard.market.history import DatasetStatus


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap verified Binance market history")
    parser.add_argument("--symbol", default="PAXGUSDT")
    parser.add_argument("--start", type=_parse_datetime)
    parser.add_argument("--end", type=_parse_datetime)
    parser.add_argument("--storage-dir", type=Path, default=Path("data"))
    parser.add_argument("--warmup-days", type=int, default=30)
    parser.add_argument("--timeframes", default="15m,1h")
    return parser.parse_args(argv)


def _show_progress(progress: DatasetProgress) -> None:
    timeframe = progress.timeframe or "all"
    suffix = f" error={progress.error}" if progress.error else ""
    print(
        f"[progress] {progress.status.value} {timeframe}: "
        f"{progress.downloaded_candles}/{progress.expected_candles} "
        f"({progress.percent}%){suffix}",
        flush=True,
    )


async def main(argv: list[str] | None = None) -> int:
    args = _arguments(argv)
    symbol = str(args.symbol).upper()
    end_date = args.end or datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    start_date = args.start or end_date - timedelta(days=3 * 365)
    warmup_days = int(args.warmup_days)
    storage_dir = Path(args.storage_dir)
    timeframes = tuple(item.strip() for item in str(args.timeframes).split(",") if item.strip())

    print(f"[*] Starting 3-year historical bootstrap for {symbol}")
    print(
        f"[*] Target range: {start_date.isoformat()} to {end_date.isoformat()} "
        f"(+{warmup_days}d warmup)"
    )

    async with httpx.AsyncClient(timeout=30.0) as http_client:
        client = BinancePublicClient(http_client=http_client)
        service = DatasetService(
            client=client,
            storage_dir=storage_dir,
            timeframes=timeframes,
            warmup_days=warmup_days,
            progress_callback=_show_progress,
        )
        manifest = await service.bootstrap(symbol, start_date, end_date)

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
    code = asyncio.run(main(sys.argv[1:]))
    sys.exit(code)
