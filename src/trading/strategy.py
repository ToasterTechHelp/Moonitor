import os
import logging


def calculate_trade_plan(analysis: dict) -> dict | None:
    """
    Calculates a detailed trade plan based on LLM analysis and settings from env.

    Args:
        analysis (dict): The analysis dictionary from the LLM.
                         Expected keys: 'decision', 'confidence_score'.

    Returns:
        dict | None: A dictionary containing the trade plan, or None if the decision is not 'buy'.
                     The plan includes:
                     - 'purchase_amount_sol': The amount of SOL to spend.
                     - 'take_profit_percentage': The target gain percentage for the take-profit order.
                     - 'stop_loss_percentage': The percentage loss for the stop-loss order.
    """

    try:
        # ----- Load Base Strategy Parameters from .env -----
        base_purchase_sol = float(os.getenv("BASE_PURCHASE_SOL"))
        base_take_profit_pct = float(os.getenv("BASE_TAKE_PROFIT_PCT", 0.3))
        base_stop_loss_pct = float(os.getenv("BASE_STOP_LOSS_PCT", 0.5))

        # Determine how much confidence affects the trade size.
        purchase_influence_factor = float(os.getenv("PURCHASE_INFLUENCE_FACTOR", 0.5))
        tp_increase_factor = float(os.getenv("TAKE_PROFIT_INCREASE_FACTOR", 0.5))
        sl_decrease_factor = float(os.getenv("STOP_LOSS_DECREASE_FACTOR", 0.5))

        confidence_score = analysis.get('confidence_score', 0.0)

        # ----- Calculate Dynamic Trade Parameters -----

        # 1. Calculate final purchase amount
        purchase_multiplier = 1 + (confidence_score * purchase_influence_factor)
        final_purchase_sol = base_purchase_sol * purchase_multiplier

        # 2. Calculate final take-profit percentage
        tp_multiplier = 1 + (confidence_score * tp_increase_factor)
        final_take_profit_pct = base_take_profit_pct * tp_multiplier

        # 3. Calculate final stop-loss percentage
        sl_multiplier = 1 + (confidence_score * sl_decrease_factor)
        calculated_stop_loss = base_stop_loss_pct * sl_multiplier
        final_stop_loss_pct = min(calculated_stop_loss, 0.99)

        trade_plan = {
            "purchase_amount_sol": final_purchase_sol,
            "take_profit_percentage": final_take_profit_pct,
            "stop_loss_percentage": final_stop_loss_pct,
            "token_address": analysis.get('token_address')
        }

        logging.info(f"Calculated trade plan: {trade_plan}")
        return trade_plan

    except (ValueError, TypeError) as e:
        logging.error(f"Error in trade plan calculation due to invalid .env variables: {e}")
        return None
    except Exception as e:
        logging.error(f"An unexpected error occurred in calculate_trade_plan: {e}", exc_info=True)
        return None