#!/usr/bin/env python3
"""
Signature Proof Generation and Verification Module

This module handles the core logic for generating and verifying signature chain proofs
for DStack TEE attestation, separate from the distributed counter application logic.
"""

import asyncio
import hashlib
import logging
from typing import Optional, Tuple, Dict, Any
from dataclasses import dataclass

try:
    from dstack_sdk import DstackClient
    DSTACK_AVAILABLE = True
except ImportError:
    DSTACK_AVAILABLE = False
    DstackClient = None

try:
    from eth_account import Account
    from web3 import Web3
    from web3.types import bytes32
except ImportError:
    # Fallback for older web3 versions
    try:
        from web3.types import bytes32
    except ImportError:
        bytes32 = bytes

logger = logging.getLogger(__name__)

@dataclass
class SignatureProof:
    """Container for signature chain proof components"""
    instance_id_bytes32: bytes
    derived_public_key: bytes
    app_signature: bytes
    kms_signature: bytes
    purpose: str
    app_id: bytes

@dataclass
class RegistrationData:
    """Container for registration data"""
    token_id: int
    instance_id_bytes32: bytes
    derived_public_key: bytes
    app_signature: bytes
    kms_signature: bytes
    purpose: str

class SignatureProofGenerator:
    """Handles generation and verification of signature chain proofs"""
    
    def __init__(self, dstack_socket: str = None):
        if not DSTACK_AVAILABLE:
            raise RuntimeError("DStack SDK is required but not available")
        
        self.dstack_socket = dstack_socket or './simulator/dstack.sock'
        self.dstack_client = DstackClient(self.dstack_socket)
    
    def generate_proof(self, instance_id: str, key_path: str, 
                      key_purpose: str = "ethereum") -> SignatureProof:
        """
        Generate a complete signature chain proof for an instance
        
        Args:
            instance_id: String identifier for the instance
            key_path: DStack key derivation path
            key_purpose: Purpose for key derivation
            
        Returns:
            SignatureProof object containing all proof components
        """
        # Convert instance ID to bytes32
        instance_hash = hashlib.sha256(instance_id.encode()).digest()
        instance_id_bytes32 = bytes32(instance_hash)
        
        # Get signature chain proof from DStack
        key_response = self.dstack_client.get_key(key_path, key_purpose)
        
        # Extract signature chain components
        derived_private_key = key_response.key
        signature_chain = key_response.signature_chain
        
        if len(signature_chain) < 2:
            raise RuntimeError(f"Insufficient signature chain length: {len(signature_chain)}")
        
        app_signature = signature_chain[0]
        kms_signature = signature_chain[1]
        
        # Ensure signatures are in bytes format
        if isinstance(app_signature, str):
            app_signature = bytes.fromhex(app_signature.replace('0x', ''))
        if isinstance(kms_signature, str):
            kms_signature = bytes.fromhex(kms_signature.replace('0x', ''))
        
        # Get public key from private key
        account = Account.from_key(derived_private_key)
        derived_public_key_bytes = bytes.fromhex(account.address[2:])
        
        # Get app ID from dstack client
        info = self.dstack_client.info()
        app_id = info.app_id
        
        # Convert app_id to bytes32 (remove 0x prefix and pad to 32 bytes)
        app_id_bytes = bytes.fromhex(app_id[2:])  # Remove 0x prefix
        app_id_bytes32 = app_id_bytes.ljust(32, b'\x00')  # Pad to 32 bytes
        
        return SignatureProof(
            instance_id_bytes32=instance_id_bytes32,
            derived_public_key=derived_public_key_bytes,
            app_signature=app_signature,
            kms_signature=kms_signature,
            purpose=key_purpose,
            app_id=app_id_bytes32  # Store as bytes32
        )
    
    def get_registration_data(self, contract: Any, wallet_address: str, 
                            instance_id: str, key_path: str, 
                            key_purpose: str = "ethereum") -> RegistrationData:
        """
        Get complete registration data including NFT token ID
        
        Args:
            contract: Web3 contract instance
            wallet_address: Ethereum wallet address
            instance_id: String identifier for the instance
            key_path: DStack key derivation path
            key_purpose: Purpose for key derivation
            
        Returns:
            RegistrationData object ready for contract registration
        """
        # Get token ID for this wallet
        token_id = contract.functions.walletToTokenId(wallet_address).call()
        if token_id == 0:
            raise RuntimeError(f"No NFT found for wallet {wallet_address}")
        
        # Generate signature proof
        proof = self.generate_proof(instance_id, key_path, key_purpose)
        
        return RegistrationData(
            token_id=token_id,
            instance_id_bytes32=proof.instance_id_bytes32,
            derived_public_key=proof.derived_public_key,
            app_signature=proof.app_signature,
            kms_signature=proof.kms_signature,
            purpose=proof.purpose
        )
    
    def verify_proof_format(self, proof: SignatureProof) -> bool:
        """
        Verify that a proof has the correct format and components
        
        Args:
            proof: SignatureProof object to verify
            
        Returns:
            True if proof format is valid
        """
        try:
            # Check instance ID is 32 bytes
            if len(proof.instance_id_bytes32) != 32:
                logger.error(f"Invalid instance_id_bytes32 length: {len(proof.instance_id_bytes32)}")
                return False
            
            # Check public key is 20 bytes (Ethereum address)
            if len(proof.derived_public_key) != 20:
                logger.error(f"Invalid derived_public_key length: {len(proof.derived_public_key)}")
                return False
            
            # Check signatures are reasonable lengths (at least 65 bytes for ECDSA)
            if len(proof.app_signature) < 65:
                logger.error(f"App signature too short: {len(proof.app_signature)}")
                return False
            
            if len(proof.kms_signature) < 65:
                logger.error(f"KMS signature too short: {len(proof.kms_signature)}")
                return False
            
            # Check purpose is not empty
            if not proof.purpose or len(proof.purpose) == 0:
                logger.error("Purpose is empty")
                return False
            
            # Check app ID is not empty
            if not proof.app_id or len(proof.app_id) == 0:
                logger.error("App ID is empty")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Proof format verification failed: {e}")
            return False
    
    def get_dstack_info(self) -> Dict[str, Any]:
        """Get DStack client information for debugging"""
        try:
            info = self.dstack_client.info()
            return {
                'app_id': info.app_id,
                'socket': self.dstack_socket,
                'available': True
            }
        except Exception as e:
            return {
                'error': str(e),
                'socket': self.dstack_socket,
                'available': False
            }

async def test_signature_proof():
    """Test function for signature proof generation"""
    try:
        generator = SignatureProofGenerator()
        
        # Test DStack connection
        dstack_info = generator.get_dstack_info()
        print(f"DStack Info: {dstack_info}")
        
        if not dstack_info['available']:
            print("DStack not available, skipping proof generation test")
            return
        
        # Test proof generation
        proof = generator.generate_proof("test-node", "test/path", "ethereum")
        print(f"Generated proof: {proof}")
        
        # Test proof format verification
        is_valid = generator.verify_proof_format(proof)
        print(f"Proof format valid: {is_valid}")
        
        print("Signature proof test completed successfully!")
        
    except Exception as e:
        print(f"Signature proof test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_signature_proof())
