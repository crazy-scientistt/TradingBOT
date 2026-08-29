from __future__ import annotations

from typing import Any


class FakeBinance:
    """Deterministic Binance HTTP stand-in. Never used against the real network."""

    def __init__(self) -> None:
        self.post_count = 0
        self.get_count = 0
        self.delete_count = 0
        self.timeout_after_accept = False
        self.malformed_status = False
        self.accepted_order_id = "1001"
        self.orders: dict[str, dict[str, Any]] = {}
        self.last_query: dict[str, Any] = {}
        self.server_time = {"serverTime": 1724832000123}
        self.account: dict[str, Any] = {
            "canTrade": True,
            "balances": [{"asset": "USDT", "free": "10000.00", "locked": "0"}],
        }
        self.restrictions: dict[str, Any] = {
            "ipRestrict": True,
            "enableWithdrawals": False,
            "enableInternalTransfer": False,
            "permitsUniversalTransfer": False,
            "enableSpotAndMarginTrading": True,
            "enableFutures": True,
        }
        self.futures_account: dict[str, Any] = {
            "totalWalletBalance": "10000.00",
            "availableBalance": "10000.00",
            "totalUnrealizedProfit": "0",
        }

    async def request(
        self, method: str, path: str, params: dict[str, Any], headers: dict[str, str]
    ) -> Any:
        self.last_query = dict(params)
        if path.endswith("/time") and method == "GET":
            return self.server_time
        if path.endswith("/apiRestrictions") and method == "GET":
            return self.restrictions
        if path.endswith("/fapi/v2/account") and method == "GET":
            return self.futures_account
        if path.endswith("/account") and method == "GET":
            return self.account
        if path.endswith("/positionSide/dual") or path.endswith("/marginType") or path.endswith(
            "/leverage"
        ):
            return {"code": 200, "msg": "success"}
        if path.endswith("/order") and method == "POST":
            self.post_count += 1
            cid = str(params.get("newClientOrderId"))
            qty = str(params.get("quantity"))
            order: dict[str, Any] = {
                "orderId": int(self.accepted_order_id),
                "clientOrderId": cid,
                "status": "FILLED",
                "executedQty": qty,
                "origQty": qty,
                "price": str(params.get("price") or "0"),
                "avgPrice": str(params.get("price") or "2500"),
                "symbol": params.get("symbol"),
                "side": params.get("side"),
                "type": params.get("type"),
            }
            if self.malformed_status:
                order.pop("status")
            self.orders[cid] = order
            if self.timeout_after_accept:
                raise TimeoutError("timeout after accept")
            return order
        if path.endswith("/order") and method == "GET":
            self.get_count += 1
            cid = str(params.get("origClientOrderId"))
            if cid in self.orders:
                return self.orders[cid]
            raise LookupError("order not found")
        if path.endswith("/order") and method == "DELETE":
            self.delete_count += 1
            cid = str(params.get("origClientOrderId"))
            order = dict(self.orders.get(cid) or {})
            order["status"] = "CANCELED"
            order.setdefault("executedQty", "0")
            order.setdefault("orderId", int(self.accepted_order_id))
            return order
        raise ValueError(f"unexpected {method} {path}")
