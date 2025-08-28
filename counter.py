#!/usr/bin/env python3
"""
Distributed Counter Service with NFT-based Membership and Byzantine Fault Tolerance

This application demonstrates:
- NFT-based node authorization
- Byzantine fault tolerant leader election
- Distributed consensus for counter operations
- Automatic failover when leader becomes unresponsive
- DStack integration for secure key derivation
"""

import asyncio
import logging
import argparse
import json
from typing import Dict, Any, Optional

try:
    from dstack_sdk import DstackClient
    DSTACK_AVAILABLE = True
except ImportError:
    DSTACK_AVAILABLE = False

try:
    from web3 import Web3
    from web3.middleware.proof_of_authority import ExtraDataToPOAMiddleware as geth_poa_middleware
    from eth_account import Account
    from web3.types import bytes32
except ImportError:
    # Fallback for older web3 versions
    try:
        from web3.types import bytes32
    except ImportError:
        bytes32 = bytes

# Import our signature proof module
from signature_proof import SignatureProofGenerator, RegistrationData

logger = logging.getLogger(__name__)

class DistributedCounter:
    def __init__(self, instance_id: str, contract_address: str = None, 
                 rpc_url: str = "http://localhost:8545", 
                 port: int = 8080, dstack_socket: str = None,
                 dstack_key_path: str = None, dstack_key_purpose: str = None):
        self.instance_id = instance_id
        self.port = port
        self.dstack_socket = dstack_socket
        self.dstack_key_path = dstack_key_path or f"node/{instance_id}"
        self.dstack_key_purpose = dstack_key_purpose or "ethereum"
        
        # Initialize DStack wallet (required for signature chain verification)
        self._init_dstack_wallet()
        
        # Web3 setup
        if not contract_address:
            raise ValueError("contract_address is required")
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        self.w3.middleware_onion.inject(geth_poa_middleware, layer=0)
        self.contract_address = contract_address
        
        # Counter state
        self.counter_value = 0
        self.operation_log = []
        self.is_leader = False
        self.last_leader_heartbeat = 0
        
        # Instance registration state
        self.token_id = None
        self.instance_id_bytes32 = bytes32(0)
        
        # Contract ABI (simplified for demo)
        self.contract_abi = [
            {"inputs": [], "name": "currentLeader", "outputs": [{"type": "address"}], "stateMutability": "view", "type": "function"},
            {"inputs": [], "name": "totalActiveNodes", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
            {"inputs": [], "name": "requiredVotes", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
            {"inputs": [{"type": "address"}, {"type": "bool"}], "name": "castVote", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
            {"inputs": [], "name": "electLeader", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
            {"inputs": [], "name": "getActiveInstances", "outputs": [{"type": "bytes32[]"}], "stateMutability": "view", "type": "function"},
            {"inputs": [{"type": "bytes32"}, {"type": "uint256"}], "name": "registerInstance", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
            {"inputs": [{"type": "bytes32"}, {"type": "uint256"}, {"type": "bytes"}, {"type": "bytes"}, {"type": "bytes"}, {"type": "string"}], "name": "registerInstanceWithProof", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
            {"inputs": [{"type": "address"}], "name": "walletToTokenId", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
            {"inputs": [], "name": "updateClusterSize", "outputs": [], "stateMutability": "nonpayable", "type": "function"}
        ]
        
        self.contract = self.w3.eth.contract(address=contract_address, abi=self.contract_abi)
        
        # HTTP client for inter-node communication
        self.http_client = None
        
        # Background tasks
        self.leader_monitor_task = None
        self.heartbeat_task = None
        
    def _init_dstack_wallet(self):
        """Initialize wallet using dstack-sdk for key derivation"""
        try:
            logger.info(f"Initializing dstack wallet with path: {self.dstack_key_path}, purpose: {self.dstack_key_purpose}")
            
            # Create dstack client
            if self.dstack_socket:
                self.dstack_client = DstackClient(self.dstack_socket)
            else:
                # Try to auto-detect socket
                if os.path.exists('./simulator/dstack.sock'):
                    self.dstack_client = DstackClient('./simulator/dstack.sock')
                else:
                    raise ValueError("No dstack socket specified and ./simulator/dstack.sock not found")
            
            # Test connection
            info = self.dstack_client.info()
            logger.info(f"Connected to dstack: {info.app_name} (ID: {info.app_id})")
            
            # Derive key
            key_response = self.dstack_client.get_key(self.dstack_key_path, self.dstack_key_purpose)
            private_key_bytes = key_response.decode_key()
            
            # Convert to eth_account
            from dstack_sdk.ethereum import to_account_secure
            self.account = to_account_secure(key_response)
            self.wallet_address = self.account.address
            
            logger.info(f"DStack wallet initialized: {self.wallet_address}")
            logger.info(f"Key derived from path: {self.dstack_key_path}, purpose: {self.dstack_key_purpose}")
            
        except Exception as e:
            logger.error(f"Failed to initialize dstack wallet: {e}")
            raise RuntimeError(f"DStack wallet initialization failed: {e}")
    
    def get_wallet_info(self):
        """Get wallet information for debugging"""
        return {
            'type': 'dstack',
            'address': self.wallet_address,
            'key_path': self.dstack_key_path,
            'key_purpose': self.dstack_key_purpose,
            'socket': self.dstack_socket or './simulator/dstack.sock'
        }
    
    async def register_instance(self):
        """Register instance using signature chain verification"""
        logger.info("Registering instance with signature chain verification...")
        
        try:
            # Use signature proof generator
            proof_generator = SignatureProofGenerator(self.dstack_socket)
            
            # Get registration data
            registration_data = proof_generator.get_registration_data(
                self.contract,
                self.wallet_address,
                self.instance_id,
                self.dstack_key_path,
                self.dstack_key_purpose
            )
            
            # Store for later use
            self.token_id = registration_data.token_id
            self.instance_id_bytes32 = registration_data.instance_id_bytes32
            
            # Call enhanced registration
            tx = self.contract.functions.registerInstanceWithProof(
                registration_data.instance_id_bytes32,
                registration_data.token_id,
                registration_data.derived_public_key,
                registration_data.app_signature,
                registration_data.kms_signature,
                registration_data.purpose
            ).build_transaction({
                'from': self.wallet_address,
                'gas': 500000,
                'nonce': self.w3.eth.get_transaction_count(self.wallet_address)
            })
            
            signed_tx = self.account.sign_transaction(tx)
            
            # Handle different Web3.py versions
            if hasattr(signed_tx, 'rawTransaction'):
                raw_tx = signed_tx.rawTransaction
            elif hasattr(signed_tx, 'raw_transaction'):
                raw_tx = signed_tx.raw_transaction
            else:
                raw_tx = signed_tx.rawTransaction if hasattr(signed_tx, 'rawTransaction') else signed_tx.raw_transaction
            
            tx_hash = self.w3.eth.send_raw_transaction(raw_tx)
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            
            if receipt.status == 1:
                logger.info(f"Instance registered with attestation proof: {tx_hash.hex()}")
            else:
                raise RuntimeError("Registration with proof failed")
            
            # Update cluster size
            try:
                self.contract.functions.updateClusterSize().call()
                logger.info("Cluster size updated")
            except Exception as e:
                logger.warning(f"Failed to update cluster size: {e}")
                
        except Exception as e:
            logger.error(f"Registration failed: {e}")
            raise
    
    async def start(self):
        """Start the counter service"""
        logger.info(f"Starting distributed counter on port {self.port}")
        
        # Initialize HTTP client
        self.http_client = aiohttp.ClientSession()
        
        # Start background tasks
        self.leader_monitor_task = asyncio.create_task(self.monitor_leader_health())
        self.heartbeat_task = asyncio.create_task(self.leader_heartbeat())
        
        # Start HTTP server
        app = web.Application()
        app.router.add_get('/counter', self.get_counter)
        app.router.add_post('/increment', self.increment_counter)
        app.router.add_get('/log', self.get_log)
        app.router.add_get('/status', self.get_status)
        app.router.add_get('/members', self.get_members)
        app.router.add_get('/health', self.health_check)
        app.router.add_get('/wallet-info', self.get_wallet_info_endpoint)
        
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', self.port)
        await site.start()
        
        logger.info(f"Counter service started on port {self.port}")
        
        # Register this instance
        await self.register_instance()
        
        # Keep running
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("Shutting down...")
        finally:
            await self.cleanup()
    
    async def cleanup(self):
        """Clean up resources"""
        if self.leader_monitor_task:
            self.leader_monitor_task.cancel()
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
        if self.http_client:
            await self.http_client.close()
    
    async def monitor_leader_health(self):
        """Monitor leader health and participate in consensus"""
        while True:
            try:
                await self.check_leader_status()
                await asyncio.sleep(10)  # Check every 10 seconds
            except Exception as e:
                logger.error(f"Error in leader monitoring: {e}")
                await asyncio.sleep(5)
    
    async def check_leader_status(self):
        """Check current leader status and participate in consensus"""
        try:
            current_leader = self.contract.functions.currentLeader().call()
            
            if current_leader == self.wallet_address:
                # I am the leader
                if not self.is_leader:
                    logger.info("I am now the leader!")
                    self.is_leader = True
            else:
                # I am not the leader
                if self.is_leader:
                    logger.info("I am no longer the leader")
                    self.is_leader = False
                
                # Check if leader is responsive
                if current_leader != '0x0000000000000000000000000000000000000000':
                    is_responsive = await self.ping_leader(current_leader)
                    if not is_responsive:
                        logger.info(f"Leader {current_leader} is unresponsive, voting no confidence")
                        await self.vote_no_confidence(current_leader)
                    else:
                        # Leader is responsive, clear any no-confidence vote
                        await self.vote_confidence(current_leader)
                        
        except Exception as e:
            logger.error(f"Error checking leader status: {e}")
    
    async def ping_leader(self, leader_address: str, timeout: float = 5.0) -> bool:
        """Ping the leader to check responsiveness"""
        try:
            # Get leader's instance ID from contract
            active_instances = self.contract.functions.getActiveInstances().call()
            
            # For demo purposes, we'll try to ping a known endpoint
            # In production, this would use the actual instance discovery
            leader_url = f"http://localhost:8080/health"  # Simplified for demo
            
            async with aiohttp.ClientTimeout(total=timeout):
                async with self.http_client.get(leader_url) as response:
                    return response.status == 200
        except Exception as e:
            logger.debug(f"Leader ping failed: {e}")
            return False
    
    async def vote_no_confidence(self, target_leader: str):
        """Vote no confidence against a leader"""
        try:
            # Build transaction
            tx = self.contract.functions.castVote(target_leader, True).build_transaction({
                'from': self.wallet_address,
                'nonce': self.w3.eth.get_transaction_count(self.wallet_address),
                'gas': 200000,
                'gasPrice': self.w3.eth.gas_price
            })
            
            # Sign and send transaction
            signed_tx = self.w3.eth.account.sign_transaction(tx, self.wallet_private_key)
            
            # Handle different Web3.py versions
            if hasattr(signed_tx, 'rawTransaction'):
                raw_tx = signed_tx.rawTransaction
            elif hasattr(signed_tx, 'raw_transaction'):
                raw_tx = signed_tx.raw_transaction
            else:
                raw_tx = signed_tx.rawTransaction if hasattr(signed_tx, 'rawTransaction') else signed_tx.raw_transaction
            
            tx_hash = self.w3.eth.send_raw_transaction(raw_tx)
            
            logger.info(f"Voted no confidence against {target_leader}, tx: {tx_hash.hex()}")
            
        except Exception as e:
            logger.error(f"Error voting no confidence: {e}")
    
    async def vote_confidence(self, target_leader: str):
        """Vote confidence in a leader"""
        try:
            # Build transaction
            tx = self.contract.functions.castVote(target_leader, False).build_transaction({
                'from': self.wallet_address,
                'nonce': self.w3.eth.get_transaction_count(self.wallet_address),
                'gas': 200000,
                'gasPrice': self.w3.eth.gas_price
            })
            
            # Sign and send transaction
            signed_tx = self.w3.eth.account.sign_transaction(tx, self.wallet_private_key)
            
            # Handle different Web3.py versions
            if hasattr(signed_tx, 'rawTransaction'):
                raw_tx = signed_tx.rawTransaction
            elif hasattr(signed_tx, 'raw_transaction'):
                raw_tx = signed_tx.raw_transaction
            else:
                raw_tx = signed_tx.rawTransaction if hasattr(signed_tx, 'rawTransaction') else signed_tx.raw_transaction
            
            tx_hash = self.w3.eth.send_raw_transaction(raw_tx)
            
            logger.debug(f"Voted confidence in {target_leader}, tx: {tx_hash.hex()}")
            
        except Exception as e:
            logger.error(f"Error voting confidence: {e}")
    
    async def leader_heartbeat(self):
        """Send heartbeat if I am the leader"""
        while True:
            try:
                if self.is_leader:
                    # Leader heartbeat logic could go here
                    # For now, just log that we're alive
                    logger.debug("Leader heartbeat")
                    self.last_leader_heartbeat = time.time()
                
                await asyncio.sleep(30)  # Heartbeat every 30 seconds
            except Exception as e:
                logger.error(f"Error in leader heartbeat: {e}")
                await asyncio.sleep(5)
    
    async def get_counter(self, request):
        """Get current counter value"""
        return web.json_response({
            'value': self.counter_value,
            'instance_id': self.instance_id,
            'is_leader': self.is_leader
        })
    
    async def increment_counter(self, request):
        """Increment counter (only leader can do this)"""
        if not self.is_leader:
            return web.json_response({
                'error': 'Only leader can increment counter'
            }, status=403)
        
        # Increment counter
        self.counter_value += 1
        
        # Log operation
        operation = {
            'timestamp': time.time(),
            'operation': 'increment',
            'new_value': self.counter_value,
            'leader': self.wallet_address
        }
        self.operation_log.append(operation)
        
        logger.info(f"Counter incremented to {self.counter_value}")
        
        return web.json_response({
            'success': True,
            'new_value': self.counter_value,
            'operation_id': len(self.operation_log)
        })
    
    async def get_log(self, request):
        """Get operation log"""
        return web.json_response({
            'operations': self.operation_log,
            'total_operations': len(self.operation_log)
        })
    
    async def get_status(self, request):
        """Get node status"""
        try:
            total_nodes = self.contract.functions.totalActiveNodes().call()
            required_votes = self.contract.functions.requiredVotes().call()
            current_leader = self.contract.functions.currentLeader().call()
            
            return web.json_response({
                'instance_id': self.instance_id,
                'wallet_address': self.wallet_address,
                'is_leader': self.is_leader,
                'counter_value': self.counter_value,
                'total_active_nodes': total_nodes,
                'required_votes': required_votes,
                'current_leader': current_leader,
                'last_leader_heartbeat': self.last_leader_heartbeat
            })
        except Exception as e:
            return web.json_response({
                'error': str(e)
            }, status=500)
    
    async def get_members(self, request):
        """Get active cluster members"""
        try:
            active_instances = self.contract.functions.getActiveInstances().call()
            return web.json_response({
                'active_instances': [instance.hex() for instance in active_instances],
                'total_active': len(active_instances)
            })
        except Exception as e:
            return web.json_response({
                'error': str(e)
            }, status=500)
    
    async def health_check(self, request):
        """Health check endpoint"""
        return web.json_response({
            'status': 'healthy',
            'instance_id': self.instance_id,
            'timestamp': time.time()
        })

    async def get_wallet_info_endpoint(self, request):
        """Get wallet information for debugging"""
        return web.json_response(self.get_wallet_info())

async def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Distributed Counter Service')
    parser.add_argument('--instance-id', required=True, help='Unique instance ID')
    parser.add_argument('--wallet', help='Wallet private key (required when not using dstack)')
    parser.add_argument('--contract', required=True, help='Contract address')
    parser.add_argument('--rpc-url', default='http://localhost:8545', help='Ethereum RPC URL')
    parser.add_argument('--port', type=int, default=8080, help='HTTP port')
    
    # DStack options
    parser.add_argument('--use-dstack', action='store_true', help='Use dstack-sdk for key derivation')
    parser.add_argument('--dstack-socket', help='DStack socket path (default: ./simulator/dstack.sock)')
    parser.add_argument('--dstack-key-path', help='DStack key derivation path (default: node/{instance-id})')
    parser.add_argument('--dstack-key-purpose', help='DStack key purpose (default: ethereum)')
    
    args = parser.parse_args()
    
    # Validate arguments
    if not args.use_dstack and not args.wallet:
        parser.error("Either --use-dstack or --wallet must be specified")
    
    if args.use_dstack and not DSTACK_AVAILABLE:
        parser.error("--use-dstack specified but dstack-sdk is not available")
    
    # Create and start counter service
    counter = DistributedCounter(
        instance_id=args.instance_id,
        wallet_private_key=args.wallet,
        contract_address=args.contract,
        rpc_url=args.rpc_url,
        port=args.port,
        use_dstack=args.use_dstack,
        dstack_socket=args.dstack_socket,
        dstack_key_path=args.dstack_key_path,
        dstack_key_purpose=args.dstack_key_purpose
    )
    
    await counter.start()

if __name__ == '__main__':
    asyncio.run(main())
