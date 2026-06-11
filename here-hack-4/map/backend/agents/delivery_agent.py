# pyre-ignore-all-errors
# ============================================================================
# Agent 4 — Delivery App Evidence Agent (Singapore)
# ============================================================================
"""
Gathers operational evidence from food delivery platforms:
- foodpanda Singapore (OAuth 2.0 Client Credentials)
- Deliveroo Singapore

Implements OAuth 2.0 token caching and reuse until expiration.
"""
import logging
import time
from typing import Any, Dict, List, Optional
import httpx

from backend.agents.base_agent import BaseAgent
from backend.schemas.models import DeliveryEvidence, SourceTypeEnum, FreshnessLabel
from backend.config import settings

log = logging.getLogger("delivery_agent")

FOODPANDA_OAUTH_URL = "https://api.foodpanda.sg/oauth/token"
FOODPANDA_API_URL = "https://api.foodpanda.sg/v1"
DELIVEROO_API_URL = "https://api.deliveroo.sg/v1"
REQUEST_TIMEOUT = 10.0

# OAuth 2.0 Token Cache (in-memory)
# Structure: {"access_token": str, "expires_at": float (unix timestamp)}
_foodpanda_token_cache: Dict[str, Any] = {}


class DeliveryEvidenceAgent(BaseAgent):
    name = "delivery_evidence"

    async def execute(self, payload: Dict[str, Any]) -> List[DeliveryEvidence]:
        baseline = payload.get("baseline", [])
        results = []

        # Filter for food & beverage
        fb_places = [
            p for p in baseline 
            if any(cat in p.get("category", "").lower() for cat in ["food", "restaurant", "cafe", "bar"])
        ]

        async with httpx.AsyncClient() as client:
            # Check foodpanda (OAuth 2.0)
            if settings.foodpanda_client_id and settings.foodpanda_client_secret:
                fp_results = await self._check_foodpanda(client, fb_places)
                results.extend(fp_results)
            else:
                log.warning("FOODPANDA_CLIENT_ID/SECRET not set — skipping foodpanda")

            # Check Deliveroo
            if settings.deliveroo_api_key:
                dr_results = await self._check_deliveroo(client, fb_places)
                results.extend(dr_results)
            else:
                log.warning("DELIVEROO_API_KEY not set — skipping Deliveroo")

        log.info(f"Delivery evidence: Found {len(results)} listings across foodpanda/Deliveroo")
        return results

    async def _get_foodpanda_access_token(self, client: httpx.AsyncClient) -> Optional[str]:
        """
        OAuth 2.0 Client Credentials Flow - Get and cache access token.
        Implements token caching with TTL from expires_in field.
        """
        global _foodpanda_token_cache
        
        # Check if cached token is still valid
        if _foodpanda_token_cache:
            expires_at = _foodpanda_token_cache.get("expires_at", 0)
            if time.time() < expires_at:
                return _foodpanda_token_cache.get("access_token")
        
        # Token expired or missing - get new one
        try:
            data = {
                "grant_type": "client_credentials",
                "client_id": settings.foodpanda_client_id,
                "client_secret": settings.foodpanda_client_secret,
            }
            
            resp = await client.post(
                FOODPANDA_OAUTH_URL,
                data=data,
                timeout=REQUEST_TIMEOUT
            )
            
            if resp.status_code == 200:
                token_response = resp.json()
                access_token = token_response.get("access_token")
                expires_in = token_response.get("expires_in", 3600)  # Default 1 hour
                
                # Cache token with expiration time (TTL)
                _foodpanda_token_cache = {
                    "access_token": access_token,
                    "expires_at": time.time() + expires_in - 60,  # Refresh 60s before expiry
                }
                
                log.debug(f"foodpanda: OAuth token obtained (expires in {expires_in}s)")
                return access_token
            else:
                log.error(f"foodpanda OAuth failed: {resp.status_code} - {resp.text}")
                return None
                
        except Exception as e:
            log.error(f"foodpanda OAuth error: {e}")
            return None

    async def _check_foodpanda(
        self,
        client: httpx.AsyncClient,
        places: List[Dict]
    ) -> List[DeliveryEvidence]:
        """Query foodpanda Singapore API for merchant listings using OAuth 2.0."""
        results = []
        
        # Get cached or fresh access token
        access_token = await self._get_foodpanda_access_token(client)
        if not access_token:
            log.warning("Cannot get foodpanda access token")
            return results
        
        try:
            headers = {"Authorization": f"Bearer {access_token}"}
            
            for place in places[:30]:  # Limit to avoid rate-limiting
                name = place.get("name", "")
                if not name:
                    continue

                # Search foodpanda for merchant
                try:
                    params = {"q": name, "region": "singapore"}
                    resp = await client.get(
                        f"{FOODPANDA_API_URL}/merchants/search",
                        headers=headers,
                        params=params,
                        timeout=REQUEST_TIMEOUT
                    )
                    if resp.status_code != 200:
                        continue

                    data = resp.json()
                    merchants = data.get("merchants", [])
                    
                    for merchant in merchants:
                        results.append(DeliveryEvidence(
                            source_type=SourceTypeEnum.foodpanda,
                            platform="foodpanda",
                            merchant_name=merchant.get("name", name),
                            merchant_id=merchant.get("id"),
                            category=place.get("category", "food"),
                            is_available=merchant.get("is_available", True),
                            has_delivery=merchant.get("has_delivery", True),
                            has_pickup=merchant.get("has_pickup", False),
                            menu_item_count=merchant.get("menu_item_count"),
                            rating=merchant.get("rating"),
                            confidence=0.85,
                            freshness=FreshnessLabel.very_recent,
                            raw_data=merchant,
                        ))
                        log.debug(f"foodpanda: Found {merchant.get('name')}")
                        
                except Exception as e:
                    log.debug(f"foodpanda search error for '{name}': {e}")
                    continue

        except Exception as e:
            log.warning(f"foodpanda agent error: {e}")

        return results

    async def _check_deliveroo(
        self,
        client: httpx.AsyncClient,
        places: List[Dict]
    ) -> List[DeliveryEvidence]:
        """Query Deliveroo Singapore API for merchant listings."""
        results = []
        try:
            headers = {"Authorization": f"Bearer {settings.deliveroo_api_key}"}
            
            for place in places[:30]:  # Limit to avoid rate-limiting
                name = place.get("name", "")
                if not name:
                    continue

                # Search Deliveroo for merchant
                try:
                    params = {"q": name, "country_code": "sg"}
                    resp = await client.get(
                        f"{DELIVEROO_API_URL}/restaurants/search",
                        headers=headers,
                        params=params,
                        timeout=REQUEST_TIMEOUT
                    )
                    if resp.status_code != 200:
                        continue

                    data = resp.json()
                    restaurants = data.get("restaurants", [])
                    
                    for restaurant in restaurants:
                        results.append(DeliveryEvidence(
                            source_type=SourceTypeEnum.deliveroo,
                            platform="deliveroo",
                            merchant_name=restaurant.get("name", name),
                            merchant_id=restaurant.get("id"),
                            category=place.get("category", "food"),
                            is_available=restaurant.get("is_available", True),
                            has_delivery=restaurant.get("has_delivery", True),
                            has_pickup=restaurant.get("has_pickup", False),
                            menu_item_count=restaurant.get("menu_item_count"),
                            rating=restaurant.get("rating"),
                            confidence=0.85,
                            freshness=FreshnessLabel.very_recent,
                            raw_data=restaurant,
                        ))
                        log.debug(f"Deliveroo: Found {restaurant.get('name')}")
                        
                except Exception as e:
                    log.debug(f"Deliveroo search error for '{name}': {e}")
                    continue

        except Exception as e:
            log.warning(f"Deliveroo agent error: {e}")

        return results

