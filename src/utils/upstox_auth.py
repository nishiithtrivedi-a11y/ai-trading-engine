"""
Upstox API Authentication Helper.

Handles the OAuth2 authorization code flow:
1. Generate login URL (to get interactive user consent).
2. Exchange authorization code for an API access token.
"""

from __future__ import annotations

import os
import urllib.parse
from src.utils.logger import setup_logger

logger = setup_logger("upstox_auth")

def get_upstox_credentials() -> dict[str, str]:
    """Retrieve base API keys from environment."""
    api_key = os.environ.get("UPSTOX_API_KEY", "").strip()
    api_secret = os.environ.get("UPSTOX_API_SECRET", "").strip()
    # The URL your app is running on must match what's configured in Upstox dev portal
    redirect_uri = os.environ.get("UPSTOX_REDIRECT_URI", "http://127.0.0.1:8000/api/v1/providers/sessions/upstox/callback").strip()

    if not api_key or not api_secret:
        raise EnvironmentError(
            "UPSTOX_API_KEY or UPSTOX_API_SECRET is missing. "
            "Please add them to your .env file."
        )

    return {
        "api_key": api_key,
        "api_secret": api_secret,
        "redirect_uri": redirect_uri,
    }

def get_login_url() -> str:
    """Generate the OAuth2 browser explicit grant login URL."""
    creds = get_upstox_credentials()
    params = urllib.parse.urlencode({
        "response_type": "code",
        "client_id": creds["api_key"],
        "redirect_uri": creds["redirect_uri"]
    })
    url = f"https://api.upstox.com/v2/login/authorization/dialog?{params}"
    logger.info("Generated Upstox login URL")
    return url

def generate_access_token(code: str) -> str:
    """Exchange the OAuth authorization code for an access_token.
    
    Args:
        code: The authorization code received at the redirect URI.
        
    Returns:
        The valid access token.
    """
    import requests
    
    creds = get_upstox_credentials()
    
    url = "https://api.upstox.com/v2/login/authorization/token"
    headers = {
        "accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {
        "code": code,
        "client_id": creds["api_key"],
        "client_secret": creds["api_secret"],
        "redirect_uri": creds["redirect_uri"],
        "grant_type": "authorization_code",
    }
    
    response = requests.post(url, headers=headers, data=data)
    
    if not response.ok:
        logger.error(f"Upstox token exchange failed: {response.text}")
        raise Exception(f"Failed to generate Upstox access token: {response.status_code} - {response.text}")
        
    res_data = response.json()
    access_token = res_data.get("access_token")
    
    if not access_token:
        raise Exception(f"Upstox response did not contain an access_token: {res_data}")
        
    logger.info("Successfully generated Upstox access token")
    return access_token
