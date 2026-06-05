#include "db_box.h"
#include <cstring> 
namespace dbench {
	DbBox::DbBox()
	{
	}

	DbBox::~DbBox()
	{

	}


	DbBox::DbBox(std::string box_type_str)
	{
		set_box_type(box_type_str);
	}

	DbBox::DbBox(std::string box_type_str, unsigned char* paylaod_ptr, uint64_t payload_size)
	{
		set_box_type(box_type_str);
		payload_ = paylaod_ptr;
		payload_size_ = payload_size;
		set_box_size();
	}

	void DbBox::set_box(std::string box_type_str, unsigned char* paylaod_ptr, uint64_t payload_size)
	{
		set_box_type(box_type_str);
		payload_ = paylaod_ptr;
		payload_size_ = payload_size;
		set_box_size();
	}

	void DbBox::set_box(uint32_t box_type_in, unsigned char* paylaod_ptr, uint64_t payload_size)
	{
		set_tbox(box_type_in);
		payload_ = paylaod_ptr;
		payload_size_ = payload_size;
		set_box_size();
	}

	void DbBox::set_box_payload(unsigned char* paylaod_ptr, uint64_t paylaod_size)
	{
		payload_ = paylaod_ptr;
		payload_size_ = paylaod_size;
		set_box_size();
	}

	void DbBox::set_payload(unsigned char* paylaod_ptr)
	{
		payload_ = paylaod_ptr;
	}

	void DbBox::set_payload_size(uint64_t size)
	{
		payload_size_ = size;
	}


	uint32_t DbBox::get_lbox()
	{
		return this->lbox_;
	}

	void DbBox::set_tbox(const uint32_t type)
	{
		this->tbox_ = type;
		this->tbox_str_ = uint32_to_ASCII(type);
	}
	uint32_t DbBox::get_tbox()
	{
		return this->tbox_;
	}


	void DbBox::set_box_type(std::string type)
	{
		this->set_tbox(box_type_str_to_uint32(type));
	}


	std::string DbBox::get_box_type_str()
	{
		return uint32_to_ASCII(this->tbox_);
	}


	void DbBox::set_box_size()
	{
		box_size_ = 8 + payload_size_;
		if (box_size_ > MAX_32BIT_UINT_VALUE)
		{
			lbox_ = 1;
			xl_box_ = box_size_;
			xl_box_present_ = true;
		}
		else {
			lbox_ = static_cast<uint32_t>(box_size_);
			xl_box_present_ = false;
		}
	}

	uint64_t DbBox::get_box_size()
	{
		return this->box_size_;
	}


	bool DbBox::is_xl_box_present()
	{
		return this->xl_box_present_;
	}
	uint64_t DbBox::get_xl_box()
	{
		return this->xl_box_;
	}

	unsigned char* DbBox::get_payload()
	{
		return payload_;
	}

	uint64_t DbBox::get_payload_size()
	{
		uint64_t boxsize = get_box_size();
		if (xl_box_present_)
			return (boxsize - 16);
		else
			return (boxsize - 8);
	}


	void DbBox::deserialize(unsigned char* in_box_buf, uint64_t in_buf_size)
	{
		unsigned char* buf = in_box_buf;
		uint64_t header_size{ 8 };
		lbox_ = db_get_4byte(&buf);
		tbox_ = db_get_4byte(&buf);
		tbox_str_ = uint32_to_ASCII(tbox_);
		if (lbox_ == 1) {
			xl_box_ = db_get_8byte(&buf);
			xl_box_present_ = true;
			header_size += 8;
			box_size_ = xl_box_;
		}
		else if (lbox_ == 0) {
			box_size_ = in_buf_size;
		}
		else
			box_size_ = lbox_;

		payload_ = buf;
		payload_size_ = box_size_ - header_size;
	}

}