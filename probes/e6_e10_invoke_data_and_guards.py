import time
from statemachine.io import load
SC = """<scxml xmlns="http://www.w3.org/2005/07/scxml" version="1.0" initial="IDLE" datamodel="python">
  <datamodel><data id="seen" expr="None"/></datamodel>
  <state id="IDLE"><transition event="go" cond="ready" target="DOCKING"/></state>
  <state id="DOCKING">
    <transition event="done.invoke.DOCKING" target="DONE"><assign location="seen" expr="_event.data"/></transition>
  </state>
  <state id="DONE"/></scxml>"""
class Model:
    def ready(self, **kw): return True
class L:
    def on_invoke_DOCKING(self, ctx=None, **kw): return {'status': 'succeeded', 'code': 0}
    def after_transition(self, event=None, source=None, target=None, **kw):
        print('  ', event, source.id if source else None, '->', target.id if target else None, {k: v for k, v in kw.items() if k in ('data',)})
for trusted in (False, True):
    m = Model(); cls = load(SC, format="scxml", trusted=trusted); sm = cls(model=m, listeners=[L()])
    sm.send('go')
    for _ in range(40):
        if 'DONE' in sm.configuration_values: break
        time.sleep(0.05)
    print('trusted', trusted, list(sm.configuration_values), 'seen =', repr(getattr(m, 'seen', getattr(sm, 'seen', '?'))))
