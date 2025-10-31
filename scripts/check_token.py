#!/usr/bin/env python3
"""
Script para verificar el token OAuth2 y sus claims
"""
import sys
import os
import jwt
import json

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.oauth import MS365OAuth
from src.config import Config

def decode_token(token):
    """Decode JWT token without verification to see claims"""
    try:
        # Decode without verification (just to see claims)
        decoded = jwt.decode(token, options={"verify_signature": False})
        return decoded
    except Exception as e:
        print(f"Error decoding token: {e}")
        return None

def main():
    print("=" * 60)
    print("Verificación de Token OAuth2")
    print("=" * 60)
    print()
    
    # Initialize OAuth
    oauth = MS365OAuth()
    
    # Get token
    print("Adquiriendo token...")
    try:
        token = oauth.get_access_token()
        print(f"✅ Token adquirido exitosamente")
        print(f"   Longitud: {len(token)} caracteres")
        print()
        
        # Decode token
        print("Decodificando claims del token...")
        claims = decode_token(token)
        
        if claims:
            print("\n📋 Claims importantes:")
            print(f"   App ID (appid): {claims.get('appid', 'N/A')}")
            print(f"   Tenant ID (tid): {claims.get('tid', 'N/A')}")
            print(f"   Audience (aud): {claims.get('aud', 'N/A')}")
            print(f"   Issuer (iss): {claims.get('iss', 'N/A')}")
            print(f"   Subject (sub): {claims.get('sub', 'N/A')}")
            print(f"   Identity Type (idtyp): {claims.get('idtyp', 'N/A')}")
            
            # Check if it's app-only or delegated
            if 'upn' in claims or 'unique_name' in claims:
                print(f"\n   🔹 Token type: DELEGATED (user context)")
                print(f"   User: {claims.get('upn') or claims.get('unique_name', 'N/A')}")
            else:
                print(f"\n   🔹 Token type: APP-ONLY (application context)")
            
            # Roles and scopes
            if 'roles' in claims:
                print(f"\n   Application Roles: {claims.get('roles')}")
            if 'scp' in claims:
                print(f"   Delegated Scopes: {claims.get('scp')}")
            
            # Expiration
            import datetime
            if 'exp' in claims:
                exp_time = datetime.datetime.fromtimestamp(claims['exp'])
                print(f"\n   Expira: {exp_time}")
            
            # Full claims (debug)
            print(f"\n📄 Todos los claims:")
            print(json.dumps(claims, indent=2))
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == '__main__':
    sys.exit(main())
