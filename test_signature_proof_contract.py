#!/usr/bin/env python3
"""
Test Signature Proof Module Against Running Anvil Contract

This script tests the complete flow:
1. Connect to Anvil blockchain
2. Deploy or use existing DstackMembershipNFT contract
3. Generate signature proofs using DStack
4. Call contract functions with the proofs
5. Verify the results
"""

import asyncio
import logging
import sys
import os
import json

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from signature_proof import SignatureProofGenerator
from web3 import Web3
from eth_account import Account

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Contract ABI for DstackMembershipNFT
CONTRACT_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "_kmsRootAddress", "type": "address"}
        ],
        "stateMutability": "nonpayable",
        "type": "constructor"
    },
    {
        "inputs": [
            {"internalType": "bytes32", "name": "instanceId", "type": "bytes32"},
            {"internalType": "uint256", "name": "tokenId", "type": "uint256"},
            {"internalType": "bytes", "name": "derivedPublicKey", "type": "bytes"},
            {"internalType": "bytes", "name": "appSignature", "type": "bytes"},
            {"internalType": "bytes", "name": "kmsSignature", "type": "bytes"},
            {"internalType": "string", "name": "purpose", "type": "string"}
        ],
        "name": "registerInstanceWithProof",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "address", "name": "wallet", "type": "address"}],
        "name": "walletToTokenId",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "updateClusterSize",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]

class ContractSignatureProofTester:
    """Tests signature proof generation and contract integration"""
    
    def __init__(self, rpc_url: str = "http://localhost:8545", 
                 contract_address: str = None, private_key: str = None):
        self.rpc_url = rpc_url
        self.contract_address = contract_address
        self.private_key = private_key
        
        # Initialize Web3
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        if not self.w3.is_connected():
            raise RuntimeError(f"Failed to connect to {rpc_url}")
        
        # Initialize account
        if private_key:
            self.account = Account.from_key(private_key)
            self.wallet_address = self.account.address
        else:
            # Use first Anvil account
            self.account = Account.from_key("0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80")
            self.wallet_address = self.account.address
        
        logger.info(f"Using wallet: {self.wallet_address}")
        
        # Initialize contract
        if contract_address:
            self.contract = self.w3.eth.contract(
                address=contract_address, 
                abi=CONTRACT_ABI
            )
            logger.info(f"Using existing contract: {contract_address}")
        else:
            self.contract = None
            logger.info("No contract address provided, will deploy new one")
        
        # Initialize signature proof generator
        self.proof_generator = SignatureProofGenerator()
    
    def deploy_contract(self, kms_root_address: str = None) -> str:
        """Deploy a new DstackMembershipNFT contract"""
        if not kms_root_address:
            # Use a mock KMS root address (first Anvil account)
            kms_root_address = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"
        
        logger.info(f"Deploying contract with KMS root: {kms_root_address}")
        
        # Contract bytecode (you'll need to compile this)
        # For now, we'll use a placeholder - you'll need to get the actual bytecode
        logger.warning("Contract deployment requires compiled bytecode")
        logger.warning("Please deploy using Foundry and provide the address")
        
        return None
    
    def test_signature_proof_generation(self):
        """Test signature proof generation with DStack"""
        logger.info("Testing signature proof generation...")
        
        try:
            # Test DStack connection
            dstack_info = self.proof_generator.get_dstack_info()
            logger.info(f"DStack Info: {dstack_info}")
            
            if not dstack_info['available']:
                raise RuntimeError("DStack not available")
            
            # Generate proof
            proof = self.proof_generator.generate_proof(
                "test-contract-node", 
                "test/contract", 
                "ethereum"
            )
            
            logger.info("✅ Signature proof generated successfully")
            logger.info(f"  Instance ID: {proof.instance_id_bytes32.hex()}")
            logger.info(f"  Public Key: {proof.derived_public_key.hex()}")
            logger.info(f"  App Signature: {proof.app_signature.hex()}")
            logger.info(f"  KMS Signature: {proof.kms_signature.hex()}")
            logger.info(f"  Purpose: {proof.purpose}")
            logger.info(f"  App ID: {proof.app_id.hex()}")
            
            # Verify proof format
            is_valid = self.proof_generator.verify_proof_format(proof)
            if not is_valid:
                raise RuntimeError("Proof format validation failed")
            
            logger.info("✅ Proof format validation passed")
            return proof
            
        except Exception as e:
            logger.error(f"❌ Signature proof generation failed: {e}")
            raise
    
    def test_contract_registration(self, proof):
        """Test contract registration with the generated proof"""
        if not self.contract:
            logger.warning("No contract available, skipping registration test")
            return False
        
        logger.info("Testing contract registration...")
        
        try:
            # Get token ID for this wallet
            token_id = self.contract.functions.walletToTokenId(self.wallet_address).call()
            if token_id == 0:
                logger.warning("No NFT found for this wallet, minting one first...")
                # You might need to mint an NFT first
                return False
            
            logger.info(f"Found NFT token ID: {token_id}")
            
            # Prepare registration data
            registration_data = {
                'instanceId': proof.instance_id_bytes32,
                'tokenId': token_id,
                'derivedPublicKey': proof.derived_public_key,
                'appSignature': proof.app_signature,
                'kmsSignature': proof.kms_signature,
                'purpose': proof.purpose,
                'appId': proof.app_id  # Add app_id
            }
            
            logger.info("Registration data prepared:")
            for key, value in registration_data.items():
                if isinstance(value, bytes):
                    logger.info(f"  {key}: {value.hex()}")
                else:
                    logger.info(f"  {key}: {value}")
            
            # Build transaction
            tx = self.contract.functions.registerInstanceWithProof(
                registration_data['instanceId'],
                registration_data['tokenId'],
                registration_data['derivedPublicKey'],
                registration_data['appSignature'],
                registration_data['kmsSignature'],
                registration_data['purpose']
            ).build_transaction({
                'from': self.wallet_address,
                'gas': 500000,
                'nonce': self.w3.eth.get_transaction_count(self.wallet_address)
            })
            
            # Sign and send transaction
            signed_tx = self.account.sign_transaction(tx)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            
            logger.info(f"Transaction sent: {tx_hash.hex()}")
            
            # Wait for receipt
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            
            if receipt.status == 1:
                logger.info("✅ Contract registration successful!")
                return True
            else:
                logger.error("❌ Contract registration failed")
                return False
                
        except Exception as e:
            logger.error(f"❌ Contract registration test failed: {e}")
            raise
    
    def run_full_test(self):
        """Run the complete test suite"""
        logger.info("Starting Contract Signature Proof Test")
        logger.info("=" * 50)
        
        try:
            # Test 1: Signature proof generation
            proof = self.test_signature_proof_generation()
            
            # Test 2: Contract registration (if contract available)
            if self.contract:
                success = self.test_contract_registration(proof)
                if success:
                    logger.info("🎉 All tests passed!")
                else:
                    logger.warning("⚠️  Some tests had issues")
            else:
                logger.info("ℹ️  Contract not available, skipping registration test")
                logger.info("✅ Signature proof generation test passed!")
            
        except Exception as e:
            logger.error(f"❌ Test suite failed: {e}")
            import traceback
            traceback.print_exc()
            return False
        
        return True

async def main():
    """Main test function"""
    # Check if contract address is provided
    contract_address = os.environ.get('CONTRACT_ADDRESS')
    
    if not contract_address:
        logger.warning("No CONTRACT_ADDRESS environment variable found")
        logger.warning("Will only test signature proof generation")
        logger.warning("To test contract integration, set CONTRACT_ADDRESS")
    
    # Create tester
    tester = ContractSignatureProofTester(
        contract_address=contract_address
    )
    
    # Run tests
    success = tester.run_full_test()
    
    if success:
        print("\n✅ Test completed successfully!")
    else:
        print("\n❌ Test failed!")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
