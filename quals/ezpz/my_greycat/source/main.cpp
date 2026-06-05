#include <iostream>
#include <fstream> 
#include <iterator>
#define N 257
using namespace std;

uint32_t cs[] = {}; // removed to reduce filesize
uint32_t ds[] = {};

uint32_t n = std::size(cs);

int main() {
    std::ofstream outFile("data.bin", std::ios::out | std::ios::binary);
    for (int i = 0; i < n; i++) {
        uint32_t ori = cs[i];
        uint32_t cur = 1;
        for (uint32_t j = 0; j < ds[i]; j++) {
            cur = ori * cur;
            cur %= N;
        }
        // cout << "cur: " << cur << endl;
        uint32_t data[] = {cur};
        outFile.write((char*) &data[0], sizeof(uint8_t));
    }
}