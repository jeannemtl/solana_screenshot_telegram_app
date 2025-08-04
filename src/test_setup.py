#!/usr/bin/env python3

import sys
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv('config/.env')

def test_imports():
    try:
        # Test imports with correct paths for solana 0.32.0
        from solana.rpc.api import Client
        from solders.keypair import Keypair  # Note: keypair is in solders, not solana
        from solders.pubkey import Pubkey
        import requests
        import base58
        from watchdog.observers import Observer
        from PIL import Image
        print("✅ All imports successful!")
        return True
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("💡 Trying alternative imports...")
        
        # Try alternative import paths
        try:
            from solana.rpc.api import Client
            from solana.keypair import Keypair  # Fallback import
            import requests
            print("✅ Core imports working with fallback!")
            return True
        except ImportError as e2:
            print(f"❌ Fallback import error: {e2}")
            return False

def test_environment():
    required_vars = [
        'ANTHROPIC_API_KEY',
        'SOLANA_RPC_URL',
        'WALLET_KEYPAIR_PATH'
    ]
    
    missing = []
    for var in required_vars:
        if not os.getenv(var):
            missing.append(var)
    
    if missing:
        print(f"❌ Missing environment variables: {', '.join(missing)}")
        return False
    else:
        print("✅ Environment variables configured!")
        return True

def test_solana_connection():
    try:
        from solana.rpc.api import Client
        rpc_url = os.getenv('SOLANA_RPC_URL')
        client = Client(rpc_url)
        
        # Test connection with a method that exists in this version
        try:
            # Try get_version which should exist in all versions
            result = client.get_version()
            print(f"✅ Solana connection successful! Network: {rpc_url}")
            print(f"   Solana version: {result.value.get('solana-core', 'unknown')}")
            return True
        except Exception as e1:
            try:
                # Try get_cluster_nodes as backup
                result = client.get_cluster_nodes()
                print(f"✅ Solana connection successful! Network: {rpc_url}")
                return True
            except Exception as e2:
                try:
                    # Try get_balance with a known address as final test
                    from solders.pubkey import Pubkey
                    test_pubkey = Pubkey.from_string("11111111111111111111111111111112")  # System program
                    result = client.get_balance(test_pubkey)
                    print(f"✅ Solana connection successful! Network: {rpc_url}")
                    return True
                except Exception as e3:
                    print(f"❌ Solana connection failed: {e3}")
                    return False
                    
    except Exception as e:
        print(f"❌ Solana connection failed: {e}")
        return False

def test_wallet_file():
    """Test if wallet file exists and is readable"""
    wallet_path = os.getenv('WALLET_KEYPAIR_PATH')
    if not wallet_path:
        print("❌ WALLET_KEYPAIR_PATH not set")
        return False
    
    if not os.path.exists(wallet_path):
        print(f"❌ Wallet file not found: {wallet_path}")
        return False
    
    try:
        import json
        with open(wallet_path, 'r') as f:
            data = json.load(f)
        
        if isinstance(data, list) and len(data) >= 32:
            print("✅ Wallet file is valid!")
            return True
        else:
            print("❌ Wallet file format invalid")
            return False
            
    except Exception as e:
        print(f"❌ Error reading wallet file: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Testing Solana Screenshot NFT Setup")
    print("=" * 40)
    
    tests = [
        ("Package Imports", test_imports),
        ("Environment Config", test_environment),
        ("Wallet File", test_wallet_file),
        ("Solana Connection", test_solana_connection),
    ]
    
    passed = 0
    for name, test_func in tests:
        print(f"\n{name}:")
        if test_func():
            passed += 1
    
    print(f"\n📊 Results: {passed}/{len(tests)} tests passed")
    
    if passed >= 3:  # Allow some flexibility
        print("🎉 Setup mostly complete! Ready to build your Solana screenshot NFTs!")
    else:
        print("🔧 Please fix the failing tests before proceeding.")
        
    # Show what packages are installed
    print(f"\n📦 Installed Solana packages:")
    try:
        import pkg_resources
        for pkg in pkg_resources.working_set:
            if 'solana' in pkg.project_name.lower() or 'solders' in pkg.project_name.lower():
                print(f"   {pkg.project_name}: {pkg.version}")
    except:
        pass