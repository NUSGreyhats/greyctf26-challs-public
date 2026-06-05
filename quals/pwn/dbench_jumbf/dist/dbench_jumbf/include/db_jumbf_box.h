#pragma once

#include <list>
#include "dbench_jumbf.h"
#include "db_box.h"
#include "db_jumbf_desc_box.h"
#include "db_free_box.h"

namespace dbench {
	class DbJumbBox : public DbBox
	{
	public:
		DbJumbBox();
		~DbJumbBox();
		DbJumbBox(DbJumbDescBox ds_box);
		DbJumbBox(DbJumbDescBox ds_box, DbFreeBox fre_box);

		void set_jumbf_description_box(DbJumbDescBox desc_box_in);
		void insert_content_box(DbBox box_in);
		void set_free_box(DbFreeBox free_box);
		void set_box_size();
		unsigned char* get_jumb_content_type();

		void deserialize(unsigned char* in_box_buf, uint64_t in_buf_size);

		DbJumbDescBox desc_box_;
		std::list<DbBox> content_boxes_;
		DbFreeBox padding_box_;
		bool padding_box_present_ = false;
	};

}