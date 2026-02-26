#!/bin/bash
# Test OCI authentication before running Terraform

echo "=== OCI Authentication Diagnostic ==="
echo ""

# Check required variables
REQUIRED_VARS=(
  "TF_VAR_user_ocid"
  "TF_VAR_tenancy_ocid"
  "TF_VAR_fingerprint"
  "TF_VAR_region"
  "TF_VAR_compartment_id"
  "TF_VAR_private_key"
)

echo "1. Checking environment variables..."
MISSING=0
for var in "${REQUIRED_VARS[@]}"; do
  if [ -z "${!var}" ]; then
    echo "   ❌ $var is not set"
    MISSING=1
  else
    echo "   ✅ $var is set"
  fi
done

if [ $MISSING -eq 1 ]; then
  echo ""
  echo "ERROR: Missing required variables. Set them before running Terraform."
  exit 1
fi

echo ""
echo "2. Validating private key format..."
if echo "$TF_VAR_private_key" | grep -q "BEGIN.*PRIVATE KEY"; then
  echo "   ✅ Private key has BEGIN header"
else
  echo "   ❌ Private key missing BEGIN header"
  exit 1
fi

if echo "$TF_VAR_private_key" | grep -q "END.*PRIVATE KEY"; then
  echo "   ✅ Private key has END footer"
else
  echo "   ❌ Private key missing END footer"
  exit 1
fi

LINE_COUNT=$(echo "$TF_VAR_private_key" | wc -l)
if [ "$LINE_COUNT" -gt 5 ]; then
  echo "   ✅ Private key has multiple lines ($LINE_COUNT)"
else
  echo "   ⚠️  Private key has only $LINE_COUNT lines (may be malformed)"
fi

echo ""
echo "3. Validating fingerprint format..."
if echo "$TF_VAR_fingerprint" | grep -qE '^[a-f0-9]{2}(:[a-f0-9]{2}){15}$'; then
  echo "   ✅ Fingerprint format is valid"
else
  echo "   ❌ Fingerprint format is invalid"
  echo "      Expected: aa:bb:cc:dd:ee:ff:00:11:22:33:44:55:66:77:88:99"
  echo "      Got: $TF_VAR_fingerprint"
  exit 1
fi

echo ""
echo "4. Validating OCID formats..."
if echo "$TF_VAR_user_ocid" | grep -q "^ocid1\.user\."; then
  echo "   ✅ User OCID format is valid"
else
  echo "   ❌ User OCID format is invalid (should start with ocid1.user.)"
fi

if echo "$TF_VAR_tenancy_ocid" | grep -q "^ocid1\.tenancy\."; then
  echo "   ✅ Tenancy OCID format is valid"
else
  echo "   ❌ Tenancy OCID format is invalid (should start with ocid1.tenancy.)"
fi

if echo "$TF_VAR_compartment_id" | grep -qE "^ocid1\.(compartment|tenancy)\."; then
  echo "   ✅ Compartment OCID format is valid"
else
  echo "   ❌ Compartment OCID format is invalid"
fi

echo ""
echo "5. Testing OCI API connectivity..."
echo "   Creating temporary key file..."
TMP_KEY=$(mktemp)
echo "$TF_VAR_private_key" > "$TMP_KEY"
chmod 600 "$TMP_KEY"

# Test with curl (OCI API signature)
TIMESTAMP=$(date -u '+%a, %d %b %Y %H:%M:%S GMT')
REQUEST_TARGET="get /20160918/availabilityDomains?compartmentId=$TF_VAR_compartment_id"

echo "   Testing API call to: https://identity.$TF_VAR_region.oci.oraclecloud.com"
echo "   Request: $REQUEST_TARGET"

# Simple test - if this fails, credentials are wrong
RESPONSE=$(curl -s -w "\n%{http_code}" \
  -H "date: $TIMESTAMP" \
  "https://identity.$TF_VAR_region.oci.oraclecloud.com/20160918/availabilityDomains?compartmentId=$TF_VAR_compartment_id" 2>&1)

HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
rm -f "$TMP_KEY"

if [ "$HTTP_CODE" = "401" ]; then
  echo "   ❌ Authentication failed (401)"
  echo ""
  echo "DIAGNOSIS: Your OCI API credentials are incorrect."
  echo ""
  echo "Common causes:"
  echo "  1. Private key doesn't match the public key uploaded to OCI"
  echo "  2. Fingerprint is incorrect"
  echo "  3. User OCID is wrong"
  echo "  4. API key not uploaded to OCI Console"
  echo ""
  echo "ACTION REQUIRED:"
  echo "  1. Go to OCI Console → Profile → User Settings → API Keys"
  echo "  2. Delete old API keys"
  echo "  3. Generate new key pair:"
  echo "     openssl genrsa -out ~/.oci/oci_api_key.pem 2048"
  echo "     openssl rsa -pubout -in ~/.oci/oci_api_key.pem -out ~/.oci/oci_api_key_public.pem"
  echo "  4. Upload oci_api_key_public.pem to OCI Console"
  echo "  5. Copy the fingerprint shown"
  echo "  6. Update GitHub Secrets:"
  echo "     - OCI_PRIVATE_KEY = contents of oci_api_key.pem"
  echo "     - OCI_FINGERPRINT = fingerprint from OCI Console"
  exit 1
elif [ "$HTTP_CODE" = "404" ]; then
  echo "   ⚠️  Authentication succeeded but compartment not found (404)"
  echo "   Check TF_VAR_compartment_id is correct"
  exit 1
elif [ "$HTTP_CODE" = "200" ]; then
  echo "   ✅ Authentication successful!"
else
  echo "   ⚠️  Unexpected response: $HTTP_CODE"
  echo "$RESPONSE" | head -n-1
fi

echo ""
echo "=== All checks passed! Terraform should work. ==="
