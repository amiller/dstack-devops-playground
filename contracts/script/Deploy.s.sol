// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Script.sol";
import "../src/DstackMembershipNFT.sol";

contract DeployScript is Script {
    function run() external {
        uint256 deployerPrivateKey = vm.envUint("PRIVATE_KEY");
        
        vm.startBroadcast(deployerPrivateKey);
        
        DstackMembershipNFT nft = new DstackMembershipNFT();
        
        console.log("DstackMembershipNFT deployed at:", address(nft));
        
        // Mint NFTs for test accounts
        address[] memory testAccounts = new address[](3);
        testAccounts[0] = 0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266; // Account 0
        testAccounts[1] = 0x70997970C51812dc3A010C7d01b50e0d17dc79C8; // Account 1
        testAccounts[2] = 0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC; // Account 2
        
        for (uint i = 0; i < testAccounts.length; i++) {
            nft.mintNodeAccess(testAccounts[i], string(abi.encodePacked("node", vm.toString(i + 1))));
            console.log("Minted NFT for:", testAccounts[i]);
        }
        
        vm.stopBroadcast();
    }
}
