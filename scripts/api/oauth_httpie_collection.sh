#!/bin/bash
# OAuth API Testing Collection for HTTPie
# BaliBlissed Backend - OAuth Endpoints
#
# Usage:
#   chmod +x oauth_httpie_collection.sh
#   ./oauth_httpie_collection.sh
#
# Or run individual commands directly

# Configuration
BASE_URL="http://localhost:8000"
PROVIDER="google"

echo "==================================="
echo "OAuth API Testing Collection"
echo "BaliBlissed Backend"
echo "==================================="
echo ""

# ============================================================================
# 1. OAUTH LOGIN - Initiate OAuth Flow
# ============================================================================
echo "1. OAUTH LOGIN - Initiate OAuth Flow"
echo "------------------------------------"
echo "Description: Redirects to OAuth provider login page"
echo ""
echo "Command:"
echo "  http -v GET ${BASE_URL}/auth/login/${PROVIDER}"
echo ""
echo "Expected Response:"
echo "  HTTP/1.1 302 Found"
echo "  Location: https://accounts.google.com/o/oauth2/v2/auth?..."
echo ""

# Uncomment to run:
# http -v GET ${BASE_URL}/auth/login/${PROVIDER}

echo ""

# ============================================================================
# 2. OAUTH LOGIN - Unconfigured Provider
# ============================================================================
echo "2. OAUTH LOGIN - Unconfigured Provider (Error Case)"
echo "----------------------------------------------------"
echo "Description: Tests error handling for unconfigured provider"
echo ""
echo "Command:"
echo "  http GET ${BASE_URL}/auth/login/nonexistent"
echo ""
echo "Expected Response:"
echo "  HTTP/1.1 404 Not Found"
echo '  {"detail": "Provider nonexistent not configured"}'
echo ""

# Uncomment to run:
# http GET ${BASE_URL}/auth/login/nonexistent

echo ""

# ============================================================================
# 3. OAUTH CALLBACK - Simulate Callback (Manual Test)
# ============================================================================
echo "3. OAUTH CALLBACK - Simulate Provider Callback"
echo "-----------------------------------------------"
echo "Description: Simulates OAuth provider callback"
echo "Note: This requires a valid state from the login step"
echo ""
echo "Command:"
echo "  http GET ${BASE_URL}/auth/callback/${PROVIDER} \\"
echo "    state==YOUR_STATE_FROM_LOGIN \\"
echo "    code==AUTHORIZATION_CODE_FROM_PROVIDER"
echo ""
echo "Expected Response (Success):"
echo "  HTTP/1.1 200 OK"
echo '  {'
echo '    "access_token": "eyJhbGciOiJIUzI1NiIs...",'
echo '    "refresh_token": "eyJhbGciOiJIUzI1NiIs...",'
echo '    "token_type": "bearer"'
echo '  }'
echo ""
echo "Expected Response (Invalid State):"
echo "  HTTP/1.1 400 Bad Request"
echo '  {"detail": "Invalid or expired OAuth state"}'
echo ""

# Uncomment to run (replace with actual values):
# http GET ${BASE_URL}/auth/callback/${PROVIDER} state==test_state code==test_code

echo ""

# ============================================================================
# 4. OAUTH CALLBACK - Missing State (Error Case)
# ============================================================================
echo "4. OAUTH CALLBACK - Missing State (Error Case)"
echo "-----------------------------------------------"
echo "Description: Tests error handling for missing state parameter"
echo ""
echo "Command:"
echo "  http GET ${BASE_URL}/auth/callback/${PROVIDER} code==some_code"
echo ""
echo "Expected Response:"
echo "  HTTP/1.1 400 Bad Request"
echo '  {"detail": "Missing OAuth state parameter"}'
echo ""

# Uncomment to run:
# http GET ${BASE_URL}/auth/callback/${PROVIDER} code==some_code

echo ""

# ============================================================================
# 5. OAUTH CALLBACK - Invalid State (Error Case)
# ============================================================================
echo "5. OAUTH CALLBACK - Invalid State (Error Case)"
echo "-----------------------------------------------"
echo "Description: Tests error handling for invalid/expired state"
echo ""
echo "Command:"
echo "  http GET ${BASE_URL}/auth/callback/${PROVIDER} \\"
echo "    state==invalid_state \\"
echo "    code==some_code"
echo ""
echo "Expected Response:"
echo "  HTTP/1.1 400 Bad Request"
echo '  {"detail": "Invalid or expired OAuth state"}'
echo ""

# Uncomment to run:
# http GET ${BASE_URL}/auth/callback/${PROVIDER} state==invalid_state code==some_code

echo ""

# ============================================================================
# 6. COMPLETE OAUTH FLOW TEST (Full Integration)
# ============================================================================
echo "6. COMPLETE OAUTH FLOW TEST (Full Integration)"
echo "-----------------------------------------------"
echo "Description: Complete OAuth flow from login to callback"
echo ""
echo "Step 1: Get redirect URL and state"
echo "  http -h GET ${BASE_URL}/auth/login/${PROVIDER} | grep Location"
echo ""
echo "Step 2: Complete login in browser with the redirect URL"
echo ""
echo "Step 3: Capture the callback URL (browser will redirect to:)"
echo "  ${BASE_URL}/auth/callback/${PROVIDER}?state=XXX&code=YYY"
echo ""
echo "Step 4: Exchange code for tokens (if not automatically handled)"
echo "  # This is done automatically by the callback endpoint"
echo ""

echo ""

# ============================================================================
# 7. MULTI-PROVIDER TEST
# ============================================================================
echo "7. MULTI-PROVIDER AVAILABILITY TEST"
echo "------------------------------------"
echo "Description: Check which OAuth providers are configured"
echo ""

for p in google wechat apple; do
  echo "Testing provider: ${p}"
  echo "  Command: http -h GET ${BASE_URL}/auth/login/${p}"
  # http -h GET ${BASE_URL}/auth/login/${p} 2>/dev/null | head -1
done

echo ""

# ============================================================================
# 8. ENVIRONMENT CHECK
# ============================================================================
echo "8. ENVIRONMENT CHECK"
echo "--------------------"
echo "Description: Verify OAuth configuration"
echo ""
echo "Command:"
echo "  http GET ${BASE_URL}/health"
echo ""

# Uncomment to run:
# http GET ${BASE_URL}/health

echo ""
echo "==================================="
echo "Collection Complete"
echo "==================================="
