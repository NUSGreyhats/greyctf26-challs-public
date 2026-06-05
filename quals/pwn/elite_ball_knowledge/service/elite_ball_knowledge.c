// gcc -no-pie -fno-stack-protector -static elite_ball_knowledge.c -o elite_ball_knowledge -lseccomp

#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <stdbool.h>
#include <unistd.h>
#include <errno.h>
#include <sys/mman.h>
#include <sys/prctl.h>
#include <seccomp.h>
#include <linux/seccomp.h>

int setup_sandbox()
{
    if (prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0) {
        perror("prctl(NO_NEW_PRIVS)");
        return 1;
    }

    scmp_filter_ctx ctx = seccomp_init(SCMP_ACT_ALLOW);
    if (!ctx) {
        perror("seccomp_init");
        return 1;
    }

    for (int i = 0; i <= 335; i++) {
        if (i == 60 || i == 231) continue;
        int res = seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EPERM), i, 0);
        if (res != 0) {
            return 1;
        }
    }

    if (seccomp_load(ctx) < 0) {
        perror("seccomp_load");
        return 1;
    }

    seccomp_release(ctx);

    return 0;
}

int main() {
    char buf[16];
    fgets(buf, 0x676700, stdin);
    if (setup_sandbox() != 0) {
        perror("setup_sandbox");
        return 1;
    }
}