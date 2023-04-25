from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
import sys, subprocess, random, time, traceback

import faulthandler
faulthandler.enable(all_threads=True)

# https://www.pythonguis.com/tutorials/multithreading-pyqt-applications-qthreadpool/
class WorkerSignals(QObject):
    finished = pyqtSignal()
    error = pyqtSignal(tuple)
    result = pyqtSignal(object)
    progress = pyqtSignal(int)

class Worker(QRunnable):
    def __init__(self, fn, *args, **kwargs):
        super(Worker, self).__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    @pyqtSlot()
    def run(self):
        try:
            result = self.fn(*self.args, **self.kwargs)
        except:
            traceback.print_exc()
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
        else:
            self.signals.result.emit(result)
        finally:
            self.signals.finished.emit()

class MainWindow(QMainWindow):
    def __init__(self, *args, **kwargs):
        super(MainWindow, self).__init__(*args, **kwargs)

        # Setting up GUI here.
        self.setWindowTitle("TikTok puller")
        self.setWindowIcon(QIcon("icon.png"))
        self.layout = QGridLayout()
        self.download = QPushButton("Download")
        self.clear = QPushButton("Clear")
        self.count = QLineEdit(self, placeholderText="File count")
        self.syncCount = QCheckBox("File count sync")
        self.target = QTextEdit(self,
                                acceptRichText=False,
                                lineWrapMode=QTextEdit.WidgetWidth,
                                undoRedoEnabled=True,
                                placeholderText="URLs go here")
        self.status = QStatusBar()
        self.debugBoxLabel = QLabel("Debug screen")
        self.debugBox = QTextEdit(self,
                                readOnly=True,
                                acceptRichText=True,
                                lineWrapMode=QTextEdit.WidgetWidth)
        #self.debug = QCheckBox("Debug mode")

        # https://www.pythonguis.com/tutorials/pyqt-layouts/
        # https://stackoverflow.com/questions/61451279/how-does-setcolumnstretch-and-setrowstretch-works
        self.layout.addWidget(self.download, 0, 0)
        self.layout.addWidget(self.clear, 0, 1, 1, 2)   # 1 row, 2 columns
        self.layout.addWidget(self.count, 1, 1)
        self.layout.addWidget(self.syncCount, 1, 2)
        self.layout.addWidget(self.target, 1, 0, 2, 1)  # 2 rows, 1 column
        self.layout.addWidget(self.status, 2, 1)
        self.layout.addWidget(self.debugBoxLabel, 3, 0)
        self.layout.addWidget(self.debugBox, 4, 0, 1, 2) # 1 row, 2 columns)

        self.download.clicked.connect(self.doTheThing)
        self.clear.clicked.connect(self.cleanUp)
        w = QWidget(); w.setLayout(self.layout); self.setCentralWidget(w); self.show()
        self.threadpool = QThreadPool(); self.threadpool.setMaxThreadCount(1000)
        #print("Multithreading with maximum %d threads" % self.threadpool.maxThreadCount())

    # Depending on whether debug checkbox is checked the UI will look different.
    # Kept only for future reference because debug box is now always visible.
    #def debugUI(self):
    #    if self.debug.isChecked():
    #        self.debugBox = QTextEdit(self,
    #                                readOnly=True,
    #                                acceptRichText=True,
    #                                lineWrapMode=QTextEdit.WidgetWidth)
    #        self.layout.addWidget(self.debugBox, 3, 0, 1, 2)
    #    else:
    #        # https://stackoverflow.com/questions/5899826/pyqt-how-to-remove-a-widget
    #        self.layout.removeWidget(self.debugBox); self.debugBox.deleteLater()

    # One and the only worker function.
    def downloadVideo(self, url, t, cmd_str):
        _event = subprocess.run(cmd_str, shell=True, capture_output=True, text=True)

        return _event

    # Updating the status message once all threads finish.
    def thread_complete(self):
        if self.threadpool.activeThreadCount() == 0:
            self.enableButtons()
            self.status.showMessage("Nothing to do")
            # Convenience feature. Update the file count value with what the iterator has reached provided the sync count box is checked.
            if self.syncCount.isChecked():
                self.count.setText(str(self.t1))

    # Updating the debug box outside of any threads because otherwise there will be constant segmentation faults.
    def updateDebugBox(self, outcome):
        # yt-dlp developers do not consider cases when the tool would not override an existing file worthy of exiting with a non-0 code.
        # This is a workaround. First check if yt-dlp reported an already existing file, then validate everything else.
        if "has already been downloaded" in outcome.stdout:
            self.debugBox.insertHtml(str('<pre style="color: red">' + outcome.stdout + "</pre><br>"))
        elif outcome.returncode == 0:
            self.debugBox.insertHtml(str('<pre>' + outcome.stdout + "</pre><br>"))
        else:
            self.debugBox.insertHtml(str('<pre style="color: red">' + outcome.stderr + "</pre><br>"))
        #print (outcome)

    # Wrapper function around the worker function. Needed for managing GUI configuration and multithreading.
    def doTheThing(self):
        try:
            t = int(self.count.text()); self.disableButtons()   # no easy way to kill threads in pyqt5, so unless the window is closed you will have to wait
            for url in self.target.toPlainText().split("\n"):
                if url:
                    _cmd_str = f'yt-dlp -S res,ext:mp4:m4a -o "{t}.mp4" "{url}"'
                    worker = Worker(self.downloadVideo, url, t, _cmd_str)
                    worker.signals.result.connect(self.updateDebugBox)
                    worker.signals.finished.connect(self.thread_complete)
                    self.debugBox.insertHtml(f"<p><br>>>> Working with {url}<br>{(str(_cmd_str))}<br></p>")
                    self.status.showMessage("Work in progress"); outcome = self.threadpool.start(worker)
                    t += 1; self.t1 = t     # needed for updating the file count field
        except ValueError:
            self.debugBox.insertHtml(str('<pre style="color:red;">' + "ERROR: file count must be an integer." + "</pre><br>"))

    # Disabling and enabling all elements of GUI that should not be modified when threads are running.
    def disableButtons(self):
       self.download.setEnabled(False)
       self.clear.setEnabled(False)
       self.count.setReadOnly(True)

    def enableButtons(self):
        self.download.setEnabled(True)
        self.clear.setEnabled(True)
        self.count.setReadOnly(False)

    # Remove contents of all fields and wait for all threads to finish.
    def cleanUp(self):
        """
        Make the buttons inactive assuming some threads are still running.
        Prevents the user from starting new threads while the previous batch is still running.
        
        TODO: revisit the soundness of this approach; mayt be better to instead let the user
        create as many threads as he wants even while others are running.
        """
        if self.threadpool.activeThreadCount() != 0:
            self.disableButtons()
        self.target.clear()
        self.debugBox.clear()

def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    # https://stackoverflow.com/questions/2007103/how-can-i-disable-clear-of-clipboard-on-exit-of-pyqt-application
    clipboard = QApplication.clipboard(); event = QEvent(QEvent.Clipboard); QApplication.sendEvent(clipboard, event)
    app.exit(app.exec_())

if __name__ == "__main__":
    main()
