// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "@openzeppelin/contracts/token/ERC721/ERC721.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
interface IDstackApp {
    struct AppBootInfo {
        address appId;
        bytes32 instanceId;
        bytes32 composeHash;
        bytes32 manifestHash;
        bytes32 configHash;
        bytes32 secretHash;
        string runner;
        string[] allowedEnvVars;
    }
    
    function isAppAllowed(AppBootInfo calldata bootInfo) external view returns (bool, string memory);
}

contract DstackMembershipNFT is ERC721, Ownable, IDstackApp {
    uint256 private _tokenIds;
    uint256 private _totalSupply;
    
    // Instance management
    mapping(uint256 => bytes32) public tokenToInstance;     // NFT → instanceID
    mapping(bytes32 => uint256) public instanceToToken;     // instanceID → NFT  
    mapping(bytes32 => bool) public activeInstances;        // instanceID → active
    mapping(address => uint256) public walletToTokenId;     // wallet → tokenId
    
    // KMS attestation verification
    address public kmsRootAddress;
    
    function totalSupply() public view returns (uint256) {
        return _totalSupply;
    }
    
    // Byzantine fault tolerant leader election state
    struct Vote {
        address voter;
        address target;
        uint256 tokenId;
        bool isNoConfidence;
        uint256 timestamp;
    }
    
    mapping(address => Vote) public currentVotes;           // voter → current vote
    mapping(address => uint256) public noConfidenceCount;   // leader → votes against
    uint256 public totalActiveNodes;                        // Current cluster size
    uint256 public requiredVotes;                           // f+1 threshold for 2f+1 nodes
    
    address public currentLeader;                           // Current leader's wallet
    uint256 public currentLeaderTokenId;                    // Leader's NFT token
    
    // Leader election events
    event LeaderElected(address indexed leader, uint256 indexed tokenId, bytes32 instanceId);
    event VoteCast(address indexed voter, address indexed target, bool isNoConfidence);
    event LeaderChallenged(address indexed newLeader, address indexed oldLeader, uint256 voteCount);
    event InstanceRegistered(bytes32 indexed instanceId, uint256 indexed tokenId);
    event InstanceDeactivated(bytes32 indexed instanceId);
    event KmsRootUpdated(address indexed oldRoot, address indexed newRoot);
    
    constructor(address _kmsRootAddress) ERC721("DStack Membership NFT", "DSTACK") Ownable(msg.sender) {
        _tokenIds = 1; // Start from token ID 1
        kmsRootAddress = _kmsRootAddress;
    }
    
    function setKmsRootAddress(address _newKmsRoot) external onlyOwner {
        address oldRoot = kmsRootAddress;
        kmsRootAddress = _newKmsRoot;
        emit KmsRootUpdated(oldRoot, _newKmsRoot);
    }
    
    function mintNodeAccess(address to, string memory name) external onlyOwner returns (uint256) {
        require(walletToTokenId[to] == 0, "Wallet already has NFT");
        
        uint256 newTokenId = _tokenIds;
        _mint(to, newTokenId);
        walletToTokenId[to] = newTokenId;
        
        _tokenIds++;
        _totalSupply++;
        return newTokenId;
    }
    
    function registerInstance(bytes32 instanceId, uint256 tokenId) external {
        require(ownerOf(tokenId) == msg.sender, "Must own NFT");
        require(instanceToToken[instanceId] == 0, "Instance already registered");
        require(tokenToInstance[tokenId] == bytes32(0), "Token already has instance");
        
        tokenToInstance[tokenId] = instanceId;
        instanceToToken[instanceId] = tokenId;
        activeInstances[instanceId] = true;
        
        emit InstanceRegistered(instanceId, tokenId);
        updateClusterSize();
    }
    
    function registerInstanceWithProof(
        bytes32 instanceId, 
        uint256 tokenId,
        bytes memory derivedPublicKey,
        bytes memory appSignature,
        bytes memory kmsSignature,
        string memory purpose,
        bytes32 appId
    ) external {
        require(ownerOf(tokenId) == msg.sender, "Must own NFT");
        require(instanceToToken[instanceId] == 0, "Instance already registered");
        require(tokenToInstance[tokenId] == bytes32(0), "Token already has instance");
        
        // Verify signature chain proves KMS attestation
        require(
            verifySignatureChain(
                appId,
                derivedPublicKey,
                appSignature,
                kmsSignature,
                purpose
            ),
            "Invalid attestation proof"
        );
        
        tokenToInstance[tokenId] = instanceId;
        instanceToToken[instanceId] = tokenId;
        activeInstances[instanceId] = true;
        
        emit InstanceRegistered(instanceId, tokenId);
        updateClusterSize();
    }
    
    function verifySignatureChain(
        bytes32 appId,
        bytes memory derivedPublicKey,
        bytes memory appSignature,
        bytes memory kmsSignature,
        string memory purpose
    ) public view returns (bool) {
        // Step 1: Recover app public key from app signature
        bytes32 derivedKeyMessage = keccak256(abi.encodePacked(purpose, ":", _toHex(derivedPublicKey)));
        
        // Split signature into v, r, s components using assembly
        require(appSignature.length == 65, "Invalid app signature length");
        uint8 v;
        bytes32 r;
        bytes32 s;
        
        assembly {
            r := mload(add(appSignature, 32))
            s := mload(add(appSignature, 64))
            v := byte(0, mload(add(appSignature, 96)))
        }
        
        address appPublicKey = ecrecover(derivedKeyMessage, v, r, s);
        
        // Step 2: Verify KMS signature over app key
        bytes32 kmsMessage = keccak256(abi.encodePacked("dstack-kms-issued:", appId, abi.encodePacked(appPublicKey)));
        
        // Split KMS signature into v, r, s components
        require(kmsSignature.length == 65, "Invalid KMS signature length");
        uint8 kmsV;
        bytes32 kmsR;
        bytes32 kmsS;
        
        assembly {
            kmsR := mload(add(kmsSignature, 32))
            kmsS := mload(add(kmsSignature, 64))
            kmsV := byte(0, mload(add(kmsSignature, 96)))
        }
        
        address recoveredKMS = ecrecover(kmsMessage, kmsV, kmsR, kmsS);
        
        return recoveredKMS == kmsRootAddress;
    }
    
    function _toHex(bytes memory data) internal pure returns (string memory) {
        bytes memory alphabet = "0123456789abcdef";
        bytes memory str = new bytes(2 + data.length * 2);
        str[0] = "0";
        str[1] = "x";
        for (uint256 i = 0; i < data.length; i++) {
            str[2 + i * 2] = alphabet[uint8(data[i] >> 4)];
            str[2 + i * 2 + 1] = alphabet[uint8(data[i] & 0x0f)];
        }
        return string(str);
    }
    
    function deactivateInstance(bytes32 instanceId) external {
        uint256 tokenId = instanceToToken[instanceId];
        require(ownerOf(tokenId) == msg.sender, "Must own NFT");
        
        activeInstances[instanceId] = false;
        emit InstanceDeactivated(instanceId);
        updateClusterSize();
        
        // If this was the leader, trigger new election
        if (currentLeader == msg.sender) {
            currentLeader = address(0);
            currentLeaderTokenId = 0;
        }
    }
    
    function electLeader() external {
        require(walletToTokenId[msg.sender] != 0, "Must own NFT");
        require(activeInstances[tokenToInstance[walletToTokenId[msg.sender]]], "Instance not active");
        
        if (currentLeader == address(0)) {
            currentLeader = msg.sender;
            currentLeaderTokenId = walletToTokenId[msg.sender];
            emit LeaderElected(msg.sender, currentLeaderTokenId, tokenToInstance[currentLeaderTokenId]);
        }
    }
    
    function castVote(address target, bool isNoConfidence) external {
        require(walletToTokenId[msg.sender] != 0, "Must own NFT");
        require(activeInstances[tokenToInstance[walletToTokenId[msg.sender]]], "Instance not active");
        
        // Clear previous vote if exists
        if (currentVotes[msg.sender].voter != address(0)) {
            if (currentVotes[msg.sender].isNoConfidence) {
                if (noConfidenceCount[currentVotes[msg.sender].target] > 0) {
                    noConfidenceCount[currentVotes[msg.sender].target]--;
                }
            }
        }
        
        // Record new vote
        currentVotes[msg.sender] = Vote({
            voter: msg.sender,
            target: target,
            tokenId: walletToTokenId[msg.sender],
            isNoConfidence: isNoConfidence,
            timestamp: block.timestamp
        });
        
        if (isNoConfidence) {
            noConfidenceCount[target]++;
            
            // Check if threshold reached for current leader
            if (noConfidenceCount[target] >= requiredVotes && target == currentLeader) {
                _electNewLeader();
            }
        }
        
        emit VoteCast(msg.sender, target, isNoConfidence);
    }
    
    function _electNewLeader() internal {
        address oldLeader = currentLeader;
        
        // Find new leader: active node with lowest no-confidence votes
        // Tie-breaker: lowest tokenId
        uint256 minVotes = type(uint256).max;
        uint256 minTokenId = type(uint256).max;
        address newLeader = address(0);
        
        for (uint256 i = 1; i <= _totalSupply; i++) {
            address candidate = ownerOf(i);
            bytes32 instanceId = tokenToInstance[i];
            
            if (activeInstances[instanceId] && candidate != oldLeader) {
                uint256 votes = noConfidenceCount[candidate];
                if (votes < minVotes || (votes == minVotes && i < minTokenId)) {
                    minVotes = votes;
                    minTokenId = i;
                    newLeader = candidate;
                }
            }
        }
        
        if (newLeader != address(0)) {
            currentLeader = newLeader;
            currentLeaderTokenId = minTokenId;
            
            // Clear votes for new leader
            noConfidenceCount[newLeader] = 0;
            
            emit LeaderChallenged(newLeader, oldLeader, noConfidenceCount[oldLeader]);
        }
    }
    
    function updateClusterSize() public {
        uint256 activeCount = 0;
        for (uint256 i = 1; i <= _totalSupply; i++) {
            if (activeInstances[tokenToInstance[i]]) {
                activeCount++;
            }
        }
        totalActiveNodes = activeCount;
        requiredVotes = (activeCount / 2) + 1; // f+1 for 2f+1 nodes
    }
    
    // Override DstackApp's isAppAllowed to add instance validation
    function isAppAllowed(AppBootInfo calldata bootInfo) external view override returns (bool, string memory) {
        // Check if instanceId is registered with an NFT
        uint256 tokenId = instanceToToken[bootInfo.instanceId];
        if (tokenId == 0) return (false, "Instance not registered with NFT");
        
        // Verify NFT still exists and is active
        if (_ownerOf(tokenId) == address(0)) return (false, "NFT no longer exists");
        if (!activeInstances[bootInfo.instanceId]) return (false, "Instance marked inactive");
        
        return (true, "");
    }
    
    function getActiveInstances() external view returns (bytes32[] memory) {
        uint256 count = 0;
        for (uint256 i = 1; i <= _totalSupply; i++) {
            if (activeInstances[tokenToInstance[i]]) {
                count++;
            }
        }
        
        bytes32[] memory instances = new bytes32[](count);
        uint256 index = 0;
        for (uint256 i = 1; i <= _totalSupply; i++) {
            if (activeInstances[tokenToInstance[i]]) {
                instances[index] = tokenToInstance[i];
                index++;
            }
        }
        
        return instances;
    }
    
    function getInstanceInfo(bytes32 instanceId) external view returns (uint256 tokenId, bool active, address owner) {
        tokenId = instanceToToken[instanceId];
        active = activeInstances[instanceId];
        owner = tokenId > 0 ? ownerOf(tokenId) : address(0);
    }
}
