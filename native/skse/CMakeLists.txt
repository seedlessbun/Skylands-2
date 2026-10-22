cmake_minimum_required(VERSION 3.21)
project(SkylandsNative VERSION 1.0.0 LANGUAGES CXX)

# Built by .github/workflows/skse-plugin.yml (MSVC + vcpkg). alandtse/CommonLibSSE-NG is cloned next to this folder by the workflow
# (or pass -DCOMMONLIB_DIR=<path to a CommonLibSSE-NG checkout>).
set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>DLL")
set(BUILD_TESTS OFF CACHE BOOL "" FORCE)
# all three runtimes stay on (the default): the prebuilt CommonLibSSE-NG library is built that way and its headers differ per runtime set

if(NOT COMMONLIB_DIR)
  set(COMMONLIB_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../../ext/CommonLibSSE-NG")
endif()
add_subdirectory("${COMMONLIB_DIR}" "${CMAKE_CURRENT_BINARY_DIR}/commonlib" EXCLUDE_FROM_ALL)

add_library(SkylandsNative SHARED src/main.cpp)
target_link_libraries(SkylandsNative PRIVATE CommonLibSSE::CommonLibSSE)
target_precompile_headers(SkylandsNative PRIVATE src/PCH.h)
set_target_properties(SkylandsNative PROPERTIES OUTPUT_NAME "SkylandsNative")
if(MSVC)
  target_compile_options(SkylandsNative PRIVATE /permissive- /Zc:preprocessor /EHsc /W3)
endif()
