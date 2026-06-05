#include <iostream>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <vector>

#include "dbench_jumbf.h"

namespace dbench {
	void print_lib_version()
	{
		std::cout << "Doublebench JUMBF Library : v" << jumbf_lib_major_ver << "." << jumbf_lib_minor_ver << "." << jumbf_lib_patch_ver << std::endl;
	}
	// n should be 1<=n<=8;
	bool isNthBitSet_1(unsigned char byte, int n)
	{
		if (n < 1 || n>8) {
			throw std::runtime_error("Error: Checking status of a bit in Byte, n should be 1<=n<=8.");
		}
		if ((byte >> (n - 1)) & 1)
			return true;
		else
			return false;
	}
	bool db_put_byte(unsigned char** dst_buf, char data)
	{

		**dst_buf = data;
		(*dst_buf)++;
		return true;
	}

	bool db_put_2byte(unsigned char** dst_buf, uint32_t data)
	{
		unsigned char temp_data = (unsigned char)(data >> 8);
		db_put_byte(dst_buf, temp_data);

		temp_data = (unsigned char)(data);
		db_put_byte(dst_buf, temp_data);

		return true;
	}

	bool db_put_4byte(unsigned char** dst_buf, uint32_t data)
	{
		unsigned char temp_data = (unsigned char)(data >> 24);
		db_put_byte(dst_buf, temp_data);

		temp_data = (unsigned char)(data >> 16);
		db_put_byte(dst_buf, temp_data);

		temp_data = (unsigned char)(data >> 8);
		db_put_byte(dst_buf, temp_data);
		temp_data = (unsigned char)(data);
		db_put_byte(dst_buf, temp_data);
		return true;
	}

	bool db_put_8byte(unsigned char** dst_buf, uint64_t value)
	{
		for (auto i = 7; i >= 0; i--) {
			unsigned char temp_data = (unsigned char)(value >> (8 * i));
			db_put_byte(dst_buf, temp_data);
		}
		return true;
	}

	unsigned char db_get_byte(unsigned char** buf)
	{
		unsigned char val;
		val = *(*buf)++;
		return val;
	}

	uint16_t db_get_2byte(unsigned char** buf)
	{
		int val1, val2;
		val1 = (db_get_byte(buf)) << 8;
		val2 = db_get_byte(buf);
		return val1 + val2;

	}

	uint32_t db_get_4byte(unsigned char** buf)
	{
		long val1, val2;
		val1 = (db_get_2byte(buf)) << 16;
		val2 = db_get_2byte(buf);

		return val1 + val2;
	}

	uint64_t db_get_8byte(unsigned char** buf)
	{
		uint64_t val1, val2;

		val1 = (static_cast<uint64_t>(db_get_4byte(buf))) << 32;
		val2 = static_cast<uint64_t>(db_get_4byte(buf));
		return val1 + val2;
	}


	uint32_t box_type_str_to_uint32(std::string& type_str)
	{
		if (type_str.size() != 4) {
			std::cerr << "Input string must be exactly 4 characters long." << std::endl;
			return 0;
		}
		uint32_t result;
		std::memcpy(&result, type_str.data(), 4);
		// Convert to little endian
		result = ((result & 0xff000000) >> 24) |
			((result & 0x00ff0000) >> 8) |
			((result & 0x0000ff00) << 8) |
			((result & 0x000000ff) << 24);
		return result;
	}


	std::string uint32_to_ASCII(uint32_t input) {
		std::string result;
		for (int i = 0; i < 4; ++i) {
			char c = static_cast<char>((input >> (8 * i)) & 0xFF);
			result.insert(result.begin(), c);
		}
		return result;
	}

	int db_write_jumbf_buf_to_jpg_buf(unsigned char* jumbf_buf, uint64_t jumbf_size, unsigned char* input_jpg, uint64_t jpg_size, unsigned char** output_buf, uint64_t* output_buf_size)
	{
		unsigned short previous_jumb_en = 0;
		unsigned short previous_jumb_z = 1;
		unsigned short this_jumb_z = 1;
		if (input_jpg == nullptr || jumbf_buf == nullptr)
		{
			std::cout << "Error: Empty JPEG bufer or JUMBF buffer detected while embedding JUMBF Buffer." << std::endl;
			return false;
		}


		uint32_t jumb_header_size{ 8 };
		uint32_t JumbLbox = db_get_4byte(&jumbf_buf);
		uint32_t Tbox = db_get_4byte(&jumbf_buf);
		uint64_t jumb_xl_box{ 0 };
		if (JumbLbox == 1) {
			jumb_xl_box = db_get_8byte(&jumbf_buf);
			jumb_header_size += 8;
		}

		uint32_t size_per_marker = 65535;
		uint32_t app11_header_size = 10 + jumb_header_size; //Le(2) + CI(2) + En(2) + Z(4) 
		uint32_t jumb_data_size_per_marker = size_per_marker - app11_header_size;
		uint32_t no_of_app11_required = static_cast<uint32_t>((jumbf_size / jumb_data_size_per_marker) + 1);
		*output_buf_size = jpg_size + jumbf_size + ((static_cast<uint64_t>(app11_header_size) + 2) * no_of_app11_required) - jumb_header_size; // -8 Tbox and Lbox of Jumb already covered in header size;
		*output_buf = new unsigned char[*output_buf_size];

		unsigned char* dst_buf_position = *output_buf;

		bool meet_SOS = false;
		uint64_t output_buf_remaining_size = *output_buf_size;
		uint64_t jumb_buf_remaining_size = jumbf_size;

		jumb_buf_remaining_size -= jumb_header_size;
		unsigned char* jumb_payload = jumbf_buf;

		uint32_t length = 0;
		int expected_FF = 0, marker = 0;
		unsigned char* buf = input_jpg;
		uint32_t header_buf_size = 0;
		//int marker_count = 0;
		do {
			expected_FF = db_get_byte(&buf);
			header_buf_size++;
			if (expected_FF == 0xFF)
			{
				marker = db_get_byte(&buf);
				//cout << ++marker_count << "  : Marker : 0xFF" << hex << marker << endl;
				header_buf_size++;
				if ((unsigned char)(marker) == (unsigned char)(JpegMarker::M_SOI)) {
					continue;
				}
				else if ((unsigned char)(marker) == (unsigned char)(JpegMarker::M_EOI)) {
					std::cout << "Error: Pre-mature EOI." << std::endl;
					return -1;
				}
				else if ((unsigned char)(marker) == (unsigned char)(JpegMarker::M_APP11)) {
					// looks for already present APP11 markers and JUMB boxes
					length = db_get_2byte(&buf);
					unsigned short JP = db_get_2byte(&buf);
					unsigned short En = db_get_2byte(&buf);
					uint32_t Z = db_get_4byte(&buf);
					uint32_t Lbox = db_get_4byte(&buf);
					uint32_t Tbox = db_get_4byte(&buf);
					if (Tbox == uint32_t(box_type_jumb) && En == previous_jumb_en && Z == previous_jumb_z + 1) {
						// it is same jumb
						previous_jumb_z = Z;
					}
					else {
						//it is new jumbf
						previous_jumb_en = En;
					}
					header_buf_size += length;
					length -= 18;
					buf += length;
				}
				else if ((unsigned char)(marker) == (unsigned char)(JpegMarker::M_DQT)) { // write before Quantization tables
					buf -= 2;
					header_buf_size -= 2;
					//memcpy_s(dst_buf_position, *output_buf_size, input_jpg, header_buf_size);
					memcpy(dst_buf_position, input_jpg, header_buf_size);
					dst_buf_position += header_buf_size;
					output_buf_remaining_size -= header_buf_size;
					uint32_t box_instance_num = previous_jumb_en + 1;

					for (uint32_t Z = 1; Z <= no_of_app11_required; Z++) {
						uint32_t this_marker_payload_size = jumb_data_size_per_marker;
						if (Z == no_of_app11_required)
							this_marker_payload_size = static_cast<uint32_t>(jumb_buf_remaining_size);

						int APP11_marker = 0xffeb; //APP11
						int common_identifier = 0x4A50; //'JP
						db_put_2byte(&dst_buf_position, APP11_marker);
						db_put_2byte(&dst_buf_position, this_marker_payload_size + app11_header_size);
						db_put_2byte(&dst_buf_position, common_identifier);
						db_put_2byte(&dst_buf_position, box_instance_num);
						db_put_4byte(&dst_buf_position, Z);
						db_put_4byte(&dst_buf_position, JumbLbox);
						db_put_4byte(&dst_buf_position, Tbox);
						if (JumbLbox == 1) {
							db_put_8byte(&dst_buf_position, jumb_xl_box);
						}

						//memcpy_s(dst_buf_position, output_buf_remaining_size, jumb_payload, this_marker_payload_size);
						memcpy(dst_buf_position, jumb_payload, this_marker_payload_size);
						dst_buf_position += this_marker_payload_size; // advance position pointer to end of output buf.
						jumb_payload += this_marker_payload_size; // advance position for next marker data
						output_buf_remaining_size -= (static_cast<unsigned long long>(this_marker_payload_size) + app11_header_size + 2);
						jumb_buf_remaining_size -= this_marker_payload_size;
					}
					//memcpy_s(dst_buf_position, output_buf_remaining_size, buf, (jpg_size - header_buf_size));
					memcpy(dst_buf_position, buf, (jpg_size - header_buf_size));
					meet_SOS = true;
				}
				else {
					length = db_get_2byte(&buf);
					header_buf_size += length;
					length -= 2;
					buf += length;
				}
			}
		} while (meet_SOS == false);
		jumbf_buf -= 8; // repositioning of pointer to start of buffer

		//delete[] jumbf_buf;
		return 0;
	}


	int db_extract_jumbf_bitstream(unsigned char* in_jpg_buf, uint64_t in_jpg_size, const unsigned char* type, unsigned char** jumb_buf, uint32_t* jumb_buf_size)
	{
		if (in_jpg_buf == nullptr) {
			return -1;
		}
		std::vector<unsigned char> codestream_data; ///concatenated
		unsigned char* data = in_jpg_buf;
		unsigned char last = db_get_byte(&data);
		unsigned char current = db_get_byte(&data);
		if (last != 0xFF || current != (unsigned char)(JpegMarker::M_SOI)) {
			std::cout << "Image is not JPEG" << std::endl;
			return -1;
		}
		last = db_get_byte(&data);
		current = db_get_byte(&data);
		uint32_t previous_En = 1;
		uint32_t previous_Z = 0;
		unsigned Lbox = 0;
		bool is_requested_jumbf = false;
		//reading markers;
		while (1)
		{
			if (last != 0xFF)
			{
				std::cout << "Error - Expected a marker\n";
				break;
			}
			else if (current == (unsigned char)(JpegMarker::M_SOS)) {
				break;
			}
			else if (current == (unsigned char)(JpegMarker::M_APP11))
			{
				uint32_t len = db_get_2byte(&data);
				uint32_t CI = db_get_2byte(&data);
				uint32_t this_En = db_get_2byte(&data);
				uint32_t this_Z = db_get_4byte(&data);
				Lbox = db_get_4byte(&data);
				uint32_t Tbox = db_get_4byte(&data);
				if (Tbox == uint32_t(box_type_jumb) && this_Z == 1)
				{
					if (memcmp(type, (data + 8), 16) == 0) {
						is_requested_jumbf = true;
					}
				}
				if (is_requested_jumbf) {
					int this_marker_data_size = 0;
					if (this_En == previous_En && this_Z == (previous_Z + 1)) { // these checks are enough for this jumb box 
						if (this_Z == 1) {
							unsigned char* LboxTbox_ptr = new unsigned char[8];
							db_put_4byte(&LboxTbox_ptr, Lbox);
							db_put_4byte(&LboxTbox_ptr, Tbox);
							LboxTbox_ptr -= 8;
							codestream_data.insert(codestream_data.end(), &LboxTbox_ptr[0], &LboxTbox_ptr[8]);
						}
						// we have to concatenate the data.
						this_marker_data_size = len - 18;
						codestream_data.insert(codestream_data.end(), &data[0], &data[this_marker_data_size]);
						previous_Z++;
					}
					data += this_marker_data_size; //(len - 18);

				}
				else {
					data += (len - 18);
				}
			}
			else if (current == (unsigned char)(JpegMarker::M_SOI)) {
				break;
			}
			else if (current == (unsigned char)(JpegMarker::M_EOI)) {
				break;
			}
			else {
				int len = db_get_2byte(&data);
				data += (len - 2);
			}
			last = db_get_byte(&data);
			current = db_get_byte(&data);
		}
		if (!is_requested_jumbf) {
			*jumb_buf = nullptr;
			*jumb_buf_size = 0;
			return 0;
		}
		// Now codestream_data has all the concatenated data.
		if (Lbox != codestream_data.size()) {
			std::cout << "Concatenation failed to get all data" << std::endl;
			return -1;
		}
		*jumb_buf_size = uint32_t(codestream_data.size());
		*jumb_buf = new unsigned char[codestream_data.size()];
		//memcpy_s(*jumb_buf, size_t(*jumb_buf_size), codestream_data.data(), size_t(codestream_data.size()));
		memcpy(*jumb_buf, codestream_data.data(), size_t(codestream_data.size()));
		codestream_data.clear();
		return 0;
	}

	int db_extract_jumbfs_from_jpg1(unsigned char* jpg_buf, uint64_t jpg_buf_size, std::vector<unsigned char*>& jumbfs_vec, std::vector<uint64_t>& sizes)
	{
		if (jpg_buf == nullptr) {
			return -1;
		}
		unsigned char* jumb_buf = nullptr;
		unsigned char* data = jpg_buf;
		unsigned char last = db_get_byte(&data);
		unsigned char current = db_get_byte(&data);
		if (last != 0xFF || current != (unsigned char)(JpegMarker::M_SOI)) {
			std::cout << "Image is not JPEG" << std::endl;
			return -1;
		}
		last = db_get_byte(&data);
		current = db_get_byte(&data);
		uint32_t previous_En = 0;
		uint32_t previous_Z = 0;
		unsigned Lbox = 0;
		//reading markers;
		while (1)
		{
			if (last != 0xFF)
			{
				std::cout << "Error - Expected a marker\n";
				break;
			}
			else if (current == (unsigned char)(JpegMarker::M_SOS)) {
				break;
			}
			else if (current == (unsigned char)(JpegMarker::M_APP11))
			{
				uint32_t this_app11_header_size{ 10 };
				uint32_t len = db_get_2byte(&data);
				uint32_t CI = db_get_2byte(&data);
				uint32_t this_En = db_get_2byte(&data);
				uint32_t this_Z = db_get_4byte(&data);
				uint32_t this_box_header_size{ 8 };
				uint32_t this_app11_paylaod_size{ 0 };
				uint32_t next_marker{ 0 };
				Lbox = db_get_4byte(&data);
				bool xl_box_present = false;
				if (Lbox == 1)
					xl_box_present = true;
				uint32_t Tbox = db_get_4byte(&data);
				uint64_t box_length = 0;
				if (xl_box_present) {
					uint64_t xl_size = db_get_4byte(&data);
					xl_size = xl_size << 32;
					uint64_t xl_size2 = db_get_4byte(&data);
					box_length = xl_size + xl_size2;
					this_box_header_size += 8;
				}
				else
					box_length = Lbox;
				this_app11_paylaod_size = len - this_app11_header_size - this_box_header_size;
				next_marker = len - this_app11_header_size;
				if (this_En != previous_En && Tbox == box_type_jumb) { // New JUMBF
					//cout << "New JUMBF Detected. => Lbox : " << box_length << endl;
					jumb_buf = new unsigned char[box_length];
					jumbfs_vec.push_back(jumb_buf);
					sizes.push_back(box_length);
					data -= this_box_header_size;
					//memcpy_s(jumb_buf, box_length, data, static_cast<rsize_t>(this_app11_paylaod_size) + this_box_header_size);
					memcpy(jumb_buf, data, static_cast<size_t>(this_app11_paylaod_size) + this_box_header_size);
					jumb_buf += (this_app11_paylaod_size + this_box_header_size);
					data += (this_app11_paylaod_size + this_box_header_size);
				}
				else if (this_En == previous_En && Tbox == uint32_t(0x6a756d62) && this_Z == (previous_Z + 1))
				{
					//memcpy_s(jumb_buf, box_length, data, this_app11_paylaod_size);
					memcpy(jumb_buf, data, this_app11_paylaod_size);
					jumb_buf += this_app11_paylaod_size;
					data += this_app11_paylaod_size;
				}
				else {
					std::cout << "Unrecognized En, and Z value detected in APP11 Marker" << std::endl;
					return -1;
				}
				//data += (len - this_app11_header_size );
				previous_En = this_En;
				previous_Z = this_Z;
			}
			else if (current == (unsigned char)(JpegMarker::M_SOI)) {
				break;
			}
			else if (current == (unsigned char)(JpegMarker::M_EOI)) {
				break;
			}
			else {
				int len = db_get_2byte(&data);
				data += (len - 2);
			}
			last = db_get_byte(&data);
			current = db_get_byte(&data);
		}
		// Now codestream_data has all the concatenated data.
		return 0;
	}




	void db_read_file_bitstream(std::string InputFile, unsigned char** pBuffer, uint64_t* file_size) {
		std::ifstream in_file(InputFile, std::ifstream::binary);
		if (in_file) {
			in_file.seekg(0, in_file.end);
			uint64_t length = uint64_t(in_file.tellg());
			in_file.seekg(0, in_file.beg);
			char* buffer = new char[length];
			in_file.read(buffer, length);
			if (in_file) {
				*pBuffer = (unsigned char*)buffer;
				*file_size = length;
			}
			else
				std::cout << "error: only " << in_file.gcount() << " could be read from input file";
			in_file.close();
		}
		else {
			std::cerr << "Error opening file: " << InputFile << std::endl;
			return;
		}
	}
	bool db_write_file_bitstream(std::string filename, const unsigned char* const data, const uint64_t data_size) {
		try {
			// Open the file in binary mode for writing
			std::ofstream file(filename, std::ios::out | std::ios::binary);
			if (!file.is_open()) {
				std::cerr << "Error opening file: " << filename << std::endl;
				return false;
			}

			// Write the data to the file
			file.write(reinterpret_cast<const char*>(data), static_cast<std::streamsize>(data_size));

			// Check if writing was successful
			if (!file.good()) {
				std::cerr << "Error occurred while writing data to file: " << filename << std::endl;
				return false;
			}

			// Close the file
			file.close();

			return true; // Data successfully written
		}
		catch (const std::exception& e) {
			std::cerr << "Exception occurred: " << e.what() << std::endl;
			return false;
		}

	}


}