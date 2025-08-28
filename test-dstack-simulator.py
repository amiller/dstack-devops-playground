#!/usr/bin/env python3
"""
Test script for dstack simulator integration
"""

import dstack_sdk
import asyncio

def test_sync_client():
    """Test synchronous dstack client"""
    print("=== Testing Synchronous Dstack Client ===")
    
    # Connect to local simulator
    client = dstack_sdk.DstackClient('./simulator/dstack.sock')
    
    try:
        # Get service info
        info = client.info()
        print(f"✅ Connected to simulator")
        print(f"   App ID: {info.app_id}")
        print(f"   Instance ID: {info.instance_id}")
        print(f"   App Name: {info.app_name}")
        
        # Test key derivation
        key = client.get_key('wallet/ethereum', 'mainnet')
        print(f"✅ Key derivation successful")
        print(f"   Key length: {len(key.decode_key())} bytes")
        print(f"   Signature chain: {len(key.signature_chain)} items")
        
        # Test quote generation
        quote = client.get_quote(b'test-attestation-data')
        print(f"✅ Quote generation successful")
        print(f"   Quote length: {len(quote.quote)} bytes")
        print(f"   Event log length: {len(quote.event_log)} bytes")
        
        # Test reachability
        if client.is_reachable():
            print("✅ Service is reachable")
        else:
            print("❌ Service is not reachable")
            
    except Exception as e:
        print(f"❌ Error: {e}")

async def test_async_client():
    """Test asynchronous dstack client"""
    print("\n=== Testing Asynchronous Dstack Client ===")
    
    # Connect to local simulator
    client = dstack_sdk.AsyncDstackClient('./simulator/dstack.sock')
    
    try:
        # Get service info
        info = await client.info()
        print(f"✅ Connected to simulator (async)")
        print(f"   App ID: {info.app_id}")
        print(f"   Instance ID: {info.instance_id}")
        print(f"   App Name: {info.app_name}")
        
        # Test concurrent operations
        print("✅ Testing concurrent operations...")
        tasks = [
            client.get_key('wallet/btc', 'mainnet'),
            client.get_key('wallet/eth', 'mainnet'),
            client.get_key('signing/key', 'production')
        ]
        
        keys = await asyncio.gather(*tasks)
        for i, key in enumerate(keys):
            print(f"   Key {i+1}: {len(key.decode_key())} bytes")
            
    except Exception as e:
        print(f"❌ Error: {e}")

def main():
    """Main test function"""
    print("🚀 Testing Dstack Simulator Integration\n")
    
    # Test synchronous client
    test_sync_client()
    
    # Test asynchronous client
    asyncio.run(test_async_client())
    
    print("\n✅ All tests completed!")

if __name__ == "__main__":
    main()
