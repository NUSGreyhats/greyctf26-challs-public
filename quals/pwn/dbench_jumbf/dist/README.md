# dbench_jumbf

Our media team deployed a C2PA Content Credentials validation service. Upload a JPEG and it will parse the embedded JUMBF metadata to verify the image's provenance chain.

The flag is in `/flag.txt` on the server.

## Running locally

```sh
docker compose up --build
```

The service listens on port `32167` on the host and port `1337` in the container.

To submit the bundled sample image:

```sh
python3 submit_sample.py localhost 32167
```

Expected output:

```text
=== C2PA JUMBF Validator ===

jpeg size> jpeg hex> 
Found 1 JUMBF box(es)

--- Box 0 ---
  JUMBF Box [size=51167]
    Description:
      Content Type : UNKNOWN [63327061-0011-0010-8000-00aa00389b71]
      Toggles      : 0x03
      Requestable  : yes
      Label        : c2pa
    Content Box 1:
      Type         : jumb (0x6a756d62)
      Size         : 51129
      Payload      : 51121 bytes

done

jpeg size> goodbye
```

## Protocol

The server runs a persistent loop. For each image:

```text
-> "jpeg size> "
-> enter size in decimal
-> "jpeg hex> "
-> enter JPEG as hex
<- parsed JUMBF metadata
<- "done"
```

Enter size `0` to disconnect.

## Files

```text
server                      target binary
sample_c2pa.jpg             sample JPEG with C2PA/JUMBF metadata
submit_sample.py            helper for sending the sample to a service
dbench_jumbf/               parser source
server.cpp                  service source
Dockerfile                  local jailed runner
docker-compose.yml          local runner compose file
flag.txt                    local dummy flag
```

## Third-Party Notice

The bundled `dbench_jumbf/` parser source is derived from the JPEG Systems JUMBF Reference Implementation 2:

https://gitlab.com/wg1/jpeg-systems/reference-software/jumbf-reference-implementation-2

It is licensed under the BSD 3-Clause "New" or "Revised" License. See `THIRD_PARTY_LICENSES.md` and `dbench_jumbf/LICENSE.txt`.

This bundle is not a full copy of upstream. It keeps the generic JUMBF/JPEG parsing code used by this service, omits unused typed box wrappers and encoder/serialization helpers, and includes small compatibility edits for the bundled validator.
