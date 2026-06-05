
#include "db_binary_file_desc_box.h"

namespace dbench {

	DbFileDescBox::DbFileDescBox()
	{
		set_box_type("bfdb");
	}

	DbFileDescBox::~DbFileDescBox()
	{
	}



	DbFileDescBox::DbFileDescBox(std::string media_type_v, std::string file_name_v, bool ext_ref)
	{
		this->set_box(media_type_v, file_name_v, ext_ref);
	}

	void DbFileDescBox::set_box(std::string media_type_v, std::string file_name_v, bool ext_ref)
	{
		this->set_box_type("bfdb");
		this->set_media_type(media_type_v);
		this->set_file_name(file_name_v);
		this->set_external_reference(ext_ref);
		this->set_box_size();
	}

	void DbFileDescBox::set_file_name(std::string file_name_v)
	{
		if (!file_name_v.empty()) {
			file_name_ = file_name_v;
			toggles_ = toggles_ | 0x01;
			filename_present_ = true;
		}
		set_box_size();
	}

	void DbFileDescBox::set_external_reference(bool ext_ref)
	{
		if (ext_ref) {
			external_ref_ = true;
			toggles_ = toggles_ | 0x02;
		}
		else {
			external_ref_ = false;
			toggles_ = toggles_ & 0xFD; // and with 1111 1101
		}
	}

	std::string DbFileDescBox::get_file_name()
	{
		return file_name_;
	}

	void DbFileDescBox::set_media_type(std::string mediatype)
	{
		if (!mediatype.empty()) {
			media_type_ = mediatype;
		}
		else {
			throw std::runtime_error("Error: Media Type should is empty.");
		}
		set_box_size();
	}

	std::string DbFileDescBox::get_media_type()
	{
		return media_type_;
	}

	void DbFileDescBox::set_box_size()
	{
		box_size_ = 9; // lbox + tbox + 1 toggle
		box_size_ += (media_type_.size() + 1); // +1 for null character
		if (!file_name_.empty()) {
			box_size_ += (file_name_.size() + 1); // +1 for null character
		}

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

	uint64_t DbFileDescBox::get_box_size()
	{
		set_box_size();
		return box_size_;
	}

	bool DbFileDescBox::is_externally_referenced()
	{
		return external_ref_;
	}

	unsigned char DbFileDescBox::get_toggle_byte()
	{
		return toggles_;
	}


	void DbFileDescBox::deserialize(unsigned char* in_box_buf, uint64_t in_buf_size)
	{
		unsigned char* buf = in_box_buf;
		uint64_t header_size{ 8 };
		lbox_ = db_get_4byte(&buf);
		tbox_ = db_get_4byte(&buf);
		if (tbox_ != box_type_bfdb) {
			throw std::runtime_error("Error: De-Serializing BFDB, input buffer is not BFDB buffer.");
			return;
		}
		tbox_str_ = "bfdb";
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

		toggles_ = db_get_byte(&buf);

		filename_present_ = isNthBitSet_1(toggles_, 1);
		external_ref_ = isNthBitSet_1(toggles_, 2);

		std::vector<unsigned char> media_type;
		for (uint32_t k = 0; ; ++k) { // will go to null character
			unsigned char a = db_get_byte(&buf);
			media_type.push_back(a);
			if (a == 0x00)
				break;
		}
		std::string s(media_type.begin(), media_type.end() - 1); // -1 for removing null character. as it is attached again by set_lable function
		media_type_ = s;

		if (filename_present_) {
			std::vector<unsigned char> filename;
			for (uint32_t k = 0; ; ++k) { // will go to null character
				unsigned char a = db_get_byte(&buf);
				filename.push_back(a);
				if (a == 0x00)
					break;
			}
			std::string s(filename.begin(), filename.end() - 1); // -1 for removing null character. as it is attached again by set_lable function
			file_name_ = s;
		}
	}

}
