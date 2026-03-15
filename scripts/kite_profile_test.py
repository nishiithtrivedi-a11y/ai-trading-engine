#!/usr/bin/env python
"""
Kite Connect — Profile Smoke Test
===================================

Verifies that your credentials work by calling kite.profile().

Prerequisites:
    - Fill ZERODHA_API_KEY, ZERODHA_API_SECRET, ZERODHA_ACCESS_TOKEN in .env
    - pip install kiteconnect python-dotenv

Usage:
    python scripts/kite_profile_test.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils.kite_auth import get_kite_client


def main():
    print("Connecting to Kite Connect...")
    try:
        kite = get_kite_client()
    except (EnvironmentError, ImportError) as e:
        print(f"\nERROR: {e}")
        sys.exit(1)

    try:
        profile = kite.profile()
    except Exception as e:
        print(f"\nERROR calling kite.profile(): {e}")
        print("Your access token may have expired. Generate a new one:")
        print("    python scripts/kite_auth_test.py --request-token YOUR_TOKEN")
        sys.exit(1)

    print(f"\n{'='*50}")
    print("KITE PROFILE — CONNECTION SUCCESSFUL")
    print(f"{'='*50}")
    print(f"  User Name  : {profile.get('user_name', 'N/A')}")
    print(f"  User ID    : {profile.get('user_id', 'N/A')}")
    print(f"  Email      : {profile.get('email', 'N/A')}")
    print(f"  Broker     : {profile.get('broker', 'N/A')}")
    print(f"  Exchanges  : {profile.get('exchanges', [])}")
    print(f"  Products   : {profile.get('products', [])}")
    print(f"  Order Types: {profile.get('order_types', [])}")
    print(f"{'='*50}")
    print("\nKite Connect is working correctly!")


if __name__ == "__main__":
    main()
