#pragma once

#include "db_box.h"
#include "dbench_jumbf.h"

namespace dbench {

	class DbUuidBox : public DbBox
	{
	public:
		DbUuidBox();
		~DbUuidBox();

		DbUuidBox(unsigned char* uuid, unsigned char* uuid_payload, uint64_t uuid_payload_size);
		void set_box(unsigned char* uuid, unsigned char* uuid_payload, uint64_t uuid_payload_size);
		void set_uuid(unsigned char* uuid);
		void set_uuid_paylaod(unsigned char* paylaod_data, uint64_t payload_size);

		void set_box_size();
		uint64_t get_box_size();
		void deserialize(unsigned char* in_buf, uint64_t in_buf_size);
		unsigned char* get_uuid();

	private:
		unsigned char uuid_[16]{ 0 };
	};



}