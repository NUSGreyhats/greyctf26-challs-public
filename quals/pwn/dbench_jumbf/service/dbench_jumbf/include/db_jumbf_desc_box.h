#pragma once

#include "dbench_jumbf.h"
#include "db_box.h"

namespace dbench {
	class DbJumbDescBox : public DbBox
	{
	public:
		DbJumbDescBox();
		~DbJumbDescBox();

	private:
		// pointer to 16 bytes  type uuid
		unsigned char type_uuid_[16]{ 0 };

		// 1 byte toggle
		unsigned char toggles_ = 0;

		bool requestable_ = false;

		bool label_present_ = false;
		std::string label_ = "";
		uint32_t lable_size_ = 0;

		bool id_present_ = false;
		uint32_t id_ = 0;

		// hash == signature
		bool hash_present_ = false;
		unsigned char* hash_ = nullptr;

		bool private_present_ = false;
		DbBox* private_box_{ nullptr };


		void set_requestable_bit_ON();
		void set_label_toggle_bit_ON();
		void set_id_toggle_bit_ON();
		void set_hash_toggle_bit_ON();
		void set_private_toggle_bit_ON();

	protected:

	public:
		DbJumbDescBox(const unsigned char* content_type_in);
		DbJumbDescBox(const unsigned char* content_type_in, std::string label);
		DbJumbDescBox(const unsigned char* content_type_in, std::string label, uint32_t ID);
		DbJumbDescBox(const unsigned char* content_type_in, std::string label, uint32_t ID, unsigned char* hash);
		DbJumbDescBox(const unsigned char* content_type_in, std::string label, uint32_t ID, unsigned char* hash, DbBox* priv_box);


		void set_box(const unsigned char* typein, bool requestable, std::string label, bool id_present, uint32_t ID, unsigned char* hash, DbBox* priv_box);

		void set_box_size(); 
		void set_content_type(const unsigned char* type);
		unsigned char* get_jumb_content_type();
		void set_type_16bytes(const unsigned char* type);
		unsigned char* get_type_16bytes();

		void set_toggles_byte(unsigned char byte);
		unsigned char get_toggles_byte();

		bool is_requestable();
		void set_requestable(bool on_off);

		bool is_label_present();
		void set_label(std::string label);
		std::string get_label();

		bool is_id_present();
		void set_id(uint32_t id);
		uint32_t get_id();

		bool is_hash_present();
		void set_hash(unsigned char* hs);
		unsigned char* get_hash();


		bool is_private_box_present();
		void set_private_box(DbBox* priv_box);
		DbBox* get_private_box();

		void deserialize(unsigned char* in_jumd_buf, uint64_t in_buf_size);

	};



}