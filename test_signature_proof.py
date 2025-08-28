#!/usr/bin/env python3
"""
Test script for signature proof generation and verification

This script tests the core signature proof functionality without the complexity
of the distributed counter application.
"""

import asyncio
import logging
import sys
import os

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from signature_proof import SignatureProofGenerator, test_signature_proof

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def main():
    """Main test function"""
    print("Testing Signature Proof Module")
    print("=" * 40)
    
    try:
        # Test basic functionality
        await test_signature_proof()
        
        # Additional tests
        print("\nAdditional Tests:")
        print("-" * 20)
        
        # Test DStack connection
        generator = SignatureProofGenerator()
        dstack_info = generator.get_dstack_info()
        print(f"DStack Connection: {dstack_info}")
        
        if dstack_info['available']:
            # Test proof generation with specific parameters
            try:
                proof = generator.generate_proof("test-instance", "test/node", "ethereum")
                print(f"Proof Generation: SUCCESS")
                print(f"  Instance ID: {proof.instance_id_bytes32.hex()}")
                print(f"  Public Key: {proof.derived_public_key.hex()}")
                print(f"  App Signature Length: {len(proof.app_signature)}")
                print(f"  KMS Signature Length: {len(proof.kms_signature)}")
                print(f"  Purpose: {proof.purpose}")
                print(f"  App ID: {proof.app_id}")
                
                # Test proof format verification
                is_valid = generator.verify_proof_format(proof)
                print(f"Proof Format Validation: {'PASS' if is_valid else 'FAIL'}")
                
            except Exception as e:
                print(f"Proof Generation: FAILED - {e}")
        else:
            print("DStack not available - skipping proof generation tests")
        
        print("\nTest completed!")
        
    except Exception as e:
        print(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
