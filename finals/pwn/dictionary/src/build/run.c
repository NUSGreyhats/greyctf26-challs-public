#include <stdio.h>
#include <fcntl.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <malloc.h>

void setup() {
  setbuf(stdin, NULL);
  setbuf(stdout, NULL);
  setbuf(stderr, NULL);
}

int main() {
  setup();
  char buf[0x100];
  size_t len;
  printf("enter size of exploit script > ");
  scanf("%zu", &len);

  getchar();

  char *payload = malloc(len + 0x1);
  if (!payload) {
    puts("failed to allocate memory");
    return -1;
  }
  memset(payload, 0, len+0x1);
  printf("enter exploit script (base64-encoded) > ");
  size_t got = 0;
  while (got < len) {
      ssize_t n = read(0, payload + got, len - got);
      if (n <= 0) break;
      got += n;
  }

  int fd = open("/tmp/solve.txt", O_CREAT | O_WRONLY, 0700);
  if (fd < 0) {
    puts("failed to open file for writing");
  }
  write(fd, payload, len);
  close(fd);
  system("base64 -d /tmp/solve.txt > /tmp/test.py && rm /tmp/solve.txt");

  puts("executing payload...");
  system("/app/python /tmp/test.py");
}
