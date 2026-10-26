# Viewer tests in a browser

`browser_viewer.py` drives the viewer page in headless Chromium with
Playwright: the page loads, receives a structure and a status, highlights
the active states, sends events, shows refusals, travels back in the log,
loads nothing from outside the viewer, and replays a bag of the patrol
example with the right highlighting. CI runs it in the job "viewer in a
headless browser"; colcon test does not collect it (the file name does not
start with `test_`).

```bash
pip install playwright && playwright install --with-deps chromium
python3 -m pytest statechart_ros_viewer/test_browser/browser_viewer.py
```
