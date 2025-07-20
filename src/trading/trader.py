import os
import logging
import requests
import base58
import base64
import time
from typing import Dict, Any, Optional, Tuple, Union

from dotenv import load_dotenv
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction

logger = logging.getLogger(__name__)

class JupiterTrader:
    """Jupiter Trading API client for Solana memecoin trading.

    This class provides a clean interface to Jupiter API for:
    - Market swaps via Ultra API
    - Limit orders via Trigger API (to be implemented)
    """


    def __init__(self):
        """Initialize Jupiter trader using environment variables."""

        # Read configuration
        private_key = os.getenv("PRIVATE_KEY")
        if not private_key:
            raise ValueError("PRIVATE_KEY must be set in your .env file")

        # API configuration
        self.api_key = os.getenv("JUPITER_API_KEY")
        self.base_url = "https://api.jup.ag" if self.api_key else "https://lite-api.jup.ag"
        self.headers = {"x-api-key": self.api_key} if self.api_key else {}

        # Trade configuration
        self.slippage = os.getenv("SLIPPAGE", 300)

        # Setup wallet
        try:
            private_key_bytes = base58.b58decode(private_key)
            self.wallet = Keypair.from_bytes(private_key_bytes)
            logger.info(f"Wallet initialized: {self.wallet.pubkey()}")
        except Exception as e:
            logger.error(f"Failed to initialize wallet: {e}")
            raise

    def get_quote(self, input_mint: str, output_mint: str, amount: int) -> Optional[Dict[str, Any]]:
        """Get a swap quote from Jupiter.

        Args:
            input_mint: Input token mint address
            output_mint: Output token mint address
            amount: Amount in smallest units (lamports for SOL)

        Returns:
            Quote data or None if failed
        """
        logger.info(f"Getting quote: {amount} {input_mint} -> {output_mint}")

        endpoint = f"{self.base_url}/ultra/v1/order"
        params = {
            "inputMint": input_mint,
            "outputMint": output_mint,
            "amount": amount,
            "taker": str(self.wallet.pubkey()),
            "slippageBps": self.slippage,
            "onlyDirectRoutes": False
        }

        try:
            response = requests.get(endpoint, params=params, headers=self.headers)
            response.raise_for_status()
            quote = response.json()

            if 'outAmount' in quote:
                logger.info(f"Quote received: {quote['outAmount']} output tokens")
                return quote
            else:
                logger.warning("Quote missing outAmount")
                return None

        except Exception as e:
            logger.error(f"Error getting quote: {e}")
            return None

    def sign_transaction(self, quote_data: Dict[str, Any]) -> Optional[str]:
        """Sign a transaction from Jupiter API.

        Args:
            quote_data: Quote data containing transaction

        Returns:
            Base64 encoded signed transaction or None if failed
        """
        try:
            # Extract transaction
            swap_transaction_base64 = quote_data.get("transaction")
            if not swap_transaction_base64:
                logger.error("No transaction found in quote data")
                return None

            # Decode and parse transaction
            swap_transaction_bytes = base64.b64decode(swap_transaction_base64)
            raw_transaction = VersionedTransaction.from_bytes(swap_transaction_bytes)

            # Find wallet index and sign
            account_keys = raw_transaction.message.account_keys
            wallet_pubkey = self.wallet.pubkey()

            try:
                wallet_index = account_keys.index(wallet_pubkey)
            except ValueError:
                logger.error(f"Wallet {wallet_pubkey} not found in transaction accounts")
                return None

            # Create signatures
            signers = list(raw_transaction.signatures)
            signers[wallet_index] = self.wallet

            # Create signed transaction
            signed_transaction = VersionedTransaction(raw_transaction.message, signers)
            serialized_signed_transaction = base64.b64encode(bytes(signed_transaction)).decode("utf-8")

            logger.info("Transaction signed successfully")
            return serialized_signed_transaction

        except Exception as e:
            logger.error(f"Error signing transaction: {e}")
            return None

    def execute_swap(self, signed_tx: str, request_id: str) -> Optional[Dict[str, Any]]:
        """Execute a signed swap transaction.

        Args:
            signed_tx: Base64 encoded signed transaction
            request_id: Request ID from quote

        Returns:
            Execution result or None if failed
        """
        logger.info("Executing swap transaction...")

        endpoint = f"{self.base_url}/ultra/v1/execute"
        execute_request = {
            "signedTransaction": signed_tx,
            "requestId": request_id
        }

        try:
            response = requests.post(endpoint, json=execute_request, headers=self.headers)
            response.raise_for_status()
            result = response.json()

            # Process result
            signature = result.get("signature")
            status = result.get("status")

            if status == "Success":
                logger.info(f"Swap successful! Signature: {signature}")
                print(f"\nView on Solscan: https://solscan.io/tx/{signature}")
            else:
                error_code = result.get("code", "Unknown")
                error_message = result.get("error", "Unknown error")
                logger.error(f"Swap failed: {error_message} (Code: {error_code})")

                if signature:
                    print(f"\nFailed transaction: https://solscan.io/tx/{signature}")

            return result

        except Exception as e:
            logger.error(f"Error executing swap: {e}")
            return None

    def market_swap(self, input_mint: str, output_mint: str,
                   amount: int) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """Perform a complete market swap.

        Args:
            input_mint: Input token mint address
            output_mint: Output token mint address
            amount: Amount in smallest units (lamports for SOL)

        Returns:
            (success, signature, result)
        """
        # Step 1: Get quote
        quote = self.get_quote(input_mint, output_mint, amount)
        if not quote:
            return False, None, {"error": "Failed to get quote"}

        # Step 2: Sign transaction
        signed_tx = self.sign_transaction(quote)
        if not signed_tx:
            return False, None, {"error": "Failed to sign transaction"}

        request_id = quote.get("requestId")
        if not request_id:
            return False, None, {"error": "Missing requestId in quote"}

        # Step 3: Execute swap
        result = self.execute_swap(signed_tx, request_id)
        if not result:
            return False, None, {"error": "Execution failed"}

        # Process result
        signature = result.get("signature")
        success = result.get("status") == "Success"

        return success, signature, result

    def create_limit_order(self, input_mint: str, output_mint: str, 
                          making_amount: int, taking_amount: int) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """Create a limit order using Jupiter Trigger API.

        Args:
            input_mint: Token we're selling (memecoin)
            output_mint: Token we want to receive (SOL)
            making_amount: Amount of input token to sell (in token's smallest unit)
            taking_amount: Amount of output token we want to receive (in lamports for SOL)

        Returns:
            (success, order_id, signature, result)
        """
        logger.info(f"Creating limit order: {making_amount} {input_mint} -> {taking_amount} {output_mint}")

        # Create the order request
        order_request = {
            "inputMint": input_mint,
            "outputMint": output_mint,
            "maker": str(self.wallet.pubkey()),
            "payer": str(self.wallet.pubkey()),
            "params": {
                "makingAmount": str(making_amount),
                "takingAmount": str(taking_amount),
            },
        }

        endpoint = f"{self.base_url}/trigger/v1/createOrder"
        
        try:
            # Step 1: Create order
            response = requests.post(endpoint, json=order_request, headers=self.headers)
            response.raise_for_status()
            order_data = response.json()

            logger.info(f"Order created successfully: {order_data}")

            # Step 2: Sign transaction
            signed_tx = self.sign_transaction(order_data)
            if not signed_tx:
                logger.error("Failed to sign limit order transaction")
                return False, None, {"error": "Failed to sign transaction"}

            request_id = order_data.get("requestId")
            if not request_id:
                logger.error("Missing requestId in order response")
                return False, None, {"error": "Missing requestId"}

            # Step 3: Execute the order transaction
            result = self.execute_limit_order(signed_tx, request_id)
            if not result:
                logger.error("Failed to execute limit order transaction")
                return False, None, {"error": "Execution failed"}

            # Extract results
            signature = result.get("signature")
            success = result.get("status") == "Success"

            if success:
                logger.info(f"Limit order created successfully! Signature: {signature}")
            else:
                logger.error(f"Limit order creation failed: {result}")

            return success, signature, result

        except Exception as e:
            logger.error(f"Error creating limit order: {e}")
            return False, None, {"error": str(e)}

    def execute_limit_order(self, signed_tx: str, request_id: str) -> Optional[Dict[str, Any]]:
        """Execute a signed limit order transaction.

        Args:
            signed_tx: Base64 encoded signed transaction
            request_id: Request ID from order creation

        Returns:
            Execution result or None if failed
        """
        logger.info("Executing limit order transaction...")

        endpoint = f"{self.base_url}/trigger/v1/execute"
        execute_request = {
            "signedTransaction": signed_tx,
            "requestId": request_id
        }

        try:
            response = requests.post(endpoint, json=execute_request, headers=self.headers)
            response.raise_for_status()
            result = response.json()

            # Process result
            signature = result.get("signature")
            status = result.get("status")

            if status == "Success":
                logger.info(f"Limit order executed successfully! Signature: {signature}")
                print(f"\nView limit order on Solscan: https://solscan.io/tx/{signature}")
            else:
                error_code = result.get("code", "Unknown")
                error_message = result.get("error", "Unknown error")
                logger.error(f"Limit order execution failed: {error_message} (Code: {error_code})")

                if signature:
                    print(f"\nFailed limit order transaction: https://solscan.io/tx/{signature}")

            return result

        except Exception as e:
            logger.error(f"Error executing limit order: {e}")
            return None

