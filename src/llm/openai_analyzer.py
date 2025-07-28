import os
import logging
import json
from openai import OpenAI, RateLimitError, APIError


def analyze_with_openai(message_list: list[dict]) -> dict | None:
    """
    Analyzes a given list of message dictionaries using the OpenAI GPT model
    and returns a structured response.

    Args:
        message_list (list[dict]): A list of message dictionaries representing the
                                   conversation history and the newest message.

    Returns:
        dict | None: A dictionary containing the LLM's analysis (decision, confidence, etc.)
                      or None if an error occurs or the response is invalid.
    """
    try:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        # --- SYSTEM PROMPT ---
        system_prompt = """
        You are a financial analyst specializing in identifying trading signals for memecoins on the Solana blockchain from Telegram messages.
        Your task is to analyze the conversation history provided and determine if the LAST message in the list contains a trading signal.

        CORE RULE: If a Solana token address is provided in the current message, default to "buy" UNLESS there are explicit warning signals.

        Warning signals that indicate "hold":
        - Words like "scam", "rug", "avoid", "don't buy", "stay away"
        - Phrases indicating past losses or failures
        - Clear statements advising against purchase

        Trading signals that indicate "buy":
        - Any Solana token address (44 characters, alphanumeric)
        - Market cap mentions with addresses
        - Price targets or entry points
        - Calls to action like "ape in", "buy", "entry", "gamble"
        - General memecoin discussion with addresses

        You must return your analysis in a strict JSON format. The JSON object must contain the following keys:
        - "decision": Your decision, which must be one of two strings: "buy" or "hold".
        - "confidence_score": A float between 0.0 and 1.0 representing your confidence in the buy. If hold, set this to 0.0.
        - "rationale": A brief, one-sentence explanation for your decision, focusing on the last message.
        - "token_address": The Solana contract address of the token mentioned. If no address is found, this must be null.

        When in doubt with a token address present in the last message, choose "buy" over "hold". "buy" is the default unless it clearly says to "DO NOT BUY" or similar.
        Only look into the last message in the list for the token and decision-making. Previous messages are for context only.
        """

        messages_to_send = [
            {"role": "system", "content": system_prompt},
            *message_list  # Unpack the list of user messages
        ]

        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            response_format={"type": "json_object"},
            messages=messages_to_send
        )

        llm_output_str = response.choices[0].message.content
        logging.info(f"LLM Raw Response: {llm_output_str}")

        analysis_result = json.loads(llm_output_str)

        # Validate the response structure
        required_keys = ["decision", "confidence_score", "rationale", "token_address"]
        if not all(key in analysis_result for key in required_keys):
            logging.error(f"LLM response is missing required keys: {analysis_result}")
            return None

        if analysis_result.get("decision") not in ["buy", "hold"]:
            logging.error(f"LLM returned an invalid decision: {analysis_result.get('decision')}")
            return None

        return analysis_result

    except RateLimitError:
        logging.error("OpenAI API rate limit exceeded. Please check your plan and usage.")
        return None
    except APIError as e:
        logging.error(f"An OpenAI API error occurred: {e}", exc_info=True)
        return None
    except json.JSONDecodeError:
        logging.error(f"Failed to decode JSON from LLM response: {llm_output_str}")
        return None
    except Exception as e:
        logging.error(f"An unexpected error occurred during LLM analysis: {e}", exc_info=True)
        return None