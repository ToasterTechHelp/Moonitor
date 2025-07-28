#!/usr/bin/env python3
"""
Order Management CLI for Moonitor

This script allows you to view and cancel open Jupiter limit orders.
"""

import os
import sys
from dotenv import load_dotenv

# Add src to path so we can import our modules
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.trading.trader import JupiterTrader

def format_order_info(order):
    """Format order information for display."""
    order_key = order.get('orderKey', 'Unknown')
    input_mint = order.get('inputMint', 'Unknown')
    output_mint = order.get('outputMint', 'Unknown')
    making_amount = order.get('makingAmount', 'Unknown')
    taking_amount = order.get('takingAmount', 'Unknown')
    
    # Try to get token symbols if available
    input_symbol = order.get('inputTokenSymbol', input_mint[:8] + '...')
    output_symbol = order.get('outputTokenSymbol', output_mint[:8] + '...')
    
    return f"""
Order Key: {order_key}
Selling: {making_amount} {input_symbol}
For: {taking_amount} {output_symbol}
Input Mint: {input_mint}
Output Mint: {output_mint}
"""

def main():
    # Load environment variables
    load_dotenv()
    
    try:
        # Initialize trader
        print("Initializing Jupiter trader...")
        trader = JupiterTrader()
        
        while True:
            print("\n" + "="*60)
            print("MOONITOR ORDER MANAGEMENT")
            print("="*60)
            print("1. View open orders")
            print("2. Cancel specific order")
            print("3. Exit")
            print("="*60)
            
            choice = input("Select option (1-3): ").strip()
            
            if choice == "1":
                print("\nFetching open orders...")
                result = trader.get_open_orders()
                
                if not result:
                    print("❌ Failed to fetch orders")
                    continue
                
                orders = result.get("orders", [])
                
                if not orders:
                    print("✅ No open orders found")
                    continue
                
                print(f"\n📋 Found {len(orders)} open orders:")
                print("-" * 60)
                
                for i, order in enumerate(orders, 1):
                    print(f"\n[{i}] {format_order_info(order)}")
                    print("-" * 60)
            
            elif choice == "2":
                print("\nFetching orders to cancel...")
                result = trader.get_open_orders()
                
                if not result:
                    print("❌ Failed to fetch orders")
                    continue
                
                orders = result.get("orders", [])
                
                if not orders:
                    print("✅ No open orders to cancel")
                    continue
                
                print(f"\n📋 Select order to cancel:")
                print("-" * 60)
                
                for i, order in enumerate(orders, 1):
                    print(f"\n[{i}] {format_order_info(order)}")
                    print("-" * 60)
                
                try:
                    selection = int(input(f"\nEnter order number (1-{len(orders)}) or 0 to cancel: "))
                    
                    if selection == 0:
                        print("❌ Cancelled")
                        continue
                    
                    if selection < 1 or selection > len(orders):
                        print("❌ Invalid selection")
                        continue
                    
                    selected_order = orders[selection - 1]
                    order_key = selected_order.get('orderKey')
                    
                    if not order_key:
                        print("❌ Invalid order account")
                        continue
                    
                    print(f"\n⚠️  Cancelling order: {order_key}")
                    confirm = input("Are you sure? (yes/no): ").strip().lower()
                    
                    if confirm not in ['yes', 'y']:
                        print("❌ Cancelled")
                        continue
                    
                    print("🔄 Cancelling order...")
                    success, signature, result = trader.cancel_order(order_key)
                    
                    if success:
                        print(f"✅ Order cancelled successfully!")
                        print(f"Transaction: https://solscan.io/tx/{signature}")
                    else:
                        print(f"❌ Failed to cancel order: {result}")
                
                except ValueError:
                    print("❌ Invalid input")
                except Exception as e:
                    print(f"❌ Error: {e}")
            
            elif choice == "3":
                print("👋 Goodbye!")
                break
            
            else:
                print("❌ Invalid choice. Please select 1-3.")
    
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())