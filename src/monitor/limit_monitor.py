import logging
import requests
from datetime import datetime, timezone

from src.database.database import get_db_session, Trade

logger = logging.getLogger(__name__)


def check_limit_order(trader):
    """
    Check for non-active orders and update database with appropriate status and sell information.
    """
    try:
        # Get ALL order history from Jupiter API
        endpoint = f"{trader.base_url}/trigger/v1/getTriggerOrders"
        params = {"user": str(trader.wallet.pubkey()), "orderStatus": "history"}

        response = requests.get(endpoint, params=params, headers=trader.headers)
        response.raise_for_status()

        orders_data = response.json()
        orders = orders_data.get('orders')

        logger.info(f"Retrieved {len(orders)} total orders from API")

        # Filter for non-active orders and extract relevant info
        non_active_orders = {}
        for order in orders:
            status = order.get('status').lower()
            if status != 'open':  # Get all non-active orders
                open_tx = order.get('openTx')
                close_tx = order.get('closeTx')
                updated_at = order.get('updatedAt')

                if open_tx:
                    non_active_orders[open_tx] = {
                        'status': status,
                        'closeTx': close_tx,
                        'updatedAt': updated_at,
                        'order': order
                    }

        logger.info(f"Found {len(non_active_orders)} non-active orders")

        # Update database
        with get_db_session() as db:
            # Get all trades that might need status updates (not failed/closed already)
            trades_to_check = db.query(Trade).filter(
                Trade.status.in_(["open"])  # Only check open trades
            ).all()

            logger.info(f"Found {len(trades_to_check)} open trades to check")

            updates_made = 0
            for trade in trades_to_check:
                # Check if this trade's TP order signature matches any non-active order's openTx
                if trade.tp_order_sig and trade.tp_order_sig in non_active_orders:
                    order_info = non_active_orders[trade.tp_order_sig]
                    order_status = order_info['status']

                    # Map Jupiter order status to our trade status
                    if order_status == 'completed':
                        trade.status = order_status
                        trade.sell_transaction_sig = order_info['closeTx']
                        logger.info(f"Trade {trade.id} completed successfully")
                    else:
                        # Handle any other non-active statuses
                        trade.status = order_status
                        logger.info(f"Trade {trade.id} closed with unknown status: {order_status}")

                    # Parse updatedAt timestamp if available
                    if order_info['updatedAt']:
                        try:
                            if order_status == 'completed':
                                trade.sell_timestamp = datetime.fromisoformat(
                                    order_info['updatedAt'].replace('Z', '+00:00')
                                )
                        except (ValueError, AttributeError):
                            if order_status == 'completed':
                                trade.sell_timestamp = datetime.now(timezone.utc)
                    else:
                        if order_status == 'completed':
                            trade.sell_timestamp = datetime.now(timezone.utc)

                    logger.info(f"Updated trade {trade.id}: status={trade.status}, "
                                f"sell_tx={trade.sell_transaction_sig}")
                    updates_made += 1

            if updates_made > 0:
                logger.info(f"Successfully updated {updates_made} trades")
            else:
                logger.info("No trades needed updates")

    except Exception as e:
        logger.error(f"Error checking orders: {e}")