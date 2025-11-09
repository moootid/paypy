import os
import requests
import hmac
import hashlib
import base64
import json
from datetime import datetime
import pytz
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# --- Environment Variable Loading ---
# Load configuration from environment
MERCHANT_PUBLIC_KEY = os.getenv("MERCHANT_PUBLIC_KEY")
API_PASSWORD = os.getenv("API_PASSWORD")
CALLBACK_URL = os.getenv("CALLBACK_URL")
RETURN_URL = os.getenv("RETURN_URL")
# Use a default merchant reference ID if not provided, or generate one
MERCHANT_REFERENCE_ID = os.getenv("MERCHANT_REFERENCE_ID", "default-ref-id")
GEIDEA_API_URL = os.getenv(
    "GEIDEA_API_URL",
    "https://api.ksamerchant.geidea.net/payment-intent/api/v2/direct/session"
)
PAYMENT_LANGUAGE = os.getenv("PAYMENT_LANGUAGE", "en")
TIMEZONE = os.getenv("TIMEZONE", "Asia/Riyadh")

# Validate critical environment variables
if not all([MERCHANT_PUBLIC_KEY, API_PASSWORD, CALLBACK_URL, RETURN_URL]):
    print("FATAL ERROR: Missing one or more critical environment variables.")
    # In a real app, you might want to exit or raise a more specific config error
    # For now, this will cause the functions to fail if used.

# --- Pydantic Models (Request & Response) ---

class CreateSessionRequest(BaseModel):
    amount: float = Field(..., gt=0, description="The payment amount.")
    currency: str = Field(..., max_length=3, description="The 3-letter currency code (e.g., SAR).")
    customer_email: str = Field(..., description="Customer's email address.")
    customer_phone_number: str = Field(..., description="Customer's full phone number.")
    customer_phone_country_code: str = Field(..., description="Country code (e.g., +966).")

class CreateSessionResponse(BaseModel):
    session_id: str
    session: dict # Optionally return the whole session object

class ErrorResponse(BaseModel):
    detail: str

# --- Helper Functions (Your Original Logic) ---

def generate_auth_token(key, password):
    """
    Generates a Basic HTTP Authorization token from a key and password.
    """
    credentials = f"{key}:{password}"
    credentials_bytes = credentials.encode('utf-8')
    token_bytes = base64.b64encode(credentials_bytes)
    token_str = token_bytes.decode('utf-8')
    return f"Basic {token_str}"

def generate_signature(merchant_public_key, order_amount, order_currency, order_merchant_reference_id, api_password, time_stamp):
    """
    Generates an HMAC-SHA256 signature based on Geidea API requirements.
    """
    amount_str = f"{order_amount:.2f}"
    ref_id = order_merchant_reference_id or ""
    data = f"{merchant_public_key}{amount_str}{order_currency}{ref_id}{time_stamp}"
    
    key_bytes = api_password.encode('utf-8')
    message_bytes = data.encode('utf-8')
    
    h = hmac.new(key_bytes, message_bytes, hashlib.sha256)
    hash_bytes = h.digest()
    
    signature = base64.b64encode(hash_bytes).decode('utf-8')
    return signature

def get_formatted_timestamp():
    """
    Generates a timestamp in the format required by Geidea (M/d/yyyy h:mm:ss tt)
    e.g., "2/21/2024 5:16:48 AM"
    """
    try:
        tz = pytz.timezone(TIMEZONE)
    except pytz.UnknownTimeZoneError:
        tz = pytz.timezone("UTC")
        
    now = datetime.now(tz)
    
    # Format hour without leading zero (e.g., 5, not 05)
    hour = now.strftime('%I').lstrip('0')
    minute_second_ampm = now.strftime('%M:%S %p')
    
    # Format month and day without leading zeros
    timestamp = f"{now.month}/{now.day}/{now.year} {hour}:{minute_second_ampm}"
    return timestamp

# --- FastAPI Application ---

app = FastAPI(
    title="Geidea Payment Gateway Service",
    description="A backend service to create payment sessions with Geidea."
)

@app.post("/create-payment-session",
          response_model=CreateSessionResponse,
          responses={500: {"model": ErrorResponse}, 400: {"model": ErrorResponse}})
async def create_payment_session(request_data: CreateSessionRequest):
    """
    Creates a new Geidea payment session.
    """
    if not all([MERCHANT_PUBLIC_KEY, API_PASSWORD]):
        raise HTTPException(status_code=500, detail="Server is not configured correctly.")

    try:
        current_timestamp = get_formatted_timestamp()
        
        # Generate the signature
        generated_signature = generate_signature(
            MERCHANT_PUBLIC_KEY,
            request_data.amount,
            request_data.currency,
            MERCHANT_REFERENCE_ID,
            API_PASSWORD,
            current_timestamp
        )

        # Build the full payload
        payload = {
            "amount": request_data.amount,
            "currency": request_data.currency,
            "timestamp": current_timestamp,
            "merchantReferenceId": MERCHANT_REFERENCE_ID,
            "signature": generated_signature,
            "paymentOperation": "Pay",
            "appearance": {"uiMode": "modal"},
            "language": PAYMENT_LANGUAGE,
            "callbackUrl": CALLBACK_URL,
            "returnUrl": RETURN_URL,
            "customer": {
                "email": request_data.customer_email,
                "phoneNumber": request_data.customer_phone_number,
                "phoneCountryCode": request_data.customer_phone_country_code
            },
            "initiatedBy": "Internet"
        }

        # Generate the auth token
        auth_token = generate_auth_token(MERCHANT_PUBLIC_KEY, API_PASSWORD)
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "authorization": auth_token
        }
        
        # --- Call Geidea API ---
        print(f"Sending request to Geidea API at {GEIDEA_API_URL}")
        response = requests.post(GEIDEA_API_URL, json=payload, headers=headers)
        
        # Raise an exception for bad HTTP status codes
        response.raise_for_status()

        # --- Process Response ---
        response_data = response.json()
        
        session_id = response_data.get("session", {}).get("id", None)
        
        if not session_id:
            print(f"Error: 'session.id' not found in Geidea response. Full response: {response_data}")
            raise HTTPException(status_code=500, detail="Failed to retrieve session ID from payment provider.")

        print(f"Successfully created session: {session_id}")
        return CreateSessionResponse(
            session_id=session_id,
            session=response_data.get("session")
        )

    except requests.exceptions.HTTPError as http_err:
        # Handle HTTP errors from Geidea
        print(f"HTTP error occurred: {http_err} - {http_err.response.text}")
        raise HTTPException(
            status_code=http_err.response.status_code,
            detail=f"Payment provider error: {http_err.response.text}"
        )
    except Exception as e:
        # Handle any other unexpected errors
        print(f"An unexpected error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An internal server error occurred: {str(e)}")

# Add a simple health check endpoint
@app.get("/health", status_code=200)
def health_check():
    return {"status": "ok"}