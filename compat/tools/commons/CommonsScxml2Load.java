// Copyright 2026 The ros2_statechart Authors
// SPDX-License-Identifier: Apache-2.0
//
// Apache Commons SCXML 2.0: reads a chart with SCXMLReader (lenient, then
// strict), writes it back with SCXMLWriter, runs it with SCXMLExecutor and
// fires the events given on the command line.
//
// usage: java -cp <jars>:. CommonsScxml2Load CHART.scxml OUT.scxml [EVENT ...]

import java.io.File;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.TreeSet;
import org.apache.commons.scxml2.EventBuilder;
import org.apache.commons.scxml2.SCXMLExecutor;
import org.apache.commons.scxml2.TriggerEvent;
import org.apache.commons.scxml2.io.SCXMLReader;
import org.apache.commons.scxml2.io.SCXMLWriter;
import org.apache.commons.scxml2.model.EnterableState;
import org.apache.commons.scxml2.model.SCXML;

public class CommonsScxml2Load {
    static String active(SCXMLExecutor ex) {
        TreeSet<String> ids = new TreeSet<>();
        for (EnterableState s : ex.getStatus().getStates()) ids.add(s.getId());
        return ids.toString();
    }

    static SCXML read(String path, boolean strict) {
        try {
            SCXMLReader.Configuration cfg = new SCXMLReader.Configuration();
            cfg.setStrict(strict);
            SCXML m = SCXMLReader.read(new File(path).toURI().toURL(), cfg);
            System.out.println("  read (strict=" + strict + "): ok, datamodel attribute = " + m.getDatamodelName());
            return m;
        } catch (Exception e) {
            System.out.println("  read (strict=" + strict + "): " + e.getClass().getSimpleName() + ": " + e.getMessage());
            return null;
        }
    }

    public static void main(String[] args) throws Exception {
        read(args[0], true);
        SCXML m = read(args[0], false);
        if (m == null) return;
        try {
            String out = SCXMLWriter.write(m);
            Files.write(Paths.get(args[1]), out.getBytes("UTF-8"));
            System.out.println("  write: ok, ros: elements in output = " + (out.contains("<ros:") ? "yes" : "no")
                + ", xmlns:ros declaration = " + (out.contains("xmlns:ros=") ? "yes" : "no"));
        } catch (Exception e) {
            System.out.println("  write: " + e.getClass().getSimpleName() + ": " + e.getMessage());
        }
        try {
            SCXMLExecutor ex = new SCXMLExecutor();
            ex.setStateMachine(m);
            ex.go();
            System.out.println("  run: started, active " + active(ex));
            for (int i = 2; i < args.length; i++) {
                ex.triggerEvent(new EventBuilder(args[i], TriggerEvent.SIGNAL_EVENT).build());
                System.out.println("  event " + args[i] + ": active " + active(ex));
            }
        } catch (Exception e) {
            System.out.println("  run: " + e.getClass().getSimpleName() + ": " + e.getMessage());
        }
    }
}
