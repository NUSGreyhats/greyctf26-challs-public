pragma solidity 0.8.35;

interface Player {
    function gamble() external;
}

contract LetsGoGambling {
    uint256[4] public stock = [uint256(10), 10, 10, 10];
    mapping(address => uint256) boxes;
    mapping(uint256 => address) requests;
    uint256 public legendary;
    uint256 next;
    bool live;
    address immutable ORACLE;
    event Requested(uint256 indexed id);

    constructor(address o) {
        ORACLE = o;
    }

    function buy(uint256 n) external payable {
        require(msg.value == n * 1 ether);
        boxes[msg.sender] += n;
    }

    function open() external {
        require(!live && boxes[msg.sender] != 0);
        uint256 id = next++;
        requests[id] = msg.sender;
        emit Requested(id);
    }

    function fulfill(uint256 id, bytes32 random) external {
        address player = requests[id];
        uint256 x = uint256(random);
        require(msg.sender == ORACLE && player != address(0) && x < 100);
        uint256 rarity = x < 5 ? 3 : x < 20 ? 2 : x < 50 ? 1 : 0;
        uint256 n = stock[rarity];
        require(n != 0);
        live = true;
        Player(player).gamble();
        live = false;
        stock[rarity] = n - 1;
        boxes[player]--;
        if (rarity == 3) legendary++;
        delete requests[id];
    }
}

contract Setup {
    LetsGoGambling public immutable TARGET;

    constructor() {
        TARGET = new LetsGoGambling(msg.sender);
    }

    function isSolved() external view returns (bool) {
        return TARGET.legendary() == 10;
    }
}
