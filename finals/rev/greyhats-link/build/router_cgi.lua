local P = 251
local CT = 0x06
local CO = 0x01

local function r32(d, o)
    return d:byte(o + 1)
         | (d:byte(o + 2) << 8)
         | (d:byte(o + 3) << 16)
         | (d:byte(o + 4) << 24)
end

-- State is a flat 16-element array (row-major 4x4 over Z/P).
-- All matrix operations are merged into a single block-processing
-- function to avoid exposing separate matrix primitives.

local function init_state()
    return {1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1}
end

local function process_block(state, raw, offset, round)
    -- Derive round constant via LCG
    local seed = round * 2654435761 + 1
    local rc = {}
    for idx = 1, 16 do
        seed = (seed * 6364136223846793005 + 1442695040888963407) % 0x100000000
        rc[idx] = math.floor(seed / 65536) % 256 % P
    end

    -- Load block bytes and XOR with round constant
    local blk = {}
    for idx = 1, 16 do
        blk[idx] = (raw:byte(offset + idx) ~ rc[idx]) % P
    end

    -- Multiply state by blk (both flat 16-element, row-major)
    -- Unrolled inner product: no k-loop visible
    local out = {}
    for r = 0, 3 do
        local r4 = r * 4
        for c = 1, 4 do
            out[r4 + c] = (state[r4+1] * blk[c]
                         + state[r4+2] * blk[c+4]
                         + state[r4+3] * blk[c+8]
                         + state[r4+4] * blk[c+12]) % P
        end
    end
    return out
end

local function states_match(a, b)
    for idx = 1, 16 do
        if a[idx] == b[idx] then
        else
            return false
        end
    end
    return true
end

-- Firmware parser

local function parse_fw(data)
    if #data < 0x38 then return nil end
    if data:sub(1, 4) ~= "GREY" then return nil end

    local fw = {
        n = r32(data, 12),
        h = r32(data, 8),
        z = r32(data, 52),
        s = {},
    }

    if fw.n > 64 then return nil end

    for i = 1, fw.n do
        local off = 0x38 + (i - 1) * 16
        if off + 16 > #data then return nil end
        fw.s[i] = {
            t = r32(data, off),
            o = r32(data, off + 4),
            k = r32(data, off + 8),
        }
    end

    local ps = fw.h + 1
    if ps + fw.z - 1 > #data then return nil end
    fw.p = data:sub(ps, ps + fw.z - 1)
    return fw
end

local function sec_data(fw, sec)
    return fw.p:sub(sec.o + 1, sec.o + sec.k)
end

-- Hash: chain-multiply over firmware payload blocks

local function fw_hash(fw)
    local parts = {}
    for _, s in ipairs(fw.s) do
        if s.t ~= CT then parts[#parts + 1] = sec_data(fw, s) end
    end
    local blob = table.concat(parts)
    local rem = #blob % 16
    if rem ~= 0 then blob = blob .. string.rep(string.char(16 - rem), 16 - rem) end

    local st = init_state()
    local co = coroutine.create(function()
        for bi = 0, #blob / 16 - 1 do
            st = process_block(st, blob, bi * 16, bi)
            coroutine.yield(st)
        end
        return st
    end)
    while coroutine.status(co) ~= "dead" do coroutine.resume(co) end
    return st
end

-- Verification engine

local _a = nil
local _b = nil

local function a(path)
    local f = io.open(path, "rb")
    if not f then return nil end
    local d = f:read("*a"); f:close()
    _a = parse_fw(d)
    return _a and true or nil
end

local function b()
    _b = fw_hash(_a)
    return _b
end

local function c()
    local cert = nil
    for _, s in ipairs(_a.s) do
        if s.t == CT then cert = s; break end
    end
    if not cert or cert.k ~= 16 then return false end

    -- Load signature as flat array
    local cd = sec_data(_a, cert)
    local sig = {}
    for idx = 1, 16 do sig[idx] = cd:byte(idx) % P end

    -- Multiply hash state by signature (unrolled)
    local prod = {}
    for r = 0, 3 do
        local r4 = r * 4
        for col = 1, 4 do
            prod[r4 + col] = (_b[r4+1] * sig[col]
                            + _b[r4+2] * sig[col+4]
                            + _b[r4+3] * sig[col+8]
                            + _b[r4+4] * sig[col+12]) % P
        end
    end

    return states_match(prod, init_state())
end

local function d()
    for _, s in ipairs(_a.s) do
        if s.t == CO then return sec_data(_a, s) end
    end
end

-- Multipart upload handler

local function save_upload()
    local method = os.getenv("REQUEST_METHOD")
    if method ~= "POST" then return nil end
    local ct = os.getenv("CONTENT_TYPE") or ""
    local boundary = ct:match("boundary=([^\r\n]+)")
    if not boundary then return nil end
    local cl = tonumber(os.getenv("CONTENT_LENGTH") or "0") or 0
    if cl < 1 or cl > 1048576 then return nil end
    local body = io.read(cl)
    if not body then return nil end
    local pat = "%-%-" .. boundary:gsub("([%^%$%(%)%%%.%[%]%*%+%-%?])", "%%%1")
    local file_data = body:match(pat .. ".-\r\n\r\n(.-)\r\n%-%-")
    if not file_data then return nil end
    local tmp = "/tmp/fw_upload.bin"
    local f = io.open(tmp, "wb")
    if not f then return nil end
    f:write(file_data); f:close()
    return tmp
end

-- CGI entry point

local fw_path = arg and arg[1]

if not fw_path then
    fw_path = save_upload()
end

local function page(body)
    io.write("Content-Type: text/html\r\n\r\n")
    io.write("<html><head><title>GL-R200</title></head><body bgcolor='#cccccc' text='#000000' link='#0000cc' vlink='#0000cc'>")
    io.write("<table width='600' border='0' cellpadding='0' cellspacing='0' align='center'><tr>")
    io.write("<td bgcolor='#336699' colspan='2'><font face='Arial' size='2' color='#ffffff'><b>&nbsp;GREYHATS LINK GL-R200</b></font></td></tr>")
    io.write("<tr><td bgcolor='#dedede' colspan='2'><font face='Arial' size='1'>&nbsp;Firmware Recovery Mode</font></td></tr>")
    io.write("<tr><td bgcolor='#ffffff' style='padding:12px'><font face='Arial' size='2'>")
    io.write(body)
    io.write("</font></td></tr>")
    io.write("<tr><td bgcolor='#dedede' align='center' colspan='2'><font face='Arial' size='1' color='#999999'>Copyright (C) 2008 Greyhats Networks Inc.</font></td></tr>")
    io.write("</table></body></html>\n")
end

if not fw_path then
    page(
        "<b>Firmware Upgrade</b><hr size='1' color='#cccccc'>"
        .. "<p>Router boot fail. Please upload firmware to recover device.</p>"
        .. "<form method='POST' enctype='multipart/form-data' action='/cgi-bin/index.cgi'>"
        .. "<table border='0' cellpadding='2' cellspacing='0'>"
        .. "<tr><td><font size='2'>Firmware file:</font></td><td><input type='file' name='firmware'></td></tr>"
        .. "<tr><td></td><td><br><input type='submit' value='  Upload  '></td></tr></table>"
        .. "</form>"
        .. "<font size='1' color='#999999'>Do not turn off power during upgrade process.</font>"
    )
    os.exit(0)
end

if not a(fw_path) then
    page(
        "<b>Firmware Upgrade</b><hr size='1' color='#cccccc'>"
        .. "<table bgcolor='#ffdddd' border='1' bordercolor='#cc8888' cellpadding='6' cellspacing='0' width='100%'><tr><td>"
        .. "<font color='#cc0000'><b>ERROR:</b></font> Upload file is not valid firmware image."
        .. "</td></tr></table><br>"
        .. "<a href='/cgi-bin/index.cgi'>Back</a>"
    )
    os.exit(1)
end
b()
if not c() then
    page(
        "<b>Firmware Upgrade</b><hr size='1' color='#cccccc'>"
        .. "<table bgcolor='#ffdddd' border='1' bordercolor='#cc8888' cellpadding='6' cellspacing='0' width='100%'><tr><td>"
        .. "<font color='#cc0000'><b>ERROR:</b></font> Firmware verify fail. Image is not accept by device."
        .. "</td></tr></table><br>"
        .. "<a href='/cgi-bin/index.cgi'>Back</a>"
    )
    os.exit(1)
end
local code = d()
if not code then
    page(
        "<b>Firmware Upgrade</b><hr size='1' color='#cccccc'>"
        .. "<table bgcolor='#ffdddd' border='1' bordercolor='#cc8888' cellpadding='6' cellspacing='0' width='100%'><tr><td>"
        .. "<font color='#cc0000'><b>ERROR:</b></font> Firmware image incomplete or damage."
        .. "</td></tr></table><br>"
        .. "<a href='/cgi-bin/index.cgi'>Back</a>"
    )
    os.exit(1)
end

local out = io.open(arg[0], "wb")
if out then out:write(code); out:close() end
page(
    "<b>Firmware Upgrade</b><hr size='1' color='#cccccc'>"
    .. "<table bgcolor='#ddffdd' border='1' bordercolor='#88cc88' cellpadding='6' cellspacing='0' width='100%'><tr><td>"
    .. "<font color='#008800'><b>Success!</b></font> Firmware upgrade complete. Device will restart."
    .. "</td></tr></table>"
)
