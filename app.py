from flask import Flask, jsonify
import asyncio
import random
import traceback
import time
from decimal import Decimal

from pytoniq import (
    LiteClient,
    Address,
    WalletV5R1
)

from tonsdk.crypto import mnemonic_new

# =========================================================
# FLASK APP
# =========================================================

app = Flask(__name__)

# =========================================================
# SETTINGS
# =========================================================

WALLET_ID = 698983191

HOST = "0.0.0.0"
PORT = 5000

MAX_RETRIES = 5
RECONNECT_DELAY = 1

# =========================================================
# GLOBAL EVENT LOOP
# =========================================================

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

# =========================================================
# GLOBAL CLIENT
# =========================================================

client = None

# =========================================================
# AUTO JSON RESPONSE
# =========================================================

def response_json(
    success=False,
    message="",
    data=None,
    error=None,
    status=200
):

    return jsonify({

        "success": success,

        "message": message,

        "server_time": int(time.time()),

        "data": data if data else {},

        "error": error if error else None

    }), status

# =========================================================
# FORMAT ERROR
# =========================================================

def format_error(e):

    return {

        "type": type(e).__name__,

        "message": str(e),

        "traceback": traceback.format_exc()
    }

# =========================================================
# CREATE CLIENT
# =========================================================

def create_client():

    return LiteClient.from_mainnet_config(

        ls_i=random.randint(0, 15),

        trust_level=2
    )

# =========================================================
# CONNECT CLIENT
# =========================================================

async def connect_client():

    global client

    try:

        if client:

            try:
                await client.close()
            except:
                pass

        client = create_client()

        await client.connect()

        return True

    except:

        return False

# =========================================================
# STARTUP
# =========================================================

loop.run_until_complete(
    connect_client()
)

# =========================================================
# ENSURE CLIENT CONNECTED
# =========================================================

async def ensure_client():

    global client

    try:

        if client is None:

            await connect_client()

        return client

    except:

        await connect_client()

        return client

# =========================================================
# SAFE ACCOUNT STATE
# =========================================================

async def safe_get_account_state(address):

    global client

    for _ in range(MAX_RETRIES):

        try:

            await ensure_client()

            state = await client.get_account_state(
                address
            )

            return state

        except:

            try:

                await connect_client()

            except:
                pass

            await asyncio.sleep(
                RECONNECT_DELAY
            )

    raise Exception(
        "TON LiteServer unavailable"
    )

# =========================================================
# FORMAT TON
# =========================================================

def format_ton(value):

    try:

        value = Decimal(value)

        return format(
            value.normalize(),
            "f"
        )

    except:

        return str(value)

# =========================================================
# VALIDATE ADDRESS
# =========================================================

def validate_address(address_text):

    try:

        address = Address(address_text)

        return True, address

    except Exception as e:

        return False, str(e)

# =========================================================
# CREATE WALLET
# =========================================================

async def create_wallet():

    try:

        await ensure_client()

        mnemonic_words = mnemonic_new()

        wallet = await WalletV5R1.from_mnemonic(

            provider=client,

            mnemonics=mnemonic_words,

            wallet_id=WALLET_ID,

            wc=0
        )

        bounceable = wallet.address.to_str(
            is_user_friendly=True,
            is_bounceable=True
        )

        non_bounceable = wallet.address.to_str(
            is_user_friendly=True,
            is_bounceable=False
        )

        raw_address = wallet.address.to_str(
            is_user_friendly=False
        )

        return {

            "wallet_version": "v5r1",

            "wallet_id": WALLET_ID,

            "mnemonic": mnemonic_words,

            "mnemonic_text": " ".join(
                mnemonic_words
            ),

            "addresses": {

                "bounceable": bounceable,

                "non_bounceable": non_bounceable,

                "raw": raw_address
            }
        }

    except Exception as e:

        raise Exception(
            format_error(e)
        )

# =========================================================
# GET WALLET BALANCE
# =========================================================

async def get_wallet_balance(address_text):

    try:

        valid, result = validate_address(
            address_text
        )

        if not valid:

            raise Exception(
                f"Invalid TON Address: {result}"
            )

        address = result

        account_state = await safe_get_account_state(
            address
        )

        balance = int(
            account_state.balance
        )

        ton_balance = Decimal(balance) / Decimal(
            "1000000000"
        )

        bounceable = address.to_str(
            is_user_friendly=True,
            is_bounceable=True
        )

        non_bounceable = address.to_str(
            is_user_friendly=True,
            is_bounceable=False
        )

        raw_address = address.to_str(
            is_user_friendly=False
        )

        return {

            "addresses": {

                "bounceable": bounceable,

                "non_bounceable": non_bounceable,

                "raw": raw_address
            },

            "balance": {

                "nano": str(balance),

                "ton": format_ton(
                    ton_balance
                )
            }
        }

    except Exception as e:

        raise Exception(
            format_error(e)
        )

# =========================================================
# ERROR HANDLERS
# =========================================================

@app.errorhandler(404)
def not_found(e):

    return response_json(

        success=False,

        message="Route Not Found",

        error={

            "type": "NotFound",

            "message": str(e)
        },

        status=404
    )

@app.errorhandler(405)
def method_not_allowed(e):

    return response_json(

        success=False,

        message="Method Not Allowed",

        error={

            "type": "MethodNotAllowed",

            "message": str(e)
        },

        status=405
    )

@app.errorhandler(500)
def internal_server_error(e):

    return response_json(

        success=False,

        message="Internal Server Error",

        error={

            "type": "InternalServerError",

            "message": str(e)
        },

        status=500
    )

@app.errorhandler(Exception)
def handle_exception(e):

    return response_json(

        success=False,

        message="Unhandled Exception",

        error=format_error(e),

        status=500
    )

# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():

    return response_json(

        success=True,

        message="TON Wallet API Running",

        data={

            "routes": {

                "create_wallet":
                "/create_wallet",

                "wallet_balance":
                "/wallet_balance/<address>",

                "health":
                "/health"
            },

            "wallet_version": "v5r1",

            "wallet_id": WALLET_ID
        }
    )

# =========================================================
# HEALTH
# =========================================================

@app.route("/health")
def health():

    try:

        connected = client is not None

        return response_json(

            success=True,

            message="Server Healthy",

            data={

                "client_connected": connected
            }
        )

    except Exception as e:

        return response_json(

            success=False,

            message="Health Check Failed",

            error=format_error(e),

            status=500
        )

# =========================================================
# CREATE WALLET API
# =========================================================

@app.route("/create_wallet")
def create_wallet_api():

    try:

        result = loop.run_until_complete(
            create_wallet()
        )

        return response_json(

            success=True,

            message="Wallet Created Successfully",

            data=result
        )

    except Exception as e:

        return response_json(

            success=False,

            message="Wallet Creation Failed",

            error=format_error(e),

            status=500
        )

# =========================================================
# BALANCE API
# =========================================================

@app.route("/wallet_balance/<path:address>")
def wallet_balance_api(address):

    try:

        result = loop.run_until_complete(
            get_wallet_balance(address)
        )

        return response_json(

            success=True,

            message="Wallet Balance Fetched",

            data=result
        )

    except Exception as e:

        return response_json(

            success=False,

            message="Failed To Fetch Balance",

            error=format_error(e),

            status=500
        )

# =========================================================
# START SERVER
# =========================================================

if __name__ == "__main__":

    app.run(

        host=HOST,

        port=PORT,

        threaded=True,

        debug=False
    )
