#include <iostream>
#include <memory>
#include <vector>
#include <string>
#include <cstdint>
#include <cstdlib>
#include <fstream>

template<class T, size_t N>
class RingBuffer {
    alignas(T) unsigned char storage[N][sizeof(T)];
    size_t head = 0;

public:
    template<class... Args>
    void emplace(Args&&... args) {
        void* slot = storage[head];
        ::new (slot) T(std::forward<Args>(args)...);
        head = (head + 1) % N;
    }
};

struct Item {
    std::string name;
    int level;

    Item(const std::string& name) : name(name), level(42) {
    }

    virtual ~Item() = default;

    virtual void inspect() {
        std::cout << "Item(" << name << ", level=" << level << ")\n";
    }
};

struct Sword : Item {
    Sword() : Item("Sword") {
    }
};

struct Potion : Item {
    Potion() : Item("Potion") {
        level = 3;
    }
};

struct Rock : Item {
    Rock() : Item("Rock") {
        level = 1;
    }
};

using item_t = std::shared_ptr<Item>;

struct ItemReceivedNotification {
    item_t item;
    std::string message;
};

struct Player {
    std::vector<item_t> inventory;
};

static constexpr size_t NOTIFICATION_CAP = 1 << 20;
RingBuffer<ItemReceivedNotification, NOTIFICATION_CAP> notifications;

std::vector<item_t> items;
Player player;

void win() {
    system("/bin/cat flag.txt");
    exit(0);
}

void setup_items() {
    items.emplace_back(std::make_shared<Sword>());
    items.emplace_back(std::make_shared<Potion>());
    items.emplace_back(std::make_shared<Rock>());

    player.inventory.reserve(1);
}

static int oracle(int round) {
    return (round * round + round + 1) % 3;
}

void battle() {
    uint32_t reward_count = 0;
    uint32_t round = 0;

    std::cout << "A mirror knight challenges you.\n";
    std::cout << "Choose each round: 0=block 1=dodge 2=parry\n";

    while (true) {
        std::cout << "Round " << round << "> ";

        uint32_t option;
        std::cin >> option;

        if (option != oracle(round)) {
            std::cout << "You lose!\n";
            reward_count = 0;
            break;
        }

        std::cout << "You win this exchange! Double up? ";
        std::string choice;
        std::cin >> choice;

        reward_count = reward_count == 0 ? 1 : reward_count * 2;
        round++;

        if (choice == "no")
            break;
    }

    auto reward = items[1];  // potion
    for (uint32_t i = 0; i < reward_count; i++) {
        notifications.emplace(ItemReceivedNotification{
            .item = reward,
            .message = "Battle reward"
            });
    }

    std::cout << "Rewards queued: " << reward_count << "\n";
}

void blacksmith() {
    std::cout << "Blacksmith commands:\n";
    std::cout << "  buy <id>\n";
    std::cout << "  rename <idx> <name>\n";
    std::cout << "  inspect <idx>\n";
    std::cout << "  back\n";

    while (true) {
        std::cout << "blacksmith> ";

        std::string command;
        std::cin >> command;

        if (command == "back") {
            break;
        }
        else if (command == "buy") {
            size_t id;
            std::cin >> id;

            if (id >= items.size()) {
                std::cout << "No such item.\n";
                continue;
            }

            player.inventory.emplace_back(items[id]);
            std::cout << "Bought " << items[id]->name << ".\n";
        }
        else if (command == "rename") {
            size_t idx;
            std::string name;
            std::cin >> idx >> name;

            if (idx >= player.inventory.size() || !player.inventory[idx]) {
                std::cout << "No such inventory slot.\n";
                continue;
            }

            player.inventory[idx]->name = name;
            std::cout << "Renamed.\n";
        }
        else if (command == "inspect") {
            size_t idx;
            std::cin >> idx;

            if (idx >= player.inventory.size() || !player.inventory[idx]) {
                std::cout << "No such inventory slot.\n";
                continue;
            }

            player.inventory[idx]->inspect();
        }
        else {
            std::cout << "Unknown blacksmith command.\n";
        }
    }
}

int main() {
    setup_items();

    std::cout << "Commands: battle, blacksmith, quit\n";

    while (true) {
        std::cout << "> ";

        std::string command;
        std::cin >> command;

        if (!std::cin)
            break;

        if (command == "battle") {
            battle();
        }
        else if (command == "blacksmith") {
            blacksmith();
        }
        else if (command == "quit") {
            break;
        }
        else {
            std::cout << "Unknown command.\n";
        }
    }
}