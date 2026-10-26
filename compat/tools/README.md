# SCXML tool compatibility runs

Scripts that measure what third-party SCXML tools do with the sample charts in
`compat/charts/` (documents with `ros:` extension elements and
`datamodel="python"`). Results go to `tmp/compat/` (logs `run.log` per tool,
saved documents under `out/`).

`make_variants.sh` writes, for each chart, the variants every runner uses
(into `tmp/compat/variants/`):

| Variant | `datamodel` | `ros:` elements |
|---|---|---|
| `python` | `python` (the chart as is) | kept |
| `null`, `ecmascript` | changed | kept |
| `null.plain`, `ecmascript.plain` | changed | removed (control) |
| `nodm`, `nodm.plain` | attribute removed (Commons SCXML 0.9) | kept / removed |

Comparing a variant with its `.plain` control isolates the effect of the
`ros:` elements from that of the datamodel.

## Runners and versions measured (2026-10-26)

| Tool | Version | Runner | Where |
|---|---|---|---|
| Qt SCXML | Qt 6.4.2 (`qt6-scxml-dev`, `libqt6scxml6-bin` 6.4.2-4build2, Ubuntu 24.04); `qscxmlc 2` | `qt/run_qt.sh` (`qscxmlc`, and `qt/qt_load.cpp`: `QScxmlStateMachine::fromFile`, start, send events) | Ubuntu 24.04 container |
| Apache Commons SCXML 2.0 | `commons-scxml2` 2.0-SNAPSHOT build `2.0-20260701.010636-103` (Apache snapshots repository; 2.0 was never released, no 2.0-M1 on Maven Central) with commons-jexl3 3.6.4, commons-logging 1.4.0, commons-io 2.22.0, jackson 2.20 | `commons/run_commons.sh` (`CommonsScxml2Load.java`: `SCXMLReader` strict and lenient, `SCXMLWriter`, `SCXMLExecutor`) | host, OpenJDK 11.0.32 |
| Apache Commons SCXML 0.9 | `commons-scxml` 0.9 (last release, 2008) with commons-digester 1.8, commons-beanutils 1.7.0, commons-jexl 1.1, xalan 2.7.3 | same script (`CommonsScxml09Load.java`: `SCXMLParser`, `SCXMLSerializer`, `SCXMLExecutor`) | host, OpenJDK 11.0.32 |
| scxmlgui | git `1e092023635b21e1d5e22820075d736b46c537fb`, prebuilt `extra/fsm-editor.jar` (built from `7ac73bc`, 2016-06-16) | `scxmlgui/run_scxmlgui.sh` (`ScxmlguiRoundTrip.java`: the editor's own `readInGraph` and `write`, headless) | host, OpenJDK 11.0.32 |
| AS2FM | not on PyPI; git `3252344093c2fb2a56d65449bb2000d167b99b85` (`OSS-release-deliverable-5.5-9-g3252344`), package version 0.0.1, in a venv | `as2fm/run_as2fm.sh` (`as2fm_load.py`: `ScxmlRoot.load_scxml_file`, `check_validity`, `to_plain_scxml`, `as_xml_string`) | Ubuntu 24.04 container, Python 3.12.3 |

Not run: Qt Creator's SCXML editor (graphical only; it has no command-line
load or save).

## Running

Qt and AS2FM ran in an Ubuntu 24.04 container with the repository mounted
at `/ws/src/ros2_statechart`:

```bash
sudo apt-get install -y qt6-scxml-dev libqt6scxml6-bin qt6-base-dev cmake g++ python3-venv
compat/tools/qt/run_qt.sh
compat/tools/as2fm/run_as2fm.sh       # clones AS2FM into tmp/compat, builds a venv
```

The Java runners need a JDK 11 (javac), curl and git:

```bash
compat/tools/commons/run_commons.sh   # downloads the jars (commons/fetch_jars.sh)
compat/tools/scxmlgui/run_scxmlgui.sh # clones scxmlgui into tmp/compat
```

`run_scxmlgui.sh` also checks each saved document against the W3C schema
when `xmllint` and the XSDs (`XSD_DIR`, default `statechart_ros/statechart_ros/schema/w3c/`) exist.
