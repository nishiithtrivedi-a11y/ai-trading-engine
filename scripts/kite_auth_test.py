#!/usr/bin/env python
"""
Kite Connect — Authentication Smoke Test
=========================================

Step 1: Run this script to get the login URL.
Step 2: Open the URL in a browser, log in to Zerodha.
Step 3: After login, you'll be redirected to a URL like:
        http://127.0.0.1:8000?request_token=XXXX&action=login&status=success
Step 4: Copy the request_token value.
Step 5: Run this script again with the --request-token flag:
        python scripts/kite_auth_test.py --request-token XXXX

The generated access_token will be printed — paste it into your .env file
as ZERODHA_ACCESS_TOKEN.

Prerequisites:
    - Fill ZERODHA_API_KEY and ZERODHA_API_SECRET in .env
    - pip install kiteconnect python-dotenv
"""

import sys
import os

# Allow imports from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils.kite_auth import get_login_url, generate_access_token, get_kite_credentials


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Kite Connect authentication helper")
    parser.add_argument(
        "--request-token",
        type=str,
        default=None,
        help="Request token from the Kite login redirect URL",
    )
    args = parser.parse_args()

    # Always show the login URL
    try:
        creds = get_kite_credentials()
        print(f"API Key: {creds['api_key'][:6]}...{creds['api_key'][-4:]}")
    except EnvironmentError as e:
        print(f"ERROR: {e}")
        print("\nMake sure ZERODHA_API_KEY and ZERODHA_API_SECRET are set in .env")
        sys.exit(1)

    login_url = get_login_url()
    print(f"\n{'='*60}")
    print("KITE LOGIN URL")
    print(f"{'='*60}")
    print(f"\n{login_url}\n")
    print("Open this URL in a browser and log in to Zerodha.")
    print("After login, copy the 'request_token' from the redirect URL.")
    print(f"{'='*60}\n")

    if args.request_token:
        print(f"Exchanging request_token for access_token...")
        try:
            access_token = generate_access_token(args.request_token)
            print(f"\nSUCCESS! Your access token:")
            print(f"\n    ZERODHA_ACCESS_TOKEN={access_token}\n")
            print("Paste this into your .env file.")
            print("Note: Access tokens expire daily — repeat this process each morning.")
        except Exception as e:
            print(f"\nERROR generating access token: {e}")
            sys.exit(1)
    else:
        print("After logging in, run again with:")
        print("    python scripts/kite_auth_test.py --request-token YOUR_TOKEN")


if __name__ == "__main__":
    main()
