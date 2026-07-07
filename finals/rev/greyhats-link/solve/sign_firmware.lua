local PRIME = 251
local CERT_TYPE = 0x06
local CODE_TYPE = 0x01

local function write_u16_le(val)
    return string.char(val % 256, math.floor(val / 256) % 256)
end

local function write_u32_le(val)
    return string.char(
        val % 256,
        math.floor(val / 256) % 256,
        math.floor(val / 65536) % 256,
        math.floor(val / 16777216) % 256
    )
end

-- 4x4 matrix operations over Z/251 (must match router_cgi.lua)

local function mat_identity()
    local M = {}
    for i = 1, 4 do
        M[i] = {}
        for j = 1, 4 do
            if i == j then M[i][j] = 1
            else M[i][j] = 0 end
        end
    end
    return M
end

local function mat_from_bytes(s)
    local M = {}
    for i = 1, 4 do
        M[i] = {}
        for j = 1, 4 do
            M[i][j] = s:byte((i - 1) * 4 + j) % PRIME
        end
    end
    return M
end

local function mat_to_bytes(M)
    local parts = {}
    for i = 1, 4 do
        for j = 1, 4 do
            parts[#parts + 1] = string.char(M[i][j] % 256)
        end
    end
    return table.concat(parts)
end

local function mat_multiply(A, B)
    local C = {}
    for i = 1, 4 do
        C[i] = {}
        for j = 1, 4 do
            local sum = 0
            for k = 1, 4 do
                sum = sum + A[i][k] * B[k][j]
            end
            C[i][j] = sum % PRIME
        end
    end
    return C
end

local function mat_xor(A, B)
    local C = {}
    for i = 1, 4 do
        C[i] = {}
        for j = 1, 4 do
            C[i][j] = (A[i][j] ~ B[i][j]) % PRIME
        end
    end
    return C
end

local function mat_print(M, label)
    io.stderr:write((label or "Matrix") .. ":\n")
    for i = 1, 4 do
        io.stderr:write("  [")
        for j = 1, 4 do
            io.stderr:write(string.format("%4d", M[i][j]))
            if j < 4 then io.stderr:write(",") end
        end
        io.stderr:write("]\n")
    end
end

local function round_constant(index)
    local M = {}
    local state = index * 2654435761 + 1
    for i = 1, 4 do
        M[i] = {}
        for j = 1, 4 do
            state = (state * 6364136223846793005 + 1442695040888963407) % 0x100000000
            M[i][j] = math.floor(state / 65536) % 256 % PRIME
        end
    end
    return M
end

-- Matrix inverse mod 251

local function extended_gcd(a, b)
    if a == 0 then return b, 0, 1 end
    local g, x, y = extended_gcd(b % a, a)
    return g, y - math.floor(b / a) * x, x
end

local function mod_inverse(a, m)
    a = a % m
    if a == 0 then return nil end
    local g, x = extended_gcd(a, m)
    if g ~= 1 then return nil end
    return x % m
end

local function minor_3x3(M, skip_row, skip_col)
    local R = {}
    local ri = 1
    for i = 1, 4 do
        if i ~= skip_row then
            R[ri] = {}
            local ci = 1
            for j = 1, 4 do
                if j ~= skip_col then
                    R[ri][ci] = M[i][j]
                    ci = ci + 1
                end
            end
            ri = ri + 1
        end
    end
    return R
end

local function det_3x3(M)
    return (M[1][1] * (M[2][2] * M[3][3] - M[2][3] * M[3][2])
          - M[1][2] * (M[2][1] * M[3][3] - M[2][3] * M[3][1])
          + M[1][3] * (M[2][1] * M[3][2] - M[2][2] * M[3][1])) % PRIME
end

local function det_4x4(M)
    local det = 0
    for j = 1, 4 do
        local sign = (j % 2 == 1) and 1 or (PRIME - 1)
        det = (det + M[1][j] * sign * det_3x3(minor_3x3(M, 1, j))) % PRIME
    end
    return det
end

local function mat_inverse(M)
    local det = det_4x4(M)
    local det_inv = mod_inverse(det, PRIME)
    if not det_inv then return nil end

    local inv = {}
    for i = 1, 4 do
        inv[i] = {}
        for j = 1, 4 do
            local sign = ((i + j) % 2 == 0) and 1 or (PRIME - 1)
            inv[i][j] = (sign * det_3x3(minor_3x3(M, j, i)) * det_inv) % PRIME
        end
    end
    return inv
end

-- Firmware builder

local function build_firmware(sections)
    local parts = {}
    local entries = {}
    local offset = 0

    for _, section in ipairs(sections) do
        entries[#entries + 1] = {
            type_id = section.type_id,
            offset  = offset,
            size    = #section.data,
            flags   = section.flags or 0,
        }
        parts[#parts + 1] = section.data
        offset = offset + #section.data
    end

    local payload = table.concat(parts)
    local num_sections = #entries
    local header_size = 0x38 + num_sections * 16

    local image = "GREY"
        .. write_u16_le(1)
        .. write_u16_le(0)
        .. write_u32_le(header_size)
        .. write_u32_le(num_sections)
        .. write_u32_le(0)
        .. string.rep("\0", 32)
        .. write_u32_le(#payload)

    for _, entry in ipairs(entries) do
        image = image
            .. write_u32_le(entry.type_id)
            .. write_u32_le(entry.offset)
            .. write_u32_le(entry.size)
            .. write_u32_le(entry.flags)
    end

    return image .. payload
end

-- Hash computation (must match router_cgi.lua)

local function pad_to_16(data)
    local remainder = #data % 16
    if remainder == 0 then return data end
    local pad_len = 16 - remainder
    return data .. string.rep(string.char(pad_len), pad_len)
end

local function compute_hash(data)
    data = pad_to_16(data)
    local state = mat_identity()
    for block_index = 0, #data / 16 - 1 do
        local block = data:sub(block_index * 16 + 1, block_index * 16 + 16)
        state = mat_multiply(state, mat_xor(mat_from_bytes(block), round_constant(block_index)))
    end
    return state
end

-- Main

local code_path = arg[1]
local output_path = arg[2]

if not code_path then
    io.stderr:write("Usage: lua sign_firmware.lua <code_file> [output_file]\n")
    os.exit(1)
end

local file = io.open(code_path, "rb")
if not file then
    io.stderr:write("Cannot open " .. code_path .. "\n")
    os.exit(1)
end
local code = file:read("*a")
file:close()

io.stderr:write("Code: " .. #code .. " bytes\n")

local H = compute_hash(code)
mat_print(H, "H")
io.stderr:write("det(H) = " .. det_4x4(H) .. "\n")

local S = mat_inverse(H)
if not S then
    io.stderr:write("Hash matrix is singular mod " .. PRIME .. "\n")
    os.exit(1)
end
mat_print(S, "S = H^-1")
mat_print(mat_multiply(H, S), "H * S")

local image = build_firmware({
    { type_id = CODE_TYPE, data = code, flags = 1 },
    { type_id = CERT_TYPE, data = mat_to_bytes(S), flags = 8 },
})

if output_path then
    local out = io.open(output_path, "wb")
    out:write(image)
    out:close()
    io.stderr:write("Written " .. #image .. " bytes to " .. output_path .. "\n")
else
    io.stdout:write(image)
end
