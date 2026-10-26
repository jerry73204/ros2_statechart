cmake_minimum_required(VERSION 3.8)
project(statechart_ros_msgs)

find_package(ament_cmake REQUIRED)
find_package(builtin_interfaces REQUIRED)
find_package(rosidl_default_generators REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/DataValue.msg"
  "msg/InvokeStatus.msg"
  "msg/StateInfo.msg"
  "msg/StatechartStatus.msg"
  "msg/StatechartStructure.msg"
  "msg/Transition.msg"
  "msg/TransitionInfo.msg"
  "srv/GetStructure.srv"
  "srv/SendEvent.srv"
  "action/RunStatechart.action"
  DEPENDENCIES builtin_interfaces
)

ament_export_dependencies(rosidl_default_runtime)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
