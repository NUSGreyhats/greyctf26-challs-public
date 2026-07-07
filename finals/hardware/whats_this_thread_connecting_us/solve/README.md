get into openthread CLI on the badge (menu 1 -> challenge 4)
ot ifconfig up
ot joiner start GREYFLAG99
ot thread start (optional)
ot dataset active -> get network key

flash sniffer
esptool.py -p <port> write_flash 0x0 sniffer_merged.bin

get a bunch of 802.15 frames
discover one of them has a suspicious PAN ID of 1337

throw it into a script that parses and decrypts an encrypted frame with the network key
python3 decrypt.py <frame_hex> <network_key_hex>
