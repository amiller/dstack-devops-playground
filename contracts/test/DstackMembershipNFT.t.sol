// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Test.sol";
import "../src/DstackMembershipNFT.sol";

contract DstackMembershipNFTTest is Test {
    DstackMembershipNFT public nft;
    address public owner;
    address public user1;
    address public user2;
    address public user3;
    
    function setUp() public {
        owner = address(this);
        user1 = makeAddr("user1");
        user2 = makeAddr("user2");
        user3 = makeAddr("user3");
        
        nft = new DstackMembershipNFT();
    }
    
    function test_MintNFT() public {
        uint256 tokenId = nft.mintNodeAccess(user1, "node1");
        assertEq(tokenId, 1);
        assertEq(nft.ownerOf(tokenId), user1);
        assertEq(nft.walletToTokenId(user1), tokenId);
    }
    
    function test_RegisterInstance() public {
        uint256 tokenId = nft.mintNodeAccess(user1, "node1");
        bytes32 instanceId = keccak256("node1");
        
        vm.prank(user1);
        nft.registerInstance(instanceId, tokenId);
        
        assertEq(nft.tokenToInstance(tokenId), instanceId);
        assertEq(nft.instanceToToken(instanceId), tokenId);
        assertTrue(nft.activeInstances(instanceId));
    }
    
    function test_LeaderElection() public {
        // Mint NFTs for 3 users
        uint256 token1 = nft.mintNodeAccess(user1, "node1");
        uint256 token2 = nft.mintNodeAccess(user2, "node2");
        uint256 token3 = nft.mintNodeAccess(user3, "node3");
        
        // Register instances
        bytes32 instance1 = keccak256("node1");
        bytes32 instance2 = keccak256("node2");
        bytes32 instance3 = keccak256("node3");
        
        vm.prank(user1);
        nft.registerInstance(instance1, token1);
        
        vm.prank(user2);
        nft.registerInstance(instance2, token2);
        
        vm.prank(user3);
        nft.registerInstance(instance3, token3);
        
        // First user becomes leader
        vm.prank(user1);
        nft.electLeader();
        
        assertEq(nft.currentLeader(), user1);
        assertEq(nft.currentLeaderTokenId(), token1);
    }
    
    function test_ByzantineFaultTolerance() public {
        // Setup 3 nodes (2f+1 = 3, f+1 = 2 votes needed)
        uint256 token1 = nft.mintNodeAccess(user1, "node1");
        uint256 token2 = nft.mintNodeAccess(user2, "node2");
        uint256 token3 = nft.mintNodeAccess(user3, "node3");
        
        bytes32 instance1 = keccak256("node1");
        bytes32 instance2 = keccak256("node2");
        bytes32 instance3 = keccak256("node3");
        
        vm.prank(user1);
        nft.registerInstance(instance1, token1);
        
        vm.prank(user2);
        nft.registerInstance(instance2, token2);
        
        vm.prank(user3);
        nft.registerInstance(instance3, token3);
        
        // User1 becomes leader
        vm.prank(user1);
        nft.electLeader();
        
        assertEq(nft.currentLeader(), user1);
        
        // User2 and User3 vote no confidence against User1
        vm.prank(user2);
        nft.castVote(user1, true);
        
        vm.prank(user3);
        nft.castVote(user1, true);
        
        // Leader should be challenged (2 votes >= requiredVotes)
        assertEq(nft.currentLeader(), user2); // User2 should become new leader (lowest tokenId)
        assertEq(nft.currentLeaderTokenId(), token2);
    }
    
    function test_VoteClearing() public {
        uint256 token1 = nft.mintNodeAccess(user1, "node1");
        uint256 token2 = nft.mintNodeAccess(user2, "node2");
        
        bytes32 instance1 = keccak256("node1");
        bytes32 instance2 = keccak256("node2");
        
        vm.prank(user1);
        nft.registerInstance(instance1, token1);
        
        vm.prank(user2);
        nft.registerInstance(instance2, token2);
        
        // User2 votes no confidence against User1
        vm.prank(user2);
        nft.castVote(user1, true);
        
        assertEq(nft.noConfidenceCount(user1), 1);
        
        // User2 changes vote to confidence
        vm.prank(user2);
        nft.castVote(user1, false);
        
        assertEq(nft.noConfidenceCount(user1), 0);
    }
    
    function test_InstanceDeactivation() public {
        uint256 token1 = nft.mintNodeAccess(user1, "node1");
        bytes32 instance1 = keccak256("node1");
        
        vm.prank(user1);
        nft.registerInstance(instance1, token1);
        
        vm.prank(user1);
        nft.electLeader();
        
        assertEq(nft.currentLeader(), user1);
        
        // Deactivate instance
        vm.prank(user1);
        nft.deactivateInstance(instance1);
        
        assertFalse(nft.activeInstances(instance1));
        assertEq(nft.currentLeader(), address(0)); // Leader cleared
    }
    
    function test_ClusterSizeUpdate() public {
        uint256 token1 = nft.mintNodeAccess(user1, "node1");
        uint256 token2 = nft.mintNodeAccess(user2, "node2");
        uint256 token3 = nft.mintNodeAccess(user3, "node3");
        
        bytes32 instance1 = keccak256("node1");
        bytes32 instance2 = keccak256("node2");
        bytes32 instance3 = keccak256("node3");
        
        vm.prank(user1);
        nft.registerInstance(instance1, token1);
        
        vm.prank(user2);
        nft.registerInstance(instance2, token2);
        
        vm.prank(user3);
        nft.registerInstance(instance3, token3);
        
        assertEq(nft.totalActiveNodes(), 3);
        assertEq(nft.requiredVotes(), 2); // (3/2) + 1 = 2
    }
    
    function test_IsAppAllowed() public {
        uint256 token1 = nft.mintNodeAccess(user1, "node1");
        bytes32 instance1 = keccak256("node1");
        
        vm.prank(user1);
        nft.registerInstance(instance1, token1);
        
        // Create mock AppBootInfo
        IDstackApp.AppBootInfo memory bootInfo = IDstackApp.AppBootInfo({
            appId: address(0x123),
            instanceId: instance1,
            composeHash: bytes32(0),
            manifestHash: bytes32(0),
            configHash: bytes32(0),
            secretHash: bytes32(0),
            runner: "docker-compose",
            allowedEnvVars: new string[](0)
        });
        
        (bool allowed, string memory reason) = nft.isAppAllowed(bootInfo);
        assertTrue(allowed);
        assertEq(reason, "");
    }
    
    function test_IsAppAllowedRejected() public {
        // Create mock AppBootInfo for unregistered instance
        IDstackApp.AppBootInfo memory bootInfo = IDstackApp.AppBootInfo({
            appId: address(0x123),
            instanceId: bytes32(0x4560000000000000000000000000000000000000000000000000000000000000),
            composeHash: bytes32(0),
            manifestHash: bytes32(0),
            configHash: bytes32(0),
            secretHash: bytes32(0),
            runner: "docker-compose",
            allowedEnvVars: new string[](0)
        });
        
        (bool allowed, string memory reason) = nft.isAppAllowed(bootInfo);
        assertFalse(allowed);
        assertEq(reason, "Instance not registered with NFT");
    }
    
    function test_GetActiveInstances() public {
        uint256 token1 = nft.mintNodeAccess(user1, "node1");
        uint256 token2 = nft.mintNodeAccess(user2, "node2");
        
        bytes32 instance1 = keccak256("node1");
        bytes32 instance2 = keccak256("node2");
        
        vm.prank(user1);
        nft.registerInstance(instance1, token1);
        
        vm.prank(user2);
        nft.registerInstance(instance2, token2);
        
        bytes32[] memory instances = nft.getActiveInstances();
        assertEq(instances.length, 2);
        
        // Check both instances are present
        bool found1 = false;
        bool found2 = false;
        for (uint i = 0; i < instances.length; i++) {
            if (instances[i] == instance1) found1 = true;
            if (instances[i] == instance2) found2 = true;
        }
        assertTrue(found1);
        assertTrue(found2);
    }
    
    function test_GetInstanceInfo() public {
        uint256 token1 = nft.mintNodeAccess(user1, "node1");
        bytes32 instance1 = keccak256("node1");
        
        vm.prank(user1);
        nft.registerInstance(instance1, token1);
        
        (uint256 tokenId, bool active, address owner) = nft.getInstanceInfo(instance1);
        assertEq(tokenId, token1);
        assertTrue(active);
        assertEq(owner, user1);
    }
}
