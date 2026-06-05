#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <stdexcept>

char USERNAME[] = "admin";

namespace {
const char BASE64_CHARS[] =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

int base64_value(char c) {
    const char *ptr = std::strchr(BASE64_CHARS, c);
    if (ptr == nullptr) {
        throw std::invalid_argument("invalid base64 character");
    }
    return static_cast<int>(ptr - BASE64_CHARS);
}

void decode_base64(const char *input, char *output) {
    int input_length = std::strlen(input);
    if (input_length == 0 || input_length % 4 != 0) {
        throw std::invalid_argument("invalid base64 length");
    }

    int output_index = 0;
    bool saw_padding = false;

    for (int i = 0; i < input_length; i += 4) {
        int value = 0;
        int padding = 0;

        for (int j = 0; j < 4; j++) {
            char c = input[i + j];
            if (c == '=') {
                if (i + 4 != input_length) {
                    throw std::invalid_argument("base64 padding before final block");
                }
                if (j < 2 || saw_padding) {
                    throw std::invalid_argument("invalid base64 padding");
                }
                saw_padding = true;
                padding++;
                value <<= 6;
                continue;
            }

            if (saw_padding) {
                throw std::invalid_argument("base64 data after padding");
            }
            value = (value << 6) | base64_value(c);
        }

        if (padding > 2) {
            throw std::invalid_argument("too much base64 padding");
        }

        for (int j = 0; j < 3 - padding; j++) {
            output[output_index++] = (value >> (16 - j * 8)) & 0xff;
        }
    }

    output[output_index] = '\0';
}

void print_plain_header() {
    std::printf("Content-Type: text/plain\n\n");
}

bool validate_auth(char *authorization, const char *flag) {
    char *basic_auth = nullptr;
    char *supplied_username = nullptr;
    char *supplied_password = nullptr;
    char decoded[0x100];

    if (authorization == nullptr || std::strncmp(authorization, "Basic ", 6) != 0) {
        return false;
    }

    basic_auth = authorization + 6;
    decode_base64(basic_auth, decoded);

    char *colon_pos = std::strchr(decoded, ':');
    if (colon_pos == nullptr) {
        return false;
    }

    *colon_pos = '\0';
    supplied_username = decoded;
    supplied_password = colon_pos + 1;

    return std::strcmp(supplied_username, USERNAME) == 0 &&
           std::strcmp(supplied_password, flag) == 0;
}
}

int main() {
    char *authorization = std::getenv("HTTP_AUTHORIZATION");
    char flag[0x20] = {0};
    FILE *flag_file = std::fopen("/flag.txt", "r");
    if (flag_file == nullptr) {
        std::fprintf(stderr, "Failed to open /flag.txt\n");
        return 1;
    }
    if (std::fgets(flag, sizeof(flag), flag_file) == nullptr) {
        std::fclose(flag_file);
        std::fprintf(stderr, "Failed to read /flag.txt\n");
        return 1;
    }
    std::fclose(flag_file);
    flag[std::strcspn(flag, "\n")] = '\0';

    print_plain_header();
    bool valid_auth = false;
    try {
        valid_auth = validate_auth(authorization, flag);
    } catch (const std::invalid_argument &error) {
        std::printf("Invalid base64 encoding.\n");
        std::fprintf(stderr, "Invalid base64 encoding: %s\n", error.what());
        return 0;
    }

    if (valid_auth) {
        std::printf("%s\n", flag);
        return 0;
    }

    if (authorization != nullptr && std::strncmp(authorization, "Basic ", 6) == 0) {
        std::printf("Invalid credentials.\n");
        return 0;
    }

    std::printf("No valid authorization provided.\n");
    return 0;
}
