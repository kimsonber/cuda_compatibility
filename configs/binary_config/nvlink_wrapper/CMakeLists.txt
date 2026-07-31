cmake_minimum_required(VERSION 3.18)

set(GEN_INC "${CMAKE_CURRENT_BINARY_DIR}/include")
file(MAKE_DIRECTORY "${GEN_INC}")
set(GENERATED_CPP "${GEN_INC}/wrapper_gen.hpp")
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

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

add_executable(nvlink
    "${GENERATED_CPP}"
    nvlink_wrapper.cpp
)

target_include_directories(nvlink PRIVATE
    "${GEN_INC}"
)

install(TARGETS nvlink
    RUNTIME DESTINATION ${CMAKE_INSTALL_PREFIX}
)
