# Copyright (c) 2001-2004 Twisted Matrix Laboratories.
# See LICENSE for details.


"""
This module provides support for Twisted to interact with the PyQt mainloop.

In order to use this support, simply do the following::

    |  from twisted.internet import qtreactor
    |  qtreactor.install()

Then use twisted.internet APIs as usual.  The other methods here are not
intended to be called directly.

API Stability: stable

Maintainer: U{Itamar Shtull-Trauring<mailto:twisted@itamarst.org>}
Port to QT4: U{Gabe Rudy<mailto:rudy@goldenhelix.com>}
"""


# System Imports
from PyQt4.QtCore import QSocketNotifier, QObject, SIGNAL, QTimer
from PyQt4.QtGui import QApplication
import sys

# Twisted Imports
from twisted.python import log, failure
from twisted.internet import posixbase

reads = {}
writes = {}
hasReader = reads.has_key
hasWriter = writes.has_key


class TwistedSocketNotifier(QSocketNotifier):
    '''Connection between an fd event and reader/writer callbacks'''

    def __init__(self, reactor, watcher, type):
        QSocketNotifier.__init__(self, watcher.fileno(), type)
        self.reactor = reactor
        self.watcher = watcher
        self.fn = None
        if type == QSocketNotifier.Read:
            self.fn = self.read
        elif type == QSocketNotifier.Write:
            self.fn = self.write
        QObject.connect(self, SIGNAL("activated(int)"), self.fn)

    def shutdown(self):
        QObject.disconnect(self, SIGNAL("activated(int)"), self.fn)
        self.setEnabled(0)
        self.fn = self.watcher = None

    def read(self, sock):
        why = None
        w = self.watcher
        try:
            log.msg('reading...')
            why = w.doRead()
        except:
            why = sys.exc_info()[1]
            log.msg('Error in %s.doRead()' % w)
            log.deferr()
        if why:
            self.reactor._disconnectSelectable(w, why, True)
        self.reactor.iterate()

    def write(self, sock):
        why = None
        w = self.watcher
        self.setEnabled(0)
        try:
            log.msg('writing...')
            why = w.doWrite()
        except:
            why = sys.exc_value
            log.msg('Error in %s.doWrite()' % w)
            log.deferr()
        if why:
            self.reactor.removeReader(w)
            self.reactor.removeWriter(w)
            try:
                w.connectionLost(failure.Failure(why))
            except:
                log.deferr()
        elif self.watcher:
            self.setEnabled(1)
        self.reactor.iterate()


class QTReactor(posixbase.PosixReactorBase):
    """Qt based reactor."""

    # Reference to a DelayedCall for self.crash() when the reactor is
    # entered through .iterate()
    _crashCall = None

    _timer = None

    def __init__(self, app=None):
        self.running = 0
        posixbase.PosixReactorBase.__init__(self)
        if app is None:
            app = QApplication([])
        self.qApp = app
        self.addSystemEventTrigger('after', 'shutdown', self.cleanup)

    def addReader(self, reader):
        if not hasReader(reader):
            log.msg("addReader...")
            reads[reader] = TwistedSocketNotifier(self, reader, QSocketNotifier.Read)

    def addWriter(self, writer):
        if not hasWriter(writer):
            log.msg("addWriter...")            
            writes[writer] = TwistedSocketNotifier(self, writer, QSocketNotifier.Write)

    def removeReader(self, reader):
        log.msg("removeReader...")
        if hasReader(reader):
            reads[reader].shutdown()
            del reads[reader]

    def removeWriter(self, writer):
        log.msg("removeWriter...")        
        if hasWriter(writer):
            writes[writer].shutdown()
            del writes[writer]

    def removeAll(self):
        return self._removeAll(reads, writes)
    
    def processQtEvents(self):
        self.qApp.processEvents()

    def simulate(self):
        if self._timer is not None:
            self._timer.stop()
            self._timer = None

#===============================================================================
#        if not self.running:
#            self.running = 1
#            self.qApp.exit_loop()
#            return
#        self.runUntilCurrent()
#===============================================================================

        #log.msg('entering runUntilCurrent')
        self.runUntilCurrent()
        #log.msg('leaving runUntilCurrent')

#===============================================================================
#        if self._crashCall is not None:
#            self._crashCall.reset(0)
#===============================================================================

        # gah
        timeout = self.timeout()
        if timeout is None:
            timeout = 1.0
        timeout = min(timeout, 0.1) * 1010
        
        #log.msg('scheduling: ' + str(timeout))

        if self._timer is None:
            self._timer = QTimer()
            QObject.connect(self._timer, SIGNAL("timeout()"), self.simulate)
        self._timer.start(timeout)

    def cleanup(self):
        if self._timer is not None:
            self._timer.stop()
            self._timer = None

    """ need this to update when simulate is called back in
    case its immediate or sooner """         
    def callLater(self,howlong, *args, **kargs):
        rval = super(QTReactor,self).callLater(howlong, *args, **kargs)
        if self._timer is not None:
            self._timer.stop()
            self._timer=None
        self._timer=QTimer()
        timeout = self.timeout()
        QObject.connect(self._timer, SIGNAL("timeout()"), self.simulate)
        self._timer.start(timeout)
        return rval

    def iterate(self, delay=0.0):
        #log.msg(channel='system', event='iteration', reactor=self)
        #self._crashCall = self.callLater(delay, self.crash)
        self.simulate()

    def returnRun(self, installSignalHandlers=1):
        self.running = 1
        self.startRunning(installSignalHandlers=installSignalHandlers)
        self.iterate()
        #self.qApp.exec_()

    def crash(self):
        if self._crashCall is not None:
            if self._crashCall.active():
                self._crashCall.cancel()
            self._crashCall = None
        self.running = 0


def install(app=None):
    """Configure the twisted mainloop to be run inside the qt mainloop.
    """
    from twisted.internet import main

    reactor = QTReactor(app=app)
    main.installReactor(reactor)

__all__ = ['install']