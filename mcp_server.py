#!/usr/bin/env python3
"""
MCP Server for Errata Tool Integration
Exposes errata client functionality as MCP tools for AI assistants

Consolidated from errata_client.py and errata_server.py using FastMCP
"""

import asyncio
import json
import logging
import os
from typing import List, Dict, Any, Optional, Tuple
from fastmcp import FastMCP
from errata_tool import Erratum
from errata_tool.product import Product
from errata_tool.release import Release
import requests
try:
    # requests_gssapi is the modern replacement for requests-kerberos
    from requests_gssapi import HTTPSPNEGOAuth, REQUIRED as GSSAPI_REQUIRED
except Exception:  # pragma: no cover - fall back if not installed
    HTTPSPNEGOAuth = None  # type: ignore
    GSSAPI_REQUIRED = None  # type: ignore

# Configure SSL certificate bundle for Red Hat internal CAs
# This ensures requests can verify Red Hat internal SSL certificates
if 'REQUESTS_CA_BUNDLE' not in os.environ:
    # Try the Red Hat IT CA we found on the system
    rh_ca_paths = [
        '/etc/pki/tls/certs/2015-RH-IT-Root-CA.pem',
        '/etc/pki/tls/certs/ca-bundle.crt',
        '/etc/pki/ca-trust/source/anchors/RH-IT-Root-CA.crt'
    ]
    
    for ca_path in rh_ca_paths:
        if os.path.exists(ca_path):
            os.environ['REQUESTS_CA_BUNDLE'] = ca_path
            print(f"Set REQUESTS_CA_BUNDLE to {ca_path}")
            break
    else:
        print("Warning: No Red Hat CA certificate found in standard locations")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastMCP server
mcp = FastMCP("errata-mcp-server")

def _get_errata_base_url() -> str:
    """Resolve the Errata Tool base URL (prod by default, stage if requested)."""
    explicit = os.environ.get("ERRATA_BASE_URL")
    if explicit:
        return explicit.rstrip('/') + '/'
    if os.environ.get("ERRATA_STAGE") in {"1", "true", "True"}:
        return "https://errata.stage.engineering.redhat.com/"
    return "https://errata.engineering.redhat.com/"


def _http_get_errata_json(path: str, params: Optional[Dict[str, Any]] = None) -> Tuple[Dict[str, Any], str]:
    """
    Perform an authenticated GET to the Errata Tool HTTP API and return JSON.

    Returns: (json, url)
    Raises: Exception on non-2xx or parsing issues.
    """
    base = _get_errata_base_url()
    url = f"{base}api/v1/{path.lstrip('/')}"

    session = requests.Session()
    verify = os.environ.get('REQUESTS_CA_BUNDLE') or True

    if HTTPSPNEGOAuth is None:
        raise RuntimeError(
            "requests-gssapi is required for Kerberos authentication. Please 'pip install requests-gssapi'."
        )

    auth = HTTPSPNEGOAuth(mutual_authentication=GSSAPI_REQUIRED)
    logger.debug(f"GET {url} params={params}")
    resp = session.get(url, params=params or {}, auth=auth, verify=verify, timeout=60)
    if resp.status_code == 401:
        raise PermissionError("Unauthorized (401). Ensure you have a valid Kerberos ticket (kinit) and network access.")
    if resp.status_code == 403:
        raise PermissionError("Forbidden (403). Your account may not have access to this advisory or environment.")
    if resp.status_code == 404:
        raise FileNotFoundError(f"Not found (404): {url}")
    if not resp.ok:
        raise RuntimeError(f"Errata API error {resp.status_code}: {resp.text}")

    try:
        return resp.json(), resp.url
    except Exception as exc:
        raise RuntimeError(f"Failed to parse JSON from {url}: {exc}")


def _fetch_builds_list_with_signing(advisory_id: int) -> Dict[str, Any]:
    """
    Fetch /api/v1/erratum/{id}/builds_list?with_sig_key=1 and return the JSON.
    """
    data, final_url = _http_get_errata_json(
        f"erratum/{advisory_id}/builds_list",
        params={"with_sig_key": 1},
    )
    logger.info(f"Fetched builds_list for {advisory_id} ({final_url})")
    return data


def _summarize_signing(builds_list: Dict[str, Any]) -> Dict[str, Any]:
    """Compute a concise signing summary across all product versions and builds."""
    total_builds = 0
    unsigned_build_nvrs: List[str] = []
    total_files = 0
    unsigned_files = 0

    # Iterate product versions
    for _pv_name, pv in builds_list.items():
        builds = pv.get("builds", [])
        for bwrap in builds:
            # Each build is a single-key dict like {"nvr": {...}}
            if not isinstance(bwrap, dict) or not bwrap:
                continue
            (nvr_key, binfo), = bwrap.items()  # type: ignore
            total_builds += 1

            # Track build-level signed
            is_build_signed = bool(binfo.get("is_signed", False))
            if not is_build_signed:
                unsigned_build_nvrs.append(nvr_key)

            # Count per-file signing state
            variant_arch = binfo.get("variant_arch", {}) or {}
            for _variant, arches in variant_arch.items():
                for _arch, files in arches.items():
                    for f in files:
                        total_files += 1
                        if not f.get("is_signed", False):
                            unsigned_files += 1

    return {
        "total_builds": total_builds,
        "unsigned_builds": unsigned_build_nvrs,
        "all_builds_signed": total_builds > 0 and len(unsigned_build_nvrs) == 0,
        "total_files": total_files,
        "unsigned_files": unsigned_files,
        "all_files_signed": total_files > 0 and unsigned_files == 0,
    }

def list_products() -> List[str]:
    """
    List available products.
    Returns an empty list if no products are found or an error occurs.
    """
    print("\n--- Listing Available Products ---")
    try:
        # Try to get some common products to test accessibility
        common_products = [
            "RHEL", "RHIVOS", "RHCEPH", "RHOSE", "RHSCL", "RHGS", "RHSAT"
        ]
        
        # Test which products are accessible
        accessible_products = []
        for product_name in common_products:
            try:
                prod = Product(product_name)
                accessible_products.append(prod.name)
                print(f"✓ Found product: {prod.name}")
            except Exception as e:
                print(f"✗ Product {product_name} not accessible: {e}")
        
        print(f"Found {len(accessible_products)} accessible products.")
        return sorted(accessible_products)
        
    except Exception as e:
        print(f"Error listing products: {e}")
        return []

def list_states() -> List[str]:
    """
    List possible advisory states.
    Returns the standard list of Errata Tool states.
    """
    print("\n--- Listing Advisory States ---")
    
    # Standard Errata Tool states
    states = [
        "NEW_FILES", "QE", "REL_PREP", "PUSH_READY", "IN_PUSH", "SHIPPED_LIVE"
    ]
    
    print(f"Available states: {', '.join(states)}")
    return states

def list_advisories(product: Optional[str] = None, state: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """
    List advisories with optional filtering by product and state.
    Note: Due to limitations in the errata-tool library, this function can only
    work with specific advisory IDs, not browse by product/state.
    """
    print(f"\n--- Listing Advisories (product='{product}', state='{state}', limit={limit}) ---")
    
    # The errata-tool library is designed to work with specific advisory IDs
    # rather than browse/search functionality. This is a fundamental limitation.
    raise Exception(
        "Listing advisories by product and state is not supported by the errata-tool library. "
        "The library is designed to work with specific advisory IDs. "
        "Use get_advisory_info() with a specific numeric advisory ID instead. "
        "Example: get_advisory_info('148894')"
    )

def get_advisory_info(advisory_id: str) -> Dict[str, Any]:
    """
    Get detailed information about a specific advisory.
    Returns an empty dictionary if the advisory is not found or an error occurs.
    """
    print(f"\n--- Getting Advisory Info for: '{advisory_id}' ---")
    print(f"KRB5CCNAME environment: {os.environ.get('KRB5CCNAME', 'Not set')}")
    print(f"REQUESTS_CA_BUNDLE: {os.environ.get('REQUESTS_CA_BUNDLE', 'Not set')}")
    
    try:
        # Try to get the advisory by ID
        if advisory_id.isdigit():
            print(f"Attempting to create Erratum object for ID: {advisory_id}")
            erratum = Erratum(errata_id=int(advisory_id))
        else:
            raise ValueError(f"Numeric advisory ID required (e.g., 12345), got: {advisory_id}")
        
        # Get advisory details
        advisory_info = {
            'id': erratum.errata_name,
            'numeric_id': getattr(erratum, 'errata_id', ''),
            'synopsis': getattr(erratum, 'synopsis', ''),
            'description': getattr(erratum, 'description', ''),
            'type': getattr(erratum, 'errata_type', ''),
            'state': erratum.errata_state,
            'product': getattr(erratum, 'product', ''),
            'release': getattr(erratum, 'release', ''),
            'created_date': str(getattr(erratum, 'issue_date', '')),
            'updated_date': str(getattr(erratum, 'update_date', '')),
            'url': erratum.url(),
            'embargoed': erratum.embargoed,
            'text_only': erratum.text_only,
            'content_types': erratum.content_types
        }
        
        # Add security-specific info if available
        if hasattr(erratum, 'security_impact'):
            advisory_info['security_impact'] = erratum.security_impact
        
        # Fetch builds_list with signing info and add a concise summary
        try:
            builds_list = _fetch_builds_list_with_signing(erratum.errata_id)
            signing_summary = _summarize_signing(builds_list)
            advisory_info['builds_signing_summary'] = signing_summary
            advisory_info['builds_list_url'] = f"{_get_errata_base_url()}api/v1/erratum/{erratum.errata_id}/builds_list?with_sig_key=1"
        except Exception as fetch_exc:
            logger.warning(f"Failed to fetch builds signing info for {advisory_id}: {fetch_exc}")
            advisory_info['builds_signing_summary'] = {
                "error": str(fetch_exc)
            }
            
        print("Advisory info retrieved successfully.")
        return advisory_info
        
    except Exception as e:
        print(f"Error getting advisory info for {advisory_id}: {e}")
        raise e

@mcp.tool()
async def list_errata_products() -> Dict[str, Any]:
    """
    List available products in the Errata Tool.
    
    Returns:
        A dictionary containing available products and their details.
    """
    try:
        products = list_products()
        if not products:
            return {
                "status": "error",
                "message": "No products found. This may be due to network connectivity issues or authentication problems with the Errata Tool."
            }
        
        return {
            "status": "success",
            "data": products,
            "message": f"Retrieved {len(products)} products"
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to retrieve products: {str(e)}"
        }

@mcp.tool()
async def list_errata_states() -> Dict[str, Any]:
    """
    List all possible advisory states in the Errata Tool.
    
    Returns:
        A dictionary containing available advisory states.
    """
    try:
        states = list_states()
        return {
            "status": "success",
            "data": states,
            "message": f"Retrieved {len(states)} advisory states"
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to retrieve states: {str(e)}"
        }

@mcp.tool()
async def list_errata_advisories(
    product: Optional[str] = None,
    state: Optional[str] = None,
    limit: int = 50
) -> Dict[str, Any]:
    """
    List advisories with optional filtering by product and state.
    
    Args:
        product: Product name to filter by (e.g., RHEL, RHIVOS, RHCEPH)
        state: Advisory state to filter by (e.g., QE, SHIPPED_LIVE, NEW_FILES)
        limit: Maximum number of advisories to return (default: 50)
    
    Returns:
        A dictionary containing matching advisories.
    """
    try:
        advisories = list_advisories(product, state, limit)
        
        return {
            "status": "success",
            "data": advisories,
            "filter": {
                "product": product,
                "state": state,
                "limit": limit
            },
            "message": f"Retrieved {len(advisories)} advisories"
        }
    except Exception as e:
        # Handle the specific case where listing advisories is not supported
        return {
            "status": "error",
            "message": f"Feature limitation: {str(e)}"
        }

@mcp.tool()
async def get_errata_advisory_info(advisory_id: str) -> Dict[str, Any]:
    """
    Get detailed information about a specific advisory.
    
    Args:
        advisory_id: Advisory ID (numeric ID like '12345')
    
    Returns:
        A dictionary containing detailed advisory information.
    """
    try:
        if not advisory_id:
            raise ValueError("advisory_id is required")
            
        advisory_info = get_advisory_info(advisory_id)
        
        return {
            "status": "success",
            "data": advisory_info,
            "advisory_id": advisory_id,
            "message": f"Retrieved information for advisory {advisory_id}"
        }
        
    except ValueError as ve:
        return {
            "status": "error",
            "advisory_id": advisory_id,
            "message": f"Invalid input: {str(ve)}"
        }
    except Exception as e:
        return {
            "status": "error",
            "advisory_id": advisory_id,
            "message": f"Failed to retrieve advisory {advisory_id}: {str(e)}"
        }


@mcp.tool()
async def get_errata_advisory_builds(advisory_id: str) -> Dict[str, Any]:
    """
    Get builds_list for an advisory with signing info included.

    Args:
        advisory_id: Advisory ID (numeric ID like '12345')

    Returns:
        A dictionary containing the raw builds_list JSON and a signing summary.
    """
    try:
        if not advisory_id or not advisory_id.isdigit():
            raise ValueError("Numeric advisory_id is required (e.g., '12345')")
        aid = int(advisory_id)
        builds_list = _fetch_builds_list_with_signing(aid)
        summary = _summarize_signing(builds_list)
        return {
            "status": "success",
            "advisory_id": advisory_id,
            "data": builds_list,
            "signing_summary": summary,
            "api_url": f"{_get_errata_base_url()}api/v1/erratum/{aid}/builds_list?with_sig_key=1"
        }
    except Exception as e:
        return {
            "status": "error",
            "advisory_id": advisory_id,
            "message": f"Failed to fetch builds_list: {str(e)}"
        }

def main():
    """Main entry point for the MCP server"""
    try:
        # Get transport method from environment, defaulting to SSE (prioritized)
        transport = os.environ.get("MCP_TRANSPORT", "sse")
        
        logger.info(f"Starting Errata Tool MCP server with {transport} transport")
        logger.info(f"KRB5CCNAME: {os.environ.get('KRB5CCNAME', 'Not set')}")
        logger.info(f"PYTHONPATH: {os.environ.get('PYTHONPATH', 'Not set')}")
        
        # For SSE transport, also log port information
        if transport == "sse":
            port = os.environ.get("MCP_PORT", "8000")
            logger.info(f"SSE transport will use port: {port}")
        
        # Run the FastMCP server
        mcp.run(transport=transport)
        
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}")
        import sys
        sys.exit(1)

if __name__ == "__main__":
    main()
