/*
 * C2PA JUMBF Validator — interactive text protocol (launched by socat)
 *
 * Parses JUMBF metadata from JPEGs and displays the full content
 * credential structure including all supported box types.
 */

#include <cstdint>
#include <cstring>
#include <cstdlib>
#include <cstdio>
#include <unistd.h>
#include <vector>
#include <string>
#include <iomanip>

#include "dbench_jumbf.h"
#include "db_jumbf_box.h"
#include "db_jumbf_lib.h"
#include "db_binary_file_desc_box.h"

using namespace dbench;

static const uint32_t MAX_JPEG = 1u << 20;

static const char* content_type_name(const unsigned char* uuid) {
    if (memcmp(uuid, jumbf_type_cbor, 16) == 0)                  return "CBOR";
    if (memcmp(uuid, jumbf_type_json, 16) == 0)                  return "JSON";
    if (memcmp(uuid, jumbf_type_xml, 16) == 0)                   return "XML";
    if (memcmp(uuid, jumbf_type_uuid, 16) == 0)                  return "UUID";
    if (memcmp(uuid, jumbf_type_contiguous_codestream, 16) == 0) return "CODESTREAM";
    if (memcmp(uuid, jumbf_type_embedded_file, 16) == 0)         return "EMBEDDED FILE";
    return "UNKNOWN";
}

static void print_hex(const unsigned char* data, int len) {
    for (int i = 0; i < len; i++)
        printf("%02x", data[i]);
}

static void print_uuid(const unsigned char* uuid) {
    for (int i = 0; i < 16; i++) {
        if (i == 4 || i == 6 || i == 8 || i == 10) printf("-");
        printf("%02x", uuid[i]);
    }
}

static void print_box(DbJumbBox& jumb) {
    unsigned char* type_uuid = jumb.desc_box_.get_type_16bytes();
    const char* type_name = content_type_name(jumb.desc_box_.get_jumb_content_type());

    printf("  JUMBF Box [size=%lu]\n", (unsigned long)jumb.get_box_size());

    printf("    Description:\n");
    printf("      Content Type : %s [", type_name);
    print_uuid(type_uuid);
    printf("]\n");
    printf("      Toggles      : 0x%02x\n", jumb.desc_box_.get_toggles_byte());
    printf("      Requestable  : %s\n", jumb.desc_box_.is_requestable() ? "yes" : "no");

    if (jumb.desc_box_.is_label_present())
        printf("      Label        : %s\n", jumb.desc_box_.get_label().c_str());

    if (jumb.desc_box_.is_id_present())
        printf("      ID           : %u\n", jumb.desc_box_.get_id());

    if (jumb.desc_box_.is_hash_present()) {
        unsigned char* h = jumb.desc_box_.get_hash();
        if (h) {
            printf("      Hash         : ");
            print_hex(h, 32);
            printf("\n");
        }
    }

    if (jumb.desc_box_.is_private_box_present()) {
        DbBox* priv = jumb.desc_box_.get_private_box();
        if (priv)
            printf("      Private Box  : type=%s size=%lu\n",
                   priv->get_box_type_str().c_str(),
                   (unsigned long)priv->get_box_size());
    }

    int no = 0;
    for (auto& box : jumb.content_boxes_) {
        printf("    Content Box %d:\n", ++no);
        printf("      Type         : %s (0x%x)\n",
               box.get_box_type_str().c_str(), box.get_tbox());
        printf("      Size         : %lu\n", (unsigned long)box.get_box_size());
        printf("      Payload      : %lu bytes\n", (unsigned long)box.get_payload_size());

        if (strcmp(type_name, "UUID") == 0 && box.get_payload()) {
            printf("      UUID Data    : ");
            print_uuid(box.get_payload());
            printf("\n");
        }

        if (strcmp(type_name, "EMBEDDED FILE") == 0 &&
            box.get_tbox() == box_type_bfdb) {
            DbFileDescBox fdesc;
            fdesc.deserialize(
                box.get_payload() - (box.is_xl_box_present() ? 16 : 8),
                box.get_box_size());
            printf("      Media Type   : %s\n", fdesc.get_media_type().c_str());
            if (!fdesc.get_file_name().empty())
                printf("      File Name    : %s\n", fdesc.get_file_name().c_str());
            printf("      External     : %s\n",
                   fdesc.is_externally_referenced() ? "yes" : "no");
        }

        if ((strcmp(type_name, "JSON") == 0 ||
             strcmp(type_name, "XML") == 0) && box.get_payload()) {
            unsigned char* p = box.get_payload();
            uint64_t sz = box.get_payload_size();
            if (sz > 256) sz = 256;
            printf("      Data         : ");
            fwrite(p, 1, sz, stdout);
            if (box.get_payload_size() > 256) printf("...");
            printf("\n");
        }
    }

    if (jumb.padding_box_present_) {
        printf("    Padding Box    : %lu bytes\n",
               (unsigned long)jumb.padding_box_.get_box_size());
    }

    delete[] type_uuid;
}

static int hex_val(int c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

int main() {
    setbuf(stdout, NULL);
    setbuf(stdin, NULL);

    printf("=== C2PA JUMBF Validator ===\n");

    for (;;) {
        printf("\njpeg size> ");
        char line[64];
        if (!fgets(line, sizeof(line), stdin)) break;
        uint32_t jpeg_size = (uint32_t)strtoul(line, NULL, 10);
        if (jpeg_size == 0) break;
        if (jpeg_size > MAX_JPEG) {
            printf("error: size exceeds maximum (%u)\n", MAX_JPEG);
            continue;
        }

        printf("jpeg hex> ");
        uint8_t* jpeg = new uint8_t[jpeg_size];
        uint32_t got = 0;
        while (got < jpeg_size) {
            int c1 = fgetc(stdin);
            while (c1 == ' ' || c1 == '\n' || c1 == '\r' || c1 == '\t')
                c1 = fgetc(stdin);
            if (c1 == EOF) goto done;
            int c2 = fgetc(stdin);
            if (c2 == EOF) goto done;
            int hi = hex_val(c1), lo = hex_val(c2);
            if (hi < 0 || lo < 0) {
                printf("error: invalid hex at byte %u\n", got);
                break;
            }
            jpeg[got++] = (uint8_t)((hi << 4) | lo);
        }
        if (got != jpeg_size) {
            delete[] jpeg;
            printf("error: expected %u bytes, got %u\n", jpeg_size, got);
            continue;
        }

        std::vector<unsigned char*> bufs;
        std::vector<uint64_t>       sizes;
        bufs.reserve(16);
        sizes.reserve(16);
        db_extract_jumbfs_from_jpg1(jpeg, (uint64_t)jpeg_size, bufs, sizes);
        delete[] jpeg;

        printf("\nFound %zu JUMBF box(es)\n", bufs.size());

        for (size_t i = 0; i < bufs.size(); i++) {
            printf("\n--- Box %zu ---\n", i);
            try {
                DbJumbBox box;
                box.deserialize(bufs[i], sizes[i]);
                print_box(box);
            } catch (const std::exception& e) {
                printf("  Parse error: %s\n", e.what());
            } catch (...) {
                printf("  Parse error\n");
            }
            delete[] bufs[i];
        }

        printf("\ndone\n");
        fflush(stdout);
    }

done:
    printf("goodbye\n");
    return 0;
}
