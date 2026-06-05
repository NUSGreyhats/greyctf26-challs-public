# CMakeList.txt : CMake project for dbench_jumbf, include source and define
# project specific logic here.
#

# Add source to this project's executable.
file(GLOB SRCS "src/*.cpp")
file(GLOB_RECURSE HDRS "include/*.h")
add_library(dbench_jumbf 
	${SRCS}
	${HDRS}
)

target_include_directories(dbench_jumbf PUBLIC "${CMAKE_SOURCE_DIR}/dbench_jumbf/include")

if (CMAKE_VERSION VERSION_GREATER 3.12)
  set_property(TARGET dbench_jumbf PROPERTY CXX_STANDARD 14)
endif()

# TODO: Add tests and install targets if needed.
