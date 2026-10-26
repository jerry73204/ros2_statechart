# Copyright 2026 The ros2_statechart Authors
# SPDX-License-Identifier: Apache-2.0
cmake_minimum_required(VERSION 3.16)
project(qt_load CXX)
set(CMAKE_CXX_STANDARD 17)
find_package(Qt6 REQUIRED COMPONENTS Core Scxml)
add_executable(qt_load qt_load.cpp)
target_link_libraries(qt_load Qt6::Core Qt6::Scxml)
