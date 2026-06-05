#pragma once

#include <cstdint>
#include <string>
#include <vector>
#include <stdexcept>
#include <cstring>

namespace dbench {

	constexpr auto MAX_32BIT_UINT_VALUE = 4294967295;

	constexpr int jumbf_lib_major_ver = 2;  // compatibility changed
	constexpr int jumbf_lib_minor_ver = 0;  // for backword compatible
	constexpr int jumbf_lib_patch_ver = 0;  // for bug fixes

	void print_lib_version();
	enum class JpegMarker {                  /* JPEG marker codes */
		M_SOF0 = 0xc0,
		M_SOF1 = 0xc1,
		M_SOF2 = 0xc2,
		M_SOF3 = 0xc3,

		M_SOF5 = 0xc5,
		M_SOF6 = 0xc6,
		M_SOF7 = 0xc7,

		M_JPG = 0xc8,
		M_SOF9 = 0xc9,
		M_SOF10 = 0xca,
		M_SOF11 = 0xcb,

		M_SOF13 = 0xcd,
		M_SOF14 = 0xce,
		M_SOF15 = 0xcf,

		M_DHT = 0xc4,

		M_DAC = 0xcc,

		M_RST0 = 0xd0,
		M_RST1 = 0xd1,
		M_RST2 = 0xd2,
		M_RST3 = 0xd3,
		M_RST4 = 0xd4,
		M_RST5 = 0xd5,
		M_RST6 = 0xd6,
		M_RST7 = 0xd7,

		M_SOI = 0xd8,
		M_EOI = 0xd9,
		M_SOS = 0xda,
		M_DQT = 0xdb,
		M_DNL = 0xdc,
		M_DRI = 0xdd,
		M_DHP = 0xde,
		M_EXP = 0xdf,

		M_APP0 = 0xe0,
		M_APP1 = 0xe1,
		M_APP2 = 0xe2,
		M_APP3 = 0xe3,
		M_APP4 = 0xe4,
		M_APP5 = 0xe5,
		M_APP6 = 0xe6,
		M_APP7 = 0xe7,
		M_APP8 = 0xe8,
		M_APP9 = 0xe9,
		M_APP10 = 0xea,
		M_APP11 = 0xeb,
		M_APP12 = 0xec,
		M_APP13 = 0xed,
		M_APP14 = 0xee,
		M_APP15 = 0xef,

		M_JPG0 = 0xf0,
		M_JPG13 = 0xfd,
		M_COM = 0xfe,

		M_TEM = 0x01,

		M_ERROR = 0x100
	};
	constexpr uint32_t box_type_jumb = 0x6a756d62; // jumb = JUMBF Superbox
	constexpr uint32_t box_type_jumd = 0x6a756d64; // jumd = jumbf description Box
	constexpr uint32_t box_type_jp2c = 0X6A703263; // Contiguous Codestream Box 
	constexpr uint32_t box_type_xml = 0X786D6C20;  // xml box
	constexpr uint32_t box_type_json = 0X6A736F6E; // json box
	constexpr uint32_t box_type_uuid = 0X75756964;  // uuid box
	constexpr uint32_t box_type_bidb = 0x62696462; // binary data box
	constexpr uint32_t box_type_bfdb = 0x62666462;  // Embedded file Description box
	constexpr uint32_t box_type_cbor = 0x63626F72; // CBOR box
	constexpr uint32_t box_type_free = 0x66726565; // free box => padding box
	constexpr uint32_t box_type_priv = 0x70726976; // Private box

	constexpr unsigned char jumbf_type_contiguous_codestream[16] = { 0x65, 0x79, 0xD6, 0xFB, 0xDB, 0xA2, 0x44, 0x6B, 0xB2, 0xAC, 0x1B, 0x82, 0xFE, 0xEB, 0x89, 0xD1 };
	constexpr unsigned char jumbf_type_xml[16] =                   { 0x78, 0x6D, 0x6C, 0x20, 0x00, 0x11, 0x00, 0x10, 0x80, 0x00, 0x00, 0xAA, 0x00, 0x38, 0x9B, 0x71 };
	constexpr unsigned char jumbf_type_json[16] =                  { 0x6A, 0x73, 0x6F, 0x6E, 0x00, 0x11, 0x00, 0x10, 0x80, 0x00, 0x00, 0xAA, 0x00, 0x38, 0x9B, 0x71 };
	constexpr unsigned char jumbf_type_uuid[16] =                  { 0x75, 0x75, 0x69, 0x64, 0x00, 0x11, 0x00, 0x10, 0x80, 0x00, 0x00, 0xAA, 0x00, 0x38, 0x9B, 0x71 };
	constexpr unsigned char jumbf_type_embedded_file[16] =         { 0x40, 0xCB, 0x0C, 0x32, 0xBB, 0x8A, 0x48, 0x9D, 0xA7, 0x0B, 0x2A, 0xD6, 0xF4, 0x7F, 0x43, 0x69 };
	constexpr unsigned char jumbf_type_cbor[16] =                  { 0x63, 0x62, 0x6F, 0x72, 0x00, 0x11, 0x00, 0x10, 0x80, 0x00, 0x00, 0xAA, 0x00, 0x38, 0x9B, 0x71 };

	bool isNthBitSet_1(unsigned char byte, int n);
	bool db_put_byte(unsigned char** dst_buf, char data);
	bool db_put_2byte(unsigned char** dst_buf, uint32_t data);
	bool db_put_4byte(unsigned char** dst_buf, uint32_t data);
	bool db_put_8byte(unsigned char** dst_buf, uint64_t value);
	unsigned char db_get_byte(unsigned char** buf);
	uint16_t db_get_2byte(unsigned char** buf);
	uint32_t db_get_4byte(unsigned char** buf);
	uint64_t db_get_8byte(unsigned char** buf);
	uint32_t box_type_str_to_uint32(std::string& type_str);
	std::string uint32_to_ASCII(uint32_t input);

	int db_write_jumbf_buf_to_jpg_buf(unsigned char* jumbf_buf, uint64_t jumbf_size, unsigned char* jpg_buf, uint64_t jpg_size, unsigned char** out_buf, uint64_t* out_buf_siz);

	// db_extract_jumbf_bitstream extract JUMBF bitstream "jumb_buf" of size "jumb_buf_size" of requested content "type" from "in_jpg_buf" of size "in_jpg_size"
	int db_extract_jumbf_bitstream(unsigned char* in_jpg_buf, uint64_t in_jpg_size, const unsigned char* type, unsigned char** jumb_buf, uint32_t* jumb_buf_size);

	// db_extract_jumbfs_from_jpg1 extract all JUMBFs bitstreams from jpg_buf of size jpg_buf_size and put pointers to each buff in jumbfs_vec
	int db_extract_jumbfs_from_jpg1(unsigned char* jpg_buf, uint64_t jpg_buf_size, std::vector<unsigned char*>& jumbfs_vec, std::vector<uint64_t>& sizes);

	void db_read_file_bitstream(std::string InputFile, unsigned char** pBuffer, uint64_t* file_size);
	bool db_write_file_bitstream(std::string OutputFile, const unsigned char* const data, const uint64_t data_size);
}