CXX      = g++
# PIE + full RELRO + stack canary + NX (all defaults on Debian bookworm)
CXXFLAGS = -std=c++17 -g -O0
LDFLAGS  = -Wl,-z,relro,-z,now
INCLUDES = -Idbench_jumbf/include
LIB_SRCS = $(wildcard dbench_jumbf/src/*.cpp)

server: server.cpp $(LIB_SRCS)
	$(CXX) $(CXXFLAGS) $(LDFLAGS) $(INCLUDES) -o $@ $^
