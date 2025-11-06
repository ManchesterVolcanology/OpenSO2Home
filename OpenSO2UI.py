import os
import sys
import yaml
import logging
import traceback
import qdarktheme
import numpy as np
import pandas as pd
import xarray as xr
import pyqtgraph as pg
from functools import partial
from datetime import datetime
from PySide6.QtCore import Qt, QObject, Slot, Signal, QThread, QTime, QTimer
from PySide6.QtGui import QIcon, QFont, QAction
from PySide6.QtWidgets import (
    QMainWindow, QApplication, QGridLayout, QScrollArea, QWidget, QTabWidget,
    QTextEdit, QLineEdit, QComboBox, QCheckBox, QSpinBox, QDoubleSpinBox,
    QFileDialog, QToolBar, QFrame, QSplitter, QPlainTextEdit, QDialog,
    QLabel, QPushButton, QDateTimeEdit, QMessageBox, QFormLayout
)

from openso2gui.station import Station
from openso2gui.plume import calc_end_point
from openso2gui.gui_functions import SyncWorker

__version__ = '2.0'
__author__ = 'Ben Esse'

if not os.path.isdir('bin/'):
    os.makedirs('bin/')

COLORS = [
    '#1f77b4', '#ff7f0e', '#2ca02c', '#9467bd', '#8c564b',
    '#e377c2', '#7f7f7f', '#bcbd22', '#17becf'
]


# =============================================================================
# =============================================================================
# Setup logging
# =============================================================================
# =============================================================================

logger = logging.getLogger()

class Signaller(QObject):
    """Signaller object for logging from QThreads."""
    signal = Signal(str, logging.LogRecord)


class QtHandler(logging.Handler):
    """Handler object for handling logs from QThreads."""

    def __init__(self, slotfunc, *args, **kwargs):
        super(QtHandler, self).__init__(*args, **kwargs)
        self.signaller = Signaller()
        self.signaller.signal.connect(slotfunc)

    def emit(self, record):
        s = self.format(record)
        self.signaller.signal.emit(s, record)


# =============================================================================
# =============================================================================
# Main GUI Window
# =============================================================================
# =============================================================================

class MainWindow(QMainWindow):
    """View for the iFit GUI."""

    # Set log level colors
    LOGCOLORS = {
        logging.DEBUG: 'darkgrey',
        logging.INFO: 'darkgrey',
        logging.WARNING: 'orange',
        logging.ERROR: 'red',
        logging.CRITICAL: 'purple',
    }

    def __init__(self, app, *args, **kwargs):
        """View initialiser."""
        super(MainWindow, self).__init__(*args, **kwargs)
        self.app = app

        # Set the window properties
        self.setWindowTitle(f'OpenSO2 Home')
        self.statusBar().showMessage('Ready')
        self.setGeometry(40, 40, 1210, 700)

        # Set the window layout
        self.generalLayout = QGridLayout()
        self._centralWidget = QScrollArea()
        self.widget = QWidget()
        self.setCentralWidget(self._centralWidget)
        self.widget.setLayout(self.generalLayout)

        # Scroll Area Properties
        self._centralWidget.setWidgetResizable(True)
        self._centralWidget.setWidget(self.widget)

        # Setup widget stylesheets
        QTabWidget().setStyleSheet('QTabWidget { font-size: 18pt; }')

        # Create an empty dictionary to hold the GUI widgets
        self.widgets = Widgets()

        # Set the default theme
        self.theme = 'Dark'

        # Initialise an empty dictionary to hold the station information
        self.stations = {}

        # Build the GUI
        self._createApp()

        # Update widgets from loaded config file
        self.config = {}
        self.config_fname = None
        if os.path.isfile('bin/.config'):
            with open('bin/.config', 'r') as r:
                self.config_fname = r.readline().strip()
            self.loadConfig(fname=self.config_fname)

        # Update GUI theme
        if self.theme == 'Light':
            self.theme = 'Dark'
        elif self.theme == 'Dark':
            self.theme = 'Light'
        self.changeTheme()

    def _createApp(self):
        """Create the application."""
        """Build the main GUI."""
        # Generate actions
        # Save action
        saveAct = QAction(QIcon('icons/save.png'), '&Save', self)
        saveAct.setShortcut('Ctrl+S')
        saveAct.triggered.connect(partial(self.saveConfig, False))

        # Save As action
        saveasAct = QAction(QIcon('icons/saveas.png'), '&Save As', self)
        saveasAct.setShortcut('Ctrl+Shift+S')
        saveasAct.triggered.connect(partial(self.saveConfig, True))

        # Load action
        loadAct = QAction(QIcon('icons/open.png'), '&Load', self)
        loadAct.triggered.connect(partial(self.loadConfig, None))

        # Change theme action
        themeAct = QAction(QIcon('icons/theme.png'), '&Change Theme', self)
        themeAct.triggered.connect(self.changeTheme)

        # Add menubar
        menubar = self.menuBar()
        fileMenu = menubar.addMenu('&File')
        fileMenu.addAction(saveAct)
        fileMenu.addAction(saveasAct)
        fileMenu.addAction(loadAct)
        toolMenu = menubar.addMenu('&View')
        toolMenu.addAction(themeAct)
        toolMenu = menubar.addMenu('&Tools')

        # Create a toolbar
        toolBar = QToolBar("Main toolbar")
        self.addToolBar(toolBar)
        toolBar.addAction(saveAct)
        toolBar.addAction(saveasAct)
        toolBar.addAction(loadAct)
        toolBar.addAction(themeAct)

        # Create a frame to hold program controls
        self.controlFrame = QFrame()
        self.controlFrame.setFrameShape(QFrame.StyledPanel)

        # Create a frame to hold program outputs
        self.outputFrame = QFrame(self)
        self.outputFrame.setFrameShape(QFrame.StyledPanel)

        # Create a frame to hold graphs
        self.resultsFrame = QFrame(self)
        self.resultsFrame.setFrameShape(QFrame.StyledPanel)

        # Add splitters to allow for adjustment
        splitter1 = QSplitter(Qt.Horizontal)
        splitter1.addWidget(self.controlFrame)
        splitter1.addWidget(self.resultsFrame)

        splitter2 = QSplitter(Qt.Vertical)
        splitter2.addWidget(splitter1)
        splitter2.addWidget(self.outputFrame)

        # Pack the Frames and splitters
        self.generalLayout.addWidget(splitter2)

        # Create different input sections
        self._createControls()
        self._createLogs()
        self._createOutputs()

# =============================================================================
#   Generate the program controls
# =============================================================================

    def _createControls(self):
        """Create program control widgets."""
        # Create the layout
        layout = QGridLayout(self.controlFrame)
        layout.setAlignment(Qt.AlignTop)
        nrow = 0

        # Form the tab widget
        controlTabHolder = QTabWidget()
        volcTab = QWidget()
        controlTabHolder.addTab(volcTab, 'Volcano/Plume')
        qualTab = QWidget()
        controlTabHolder.addTab(qualTab, 'Quality Control')
        syncTab = QWidget()
        controlTabHolder.addTab(syncTab, 'Sync Controls')
        layout.addWidget(controlTabHolder, 0, 0)

        # Volcano =============================================================

        # Add voclano and plume controls
        volc_layout = QGridLayout(volcTab)
        nrow = 0

        header = QLabel('Volcano')
        header.setAlignment(Qt.AlignLeft)
        header.setFont(QFont('Ariel', 12))
        volc_layout.addWidget(header, nrow, 0, 1, 2)
        nrow += 1

        # Create inputs for the volcano latitude
        volc_layout.addWidget(QLabel('Volcano\nLatitude:'), nrow, 0)
        self.widgets['vlat'] = QLineEdit()
        volc_layout.addWidget(self.widgets['vlat'], nrow, 1)
        nrow += 1

        # Create inputs for the volcano longitude
        volc_layout.addWidget(QLabel('Volcano\nLongitutde:'), nrow, 0)
        self.widgets['vlon'] = QLineEdit()
        volc_layout.addWidget(self.widgets['vlon'], nrow, 1)
        nrow += 1

        volc_layout.addWidget(QHLine(), nrow, 0, 1, 10)
        nrow += 1

        # Plume ===============================================================

        header = QLabel('Default Plume Settings')
        header.setAlignment(Qt.AlignLeft)
        header.setFont(QFont('Ariel', 12))
        volc_layout.addWidget(header, nrow, 0, 1, 2)
        nrow += 1

        # Create input for the plume speed
        volc_layout.addWidget(QLabel('Plume Speed\n[m/s]:'), nrow, 0)
        self.widgets['plume_speed'] = QDoubleSpinBox()
        self.widgets['plume_speed'].setRange(-1000, 1000)
        self.widgets['plume_speed'].setValue(1.0)
        volc_layout.addWidget(self.widgets['plume_speed'], nrow, 1)
        nrow += 1

        # Create input for the plume direction
        volc_layout.addWidget(QLabel('Plume Direction\n[degrees]:'), nrow, 0)
        self.widgets['plume_dir'] = QDoubleSpinBox()
        self.widgets['plume_dir'].setRange(0, 360)
        self.widgets['plume_dir'].setValue(0.0)
        volc_layout.addWidget(self.widgets['plume_dir'], nrow, 1)

        self.widgets['scan_pair_flag'] = QCheckBox('Calc Plume\nLocation?')
        self.widgets['scan_pair_flag'].setToolTip(
            'Toggle whether plume location is calculated from paired scans')
        volc_layout.addWidget(self.widgets['scan_pair_flag'], nrow, 2, 2, 1)
        nrow += 1

        # Create input for the plume altitude
        volc_layout.addWidget(QLabel('Plume Altitude\n[m a.s.l.]:'), nrow, 0)
        self.widgets['plume_alt'] = QLineEdit('3000')  # QDoubleSpinBox()
        # self.widgets['plume_alt'].setRange(0, 100000)
        # self.widgets['plume_alt'].setValue(1000)
        volc_layout.addWidget(self.widgets['plume_alt'], nrow, 1)
        nrow += 1

        volc_layout.addWidget(QLabel('Scan Pair Time\nLimit (min):'), nrow, 0)
        self.widgets['scan_pair_time'] = QSpinBox()
        self.widgets['scan_pair_time'].setRange(0, 1440)
        self.widgets['scan_pair_time'].setValue(10)
        volc_layout.addWidget(self.widgets['scan_pair_time'], nrow, 1)
        nrow += 1

        volc_layout.setRowStretch(nrow, 10)

        # Quality Control =====================================================

        # Add controls for the scan quality control
        qual_layout = QGridLayout(qualTab)
        nrow = 0

        # Create input for the lower intensity limit
        qual_layout.addWidget(QLabel('Low Intensity limit:'), nrow, 0)
        self.widgets['lo_int_lim'] = QSpinBox()
        self.widgets['lo_int_lim'].setRange(0, 100000)
        self.widgets['lo_int_lim'].setValue(1000)
        qual_layout.addWidget(self.widgets['lo_int_lim'], nrow, 1)
        nrow += 1

        # Create input for the upper intensity limit
        qual_layout.addWidget(QLabel('High Intensity limit:'), nrow, 0)
        self.widgets['hi_int_lim'] = QSpinBox()
        self.widgets['hi_int_lim'].setRange(0, 100000)
        self.widgets['hi_int_lim'].setValue(60000)
        qual_layout.addWidget(self.widgets['hi_int_lim'], nrow, 1)
        nrow += 1

        # Create input for the lower SCD limit
        qual_layout.addWidget(QLabel('Low SO<sub>2</sub>\nSCD limit:'),
                              nrow, 0)
        self.widgets['lo_scd_lim'] = QLineEdit('-1e17')
        qual_layout.addWidget(self.widgets['lo_scd_lim'], nrow, 1)
        nrow += 1

        # Create input for the upper SCD limit
        qual_layout.addWidget(QLabel('High SO<sub>2</sub>\nSCD limit:'),
                              nrow, 0)
        self.widgets['hi_scd_lim'] = QLineEdit('1e20')
        qual_layout.addWidget(self.widgets['hi_scd_lim'], nrow, 1)
        nrow += 1

        qual_layout.setRowStretch(nrow, 10)

        # Sync Settings =======================================================

        # Add syncing controls
        sync_layout = QGridLayout(syncTab)
        nrow = 0

        sync_layout.addWidget(QLabel('Local Folder:'), nrow, 0)
        self.widgets['sync_folder'] = QLineEdit('Results')
        sync_layout.addWidget(self.widgets['sync_folder'], nrow, 1)
        btn = QPushButton('Browse')
        btn.clicked.connect(partial(
            self.browse, self, self.widgets['sync_folder'], 'folder', None
        ))
        sync_layout.addWidget(btn, nrow, 2)
        nrow += 1

        sync_layout.addWidget(QHLine(), nrow, 0, 1, 10)
        nrow += 1

        header = QLabel('Analysed Scan Files')
        header.setAlignment(Qt.AlignLeft)
        header.setFont(QFont('Ariel', 12))
        sync_layout.addWidget(header, nrow, 0, 1, 3)
        nrow += 1

        # Create widgets for the start and stop scan times
        sync_layout.addWidget(QLabel('Start Time\n(HH:MM):'), nrow, 0)
        self.widgets['sync_so2_start'] = QDateTimeEdit(displayFormat='HH:mm')
        sync_layout.addWidget(self.widgets['sync_so2_start'], nrow, 1)
        nrow += 1

        sync_layout.addWidget(QLabel('Stop Time\n(HH:MM):'), nrow, 0)
        self.widgets['sync_so2_stop'] = QDateTimeEdit(displayFormat='HH:mm')
        sync_layout.addWidget(self.widgets['sync_so2_stop'], nrow, 1)
        nrow += 1

        sync_layout.addWidget(QHLine(), nrow, 0, 1, 10)
        nrow += 1

        header = QLabel('Spectra Files')
        header.setAlignment(Qt.AlignLeft)
        header.setFont(QFont('Ariel', 12))
        sync_layout.addWidget(header, nrow, 0, 1, 3)
        nrow += 1

        # Create widgets for the start and stop scan times
        sync_layout.addWidget(QLabel('Start Time\n(HH:MM):'), nrow, 0)
        self.widgets['sync_spec_start'] = QDateTimeEdit(displayFormat='HH:mm')
        sync_layout.addWidget(self.widgets['sync_spec_start'], nrow, 1)
        nrow += 1

        sync_layout.addWidget(QLabel('Stop Time\n(HH:MM):'), nrow, 0)
        self.widgets['sync_spec_stop'] = QDateTimeEdit(displayFormat='HH:mm')
        sync_layout.addWidget(self.widgets['sync_spec_stop'], nrow, 1)
        nrow += 1

        sync_layout.addWidget(QHLine(), nrow, 0, 1, 10)
        nrow += 1

        sync_layout.addWidget(QLabel('Time\nInterval (s):'), nrow, 0)
        self.widgets['sync_interval'] = QSpinBox()
        self.widgets['sync_interval'].setRange(0, 86400)
        self.widgets['sync_interval'].setValue(30)
        sync_layout.addWidget(self.widgets['sync_interval'], nrow, 1)
        nrow += 1

        sync_layout.setRowStretch(nrow, 10)

# =============================================================================
#   Generate the program logs
# =============================================================================

    def _createLogs(self):
        """Generate GUI logs."""
        # Create the layout
        layout = QGridLayout(self.outputFrame)
        layout.setAlignment(Qt.AlignTop)

        # Create a textbox to display the program logs
        self.logBox = QPlainTextEdit(self)
        self.logBox.setReadOnly(True)
        formatter = logging.Formatter('%(asctime)s - %(message)s', '%H:%M:%S')
        self.handler = QtHandler(self.updateLog)
        self.handler.setFormatter(formatter)
        logger.addHandler(self.handler)
        logger.setLevel(logging.INFO)
        layout.addWidget(self.logBox, 2, 0, 1, 5)
        logger.info(f'Welcome to OpenSO2 v{__version__}!')

# =============================================================================
#   Generate the program outputs
# =============================================================================

    def _createOutputs(self):
        """Create program output widgets."""
        # Setup tab layout
        layout = QGridLayout(self.resultsFrame)

        # Form the tab widget
        self.stationTabHolder = QTabWidget()
        resultsTab = QWidget()
        self.stationTabHolder.addTab(resultsTab, 'Flux Results')

        # Add plots for overall results
        # Create the graphs
        graph_layout = QGridLayout(resultsTab)
        self.flux_graphwin = pg.GraphicsLayoutWidget(show=True)

        # Make the graphs
        x_axis = pg.DateAxisItem(utcOffset=0)
        ax0 = self.flux_graphwin.addPlot(
            row=0, col=0, colspan=2, axisItems={'bottom': x_axis}
        )
        x_axis = pg.DateAxisItem(utcOffset=0)
        ax1 = self.flux_graphwin.addPlot(
            row=1, col=0, axisItems={'bottom': x_axis}
        )
        x_axis = pg.DateAxisItem(utcOffset=0)
        ax2 = self.flux_graphwin.addPlot(
            row=1, col=1, axisItems={'bottom': x_axis}
        )
        self.flux_axes = [ax0, ax1, ax2]

        for ax in self.flux_axes:
            ax.setDownsampling(mode='peak')
            ax.setClipToView(True)
            # ax.showGrid(x=True, y=True)
            ax.setLabel('bottom', 'Time')

        # Add axis labels
        ax0.setLabel('left', 'SO2 Flux [kg/s]')
        ax1.setLabel('left', 'Plume Altitude [m]')
        ax2.setLabel('left', 'Plume Direction [deg]')
        self.flux_legend = ax0.addLegend()

        graph_layout.addWidget(self.flux_graphwin)

        # Add a tab for the map
        mapTab = QWidget()
        self.stationTabHolder.addTab(mapTab, 'Station Map')

        # Create the map axes
        map_layout = QGridLayout(mapTab)
        self.map_graphwin = pg.GraphicsLayoutWidget(show=True)
        self.map_ax = self.map_graphwin.addPlot(row=0, col=0)
        self.map_ax.setAspectLocked()
        self.map_ax.setDownsampling(mode='peak')
        self.map_ax.setClipToView(True)
        self.map_ax.showGrid(x=True, y=True)
        self.map_ax.setLabel('bottom', 'Time')

        # Create the plot of the volcano
        scatter = pg.ScatterPlotItem(
            size=20, pen=pg.mkPen(COLORS[6]), brush=pg.mkBrush('#d62728')
        )
        scatter.setToolTip("Volcano")
        line = pg.PlotCurveItem(pen=pg.mkPen('#d62728', width=2))
        arrow = pg.ArrowItem(
            pen=pg.mkPen('#d62728', width=2), tipAngle=45, baseAngle=25,
            brush=pg.mkBrush('#d62728')
        )
        line.setToolTip("Plume")
        arrow.setToolTip("Plume")
        self.map_ax.addItem(line)
        self.map_ax.addItem(arrow)
        self.map_ax.addItem(scatter)
        self.map_plots = {'volcano': [scatter, line, arrow]}

        # Connect changes in the volcano location to the plot
        self.widgets['vlat'].textChanged.connect(self.updateMap)
        self.widgets['vlon'].textChanged.connect(self.updateMap)
        self.widgets['plume_dir'].valueChanged.connect(self.updateMap)

        # Add axis labels
        self.map_ax.setLabel('left', 'Latitude [deg]')
        self.map_ax.setLabel('bottom', 'Longitude [deg]')

        map_layout.addWidget(self.map_graphwin)

        # Generate the colormap to use
        self.cmap = pg.colormap.get('viridis')

        # Initialise dictionaries to hold the station widgets
        self.station_log = {}
        self.station_so2_map = {}
        self.station_so2_data = {}
        self.station_cbar = {}
        self.station_axes = {}
        self.station_status = {}
        self.station_graphwin = {}
        self.flux_lines = {}
        self.station_widgets = {}

        # Add station tabs
        self.stationTabs = {}
        layout.addWidget(self.stationTabHolder, 0, 0, 1, 10)

        # Add a button to control syncing
        self.sync_button = QPushButton('Syncing OFF')
        self.sync_button.setStyleSheet("background-color: red")
        self.sync_button.clicked.connect(self.toggleSync)
        self.syncing = False
        layout.addWidget(self.sync_button, 1, 0)

        # Add a button to add a station
        self.add_station_btn = QPushButton('Add Station')
        self.add_station_btn.setFixedSize(150, 25)
        self.add_station_btn.clicked.connect(self.new_station)
        layout.addWidget(self.add_station_btn, 1, 1)

# =============================================================================
#   GUI settings
# =============================================================================

    def saveConfig(self, asksavepath=True):
        """Save the config file."""
        # Get the GUI configuration
        config = {}
        for label in self.widgets:
            config[label] = self.widgets.get(label)
        config['theme'] = self.theme

        # Add the station ssettings to the config
        config['stations'] = {}
        for name, station in self.stations.items():
            config['stations'][name] = {
                'com_info': station.com_info,
                'loc_info': station.loc_info,
                'sync_flag': station.sync_flag,
                'filter_spectra_flag': self.station_widgets[name][
                    'filter_spectra_flag'
                ].isChecked()
            }

        # Get save filename if required
        if asksavepath or self.config_fname is None:
            fname, _ = QFileDialog.getSaveFileName(
                self, 'Save Config', '', 'YAML (*.yml *.yaml);;All Files (*)'
            )
            # If valid, proceed. If not, return
            if fname != '' and fname is not None:
                self.config_fname = fname
            else:
                return

        # Write the config
        with open(self.config_fname, 'w') as outfile:
            yaml.dump(config, outfile)

        # Log the update
        logger.info(f'Config file saved to {self.config_fname}')

        # Save the path to the config file
        with open('bin/.config', 'w') as w:
            w.write(self.config_fname)

        self.config = config

    def loadConfig(self, fname=None):
        """Read the config file."""
        if fname is None:
            fname, _ = QFileDialog.getOpenFileName(
                self, 'Load Config', '', 'YAML (*.yml *.yaml);;All Files (*)'
            )

        # Open the config file
        try:
            with open(fname, 'r') as ymlfile:
                config = yaml.load(ymlfile, Loader=yaml.FullLoader)

            logger.info(f'Loading config from {self.config_fname}')

            # Apply each config setting
            for label, value in config.items():
                try:
                    if label == 'theme':
                        self.theme = value
                    elif label == 'stations':
                        for name in self.stations.copy().keys():
                            self.del_station(name)
                        for name, info in value.items():
                            self.newStation(name, **info)
                    else:
                        self.widgets.set(label, value)
                except Exception:
                    logger.warning(
                        f'Failed to load {label} from config file',
                        exc_info=True
                    )

            # Update the config file settings
            self.config_fname = fname
            with open('bin/.config', 'w') as w:
                w.write(self.config_fname)

        except FileNotFoundError:
            logger.warning(f'Unable to load config file {self.config_fname}')
            config = {}
        self.config = config
        return config

    # =========================================================================
    # Plotting Functions
    # =========================================================================

    def updateMap(self):
        """Update the volcano location."""
        try:
            x = float(self.widgets.get('vlon'))
            y = float(self.widgets.get('vlat'))
            az = self.widgets.get('plume_dir')
            ay, ax = calc_end_point([y, x], 5000, az)
            self.map_plots['volcano'][0].setData([x], [y])
            self.map_plots['volcano'][1].setData([x, ax], [y, ay])
            self.map_plots['volcano'][2].setPos(ax, ay)
            self.map_plots['volcano'][2].setStyle(angle=az+90)
        except ValueError:
            pass

    # =========================================================================
    # Station functions
    # =========================================================================

    def toggleSync(self):
        """Turn station syncing on and off."""
        # If syncing if ON, turn it OFF
        if self.syncing:
            self.sync_button.setText('Syncing OFF')
            self.sync_button.setStyleSheet("background-color: red")
            self.widgets['sync_interval'].setDisabled(False)
            self.widgets['sync_interval'].setStyleSheet("color: white")
            self.syncing = False
            self.syncTimer.stop()

        # If syncing is OFF, turn it ON
        else:
            self.sync_button.setText('Syncing ON')
            self.sync_button.setStyleSheet("background-color: green")
            self.syncing = True
            interval = self.widgets.get('sync_interval') * 1000
            self.widgets['sync_interval'].setDisabled(True)
            self.widgets['sync_interval'].setStyleSheet("color: darkGray")
            self._station_sync()
            self.syncTimer = QTimer(self)
            self.syncTimer.setInterval(interval)
            self.syncTimer.timeout.connect(self._station_sync)
            self.syncTimer.start()

    def _station_sync(self):

        # If the previous sync thread is still running, wait a cycle
        try:
            if self.syncThread.isRunning():
                return
        except AttributeError:
            pass

        # Pull the syncing times
        sync_so2_start = datetime.strptime(
            self.widgets.get('sync_so2_start'), "%H:%M").time()
        sync_so2_stop = datetime.strptime(
            self.widgets.get('sync_so2_stop'), "%H:%M").time()
        sync_spec_start = datetime.strptime(
            self.widgets.get('sync_spec_start'), "%H:%M").time()
        sync_spec_stop = datetime.strptime(
            self.widgets.get('sync_spec_stop'), "%H:%M").time()

        # Get the current time
        ts = datetime.now().time()

        # See if we are within the sync time windows
        sync_so2_flag = sync_so2_start < ts and ts < sync_so2_stop
        sync_spec_flag = sync_spec_start < ts and ts < sync_spec_stop

        # Apply relevant sync mode
        if sync_so2_flag and not sync_spec_flag:
            sync_mode = 'so2'
        if not sync_so2_flag and sync_spec_flag:
            sync_mode = 'spectra'
        if sync_so2_flag and sync_spec_flag:
            sync_mode = 'both'
        if not sync_so2_flag and not sync_spec_flag:
            logger.debug('Not within syncing time window')
            return

        logger.info('Beginning scanner sync')

        # Pull the results folder
        res_dir = self.widgets.get('sync_folder')
        if not os.path.isdir(res_dir):
            os.makedirs(res_dir)

        # Get today's date
        self.analysis_date = datetime.now().date()

        # Get the volcano location
        volc_loc = [
            float(self.widgets.get('vlat')),
            float(self.widgets.get('vlon'))
        ]

        # Get the wind speed
        wind_speed = self.widgets.get('plume_speed')

        # Get the default altitude and azimuth
        default_alt = float(self.widgets.get('plume_alt'))
        default_az = float(self.widgets.get('plume_dir'))

        # Get the scan pair time
        scan_pair_time = self.widgets.get('scan_pair_time')
        scan_pair_flag = self.widgets.get('scan_pair_flag')

        # Get the min/max scd and intensity values
        min_scd = float(self.widgets.get('lo_scd_lim'))
        max_scd = float(self.widgets.get('hi_scd_lim'))
        min_int = float(self.widgets.get('lo_int_lim'))
        max_int = float(self.widgets.get('hi_int_lim'))

        self.statusBar().showMessage('Syncing...')

        # Initialise the sync thread
        self.syncThread = QThread()
        self.syncWorker = SyncWorker(
            res_dir, self.stations, self.analysis_date, sync_mode, volc_loc,
            default_alt, default_az, wind_speed, scan_pair_time,
            scan_pair_flag, min_scd, max_scd, min_int, max_int
        )

        # Move the worker to the thread
        self.syncWorker.moveToThread(self.syncThread)

        # Connect the signals
        self.syncThread.started.connect(self.syncWorker.run)
        self.syncWorker.finished.connect(self.sync_finished)
        self.syncWorker.error.connect(self.update_error)
        self.syncWorker.updateLog.connect(self.update_station_log)
        self.syncWorker.updateStationStatus.connect(self.update_stat_status)
        self.syncWorker.updateGuiStatus.connect(self.update_gui_status)
        self.syncWorker.updatePlots.connect(self.update_scan_plot)
        self.syncWorker.updateFluxPlot.connect(self.update_flux_plots)
        self.syncWorker.finished.connect(self.syncThread.quit)

        # Start the flag
        self.syncThread.start()

    def newStation(self, name, com_info, loc_info, sync_flag,
                   filter_spectra_flag=False):
        """Add a new station to the GUI."""
        # Create the station object
        self.stations[name] = Station(
            name, com_info, loc_info, sync_flag, filter_spectra_flag
        )

        # Create the tab to hold the station widgets
        self.stationTabs[name] = QWidget()
        self.stationTabHolder.addTab(self.stationTabs[name], str(name))

        # Set up the station layout
        layout = QGridLayout(self.stationTabs[name])

        # Add a status notifier
        self.station_status[name] = QLabel('Status: -')
        coln = 0
        layout.addWidget(self.station_status[name], 0, coln)

        # Add checkbox to sync the station or not
        sync_flag = QLabel(f'Syncing: {sync_flag}')
        layout.addWidget(sync_flag, 1, coln)

        layout.addWidget(QVLine(), 0, coln+1, 2, 1)
        coln += 2

        # Add the station location
        stat_lat = f'{abs(loc_info["latitude"])}'
        if loc_info["latitude"] >= 0:
            stat_lat += u"\N{DEGREE SIGN}N"
        else:
            stat_lat += u"\N{DEGREE SIGN}S"
        stat_lon = f'{abs(loc_info["longitude"])}'
        if loc_info["longitude"] >= 0:
            stat_lon += u"\N{DEGREE SIGN}E"
        else:
            stat_lon += u"\N{DEGREE SIGN}W"
        stat_loc = QLabel(f'Location: {stat_lat}, {stat_lon}')
        layout.addWidget(stat_loc, 0, coln)

        # Add the station altitude
        stat_alt = QLabel(f'Altitude: {loc_info["altitude"]} m')
        layout.addWidget(stat_alt, 1, coln)

        layout.addWidget(QVLine(), 0, coln+1, 2, 1)
        coln += 2

        # Add the station orientation
        stat_az = QLabel(f'Orientation: {loc_info["azimuth"]}'
                         + u"\N{DEGREE SIGN}")
        layout.addWidget(stat_az, 0, coln)

        # Add option to filter the bad spectra from display
        filter_spectra_cb = QCheckBox('Hide bad\nspectra?')
        filter_spectra_cb.setChecked(filter_spectra_flag)
        layout.addWidget(filter_spectra_cb, 1, coln)
        filter_spectra_cb.stateChanged.connect(
            lambda: self.update_scan_plot(
                name,
                f'{self.widgets.get("sync_folder")}/{datetime.now().date()}'
            )
        )

        layout.addWidget(QVLine(), 0, coln+1, 2, 1)
        coln += 2

        # Add button to edit the station
        edit_btn = QPushButton('Edit Station')
        edit_btn.clicked.connect(lambda: self.edit_station(name))
        layout.addWidget(edit_btn, 0, coln)

        # Add button to delete the station
        close_btn = QPushButton('Delete Station')
        close_btn.clicked.connect(lambda: self.delStation(name))
        layout.addWidget(close_btn, 1, coln)
        coln += 1

        # Add the station widgets to a dictionary
        self.station_widgets[name] = {
            'loc': stat_loc,
            'az': stat_az,
            'sync_flag': sync_flag,
            'filter_spectra_flag': filter_spectra_cb
        }

        # Create the graphs
        self.station_graphwin[name] = pg.GraphicsLayoutWidget(show=True)
        pg.setConfigOptions(antialias=True)

        # Make the graphs
        ax0 = self.station_graphwin[name].addPlot(row=0, col=0)
        x_axis = pg.DateAxisItem(utcOffset=0)
        ax1 = self.station_graphwin[name].addPlot(
            row=0, col=1, axisItems={'bottom': x_axis}
        )
        self.station_axes[name] = [ax0, ax1]

        for ax in self.station_axes[name]:
            ax.setDownsampling(mode='peak')
            ax.setClipToView(True)
            ax.showGrid(x=True, y=True)

        # Add axis labels
        ax0.setLabel('left', 'SO2 SCD [molec/cm2]')
        ax1.setLabel('left', 'Scan Angle [deg]')
        ax0.setLabel('bottom', 'Scan Angle [deg]')
        ax1.setLabel('bottom', 'Time [UTC]')

        # Initialise the scatter plot
        so2_map = pg.ScatterPlotItem()
        ax1.addItem(so2_map)
        self.station_so2_map[name] = so2_map

        # Initialise the colorbar
        im = pg.ImageItem()
        cbar = pg.ColorBarItem(values=(0, 1e18), colorMap=self.cmap)
        cbar.setImageItem(im)
        cbar.sigLevelsChangeFinished.connect(
            lambda: self._update_map_colors(name))
        self.station_cbar[name] = cbar
        self.station_graphwin[name].addItem(self.station_cbar[name], 0, 2)

        # Create a textbox to hold the station logs
        self.station_log[name] = QPlainTextEdit(self)
        self.station_log[name].setReadOnly(True)
        self.station_log[name].setFont(QFont('Courier', 10))

        # Add overview plot lines
        stat_num = len(self.stations.keys())-1
        pen = pg.mkPen(color=COLORS[stat_num], width=2)
        fe0 = pg.ErrorBarItem(pen=pen)
        fl0 = pg.PlotCurveItem(pen=pen)
        fl1 = pg.PlotCurveItem(pen=pen)
        fl2 = pg.PlotCurveItem(pen=pen)
        self.flux_axes[0].addItem(fe0)
        self.flux_axes[0].addItem(fl0)
        self.flux_axes[1].addItem(fl1)
        self.flux_axes[2].addItem(fl2)
        self.flux_lines[name] = [fe0, fl0, fl1, fl2]
        self.flux_legend.addItem(fl0, name)

        # Add station to map plot
        scatter = pg.ScatterPlotItem(
            x=[loc_info['longitude']], y=[loc_info['latitude']],
            brush=pg.mkBrush(COLORS[stat_num]), size=15
        )
        line1 = pg.PlotCurveItem(pen=pg.mkPen(COLORS[stat_num], width=4))
        line2 = pg.PlotCurveItem(pen=pg.mkPen(COLORS[stat_num], width=2))
        arrow = pg.ArrowItem(baseAngle=25, brush=pg.mkBrush(COLORS[stat_num]))
        scatter.setToolTip(name)
        line1.setToolTip('+ve')
        line2.setToolTip('-ve')
        self.map_ax.addItem(scatter)
        self.map_ax.addItem(line1)
        self.map_ax.addItem(line2)
        self.map_ax.addItem(arrow)
        self.map_plots[name] = [scatter, line1, line2, arrow]
        self.update_station_map(name)

        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(self.station_graphwin[name])
        splitter.addWidget(self.station_log[name])
        layout.addWidget(splitter, 2, 0, 1, coln)

        logger.info(f'Added {name} station')

    def delStation(self, name):
        """Remove a station tab."""
        # Get the index of the station tab
        station_idx = [
            i for i, key in enumerate(self.stationTabs.keys())
            if name == key
        ][0] + 2

        # Remove the tab from the GUI
        self.stationTabHolder.removeTab(station_idx)

        # Delete the actual widget from memory
        self.stationTabs[name].setParent(None)

        # Remove the station from the stations dictionary
        self.stations.pop(name)

        # Remove the station from the flux legend
        self.flux_legend.removeItem(name)

        # Remove the station from the map
        for item in self.map_plots[name]:
            self.map_ax.removeItem(item)
        self.map_plots.pop(name)

        logger.info(f'Removed {name} station')

    def new_station(self):
        """Input new information for a station."""
        dialog = NewStationWizard(self)
        if dialog.exec():
            self.newStation(**dialog.station_info)

    def edit_station(self, name):
        """Edit information for a station."""
        station = self.stations[name]
        dialog = EditStationWizard(self, station)
        if dialog.exec():
            # Edit the station object
            self.stations[name] = dialog.station

            # Edit the text on the station tab
            loc_info = station.loc_info
            stat_lat = f'{abs(loc_info["latitude"])}'
            if loc_info["latitude"] >= 0:
                stat_lat += u"\N{DEGREE SIGN}N"
            else:
                stat_lat += u"\N{DEGREE SIGN}S"
            stat_lon = f'{abs(loc_info["longitude"])}'
            if loc_info["longitude"] >= 0:
                stat_lon += u"\N{DEGREE SIGN}E"
            else:
                stat_lon += u"\N{DEGREE SIGN}W"
            self.station_widgets[name]['loc'].setText(
                f'Location: {stat_lat}, {stat_lon}'
            )
            self.station_widgets[name]['az'].setText(
                f'Orientation: {loc_info["azimuth"]}' + u"\N{DEGREE SIGN}"
            )
            self.station_widgets[name]['sync_flag'].setText(
                f'Syncing: {station.sync_flag}'
            )

            # Update the station map
            self.update_station_map(name)

            logger.info(f'{name} station updated')

    def update_station_map(self, name):
        """Update station on the map."""
        loc_info = self.stations[name].loc_info

        x = loc_info['longitude']
        y = loc_info['latitude']
        az = loc_info['azimuth']
        y1, x1 = calc_end_point([y, x], 2500, az-90)
        y2, x2 = calc_end_point([y, x], 2500, az+90)
        self.map_plots[name][0].setData(x=[x], y=[y])
        self.map_plots[name][1].setData([x, x1], [y, y1])
        self.map_plots[name][2].setData([x, x2], [y, y2])
        self.map_plots[name][3].setPos(x, y)
        self.map_plots[name][3].setStyle(angle=az+90)


    # =========================================================================
    # Program Global Slots
    # =========================================================================

    @Slot(str, logging.LogRecord)
    def updateLog(self, status, record):
        """Write log statements to the logBox widget."""
        color = self.LOGCOLORS.get(record.levelno, 'black')
        s = '<pre><font color="%s">%s</font></pre>' % (color, status)
        self.logBox.appendHtml(s)

    def update_error(self, error):
        """Slot to update error messages from the worker."""
        exctype, value, trace = error
        logger.warning(f'Uncaught exception!\n{trace}')

    def sync_finished(self):
        """Signal end of sync."""
        logger.info('Sync complete')
        self.statusBar().showMessage('Ready')

    def update_gui_status(self, status):
        """Update the status."""
        self.statusBar().showMessage(status)

    def update_stat_status(self, name, time, status):
        """Update the station staus."""
        self.station_status[name].setText(f'Status: {status}')

    def update_station_log(self, station, log_text):
        """Slot to update the station logs."""
        text = self.station_log[station].toPlainText().split('\n')
        for line in log_text[len(text):]:
            self.station_log[station].appendPlainText(line.strip())

    def update_scan_plot(self, name, fpath):
        """Update the plots."""
        # Get the scans in the directory
        scan_fnames = os.listdir(f'{fpath}/{name}/so2')

        # Pull the filter spectra flag
        filter_spectra_flag = self.station_widgets[name][
            'filter_spectra_flag'
        ].isChecked()

        if len(scan_fnames) == 0:
            return

        # Clear the axes
        self.station_axes[name][0].clear()

        # Add a legend
        legend = self.station_axes[name][0].addLegend()
        labels = []

        # Read in the last 5 and plot
        for i, fname in enumerate(scan_fnames[-5:][::-1]):

            # Load the scan file, unpacking the angle and SO2 data
            with xr.open_dataset(f'{fpath}/{name}/so2/{fname}') as da:
                scan_df = da.to_dataframe()
                scan_df['angle'] = da.coords['angle']
                scan_df['time'] = pd.date_range(
                    da.attrs['scan_start_time'],
                    da.attrs['scan_end_time'],
                    da.attrs['specs_per_scan']
                )

            if i == 0:
                shape = [len(scan_fnames[-5:]), len(scan_df['angle'])]
                plotx = np.zeros(shape)
                ploty = np.zeros(shape)

            # Check if the scans should be filtered
            if filter_spectra_flag:
                mask = np.vstack([
                    scan_df['SO2'] < float(self.widgets.get('lo_scd_lim')),
                    scan_df['SO2'] > float(self.widgets.get('hi_scd_lim')),
                    scan_df['average_intensity'] < float(self.widgets.get('lo_int_lim')),
                    scan_df['average_intensity'] > float(self.widgets.get('hi_int_lim'))
                ]).any(axis=0)
                plotx[i] = scan_df['angle'].to_numpy()
                ploty[i] = np.where(mask, 0, scan_df['SO2'].to_numpy())
            else:
                plotx[i] = scan_df['angle'].to_numpy()
                ploty[i] = scan_df['SO2'].to_numpy()

            # Get the scan time from the filename to use as a label
            labels.append(f'{fname[9:11]}:{fname[11:13]}')

        # Replace any nans with zeros
        ploty = np.nan_to_num(ploty)

        for i in range(shape[0]):

            if i == 0:
                width = 4
            else:
                width = 2

            # Plot the line
            line = pg.PlotCurveItem(plotx[i], ploty[i],
                                    pen=pg.mkPen(color=COLORS[i], width=width))
            self.station_axes[name][0].addItem(line)
            legend.addItem(line, labels[i])

        scan_angle = np.full([len(scan_fnames), len(plotx[0])], np.nan)
        scan_time = np.full([len(scan_fnames), len(plotx[0])], np.nan)
        scan_so2 = np.full([len(scan_fnames), len(plotx[0])], np.nan)
        scan_int = np.full([len(scan_fnames), len(plotx[0])], np.nan)

        for i, fname in enumerate(scan_fnames):

            # Load the scan file, unpacking the angle and SO2 data
            with xr.open_dataset(f'{fpath}/{name}/so2/{fname}') as da:
                scan_df = da.to_dataframe()
                scan_df['angle'] = da.coords['angle']
                scan_df['time'] = pd.date_range(
                    da.attrs['scan_start_time'],
                    da.attrs['scan_end_time'],
                    da.attrs['specs_per_scan']
                )
            scan_angle[i] = scan_df['angle'].to_numpy()
            scan_so2[i] = scan_df['SO2'].to_numpy()
            scan_int[i] = scan_df['average_intensity']

            # Pull the time and convert to a unix timestamp
            for j, ts in enumerate(scan_df['time']):
                try:
                    ds = pd.Timedelta('1s')
                    ts_ux = (ts - pd.Timestamp("1970-01-01")) // ds
                    scan_time[i, j] = ts_ux
                except ValueError:
                    pass

        # Flatten the data
        scan_angle = scan_angle.flatten()
        scan_time = scan_time.flatten()
        scan_so2 = scan_so2.flatten()
        scan_int = scan_int.flatten()

        # Check if the scans should be filtered
        if filter_spectra_flag:
            mask = np.vstack([
                scan_so2 < float(self.widgets.get('lo_scd_lim')),
                scan_so2 > float(self.widgets.get('hi_scd_lim')),
                scan_int < float(self.widgets.get('lo_int_lim')),
                scan_int > float(self.widgets.get('hi_int_lim'))
            ]).any(axis=0)
            scan_so2 = np.where(mask, 0, scan_so2)

        self.station_so2_data[name] = scan_so2

        # # Get the colormap limits
        map_lo_lim, map_hi_lim = self.station_cbar[name].levels()

        # Normalise the data and convert to colors
        norm_values = (scan_so2 - map_lo_lim) / (map_hi_lim - map_lo_lim)
        np.nan_to_num(norm_values, copy=False)
        try:
            pens = [pg.mkPen(color=self.cmap.map(val))
                    for val in norm_values]
            brushes = [pg.mkBrush(color=self.cmap.map(val))
                       for val in norm_values]
        except AttributeError:
            pens = None
            brushes = None

        self.station_so2_map[name].setData(x=scan_time, y=scan_angle,
                                           pen=pens, brush=brushes)

    def _update_map_colors(self, name):
        try:
            scan_time, scan_angle = self.station_so2_map[name].getData()
            scan_so2 = self.station_so2_data[name]

            # Get the colormap limits
            map_lo_lim, map_hi_lim = self.station_cbar[name].levels()

            # Normalise the data and convert to colors
            norm_values = (scan_so2 - map_lo_lim) / (map_hi_lim - map_lo_lim)
            np.nan_to_num(norm_values, copy=False)

            pens = [pg.mkPen(color=self.cmap.map(val)) for val in norm_values]
            brushes = [pg.mkBrush(color=self.cmap.map(val))
                       for val in norm_values]

            self.station_so2_map[name].setData(x=scan_time, y=scan_angle,
                                               pen=pens, brush=brushes)
        except ValueError:
            pass

    def update_flux_plots(self):
        """Display the calculated fluxes."""
        resfpath = self.widgets.get('sync_folder')

        min_time = []
        max_time = []

        # Cycle through the stations
        for name, station in self.stations.items():

            # Get the flux output file
            flux_fpath = f'{resfpath}/{self.analysis_date}/{name}/' \
                         + f'{self.analysis_date}_{name}_fluxes.csv'

            # Read the flux file
            try:
                flux_df = pd.read_csv(flux_fpath, parse_dates=['Time [UTC]'])
            except FileNotFoundError:
                logger.warning(f'Flux file not found for {name}!')
                continue

            # Extract the data, converting to UNIX time for the x-axis
            xdata = np.array([t.timestamp() for t in flux_df['Time [UTC]']])
            flux = flux_df['Flux [kg/s]'].to_numpy()
            flux_err = flux_df['Flux Err [kg/s]'].to_numpy()
            plume_alt = flux_df['Plume Altitude [m]'].to_numpy()
            plume_dir = flux_df['Plume Direction [deg]'].to_numpy()

            # Also update the flux plots
            self.flux_lines[name][0].setData(x=xdata, y=flux, height=flux_err)
            self.flux_lines[name][1].setData(x=xdata, y=flux)
            self.flux_lines[name][2].setData(x=xdata, y=plume_alt)
            self.flux_lines[name][3].setData(x=xdata, y=plume_dir)

            try:
                min_time.append(np.nanmin(xdata))
                max_time.append(np.nanmax(xdata))
            except ValueError:
                pass

        # Scale the x-axis (avoids issues with stations without fluxes)
        try:
            xlim_lo = min(min_time)
            xlim_hi = min(max_time)
            for ax in self.flux_axes:
                ax.setXRange(xlim_lo, xlim_hi)
        except ValueError:
            pass

    @Slot(QWidget, str, list)
    def browse(self, widget, mode='single', filterstr=None):
        """Open native file dialogue."""
        # Check if specified file extensions
        if filterstr is not None:
            filterstr = filterstr + ';;All Files (*)'

        # Pick a single file to read
        if mode == 'single':
            fname, _ = QFileDialog.getOpenFileName(
                self, 'Select File', '', filterstr
            )

        elif mode == 'multi':
            fname, _ = QFileDialog.getOpenFileNames(
                self, 'Select Files', '', filterstr
            )

        elif mode == 'save':
            fname, _ = QFileDialog.getSaveFileName(
                self, 'Save As', '', filterstr
            )

        elif mode == 'folder':
            fname = QFileDialog.getExistingDirectory(
                self, 'Select Folder'
            )

        # Get current working directory
        cwd = os.getcwd() + '/'
        cwd = cwd.replace("\\", "/")

        # Update the relavant widget for a single file
        if type(fname) == str and fname != '':
            # if cwd in fname:
            #     fname = fname[len(cwd):]
            widget.setText(fname)

        # And for multiple files
        elif type(fname) == list and fname != []:
            for i, f in enumerate(fname):
                if cwd in f:
                    fname[i] = f[len(cwd):]
            widget.setText('\n'.join(fname))

    def changeTheme(self):
        """Change the theme."""
        if self.theme == 'Light':
            # Set overall style
            self.app.setStyleSheet(qdarktheme.load_stylesheet())
            bg_color = 'k'
            plotpen = pg.mkPen('darkgrey', width=1)
            self.theme = 'Dark'
        else:
            # Set overall style
            self.app.setStyleSheet(qdarktheme.load_stylesheet("light"))
            bg_color = 'w'
            plotpen = pg.mkPen('k', width=1)
            self.theme = 'Light'


# =============================================================================
# Spinbox classes
# =============================================================================

# Create a Spinbox object for ease
class DSpinBox(QDoubleSpinBox):
    """Object for generating custom float spinboxes."""

    def __init__(self, value, input_range=None, step=1.0):
        """Initialise."""
        super().__init__()
        if input_range is not None:
            self.setRange(*input_range)
        self.setValue(value)
        self.setSingleStep(step)


class SpinBox(QSpinBox):
    """Object for generating custom integer spinboxes."""

    def __init__(self, value, input_range):
        """Initialise."""
        super().__init__()
        self.setRange(*input_range)
        self.setValue(value)


# =============================================================================
# Spacer widgets
# =============================================================================

class QHLine(QFrame):
    """Horizontal line widget."""

    def __init__(self):
        """Initialize."""
        super(QHLine, self).__init__()
        self.setFrameShape(QFrame.HLine)
        self.setFrameShadow(QFrame.Sunken)


class QVLine(QFrame):
    """Horizontal line widget."""

    def __init__(self):
        """Initialize."""
        super(QVLine, self).__init__()
        self.setFrameShape(QFrame.VLine)
        self.setFrameShadow(QFrame.Sunken)


# =============================================================================
# Widgets Object
# =============================================================================

class Widgets(dict):
    """Object to allow easy config/info transfer with Qt Widgets."""

    def __init__(self):
        """Initialise."""
        super().__init__()

    def get(self, key):
        """Get the value of a widget."""
        if key not in self.keys():
            logger.warning(f'{key} widget not found!')
            return
        if type(self[key]) == QTextEdit:
            return self[key].toPlainText()
        elif type(self[key]) == QLineEdit:
            return self[key].text()
        elif type(self[key]) == QComboBox:
            return str(self[key].currentText())
        elif type(self[key]) == QCheckBox:
            return self[key].isChecked()
        elif type(self[key]) in [QSpinBox, QDoubleSpinBox, SpinBox, DSpinBox]:
            return self[key].value()
        elif isinstance(self[key], QDateTimeEdit):
            return self[key].time().toString('HH:mm')
        else:
            raise ValueError('Widget type not recognised!')

    def set(self, key, value):
        """Set the value of a widget."""
        if key not in self.keys():
            logger.warning(f'{key} widget not found!')
        elif type(self[key]) in [QTextEdit, QLineEdit]:
            self[key].setText(str(value))
        elif type(self[key]) == QComboBox:
            index = self[key].findText(value, Qt.MatchFixedString)
            if index >= 0:
                self[key].setCurrentIndex(index)
        elif type(self[key]) == QCheckBox:
            self[key].setChecked(value)
        elif type(self[key]) in [QSpinBox, SpinBox]:
            self[key].setValue(int(value))
        elif type(self[key]) in [QDoubleSpinBox, DSpinBox]:
            self[key].setValue(float(value))
        elif isinstance(self[key], QDateTimeEdit):
            return self[key].setTime(QTime.fromString(value, 'HH:mm'))
        else:
            raise ValueError('Widget type not recognised!')


class NewStationWizard(QDialog):
    """Opens a wizard to define a new station."""

    def __init__(self, parent=None):
        """Initialise the window."""
        super(NewStationWizard, self).__init__(parent)

        # Set the window properties
        self.setWindowTitle('Add new station')
        self.station_data = {}

        self._createApp()

    def _createApp(self):
        # Set the layout
        layout = QFormLayout()

        syncComboBox = QComboBox()
        syncComboBox.addItems(['True', 'False'])

        # Setup entry widgets
        self.widgets = {
            'Name': QLineEdit(),
            'Latitude': QLineEdit(),
            'Longitude': QLineEdit(),
            'Altitude': QLineEdit(),
            'Azimuth': QLineEdit(),
            'Syncing': syncComboBox,
            'Hostname': QLineEdit(),
            'Username': QLineEdit(),
            'Password': QLineEdit()
        }
        for key, item in self.widgets.items():
            layout.addRow(key + ':', item)

        # Add cancel and accept buttons
        cancel_btn = QPushButton('Cancel')
        cancel_btn.clicked.connect(self.cancel_action)
        accept_btn = QPushButton('Accept')
        accept_btn.clicked.connect(self.accept_action)
        layout.addRow(cancel_btn, accept_btn)

        self.setLayout(layout)

    def accept_action(self):
        """Record the station data and exit."""
        try:
            loc_info = {
                'latitude':  float(self.widgets['Latitude'].text()),
                'longitude': float(self.widgets['Longitude'].text()),
                'altitude':  float(self.widgets['Azimuth'].text()),
                'azimuth':   float(self.widgets['Azimuth'].text())
            }
            com_info = {
                'hostname': self.widgets['Hostname'].text(),
                'username': self.widgets['Username'].text(),
                'password': self.widgets['Password'].text()
            }
            if self.widgets['Syncing'].currentText() == 'True':
                sync_flag = True
            else:
                sync_flag = False
        except ValueError:
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Critical)
            msg.setText("Error adding station, please check input fields.")
            msg.setWindowTitle("Error!")
            msg.setDetailedText(traceback.format_exc())
            msg.setStandardButtons(QMessageBox.Ok)
            msg.exec()
            return

        self.station_info = {
            'name': self.widgets['Name'].text(),
            'loc_info': loc_info,
            'com_info': com_info,
            'sync_flag': sync_flag
        }
        self.accept()

    def cancel_action(self):
        """Close the window without creating a new station."""
        self.station_info = {}
        self.close()


class EditStationWizard(QDialog):
    """Opens a wizard to define a new station."""

    def __init__(self, parent=None, station=None):
        """Initialise the window."""
        super(EditStationWizard, self).__init__(parent)

        # Set the window properties
        self.setWindowTitle(f'Edit {station.name} station')
        self.station = station
        self.loc_info = station.loc_info
        self.com_info = station.com_info
        self.sync_flag = station.sync_flag
        self.station_data = {}

        self._createApp()

    def _createApp(self):
        # Set the layout
        layout = QFormLayout()

        # Create sync flag widget
        syncComboBox = QComboBox()
        syncComboBox.addItems(['True', 'False'])
        index = syncComboBox.findText(str(self.sync_flag), Qt.MatchFixedString)
        if index >= 0:
            syncComboBox.setCurrentIndex(index)

        # Setup entry widgets
        self.widgets = {
            'Name': QLineEdit(str(self.station.name)),
            'Latitude': QLineEdit(str(self.loc_info['latitude'])),
            'Longitude': QLineEdit(str(self.loc_info['longitude'])),
            'Altitude': QLineEdit(str(self.loc_info['altitude'])),
            'Azimuth': QLineEdit(str(self.loc_info['azimuth'])),
            'Syncing': syncComboBox,
            'Hostname': QLineEdit(str(self.com_info['hostname'])),
            'Username': QLineEdit(str(self.com_info['username'])),
            'Password': QLineEdit(str(self.com_info['password']))}
        for key, item in self.widgets.items():
            layout.addRow(key + ':', item)

        # Add cancel and accept buttons
        cancel_btn = QPushButton('Cancel')
        cancel_btn.clicked.connect(self.cancel_action)
        accept_btn = QPushButton('Accept')
        accept_btn.clicked.connect(self.accept_action)
        layout.addRow(cancel_btn, accept_btn)

        self.setLayout(layout)

    def accept_action(self):
        """Record the station data and exit."""
        try:
            loc_info = {
                'latitude':  float(self.widgets['Latitude'].text()),
                'longitude': float(self.widgets['Longitude'].text()),
                'altitude':  float(self.widgets['Azimuth'].text()),
                'azimuth':   float(self.widgets['Azimuth'].text())
            }
            com_info = {
                'hostname': self.widgets['Hostname'].text(),
                'username': self.widgets['Username'].text(),
                'password': self.widgets['Password'].text()
            }
            if self.widgets['Syncing'].currentText() == 'True':
                sync_flag = True
            else:
                sync_flag = False
        except ValueError:
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Critical)
            msg.setText("Error adding station, please check input fields.")
            msg.setWindowTitle("Error!")
            msg.setDetailedText(traceback.format_exc())
            msg.setStandardButtons(QMessageBox.Ok)
            msg.exec()
            return

        self.station.name = self.widgets['Name'].text()
        self.station.loc_info = loc_info
        self.station.com_info = com_info
        self.station.sync_flag = sync_flag
        self.accept()

    def cancel_action(self):
        """Close the window without editing the station."""
        self.close()


# Cliet Code
if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow(app)
    window.show()
    sys.exit(app.exec())