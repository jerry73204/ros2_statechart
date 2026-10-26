// Copyright 2026 The ros2_statechart Authors
// SPDX-License-Identifier: Apache-2.0
//
// scxmlgui without its window: does what the editor's command-line convert
// mode does (start the editor with no GUI, SCXMLImportExport.readInGraph),
// then saves the graph with SCXMLImportExport.write, the editor's "Save" path,
// and lists the vertices that were read.
//
// usage: java -Djava.awt.headless=true -cp fsm-editor.jar:. ScxmlguiRoundTrip CHART.scxml OUT.scxml

import com.mxgraph.examples.swing.SCXMLGraphEditor;
import com.mxgraph.examples.swing.editor.fileimportexport.SCXMLImportExport;
import com.mxgraph.examples.swing.editor.fileimportexport.SCXMLNode;
import com.mxgraph.examples.swing.editor.scxml.SCXMLGraph;
import com.mxgraph.examples.swing.editor.scxml.SCXMLGraphComponent;
import com.mxgraph.model.mxCell;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;

public class ScxmlguiRoundTrip {
    static void collect(mxCell c, List<String> out) {
        if (c.isVertex() && c.getValue() instanceof SCXMLNode) {
            SCXMLNode n = (SCXMLNode) c.getValue();
            String other = n.getScript();
            out.add(n.getID() + (other != null && !other.trim().isEmpty() ? " (other content kept: " + other.replaceAll("\\s+", " ").trim() + ")" : ""));
        }
        for (int i = 0; i < c.getChildCount(); i++) collect((mxCell) c.getChildAt(i), out);
    }

    public static void main(String[] args) {
        int rc = 0;
        try {
            SCXMLGraphEditor editor = SCXMLGraphEditor.startEditor(true);
            SCXMLGraphComponent gc = editor.getGraphComponent();
            SCXMLGraph graph = gc.getGraph();
            SCXMLImportExport ie = new SCXMLImportExport();
            ie.readInGraph(graph, args[0], true, editor.getRestrictedStatesConfig());
            List<String> v = new ArrayList<>();
            collect((mxCell) graph.getModel().getRoot(), v);
            System.out.println("  read: ok, vertices:");
            for (String s : v) System.out.println("    " + s);
            ie.write(gc, args[1]);
            String out = new String(Files.readAllBytes(Paths.get(args[1])), "UTF-8");
            System.out.println("  write: ok, ros: elements in output = " + (out.contains("<ros:") ? "yes" : "no")
                + ", xmlns:ros declaration = " + (out.contains("xmlns:ros=") ? "yes" : "no")
                + ", datamodel attribute = " + (out.contains("datamodel=") ? out.split("datamodel=")[1].split("[\\s>]")[0] : "none"));
        } catch (Throwable e) {
            System.out.println("  error: " + e);
            rc = 1;
        }
        System.exit(rc);  // the editor starts non-daemon threads
    }
}
