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
        # This prompt is now simplified because we are sending a structured message list.
        system_prompt = """
        You are a financial analyst specializing in identifying trading signals for memecoins on the Solana blockchain from Telegram messages.
        Your task is to analyze the conversation history provided and determine if the LAST message in the list contains a trading signal.
        Use the previous messages for context. Usually, if a coin address is provided, it should be bought, unless the context clearly indicates to not buy.

        You must return your analysis in a strict JSON format. The JSON object must contain the following keys:
        - "decision": Your decision, which must be one of two strings: "buy" or "hold".
        - "confidence_score": A float between 0.0 and 1.0 representing your confidence in the decision.
        - "rationale": A brief, one-sentence explanation for your decision, focusing on the last message.
        - "token_address": The Solana contract address of the token mentioned. If no address is found, this must be null.

        If the last message is irrelevant, a joke, or is a signal to not buy, you must return "hold" with a 0 confidence_score.
        """

        messages_to_send = [
            {"role": "system", "content": system_prompt},
            *message_list  # Unpack the list of user messages
        ]

        response = client.chat.completions.create(
            model="gpt-4o-mini",  # Changed back to gpt-4o-mini as it's generally more available and cost-effective
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