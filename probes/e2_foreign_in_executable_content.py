import time
from statemachine.io import load
SC = """<scxml xmlns="http://www.w3.org/2005/07/scxml" xmlns:ros="urn:ros2-statechart" version="1.0" initial="idle" datamodel="python">
  <ros:subscribe topic="/health" event="fault"/>
  <datamodel><data id="n" expr="0"/></datamodel>
  <state id="idle">
    <onentry><ros:publish topic="/dock/hold" value="False"/><assign location="n" expr="n + 1"/></onentry>
    <transition event="go" target="busy"><ros:publish topic="/x" value="1"/></transition>
  </state>
  <state id="busy"/>
</scxml>"""
cls = load(SC, format="scxml"); sm = cls(); sm.send("go"); time.sleep(0.1)
print("ok", list(sm.configuration_values), "n =", sm.model.n if hasattr(sm,'model') and hasattr(sm.model,'n') else getattr(sm,'n','?'))
