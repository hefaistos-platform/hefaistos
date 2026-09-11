#!/bin/bash
# MISP Integration Quick Troubleshooting Script
# Run this to diagnose and fix MISP integration issues

set -e

echo "════════════════════════════════════════════════════════════════════"
echo "HEFAISTOS MISP INTEGRATION QUICK FIX"
echo "════════════════════════════════════════════════════════════════════"
echo ""

# Check if docker compose is running
if ! docker compose ps backend | grep -q running; then
    echo "❌ Backend is not running. Starting containers..."
    docker compose up -d backend
    sleep 2
fi

echo "📋 STEP 1: Check Configuration"
echo "────────────────────────────────────────────────────────────────────"
docker compose exec backend python manage.py misp_setup_guide
echo ""

echo "⚠️  STEP 2: Get Your API Key"
echo "────────────────────────────────────────────────────────────────────"
echo "1. Open in browser: https://misp.counterintel.cz"
echo "2. Log in with your credentials"
echo "3. Click your username → Profile"
echo "4. Copy the 'Authkey' field (40 characters)"
echo ""

read -p "Enter your MISP Authkey (or press Enter to skip): " authkey

if [ -n "$authkey" ]; then
    echo ""
    echo "🧪 STEP 3: Testing Your API Key"
    echo "────────────────────────────────────────────────────────────────────"
    docker compose exec backend python manage.py test_misp_key --key "$authkey"
    echo ""
    
    # Ask if key is valid
    read -p "Is the key valid? (y/n): " is_valid
    
    if [ "$is_valid" = "y" ] || [ "$is_valid" = "Y" ]; then
        echo ""
        echo "✅ Key is valid! Now updating your configuration..."
        echo ""
        echo "📝 STEP 4: Update Configuration"
        echo "────────────────────────────────────────────────────────────────────"
        echo "Update MISP_API_KEY in one of these files:"
        echo "  1. docker-compose.yml"
        echo "  2. .env file"
        echo "  3. docker-compose.override.yml"
        echo ""
        echo "Set: MISP_API_KEY=$authkey"
        echo ""
        
        read -p "Have you updated the configuration file? (y/n): " updated
        
        if [ "$updated" = "y" ] || [ "$updated" = "Y" ]; then
            echo ""
            echo "🔄 Restarting backend..."
            docker compose restart backend
            sleep 3
            
            echo ""
            echo "🧪 STEP 5: Verify Integration"
            echo "────────────────────────────────────────────────────────────────────"
            docker compose exec backend python manage.py test_misp_diagnostic
            
            echo ""
            echo "✅ Setup complete!"
            echo ""
            echo "Next: Try the PUSH 2 MISP button in the Hefaistos UI"
            echo "You should see: 'Hunt pushed to MISP (Event #XXXX)'"
        fi
    else
        echo ""
        echo "❌ Key is invalid. Please try again:"
        echo "  1. Double-check you copied the correct Authkey from MISP"
        echo "  2. Verify the user account is enabled in MISP"
        echo "  3. Check user has API permissions enabled"
        echo ""
        echo "Run this script again with a different key."
    fi
else
    echo ""
    echo "⏭️  Skipped API key test"
    echo ""
    echo "To complete setup later, run:"
    echo "  docker compose exec backend python manage.py test_misp_key --key YOUR_KEY"
fi

echo ""
echo "════════════════════════════════════════════════════════════════════"
echo "For detailed instructions, see: Docs/MISP_API_KEY_VERIFICATION.md"
echo "════════════════════════════════════════════════════════════════════"
