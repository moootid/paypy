import json
import boto3
import os
import hmac
import hashlib
import base64
from datetime import datetime, timezone
import uuid

# --- Environment Variables ---
# You MUST set these in your Lambda configuration
TABLE_NAME = "geidea_callback"
# API_PASSWORD and MERCHANT_PUBLIC_KEY are no longer needed for verification
# API_PASSWORD = os.environ.get('API_PASSWORD')
# MERCHANT_PUBLIC_KEY = os.environ.get('MERCHANT_PUBLIC_KEY')

# Initialize Boto3 clients
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(TABLE_NAME)

# --- VERIFICATION FUNCTION REMOVED FOR DEBUGGING ---
# def verify_callback_signature(payload: dict) -> bool: ...

def lambda_handler(event, context):
    """
    Main handler for API Gateway webhook.
    --- DEBUGGING MODE: SIGNATURE VERIFICATION IS DISABLED ---
    """
    print("--- NEW WEBHOOK REQUEST RECEIVED (DEBUG MODE) ---")
    
    # 1. Get timestamp and generate unique ID
    received_at = datetime.now(timezone.utc).isoformat()
    callback_id = str(uuid.uuid4())
    
    raw_body_str = '{}'
    headers = {}
    
    try:
        # 2. Extract headers and body
        # API Gateway (HTTP API payload format 2.0)
        headers = event.get('headers', {})
        raw_body_str = event.get('body', '{}')
        
        # Log for debugging (per your request)
        print(f"[DEBUG] Received Headers: {json.dumps(headers, indent=2)}")
        print(f"[DEBUG] Received Raw Body: {raw_body_str}")
        
        if not raw_body_str:
            raise ValueError("Received empty request body")
            
        # Try to parse JSON just to ensure it's valid, but store raw string
        # This will raise an error if JSON is invalid, which is caught below
        json.loads(raw_body_str)
        
    except json.JSONDecodeError:
        print("[ERROR] Failed to decode JSON from request body. Storing raw data anyway.")
        # Re-assign raw_body_str in case it was None and json.loads failed
        raw_body_str = event.get('body', 'INVALID_JSON_DATA') 
    except Exception as e:
        print(f"[ERROR] An unexpected error occurred: {e}")
        raw_body_str = f"Error parsing body: {e}"

    # 3. Store in DynamoDB (Verification step removed)
    try:
        item = {
            'id': callback_id,
            'receivedAt': received_at,
            'requestBody': raw_body_str, # Store the raw string
            'requestHeaders': json.dumps(headers), # Store headers as a JSON string
            'note': 'DEBUGGING_MODE - Signature not verified'
        }
        
        table.put_item(Item=item)
        
        print(f"[INFO] Successfully stored callback {callback_id} in DynamoDB.")
        
    except Exception as e:
        print(f"[FATAL] Failed to write to DynamoDB: {e}")
        # Return 500 so Geidea knows we had an internal error
        return {
            'statusCode': 500,
            'body': json.dumps({'message': 'Internal server error (DynamoDB)'})
        }

    # 4. Return correct HTTP response to Geidea
    # Always return 200 OK to acknowledge receipt in debug mode
    return {
        'statusCode': 200,
        'body': json.dumps({'message': 'Callback received (DEBUG MODE)'})
    }