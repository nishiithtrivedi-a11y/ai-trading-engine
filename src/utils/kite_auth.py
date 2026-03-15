"""
Zerodha Kite Connect authentication helper.

Loads credentials from environment variables (with optional .env file support)
and returns an authenticated KiteConnect client instance.

Usage::

    from src.utils.kite_auth import get_kite_client, get_login_url

    # Generate login URL for the user
    url = get_login_url()

    # After the user has an access token:
    kite = get_kite_client()
    print(kite.profile())
"""

from __future__ import annotations

import os
from typing import Optional

from src.utils.logger import setup_logger

logger = setup_logger("kite_auth")


def _load_dotenv() -> None:
    """Load .env file if python-dotenv is available."""
    try:
        from dotenv import load_dotenv

        load_dotenv()
        logger.debug("Loaded .env file")
    except ImportError:
        logger.debug("python-dotenv not installed, using raw os.environ")


def get_kite_credentials() -> dict[str, str]:
    """Read Kite credentials from environment variables.

    Loads .env file first (if python-dotenv is installed), then reads:
        - ZERODHA_API_KEY
        - ZERODHA_API_SECRET
        - ZERODHA_ACCESS_TOKEN

    Returns:
        Dict with keys ``api_key``, ``api_secret``, ``access_token``.

    Raises:
        EnvironmentError: If api_key or api_secret is missing.
    """
    _load_dotenv()

    api_key = os.environ.get("ZERODHA_API_KEY", "").strip()
    api_secret = os.environ.get("ZERODHA_API_SECRET", "").strip()
    access_token = os.environ.get("ZERODHA_ACCESS_TOKEN", "").strip()

    if not api_key:
        raise EnvironmentError(
            "ZERODHA_API_KEY is not set. "
            "Add it to your .env file or export it as an environment variable."
        )
    if not api_secret:
        raise EnvironmentError(
            "ZERODHA_API_SECRET is not set. "
            "Add it to your .env file or export it as an environment variable."
        )

    return {
        "api_key": api_key,
        "api_secret": api_secret,
        "access_token": access_token,
    }


def get_login_url(api_key: Optional[str] = None) -> str:
    """Generate the Kite Connect login URL.

    The user must open this URL in a browser, log in, and extract
    the ``request_token`` from the redirect URL query parameters.

    Args:
        api_key: Kite API key. If not provided, reads from environment.

    Returns:
        Login URL string.
    """
    if api_key is None:
        creds = get_kite_credentials()
        api_key = creds["api_key"]

    return f"https://kite.zerodha.com/connect/login?v=3&api_key={api_key}"


def generate_access_token(request_token: str) -> str:
    """Exchange a request_token for an access_token.

    Args:
        request_token: The token received from the Kite login redirect.

    Returns:
        The access_token string.

    Raises:
        EnvironmentError: If credentials are missing.
        Exception: If the Kite API rejects the token exchange.
    """
    from kiteconnect import KiteConnect

    creds = get_kite_credentials()
    kite = KiteConnect(api_key=creds["api_key"])

    data = kite.generate_session(request_token, api_secret=creds["api_secret"])
    access_token = data["access_token"]

    logger.info("Access token generated successfully")
    return access_token


def get_kite_client() -> "KiteConnect":
    """Create and return an authenticated KiteConnect client.

    Reads credentials from .env / environment variables.
    The access_token must already be set (either via .env or
    after calling ``generate_access_token``).

    Returns:
        Authenticated KiteConnect instance.

    Raises:
        EnvironmentError: If credentials (including access_token) are missing.
        ImportError: If kiteconnect package is not installed.
    """
    try:
        from kiteconnect import KiteConnect
    except ImportError:
        raise ImportError(
            "kiteconnect package is not installed. "
            "Install with: pip install kiteconnect"
        )

    creds = get_kite_credentials()

    if not creds["access_token"]:
        raise EnvironmentError(
            "ZERODHA_ACCESS_TOKEN is not set. "
            "Run the Kite login flow first to obtain an access token, "
            "then add it to your .env file."
        )

    kite = KiteConnect(api_key=creds["api_key"])
    kite.set_access_token(creds["access_token"])

    logger.info("KiteConnect client created and authenticated")
    return kite
