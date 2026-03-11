"""
Polymarket CLOB Setup — Run this ONCE to derive your API credentials.

Usage:
  pip install py-clob-client
  python polymarket-setup.py

This will print your apiKey, secret, and passphrase.
Save them in kalshi-config.json.
"""
from py_clob_client.client import ClobClient

# Your wallet private key from Polymarket Settings > Private Key
PRIVATE_KEY = "0x2038b5f13adbf9d68d7387ad50a4b0d400089ca66a0319c433496422e1e17384"

# Step 1: Create client with just the private key (L1 auth)
client = ClobClient(
    host="https://clob.polymarket.com",
    chain_id=137,  # Polygon mainnet
    key=PRIVATE_KEY
)

# Step 2: Derive API credentials
print("Deriving CLOB API credentials from wallet...")
print("(This signs a message with your wallet key)\n")

try:
    creds = client.create_or_derive_api_creds()
    print("SUCCESS! Save these in your kalshi-config.json:\n")
    print(f'  "polymarket_api_key": "{creds.api_key}",')
    print(f'  "polymarket_api_secret": "{creds.api_secret}",')
    print(f'  "polymarket_api_passphrase": "{creds.api_passphrase}",')
    print()

    # Step 3: Test the credentials by checking balance
    from py_clob_client.client import ClobClient as ClobClient2
    api_creds = {
        "key": creds.api_key,
        "secret": creds.api_secret,
        "passphrase": creds.api_passphrase,
    }
    
    # Get the funder address (proxy wallet)
    print("Fetching funder/proxy address...")
    # The funder is typically the proxy contract address for your wallet
    # For Magic Link wallets, we need to check
    
    print(f"\nYour wallet address: {client.get_address()}")
    print("\nNow testing with full credentials...")
    
    client2 = ClobClient(
        host="https://clob.polymarket.com",
        chain_id=137,
        key=PRIVATE_KEY,
        creds=api_creds,
        signature_type=2,  # 2 = POLY_GNOSIS_SAFE for Magic Link wallets
    )
    
    # Test: get open orders
    print("\nConnection test...")
    try:
        orders = client2.get_orders()
        print(f"Open orders: {len(orders) if orders else 0} — API working!")
    except Exception as e:
        print(f"Note: {e}")
        print("If you get a 'signature_type' error, we may need to try type 1 or 0")

except Exception as e:
    print(f"Error: {e}")
    print("\nTroubleshooting:")
    print("1. Make sure py-clob-client is installed: pip install py-clob-client")
    print("2. Check your private key starts with 0x")
    print("3. Make sure you have internet access")