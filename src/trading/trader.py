import os
import requests
import json
import base64
import base58
import logging
from dotenv import load_dotenv

from solana.rpc.api import Client
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction

# --- Basic Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class JupiterTrader:
    def __init__(self):
        """Initialize the Jupiter trader with environment variables."""
        try:
            # Load environment variables from a.env file
            load_dotenv()

            # Validate environment variables
            self.private_key_b58 = os.getenv('PRIVATE_KEY')
            self.rpc_url = os.getenv('SOLANA_RPC_URL')
            self.slippage = int(os.getenv('SLIPPAGE', 50))  # Default to 50 bps (0.5%)

            if not self.private_key_b58:
                raise ValueError("PRIVATE_KEY environment variable is not set")

            if not self.rpc_url:
                raise ValueError("RPC_URL environment variable is not set")

            logger.info("Environment variables loaded successfully")

            # Initialize RPC client
            try:
                self.client = Client(self.rpc_url)
                logger.info(f"RPC client initialized with URL: {self.rpc_url}")
            except Exception as e:
                raise ConnectionError(f"Failed to initialize RPC client: {e}")

            # Initialize keypair from the base58 private key
            try:
                # The private key must be decoded from base58 into bytes
                private_key_bytes = base58.b58decode(self.private_key_b58)
                self.keypair = Keypair.from_bytes(private_key_bytes)
                self.taker_address = str(self.keypair.pubkey())
                logger.info(f"Keypair initialized successfully. Taker address: {self.taker_address}")
            except Exception as e:
                raise ValueError(f"Failed to initialize keypair from private key: {e}")

        except ValueError as e:
            logger.error(f"Configuration error: {e}")
            raise
        except ConnectionError as e:
            logger.error(f"Connection error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during Jupiter trader initialization: {e}")
            raise

    def get_jupiter_order(self, input_mint, output_mint, amount):
        """Requests a swap order from the Jupiter Ultra API."""
        logger.info("Requesting swap order from Jupiter...")

        base_url = "https://lite-api.jup.ag/ultra/v1/order"
        params = {
            'inputMint': input_mint,
            'outputMint': output_mint,
            'amount': amount,
            'taker': self.taker_address,
            'slippageBps': self.slippage
        }

        try:
            logger.debug(f"Making request to {base_url} with params: {params}")
            response = requests.get(base_url, params=params, timeout=30)
            response.raise_for_status()

            order_data = response.json()
            logger.info("Successfully fetched order from Jupiter")
            logger.debug(f"Order data received: {json.dumps(order_data, indent=2)}")
            return order_data

        except requests.exceptions.Timeout:
            logger.error("Request to Jupiter API timed out")
            return None
        except requests.exceptions.ConnectionError:
            logger.error("Connection error when calling Jupiter API")
            return None
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error {e.response.status_code} when calling Jupiter API: {e.response.text}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error when calling Jupiter API: {e}")
            return None
        except json.JSONDecodeError:
            logger.error("Failed to decode JSON response from Jupiter API")
            return None
        except Exception as e:
            logger.error(f"Unexpected error when calling Jupiter API: {e}")
            return None

    def sign_and_serialize_transaction(self, order_response):
        """
        Signs the transaction received from Jupiter and serializes it for execution.
        This is the most critical client-side step.
        """
        logger.info("Signing and serializing the transaction...")
        try:
            # 1. Extract the base64 encoded transaction string
            tx_base64 = order_response.get('transaction')
            if not tx_base64:
                raise ValueError("'transaction' not found in the order response.")

            # 2. Decode the base64 string into bytes
            tx_bytes = base64.b64decode(tx_base64)

            # 3. Deserialize the bytes into a VersionedTransaction object
            transaction = VersionedTransaction.from_bytes(tx_bytes)

            # 4. Fetch the latest blockhash from the RPC
            # This is required for the transaction to be considered recent and valid
            latest_blockhash_resp = self.client.get_latest_blockhash()
            if not latest_blockhash_resp.value:
                raise ConnectionError("Failed to fetch latest blockhash.")
            transaction.message.recent_blockhash = latest_blockhash_resp.value.blockhash

            # 5. Sign the transaction with the local keypair
            transaction.sign([self.keypair])

            # 6. Serialize the signed transaction back into bytes
            signed_tx_bytes = bytes(transaction)

            # 7. Encode the signed transaction bytes into a base64 string
            signed_tx_base64 = base64.b64encode(signed_tx_bytes).decode('utf-8')

            logger.info("Transaction signed and serialized successfully.")
            return signed_tx_base64

        except (ValueError, ConnectionError) as e:
            logger.error(f"Error during transaction signing: {e}")
            return None
        except Exception as e:
            logger.error(f"An unexpected error occurred during signing: {e}")
            return None

    def execute_jupiter_order(self, signed_tx_base64, request_id):
        """
        Submits the signed transaction to the /execute endpoint to be processed
        by Jupiter's broadcasting engine.
        """
        logger.info("Executing the swap transaction...")

        base_url = "https://lite-api.jup.ag/ultra/v1/execute"
        headers = {'Content-Type': 'application/json'}
        payload = {
            'signedTransaction': signed_tx_base64,
            'requestId': request_id
        }

        try:
            logger.debug(f"Making POST request to {base_url}")
            response = requests.post(base_url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()

            exec_data = response.json()
            logger.info("Swap execution request sent successfully.")
            logger.debug(f"Execution response: {json.dumps(exec_data, indent=2)}")
            return exec_data

        except requests.exceptions.Timeout:
            logger.error("Request to Jupiter /execute API timed out")
            return None
        except requests.exceptions.ConnectionError:
            logger.error("Connection error when calling Jupiter /execute API")
            return None
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error {e.response.status_code} when calling Jupiter /execute API: {e.response.text}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error when calling Jupiter /execute API: {e}")
            return None
        except json.JSONDecodeError:
            logger.error("Failed to decode JSON response from Jupiter /execute API")
            return None
        except Exception as e:
            logger.error(f"Unexpected error when calling Jupiter /execute API: {e}")
            return None


if __name__ == "__main__":
    try:
        # --- 1. Initialize the Trader ---
        trader = JupiterTrader()

        # --- 2. Define Swap Parameters and Token Info ---
        # Using a dictionary for token info makes it easier to manage
        token_info = {
            "SOL": {"mint": "So11111111111111111111111111111111111111112", "decimals": 9},
            "USDC": {"mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", "decimals": 6}
        }

        input_token = "SOL"
        output_token = "USDC"

        # Amount to swap (in lamports for SOL)
        AMOUNT_IN_LAMPORTS = 10000000  # 0.01 SOL

        # --- 3. Get the Unsigned Transaction from /order ---
        order = trader.get_jupiter_order(
            input_mint=token_info[input_token]["mint"],
            output_mint=token_info[output_token]["mint"],
            amount=AMOUNT_IN_LAMPORTS
        )
        if not order:
            raise SystemExit("Failed to get order. Exiting.")

        # --- 4. Sign and Serialize the Transaction ---
        signed_tx = trader.sign_and_serialize_transaction(order)
        if not signed_tx:
            raise SystemExit("Failed to sign transaction. Exiting.")

        # --- 5. Execute the Swap ---
        request_id = order.get('requestId')
        if not request_id:
            raise SystemExit("'requestId' not found in order response. Exiting.")

        execution_result = trader.execute_jupiter_order(signed_tx, request_id)

        if execution_result:
            print("\n--- Swap Result ---")
            if execution_result.get('status') == 'Success':
                tx_signature = execution_result.get('signature')

                # NEW: Parse the final amounts from the response [1]
                input_amount_spent_raw = int(execution_result.get('inputAmountResult', 0))
                output_amount_received_raw = int(execution_result.get('outputAmountResult', 0))

                # Convert from raw integer to decimal format
                input_decimals = token_info[input_token]['decimals']
                output_decimals = token_info[output_token]['decimals']

                final_amount_spent = input_amount_spent_raw / (10 ** input_decimals)
                final_amount_received = output_amount_received_raw / (10 ** output_decimals)

                print(f"✅ Swap successful!")
                print(f"   Spent: {final_amount_spent:.8f} {input_token}")
                print(f"   Received: {final_amount_received:.6f} {output_token}")
                print(f"\n   View on Solscan: https://solscan.io/tx/{tx_signature}")
            else:
                print("\n❌ Swap failed.")
                print(json.dumps(execution_result, indent=2))
        else:
            print("\n❌ Swap execution failed.")

    except (ValueError, ConnectionError, SystemExit) as e:
        print(f"\nA critical error occurred: {e}")