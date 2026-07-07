// gcc -no-pie -fno-stack-protector -o artifact-11 artifact-11.c
// gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

const char wizard_art_for_fun[] = "\n                  .\n\n                   .\n         /^\\     .\n    /\\   \"V\"\n   /__\\   I      O  o\n  //..\\\\  I     .\n  \\].`[/  I\n  /l\\/j\\  (]    .  O\n /. ~~ ,\\/I          .\n \\\\L__j^\\/I       o\n  \\/--v}  I     o   .\n  |    |  I   _________\n  |    |  I c(`       ')o\n  |    l  I   \\.     ,/\n_/j  L l\\_!  _//^---^\\\\_    -Row\n\n";
const unsigned char KEY[] = { 129, 101, 73, 255, 253, 20, 170, 37, 97, 118, 198, 249, 37, 63, 144, 149, 245, 168, 233, 162, 111 };

void give_introduction(void) {
    puts("How familiar are you with reading C code?");
    puts("We shall find out...");
    puts("Some tips: Don't worry if you don't understand every detail!");
    puts("Analyse what you need. I've left the function names in the decompilation (through magic).");
    puts("");
}

void ask_for_string_input(char *input) {
    printf("Enter some text (max 32 characters): >>> ");
    scanf("%32[^\n]", input);
    printf("You entered: %s\n", input);
}

void change_first_character(char *input) {
    puts("==================================================");
    puts("We shall change the first character of your input!");
    printf("%c >>> ", input[0]);
    input[0] -= 0x20;
    printf("%c\n", input[0]);
}

void change_last_character(char *input) {
    puts("==================================================");
    puts("We shall change the last character of your input!");
    size_t last_idx = strlen(input)-1;
    printf("%c >>> ", input[last_idx]);
    input[last_idx] -= 16;
    printf("%c\n", input[last_idx]);
}

char *add_new_characters(char *input) {
    puts("==================================================");
    puts("Now we shall append new characters to your input!");
    puts("(Optional) For the brave, you can try to decipher my inner workings... >:)");
    char *buf = malloc((size_t)(33+7));
    if (!buf) {
        puts("ruh oh...");
        free(input);
        exit(1);
    }
    strcpy(buf, input);
    printf("%s >>> ", buf);
    strcat(buf, "emy! <3");
    printf("%s\n", buf);
    return buf;
}

int suspicious_check(char *input) {
    puts("==================================================");
    puts("Let's see if you've gotten the memo...");
    puts(wizard_art_for_fun);
    return !strncmp(input, "I love greycademy! <3", 21);
}

void correct(char *input) {
    puts("Correct! You shall get the flag now.");
    puts("If you are viewing this in IDA, please don't bother reversing me, it's not needed >:)");
    puts("(Unless you are confident and want some challenge)");
    srand(67);
    char flag[33+7];
    size_t size = strlen(input);
    for (int i = 0; i < size; i++) {
        flag[i] = (char)(
            (unsigned char)input[i] ^ (unsigned char)input[i+1] ^ (unsigned char)(rand() % 256) ^ KEY[i]
        );
    }
    flag[size] = '\0';
    printf("Here's your flag: %s\n", flag);
    puts("Hope you had fun! :)");
}

void wrong() {
    puts("You did not get the memo :( shall we try again?");
    puts("Goodbye!");
}

void you_can_ignore_this_just_a_cleanup(char *input) {
    free(input);
}

void run(char *input) {
    give_introduction();
    ask_for_string_input(input);
    if (strlen(input) == 0) {
        puts("Nothing to change :(");
        return;
    }
    change_first_character(input);
    change_last_character(input);
    input = add_new_characters(input);
    if (suspicious_check(input)) {
        correct(input);
    } else {
        wrong(input);
    }
    you_can_ignore_this_just_a_cleanup(input);
}

int main(void) {
    char *buf = (char *)calloc((size_t)10, (size_t)33);
    unsigned int idx;
    char c;
    while (
        (printf("Index > "),
        scanf("%u", &idx)) > 0
        && idx < 10
    ) {
        while ((c = getchar()) != '\n' && c != EOF);
        run(&buf[33*idx]);
    }
    return 0;
}

void win(void) {
    system("/bin/sh");
}
