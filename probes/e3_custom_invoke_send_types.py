import time
from statemachine.io import load
for name, body in [
 ("invoke type", '<invoke id="dock" type="ros2:action"><param name="server" expr="\'dock_robot\'"/></invoke>'),
 ("send type", '<onentry><send event="x" type="ros2:topic" target="/dock/hold"/></onentry>'),
]:
    SC = f"""<scxml xmlns="http://www.w3.org/2005/07/scxml" version="1.0" initial="idle" datamodel="python">
  <state id="idle"><transition event="go" target="docking"/></state>
  <state id="docking">{body}
    <transition event="error.execution" target="failed"/><transition event="error.communication" target="failed"/></state>
  <state id="failed"/></scxml>"""
    try:
        cls = load(SC, format="scxml"); sm = cls(); sm.send("go"); time.sleep(0.3)
        print(name, "-> loads; config after go:", list(sm.configuration_values))
    except Exception as e:
        print(name, "-> load error:", type(e).__name__, str(e)[:150])
