cmake_minimum_required(VERSION 3.14)
project(python_statemachine_vendor NONE)

find_package(ament_cmake REQUIRED)
find_package(ament_cmake_python REQUIRED)

# python-statemachine, used as released. Raise the version only together with
# the engine tests in statechart_ros/test/engine passing (docs/ENGINE.md).
set(PSM_VERSION "3.2.2")
set(PSM_WHEEL "python_statemachine-${PSM_VERSION}-py3-none-any.whl")
set(PSM_URL "https://files.pythonhosted.org/packages/85/d1/d722672f4bfbe1176588157e0f9fa6dd5331a71922bed36aca0e79271535/${PSM_WHEEL}")
set(PSM_SHA256 "141d20e00776815692e424d3df825b1bd7ccaeedc6fda7787ddf249e767e1676")

set(PYTHON_STATEMACHINE_WHEEL "" CACHE FILEPATH
  "A local copy of ${PSM_WHEEL}, used instead of downloading it (offline builds)")

set(_wheel "${CMAKE_CURRENT_BINARY_DIR}/${PSM_WHEEL}")
if(PYTHON_STATEMACHINE_WHEEL)
  configure_file("${PYTHON_STATEMACHINE_WHEEL}" "${_wheel}" COPYONLY)
elseif(NOT EXISTS "${_wheel}")
  file(DOWNLOAD "${PSM_URL}" "${_wheel}" TLS_VERIFY ON STATUS _status)
  list(GET _status 0 _code)
  if(NOT _code EQUAL 0)
    file(REMOVE "${_wheel}")
    message(FATAL_ERROR "Downloading ${PSM_URL} failed: ${_status}")
  endif()
endif()
file(SHA256 "${_wheel}" _sha)
if(NOT _sha STREQUAL PSM_SHA256)
  message(FATAL_ERROR "${_wheel}: SHA256 ${_sha}, expected ${PSM_SHA256}")
endif()

# A pure-Python wheel is a zip of the package and its metadata: unpacking it
# into site-packages is a complete installation.
set(_unpacked "${CMAKE_CURRENT_BINARY_DIR}/wheel")
file(REMOVE_RECURSE "${_unpacked}")
file(ARCHIVE_EXTRACT INPUT "${_wheel}" DESTINATION "${_unpacked}")

ament_get_python_install_dir(_python_install_dir)
install(DIRECTORY "${_unpacked}/statemachine"
  DESTINATION "${_python_install_dir}"
  PATTERN "__pycache__" EXCLUDE)
install(DIRECTORY "${_unpacked}/python_statemachine-${PSM_VERSION}.dist-info"
  DESTINATION "${_python_install_dir}")
install(FILES "${_unpacked}/python_statemachine-${PSM_VERSION}.dist-info/licenses/LICENSE"
  DESTINATION "share/${PROJECT_NAME}"
  RENAME "LICENSE.python-statemachine")

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
