io.write("Content-Type: text/html\r\n\r\n")
local f = io.open("/flag.txt", "r")
local flag = f and f:read("*a") or "grey{missing_flag}"
if f then f:close() end
io.write("<html><body><h1>" .. flag .. "</h1></body></html>\n")
