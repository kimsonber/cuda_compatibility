cmake_minimum_required(VERSION 3.18)
project(BinaryWrappers C CXX)


option(CUDA_FULL_VERSION "Set version string" "")
if(NOT CUDA_FULL_VERSION)
    if(NOT CUDA_VERSION)
        set(CUDA_FULL_VERSION "cuda-11.6.0")
    else()
        set(CUDA_FULL_VERSION "${CUDA_VERSION}.0")
    endif()
endif()
string(REPLACE "cuda-" "" VERSION_NUMBERS ${CUDA_FULL_VERSION})
string(REGEX MATCH "^([0-9]+)\\.([0-9]+)\\.([0-9]+)$" VERSION_MATCH ${VERSION_NUMBERS})
if(CMAKE_MATCH_0)
    set(CUDA_VER_MAJOR ${CMAKE_MATCH_1})
    set(CUDA_VER_MINOR ${CMAKE_MATCH_2})
    set(CUDA_VER_BUILD ${CMAKE_MATCH_3})
else()
    message(FATAL_ERROR "CUDA_FULL_VERSION \"${CUDA_FULL_VERSION}\"format is incorrect.")
endif()

add_definitions(
    -DCUDA_VER_MAJOR=${CUDA_VER_MAJOR}
    -DCUDA_VER_MINOR=${CUDA_VER_MINOR}
    -DCUDA_VER_BUILD=${CUDA_VER_BUILD}
    -DCUDA_VERSION=${CUDA_VERSION}
)

# Add subdirectories
add_subdirectory(nvcc_wrapper)
add_subdirectory(nvprune_wrapper)
add_subdirectory(ptxas_wrapper)
add_subdirectory(nvlink_wrapper)
