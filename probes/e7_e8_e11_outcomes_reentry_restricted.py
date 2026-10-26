import time
from statemachine.io import load
def doc(cond): return f"""<scxml xmlns="http://www.w3.org/2005/07/scxml" version="1.0" initial="IDLE" datamodel="python">
  <datamodel><data id="station" expr="'s1'"/></datamodel>
  <state id="IDLE"><transition event="go" cond="{cond}" target="DOCKING"/></state>
  <state id="DOCKING">
    <transition event="done.invoke.DOCKING" cond="_event.data['status'] == 'succeeded'" target="DOCKED"/>
    <transition event="done.invoke.DOCKING" target="FAILED"/>
    <transition event="error.execution" target="ERR"/>
    <transition event="pause" target="PAUSED"/>
  </state>
  <state id="PAUSED"><transition event="resume" target="DOCKING"/></state>
  <state id="DOCKED"/><state id="FAILED"/><state id="ERR"/></scxml>"""
class Model:
    station = 's1'
    def ready(self, station=None, **kw): return True
class L:
    def __init__(s, mode): s.mode, s.calls = mode, 0
    def on_invoke_DOCKING(s, ctx=None, **kw):
        s.calls += 1
        for _ in range(6):
            if ctx.cancelled.is_set(): return None
            time.sleep(0.05)
        if s.mode == 'raise': raise RuntimeError('boom')
        return {'status': s.mode}
for trusted, cond, how in [(False,'ready','listener'),(False,'ready','model'),(True,'ready(station)','model'),(True,'model.ready(station)','model'),(False,"station == 's1'",'listener')]:
    try: cls = load(doc(cond), format="scxml", trusted=trusted)
    except Exception as e: print(trusted, cond, how, 'LOAD', str(e)[:100]); continue
    for mode in ('succeeded','aborted','raise'):
        l = L(mode)
        sm = cls(model=Model(), listeners=[l]) if how=='model' else cls(listeners=[l, Model()])
        sm.send('go'); time.sleep(0.6)
        print(trusted, repr(cond), how, mode, '->', list(sm.configuration_values), l.calls)
    l = L('succeeded'); sm = cls(listeners=[l, Model()]) if how!='model' else cls(model=Model(), listeners=[l])
    sm.send('go'); time.sleep(0.1); sm.send('pause'); sm.send('resume'); time.sleep(0.6)
    print('   pause/resume ->', list(sm.configuration_values), 'invokes', l.calls)
