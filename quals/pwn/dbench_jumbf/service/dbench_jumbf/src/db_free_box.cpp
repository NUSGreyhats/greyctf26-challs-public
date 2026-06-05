

#include "db_free_box.h"
#include <string.h>

namespace dbench {
	DbFreeBox::DbFreeBox()
	{
		set_box_type("free");
	}
	DbFreeBox::DbFreeBox(uint64_t no_of_padding_bytes)
	{
		set_box_type("free");
		set_box(no_of_padding_bytes);
	}
	DbFreeBox::~DbFreeBox()
	{
	}
	void DbFreeBox::set_box(uint64_t no_of_padding_bytes)
	{
		payload_ = new unsigned char[no_of_padding_bytes];
		memset(payload_, 0x00, no_of_padding_bytes);
		payload_size_ = no_of_padding_bytes;
		set_box_size();
	}
}