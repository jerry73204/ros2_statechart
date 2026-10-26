import time
from statemachine.io import load
SC = """<scxml xmlns="http://www.w3.org/2005/07/scxml" xmlns:ros="urn:ros2-statechart" version="1.0" initial="idle" datamodel="python">
  <state id="idle"><transition event="go" target="docking"/></state>
  <state id="docking">
    <ros:action server="dock_robot" type="nav2_msgs/action/DockRobot" goal="dock_goal(station)"/>
    <transition event="done.invoke.docking" target="docked"/>
    <transition event="error.execution" target="failed"/>
    <transition event="pause" target="idle"/>
  </state>
  <state id="docked"/><state id="failed"/>
</scxml>"""
try:
    cls = load(SC, format="scxml")
    print("foreign element accepted")
except Exception as e:
    print("foreign element:", type(e).__name__, e); raise SystemExit
class L:
    def __init__(self): self.cancelled = False
    def on_invoke_docking(self, ctx=None, **kw):
        for _ in range(20):
            if ctx is not None and ctx.cancelled.is_set():
                print("  handler saw cancel"); return None
            time.sleep(0.05)
        return {"ok": True}
    def on_enter_state(self, target=None, **kw): print("  enter", target.id if target else None)
sm = cls(listeners=[L()])
sm.send("go"); time.sleep(1.5); print("config", list(sm.configuration_values))
sm2 = cls(listeners=[L()]); sm2.send("go"); time.sleep(0.2); sm2.send("pause"); time.sleep(0.3); print("config2", list(sm2.configuration_values))
print("unhandled:", sm2.send("nonsense"), list(sm2.configuration_values))
