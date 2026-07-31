cmake_minimum_required(VERSION 3.18)

set(GEN_INC "${CMAKE_CURRENT_BINARY_DIR}/include")
file(MAKE_DIRECTORY "${GEN_INC}")
set(GENERATED_CPP "${GEN_INC}/wrapper_gen.hpp")
set(EMBED_INPUT "${CMAKE_CURRENT_SOURCE_DIR}/help.txt")
set(EMBED_OUTPUT "${CMAKE_CURRENT_BINARY_DIR}/include/help_data.h")
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
set(GEN_HELP_SCRIPT "${CMAKE_CURRENT_SOURCE_DIR}/cmake_gen_help.cmake")

find_package(Python3 COMPONENTS Interpreter REQUIRED)

add_custom_command(
    OUTPUT "${GENERATED_CPP}"
    COMMAND ${CMAKE_COMMAND} -E echo "Generating wrapper source..."
    COMMAND ${Python3_EXECUTABLE} "${CMAKE_CURRENT_SOURCE_DIR}/../../../binary_wrapper/wrapper_generator/wrapper_gen.py"
            --config "${CMAKE_CURRENT_SOURCE_DIR}/wrapper_config.json"
            --output "${GEN_INC}"
    DEPENDS
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../binary_wrapper/wrapper_generator/wrapper_gen.py"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../binary_wrapper/wrapper_generator/wrapper_template.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/wrapper_config.json"
    COMMENT "Running wrapper generator script"
    VERBATIM
)

add_custom_command(
    OUTPUT  ${EMBED_OUTPUT}
    COMMAND ${CMAKE_COMMAND}
            -DINPUT_FILE=${EMBED_INPUT}
            -DOUTPUT_FILE=${EMBED_OUTPUT}
            -P ${GEN_HELP_SCRIPT}
    WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
    DEPENDS ${EMBED_INPUT} ${GEN_HELP_SCRIPT}
    VERBATIM
)

add_executable(nvcc
    "${GENERATED_CPP}"
    ${EMBED_OUTPUT}
    nvcc_wrapper.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../utils/utils.cpp
)

target_link_libraries(nvcc PRIVATE dl)

target_include_directories(nvcc PRIVATE
    "${GEN_INC}"
    "${CMAKE_CURRENT_SOURCE_DIR}/../utils"
)

install(TARGETS nvcc
    RUNTIME DESTINATION ${CMAKE_INSTALL_PREFIX}
)
