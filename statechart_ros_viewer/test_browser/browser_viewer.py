# Copyright 2026 The ros2_statechart Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""
The viewer page in a headless browser (Playwright, Chromium).

Run by the CI job "viewer in a browser", not by colcon test (the file name
does not start with test_): it needs Playwright and its Chromium.

    pip install playwright && playwright install --with-deps chromium
    python3 -m pytest statechart_ros_viewer/test_browser/browser_viewer.py
"""

import os
import signal
import subprocess
import sys
import threading
import time

from playwright.sync_api import expect, sync_playwright
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'test'))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'statechart_ros_nav2', 'test'))

from statechart_ros.spin import spin  # noqa: E402
from viewer_util import CHART, Setup, wait_for, write_composed  # noqa: E402


def active_ids(page):
    return set(page.eval_on_selector_all('#diagram .active[data-id]',
                                         'els => els.map(e => e.dataset.id)'))


@pytest.fixture(scope='module')
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def setup(tmp_path_factory):
    path = tmp_path_factory.mktemp('browser') / 'demo.scxml'
    path.write_text(CHART)
    s = Setup(path)
    yield s
    s.close()


def test_page_shows_structure_and_live_state(setup, browser):
    page = browser.new_page()
    requests = []
    page.on('request', lambda r: requests.append(r.url))
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto(setup.url + '/#/demo')
    expect(page.locator('#diagram [data-id="IDLE"]')).to_be_visible(timeout=15000)
    assert wait_for(lambda: active_ids(page) == {'run', 'mode', 'AUTO', 'task', 'IDLE'})
    expect(page.locator('#connection')).to_have_text('live')
    assert page.locator('#diagram .cluster.parallel[data-id="run"]').count() == 1
    expect(page.locator('#diagram [data-id="BUSY"] text.note')).to_have_text(
        'after: timeout after 30 s')

    # Send an event from the page: the highlight follows, the log grows.
    expect(page.locator('#send-section')).to_be_visible()
    page.select_option('#send-event', 'go')
    page.click('#send-form button')
    expect(page.locator('#send-answer')).to_have_text('handled')
    assert wait_for(lambda: active_ids(page) == {'run', 'mode', 'AUTO', 'task', 'BUSY'})
    expect(page.locator('#log li').first).to_contain_text('go')
    expect(page.locator('#data td').nth(1)).to_have_text('1')

    # A refusal shows in the answer and in the log.
    page.select_option('#send-event', 'pause')
    page.click('#send-form button')
    expect(page.locator('#send-answer')).to_have_text('handled')
    page.click('#send-form button')
    expect(page.locator('#send-answer')).to_have_text('refused: already paused')
    expect(page.locator('#log li.refused').first).to_contain_text('already paused')
    assert wait_for(lambda: 'PAUSED' in active_ids(page))

    # Time travel: click the "go" entry, then change the live state.
    page.locator('#log li', has_text='go').first.click()
    expect(page.locator('#past-banner')).to_be_visible()
    assert active_ids(page) == {'run', 'mode', 'AUTO', 'task', 'BUSY'}
    page.select_option('#send-event', 'resume')
    page.click('#send-form button')
    page.select_option('#send-event', 'go')
    page.click('#send-form button')
    time.sleep(0.5)
    assert active_ids(page) == {'run', 'mode', 'AUTO', 'task', 'BUSY'}
    page.click('#live-button')
    assert wait_for(lambda: active_ids(page) == {'run', 'mode', 'AUTO', 'task', 'IDLE'})

    # Everything came from the viewer itself.
    assert requests and all(u.startswith(setup.url) for u in requests), requests
    assert errors == []
    page.close()


def test_fold_states_and_hide_notes(setup, browser):
    page = browser.new_page()
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto(setup.url + '/#/demo')
    expect(page.locator('#diagram [data-id="IDLE"]')).to_be_visible(timeout=15000)
    assert wait_for(lambda: 'IDLE' in active_ids(page))

    # Notes: on for a small chart, and switched off from the header.
    expect(page.locator('#notes-toggle')).to_be_checked()
    expect(page.locator('#diagram [data-id="BUSY"] text.note')).to_have_count(1)
    page.uncheck('#notes-toggle')
    expect(page.locator('#diagram [data-id="BUSY"] text.note')).to_have_count(0)

    # Double-click a compound state: one box, still lit while it is active.
    page.locator('#diagram .cluster[data-id="task"] > rect').dblclick(position={'x': 6, 'y': 6})
    expect(page.locator('#diagram .state.collapsed[data-id="task"]')).to_be_visible()
    expect(page.locator('#diagram [data-id="IDLE"]')).to_have_count(0)
    assert wait_for(lambda: 'task' in active_ids(page))
    page.select_option('#send-event', 'go')
    page.click('#send-form button')
    expect(page.locator('#log li').first).to_contain_text('go')
    assert 'task' in active_ids(page)

    # Remembered in this browser, per chart.
    page.reload()
    expect(page.locator('#diagram .state.collapsed[data-id="task"]')).to_be_visible(timeout=15000)
    expect(page.locator('#notes-toggle')).not_to_be_checked()
    page.locator('#diagram .state.collapsed[data-id="task"] > rect').dblclick()
    expect(page.locator('#diagram [data-id="BUSY"]')).to_be_visible()
    page.locator('#diagram .cluster[data-id="mode"] > rect').dblclick(position={'x': 6, 'y': 6})
    page.click('#expand-button')
    expect(page.locator('#diagram [data-id="AUTO"]')).to_be_visible()
    page.check('#notes-toggle')
    page.click('#fit-button')
    assert errors == []
    page.close()


def test_child_chart_live_inside_its_state(browser, tmp_path):
    setup = Setup(write_composed(tmp_path))
    try:
        page = browser.new_page()
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.goto(setup.url + '/#/demo')
        expect(page.locator('#diagram .cluster.child-chart[data-id="PROC"]')
               ).to_be_visible(timeout=15000)
        outer = page.locator('#diagram [data-id="PROC"] rect').first.bounding_box()
        for child in ('PROC/STEP1', 'PROC/STEP2', 'PROC/done'):
            inner = page.locator(f'#diagram [data-id="{child}"]').first.bounding_box()
            assert outer['x'] <= inner['x'] and outer['y'] <= inner['y'], child
            assert inner['x'] + inner['width'] <= outer['x'] + outer['width'], child
            assert inner['y'] + inner['height'] <= outer['y'] + outer['height'], child
        assert wait_for(lambda: active_ids(page) == {'IDLE'})
        for event, expected in (('go', {'PROC', 'PROC/STEP1'}),
                                ('next', {'PROC', 'PROC/STEP2'}),
                                ('next', {'DONE'})):
            page.select_option('#send-event', event)
            page.click('#send-form button')
            assert wait_for(lambda: active_ids(page) == expected), (event, active_ids(page))
        expect(page.locator('#log li').first).to_contain_text('done')
        assert errors == []
        page.close()
    finally:
        setup.close()


def test_bag_of_the_patrol_example_replays(browser, tmp_path):
    """Record the patrol example (fake Nav2) to a bag, then replay it into the viewer."""
    from nav2_util import Env, Script
    from sensor_msgs.msg import BatteryState
    import rclpy
    from rclpy.parameter import Parameter
    from statechart_ros_viewer.node import ViewerNode

    examples = os.path.join(HERE, '..', '..', 'statechart_ros_nav2', 'examples')
    bag = os.environ.get('VIEWER_BAG_DIR', str(tmp_path)) + '/patrol_bag'
    recorder = subprocess.Popen(
        ['ros2', 'bag', 'record', '-o', bag, '/patrol/structure', '/patrol/status',
         '/patrol/transitions'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2.0)
    env = Env()
    try:
        env.fake.active['lifecycle_manager_navigation'] = True
        h = env.chart_node(os.path.join(examples, 'patrol.scxml'), 'patrol', [
            ('named_poses', os.path.join(examples, 'sandbox_poses.yaml'))])
        battery = h.client_node.create_publisher(BatteryState, '/battery_state', 10)
        assert h.wait_config({'IDLE'}, 10.0)
        env.fake.scripts['navigate_to_pose'].append(Script(duration=0.3))
        env.fake.scripts['navigate_to_pose'].append(Script(duration=30.0))
        assert h.send('start').handled
        assert h.wait_config({'TO_B'}, 10.0)
        env.fake.scripts['dock_robot'].append(Script(duration=0.3))
        assert wait_for(lambda: battery.get_subscription_count() > 0)
        battery.publish(BatteryState(percentage=0.1))
        assert h.wait_config({'CHARGING'}, 10.0)
        assert h.send('pause').handled
        assert h.wait_config({'PAUSED', 'HOLD'}, 10.0)
        expected = set(h.node.runner.configuration())
        time.sleep(1.0)
    finally:
        # Stop recording before the chart is deactivated, which publishes an empty status.
        recorder.send_signal(signal.SIGINT)
        recorder.wait(timeout=20)
        env.close()

    rclpy.init()
    executor = rclpy.executors.MultiThreadedExecutor()
    viewer = ViewerNode(parameter_overrides=[Parameter('port', value=0),
                                             Parameter('address', value='127.0.0.1'),
                                             Parameter('discovery_period', value=0.2)])
    executor.add_node(viewer)
    threading.Thread(target=spin, args=(executor,), daemon=True).start()
    try:
        page = browser.new_page()
        page.goto(f'http://127.0.0.1:{viewer.port}/#/patrol')
        # The delay lets the viewer discover the player's topics before it publishes.
        player = subprocess.run(['ros2', 'bag', 'play', '--delay', '3', bag],
                                capture_output=True, timeout=120)
        assert player.returncode == 0, player.stderr
        expect(page.locator('#diagram [data-id="PATROL"]')).to_be_visible(timeout=15000)
        assert wait_for(lambda: active_ids(page) == expected, 15.0), active_ids(page)
        log = page.locator('#log li').all_inner_texts()
        assert any('start' in line for line in log)
        assert any('pause' in line for line in log)
        page.close()
    finally:
        executor.shutdown()
        viewer.destroy_node()
        rclpy.shutdown()
