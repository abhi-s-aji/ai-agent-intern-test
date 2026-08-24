"""
Order status lookup module for loading, normalizing, and sanitizing order information.
"""

import json
import os
import re
from typing import Any, Dict, Optional


def normalize_order_id(order_id: Optional[str]) -> str:
    """
    Normalizes an order ID by stripping whitespace, converting to uppercase,
    and correcting minor formatting issues like missing hyphens.
    
    Args:
        order_id: The raw order ID string.
        
    Returns:
        The normalized order ID string.
    """
    if not order_id:
        return ""
        
    # Strip whitespace and convert to uppercase
    val = order_id.strip().upper()
    
    # Handle common format variations, e.g., 'ORD 1007' or 'ORD1007' -> 'ORD-1007'
    match = re.match(r'^ORD\s*[-.\s]?\s*(\d{4})$', val)
    if match:
        return f"ORD-{match.group(1)}"
        
    return val


def is_valid_order_id(order_id: str) -> bool:
    """
    Checks if the normalized order ID follows the valid pattern 'ORD-XXXX' (4 digits).
    
    Args:
        order_id: The normalized order ID string.
        
    Returns:
        True if valid, False otherwise.
    """
    return bool(re.match(r'^ORD-\d{4}$', order_id))


def lookup_order(order_id: Optional[str], filepath: Optional[str] = None) -> Dict[str, Any]:
    """
    Looks up an order by its ID in the orders database, sanitizes it to remove
    sensitive information, and returns a structured, customer-safe result.
    
    Args:
        order_id: The order ID to look up (e.g., 'ORD-1007').
        filepath: Optional path to the orders JSON file. Defaults to 'data/orders.json'
                  resolved relative to this module.
                  
    Returns:
        A dictionary containing:
        - status: One of 'found', 'not_found', or 'invalid' (covering missing/malformed IDs).
        - order: A sanitized dictionary of customer-safe order data if found, else None.
        - message: A customer-safe human-readable message.
        - llm_message: A clean, sanitized text representation of the result suitable for LLM context.
    """
    # 1. Resolve default filepath
    if not filepath:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        filepath = os.path.normpath(os.path.join(current_dir, "..", "data", "orders.json"))
        
    # 2. Handle missing order ID
    if not order_id or not order_id.strip():
        msg = "Order ID is missing. Please provide a valid order ID."
        return {
            "status": "invalid",
            "order": None,
            "message": msg,
            "llm_message": f"Order lookup failed: {msg} Ask the user for the order ID."
        }
        
    # 3. Normalize the order ID
    normalized_id = normalize_order_id(order_id)
    
    # 4. Handle malformed order ID
    if not is_valid_order_id(normalized_id):
        msg = f"The order ID '{order_id.strip()}' is malformed. Valid order IDs must be in the format ORD-XXXX."
        return {
            "status": "invalid",
            "order": None,
            "message": "The order ID format is invalid. Please use the format ORD-XXXX (e.g., ORD-1007).",
            "llm_message": f"Order lookup failed: {msg} Request a valid order ID."
        }
        
    # 5. Load orders file
    if not os.path.exists(filepath):
        msg = f"Orders database not found at '{filepath}'."
        return {
            "status": "not_found",
            "order": None,
            "message": "Orders database is currently unavailable.",
            "llm_message": f"Order lookup error: {msg}"
        }
        
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return {
            "status": "not_found",
            "order": None,
            "message": "Orders database error.",
            "llm_message": f"Order lookup error: Failed to parse orders database. {e}"
        }
        
    orders_list = data.get("orders", [])
    
    # 6. Find the order
    raw_order = None
    for o in orders_list:
        if o.get("order_id") == normalized_id:
            raw_order = o
            break
            
    # 7. Handle unknown order ID
    if not raw_order:
        msg = f"Order '{normalized_id}' not found."
        return {
            "status": "not_found",
            "order": None,
            "message": f"Order {normalized_id} was not found. Please verify the order ID or contact customer support.",
            "llm_message": f"Order lookup failed: {msg} Advise the user to check the ID."
        }
        
    # 8. Sanitize the order fields (customer-safe fields only)
    status = raw_order.get("status")
    
    sanitized_order = {
        "order_id": raw_order.get("order_id"),
        "membership_tier": raw_order.get("membership_tier"),
        "items": [
            {
                "name": item.get("name"),
                "quantity": item.get("quantity"),
                "final_sale": item.get("final_sale")
            }
            for item in raw_order.get("items", [])
        ],
        "placed_at": raw_order.get("placed_at"),
        "status": status,
        "status_updated_at": raw_order.get("status_updated_at"),
        "shipped_at": raw_order.get("shipped_at"),
        "delivered_at": raw_order.get("delivered_at"),
        "customer_safe_message": raw_order.get("customer_safe_message"),
    }
    
    # Handle status-based field exposures (Status precedence rule)
    if status == "cancelled":
        # Stale carrier, tracking, or estimated_delivery fields must not be exposed
        sanitized_order["carrier"] = None
        sanitized_order["tracking_number"] = None
        sanitized_order["estimated_delivery"] = None
    elif status == "returned":
        # Do not expose stale delivery ETA as if it were current
        sanitized_order["carrier"] = raw_order.get("carrier")
        sanitized_order["tracking_number"] = raw_order.get("tracking_number")
        sanitized_order["estimated_delivery"] = None
    else:
        # Shipped, pending, processing, delayed, exception, etc.
        sanitized_order["carrier"] = raw_order.get("carrier")
        sanitized_order["tracking_number"] = raw_order.get("tracking_number")
        # Return estimated delivery only when it exists, representing missing as "Unavailable"
        est_delivery = raw_order.get("estimated_delivery")
        sanitized_order["estimated_delivery"] = est_delivery if est_delivery else "Unavailable"
        
    # 9. Format LLM context message
    item_summaries = []
    for item in sanitized_order["items"]:
        fs_str = " (Final Sale)" if item["final_sale"] else ""
        item_summaries.append(f"{item['quantity']}x {item['name']}{fs_str}")
    items_text = ", ".join(item_summaries)
    
    llm_msg = (
        f"Order {sanitized_order['order_id']} found:\n"
        f"- Status: {status.upper() if status else 'UNKNOWN'}\n"
        f"- Membership Tier: {sanitized_order['membership_tier']}\n"
        f"- Placed At: {sanitized_order['placed_at']}\n"
        f"- Items: {items_text}\n"
        f"- Customer Message: {sanitized_order['customer_safe_message']}\n"
    )
    
    if status == "cancelled":
        llm_msg += "- Carrier: N/A (Order cancelled)\n- Tracking Number: N/A (Order cancelled)\n- Estimated Delivery: N/A (Order cancelled)\n"
    elif status == "returned":
        carrier = sanitized_order["carrier"] or "N/A"
        tracking = sanitized_order["tracking_number"] or "N/A"
        llm_msg += f"- Carrier: {carrier}\n- Tracking Number: {tracking}\n- Estimated Delivery: N/A (Order returned)\n"
    else:
        carrier = sanitized_order["carrier"] or "N/A"
        tracking = sanitized_order["tracking_number"] or "N/A"
        est_delivery = sanitized_order["estimated_delivery"]
        llm_msg += f"- Carrier: {carrier}\n- Tracking Number: {tracking}\n- Estimated Delivery: {est_delivery}\n"
        
    return {
        "status": "found",
        "order": sanitized_order,
        "message": sanitized_order["customer_safe_message"],
        "llm_message": llm_msg
    }
