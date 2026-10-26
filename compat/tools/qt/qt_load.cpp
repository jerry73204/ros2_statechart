// Copyright 2026 The ros2_statechart Authors
// SPDX-License-Identifier: Apache-2.0
//
// Loads an SCXML file with QScxmlStateMachine::fromFile, prints the parse
// errors, starts the machine, submits the events given on the command line
// one by one and prints the active leaf states after each step.
//
// usage: qt_load CHART.scxml [EVENT ...]

#include <QCoreApplication>
#include <QScxmlStateMachine>
#include <QScxmlError>
#include <QTimer>
#include <cstdio>

static void printActive(QScxmlStateMachine *m, const char *when) {
    std::printf("  active after %s: [%s]\n", when,
                qPrintable(m->activeStateNames(true).join(", ")));
}

int main(int argc, char **argv) {
    QCoreApplication app(argc, argv);
    if (argc < 2) { std::fprintf(stderr, "usage: qt_load CHART [EVENT ...]\n"); return 2; }
    QScxmlStateMachine *m = QScxmlStateMachine::fromFile(QString::fromLocal8Bit(argv[1]));
    const auto errors = m->parseErrors();
    std::printf("  parse errors: %d\n", int(errors.size()));
    for (const QScxmlError &e : errors)
        std::printf("    %s\n", qPrintable(e.toString()));
    if (!errors.isEmpty()) return 1;

    QStringList events;
    for (int i = 2; i < argc; ++i) events << QString::fromLocal8Bit(argv[i]);

    QObject::connect(m, &QScxmlStateMachine::log, [](const QString &l, const QString &msg) {
        std::printf("  log %s: %s\n", qPrintable(l), qPrintable(msg));
    });
    bool ok = m->init();
    std::printf("  init: %s\n", ok ? "ok" : "failed");
    m->start();
    // Let the machine settle, then feed events with an event-loop turn between them.
    int step = -1;
    QTimer timer;
    QObject::connect(&timer, &QTimer::timeout, [&]() {
        if (step == -1) { std::printf("  running: %s\n", m->isRunning() ? "yes" : "no"); printActive(m, "start"); }
        else { printActive(m, qPrintable("event " + events[step])); }
        ++step;
        if (step >= events.size()) { app.quit(); return; }
        m->submitEvent(events[step]);
    });
    timer.start(50);
    return app.exec();
}
