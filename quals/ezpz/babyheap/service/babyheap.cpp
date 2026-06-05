#include <iostream>
#include <vector>
#include <string>
using namespace std;
#define MAX_MONKEYS 10
#define MAX_GREYCATS 10

void meow(char greycat_name[]) {
    cout << "greycat " << greycat_name << " says meow meow!" << endl;
}

class Monkey {
public:
    int arms = 2;
    int legs = 2;
    char name[32];

    Monkey() {
        cout << "Enter monkey name:" << endl;
        cin >> name;
        cout << "Monkey ";
        cout << name;
        cout << " created!" << endl;
    }
};

class Greycat {
public:
    int legs = 4;
    char name[32];
    void (*speak)(char[]) = meow;
    Greycat() {
        cout << "Enter greycat name:" << endl;
        cin >> name;
        cout << "Greycat ";
        cout << name;
        cout << " created!" << endl;
    }
    void talk() {
        speak(name);
    }
};

void printmenu() {
    cout << "1. Create monkey" << endl;
    cout << "2. Create greycat" << endl;
    cout << "3. Make greycat talk" << endl;
}

int main() {
    std::ios_base::sync_with_stdio(false);
    std::cin.tie(NULL);
    std::cout.tie(NULL);
    vector<Monkey> monkeys;
    vector<Greycat> greycats;
    monkeys.reserve(MAX_MONKEYS);
    greycats.reserve(MAX_GREYCATS);
    while (1) {
        printmenu();
        int choice;
        cin >> choice;
        if (choice == 1) {
            if (monkeys.size() >= MAX_MONKEYS) {
                cout << "Too many monkeys!" << endl;
                continue;
            }
            monkeys.emplace_back();
        } else if (choice == 2) {
            if (greycats.size() >= MAX_GREYCATS) {
                cout << "Too many greycats!" << endl;
                continue;
            }
            greycats.emplace_back();
        } else if (choice == 3) {
            int idx;
            cout << "Greycat index: " << endl;
            cin >> idx;
            cin.ignore();

            if (idx < 0 || idx >= greycats.size()) {
                cout << "Invalid greycat index!" << endl;
                continue;
            }
            greycats[idx].talk();
        }else if (choice == 6767) {
            cout << (void *) malloc << endl;
        } else {
            cout << "Invalid choice!" << endl;
        }
    }
}