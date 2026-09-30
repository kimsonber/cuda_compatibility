file(READ "${INPUT_FILE}" file_content HEX)

string(REGEX MATCHALL ".." hex_bytes "${file_content}")

set(out_content "const unsigned char help_data[] = {\n  ")
foreach(byte IN LISTS hex_bytes)
    string(APPEND out_content "0x${byte}, ")
endforeach()
string(APPEND out_content "\n};\n")

list(LENGTH hex_bytes out_len)
string(APPEND out_content "const unsigned int help_data_len = ${out_len};\n")

file(WRITE "${OUTPUT_FILE}" "${out_content}")
