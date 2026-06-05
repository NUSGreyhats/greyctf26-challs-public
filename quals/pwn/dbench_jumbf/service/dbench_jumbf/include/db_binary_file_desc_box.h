#pragma once

#include "db_box.h"
#include "dbench_jumbf.h"

namespace dbench {

	class DbFileDescBox : public DbBox
	{
	public:
		DbFileDescBox();
		~DbFileDescBox();

		DbFileDescBox(std::string media_type_v, std::string file_name_v, bool ext_ref);
		void set_box(std::string media_type_v, std::string file_name_v, bool ext_ref);
		void set_file_name(std::string file_name_v);
		void set_external_reference(bool ext_ref);
		std::string get_file_name();
		void set_media_type(std::string mediatype);
		std::string get_media_type();
		void set_box_size();
		uint64_t get_box_size();
		bool is_externally_referenced();
		unsigned char get_toggle_byte();
		void deserialize(unsigned char* buf, uint64_t buf_size);
	private:
		unsigned char toggles_{ 0x00 };
		std::string media_type_{ "" };
		std::string file_name_{ "" };
		bool filename_present_{ false };
		bool external_ref_{ false };
	};



}