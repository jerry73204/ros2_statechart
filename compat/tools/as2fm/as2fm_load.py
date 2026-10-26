# Copyright 2026 The ros2_statechart Authors
# SPDX-License-Identifier: Apache-2.0
"""Load a chart with AS2FM's SCXML loader (ScxmlRoot.load_scxml_file), check
it, convert it to plain SCXML and write it back with as_xml_string.

usage: python as2fm_load.py CHART.scxml OUT.scxml
"""
import sys
import traceback

from as2fm.scxml_converter.scxml_entries.scxml_root import ScxmlRoot


def main(chart: str, out: str) -> int:
    try:
        root = ScxmlRoot.load_scxml_file(chart, {})
    except BaseException as e:  # AS2FM reports most errors with assert
        last = traceback.extract_tb(e.__traceback__)[-1]
        print(f"  load: {type(e).__name__}: {e} (at {last.name}, {last.filename.split('/as2fm/')[-1]}:{last.lineno})")
        return 1
    print("  load: ok, states:", [s.get_id() for s in root.get_states()])
    try:
        print("  check_validity:", root.check_validity())
        print("  is_plain_scxml:", root.is_plain_scxml())
        plain = root.to_plain_scxml()
        print("  to_plain_scxml: ok,", len(plain), "document(s)")
        xml = plain[0].as_xml_string()
    except BaseException as e:
        print(f"  convert/write: {type(e).__name__}: {e}")
        return 1
    with open(out, "w") as f:
        f.write(xml)
    print("  write: ok, ros: elements in output =", "yes" if "ros:" in xml or "ros2_statechart" in xml else "no",
          "| datamodel attribute in output =", xml.split("datamodel=")[1].split()[0] if "datamodel=" in xml else "none")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
