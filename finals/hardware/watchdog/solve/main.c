#define UART_BASE      0x10000000u
#define UART_TXDATA    0x00u
#define UART_STATUS    0x04u
#define UART_TX_READY  0x00000001u
#define LED_BASE       0x10000100u
#define FLAG_BASE      0x20000000u

static unsigned int read32(unsigned int addr)
{
    return *(volatile unsigned int *)addr;
}

static void write32(unsigned int addr, unsigned int value)
{
    *(volatile unsigned int *)addr = value;
}

static void uart_putc(unsigned int value)
{
    while ((read32(UART_BASE + UART_STATUS) & UART_TX_READY) == 0u) {}
    write32(UART_BASE + UART_TXDATA, value);
}

static void uart_puts(const char *value)
{
    while (*value != '\0') {
        uart_putc((unsigned int)*value);
        value++;
    }
    uart_putc('\n');
}

/*int main(void)
{
    write32(LED_BASE, 0xf0u);
    uart_puts("hello from payload");

    while (1) {}
}*/

static void uart_put_word_bytes(unsigned int value)
{
    uart_putc(value & 0xffu);
    uart_putc((value >> 8) & 0xffu);
    uart_putc((value >> 16) & 0xffu);
    uart_putc((value >> 24) & 0xffu);
}

int main(void)
{
    unsigned int length;
    unsigned int words;
    unsigned int i;

    // Basic MMIO Fuzzing Code -> Simple fuzzing
    for (unsigned int addr=0x10000200u; addr<0x10000300u; addr +=0x4u ){
        *(volatile unsigned int *)addr = 0;
    }

    length = read32(FLAG_BASE + 0xf0u);
    words = (length + 3u) / 4u;
        for (i = 0; i < words; i++) {uart_put_word_bytes(read32(FLAG_BASE + (i * 4u)));}
        uart_putc('\n');
    while (1) {}
}

// Alternative solution is just to print 1 character at a time through LED
// - Simple Solution