// Copyright 2026 The ros2_statechart Authors
// SPDX-License-Identifier: Apache-2.0
//
// Apache Commons SCXML 0.9 (last released version): parses a chart with
// SCXMLParser, serializes it back with SCXMLSerializer, runs it with
// SCXMLExecutor (JEXL evaluator) and fires the events given on the command line.
//
// usage: java -cp <jars>:. CommonsScxml09Load CHART.scxml OUT.scxml [EVENT ...]

import java.io.File;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.TreeSet;
import org.apache.commons.scxml.SCXMLExecutor;
import org.apache.commons.scxml.TriggerEvent;
import org.apache.commons.scxml.env.SimpleDispatcher;
import org.apache.commons.scxml.env.SimpleErrorHandler;
import org.apache.commons.scxml.env.SimpleErrorReporter;
import org.apache.commons.scxml.env.jexl.JexlContext;
import org.apache.commons.scxml.env.jexl.JexlEvaluator;
import org.apache.commons.scxml.io.SCXMLParser;
import org.apache.commons.scxml.io.SCXMLSerializer;
import org.apache.commons.scxml.model.SCXML;
import org.apache.commons.scxml.model.TransitionTarget;

public class CommonsScxml09Load {
    static String active(SCXMLExecutor ex) {
        TreeSet<String> ids = new TreeSet<>();
        for (Object s : ex.getCurrentStatus().getStates()) ids.add(((TransitionTarget) s).getId());
        return ids.toString();
    }

    public static void main(String[] args) throws Exception {
        SCXML m;
        try {
            m = SCXMLParser.parse(new File(args[0]).toURI().toURL(), new SimpleErrorHandler(), new ArrayList());
            if (m == null) { System.out.println("  parse: returned null"); return; }
            System.out.println("  parse: ok");
        } catch (Exception e) {
            System.out.println("  parse: " + e.getClass().getSimpleName() + ": " + e.getMessage());
            return;
        }
        String out = SCXMLSerializer.serialize(m);
        Files.write(Paths.get(args[1]), out.getBytes("UTF-8"));
        System.out.println("  serialize: ok, ros: elements in output = " + (out.contains("<ros:") ? "yes" : "no")
                + ", xmlns:ros declaration = " + (out.contains("xmlns:ros=") ? "yes" : "no"));
        try {
            SCXMLExecutor ex = new SCXMLExecutor(new JexlEvaluator(), new SimpleDispatcher(), new SimpleErrorReporter());
            ex.setStateMachine(m);
            ex.setRootContext(new JexlContext());
            ex.go();
            System.out.println("  run: started, active " + active(ex));
            for (int i = 2; i < args.length; i++) {
                ex.triggerEvent(new TriggerEvent(args[i], TriggerEvent.SIGNAL_EVENT));
                System.out.println("  event " + args[i] + ": active " + active(ex));
            }
        } catch (Exception e) {
            System.out.println("  run: " + e.getClass().getSimpleName() + ": " + e.getMessage());
        }
    }
}
