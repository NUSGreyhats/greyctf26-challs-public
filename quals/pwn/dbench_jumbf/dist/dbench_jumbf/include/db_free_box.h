#pragma once

#include "dbench_jumbf.h"
#include "db_box.h"

namespace dbench {
	class DbFreeBox : public DbBox
	{
	public:
		DbFreeBox();
		DbFreeBox(uint64_t no_of_padding_bytes);
		~DbFreeBox();

		void set_box(uint64_t no_of_padding_bytes);

	};

}