import socket
import time

SERVER = 'localhost'   # Update accordingly
PORT = 36267

input_code = "()"*30 + "{"

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect((SERVER, PORT))  

sock.recv(1024).decode()

sock.send(input_code.encode() + "\n".encode())
sock.recv(1024).decode()
print(sock.recv(1024).decode())

sock.close()